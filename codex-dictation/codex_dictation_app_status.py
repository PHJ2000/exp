from __future__ import annotations

import threading
import time
from datetime import datetime

import tkinter as tk

from codex_dictation_postedit import AICorrectionPrefetchEntry, AICorrectionPrefetchState
from codex_dictation_settings import (
    AI_PREFETCH_CACHE_SIZE,
    AUDIO_PRESET_VALUES,
    audio_preset_label,
    llm_profile_label,
    normalize_audio_preset_value,
    normalize_language_value,
    normalize_llm_profile_value,
    resolve_llm_model,
    save_settings,
)
from codex_dictation_utils import append_app_log, normalize_text, short_log_text


class AppStatusMixin:
    def log(self, msg):
        append_app_log(msg)
        self.log_q.put(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _llm_status_text(self, kind: str, detail: str = "") -> str:
        brief = short_log_text(detail, limit=72) if detail else ""
        status_map = {
            "disabled": "LLM | 비활성",
            "request_start": f"LLM | 요청 중 ({llm_profile_label(self.s.llm_profile)})",
            "skipped": f"LLM | 설정 문제: {brief or '요청 건너뜀'}",
            "connection_error": f"LLM | 연결 실패: {brief or '응답 없음'}",
            "request_error": f"LLM | 요청 실패: {brief or '오류'}",
            "empty": "LLM | 빈 응답, 원문 유지",
            "rejected": f"LLM | 수정 폭 과다, 원문 유지 ({brief})" if brief else "LLM | 수정 폭 과다, 원문 유지",
            "same": "LLM | 동일 결과, 원문 유지",
            "accepted": "LLM | 교정안 생성됨",
            "applied": "LLM | 교정 적용 완료",
            "apply_failed": "LLM | 교정 적용 실패",
        }
        return status_map.get(kind, self.llm_status.get())

    def _set_stringvar_safe(self, var: tk.StringVar, value: str):
        def apply():
            try:
                var.set(value)
            except tk.TclError:
                pass

        try:
            self.root.after(0, apply)
        except tk.TclError:
            pass

    def _sync_llm_status_idle(self):
        default = "LLM | 비활성" if not self.s.llm_correction_enabled else f"LLM | 대기 ({llm_profile_label(self.s.llm_profile)})"
        self._set_stringvar_safe(self.llm_status, default)

    def _set_llm_status(self, kind: str, detail: str = ""):
        self._set_stringvar_safe(self.llm_status, self._llm_status_text(kind, detail))

    def apply_audio_preset(self):
        preset = normalize_audio_preset_value(self.vars["audio_preset"].get())
        self.s.audio_preset = preset
        self.vars["audio_preset"].set(audio_preset_label(preset))
        values = AUDIO_PRESET_VALUES.get(preset, {})
        for key, value in values.items():
            setattr(self.s, key, value)
            if key in self.vars:
                self.vars[key].set(str(value))
        save_settings(self.s)
        self.rec.s = self.s
        self.listen.s = self.s
        self.refresh_status()
        self.refresh_audio_status()
        self.log(f"Audio preset applied: {audio_preset_label(preset)}")

    def next_ai_correction_trace(self) -> str:
        self.ai_correction_seq += 1
        return f"AI-CORR-{self.ai_correction_seq:04d}"

    def _invalidate_ai_prefetch(self, clear_ready: bool = True):
        with self.ai_prefetch_lock:
            entries = [] if clear_ready else list(self.ai_prefetch.entries)
            self.ai_prefetch = AICorrectionPrefetchState(entries=entries, job_id=self.ai_prefetch.job_id)

    def _consume_ai_prefetch(self, source_text: str) -> tuple[str, str]:
        source_key = normalize_text(source_text)
        current_signature = self._prefetch_model_signature()
        with self.ai_prefetch_lock:
            for idx in range(len(self.ai_prefetch.entries) - 1, -1, -1):
                entry = self.ai_prefetch.entries[idx]
                if entry.signature != current_signature:
                    continue
                if normalize_text(entry.source_text) != source_key:
                    continue
                corrected = entry.corrected_text
                outcome = entry.outcome
                del self.ai_prefetch.entries[idx]
                return outcome, corrected
        return "", ""

    def _await_ai_prefetch(self, source_text: str, timeout_seconds: float) -> tuple[str, str]:
        source_key = normalize_text(source_text)
        current_signature = self._prefetch_model_signature()
        deadline = time.time() + max(0.0, timeout_seconds)
        while time.time() <= deadline:
            with self.ai_prefetch_lock:
                for idx in range(len(self.ai_prefetch.entries) - 1, -1, -1):
                    entry = self.ai_prefetch.entries[idx]
                    if entry.signature != current_signature:
                        continue
                    if normalize_text(entry.source_text) != source_key:
                        continue
                    corrected = entry.corrected_text
                    outcome = entry.outcome
                    del self.ai_prefetch.entries[idx]
                    return outcome, corrected
                same_in_flight = self.ai_prefetch.in_flight and normalize_text(self.ai_prefetch.active_source_text) == source_key
            if not same_in_flight:
                return "", ""
            time.sleep(0.05)
        return "", ""

    def _prefetch_model_signature(self) -> tuple[str, str, str, bool]:
        return (
            normalize_language_value(self.s.language),
            normalize_llm_profile_value(self.s.llm_profile),
            resolve_llm_model(self.s),
            bool(self.s.llm_correction_enabled),
        )

    def _schedule_ai_prefetch_for_pending(self):
        if not self.s.llm_correction_enabled or self.last_submitted:
            self._invalidate_ai_prefetch()
            return
        source = self.pending_text.strip()
        if not source:
            self._invalidate_ai_prefetch()
            return
        signature = self._prefetch_model_signature()
        with self.ai_prefetch_lock:
            current = self.ai_prefetch
            source_key = normalize_text(source)
            if any(entry.signature == signature and normalize_text(entry.source_text) == source_key for entry in current.entries):
                return
            if normalize_text(current.active_source_text) == source_key and current.in_flight:
                return
            job_id = current.job_id + 1
            self.ai_prefetch = AICorrectionPrefetchState(
                entries=list(current.entries),
                active_source_text=source,
                in_flight=True,
                job_id=job_id,
            )
        thread = threading.Thread(target=self._ai_prefetch_worker, args=(job_id, source, signature), daemon=True)
        thread.start()

    def _ai_prefetch_worker(self, job_id: int, source_text: str, signature: tuple[str, str, str, bool]):
        trace_id = f"AI-PREFETCH-{job_id:04d}"
        self.log(f"{trace_id} | 정정 후보 생성 시작")
        corrected = self.posteditor.correct(source_text, self.s, trace_id=trace_id).strip()
        with self.ai_prefetch_lock:
            current = self.ai_prefetch
            if current.job_id != job_id:
                self.log(f"{trace_id} | 최신 작업이 아니어서 정정 후보 폐기")
                return
            current_signature = self._prefetch_model_signature()
            source_key = normalize_text(source_text)
            if current_signature != signature or normalize_text(current.active_source_text) != source_key:
                self.ai_prefetch = AICorrectionPrefetchState(entries=list(current.entries), job_id=current.job_id)
                self.log(f"{trace_id} | 정정 후보 무효화")
                return
            entries = [entry for entry in current.entries if not (entry.signature == signature and normalize_text(entry.source_text) == source_key)]
            if corrected and normalize_text(corrected) != source_key:
                entries.append(
                    AICorrectionPrefetchEntry(
                        source_text=source_text,
                        corrected_text=corrected,
                        signature=signature,
                        outcome="corrected",
                    )
                )
                entries = entries[-AI_PREFETCH_CACHE_SIZE:]
                self.ai_prefetch = AICorrectionPrefetchState(entries=entries, job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 저장 완료")
            elif corrected and normalize_text(corrected) == source_key:
                entries.append(
                    AICorrectionPrefetchEntry(
                        source_text=source_text,
                        corrected_text=source_text,
                        signature=signature,
                        outcome="same",
                    )
                )
                entries = entries[-AI_PREFETCH_CACHE_SIZE:]
                self.ai_prefetch = AICorrectionPrefetchState(entries=entries, job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 저장 완료 (same)")
            else:
                self.ai_prefetch = AICorrectionPrefetchState(entries=list(current.entries), job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 없음")
