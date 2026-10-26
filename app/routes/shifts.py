from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.models.shift import get_shift, list_shifts, save_shift
from app.security import login_required
from app.services.shift_service import validate_shift

bp = Blueprint("shifts", __name__, url_prefix="/shifts")


@bp.route("/", methods=["GET", "POST"])
@bp.route("/<dbid:shift_id>/edit", methods=["GET", "POST"])
@login_required
def index(shift_id=None):
    shift = get_shift(shift_id) if shift_id else None
    if shift_id and shift is None:
        abort(404)
    if request.method == "POST":
        try:
            save_shift(validate_shift(request.form), shift_id)
        except ValueError as exc:
            flash(str(exc), "error")
            return (
                render_template(
                    "shifts/index.html",
                    title="Turnos",
                    shifts=list_shifts(),
                    shift=request.form,
                    editing=shift_id,
                ),
                422,
            )
        flash(
            "Turno salvo. Atribuições existentes mantêm seus horários registrados.",
            "success",
        )
        return redirect(url_for("shifts.index"))
    return render_template(
        "shifts/index.html",
        title="Turnos",
        shifts=list_shifts(),
        shift=shift,
        editing=shift_id,
    )
