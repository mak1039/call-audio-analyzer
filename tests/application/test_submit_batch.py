import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from overtone.application.ports.clock import Clock
from overtone.application.use_cases.submit_batch import SubmitBatch
from overtone.domain.enums import BatchStatus, ItemStatus
from overtone.domain.exceptions import CorruptArchiveError, ManifestError
from overtone.infrastructure.archive.zip_archive_extractor import ZipArchiveExtractor
from overtone.infrastructure.manifest.csv_manifest_parser import CsvManifestParser
from overtone.infrastructure.persistence.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from overtone.infrastructure.storage.local_file_storage import LocalFileStorage

MANIFEST = b"name,result_json\ncall_001.ogg,\ncall_002.ogg,\n"
CREATED_AT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


class FixedClock(Clock):
    def now(self) -> datetime:
        return CREATED_AT


@pytest.fixture
def repository() -> InMemoryBatchRepository:
    return InMemoryBatchRepository()


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "batches")


@pytest.fixture
def submit(repository: InMemoryBatchRepository, storage: LocalFileStorage) -> SubmitBatch:
    return SubmitBatch(
        extractor=ZipArchiveExtractor(),
        parser=CsvManifestParser(),
        storage=storage,
        repository=repository,
        clock=FixedClock(),
    )


def build_zip(tmp_path: Path, entries: dict[str, bytes]) -> Path:
    archive = tmp_path / "batch.zip"
    with zipfile.ZipFile(archive, "w") as opened:
        for name, payload in entries.items():
            opened.writestr(name, payload)
    return archive


def test_batch_is_stamped_with_the_submission_time(
    submit: SubmitBatch, repository: InMemoryBatchRepository, tmp_path: Path
):
    archive = build_zip(
        tmp_path, {"labels.csv": MANIFEST, "call_001.ogg": b"a", "call_002.ogg": b"b"}
    )

    batch = repository.get(submit.execute(archive))

    assert batch.created_at == CREATED_AT


def test_creates_one_pending_item_per_manifest_row_in_order(
    submit: SubmitBatch, repository: InMemoryBatchRepository, tmp_path: Path
):
    archive = build_zip(
        tmp_path,
        {"labels.csv": MANIFEST, "call_002.ogg": b"bbb", "call_001.ogg": b"aaa"},
    )

    batch = repository.get(submit.execute(archive))

    assert [item.filename for item in batch.items] == ["call_001.ogg", "call_002.ogg"]
    assert {item.status for item in batch.items} == {ItemStatus.PENDING}
    assert batch.status is BatchStatus.PENDING


def test_extracted_audio_lands_where_storage_expects_it(
    submit: SubmitBatch, storage: LocalFileStorage, tmp_path: Path
):
    archive = build_zip(
        tmp_path, {"labels.csv": MANIFEST, "call_001.ogg": b"aaa", "call_002.ogg": b"b"}
    )

    batch_id = submit.execute(archive)

    assert storage.path_for(batch_id, "call_001.ogg").read_bytes() == b"aaa"


def test_a_row_naming_an_absent_file_fails_that_item_only(
    submit: SubmitBatch, repository: InMemoryBatchRepository, tmp_path: Path
):
    archive = build_zip(tmp_path, {"labels.csv": MANIFEST, "call_001.ogg": b"aaa"})

    batch = repository.get(submit.execute(archive))
    missing = batch.items[1]

    assert missing.status is ItemStatus.FAILED
    assert missing.error_message is not None
    assert "call_002.ogg" in missing.error_message
    assert batch.items[0].status is ItemStatus.PENDING


def test_audio_absent_from_the_manifest_is_reported_as_unmatched(
    submit: SubmitBatch, repository: InMemoryBatchRepository, tmp_path: Path
):
    archive = build_zip(
        tmp_path,
        {"labels.csv": MANIFEST, "call_001.ogg": b"a", "call_002.ogg": b"b", "stray.ogg": b"s"},
    )

    batch = repository.get(submit.execute(archive))

    assert batch.unmatched_files == ("stray.ogg",)
    assert "stray.ogg" not in [item.filename for item in batch.items]


def test_missing_and_unmatched_are_reported_together(
    submit: SubmitBatch, repository: InMemoryBatchRepository, tmp_path: Path
):
    archive = build_zip(tmp_path, {"labels.csv": MANIFEST, "call_001.ogg": b"a", "stray.ogg": b"s"})

    batch = repository.get(submit.execute(archive))

    assert batch.unmatched_files == ("stray.ogg",)
    assert batch.items[1].status is ItemStatus.FAILED


def test_non_audio_extras_are_ignored_rather_than_reported_as_unmatched(
    submit: SubmitBatch, repository: InMemoryBatchRepository, tmp_path: Path
):
    archive = build_zip(
        tmp_path,
        {"labels.csv": MANIFEST, "call_001.ogg": b"a", "call_002.ogg": b"b", "README.txt": b"hi"},
    )

    batch = repository.get(submit.execute(archive))

    assert batch.unmatched_files == ()


def test_a_malformed_label_does_not_stop_the_row_being_processed(
    submit: SubmitBatch, repository: InMemoryBatchRepository, tmp_path: Path
):
    manifest = b'name,result_json\ncall_001.ogg,"{not json"\n'
    archive = build_zip(tmp_path, {"labels.csv": manifest, "call_001.ogg": b"a"})

    batch = repository.get(submit.execute(archive))

    assert batch.items[0].status is ItemStatus.PENDING


def test_rejects_a_batch_with_no_manifest(submit: SubmitBatch, tmp_path: Path):
    archive = build_zip(tmp_path, {"call_001.ogg": b"aaa"})

    with pytest.raises(ManifestError):
        submit.execute(archive)


def test_rejects_a_batch_with_more_than_one_manifest(submit: SubmitBatch, tmp_path: Path):
    archive = build_zip(
        tmp_path, {"labels.csv": MANIFEST, "other.csv": MANIFEST, "call_001.ogg": b"a"}
    )

    with pytest.raises(ManifestError):
        submit.execute(archive)


def test_propagates_a_corrupt_archive(submit: SubmitBatch, tmp_path: Path):
    broken = tmp_path / "batch.zip"
    broken.write_bytes(b"not a zip")

    with pytest.raises(CorruptArchiveError):
        submit.execute(broken)
