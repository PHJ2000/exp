from __future__ import annotations

import time

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
from codex_dictation_settings import language_label, normalize_language_value, save_settings
from codex_dictation_targeting import (
    APP_PID,
    EXCLUDED_TARGET_CLASSES,
    EXCLUDED_TARGET_PROCS,
    control_window_state,
    fg_info,
    has_precise_text_focus,
    is_terminal,
    send_media_virtual_key,
)
from codex_dictation_utils import command_key, normalize_text, short_log_text


class AppCommandActionsMixin:
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
            if raw in {f"{token}번 붙여넣기", f"{token}번 붙여 넣기", f"붙여넣기 {token}번", f"붙여 넣기 {token}번"} or compact in {f"{token}번붙여넣기", f"붙여넣기{token}번"}:
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

    def _get_ai_correction_target(self) -> CorrectionTarget | None:
        info = fg_info()
        if info and has_precise_text_focus(info) and not is_terminal(info):
            selected = self._capture_selection_text(self._copy_hotkeys())
            if selected and selected.strip():
                return CorrectionTarget("selection", selected.strip())
        current_context = self._current_target_context(info)
        if self.last_emitted_context and current_context == self.last_emitted_context:
            source = self.last_emitted.strip()
            if source:
                return CorrectionTarget("last", source)
        self._clear_stale_pending_if_needed(info, reason="pending target no longer matches focused input")
        if self.pending_text and not self.last_submitted and (not self.pending_context or self.pending_context == current_context):
            source = self.pending_text.strip()
            if source:
                return CorrectionTarget("pending", source)
        source = self.last_emitted.strip()
        if source and not self.last_emitted_context:
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
