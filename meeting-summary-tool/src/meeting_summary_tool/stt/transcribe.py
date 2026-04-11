"""Minimal faster-whisper transcription prototype."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from meeting_summary_tool.models import TranscriptDocument
from meeting_summary_tool.models import TranscriptSegment


class TranscriptionError(RuntimeError):
    """Raised when transcription cannot complete."""


def _load_whisper_model(model_name: str, device: str, compute_type: str) -> Any:
    """Load a WhisperModel instance lazily."""

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise TranscriptionError(
            "faster-whisper가 설치되어 있지 않습니다. requirements를 먼저 준비해 주세요."
        ) from exc

    try:
        return WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:  # pragma: no cover - external runtime
        raise TranscriptionError(f"Whisper 모델을 불러오지 못했습니다: {exc}") from exc


def _segment_from_whisper(segment: Any) -> TranscriptSegment:
    """Convert a faster-whisper segment into the shared model."""

    return TranscriptSegment(
        text=(getattr(segment, "text", "") or "").strip(),
        start_sec=float(getattr(segment, "start", 0.0)),
        end_sec=float(getattr(segment, "end", 0.0)),
    )


def transcribe_audio(
    audio_path: str | Path,
    *,
    model_name: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
    language: str = "ko",
    beam_size: int = 5,
    vad_filter: bool = True,
) -> TranscriptDocument:
    """Transcribe an audio file into the shared transcript model."""

    resolved_path = Path(audio_path).expanduser().resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {resolved_path}")
    if not resolved_path.is_file():
        raise ValueError(f"입력 경로가 파일이 아닙니다: {resolved_path}")

    model = _load_whisper_model(model_name=model_name, device=device, compute_type=compute_type)

    try:
        raw_segments, info = model.transcribe(
            str(resolved_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )
    except Exception as exc:  # pragma: no cover - external runtime
        raise TranscriptionError(f"오디오 전사를 실행하지 못했습니다: {exc}") from exc

    segments = [_segment_from_whisper(segment) for segment in raw_segments]
    full_text = " ".join(segment.text for segment in segments if segment.text).strip()
    detected_language = getattr(info, "language", language) or language
    duration_sec = getattr(info, "duration", None)

    warnings: list[str] = []
    if not segments:
        warnings.append("전사 결과 세그먼트가 비어 있습니다.")
    if not full_text:
        warnings.append("전사 텍스트가 비어 있습니다.")

    return TranscriptDocument(
        source_file=resolved_path,
        segments=segments,
        full_text=full_text,
        language=detected_language,
        duration_sec=float(duration_sec) if duration_sec is not None else None,
        model_name=model_name,
        device=device,
        warnings=warnings,
    )
