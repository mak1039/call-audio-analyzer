from pathlib import Path

import pytest

from overtone.application.ports.audio_analyzer import AudioAnalyzer
from overtone.application.use_cases.process_batch import ProcessBatch
from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.audio_clip import AudioClip
from overtone.domain.batch import Batch, BatchId, BatchItem, new_batch_id
from overtone.domain.enums import (
    AudioQuality,
    BatchStatus,
    EmotionalIntensity,
    EmotionalTone,
    ItemStatus,
    NoiseSeverity,
)
from overtone.domain.exceptions import BatchNotFoundError
from overtone.infrastructure.persistence.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from overtone.infrastructure.storage.local_file_storage import LocalFileStorage

RESULT = AnalysisResult(
    emotional_tone=EmotionalTone.SATISFIED,
    emotional_intensity=EmotionalIntensity.MEDIUM,
    background_noise_present=False,
    background_noise_type="",
    background_noise_severity=NoiseSeverity.NONE,
    audio_quality=AudioQuality.CLEAR,
    speaker_overlap_present=False,
    long_silence_present=False,
    confidence=0.5,
)


class FakeAnalyzer(AudioAnalyzer):
    def __init__(self, failing: str | None = None) -> None:
        self._failing = failing
        self.seen: list[AudioClip] = []

    def analyze(self, clip: AudioClip) -> AnalysisResult:
        self.seen.append(clip)
        if clip.filename == self._failing:
            raise RuntimeError("decoder blew up")
        return RESULT


class RecordingRepository(InMemoryBatchRepository):
    def __init__(self) -> None:
        super().__init__()
        self.saves: list[Batch] = []

    def save(self, batch: Batch) -> None:
        super().save(batch)
        self.saves.append(batch)


@pytest.fixture
def repository() -> RecordingRepository:
    return RecordingRepository()


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "batches")


def seed(repository: RecordingRepository, storage: LocalFileStorage, *items: BatchItem) -> BatchId:
    batch_id = new_batch_id()
    for item in items:
        storage.path_for(batch_id, item.filename).write_bytes(b"audio")
    repository.save(Batch.create(batch_id, items))
    repository.saves.clear()
    return batch_id


def run(
    repository: RecordingRepository,
    storage: LocalFileStorage,
    analyzer: FakeAnalyzer,
    batch_id: BatchId,
) -> Batch:
    ProcessBatch(analyzer=analyzer, storage=storage, repository=repository).execute(batch_id)
    return repository.get(batch_id)


def test_every_pending_item_receives_a_result(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(repository, storage, BatchItem.pending("a.ogg"), BatchItem.pending("b.ogg"))

    batch = run(repository, storage, FakeAnalyzer(), batch_id)

    assert [item.status for item in batch.items] == [ItemStatus.SUCCEEDED, ItemStatus.SUCCEEDED]
    assert batch.items[0].result == RESULT


def test_batch_is_completed_when_processing_finishes(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(repository, storage, BatchItem.pending("a.ogg"))

    assert run(repository, storage, FakeAnalyzer(), batch_id).status is BatchStatus.COMPLETED


def test_one_failing_file_does_not_stop_the_rest_of_the_batch(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(
        repository,
        storage,
        BatchItem.pending("a.ogg"),
        BatchItem.pending("bad.ogg"),
        BatchItem.pending("c.ogg"),
    )

    batch = run(repository, storage, FakeAnalyzer(failing="bad.ogg"), batch_id)

    assert [item.status for item in batch.items] == [
        ItemStatus.SUCCEEDED,
        ItemStatus.FAILED,
        ItemStatus.SUCCEEDED,
    ]
    assert batch.status is BatchStatus.COMPLETED


def test_the_failure_reason_identifies_what_went_wrong(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(repository, storage, BatchItem.pending("bad.ogg"))

    batch = run(repository, storage, FakeAnalyzer(failing="bad.ogg"), batch_id)

    assert batch.items[0].error_message is not None
    assert "decoder blew up" in batch.items[0].error_message


def test_items_already_failed_at_submission_are_not_analysed(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(
        repository,
        storage,
        BatchItem.pending("a.ogg"),
        BatchItem.pending("gone.ogg").failed("absent from the batch"),
    )
    analyzer = FakeAnalyzer()

    batch = run(repository, storage, analyzer, batch_id)

    assert [clip.filename for clip in analyzer.seen] == ["a.ogg"]
    assert batch.items[1].error_message == "absent from the batch"


def test_the_analyzer_receives_the_original_filename_and_its_stored_path(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(repository, storage, BatchItem.pending("call_001.ogg"))
    analyzer = FakeAnalyzer()

    run(repository, storage, analyzer, batch_id)

    assert analyzer.seen[0].filename == "call_001.ogg"
    assert analyzer.seen[0].path == storage.path_for(batch_id, "call_001.ogg")


def test_progress_is_persisted_after_each_item(
    repository: RecordingRepository, storage: LocalFileStorage
):
    batch_id = seed(repository, storage, BatchItem.pending("a.ogg"), BatchItem.pending("b.ogg"))

    run(repository, storage, FakeAnalyzer(), batch_id)

    resolved_counts = [snapshot.succeeded_count for snapshot in repository.saves]
    assert resolved_counts == [0, 1, 2, 2]
    assert repository.saves[0].status is BatchStatus.RUNNING


def test_an_unknown_batch_is_rejected(repository: RecordingRepository, storage: LocalFileStorage):
    with pytest.raises(BatchNotFoundError):
        run(repository, storage, FakeAnalyzer(), new_batch_id())
