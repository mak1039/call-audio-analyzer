import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_UPLOAD_MB = 500


@dataclass(frozen=True)
class AppConfig:
    """Everything the composition root needs to wire the system."""

    workspace_root: Path
    database_url: str | None = None
    secret_key: str = "dev-secret-not-for-production"
    username: str = "admin"
    password: str = "admin"
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024

    @classmethod
    def from_env(cls) -> "AppConfig":
        megabytes = int(os.environ.get("OVERTONE_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB))
        return cls(
            workspace_root=Path(os.environ.get("OVERTONE_WORKSPACE_ROOT", "/tmp/overtone")),
            database_url=os.environ.get("DATABASE_URL"),
            secret_key=os.environ.get("SECRET_KEY", "dev-secret-not-for-production"),
            username=os.environ.get("OVERTONE_USERNAME", "admin"),
            password=os.environ.get("OVERTONE_PASSWORD", "admin"),
            max_upload_bytes=megabytes * 1024 * 1024,
        )
