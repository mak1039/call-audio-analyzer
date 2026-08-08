import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import NewType

from overtone.domain.analysis_result import AnalysisResult
from overtone.domain.enums import BatchStatus, ItemStatus

BatchId = NewType("BatchId", str)


def new_batch_id() -> BatchId:
    return BatchId(uuid.uuid4().hex)


@dataclass(frozen=True)
class BatchItem:
    """One audio file within a batch, plus whatever became of it."""

    filename: str
    status: ItemStatus
    result: AnalysisResult | None = None
    error_message: str | None = None

    @classmethod
    def pending(cls, filename: str) -> "BatchItem":
        return cls(filename=filename, status=ItemStatus.PENDING)

    def succeeded(self, result: AnalysisResult) -> "BatchItem":
        return replace(self, status=ItemStatus.SUCCEEDED, result=result, error_message=None)

    def failed(self, reason: str) -> "BatchItem":
        return replace(self, status=ItemStatus.FAILED, result=None, error_message=reason)


@dataclass(frozen=True)
class Batch:
    """A submitted evaluation batch and its per-item outcomes."""

    batch_id: BatchId
    items: tuple[BatchItem, ...]
    status: BatchStatus
    created_at: datetime
    unmatched_files: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        batch_id: BatchId,
        items: tuple[BatchItem, ...],
        created_at: datetime,
        unmatched_files: tuple[str, ...] = (),
    ) -> "Batch":
        return cls(
            batch_id=batch_id,
            items=items,
            status=BatchStatus.PENDING,
            created_at=created_at,
            unmatched_files=unmatched_files,
        )

    @property
    def pending_items(self) -> tuple[BatchItem, ...]:
        return tuple(item for item in self.items if item.status is ItemStatus.PENDING)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def succeeded_count(self) -> int:
        return self._count(ItemStatus.SUCCEEDED)

    @property
    def failed_count(self) -> int:
        return self._count(ItemStatus.FAILED)

    @property
    def is_finished(self) -> bool:
        """Whether this batch has reached a terminal status and will not change again."""
        return self.status in {BatchStatus.COMPLETED, BatchStatus.FAILED}

    def started(self) -> "Batch":
        return replace(self, status=BatchStatus.RUNNING)

    def completed(self) -> "Batch":
        return replace(self, status=BatchStatus.COMPLETED)

    def failed(self) -> "Batch":
        return replace(self, status=BatchStatus.FAILED)

    def replacing(self, item: BatchItem) -> "Batch":
        index = self._index_of(item.filename)
        items = self.items[:index] + (item,) + self.items[index + 1 :]
        return replace(self, items=items)

    def _count(self, status: ItemStatus) -> int:
        return sum(1 for item in self.items if item.status is status)

    def _index_of(self, filename: str) -> int:
        for index, item in enumerate(self.items):
            if item.filename == filename:
                return index
        raise KeyError(f"batch has no item named {filename!r}")
