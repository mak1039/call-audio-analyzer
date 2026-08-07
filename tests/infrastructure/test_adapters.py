from pathlib import Path

import pytest

from overtone.domain.audio_clip import AudioClip
from overtone.domain.batch import Batch, BatchItem, new_batch_id
from overtone.domain.enums import EmotionalTone, NoiseSeverity
from overtone.domain.exceptions import BatchNotFoundError
from overtone.infrastructure.analysis.stub_analyzer import StubAnalyzer
from overtone.infrastructure.persistence.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from overtone.infrastructure.storage.local_file_storage import LocalFileStorage


def test_workspace_is_created_and_scoped_to_the_batch(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)
    first, second = new_batch_id(), new_batch_id()

    assert storage.workspace_for(first).is_dir()
    assert storage.workspace_for(first) != storage.workspace_for(second)


def test_path_for_resolves_inside_the_batch_workspace(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)
    batch_id = new_batch_id()

    path = storage.path_for(batch_id, "call_001.ogg")

    assert path.parent == storage.workspace_for(batch_id)
    assert path.name == "call_001.ogg"


def test_path_for_rejects_a_filename_that_escapes_the_workspace(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.path_for(new_batch_id(), "../escape.ogg")


def test_repository_returns_the_saved_batch():
    repository = InMemoryBatchRepository()
    batch = Batch.create(new_batch_id(), (BatchItem.pending("a.ogg"),))

    repository.save(batch)

    assert repository.get(batch.batch_id) == batch


def test_repository_keeps_only_the_latest_save():
    repository = InMemoryBatchRepository()
    batch = Batch.create(new_batch_id(), (BatchItem.pending("a.ogg"),))
    repository.save(batch)

    repository.save(batch.started())

    assert repository.get(batch.batch_id).status is batch.started().status


def test_repository_raises_for_an_unknown_batch():
    with pytest.raises(BatchNotFoundError):
        InMemoryBatchRepository().get(new_batch_id())


def test_stub_analyzer_returns_a_schema_valid_neutral_result(tmp_path: Path):
    result = StubAnalyzer().analyze(AudioClip("a.ogg", tmp_path / "a.ogg"))

    assert result.emotional_tone is EmotionalTone.NEUTRAL
    assert result.background_noise_present is False
    assert result.background_noise_severity is NoiseSeverity.NONE
    assert 0.0 <= result.confidence <= 1.0


def test_stub_analyzer_is_deterministic(tmp_path: Path):
    analyzer = StubAnalyzer()
    clip = AudioClip("a.ogg", tmp_path / "a.ogg")

    assert analyzer.analyze(clip) == analyzer.analyze(clip)
