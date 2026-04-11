"""Shared data models for the meeting summary pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AudioInput:
    """User-provided audio input and metadata."""

    audio_path: Path
    meeting_title: str | None = None
    meeting_date: str | None = None
    attendees: list[str] = field(default_factory=list)
    notes: str | None = None
    output_dir: Path | None = None


@dataclass(slots=True)
class TranscriptSegment:
    """A single transcript segment."""

    text: str
    speaker: str | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    confidence: float | None = None

    def as_text_line(self) -> str:
        """Render a human-readable transcript line."""

        prefix = f"{self.speaker}: " if self.speaker else ""
        return f"{prefix}{self.text}".strip()


@dataclass(slots=True)
class TranscriptDocument:
    """Normalized transcript output produced by STT."""

    source_file: Path
    segments: list[TranscriptSegment] = field(default_factory=list)
    full_text: str = ""
    language: str = "ko"
    duration_sec: float | None = None
    model_name: str | None = None
    device: str | None = None
    warnings: list[str] = field(default_factory=list)

    def has_content(self) -> bool:
        """Return whether the transcript contains usable text."""

        return bool(self.full_text.strip() or self.segments)


@dataclass(slots=True)
class DecisionItem:
    """A decision extracted from a meeting."""

    text: str


@dataclass(slots=True)
class ActionItem:
    """An action item extracted from a meeting."""

    text: str
    owner: str | None = None
    due_date: str | None = None


@dataclass(slots=True)
class SummaryDocument:
    """Structured summary output generated from a transcript."""

    summary: str
    decisions: list[DecisionItem] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    provider: str | None = None
    model_name: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SavedArtifact:
    """A file created by the pipeline."""

    path: Path
    kind: str


@dataclass(slots=True)
class PipelineResult:
    """Combined pipeline result across transcript, summary, and saved files."""

    audio_input: AudioInput
    transcript: TranscriptDocument | None = None
    summary: SummaryDocument | None = None
    artifacts: list[SavedArtifact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
