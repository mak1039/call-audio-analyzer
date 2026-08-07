from pathlib import Path

import pytest

from overtone.composition.config import AppConfig


def test_from_env_reads_every_setting(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/overtone")
    monkeypatch.setenv("SECRET_KEY", "s3cret")
    monkeypatch.setenv("OVERTONE_USERNAME", "autoace")
    monkeypatch.setenv("OVERTONE_PASSWORD", "hunter2")
    monkeypatch.setenv("OVERTONE_WORKSPACE_ROOT", "/tmp/work")
    monkeypatch.setenv("OVERTONE_MAX_UPLOAD_MB", "50")

    config = AppConfig.from_env()

    assert config.database_url == "postgresql://localhost/overtone"
    assert config.secret_key == "s3cret"
    assert config.username == "autoace"
    assert config.password == "hunter2"
    assert config.workspace_root == Path("/tmp/work")
    assert config.max_upload_bytes == 50 * 1024 * 1024


def test_from_env_falls_back_to_development_defaults(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "DATABASE_URL",
        "SECRET_KEY",
        "OVERTONE_USERNAME",
        "OVERTONE_PASSWORD",
        "OVERTONE_WORKSPACE_ROOT",
        "OVERTONE_MAX_UPLOAD_MB",
    ):
        monkeypatch.delenv(name, raising=False)

    config = AppConfig.from_env()

    assert config.database_url is None
    assert config.username == "admin"
