from abc import ABC, abstractmethod
from pathlib import Path


class ArchiveExtractor(ABC):
    @abstractmethod
    def extract(self, archive: Path, destination: Path) -> tuple[Path, ...]:
        """Extract the archive into destination and return the extracted file paths.

        Raises CorruptArchiveError if the archive cannot be read or contains unsafe entries.
        """
