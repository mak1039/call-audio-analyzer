from overtone.application.ports.batch_repository import BatchRepository
from overtone.domain.batch import Batch, BatchId
from overtone.domain.exceptions import BatchNotFoundError


class InMemoryBatchRepository(BatchRepository):
    """Process-local batch store. Sufficient for the CLI; the web app uses Postgres."""

    def __init__(self) -> None:
        self._batches: dict[BatchId, Batch] = {}

    def save(self, batch: Batch) -> None:
        self._batches[batch.batch_id] = batch

    def get(self, batch_id: BatchId) -> Batch:
        if batch_id not in self._batches:
            raise BatchNotFoundError(f"no batch with id {batch_id}")
        return self._batches[batch_id]

    def list_recent(self, limit: int) -> tuple[Batch, ...]:
        newest_first = sorted(
            self._batches.values(), key=lambda batch: batch.created_at, reverse=True
        )
        return tuple(newest_first[:limit])
