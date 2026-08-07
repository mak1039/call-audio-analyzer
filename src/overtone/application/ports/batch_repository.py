from abc import ABC, abstractmethod

from overtone.domain.batch import Batch, BatchId


class BatchRepository(ABC):
    @abstractmethod
    def save(self, batch: Batch) -> None: ...

    @abstractmethod
    def get(self, batch_id: BatchId) -> Batch:
        """Return the batch, or raise BatchNotFoundError."""

    @abstractmethod
    def list_recent(self, limit: int) -> tuple[Batch, ...]:
        """Return up to `limit` batches, newest first."""

    def close(self) -> None:
        """Release any held resources (connections, pools, ...).

        No-op by default. Implementations that own real resources should override this.
        """
        return
