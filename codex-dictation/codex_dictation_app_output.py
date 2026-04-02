from __future__ import annotations

import time

import tkinter as tk

from codex_dictation_targeting import (
    BROWSER_FALLBACK_PROCS,
    SYSTEM_INPUT_PROCS,
    WINDOWS_SEARCH_PROCS,
    WinInfo,
    fg_info,
    get_clipboard_text,
    has_precise_text_focus,
    is_terminal,
    set_clipboard_text,
)


class AppOutputMixin:
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
