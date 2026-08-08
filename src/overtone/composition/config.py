import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_UPLOAD_MB = 500
DEFAULT_SECRET_KEY = "dev-secret-not-for-production"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


class InsecureConfigurationError(Exception):
    """Raised when a production deployment would run with development-only secrets."""


@dataclass(frozen=True)
class AppConfig:
    """Everything the composition root needs to wire the system."""

    workspace_root: Path
    database_url: str | None = None
    secret_key: str = DEFAULT_SECRET_KEY
    username: str = DEFAULT_USERNAME
    password: str = DEFAULT_PASSWORD
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024

    @classmethod
    def from_env(cls) -> "AppConfig":
        config = cls(
            workspace_root=Path(os.environ.get("OVERTONE_WORKSPACE_ROOT", "/tmp/overtone")),
            database_url=os.environ.get("DATABASE_URL"),
            secret_key=os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY),
            username=os.environ.get("OVERTONE_USERNAME", DEFAULT_USERNAME),
            password=os.environ.get("OVERTONE_PASSWORD", DEFAULT_PASSWORD),
            max_upload_bytes=_parse_max_upload_bytes(),
        )
        _guard_against_insecure_production(config)
        return config


def _parse_max_upload_bytes() -> int:
    raw = os.environ.get("OVERTONE_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
    try:
        return int(raw) * 1024 * 1024
    except ValueError as error:
        raise ValueError(f"OVERTONE_MAX_UPLOAD_MB must be an integer, got {raw!r}") from error


def _guard_against_insecure_production(config: "AppConfig") -> None:
    if config.database_url is None:
        return
    offenders = _insecure_defaults(config)
    if not offenders:
        return
    names = ", ".join(offenders)
    raise InsecureConfigurationError(
        "refusing to start against a database with development defaults still set: "
        f"{names}. Set these environment variables to real values before deploying."
    )


def _insecure_defaults(config: "AppConfig") -> list[str]:
    checks = (
        (config.secret_key == DEFAULT_SECRET_KEY, "SECRET_KEY"),
        (config.username == DEFAULT_USERNAME, "OVERTONE_USERNAME"),
        (config.password == DEFAULT_PASSWORD, "OVERTONE_PASSWORD"),
    )
    return [name for is_default, name in checks if is_default]
