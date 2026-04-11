"""Summary backend skeleton for meeting-summary-tool.

This module keeps the summarization layer deliberately small and explicit:

- a request model that accepts normalized transcript data
- a provider protocol that can later be backed by Ollama or OpenAI BYOK
- a summary backend that tries configured providers in order
- a deterministic mock fallback so the pipeline never hard-fails

The implementation is intentionally dependency-free so it can be used as an
early scaffold for the rest of the project.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

__all__ = [
    "ActionItem",
    "DecisionItem",
    "PromptMessage",
    "SummaryBackend",
    "SummaryBackendConfig",
    "SummaryItem",
    "SummaryPayload",
    "SummaryProvider",
    "SummaryRequest",
    "SummaryResult",
    "TranscriptDocument",
    "TranscriptSegment",
    "MockSummaryProvider",
    "OllamaSummaryProvider",
    "OpenAISummaryProvider",
    "build_default_backend",
]


@dataclass(slots=True)
class TranscriptSegment:
    """A single normalized transcript segment."""

    speaker: str
    text: str
    start_sec: float | None = None
    end_sec: float | None = None

    def as_text(self) -> str:
        prefix = f"{self.speaker}: " if self.speaker else ""
        return f"{prefix}{self.text}".strip()


@dataclass(slots=True)
class TranscriptDocument:
    """Normalized transcript input consumed by the summary backend."""

    segments: list[TranscriptSegment] = field(default_factory=list)
    transcript_text: str | None = None
    speaker_map: dict[str, str] = field(default_factory=dict)
    language: str = "ko"

    def iter_lines(self) -> list[str]:
        if self.segments:
            return [segment.as_text() for segment in self.segments if segment.text.strip()]
        if self.transcript_text:
            return [line.strip() for line in self.transcript_text.splitlines() if line.strip()]
        return []

    def render_text(self) -> str:
        lines = self.iter_lines()
        return "\n".join(lines)


@dataclass(slots=True)
class SummaryRequest:
    """Input required to generate a meeting summary."""

    transcript: TranscriptDocument
    job_id: str
    meeting_title: str | None = None
    meeting_date: str | None = None
    summary_mode: str = "standard"
    model_provider: str = "mock"
    model_name: str | None = None
    api_key: str | None = None
    output_dir: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SummaryItem:
    """Base structure for structured summary items."""

    text: str
    confidence: float | None = None


@dataclass(slots=True)
class DecisionItem(SummaryItem):
    """A meeting decision extracted from the transcript."""


@dataclass(slots=True)
class ActionItem(SummaryItem):
    """A meeting action item extracted from the transcript."""

    owner: str | None = None
    due_date: str | None = None


@dataclass(slots=True)
class SummaryPayload:
    """Structured summary content returned by a provider."""

    summary: str
    decisions: list[DecisionItem] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SummaryResult:
    """Final output emitted by the backend."""

    job_id: str
    title: str
    summary: str
    decisions: list[DecisionItem] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    provider: str = "mock"
    model_name: str | None = None
    fallback_used: bool = False
    warnings: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_response: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "summary": self.summary,
            "decisions": [asdict(item) for item in self.decisions],
            "action_items": [asdict(item) for item in self.action_items],
            "provider": self.provider,
            "model_name": self.model_name,
            "fallback_used": self.fallback_used,
            "warnings": list(self.warnings),
            "generated_at": self.generated_at,
            "raw_response": self.raw_response,
        }


@dataclass(slots=True)
class PromptMessage:
    """Simple chat-style prompt message."""

    role: str
    content: str


class SummaryProvider(Protocol):
    """Provider interface for Ollama/OpenAI/mock backends."""

    name: str

    def generate(self, request: SummaryRequest, messages: Sequence[PromptMessage]) -> str:
        """Return a raw provider response as text."""


@dataclass(slots=True)
class SummaryBackendConfig:
    """Configures provider ordering and fallback behavior."""

    providers: list[SummaryProvider] = field(default_factory=list)
    use_mock_fallback: bool = True
    default_title: str = "회의 요약"


class SummaryBackend:
    """Summarization adapter that tries providers in order and falls back safely."""

    def __init__(self, config: SummaryBackendConfig | None = None) -> None:
        self._config = config or SummaryBackendConfig()

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        title = self._resolve_title(request)
        warnings: list[str] = []
        messages = self._build_messages(request, title)

        for provider in self._provider_chain(request):
            try:
                raw_response = provider.generate(request, messages)
                payload = self._parse_payload(raw_response, request, title)
                return SummaryResult(
                    job_id=request.job_id,
                    title=title,
                    summary=payload.summary,
                    decisions=payload.decisions,
                    action_items=payload.action_items,
                    provider=getattr(provider, "name", request.model_provider),
                    model_name=request.model_name,
                    fallback_used=provider.name == "mock",
                    warnings=payload.notes + warnings,
                    raw_response=raw_response,
                )
            except Exception as exc:  # pragma: no cover - defensive fallback path
                warnings.append(f"{provider.name} failed: {exc}")

        if self._config.use_mock_fallback:
            mock_provider = MockSummaryProvider()
            raw_response = mock_provider.generate(request, messages)
            payload = self._parse_payload(raw_response, request, title)
            return SummaryResult(
                job_id=request.job_id,
                title=title,
                summary=payload.summary,
                decisions=payload.decisions,
                action_items=payload.action_items,
                provider=mock_provider.name,
                model_name=request.model_name,
                fallback_used=True,
                warnings=payload.notes + warnings,
                raw_response=raw_response,
            )

        raise RuntimeError("No summary provider succeeded and mock fallback is disabled.")

    def _provider_chain(self, request: SummaryRequest) -> list[SummaryProvider]:
        if self._config.providers:
            return list(self._config.providers)

        provider_name = request.model_provider.lower().strip()
        provider: SummaryProvider
        if provider_name == "ollama":
            provider = OllamaSummaryProvider(model_name=request.model_name)
        elif provider_name == "openai":
            provider = OpenAISummaryProvider(
                model_name=request.model_name,
                api_key=request.api_key,
            )
        else:
            provider = MockSummaryProvider()

        return [provider]

    def _build_messages(self, request: SummaryRequest, title: str) -> list[PromptMessage]:
        transcript_text = request.transcript.render_text()
        system_prompt = (
            "You are a meeting summarization engine. "
            "Return a compact JSON object with summary, decisions, and action_items."
        )
        user_prompt = "\n".join(
            [
                f"meeting_title: {title}",
                f"job_id: {request.job_id}",
                f"summary_mode: {request.summary_mode}",
                f"language: {request.transcript.language}",
                "transcript:",
                transcript_text or "(empty transcript)",
            ]
        )
        return [
            PromptMessage(role="system", content=system_prompt),
            PromptMessage(role="user", content=user_prompt),
        ]

    def _resolve_title(self, request: SummaryRequest) -> str:
        if request.meeting_title and request.meeting_title.strip():
            return request.meeting_title.strip()

        if request.output_dir:
            stem = Path(request.output_dir).name.strip()
            if stem:
                return stem

        return self._config.default_title

    def _parse_payload(
        self,
        raw_response: str,
        request: SummaryRequest,
        title: str,
    ) -> SummaryPayload:
        parsed = _extract_json_object(raw_response)
        if parsed is None:
            return self._fallback_payload(request, title, notes=["provider response was not valid JSON"])

        summary_text = _clean_text(parsed.get("summary")) or self._summarize_from_transcript(request)
        decisions = _parse_decisions(parsed.get("decisions"))
        action_items = _parse_action_items(parsed.get("action_items"))
        notes = _parse_notes(parsed.get("notes"))

        return SummaryPayload(
            summary=summary_text,
            decisions=decisions,
            action_items=action_items,
            notes=notes,
        )

    def _fallback_payload(self, request: SummaryRequest, title: str, notes: list[str] | None = None) -> SummaryPayload:
        transcript_summary = self._summarize_from_transcript(request)
        decision_text = _first_non_empty_line(request.transcript.render_text())
        decisions = [DecisionItem(text=decision_text)] if decision_text else []
        action_items = _extract_action_items_from_transcript(request.transcript.render_text())
        return SummaryPayload(
            summary=transcript_summary or f"{title}에 대한 요약을 생성하지 못했습니다.",
            decisions=decisions,
            action_items=action_items,
            notes=notes or [],
        )

    def _summarize_from_transcript(self, request: SummaryRequest) -> str:
        lines = request.transcript.iter_lines()
        if not lines:
            return "전사 내용이 비어 있어 요약을 생성할 수 없습니다."
        preview = lines[:3]
        return " | ".join(preview)


class MockSummaryProvider:
    """Deterministic fallback provider used during early development."""

    name = "mock"

    def generate(self, request: SummaryRequest, messages: Sequence[PromptMessage]) -> str:
        transcript_text = request.transcript.render_text()
        summary = _build_mock_summary_text(request, transcript_text)
        payload = {
            "summary": summary,
            "decisions": _mock_decisions(transcript_text),
            "action_items": _mock_action_items(transcript_text),
            "notes": ["mock fallback response"],
        }
        return json.dumps(payload, ensure_ascii=False)


class OllamaSummaryProvider:
    """Placeholder adapter for a future Ollama implementation."""

    name = "ollama"

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name

    def generate(self, request: SummaryRequest, messages: Sequence[PromptMessage]) -> str:
        raise NotImplementedError(
            "Ollama integration is not implemented yet. "
            "Use MockSummaryProvider or attach a real Ollama client later."
        )


class OpenAISummaryProvider:
    """Placeholder adapter for a future OpenAI BYOK implementation."""

    name = "openai"

    def __init__(self, model_name: str | None = None, api_key: str | None = None) -> None:
        self.model_name = model_name
        self.api_key = api_key

    def generate(self, request: SummaryRequest, messages: Sequence[PromptMessage]) -> str:
        raise NotImplementedError(
            "OpenAI integration is not implemented yet. "
            "Use MockSummaryProvider or attach a real OpenAI client later."
        )


def build_default_backend() -> SummaryBackend:
    """Create a backend with the standard mock-first scaffold."""

    config = SummaryBackendConfig(
        providers=[MockSummaryProvider()],
        use_mock_fallback=True,
    )
    return SummaryBackend(config=config)


def _extract_json_object(raw_response: str) -> dict[str, Any] | None:
    text = raw_response.strip()
    if not text:
        return None

    if text.startswith("```"):
        text = _strip_code_fence(text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_decisions(value: Any) -> list[DecisionItem]:
    if not isinstance(value, list):
        return []

    decisions: list[DecisionItem] = []
    for item in value:
        if isinstance(item, dict):
            text = _clean_text(item.get("text"))
            if text:
                confidence = _to_float(item.get("confidence"))
                decisions.append(DecisionItem(text=text, confidence=confidence))
        else:
            text = _clean_text(item)
            if text:
                decisions.append(DecisionItem(text=text))
    return decisions


def _parse_action_items(value: Any) -> list[ActionItem]:
    if not isinstance(value, list):
        return []

    action_items: list[ActionItem] = []
    for item in value:
        if isinstance(item, dict):
            text = _clean_text(item.get("text"))
            if not text:
                continue
            action_items.append(
                ActionItem(
                    text=text,
                    confidence=_to_float(item.get("confidence")),
                    owner=_clean_text(item.get("owner")) or None,
                    due_date=_clean_text(item.get("due_date")) or None,
                )
            )
        else:
            text = _clean_text(item)
            if text:
                action_items.append(ActionItem(text=text))
    return action_items


def _parse_notes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _extract_action_items_from_transcript(text: str) -> list[ActionItem]:
    action_items: list[ActionItem] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(keyword in lower for keyword in ("해야", "할게", "will", "todo", "action")):
            action_items.append(ActionItem(text=stripped))
    return action_items


def _build_mock_summary_text(request: SummaryRequest, transcript_text: str) -> str:
    title = request.meeting_title.strip() if request.meeting_title else "회의"
    lines = [line.strip() for line in transcript_text.splitlines() if line.strip()]
    if not lines:
        return f"{title}에 대한 요약을 생성할 수 없습니다."

    preview = lines[:5]
    return f"{title} 요약 초안: " + " / ".join(preview)


def _mock_decisions(transcript_text: str) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for line in transcript_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(keyword in lower for keyword in ("결정", "확정", "approved", "decided")):
            decisions.append({"text": stripped, "confidence": 0.5})
    if not decisions and transcript_text.strip():
        decisions.append({"text": "기본 결정사항 초안은 mock provider가 생성했습니다.", "confidence": 0.2})
    return decisions


def _mock_action_items(transcript_text: str) -> list[dict[str, Any]]:
    action_items: list[dict[str, Any]] = []
    for line in transcript_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(keyword in lower for keyword in ("해야", "할게", "will", "todo", "action")):
            action_items.append({"text": stripped, "confidence": 0.5, "owner": None, "due_date": None})
    if not action_items and transcript_text.strip():
        action_items.append(
            {
                "text": "전사 내용을 바탕으로 후속 액션 아이템을 확인하세요.",
                "confidence": 0.2,
                "owner": None,
                "due_date": None,
            }
        )
    return action_items
