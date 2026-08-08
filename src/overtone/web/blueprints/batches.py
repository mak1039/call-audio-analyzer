import tempfile
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.datastructures import FileStorage as UploadedFile

from overtone.composition.container import Container
from overtone.domain.batch import Batch, BatchId
from overtone.domain.exceptions import BatchNotFoundError, DomainError
from overtone.web.auth.session_guard import login_required

blueprint = Blueprint("batches", __name__)
RECENT_LIMIT = 20


@blueprint.get("/")
@login_required
def dashboard() -> str:
    return render_template("dashboard.html", batches=_container().batches.list_recent(RECENT_LIMIT))


@blueprint.post("/batches")
@login_required
def upload() -> Any:
    upload_file = request.files.get("archive")
    if upload_file is None or not upload_file.filename:
        return _upload_error("Choose a ZIP file containing your audio and a CSV manifest.")
    try:
        batch_id = _submit(upload_file)
    except DomainError as error:
        return _upload_error(str(error))
    container = _container()
    container.job_runner.submit(lambda: container.process_batch.execute(batch_id))
    return redirect(url_for("batches.detail", batch_id=batch_id))


@blueprint.get("/batches/<batch_id>")
@login_required
def detail(batch_id: str) -> str:
    return render_template("batch_detail.html", batch=_find(batch_id))


@blueprint.get("/batches/<batch_id>/status.json")
@login_required
def status(batch_id: str) -> Response:
    return jsonify(_status_payload(_find(batch_id)))


@blueprint.get("/batches/<batch_id>/download/<fmt>")
@login_required
def download(batch_id: str, fmt: str) -> Response:
    serializer = _container().serializers.get(fmt)
    if serializer is None:
        abort(404)
    batch = _find(batch_id)
    return Response(
        serializer.serialize(batch),
        mimetype="text/csv" if fmt == "csv" else "application/json",
        headers={"Content-Disposition": f"attachment; filename=results.{fmt}"},
    )


def _submit(upload_file: UploadedFile) -> BatchId:
    with tempfile.TemporaryDirectory(prefix="overtone-upload-") as staging:
        archive = Path(staging) / "batch.zip"
        upload_file.save(archive)
        return _container().submit_batch.execute(archive)


def _status_payload(batch: Batch) -> dict[str, Any]:
    return {
        "status": batch.status.value,
        "total": batch.total,
        "succeeded": batch.succeeded_count,
        "failed": batch.failed_count,
        "unmatched_files": list(batch.unmatched_files),
        "finished": batch.is_finished,
    }


def _upload_error(message: str) -> tuple[str, int]:
    batches = _container().batches.list_recent(RECENT_LIMIT)
    return render_template("dashboard.html", batches=batches, error=message), 400


def _find(batch_id: str) -> Batch:
    try:
        return _container().batches.get(BatchId(batch_id))
    except BatchNotFoundError:
        abort(404)


def _container() -> Container:
    container: Container = current_app.extensions["overtone"]
    return container
