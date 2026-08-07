import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from overtone.application.ports.file_storage import FileStorage
from overtone.domain.batch import BatchId

logger = logging.getLogger(__name__)


class LocalFileStorage(FileStorage):
    """Filesystem-backed batch workspaces, one directory per batch."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def workspace_for(self, batch_id: BatchId) -> Path:
        workspace = self._root / batch_id
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def path_for(self, batch_id: BatchId, filename: str) -> Path:
        workspace = self.workspace_for(batch_id)
        candidate = (workspace / filename).resolve()
        if candidate.parent != workspace.resolve():
            raise ValueError(f"filename '{filename}' escapes the batch workspace")
        return candidate

    def discard(self, batch_id: BatchId) -> None:
        shutil.rmtree(self._root / batch_id, onexc=self._log_discard_failure)

    def _log_discard_failure(
        self, func: Callable[..., object], path: str, exc: BaseException
    ) -> None:
        if isinstance(exc, FileNotFoundError):
            return
        logger.error("failed to discard %s during %s: %s", path, func.__name__, exc)
