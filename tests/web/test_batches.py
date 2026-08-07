import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

from flask import Flask
from flask.testing import FlaskClient

from overtone.application.ports.job_runner import JobRunner
from overtone.composition.config import AppConfig
from overtone.web.app import create_app

MANIFEST = b"name,result_json\ncall_001.ogg,\ncall_002.ogg,\ncall_missing.ogg,\n"


class DeferredJobRunner(JobRunner):
    """Queues work instead of running it, so tests can run it outside the request.

    This is what catches a submitted closure that secretly depends on Flask's request
    or application context: SynchronousJobRunner runs work inline on the request
    thread, where that context still exists, and would never expose the bug.
    """

    def __init__(self) -> None:
        self.pending: list[Callable[[], None]] = []

    def submit(self, work: Callable[[], None]) -> None:
        self.pending.append(work)

    def run_pending(self) -> None:
        jobs, self.pending = self.pending, []
        for job in jobs:
            job()

    def shutdown(self) -> None:
        return None


def batch_archive() -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("labels.csv", MANIFEST)
        archive.writestr("call_001.ogg", b"OggS one")
        archive.writestr("call_002.ogg", b"OggS two")
        archive.writestr("stray.ogg", b"OggS stray")
    buffer.seek(0)
    return buffer


def upload(client: FlaskClient) -> str:
    response = client.post(
        "/batches",
        data={"archive": (batch_archive(), "evaluation_batch.zip")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    return response.headers["Location"]


def test_upload_redirects_to_the_batch_page(logged_in: FlaskClient):
    assert "/batches/" in upload(logged_in)


def test_status_reports_completion_and_counts(logged_in: FlaskClient):
    location = upload(logged_in)

    payload = json.loads(logged_in.get(f"{location}/status.json").data)

    assert payload["status"] == "completed"
    assert payload["total"] == 3
    assert payload["succeeded"] == 2
    assert payload["failed"] == 1


def test_status_reports_unmatched_files(logged_in: FlaskClient):
    location = upload(logged_in)

    payload = json.loads(logged_in.get(f"{location}/status.json").data)

    assert payload["unmatched_files"] == ["stray.ogg"]


def test_the_batch_page_shows_each_filename_and_the_failure_reason(logged_in: FlaskClient):
    location = upload(logged_in)

    body = logged_in.get(location).data.decode()

    assert "call_001.ogg" in body
    assert "call_missing.ogg" in body
    assert "absent from the batch" in body


def test_csv_download_preserves_original_filenames(logged_in: FlaskClient):
    location = upload(logged_in)

    body = logged_in.get(f"{location}/download/csv").data.decode()

    assert "call_001.ogg" in body
    assert body.startswith("name,status,error,emotional_tone")


def test_json_download_carries_the_output_schema(logged_in: FlaskClient):
    location = upload(logged_in)

    payload = json.loads(logged_in.get(f"{location}/download/json").data)

    assert payload["results"][0]["result"]["emotional_tone"] == "neutral"


def test_an_unknown_download_format_is_rejected(logged_in: FlaskClient):
    location = upload(logged_in)

    assert logged_in.get(f"{location}/download/xml").status_code == 404


def test_a_corrupt_archive_is_reported_on_the_upload_page(logged_in: FlaskClient):
    response = logged_in.post(
        "/batches",
        data={"archive": (io.BytesIO(b"not a zip"), "broken.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "could not read archive" in response.data.decode()


def test_a_batch_with_no_manifest_is_reported(logged_in: FlaskClient):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("call_001.ogg", b"OggS")
    buffer.seek(0)

    response = logged_in.post(
        "/batches",
        data={"archive": (buffer, "no_manifest.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "manifest" in response.data.decode().lower()


def test_uploading_without_a_file_is_reported(logged_in: FlaskClient):
    response = logged_in.post("/batches", data={}, content_type="multipart/form-data")

    assert response.status_code == 400


def test_the_dashboard_lists_a_submitted_batch(logged_in: FlaskClient):
    upload(logged_in)

    assert "batch" in logged_in.get("/").data.decode().lower()


def test_an_unknown_batch_returns_404(logged_in: FlaskClient):
    assert logged_in.get("/batches/does-not-exist").status_code == 404


def test_batch_routes_require_a_session(client: FlaskClient):
    assert client.get("/batches/anything").status_code == 302
    assert client.post("/batches").status_code == 302
    assert client.get("/batches/anything/status.json").status_code == 302
    assert client.get("/batches/anything/download/csv").status_code == 302


def test_processing_deferred_past_the_request_does_not_need_an_app_context(tmp_path: Path):
    runner = DeferredJobRunner()
    config = AppConfig(workspace_root=tmp_path / "workspace", secret_key="test-secret")
    app = create_app(config, job_runner=runner)
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "admin"})

    location = upload(client)
    assert runner.pending, "upload() should have queued processing instead of running it"

    runner.run_pending()  # outside the request/app context the view ran under

    payload = json.loads(client.get(f"{location}/status.json").data)
    assert payload["status"] == "completed"


def test_an_oversized_upload_gets_a_readable_message(app: Flask, logged_in: FlaskClient):
    app.config["MAX_CONTENT_LENGTH"] = 10

    response = logged_in.post(
        "/batches",
        data={"archive": (io.BytesIO(b"x" * 5000), "big.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert "too large" in response.data.decode().lower()
