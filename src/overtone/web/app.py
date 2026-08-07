from flask import Flask, render_template
from werkzeug.exceptions import RequestEntityTooLarge

from overtone.application.ports.job_runner import JobRunner
from overtone.composition.config import AppConfig
from overtone.composition.container import build_container
from overtone.web.blueprints import auth, batches


def create_app(config: AppConfig, job_runner: JobRunner | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.secret_key
    app.config["MAX_CONTENT_LENGTH"] = config.max_upload_bytes
    app.config["OVERTONE_CONFIG"] = config
    app.extensions["overtone"] = build_container(config, job_runner=job_runner)
    app.register_blueprint(auth.blueprint)
    app.register_blueprint(batches.blueprint)
    _register_health_check(app)
    _register_error_handlers(app)
    return app


def _register_health_check(app: Flask) -> None:
    @app.get("/healthz")
    def healthz() -> tuple[str, int]:
        return "ok", 200


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error: RequestEntityTooLarge) -> tuple[str, int]:
        limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        message = f"That upload is too large. The limit is {limit_mb} MB."
        return render_template("dashboard.html", batches=(), error=message), 413
