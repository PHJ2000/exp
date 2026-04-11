"""Audio input loading helpers."""

from __future__ import annotations

from pathlib import Path


def resolve_audio_path(raw_path: str | Path) -> Path:
    """Normalize a user-provided audio path."""

    return Path(raw_path).expanduser().resolve()
