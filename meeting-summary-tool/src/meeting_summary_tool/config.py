"""Configuration helpers for local execution."""

from __future__ import annotations

from pathlib import Path


def resolve_project_root() -> Path:
    """Return the repository-local project directory."""

    return Path(__file__).resolve().parents[2]


def resolve_default_output_dir() -> Path:
    """Return the default output directory for generated artifacts."""

    return resolve_project_root() / "outputs" / "meeting-summary-tool"
