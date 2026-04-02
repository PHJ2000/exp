from __future__ import annotations

import difflib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from codex_dictation_settings import Settings, normalize_language_value, resolve_llm_model
from codex_dictation_utils import normalize_text


@dataclass
class AICorrectionPrefetchEntry:
    source_text: str = ""
    corrected_text: str = ""
    signature: tuple[str, str, str, bool] = ("", "", "", False)
    outcome: str = "corrected"


@dataclass
class AICorrectionPrefetchState:
    entries: list[AICorrectionPrefetchEntry] = field(default_factory=list)
    active_source_text: str = ""
    in_flight: bool = False
    job_id: int = 0


def conservative_postedit_prompt(text: str, language: str, strict: bool = False) -> str:
    lang_note = {
        "auto": "입력 언어는 한국어 또는 영어일 수 있습니다.",
        "ko": "입력 언어는 한국어입니다.",
        "en": "입력 언어는 영어입니다.",
    }.get(normalize_language_value(language), "입력 언어는 한국어 또는 영어일 수 있습니다.")
    strict_note = (
        "- 원문의 단어 순서와 문장 수를 최대한 유지합니다.\n"
        "- 새 단어를 덧붙이거나 설명을 쓰지 않습니다.\n"
        "- 확신이 없으면 한 글자도 바꾸지 않습니다.\n"
    ) if strict else ""
    return (
        "당신은 STT 후처리 교정기입니다.\n"
        f"{lang_note}\n"
        "아래 원문을 보수적으로만 교정하세요.\n"
        "규칙:\n"
        "- 띄어쓰기, 조사, 문장 부호, 명백한 오인식만 고칩니다.\n"
        "- 뜻을 추정해서 새 내용을 추가하지 않습니다.\n"
        "- 문장 수를 늘리지 않습니다.\n"
        "- 요약하거나 재서술하지 않습니다.\n"
        "- 확신이 없으면 원문을 유지합니다.\n"
        f"{strict_note}"
        "- 설명 없이 교정 결과만 한 줄로 출력합니다.\n\n"
        f"원문:\n{text}\n"
    )


def _clean_postedit_output(text: str) -> str:
    cleaned = (text or "").strip()
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[-1].strip()
    if cleaned.lower().startswith("<think>"):
        cleaned = cleaned.rsplit("</think>", 1)[-1].strip() if "</think>" in cleaned else ""
    cleaned = cleaned.replace("```", "").strip()
    for prefix in ("교정 결과:", "결과:", "수정:", "output:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned.split(":", 1)[1].strip()
    cleaned = cleaned.splitlines()[0].strip() if cleaned.splitlines() else cleaned
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _postedit_compare_key(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def should_accept_postedit(original: str, corrected: str) -> bool:
    original_norm = normalize_text(original or "")
    corrected_norm = normalize_text(corrected or "")
    if not original_norm or not corrected_norm:
        return False
    if original_norm == corrected_norm:
        return True
    if "\n" in corrected_norm:
        return False
    original_key = _postedit_compare_key(original_norm)
    corrected_key = _postedit_compare_key(corrected_norm)
    ratio = difflib.SequenceMatcher(a=original_norm, b=corrected_norm).ratio()
    key_ratio = difflib.SequenceMatcher(a=original_key, b=corrected_key).ratio() if original_key and corrected_key else ratio
    if original_key and corrected_key and original_key == corrected_key:
        return True
    if ratio >= 0.85 and key_ratio >= 0.90:
        return True
    original_sentences = sum(original_norm.count(ch) for ch in ".!?")
    corrected_sentences = sum(corrected_norm.count(ch) for ch in ".!?")
    if corrected_sentences > original_sentences + 1:
        return False
    if ratio < 0.75 and key_ratio < 0.82:
        return False
    if len(corrected_norm) > max(len(original_norm) * 2, len(original_norm) + 24):
        return False
    if len(corrected_norm) < max(1, int(len(original_norm) * 0.4)):
        return False
    if key_ratio < 0.68:
        return False
    return True


def postedit_similarity_metrics(original: str, corrected: str) -> tuple[float, float]:
    original_norm = normalize_text(original or "")
    corrected_norm = normalize_text(corrected or "")
    ratio = difflib.SequenceMatcher(a=original_norm, b=corrected_norm).ratio()
    original_key = _postedit_compare_key(original_norm)
    corrected_key = _postedit_compare_key(corrected_norm)
    key_ratio = difflib.SequenceMatcher(a=original_key, b=corrected_key).ratio() if original_key and corrected_key else ratio
    return ratio, key_ratio


class OllamaPostEditor:
    def __init__(self, logger, status_reporter=None):
        self.log = logger
        self.report_status = status_reporter or (lambda kind, detail="": None)

    def _request(self, prompt: str, settings: Settings, trace_id: str | None = None) -> str:
        trace_prefix = f"{trace_id} | " if trace_id else ""
        base_url = (settings.llm_base_url or "").strip().rstrip("/")
        if not base_url:
            self.report_status("skipped", "base URL 비어 있음")
            self.log(f"{trace_prefix}LLM 교정 건너뜀: base URL 비어 있음")
            return ""
        payload = {
            "model": resolve_llm_model(settings),
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "top_p": 0.05, "num_predict": 128, "repeat_penalty": 1.2},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = max(float(settings.llm_timeout_seconds or 0), 0.5)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            self.report_status("connection_error", str(e))
            self.log(f"{trace_prefix}LLM 교정 건너뜀: {e}")
            return ""
        except Exception as e:
            self.report_status("request_error", str(e))
            self.log(f"{trace_prefix}LLM 교정 실패: {e}")
            return ""
        return _clean_postedit_output(data.get("response", ""))

    def correct(self, text: str, settings: Settings, trace_id: str | None = None) -> str:
        if not settings.llm_correction_enabled:
            self.report_status("disabled", "")
            return text
        source = (text or "").strip()
        if not source:
            return text
        started = time.perf_counter()
        trace_prefix = f"{trace_id} | " if trace_id else ""
        self.report_status("request_start", "")
        self.log(f"{trace_prefix}LLM 요청 시작")
        corrected = self._request(conservative_postedit_prompt(source, settings.language), settings, trace_id=trace_id)
        if not corrected:
            self.report_status("empty", "")
            self.log(f"{trace_prefix}LLM 응답 완료 ({time.perf_counter() - started:.3f}s, empty)")
            self.log(f"{trace_prefix}LLM 빈 응답 -> 원문 유지")
            return text
        if not should_accept_postedit(source, corrected):
            self.log(f"{trace_prefix}1차 결과 거부 -> 보수 프롬프트 재시도")
            retry = self._request(conservative_postedit_prompt(source, settings.language, strict=True), settings, trace_id=trace_id)
            if retry and should_accept_postedit(source, retry):
                corrected = retry
                self.log(f"{trace_prefix}재시도 결과 채택")
            else:
                ratio, key_ratio = postedit_similarity_metrics(source, retry or corrected or source)
                self.report_status("rejected", f"ratio={ratio:.3f}, key_ratio={key_ratio:.3f}")
                self.log(f"{trace_prefix}LLM 응답 완료 ({time.perf_counter() - started:.3f}s, rejected)")
                self.log(f"{trace_prefix}결과 거부: diff too large (ratio={ratio:.3f}, key_ratio={key_ratio:.3f}) -> 원문 유지")
                return text
        if normalize_text(corrected) == normalize_text(source):
            self.report_status("same", "")
            self.log(f"{trace_prefix}LLM 응답 완료 ({time.perf_counter() - started:.3f}s, same)")
            self.log(f"{trace_prefix}결과 동일 -> 원문 유지")
            return text
        self.report_status("accepted", "")
        self.log(f"{trace_prefix}LLM 응답 완료 ({time.perf_counter() - started:.3f}s)")
        self.log(f"{trace_prefix}LLM 결과 채택")
        return corrected
