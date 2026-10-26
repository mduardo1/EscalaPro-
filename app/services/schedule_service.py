from datetime import datetime, time, timedelta

from app.database import get_db, parameters, begin_write, lock_employees, lock_schedule
from app.tenant import company_id
from app.models.employee import get_employee
from app.models.schedule import (
    employee_schedules,
    get_schedule,
    list_schedules,
    list_unavailabilities,
)
from app.models.shift import get_shift
from app.models.settings import get_settings
from app.services.schedule_validator import (
    collect_alerts,
    shift_period,
    validate_conflicts,
)
from app.services.validation import (
    MIN_DATE,
    date_value,
    datetime_value,
    number_value,
    text_value,
)


def week_period(value):
    # A primeira semana começa em dezembro de 1999, embora as atribuições
    # continuem restritas a datas a partir de 01/01/2000.
    day = date_value(value, minimum=MIN_DATE - timedelta(days=MIN_DATE.weekday()))
    monday = day - timedelta(days=day.weekday())
    start = datetime.combine(monday, time.min)
    return start, start + timedelta(days=7)


def week_alerts(start, end):
    # Até 72h de descanso configurável; 4 dias também cobrem um turno noturno anterior.
    rows = list_schedules((start - timedelta(days=4)).isoformat(), end.isoformat())
    return collect_alerts(rows, get_settings(), start, end)


def save_assignment(form, schedule_id=None):
    employee_id = number_value(
        form.get("employee_id"), "Funcionário", 1, 2**63 - 1, integer=True
    )
    shift_id = number_value(form.get("shift_id"), "Turno", 1, 2**63 - 1, integer=True)
    day = date_value(form.get("work_date"))
    db = get_db()
    # Serializa validação e escrita para impedir conflitos em requisições simultâneas.
    begin_write()
    try:
        lock_schedule(schedule_id)
        previous = get_schedule(schedule_id) if schedule_id else None
        lock_employees([employee_id] + ([previous["employee_id"]] if previous else []))
        employee, shift = get_employee(employee_id), get_shift(shift_id)
        if employee is None or not employee["active"]:
            raise ValueError("Selecione um funcionário ativo.")
        if shift is None:
            raise ValueError("Selecione um turno válido.")
        if schedule_id is not None and get_schedule(schedule_id) is None:
            raise ValueError("Atribuição não encontrada.")
        existing_assignments = employee_schedules(employee_id, schedule_id or 0)
        if any(
            row["shift_id"] == shift_id and row["work_date"] == day.isoformat()
            for row in existing_assignments
        ):
            raise ValueError(
                "Conflito: este turno já foi atribuído ao funcionário nessa data. Edite a atribuição existente."
            )
        start, end = shift_period(day, shift)
        validate_conflicts(
            start,
            end,
            existing_assignments,
            list_unavailabilities(employee_id),
        )
        values = (
            employee_id,
            shift_id,
            day.isoformat(),
            start.isoformat(),
            end.isoformat(),
            shift["name"],
            shift["break_minutes"],
            shift["color"],
            company_id(),
        )
        if schedule_id is None:
            db.execute(
                "INSERT INTO schedules(employee_id,shift_id,work_date,start_at,end_at,shift_name,break_minutes,color,company_id) VALUES(:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8)",
                parameters(values),
            )
        else:
            db.execute(
                "UPDATE schedules SET employee_id=:p0,shift_id=:p1,work_date=:p2,start_at=:p3,end_at=:p4,shift_name=:p5,break_minutes=:p6,color=:p7 WHERE company_id=:p8 AND id=:p9",
                parameters((*values, schedule_id)),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    first_week, _ = week_period(day.isoformat())
    affected_weeks = {first_week}
    following_week = first_week + timedelta(days=7)
    if end > following_week:
        affected_weeks.add(following_week)

    # Uma inclusão anterior pode reduzir o descanso de uma escala já existente
    # na próxima semana, mesmo quando o novo turno termina no domingo.
    rest_window = timedelta(hours=get_settings()["min_rest_hours"])
    for row in employee_schedules(employee_id):
        other_start = datetime.fromisoformat(row["start_at"])
        if end <= other_start < end + rest_window:
            affected_weeks.add(week_period(row["work_date"])[0])
    return [
        f"Semana de {week_start:%d/%m/%Y}: {alert}"
        for week_start in sorted(affected_weeks)
        for alert in week_alerts(week_start, week_start + timedelta(days=7))
    ]


def remove_assignment(schedule_id):
    db = get_db()
    db.execute(
        "DELETE FROM schedules WHERE id=:p0 AND company_id=:p1",
        parameters((schedule_id, company_id())),
    )
    db.commit()


def add_unavailability(form):
    employee_id = number_value(
        form.get("employee_id"), "Funcionário", 1, 2**63 - 1, integer=True
    )
    start = datetime_value(form.get("start_at"))
    end = datetime_value(form.get("end_at"))
    reason = text_value(form.get("reason", ""), "Motivo", 2, 120)
    if end <= start:
        raise ValueError("O fim da indisponibilidade deve ser posterior ao início.")
    db = get_db()
    begin_write()
    try:
        lock_employees([employee_id])
        if get_employee(employee_id) is None:
            raise ValueError("Funcionário não encontrado.")
        validate_conflicts(
            start,
            end,
            employee_schedules(employee_id),
            list_unavailabilities(employee_id),
        )
        db.execute(
            "INSERT INTO unavailabilities(employee_id,start_at,end_at,reason,company_id) VALUES(:p0,:p1,:p2,:p3,:p4)",
            parameters(
                (employee_id, start.isoformat(), end.isoformat(), reason, company_id())
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def remove_unavailability(record_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM unavailabilities WHERE id=:p0 AND company_id=:p1",
        parameters((record_id, company_id())),
    )
    db.commit()
    return cursor.rowcount > 0
