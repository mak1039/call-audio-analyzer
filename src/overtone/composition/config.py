from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Everything the composition root needs to wire the system."""

    workspace_root: Path
