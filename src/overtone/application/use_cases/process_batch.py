import logging

from overtone.application.ports.audio_analyzer import AudioAnalyzer
from overtone.application.ports.batch_repository import BatchRepository
from overtone.application.ports.file_storage import FileStorage
from overtone.domain.audio_clip import AudioClip
from overtone.domain.batch import Batch, BatchId, BatchItem

logger = logging.getLogger(__name__)


class ProcessBatch:
    """Runs the analyzer over every pending item, isolating per-item failures.

    Isolation lives here rather than in any adapter, so every present and future
    analyzer inherits it without having to remember to.
    """

    def __init__(
        self,
        analyzer: AudioAnalyzer,
        storage: FileStorage,
        repository: BatchRepository,
    ) -> None:
        self._analyzer = analyzer
        self._storage = storage
        self._repository = repository

    def execute(self, batch_id: BatchId) -> None:
        batch = self._repository.get(batch_id).started()
        self._repository.save(batch)
        try:
            self._run(batch)
        except Exception:
            self._mark_failed(batch_id)
            raise
        finally:
            self._storage.discard(batch_id)

    def _run(self, batch: Batch) -> None:
        for item in batch.pending_items:
            batch = batch.replacing(self._analyze(batch.batch_id, item))
            self._repository.save(batch)
        self._repository.save(batch.completed())

    def _mark_failed(self, batch_id: BatchId) -> None:
        try:
            self._repository.save(self._repository.get(batch_id).failed())
        except Exception:  # noqa: BLE001 - already failing; do not mask the original error
            logger.exception("could not record batch failure")

    def _analyze(self, batch_id: BatchId, item: BatchItem) -> BatchItem:
        try:
            clip = AudioClip(item.filename, self._storage.path_for(batch_id, item.filename))
            return item.succeeded(self._analyzer.analyze(clip))
        except Exception as error:  # noqa: BLE001 - one bad file must never sink the batch
            return item.failed(f"{type(error).__name__}: {error}")
