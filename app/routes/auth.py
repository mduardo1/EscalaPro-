import math
import time

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import SecurityError

from app.models.user import (
    create_auth_session,
    find_by_email,
    find_session_user,
    revoke_auth_session,
)
from app.security import (
    consume_rate_limit,
    login_blocked,
    login_key,
    login_required,
    record_login,
)
from app.services import auth_service
from app.services.email_service import mail_ready
from app.models.verification import get_challenge, reset_grant

bp = Blueprint("auth", __name__)
# Mesmo custo de verificação para contas inexistentes, sem credencial utilizável.
DUMMY_HASH = generate_password_hash("unused-auth-timing-placeholder")


@bp.before_app_request
def load_user():
    if isinstance(request.routing_exception, SecurityError) or (
        request.endpoint and request.endpoint.startswith("health.")
    ):
        g.user = None
        return
    g.user = find_session_user(session.get("auth_token"))
    if g.user is None and (session.get("user_id") or session.get("auth_token")):
        session.clear()


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:254]
        password = request.form.get("password", "")
        key = login_key(email)
        if not consume_rate_limit(
            "login:ip", request.remote_addr or "unknown", 30, 900
        ) or login_blocked(key):
            flash(
                "Muitas tentativas. Aguarde 15 minutos para tentar novamente.", "error"
            )
            return render_template("auth/login.html", title="Entrar"), 429
        user = find_by_email(email)
        valid = len(password) <= 128 and check_password_hash(
            user["password_hash"] if user else DUMMY_HASH, password
        )
        if user and valid and user["email_verified"]:
            record_login(key, True)
            auth_token = create_auth_session(user["id"])
            session.clear()
            session["user_id"] = user["id"]
            session["auth_token"] = auth_token
            session.permanent = True
            return redirect(url_for("dashboard.index"))
        record_login(key, False)
        flash("E-mail ou senha inválidos.", "error")
        return render_template("auth/login.html", title="Entrar"), 401
    return render_template("auth/login.html", title="Entrar")


@bp.post("/logout")
@login_required
def logout():
    revoke_auth_session(session.get("auth_token"))
    session.clear()
    return redirect(url_for("auth.login"))


def start_flow(purpose):
    if g.user:
        return redirect(url_for("dashboard.index"))
    template = (
        "auth/register.html" if purpose == "signup" else "auth/forgot_password.html"
    )
    title = "Criar conta" if purpose == "signup" else "Recuperar senha"
    if request.method == "POST":
        if not mail_ready():
            flash(
                "O envio de e-mails está indisponível. Contate o responsável pela instalação.",
                "error",
            )
            return render_template(template, title=title), 503
        try:
            challenge_id = auth_service.request_code(purpose, request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template(template, title=title), 422
        if challenge_id is None:
            flash("Muitas solicitações. Aguarde antes de tentar novamente.", "error")
            return render_template(template, title=title), 429
        session[f"pending_{purpose}"] = challenge_id
        session.pop("reset_grant", None)
        flash(
            "Se a solicitação puder prosseguir, você receberá um código por e-mail. Confira também a pasta de spam.",
            "success",
        )
        return redirect(url_for("auth.verify_email", purpose=purpose))
    return render_template(template, title=title)


@bp.route("/register", methods=["GET", "POST"])
def register():
    return start_flow("signup")


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    return start_flow("reset")


def pending_id(purpose):
    if purpose not in {"signup", "reset"}:
        abort(404)
    return session.get(f"pending_{purpose}")


@bp.route("/verify/<purpose>", methods=["GET", "POST"])
def verify_email(purpose):
    if g.user:
        return redirect(url_for("dashboard.index"))
    challenge_id = pending_id(purpose)
    if challenge_id is None:
        return redirect(
            url_for("auth.register" if purpose == "signup" else "auth.forgot_password")
        )
    row = get_challenge(challenge_id, purpose)
    remaining = (
        max(
            0,
            math.ceil(
                row["sent_at"]
                + current_app.config["CODE_RESEND_INTERVAL"]
                - time.time()
            ),
        )
        if row
        else 0
    )
    if request.method == "POST":
        success, grant = auth_service.verify_code(
            challenge_id, purpose, request.form.get("code", "")
        )
        if success:
            if purpose == "signup":
                session.pop("pending_signup", None)
                flash(
                    "Solicitação confirmada. Entre na sua conta ou recupere a senha caso já tivesse um cadastro.",
                    "success",
                )
                return redirect(url_for("auth.login"))
            session["reset_grant"] = grant
            return redirect(url_for("auth.reset_password"))
        flash(
            "Código inválido, expirado ou com limite de tentativas atingido. Reenvie após o intervalo ou reinicie a solicitação.",
            "error",
        )
        return (
            render_template(
                "auth/verify_email.html",
                title="Confirmar e-mail",
                purpose=purpose,
                resend_after=remaining,
            ),
            422,
        )
    return render_template(
        "auth/verify_email.html",
        title="Confirmar e-mail",
        purpose=purpose,
        resend_after=remaining,
    )


@bp.post("/verify/<purpose>/resend")
def resend(purpose):
    if g.user:
        return redirect(url_for("dashboard.index"))
    challenge_id = pending_id(purpose)
    if challenge_id is None:
        return redirect(
            url_for("auth.register" if purpose == "signup" else "auth.forgot_password")
        )
    if not auth_service.resend_code(challenge_id, purpose):
        flash(
            "Aguarde o intervalo de reenvio. Se a solicitação já foi concluída, reinicie o processo.",
            "warning",
        )
    else:
        flash(
            "Se a solicitação puder prosseguir, você receberá um novo código. O código anterior não será mais aceito.",
            "success",
        )
    return redirect(url_for("auth.verify_email", purpose=purpose))


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if g.user:
        return redirect(url_for("dashboard.index"))
    challenge_id, grant = session.get("pending_reset"), session.get("reset_grant")
    if reset_grant(challenge_id, grant) is None:
        flash(
            "A autorização para redefinir a senha expirou. Inicie uma nova solicitação.",
            "error",
        )
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        try:
            changed = auth_service.change_password(challenge_id, grant, request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("auth/reset_password.html", title="Nova senha"), 422
        if not changed:
            flash("A autorização expirou. Solicite um novo código.", "error")
            return redirect(url_for("auth.forgot_password"))
        session.clear()
        flash("Senha redefinida. Entre novamente com a nova senha.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", title="Nova senha")
