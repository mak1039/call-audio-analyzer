import logging
from pathlib import Path

from overtone.application.ports.archive_extractor import ArchiveExtractor
from overtone.application.ports.batch_repository import BatchRepository
from overtone.application.ports.clock import Clock
from overtone.application.ports.file_storage import FileStorage
from overtone.application.ports.manifest_parser import ManifestParser, ManifestRow
from overtone.domain.audio_clip import is_supported_audio
from overtone.domain.batch import Batch, BatchId, BatchItem, new_batch_id
from overtone.domain.exceptions import ManifestError

logger = logging.getLogger(__name__)

MANIFEST_SUFFIX = ".csv"


class SubmitBatch:
    """Accepts an uploaded archive and turns it into a batch ready for processing.

    Mismatches between the manifest and the archive are recorded, never fatal: a row with
    no file fails that item alone, and a file with no row is reported as unmatched.

    A batch that cannot be accepted at all leaves nothing behind: the workspace is discarded
    before the error escapes, because extraction has already written confidential audio to it.
    """

    def __init__(
        self,
        extractor: ArchiveExtractor,
        parser: ManifestParser,
        storage: FileStorage,
        repository: BatchRepository,
        clock: Clock,
    ) -> None:
        self._extractor = extractor
        self._parser = parser
        self._storage = storage
        self._repository = repository
        self._clock = clock

    def execute(self, archive: Path) -> BatchId:
        batch_id = new_batch_id()
        workspace = self._storage.workspace_for(batch_id)
        try:
            batch = self._build_batch(batch_id, archive, workspace)
        except BaseException:
            self._discard(batch_id)
            raise
        self._repository.save(batch)
        return batch_id

    def _build_batch(self, batch_id: BatchId, archive: Path, workspace: Path) -> Batch:
        extracted = self._extractor.extract(archive, workspace)
        rows = self._parser.parse(self._manifest_of(extracted).read_bytes())
        audio_names = self._audio_names(extracted)
        return Batch.create(
            batch_id,
            items=tuple(self._to_item(row, audio_names) for row in rows),
            created_at=self._clock.now(),
            unmatched_files=self._unmatched(audio_names, rows),
        )

    def _discard(self, batch_id: BatchId) -> None:
        try:
            self._storage.discard(batch_id)
        except Exception:  # noqa: BLE001 - cleanup must not mask why the batch was rejected
            logger.exception("could not discard the workspace of rejected batch %s", batch_id)

    def _manifest_of(self, extracted: tuple[Path, ...]) -> Path:
        manifests = [path for path in extracted if path.suffix.lower() == MANIFEST_SUFFIX]
        if len(manifests) != 1:
            raise ManifestError(
                f"batch must contain exactly one CSV manifest, found {len(manifests)}"
            )
        return manifests[0]

    def _audio_names(self, extracted: tuple[Path, ...]) -> tuple[str, ...]:
        return tuple(path.name for path in extracted if is_supported_audio(path.name))

    def _to_item(self, row: ManifestRow, audio_names: tuple[str, ...]) -> BatchItem:
        item = BatchItem.pending(row.name)
        if row.name in audio_names:
            return item
        return item.failed(f"'{row.name}' is listed in the manifest but absent from the batch")

    def _unmatched(
        self, audio_names: tuple[str, ...], rows: tuple[ManifestRow, ...]
    ) -> tuple[str, ...]:
        listed = {row.name for row in rows}
        return tuple(name for name in audio_names if name not in listed)
