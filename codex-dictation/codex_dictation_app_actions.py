from __future__ import annotations

import threading
import time
from datetime import datetime

import tkinter as tk

from codex_dictation_commands import (
    AI_CORRECTION_COMMANDS,
    CLEAR_ALL_COMMANDS,
    CLEAR_FOCUSED_INPUT_COMMANDS,
    COPY_COMMANDS,
    CUT_COMMANDS,
    ENTER_COMMANDS,
    PASTE_COMMANDS,
    PASTE_UNDO_COMMANDS,
    REPLACE_UNDO_COMMANDS,
    SLOT_NUMBER_WORDS,
    WINDOW_MAXIMIZE_COMMANDS,
    WINDOW_MINIMIZE_COMMANDS,
    WINDOW_RESTORE_COMMANDS,
    CorrectionTarget,
    is_voice_command_text,
    parse_correction_text,
    parse_delete_count_text,
    parse_language_switch_text,
    parse_media_command_text,
)
from codex_dictation_postedit import AICorrectionPrefetchEntry, AICorrectionPrefetchState
from codex_dictation_settings import (
    AI_PREFETCH_CACHE_SIZE,
    AUDIO_PRESET_VALUES,
    audio_preset_label,
    language_label,
    llm_profile_label,
    normalize_audio_preset_value,
    normalize_language_value,
    normalize_llm_profile_value,
    resolve_llm_model,
    save_settings,
)
from codex_dictation_targeting import (
    APP_PID,
    BROWSER_FALLBACK_PROCS,
    EXCLUDED_TARGET_CLASSES,
    EXCLUDED_TARGET_PROCS,
    SYSTEM_INPUT_PROCS,
    WINDOWS_SEARCH_PROCS,
    WinInfo,
    control_window_state,
    fg_info,
    get_clipboard_text,
    has_precise_text_focus,
    is_terminal,
    send_media_virtual_key,
    set_clipboard_text,
)
from codex_dictation_utils import append_app_log, command_key, normalize_text, short_log_text


class AppActionsMixin:
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
        self._set_stringvar_safe(self.llm_status, "LLM | 비활성" if not self.s.llm_correction_enabled else f"LLM | 대기 ({llm_profile_label(self.s.llm_profile)})")

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
            self.ai_prefetch = AICorrectionPrefetchState(entries=list(current.entries), active_source_text=source, in_flight=True, job_id=job_id)
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
            if current_signature != signature or normalize_text(current.active_source_text) != normalize_text(source_text):
                self.ai_prefetch = AICorrectionPrefetchState(entries=list(current.entries), job_id=current.job_id)
                self.log(f"{trace_id} | 정정 후보 무효화")
                return
            if corrected and normalize_text(corrected) != normalize_text(source_text):
                entries = [entry for entry in current.entries if not (entry.signature == signature and normalize_text(entry.source_text) == normalize_text(source_text))]
                entries.append(AICorrectionPrefetchEntry(source_text=source_text, corrected_text=corrected, signature=signature, outcome="corrected"))
                entries = entries[-AI_PREFETCH_CACHE_SIZE:]
                self.ai_prefetch = AICorrectionPrefetchState(entries=entries, job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 저장 완료")
            elif corrected and normalize_text(corrected) == normalize_text(source_text):
                entries = [entry for entry in current.entries if not (entry.signature == signature and normalize_text(entry.source_text) == normalize_text(source_text))]
                entries.append(AICorrectionPrefetchEntry(source_text=source_text, corrected_text=source_text, signature=signature, outcome="same"))
                entries = entries[-AI_PREFETCH_CACHE_SIZE:]
                self.ai_prefetch = AICorrectionPrefetchState(entries=entries, job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 저장 완료 (same)")
            else:
                self.ai_prefetch = AICorrectionPrefetchState(entries=list(current.entries), job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 없음")


    def _keyboard(self):
        import keyboard

        return keyboard

    def _backspace_text(self, text) -> bool:
        if not text:
            return True
        try:
            keyboard = self._keyboard()
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        for _ in text:
            keyboard.press_and_release("backspace")
        return True

    def _clear_focused_input(self) -> bool:
        info = fg_info()
        if not info or not (has_precise_text_focus(info) or is_terminal(info)):
            self.log("Voice command ignored: no focused input target")
            return False
        try:
            keyboard = self._keyboard()
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        keyboard.press_and_release("ctrl+a")
        time.sleep(0.05)
        keyboard.press_and_release("delete")
        time.sleep(0.03)
        keyboard.press_and_release("backspace")
        self.pending_text = ""
        self.pending_segments = []
        self.last_emitted = ""
        self.last_submitted = False
        self._invalidate_ai_prefetch()
        self.log("Voice command executed: clear focused input")
        return True

    def _update_latest_transcript(self, text):
        self.last = text
        self.txt.delete("1.0", tk.END)
        self.txt.insert("1.0", text)
        self.copy_clip(text)

    def _copy_hotkeys(self) -> tuple[str, ...]:
        return ("ctrl+c", "ctrl+insert")

    def _cut_hotkeys(self) -> tuple[str, ...]:
        return ("ctrl+x", "shift+delete")

    def _paste_hotkey(self) -> str:
        return self.s.paste_hotkey or "ctrl+v"

    def _should_safe_paste(self, info: WinInfo | None) -> bool:
        return bool(info and (info.proc in BROWSER_FALLBACK_PROCS or info.proc in WINDOWS_SEARCH_PROCS or info.proc in SYSTEM_INPUT_PROCS))

    def _run_hotkey_sequence(self, *keys: str) -> bool:
        try:
            keyboard = self._keyboard()
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        for key in keys:
            keyboard.press_and_release(key)
            time.sleep(0.05)
        return True

    def _capture_selection_text(self, hotkeys: tuple[str, ...], remove: bool = False) -> str:
        original = get_clipboard_text()
        sentinel = f"__codex_capture__{time.time_ns()}__"
        try:
            for hotkey in hotkeys:
                set_clipboard_text(sentinel)
                time.sleep(0.03)
                if not self._run_hotkey_sequence(hotkey):
                    continue
                for _ in range(16):
                    time.sleep(0.05)
                    captured = get_clipboard_text()
                    if captured and captured != sentinel:
                        return captured
            return ""
        finally:
            set_clipboard_text(original)

    def _store_internal_buffer(self, text: str, slot: int | None = None) -> bool:
        if not text:
            return False
        if slot is None:
            self.internal_buffer = text
            self.log("Voice command executed: copy to internal buffer")
        else:
            self.buffer_slots[slot] = text
            self.log(f"Voice command executed: store slot {slot}")
        return True

    def _remember_output_payload(self, payload: str, sent_enter: bool = False):
        self.last_emitted = payload
        self.last_submitted = bool(sent_enter)
        if sent_enter:
            self.pending_text = ""
            self.pending_segments = []
            self._invalidate_ai_prefetch()
        else:
            self.pending_text = f"{self.pending_text}{payload}"
            self.pending_segments.append(payload)
            self._schedule_ai_prefetch_for_pending()

    def _paste_text_via_clipboard(self, text: str) -> bool:
        if not text:
            return False
        try:
            keyboard = self._keyboard()
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        original = get_clipboard_text()
        try:
            if not set_clipboard_text(text):
                return False
            time.sleep(0.05)
            keyboard.press_and_release(self._paste_hotkey())
            return True
        finally:
            time.sleep(0.03)
            set_clipboard_text(original)

    def _paste_payload(self, text: str) -> bool:
        if not text:
            return False
        self._update_latest_transcript(text)
        if not self._paste_text_via_clipboard(text):
            return False
        self._remember_output_payload(text, sent_enter=False)
        self.last_paste_payload = text
        return True

    def _replace_pending_with_prepared_clipboard(self, text: str, trace_id: str | None = None) -> bool:
        if not self.pending_text:
            self.log("Voice command ignored: no current text to replace")
            return False
        if self.last_submitted:
            self.log("Voice command ignored: last text was already submitted")
            return False
        info = fg_info()
        allow_space = has_precise_text_focus(info)
        payload = f"{text} " if text and allow_space else text
        old_pending = self.pending_text
        old_segments = list(self.pending_segments)
        old_last = self.last_emitted
        try:
            keyboard = self._keyboard()
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        use_typed_output = self.s.output_mode == "type" and not self._should_safe_paste(info)
        original_clipboard = get_clipboard_text() if not use_typed_output else ""
        trace_prefix = f"{trace_id} | " if trace_id else ""
        self.log(f"{trace_prefix}교체 준비: target=pending, mode={'type' if use_typed_output else 'paste'}, old_len={len(old_pending)}, new_len={len(payload)}")
        if not use_typed_output and not set_clipboard_text(payload):
            self.log("Voice command failed: failed to prepare correction clipboard")
            return False
        try:
            try:
                keyboard.press_and_release("end")
                time.sleep(0.01)
            except Exception as exc:
                self.log(f"Voice command failed: failed to prepare current input replacement ({exc})")
                return False
            delete_started = time.perf_counter()
            self.log(f"{trace_prefix}교체 시작")
            if not self._backspace_text(old_pending):
                return False
            self.log(f"{trace_prefix}원문 제거 완료 ({time.perf_counter() - delete_started:.3f}s)")
            self.pending_text = ""
            self.pending_segments = []
            self.last_emitted = ""
            self._update_latest_transcript(text)
            reinject_started = time.perf_counter()
            try:
                if use_typed_output:
                    keyboard.write(payload, delay=0)
                else:
                    keyboard.press_and_release(self._paste_hotkey())
            except Exception as exc:
                return self._rollback_replace(old_pending, old_pending, old_segments, old_last, f"failed to emit corrected input ({exc})", trace_id=trace_id)
            time.sleep(0.03)
            self._remember_output_payload(payload, sent_enter=False)
            self.log(f"{trace_prefix}교정문 삽입 완료 ({time.perf_counter() - reinject_started:.3f}s)")
            self.log(f"{trace_prefix}빈 구간 추정 {time.perf_counter() - delete_started:.3f}s")
            self._remember_replace_state("pending", old_pending, payload, old_last, old_pending, old_segments)
            self.log(f"{trace_prefix}교체 완료")
            return True
        finally:
            if not use_typed_output:
                time.sleep(0.02)
                set_clipboard_text(original_clipboard)

    def _remember_replace_state(self, kind: str, old_text: str, new_payload: str, old_segment: str = "", old_pending: str = "", old_segments: list[str] | None = None):
        self.last_replace_state = {
            "kind": kind,
            "old_text": old_text,
            "new_payload": new_payload,
            "old_segment": old_segment,
            "old_pending": old_pending,
            "old_segments": list(old_segments or []),
        }

    def _iter_slot_tokens(self, text: str):
        raw = text.strip().lower()
        compact = self._command_key(text)
        for token, slot in SLOT_NUMBER_WORDS.items():
            yield token, slot, raw, compact

    def _parse_slot_command(self, text: str) -> tuple[str, int] | None:
        for token, slot, raw, compact in self._iter_slot_tokens(text):
            if raw in {f"{token}번 복사", f"복사 {token}번"} or compact in {f"{token}번복사", f"복사{token}번"}:
                return ("copy", slot)
            if raw in {f"{token}번 잘라", f"{token}번 잘라내기", f"잘라 {token}번"} or compact in {f"{token}번잘라", f"{token}번잘라내기", f"잘라{token}번"}:
                return ("cut", slot)
            if raw in {f"{token}번 붙여넣기", f"{token}번 붙여 넣기", f"붙여넣기 {token}번", f"붙여 넣기 {token}번"} or compact in {f"{token}번붙여넣기", f"{token}번붙여넣기", f"붙여넣기{token}번"}:
                return ("paste", slot)
        return None

    def copy_selection_to_buffer(self) -> bool:
        copied = self._capture_selection_text(self._copy_hotkeys())
        if not copied:
            self.log("Voice command ignored: no selected text copied")
            return False
        return self._store_internal_buffer(copied)

    def copy_selection_to_slot(self, slot: int) -> bool:
        copied = self._capture_selection_text(self._copy_hotkeys())
        if not copied:
            self.log("Voice command ignored: no selected text copied")
            return False
        return self._store_internal_buffer(copied, slot)

    def cut_selection_to_buffer(self) -> bool:
        cut_text = self._capture_selection_text(self._cut_hotkeys(), remove=True)
        if not cut_text:
            self.log("Voice command ignored: no selected text cut")
            return False
        return self._store_internal_buffer(cut_text)

    def cut_selection_to_slot(self, slot: int) -> bool:
        cut_text = self._capture_selection_text(self._cut_hotkeys(), remove=True)
        if not cut_text:
            self.log("Voice command ignored: no selected text cut")
            return False
        return self._store_internal_buffer(cut_text, slot)

    def paste_internal_buffer(self) -> bool:
        if not self.internal_buffer:
            self.log("Voice command ignored: internal buffer is empty")
            return False
        ok = self._paste_payload(self.internal_buffer)
        if ok:
            self.log("Voice command executed: paste internal buffer")
        return ok

    def paste_slot_buffer(self, slot: int) -> bool:
        value = self.buffer_slots.get(slot, "")
        if not value:
            self.log(f"Voice command ignored: slot {slot} is empty")
            return False
        ok = self._paste_payload(value)
        if ok:
            self.log(f"Voice command executed: paste slot {slot}")
        return ok

    def undo_last_paste(self) -> bool:
        if not self.last_paste_payload:
            self.log("Voice command ignored: no pasted text to undo")
            return False
        payload = self.last_paste_payload
        if not self._run_hotkey_sequence("ctrl+z"):
            return False
        self.last_paste_payload = ""
        if self.pending_segments and self.pending_segments[-1] == payload:
            self.pending_segments = self.pending_segments[:-1]
            if self.pending_text.endswith(payload):
                self.pending_text = self.pending_text[: -len(payload)]
            self.last_emitted = self.pending_segments[-1] if self.pending_segments else ""
        self._invalidate_ai_prefetch()
        self.log("Voice command executed: undo last paste")
        return True

    def undo_last_replace(self) -> bool:
        state = self.last_replace_state
        if not state:
            self.log("Voice command ignored: no replacement to undo")
            return False
        new_payload = state.get("new_payload", "")
        if new_payload and not self._backspace_text(new_payload):
            return False
        old_text = state.get("old_text", "")
        old_segments = state.get("old_segments", [])
        old_pending = state.get("old_pending", "")
        old_segment = state.get("old_segment", "")
        self.emit_text(old_text, remember=False, press_enter=False, append_space=False, force_paste=True)
        if state.get("kind") in {"last", "pending"}:
            self.pending_segments = old_segments
            self.pending_text = old_pending
            self.last_emitted = old_segment
            self._schedule_ai_prefetch_for_pending()
        self.last_replace_state = None
        self.log("Voice command executed: undo last replace")
        return True

    def _rollback_replace(self, restore_text: str, old_pending: str, old_segments: list[str], old_last: str, reason: str, trace_id: str | None = None) -> bool:
        restored = False
        trace_prefix = f"{trace_id} | " if trace_id else ""
        if restore_text:
            restored = bool(self.emit_text(restore_text, remember=False, press_enter=False, append_space=False, force_paste=True))
        self.pending_text = old_pending
        self.pending_segments = list(old_segments)
        self.last_emitted = old_last
        self.last_replace_state = None
        if old_pending and not self.last_submitted:
            self._schedule_ai_prefetch_for_pending()
        else:
            self._invalidate_ai_prefetch()
        if restore_text:
            self._update_latest_transcript(restore_text)
            self.log(f"{trace_prefix}롤백 시도 완료: restored={restored}")
        self.log(f"{trace_prefix}Voice command failed: {reason}")
        return restored

    def emit_text(self, text, remember=True, press_enter: bool | None = None, append_space=True, force_paste: bool = False):
        try:
            import keyboard
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        sent_enter = self.s.auto_enter if press_enter is None else press_enter
        info = fg_info()
        allow_space = append_space and has_precise_text_focus(info)
        payload = f"{text} " if text and allow_space and not sent_enter else text
        if self.s.output_mode == "clipboard":
            self.log("Copied transcript to clipboard")
            return True
        if self.s.output_mode == "type" and not force_paste and not self._should_safe_paste(info):
            try:
                keyboard.write(payload, delay=0)
            except Exception as exc:
                self.log(f"Output typing failed: {exc}")
                return False
        else:
            original = get_clipboard_text()
            try:
                if not set_clipboard_text(payload):
                    self.log("Output paste failed: clipboard set failed")
                    return False
                time.sleep(0.05)
                keyboard.press_and_release(self._paste_hotkey())
            except Exception as exc:
                self.log(f"Output paste failed: {exc}")
                return False
            finally:
                time.sleep(0.03)
                set_clipboard_text(original)
        if sent_enter:
            try:
                time.sleep(0.03)
                keyboard.press_and_release("enter")
            except Exception as exc:
                self.log(f"Output enter failed: {exc}")
                return False
        if remember:
            self._remember_output_payload(payload, sent_enter=sent_enter)
        self.log(f"Transcript sent via {self.s.output_mode}")
        return True

    def send_enter(self) -> bool:
        try:
            keyboard = self._keyboard()
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        keyboard.press_and_release("enter")
        self.last_submitted = True
        self.pending_text = ""
        self.pending_segments = []
        self.log("Voice command executed: submit")
        return True

    def undo_last_emitted(self, count: int = 1) -> bool:
        if count <= 0:
            return False
        if not self.pending_segments:
            self.log("Voice command ignored: no recent text to erase")
            return False
        if self.last_submitted:
            self.log("Voice command ignored: last text was already submitted")
            return False
        if count > len(self.pending_segments):
            count = len(self.pending_segments)
        removed = "".join(self.pending_segments[-count:])
        if not self._backspace_text(removed):
            return False
        self.pending_segments = self.pending_segments[:-count]
        if self.pending_text.endswith(removed):
            self.pending_text = self.pending_text[: -len(removed)]
        self.last_emitted = self.pending_segments[-1] if self.pending_segments else ""
        if self.pending_text and not self.last_submitted:
            self._schedule_ai_prefetch_for_pending()
        else:
            self._invalidate_ai_prefetch()
        self.log(f"Voice command executed: erase last {count} segment(s)")
        return True

    def clear_pending_input(self) -> bool:
        if not self.pending_text:
            self.log("Voice command ignored: no current text to clear")
            return False
        if self.last_submitted:
            self.log("Voice command ignored: last text was already submitted")
            return False
        try:
            keyboard = self._keyboard()
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        keyboard.press_and_release("end")
        if not self._backspace_text(self.pending_text):
            return False
        self.log("Voice command executed: clear current input")
        self.pending_text = ""
        self.pending_segments = []
        self.last_emitted = ""
        self._invalidate_ai_prefetch()
        return True

    def replace_last_emitted(self, text: str, trace_id: str | None = None) -> bool:
        if not self.pending_segments:
            self.log("Voice command ignored: no recent text to replace")
            return False
        if self.last_submitted:
            self.log("Voice command ignored: last text was already submitted")
            return False
        last_segment = self.pending_segments[-1]
        old_pending = self.pending_text
        old_segments = list(self.pending_segments)
        old_last = self.last_emitted
        trace_prefix = f"{trace_id} | " if trace_id else ""
        self.log(f"{trace_prefix}교체 준비: target=last, old_len={len(last_segment)}, new_len={len(text)}")
        if not self._backspace_text(last_segment):
            return False
        self.pending_segments = self.pending_segments[:-1]
        if self.pending_text.endswith(last_segment):
            self.pending_text = self.pending_text[: -len(last_segment)]
        self._update_latest_transcript(text)
        if not self.emit_text(text, remember=True, press_enter=False, append_space=True, force_paste=True):
            return self._rollback_replace(last_segment, old_pending, old_segments, old_last, "failed to replace last emitted text", trace_id=trace_id)
        self._remember_replace_state("last", last_segment, self.last_emitted, last_segment, old_pending, old_segments)
        self.log(f"{trace_prefix}교체 완료")
        return True

    def replace_pending_text(self, text: str, trace_id: str | None = None) -> bool:
        return self._replace_pending_with_prepared_clipboard(text, trace_id=trace_id)

    def replace_selection_or_last(self, text: str) -> bool:
        selected = self._capture_selection_text(self._copy_hotkeys())
        if selected:
            self._update_latest_transcript(text)
            if not self.emit_text(text, remember=False, press_enter=False, append_space=False, force_paste=True):
                self._update_latest_transcript(selected)
                self.log("Voice command failed: failed to replace current selection")
                return False
            self._remember_replace_state("selection", selected, text)
            self.log("Voice command executed: replace current selection")
            return True
        return self.replace_last_emitted(text)

    def replace_selected_text(self, selected_text: str, text: str, trace_id: str | None = None) -> bool:
        selected = self._capture_selection_text(self._copy_hotkeys())
        if not selected:
            self.log("Voice command ignored: no selected text to replace")
            return False
        trace_prefix = f"{trace_id} | " if trace_id else ""
        self.log(f"{trace_prefix}교체 준비: target=selection, old_len={len(selected)}, new_len={len(text)}")
        self._update_latest_transcript(text)
        if not self.emit_text(text, remember=False, press_enter=False, append_space=False, force_paste=True):
            self._update_latest_transcript(selected_text or selected)
            self.log("Voice command failed: failed to replace current selection")
            return False
        self._remember_replace_state("selection", selected, text)
        self.log(f"{trace_prefix}교체 완료")
        return True

    def _get_ai_correction_target(self) -> CorrectionTarget | None:
        info = fg_info()
        if self.pending_text and not self.last_submitted:
            source = self.pending_text.strip()
            if source:
                return CorrectionTarget("pending", source)
        if info and has_precise_text_focus(info) and not is_terminal(info):
            selected = self._capture_selection_text(self._copy_hotkeys())
            if selected and selected.strip():
                return CorrectionTarget("selection", selected.strip())
        source = self.last_emitted.strip()
        if source:
            return CorrectionTarget("last", source)
        return None

    def _apply_ai_correction_target(self, target: CorrectionTarget, corrected: str, trace_id: str | None = None) -> bool:
        if target.kind == "selection":
            return self.replace_selected_text(target.source_text, corrected, trace_id=trace_id)
        if target.kind == "pending":
            return self.replace_pending_text(corrected, trace_id=trace_id)
        return self.replace_last_emitted(corrected, trace_id=trace_id)

    def ai_correct_selection_or_last(self) -> bool:
        if not self.s.llm_correction_enabled:
            self.log("Voice command ignored: local LLM correction is disabled")
            return False
        trace_id = self.next_ai_correction_trace()
        self.log(f"{trace_id} | 정정 명령 수신")
        target = self._get_ai_correction_target()
        if not target or not target.source_text:
            self.log(f"{trace_id} | 교정 대상 없음")
            return False
        source = target.source_text
        self.log(f"{trace_id} | 대상 확정: kind={target.kind}, text={short_log_text(source)}")
        self.log(f"{trace_id} | LLM 요청 시작 전 원문 유지")
        corrected = ""
        prefetched_outcome = ""
        if target.kind == "pending":
            prefetched_outcome, corrected = self._consume_ai_prefetch(source)
            corrected = corrected.strip()
            if corrected:
                if prefetched_outcome == "same":
                    self.log(f"{trace_id} | 백그라운드 정정 후보 재사용 (same)")
                else:
                    self.log(f"{trace_id} | 백그라운드 정정 후보 재사용")
            else:
                with self.ai_prefetch_lock:
                    should_wait = self.ai_prefetch.in_flight and normalize_text(self.ai_prefetch.active_source_text) == normalize_text(source)
                if should_wait:
                    self.log(f"{trace_id} | 백그라운드 정정 후보 대기")
                    prefetched_outcome, corrected = self._await_ai_prefetch(source, timeout_seconds=self.s.llm_timeout_seconds + 1.0)
                    corrected = corrected.strip()
                    if corrected:
                        if prefetched_outcome == "same":
                            self.log(f"{trace_id} | 백그라운드 정정 후보 완료 후 재사용 (same)")
                        else:
                            self.log(f"{trace_id} | 백그라운드 정정 후보 완료 후 재사용")
        if prefetched_outcome == "same":
            self._update_latest_transcript(source)
            self._set_llm_status("same", "")
            self.log(f"{trace_id} | 결과 동일 -> 원문 유지")
            return True
        if not corrected:
            corrected = self.posteditor.correct(source, self.s, trace_id=trace_id).strip()
        if not corrected:
            self.log(f"{trace_id} | LLM 결과 비어 있음 -> 원문 유지")
            return False
        self.log(f"{trace_id} | LLM 결과 수신: {short_log_text(corrected)}")
        if normalize_text(corrected) == normalize_text(source):
            self._update_latest_transcript(source)
            self._set_llm_status("same", "")
            self.log(f"{trace_id} | 결과 동일 -> 원문 유지")
            return True
        self.log(f"{trace_id} | 결과 검증 통과 -> 교체 진행")
        ok = self._apply_ai_correction_target(target, corrected, trace_id=trace_id)
        if ok:
            self._set_llm_status("applied", "")
            self.log(f"{trace_id} | 정정 완료")
        else:
            self._set_llm_status("apply_failed", "")
            self.log(f"{trace_id} | 정정 실패 -> 원문 유지/복구 확인 필요")
        return ok

    def _command_key(self, text: str) -> str:
        return command_key(text)

    def parse_language_switch(self, text: str) -> str | None:
        return parse_language_switch_text(text)

    def parse_correction(self, text: str) -> str:
        return parse_correction_text(text)

    def set_language_mode(self, language: str) -> bool:
        normalized = normalize_language_value(language)
        if normalized == self.s.language:
            self.log(f"Voice command ignored: language already set to {language_label(self.s.language)}")
            return True
        self.s.language = normalized
        self.vars["language"].set(language_label(self.s.language))
        save_settings(self.s)
        self.refresh_status()
        self.log(f"Voice command executed: language -> {language_label(self.s.language)}")
        return True

    def control_focused_window(self, action: str) -> bool:
        info = fg_info()
        if not info:
            self.log("Voice command ignored: no active window")
            return False
        ok = control_window_state(info, action)
        if not ok:
            self.log(f"Voice command ignored: unable to {action} current window")
            return False
        label = {"maximize": "maximize", "minimize": "minimize", "restore": "restore"}.get(action, action)
        self.log(f"Voice command executed: window {label}")
        return True

    def parse_media_command(self, text: str) -> tuple[str, int] | None:
        return parse_media_command_text(text)

    def execute_media_control(self, action: str, count: int = 1) -> bool:
        info = fg_info()
        if not info or info.pid == APP_PID or info.proc in EXCLUDED_TARGET_PROCS or info.cls in EXCLUDED_TARGET_CLASSES:
            self.log("Voice command ignored: no controllable foreground window")
            return False
        if action == "play_pause":
            if not send_media_virtual_key(0xB3):
                self.log("Voice command failed: media play_pause")
                return False
            self.log("Voice command executed: play/pause")
            return True
        try:
            keyboard = self._keyboard()
        except Exception as exc:
            self.log(f"Output hotkeys unavailable: {exc}")
            return False
        key_map = {"escape": "esc", "forward": "right", "backward": "left"}
        press_key = key_map.get(action)
        if not press_key:
            return False
        count = max(1, min(int(count or 1), 10))
        try:
            for _ in range(count):
                keyboard.press_and_release(press_key)
                time.sleep(0.03)
        except Exception as exc:
            self.log(f"Voice command failed: media {action} ({exc})")
            return False
        if action == "escape":
            self.log("Voice command executed: esc")
        elif action == "forward":
            self.log(f"Voice command executed: seek forward x{count}")
        else:
            self.log(f"Voice command executed: seek backward x{count}")
        return True

    def parse_delete_count(self, text: str) -> int:
        return parse_delete_count_text(text)

    def is_voice_command_text(self, text: str) -> bool:
        return is_voice_command_text(text)

    def handle_voice_command(self, text: str) -> bool:
        key = self._command_key(text)
        if not key:
            return False
        slot_command = self._parse_slot_command(text)
        if slot_command:
            action, slot = slot_command
            if action == "copy":
                return self.copy_selection_to_slot(slot)
            if action == "cut":
                return self.cut_selection_to_slot(slot)
            if action == "paste":
                return self.paste_slot_buffer(slot)
        if key in ENTER_COMMANDS:
            return self.send_enter()
        if key in COPY_COMMANDS:
            return self.copy_selection_to_buffer()
        if key in CUT_COMMANDS:
            return self.cut_selection_to_buffer()
        if key in PASTE_COMMANDS:
            return self.paste_internal_buffer()
        if key in PASTE_UNDO_COMMANDS:
            return self.undo_last_paste()
        if key in REPLACE_UNDO_COMMANDS:
            return self.undo_last_replace()
        if key in CLEAR_FOCUSED_INPUT_COMMANDS:
            return self._clear_focused_input()
        if key in CLEAR_ALL_COMMANDS:
            return self.clear_pending_input()
        if key in AI_CORRECTION_COMMANDS:
            return self.ai_correct_selection_or_last()
        if key in WINDOW_MAXIMIZE_COMMANDS:
            return self.control_focused_window("maximize")
        if key in WINDOW_MINIMIZE_COMMANDS:
            return self.control_focused_window("minimize")
        if key in WINDOW_RESTORE_COMMANDS:
            return self.control_focused_window("restore")
        language = self.parse_language_switch(text)
        if language:
            return self.set_language_mode(language)
        media_action = self.parse_media_command(text)
        if media_action:
            return self.execute_media_control(*media_action)
        delete_count = self.parse_delete_count(text)
        if delete_count:
            return self.undo_last_emitted(delete_count)
        replacement = self.parse_correction(text)
        if replacement:
            return self.replace_selection_or_last(replacement)
        return False

    def copy_clip(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def paste_last(self):
        if not self.last:
            self.log("No transcript to paste yet")
            return
        self.copy_clip(self.last)
        self.emit_text(self.last)

    def copy_last(self):
        if not self.last:
            self.log("No transcript to copy yet")
            return
        self.copy_clip(self.last)
        self.log("Last transcript copied")

    def cycle_output(self):
        order = ["paste", "clipboard", "type"]
        self.s.output_mode = order[(order.index(self.s.output_mode) + 1) % len(order)] if self.s.output_mode in order else "paste"
        self.vars["output_mode"].set(self.s.output_mode)
        save_settings(self.s)
        self.refresh_status()
        self.log(f"Output mode: {self.s.output_mode}")

    def toggle_enter(self):
        self.s.auto_enter = not self.s.auto_enter
        self.bools["auto_enter"].set(self.s.auto_enter)
        save_settings(self.s)
        self.refresh_status()
        self.log(f"Auto enter: {self.s.auto_enter}")
