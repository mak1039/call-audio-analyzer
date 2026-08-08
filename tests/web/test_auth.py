from dataclasses import replace

from flask import Flask
from flask.testing import FlaskClient

from tests.web.conftest import PASSWORD, USERNAME


def test_healthz_is_public(client: FlaskClient):
    assert client.get("/healthz").status_code == 200


def test_the_dashboard_redirects_when_not_logged_in(client: FlaskClient):
    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_valid_credentials_grant_access(client: FlaskClient):
    response = client.post(
        "/login", data={"username": USERNAME, "password": PASSWORD}, follow_redirects=True
    )

    assert response.status_code == 200


def test_the_dashboard_is_reachable_once_logged_in(logged_in: FlaskClient):
    assert logged_in.get("/").status_code == 200


def test_wrong_password_is_rejected(client: FlaskClient):
    response = client.post("/login", data={"username": USERNAME, "password": "wrong"})

    assert response.status_code == 401


def test_unknown_username_is_rejected(client: FlaskClient):
    response = client.post("/login", data={"username": "nobody", "password": PASSWORD})

    assert response.status_code == 401


def test_a_non_ascii_username_is_rejected_not_crashed(client: FlaskClient):
    response = client.post("/login", data={"username": "José", "password": PASSWORD})

    assert response.status_code == 401


def test_a_non_ascii_password_is_rejected_not_crashed(client: FlaskClient):
    response = client.post("/login", data={"username": USERNAME, "password": "sésame”"})

    assert response.status_code == 401


def test_non_ascii_credentials_can_be_configured_and_used(app: Flask, client: FlaskClient):
    app.config["OVERTONE_CONFIG"] = replace(
        app.config["OVERTONE_CONFIG"], username="José", password="café-“strong”"
    )

    response = client.post("/login", data={"username": "José", "password": "café-“strong”"})

    assert response.status_code == 302


def test_logout_ends_the_session(logged_in: FlaskClient):
    logged_in.post("/logout")

    assert logged_in.get("/").status_code == 302
