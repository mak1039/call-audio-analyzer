from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from overtone.composition.config import AppConfig
from overtone.infrastructure.jobs.synchronous_job_runner import SynchronousJobRunner
from overtone.web.app import create_app

USERNAME = "autoace"
PASSWORD = "hunter2"


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    config = AppConfig(
        workspace_root=tmp_path / "workspace",
        secret_key="test-secret",
        username=USERNAME,
        password=PASSWORD,
    )
    return create_app(config, job_runner=SynchronousJobRunner())


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def logged_in(client: FlaskClient) -> FlaskClient:
    client.post("/login", data={"username": USERNAME, "password": PASSWORD})
    return client
