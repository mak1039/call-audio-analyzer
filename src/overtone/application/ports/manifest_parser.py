from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ManifestRow:
    """One row of the evaluation manifest.

    `expected_result` is the label from `result_json` when the batch is labelled. It is
    never fed to the analyzer — it exists so predictions can be shown beside labels.
    `label_error` records an unparseable `result_json` without discarding the row.
    """

    name: str
    expected_result: dict[str, object] | None = None
    label_error: str | None = None


class ManifestParser(ABC):
    @abstractmethod
    def parse(self, content: bytes) -> tuple[ManifestRow, ...]:
        """Parse manifest bytes, or raise ManifestError if it is structurally unusable."""
