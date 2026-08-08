from dataclasses import dataclass
from pathlib import Path

SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {".wav", ".mp3", ".ogg", ".oga", ".opus", ".flac", ".m4a", ".aac", ".webm"}
)


def is_supported_audio(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


@dataclass(frozen=True)
class AudioClip:
    """An audio file to analyse.

    `filename` is the name from the manifest and is what appears in exported results;
    `path` is wherever the bytes currently live. Keeping them separate is what lets
    downloads preserve original filenames regardless of internal storage layout.
    """

    filename: str
    path: Path
