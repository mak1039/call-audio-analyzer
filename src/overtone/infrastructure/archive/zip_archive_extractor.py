import shutil
import zipfile
from pathlib import Path

from overtone.application.ports.archive_extractor import ArchiveExtractor
from overtone.domain.exceptions import CorruptArchiveError

DEFAULT_MAX_ENTRIES = 1000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 2 * 1024**3
RESOURCE_FORK_PREFIX = "__MACOSX/"


class ZipArchiveExtractor(ArchiveExtractor):
    """Extracts an uploaded batch, flattening any wrapper directory to the root.

    Entries are validated before anything is written: an archive that tries to escape
    the destination is rejected outright rather than quietly sanitised, because a batch
    containing such an entry is not a legitimate evaluation batch.
    """

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    ) -> None:
        self._max_entries = max_entries
        self._max_uncompressed_bytes = max_uncompressed_bytes

    def extract(self, archive: Path, destination: Path) -> tuple[Path, ...]:
        try:
            with zipfile.ZipFile(archive) as opened:
                return self._extract_all(opened, destination)
        except (OSError, zipfile.BadZipFile) as error:
            raise CorruptArchiveError(
                f"could not read archive '{archive.name}': {error}"
            ) from error

    def _extract_all(self, archive: zipfile.ZipFile, destination: Path) -> tuple[Path, ...]:
        entries = self._payload_entries(archive)
        self._enforce_caps(entries)
        names = self._flattened_names(entries)
        pairs = zip(entries, names, strict=True)
        return tuple(self._write(archive, entry, destination / name) for entry, name in pairs)

    def _payload_entries(self, archive: zipfile.ZipFile) -> tuple[zipfile.ZipInfo, ...]:
        return tuple(
            entry
            for entry in archive.infolist()
            if not entry.is_dir() and not entry.filename.startswith(RESOURCE_FORK_PREFIX)
        )

    def _enforce_caps(self, entries: tuple[zipfile.ZipInfo, ...]) -> None:
        if len(entries) > self._max_entries:
            raise CorruptArchiveError(
                f"archive holds {len(entries)} files, limit is {self._max_entries}"
            )
        total = sum(entry.file_size for entry in entries)
        if total > self._max_uncompressed_bytes:
            raise CorruptArchiveError(
                f"archive expands to {total} bytes, limit is {self._max_uncompressed_bytes}"
            )

    def _flattened_names(self, entries: tuple[zipfile.ZipInfo, ...]) -> tuple[str, ...]:
        names = tuple(self._safe_basename(entry.filename) for entry in entries)
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise CorruptArchiveError(f"archive holds duplicate filenames: {sorted(duplicates)}")
        return names

    def _safe_basename(self, entry_name: str) -> str:
        parts = entry_name.replace("\\", "/").split("/")
        if entry_name.startswith("/") or ".." in parts or ":" in parts[0]:
            raise CorruptArchiveError(f"archive entry '{entry_name}' escapes the destination")
        return parts[-1]

    def _write(self, archive: zipfile.ZipFile, entry: zipfile.ZipInfo, target: Path) -> Path:
        with archive.open(entry) as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink)
        return target
