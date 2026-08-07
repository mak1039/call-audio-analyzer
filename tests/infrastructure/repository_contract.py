from datetime import UTC, datetime, timedelta

import pytest

from overtone.application.ports.batch_repository import BatchRepository
from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.batch import Batch, BatchItem, new_batch_id
from overtone.domain.enums import (
    AudioQuality,
    BatchStatus,
    EmotionalIntensity,
    EmotionalTone,
    NoiseSeverity,
)
from overtone.domain.exceptions import BatchNotFoundError

BASE_TIME = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)

SAMPLE_RESULT = AnalysisResult(
    emotional_tone=EmotionalTone.UPSET,
    emotional_intensity=EmotionalIntensity.HIGH,
    background_noise_present=True,
    background_noise_type="TV",
    background_noise_severity=NoiseSeverity.MEDIUM,
    audio_quality=AudioQuality.CLEAR,
    speaker_overlap_present=True,
    long_silence_present=False,
    confidence=0.82,
)


def a_batch(minutes: int = 0, unmatched: tuple[str, ...] = ()) -> Batch:
    items = (BatchItem.pending("call_001.ogg"),)
    return Batch.create(
        new_batch_id(), items, BASE_TIME + timedelta(minutes=minutes), unmatched_files=unmatched
    )


class BatchRepositoryContract:
    """Behaviour every BatchRepository must exhibit. Subclass and supply `repository`."""

    def test_returns_the_saved_batch(self, repository: BatchRepository):
        batch = a_batch()

        repository.save(batch)

        assert repository.get(batch.batch_id) == batch

    def test_keeps_only_the_latest_save(self, repository: BatchRepository):
        batch = a_batch()
        repository.save(batch)

        repository.save(batch.started())

        assert repository.get(batch.batch_id).status is BatchStatus.RUNNING

    def test_round_trips_unmatched_files(self, repository: BatchRepository):
        batch = a_batch(unmatched=("stray.ogg",))

        repository.save(batch)

        assert repository.get(batch.batch_id).unmatched_files == ("stray.ogg",)

    def test_round_trips_a_completed_item_with_its_result(self, repository: BatchRepository):
        batch = a_batch()
        batch = batch.replacing(batch.items[0].succeeded(SAMPLE_RESULT))

        repository.save(batch)

        assert repository.get(batch.batch_id).items[0].result == SAMPLE_RESULT

    def test_round_trips_a_failed_item_with_its_reason(self, repository: BatchRepository):
        batch = a_batch()
        batch = batch.replacing(batch.items[0].failed("decoder blew up"))

        repository.save(batch)

        assert repository.get(batch.batch_id).items[0].error_message == "decoder blew up"

    def test_raises_for_an_unknown_batch(self, repository: BatchRepository):
        with pytest.raises(BatchNotFoundError):
            repository.get(new_batch_id())

    def test_lists_recent_batches_newest_first(self, repository: BatchRepository):
        older, newer = a_batch(minutes=0), a_batch(minutes=5)
        repository.save(older)
        repository.save(newer)

        listed = repository.list_recent(10)

        assert [batch.batch_id for batch in listed[:2]] == [newer.batch_id, older.batch_id]

    def test_list_recent_honours_the_limit(self, repository: BatchRepository):
        for minute in range(3):
            repository.save(a_batch(minutes=minute))

        assert len(repository.list_recent(2)) == 2
