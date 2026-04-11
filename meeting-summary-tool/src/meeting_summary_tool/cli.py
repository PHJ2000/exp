"""CLI entrypoint for the meeting summary tool."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from meeting_summary_tool.models import AudioInput
from meeting_summary_tool.pipeline import PipelineExecutionError
from meeting_summary_tool.pipeline import prepare_pipeline_run
from meeting_summary_tool.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="meeting-summary-tool",
        description="회의 오디오 파일 입력과 기본 실행 계획을 준비합니다.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="전사할 오디오 파일 경로",
    )
    parser.add_argument(
        "--title",
        help="회의 제목",
    )
    parser.add_argument(
        "--date",
        help="회의 날짜 (예: 2026-04-11)",
    )
    parser.add_argument(
        "--attendees",
        help="쉼표로 구분한 참석자 목록",
    )
    parser.add_argument(
        "--notes",
        help="추가 메모",
    )
    parser.add_argument(
        "--output-dir",
        help="결과 저장 디렉토리",
    )
    parser.add_argument(
        "--summary-provider",
        default="mock",
        choices=["mock", "ollama", "openai"],
        help="요약 백엔드 선택",
    )
    parser.add_argument(
        "--summary-model",
        help="요약 모델 이름",
    )
    return parser


def parse_attendees(raw_attendees: str | None) -> list[str]:
    """Parse a comma-separated attendee list."""

    if not raw_attendees:
        return []
    return [item.strip() for item in raw_attendees.split(",") if item.strip()]


def build_audio_input_from_args(args: argparse.Namespace) -> AudioInput:
    """Convert CLI arguments into the shared audio input model."""

    audio_path = Path(args.input).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {audio_path}")
    if not audio_path.is_file():
        raise ValueError(f"입력 경로가 파일이 아닙니다: {audio_path}")

    output_dir = None
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()

    return AudioInput(
        audio_path=audio_path,
        meeting_title=args.title,
        meeting_date=args.date,
        attendees=parse_attendees(args.attendees),
        notes=args.notes,
        output_dir=output_dir,
    )


def _render_run_summary(audio_input: AudioInput) -> list[str]:
    """Build a user-facing summary for the prepared run."""

    lines = [
        "meeting-summary-tool CLI 입력이 준비되었습니다.",
        f"- 입력 파일: {audio_input.audio_path}",
    ]
    if audio_input.meeting_title:
        lines.append(f"- 회의 제목: {audio_input.meeting_title}")
    if audio_input.meeting_date:
        lines.append(f"- 회의 날짜: {audio_input.meeting_date}")
    if audio_input.attendees:
        lines.append(f"- 참석자: {', '.join(audio_input.attendees)}")
    if audio_input.output_dir:
        lines.append(f"- 출력 디렉토리: {audio_input.output_dir}")
    return lines


def _render_result_summary(markdown_paths: list[Path], warnings: list[str]) -> list[str]:
    """Build a user-facing result summary."""

    lines = ["meeting-summary-tool 파이프라인 실행이 완료되었습니다."]
    if markdown_paths:
        lines.append("- 생성 파일:")
        for path in markdown_paths:
            lines.append(f"  - {path}")
    if warnings:
        lines.append("- 경고:")
        for warning in warnings:
            lines.append(f"  - {warning}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        audio_input = build_audio_input_from_args(args)
    except (FileNotFoundError, ValueError) as exc:
        parser.exit(status=2, message=f"{exc}\n")

    prepared_run = prepare_pipeline_run(audio_input)

    for line in _render_run_summary(prepared_run.audio_input):
        print(line)
    print(f"- 정규화된 출력 디렉토리: {prepared_run.output_dir}")

    try:
        result = run_pipeline(
            prepared_run,
            model_provider=args.summary_provider,
            model_name=args.summary_model,
        )
    except PipelineExecutionError as exc:
        parser.exit(status=1, message=f"파이프라인 실행 실패: {exc}\n")

    markdown_paths = [artifact.path for artifact in result.artifacts if artifact.kind == "markdown"]
    for line in _render_result_summary(markdown_paths, result.warnings):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
