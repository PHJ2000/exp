"""Top-level pipeline orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from meeting_summary_tool.config import resolve_default_output_dir
from meeting_summary_tool.models import AudioInput


@dataclass(slots=True)
class PreparedPipelineRun:
    """Normalized run plan prepared by the CLI layer."""

    audio_input: AudioInput
    output_dir: Path
    warnings: list[str] = field(default_factory=list)


def prepare_pipeline_run(audio_input: AudioInput) -> PreparedPipelineRun:
    """Prepare a normalized run plan before the real pipeline is wired."""

    output_dir = audio_input.output_dir or resolve_default_output_dir()
    warnings: list[str] = []

    if not audio_input.meeting_title:
        warnings.append("회의 제목이 없어 파일명 기반 기본값을 사용하게 됩니다.")
    if not audio_input.meeting_date:
        warnings.append("회의 날짜가 없어 실행 시점 기반 기본값을 사용하게 됩니다.")

    return PreparedPipelineRun(
        audio_input=audio_input,
        output_dir=output_dir,
        warnings=warnings,
    )


def run_pipeline() -> None:
    """Placeholder pipeline entrypoint.

    The real orchestration logic is added in follow-up issues.
    """

    raise NotImplementedError("Pipeline orchestration is not implemented yet.")
