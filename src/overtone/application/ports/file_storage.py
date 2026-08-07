from abc import ABC, abstractmethod
from pathlib import Path

from overtone.domain.batch import BatchId


class FileStorage(ABC):
    @abstractmethod
    def workspace_for(self, batch_id: BatchId) -> Path:
        """Return (creating if needed) the directory holding this batch's files."""

    @abstractmethod
    def path_for(self, batch_id: BatchId, filename: str) -> Path:
        """Return where a named file within this batch lives."""
