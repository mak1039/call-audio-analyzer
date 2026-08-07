from flask import Blueprint, current_app, render_template

from overtone.composition.container import Container
from overtone.web.auth.session_guard import login_required

blueprint = Blueprint("batches", __name__)
RECENT_LIMIT = 20


@blueprint.get("/")
@login_required
def dashboard() -> str:
    return render_template("dashboard.html", batches=_container().batches.list_recent(RECENT_LIMIT))


def _container() -> Container:
    container: Container = current_app.extensions["overtone"]
    return container
