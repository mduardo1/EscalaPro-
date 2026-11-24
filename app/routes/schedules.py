from calendar import Calendar
from datetime import timedelta

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from app.models.employee import list_employees
from app.models.schedule import get_schedule, list_schedules, list_unavailabilities
from app.models.settings import get_settings
from app.models.shift import list_shifts
from app.security import login_required
from app.services.schedule_service import (
    add_unavailability,
    remove_assignment,
    remove_unavailability,
    save_assignment,
    week_alerts,
    week_period,
    month_period,
    month_alerts,
    MONTH_NAMES,
)
from app.services.clock import local_now
from app.services.validation import MAX_DATE, MIN_DATE, date_value

bp = Blueprint("schedules", __name__, url_prefix="/schedules")


def selected_week():
    try:
        return week_period(request.args.get("week", local_now().date().isoformat()))
    except ValueError as exc:
        abort(400, description=str(exc))


def selected_period(default_day=None):
    if "week" in request.args and "month" not in request.args:
        return "week", *selected_week()
    value = request.args.get(
        "month", (default_day or local_now().date().isoformat())[:7]
    )
    try:
        return "month", *month_period(value)
    except ValueError as exc:
        abort(400, description=str(exc))


def period_args(view, day):
    return {"month": day[:7]} if view == "month" else {"week": day}


def render_calendar(
    view, start, end, assignment=None, submitted=None, unavailable_form=None
):
    today = local_now().date()
    default_day = (
        today if start.date() <= today < end.date() else max(start.date(), MIN_DATE)
    )
    if assignment:
        assignment_day = date_value(assignment["work_date"])
        # Uma continuação noturna pode começar no período anterior.
        if (
            assignment["start_at"] < end.isoformat()
            and assignment["end_at"] > start.isoformat()
        ):
            default_day = max(assignment_day, start.date(), MIN_DATE)
    try:
        selected_day = date_value(request.args.get("day", default_day.isoformat()))
    except ValueError as exc:
        abort(400, description=str(exc))
    if not start.date() <= selected_day < end.date():
        abort(400, description="Selecione uma data do período exibido.")
    rows = list_schedules(start.isoformat(), end.isoformat())
    days = [start + timedelta(days=i) for i in range((end - start).days)]
    events_by_day = {
        day.date().isoformat(): [
            row
            for row in rows
            if row["start_at"] < (day + timedelta(days=1)).isoformat()
            and row["end_at"] > day.isoformat()
        ]
        for day in days
    }
    previous_day = start - timedelta(days=1 if view == "month" else 7)
    return render_template(
        "schedules/index.html",
        title="Escalas",
        schedules=rows,
        days=days,
        view=view,
        period_args=period_args(view, start.date().isoformat()),
        month_label=f"{MONTH_NAMES[start.month - 1]} de {start.year}",
        calendar_weeks=Calendar(firstweekday=0).monthdayscalendar(
            start.year, start.month
        ),
        events_by_day=events_by_day,
        selected_events=events_by_day[selected_day.isoformat()],
        today=today.isoformat(),
        selected_date=selected_day,
        start=start,
        end=end,
        previous=(
            (
                previous_day.strftime("%Y-%m")
                if view == "month"
                else previous_day.date().isoformat()
            )
            if start.date() > MIN_DATE
            else None
        ),
        following=(
            (end.strftime("%Y-%m") if view == "month" else end.date().isoformat())
            if end.date() <= MAX_DATE
            else None
        ),
        min_date=MIN_DATE,
        max_date=MAX_DATE,
        employees=list_employees(active_only=True),
        all_employees=list_employees(),
        shifts=list_shifts(),
        assignment=assignment,
        form=submitted if submitted is not None else assignment,
        selected_day=selected_day.isoformat(),
        alerts=month_alerts(start, end) if view == "month" else week_alerts(start, end),
        unavailable=list_unavailabilities(),
        unavailable_form=unavailable_form,
    )


@bp.route("/", methods=["GET", "POST"])
@bp.route("/<dbid:schedule_id>/edit", methods=["GET", "POST"])
@login_required
def index(schedule_id=None):
    assignment = get_schedule(schedule_id) if schedule_id else None
    if schedule_id and assignment is None:
        abort(404)
    view, start, end = selected_period(assignment["work_date"] if assignment else None)
    if request.method == "POST":
        try:
            alerts = save_assignment(request.form, schedule_id)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_calendar(view, start, end, assignment, request.form), 422
        flash("Atribuição salva.", "success")
        if alerts:
            # Detalhes permanecem no calendário; o cookie tem espaço limitado.
            flash(alerts[0][:240], "warning")
            if len(alerts) > 1:
                flash(
                    f"Mais {len(alerts) - 1} alerta(s). Consulte as semanas afetadas na escala.",
                    "warning",
                )
        return redirect(
            url_for(
                "schedules.index",
                **period_args(view, request.form["work_date"]),
                day=request.form["work_date"],
            )
        )
    return render_calendar(view, start, end, assignment)


@bp.post("/<dbid:schedule_id>/delete")
@login_required
def delete(schedule_id):
    row = get_schedule(schedule_id)
    if row is None:
        abort(404)
    view, _, _ = selected_period(row["work_date"])
    remove_assignment(schedule_id)
    flash("Atribuição removida.", "success")
    return redirect(
        url_for(
            "schedules.index",
            **period_args(view, row["work_date"]),
            day=row["work_date"],
        )
    )


@bp.post("/unavailability")
@login_required
def unavailability():
    view, start, end = selected_period()
    try:
        add_unavailability(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return render_calendar(view, start, end, unavailable_form=request.form), 422
    flash("Indisponibilidade cadastrada.", "success")
    return redirect(
        url_for(
            "schedules.index",
            **period_args(view, max(start.date(), MIN_DATE).isoformat()),
        )
    )


@bp.post("/unavailability/<dbid:record_id>/delete")
@login_required
def delete_unavailability(record_id):
    view, start, _ = selected_period()
    if not remove_unavailability(record_id):
        abort(404)
    flash("Indisponibilidade removida.", "success")
    return redirect(
        url_for(
            "schedules.index",
            **period_args(view, max(start.date(), MIN_DATE).isoformat()),
        )
    )


@bp.get("/export.pdf")
@login_required
def export():
    from app.services.pdf_service import monthly_pdf, weekly_pdf

    view, start, end = selected_period()
    rows = list_schedules(start.isoformat(), end.isoformat())
    return send_file(
        (monthly_pdf if view == "month" else weekly_pdf)(
            get_settings()["company_name"], start, end, rows
        ),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"escalapro-{start.strftime('%Y-%m') if view == 'month' else start.strftime('%Y-%m-%d')}.pdf",
        max_age=0,
    )
