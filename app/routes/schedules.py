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
)
from app.services.clock import local_now
from app.services.validation import MAX_DATE, MIN_DATE, date_value

bp = Blueprint("schedules", __name__, url_prefix="/schedules")


def selected_week():
    try:
        return week_period(request.args.get("week", local_now().date().isoformat()))
    except ValueError as exc:
        abort(400, description=str(exc))


def render_week(start, end, assignment=None, submitted=None, unavailable_form=None):
    try:
        selected_day = date_value(
            request.args.get("day", max(start.date(), MIN_DATE).isoformat())
        )
    except ValueError as exc:
        abort(400, description=str(exc))
    if not start.date() <= selected_day < end.date():
        abort(400, description="Selecione uma data da semana exibida.")
    rows = list_schedules(start.isoformat(), end.isoformat())
    days = [start + timedelta(days=i) for i in range(7)]
    return render_template(
        "schedules/index.html",
        title="Escalas",
        schedules=rows,
        days=days,
        start=start,
        end=end,
        previous=(
            (start - timedelta(days=7)).date().isoformat()
            if start.date() > MIN_DATE
            else None
        ),
        following=end.date().isoformat() if end.date() <= MAX_DATE else None,
        min_date=MIN_DATE,
        max_date=MAX_DATE,
        employees=list_employees(active_only=True),
        all_employees=list_employees(),
        shifts=list_shifts(),
        assignment=assignment,
        form=submitted if submitted is not None else assignment,
        selected_day=selected_day.isoformat(),
        alerts=week_alerts(start, end),
        unavailable=list_unavailabilities(),
        unavailable_form=unavailable_form,
    )


@bp.route("/", methods=["GET", "POST"])
@bp.route("/<dbid:schedule_id>/edit", methods=["GET", "POST"])
@login_required
def index(schedule_id=None):
    start, end = selected_week()
    assignment = get_schedule(schedule_id) if schedule_id else None
    if schedule_id and assignment is None:
        abort(404)
    if request.method == "POST":
        try:
            alerts = save_assignment(request.form, schedule_id)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_week(start, end, assignment, request.form), 422
        flash("Atribuição salva.", "success")
        if alerts:
            # Detalhes permanecem no calendário; o cookie tem espaço limitado.
            flash(alerts[0][:240], "warning")
            if len(alerts) > 1:
                flash(
                    f"Mais {len(alerts) - 1} alerta(s). Consulte as semanas afetadas na escala.",
                    "warning",
                )
        return redirect(url_for("schedules.index", week=request.form["work_date"]))
    return render_week(start, end, assignment)


@bp.post("/<dbid:schedule_id>/delete")
@login_required
def delete(schedule_id):
    row = get_schedule(schedule_id)
    if row is None:
        abort(404)
    remove_assignment(schedule_id)
    flash("Atribuição removida.", "success")
    return redirect(url_for("schedules.index", week=row["work_date"]))


@bp.post("/unavailability")
@login_required
def unavailability():
    start, end = selected_week()
    try:
        add_unavailability(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return render_week(start, end, unavailable_form=request.form), 422
    flash("Indisponibilidade cadastrada.", "success")
    return redirect(url_for("schedules.index", week=start.date().isoformat()))


@bp.post("/unavailability/<dbid:record_id>/delete")
@login_required
def delete_unavailability(record_id):
    start, _ = selected_week()
    if not remove_unavailability(record_id):
        abort(404)
    flash("Indisponibilidade removida.", "success")
    return redirect(url_for("schedules.index", week=start.date().isoformat()))


@bp.get("/export.pdf")
@login_required
def export():
    from app.services.pdf_service import weekly_pdf

    start, end = selected_week()
    rows = list_schedules(start.isoformat(), end.isoformat())
    return send_file(
        weekly_pdf(get_settings()["company_name"], start, end, rows),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"escalapro-{start:%Y-%m-%d}.pdf",
        max_age=0,
    )
