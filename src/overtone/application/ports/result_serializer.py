from abc import ABC, abstractmethod

from overtone.domain.batch import Batch


class ResultSerializer(ABC):
    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Extension for the downloadable file, without a leading dot."""

    @abstractmethod
    def serialize(self, batch: Batch) -> str:
        """Render the batch's predictions as downloadable text."""
