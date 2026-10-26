from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.models.employee import get_employee, list_employees, save_employee, set_active
from app.security import login_required
from app.services.employee_service import validate_employee

bp = Blueprint("employees", __name__, url_prefix="/employees")


@bp.get("/")
@login_required
def index():
    query = request.args.get("q", "").strip()[:100]
    return render_template(
        "employees/index.html",
        title="Funcionários",
        employees=list_employees(query),
        query=query,
    )


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<dbid:employee_id>/edit", methods=["GET", "POST"])
@login_required
def form(employee_id=None):
    employee = get_employee(employee_id) if employee_id else None
    if employee_id and employee is None:
        abort(404)
    if request.method == "POST":
        try:
            save_employee(validate_employee(request.form), employee_id)
        except ValueError as exc:
            flash(str(exc), "error")
            return (
                render_template(
                    "employees/form.html",
                    title="Editar funcionário" if employee_id else "Novo funcionário",
                    employee=request.form,
                ),
                422,
            )
        flash(
            "Funcionário atualizado." if employee_id else "Funcionário cadastrado.",
            "success",
        )
        return redirect(url_for("employees.index"))
    return render_template(
        "employees/form.html",
        title="Editar funcionário" if employee_id else "Novo funcionário",
        employee=employee,
    )


@bp.post("/<dbid:employee_id>/toggle")
@login_required
def toggle(employee_id):
    employee = get_employee(employee_id)
    if employee is None:
        abort(404)
    set_active(employee_id, not employee["active"])
    flash("Status atualizado. As escalas existentes foram preservadas.", "success")
    return redirect(url_for("employees.index"))
