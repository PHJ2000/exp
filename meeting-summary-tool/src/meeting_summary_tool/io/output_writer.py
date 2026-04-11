"""Markdown output helpers for meeting-summary-tool."""

from __future__ import annotations

import re
from pathlib import Path

from meeting_summary_tool.config import resolve_default_output_dir
from meeting_summary_tool.models import AudioInput
from meeting_summary_tool.models import PipelineResult
from meeting_summary_tool.models import SummaryDocument
from meeting_summary_tool.models import TranscriptDocument


def slugify_title(raw_title: str) -> str:
    """Normalize a title into a filesystem-friendly slug."""

    normalized = raw_title.strip().replace(" ", "-")
    normalized = re.sub(r"[^\w\-가-힣]+", "", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-") or "meeting-summary"


def build_output_filename(audio_input: AudioInput) -> str:
    """Build the default Markdown filename."""

    date_part = audio_input.meeting_date or "undated"
    title_part = slugify_title(audio_input.meeting_title or audio_input.audio_path.stem)
    return f"{date_part}-{title_part}.md"


def resolve_output_path(audio_input: AudioInput) -> Path:
    """Resolve the final Markdown output path."""

    output_dir = audio_input.output_dir or resolve_default_output_dir()
    return output_dir / build_output_filename(audio_input)


def _render_metadata(audio_input: AudioInput, transcript: TranscriptDocument | None, summary: SummaryDocument | None, output_path: Path) -> list[str]:
    attendees = audio_input.attendees or []
    transcript_method = transcript.model_name if transcript and transcript.model_name else ""
    summary_method = summary.provider if summary and summary.provider else ""
    speaker_count = 0
    if transcript:
        speaker_count = len({segment.speaker for segment in transcript.segments if segment.speaker})

    lines = [
        "---",
        f"title: {audio_input.meeting_title or audio_input.audio_path.stem}",
        f"date: {audio_input.meeting_date or 'undated'}",
        f"source_file: {audio_input.audio_path}",
        f"output_file: {output_path}",
        "language: ko",
        "status: draft",
        f"speaker_count: {speaker_count}",
        f"duration: {transcript.duration_sec if transcript and transcript.duration_sec is not None else ''}",
        f"transcript_method: {transcript_method}",
        "speaker_method: ",
        f"summary_method: {summary_method}",
    ]
    if attendees:
        lines.append("attendees:")
        lines.extend([f"  - {attendee}" for attendee in attendees])
    else:
        lines.append("attendees: []")
    lines.append("---")
    return lines


def _render_summary_section(summary: SummaryDocument | None) -> list[str]:
    if summary is None:
        return ["## 요약", "", "- 요약 결과가 아직 생성되지 않았습니다.", ""]

    lines = ["## 요약", ""]
    if summary.summary.strip():
        lines.extend([f"- {line.strip()}" for line in summary.summary.splitlines() if line.strip()])
    else:
        lines.append("- 요약 결과가 비어 있습니다.")
    lines.append("")

    lines.append("## 결정사항")
    lines.append("")
    if summary.decisions:
        lines.extend([f"- {item.text}" for item in summary.decisions])
    else:
        lines.append("- 결정사항이 아직 정리되지 않았습니다.")
    lines.append("")

    lines.append("## 액션 아이템")
    lines.append("")
    if summary.action_items:
        for item in summary.action_items:
            owner_prefix = f"{item.owner}: " if item.owner else ""
            lines.append(f"- {owner_prefix}{item.text}")
    else:
        lines.append("- 액션 아이템이 아직 정리되지 않았습니다.")
    lines.append("")
    return lines


def _render_transcript_section(transcript: TranscriptDocument | None) -> list[str]:
    lines = ["## Transcript", ""]
    if transcript is None or not transcript.has_content():
        lines.append("Transcript가 아직 생성되지 않았습니다.")
        lines.append("")
        return lines

    if transcript.segments:
        for segment in transcript.segments:
            speaker = segment.speaker or "Speaker"
            lines.append(f"### {speaker}")
            lines.append("")
            lines.append(segment.text.strip())
            lines.append("")
        return lines

    lines.append(transcript.full_text.strip())
    lines.append("")
    return lines


def render_markdown(
    audio_input: AudioInput,
    transcript: TranscriptDocument | None = None,
    summary: SummaryDocument | None = None,
) -> str:
    """Render the meeting result as a Markdown document."""

    output_path = resolve_output_path(audio_input)
    title = audio_input.meeting_title or audio_input.audio_path.stem
    lines: list[str] = []
    lines.extend(_render_metadata(audio_input, transcript, summary, output_path))
    lines.extend(["", f"# {title}", ""])
    lines.extend(["## 메타데이터", ""])
    lines.append(f"- 날짜: {audio_input.meeting_date or 'undated'}")
    lines.append(f"- 참석자: {', '.join(audio_input.attendees) if audio_input.attendees else '미정'}")
    lines.append(f"- 원본 파일: `{audio_input.audio_path.name}`")
    lines.append("- 처리 상태: draft")
    lines.append("")
    lines.extend(_render_summary_section(summary))
    lines.extend(_render_transcript_section(transcript))
    return "\n".join(lines).rstrip() + "\n"


def write_markdown_output(result: PipelineResult) -> Path:
    """Write the rendered Markdown output to disk."""

    output_path = resolve_output_path(result.audio_input)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_markdown(
            audio_input=result.audio_input,
            transcript=result.transcript,
            summary=result.summary,
        ),
        encoding="utf-8",
    )
    return output_path
