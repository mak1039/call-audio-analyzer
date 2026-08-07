import hmac

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.wrappers import Response

from overtone.web.auth.session_guard import SESSION_KEY

blueprint = Blueprint("auth", __name__)


@blueprint.get("/login")
def login_form() -> str:
    return render_template("login.html")


@blueprint.post("/login")
def login() -> Response | tuple[str, int]:
    if not _credentials_match(request.form.get("username", ""), request.form.get("password", "")):
        return render_template("login.html", error="Incorrect username or password."), 401
    session.clear()
    session[SESSION_KEY] = True
    return redirect(url_for("batches.dashboard"))


@blueprint.post("/logout")
def logout() -> Response:
    session.clear()
    return redirect(url_for("auth.login"))


def _credentials_match(username: str, password: str) -> bool:
    config = current_app.config["OVERTONE_CONFIG"]
    username_matches = hmac.compare_digest(username, config.username)
    password_matches = hmac.compare_digest(password, config.password)
    return username_matches and password_matches
