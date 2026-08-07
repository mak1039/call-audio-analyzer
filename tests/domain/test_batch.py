import pytest

from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.batch import Batch, BatchItem, new_batch_id
from overtone.domain.enums import (
    AudioQuality,
    BatchStatus,
    EmotionalIntensity,
    EmotionalTone,
    ItemStatus,
    NoiseSeverity,
)

RESULT = AnalysisResult(
    emotional_tone=EmotionalTone.NEUTRAL,
    emotional_intensity=EmotionalIntensity.LOW,
    background_noise_present=False,
    background_noise_type="",
    background_noise_severity=NoiseSeverity.NONE,
    audio_quality=AudioQuality.CLEAR,
    speaker_overlap_present=False,
    long_silence_present=False,
    confidence=0.5,
)


def batch_of(*filenames: str, unmatched: tuple[str, ...] = ()) -> Batch:
    items = tuple(BatchItem.pending(name) for name in filenames)
    return Batch.create(new_batch_id(), items, unmatched_files=unmatched)


def test_new_batch_id_is_unique():
    assert new_batch_id() != new_batch_id()


def test_pending_item_has_no_result_and_no_error():
    item = BatchItem.pending("call_001.ogg")

    assert item.status is ItemStatus.PENDING
    assert item.result is None
    assert item.error_message is None


def test_succeeded_item_carries_result_and_clears_error():
    item = BatchItem.pending("call_001.ogg").failed("boom").succeeded(RESULT)

    assert item.status is ItemStatus.SUCCEEDED
    assert item.result is RESULT
    assert item.error_message is None


def test_failed_item_carries_reason_and_no_result():
    item = BatchItem.pending("call_001.ogg").succeeded(RESULT).failed("unsupported codec")

    assert item.status is ItemStatus.FAILED
    assert item.result is None
    assert item.error_message == "unsupported codec"


def test_transitions_do_not_mutate_the_original_item():
    original = BatchItem.pending("call_001.ogg")

    original.succeeded(RESULT)

    assert original.status is ItemStatus.PENDING


def test_new_batch_is_pending():
    assert batch_of("a.ogg").status is BatchStatus.PENDING


def test_batch_records_unmatched_files_separately_from_items():
    batch = batch_of("a.ogg", unmatched=("stray.ogg",))

    assert [item.filename for item in batch.items] == ["a.ogg"]
    assert batch.unmatched_files == ("stray.ogg",)


def test_started_and_completed_advance_status():
    batch = batch_of("a.ogg")

    assert batch.started().status is BatchStatus.RUNNING
    assert batch.started().completed().status is BatchStatus.COMPLETED


def test_pending_items_excludes_already_resolved_items():
    batch = batch_of("a.ogg", "b.ogg")
    resolved = batch.items[0].succeeded(RESULT)

    remaining = batch.replacing(resolved).pending_items

    assert [item.filename for item in remaining] == ["b.ogg"]


def test_replacing_preserves_item_order():
    batch = batch_of("a.ogg", "b.ogg", "c.ogg")

    updated = batch.replacing(batch.items[1].succeeded(RESULT))

    assert [item.filename for item in updated.items] == ["a.ogg", "b.ogg", "c.ogg"]
    assert updated.items[1].status is ItemStatus.SUCCEEDED


def test_replacing_an_unknown_item_is_rejected():
    batch = batch_of("a.ogg")

    with pytest.raises(KeyError):
        batch.replacing(BatchItem.pending("ghost.ogg"))


def test_counts_reflect_item_outcomes():
    batch = batch_of("a.ogg", "b.ogg", "c.ogg")
    batch = batch.replacing(batch.items[0].succeeded(RESULT))
    batch = batch.replacing(batch.items[1].failed("boom"))

    assert (batch.total, batch.succeeded_count, batch.failed_count) == (3, 1, 1)
