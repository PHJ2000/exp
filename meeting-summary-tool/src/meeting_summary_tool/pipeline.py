"""Top-level pipeline orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from meeting_summary_tool.config import resolve_default_output_dir
from meeting_summary_tool.io.output_writer import write_markdown_output
from meeting_summary_tool.models import ActionItem
from meeting_summary_tool.models import AudioInput
from meeting_summary_tool.models import DecisionItem
from meeting_summary_tool.models import PipelineResult
from meeting_summary_tool.models import SavedArtifact
from meeting_summary_tool.models import SummaryDocument
from meeting_summary_tool.stt.transcribe import TranscriptionError
from meeting_summary_tool.stt.transcribe import transcribe_audio
from meeting_summary_tool.summarize.backend import SummaryBackend
from meeting_summary_tool.summarize.backend import SummaryRequest
from meeting_summary_tool.summarize.backend import SummaryResult
from meeting_summary_tool.summarize.backend import build_default_backend


@dataclass(slots=True)
class PreparedPipelineRun:
    """Normalized run plan prepared by the CLI layer."""

    audio_input: AudioInput
    output_dir: Path
    warnings: list[str] = field(default_factory=list)


class PipelineExecutionError(RuntimeError):
    """Raised when the end-to-end pipeline cannot complete."""


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


def _normalized_audio_input(prepared_run: PreparedPipelineRun) -> AudioInput:
    """Apply default values needed for actual execution."""

    meeting_date = prepared_run.audio_input.meeting_date or datetime.now().date().isoformat()
    meeting_title = prepared_run.audio_input.meeting_title or prepared_run.audio_input.audio_path.stem
    return replace(
        prepared_run.audio_input,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        output_dir=prepared_run.output_dir,
    )


def _build_summary_document(summary_result: SummaryResult) -> SummaryDocument:
    """Convert backend summary output into the shared summary model."""

    return SummaryDocument(
        summary=summary_result.summary,
        decisions=[
            DecisionItem(text=item.text, confidence=item.confidence)
            for item in summary_result.decisions
        ],
        action_items=[
            ActionItem(
                text=item.text,
                confidence=item.confidence,
                owner=item.owner,
                due_date=item.due_date,
            )
            for item in summary_result.action_items
        ],
        provider=summary_result.provider,
        model_name=summary_result.model_name,
        warnings=list(summary_result.warnings),
    )


def run_pipeline(
    prepared_run: PreparedPipelineRun,
    *,
    model_provider: str = "mock",
    model_name: str | None = None,
    summary_backend: SummaryBackend | None = None,
) -> PipelineResult:
    """Run the minimum end-to-end pipeline."""

    normalized_input = _normalized_audio_input(prepared_run)
    pipeline_warnings = list(prepared_run.warnings)

    try:
        transcript = transcribe_audio(normalized_input.audio_path)
    except (FileNotFoundError, ValueError, TranscriptionError) as exc:
        raise PipelineExecutionError(str(exc)) from exc

    backend = summary_backend or build_default_backend()
    summary_request = SummaryRequest(
        transcript=transcript,
        job_id=f"{normalized_input.meeting_date}-{normalized_input.meeting_title}",
        meeting_title=normalized_input.meeting_title,
        meeting_date=normalized_input.meeting_date,
        model_provider=model_provider,
        model_name=model_name,
        output_dir=normalized_input.output_dir,
    )

    try:
        summary_result = backend.summarize(summary_request)
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise PipelineExecutionError(f"요약 단계 실행에 실패했습니다: {exc}") from exc

    summary = _build_summary_document(summary_result)
    pipeline_warnings.extend(transcript.warnings)
    pipeline_warnings.extend(summary.warnings)

    result = PipelineResult(
        audio_input=normalized_input,
        transcript=transcript,
        summary=summary,
        warnings=pipeline_warnings,
    )

    try:
        output_path = write_markdown_output(result)
    except Exception as exc:  # pragma: no cover - filesystem boundary
        raise PipelineExecutionError(f"Markdown 저장에 실패했습니다: {exc}") from exc

    result.artifacts.append(SavedArtifact(path=output_path, kind="markdown"))
    return result
