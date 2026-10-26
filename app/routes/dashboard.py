from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.models.employee import list_employees
from app.models.schedule import list_schedules
from app.models.settings import get_settings, save_settings
from app.models.shift import list_shifts
from app.security import login_required
from app.services.clock import local_now
from app.services.schedule_service import week_alerts, week_period
from app.services.schedule_validator import net_hours
from app.services.validation import number_value, text_value

bp = Blueprint("dashboard", __name__)


@bp.get("/dashboard")
@login_required
def index():
    now = local_now().replace(tzinfo=None)
    start, end = week_period(now.date().isoformat())
    rows = list_schedules(start.isoformat(), end.isoformat())
    days = [start + timedelta(days=i) for i in range(7)]
    chart = [
        round(sum(net_hours(row, day, day + timedelta(days=1)) for row in rows), 1)
        for day in days
    ]
    upcoming = list_schedules(now.isoformat(), (now + timedelta(days=7)).isoformat())[
        :6
    ]
    return render_template(
        "dashboard/index.html",
        title="Dashboard",
        employees=list_employees(active_only=True),
        shifts=list_shifts(),
        schedules=rows,
        upcoming=upcoming,
        alerts=week_alerts(start, end),
        chart=chart,
        total_hours=round(sum(net_hours(row, start, end) for row in rows), 1),
        start=start,
        end=end,
        now=now,
    )


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        try:
            name = text_value(
                request.form.get("company_name", ""), "Nome da empresa", 2, 100
            )
            rest = number_value(
                request.form.get("min_rest_hours"), "Descanso mínimo", 0, 72
            )
            save_settings(name, rest, request.form.get("weekly_alerts") == "on")
        except ValueError as exc:
            flash(str(exc), "error")
            return (
                render_template(
                    "settings.html", title="Configurações", settings=request.form
                ),
                422,
            )
        flash("Configurações atualizadas.", "success")
        return redirect(url_for("dashboard.settings"))
    return render_template(
        "settings.html", title="Configurações", settings=get_settings()
    )
