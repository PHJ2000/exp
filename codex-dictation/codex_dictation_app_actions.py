from __future__ import annotations

import time

from codex_dictation_app_commands import AppCommandActionsMixin
from codex_dictation_app_output import AppOutputMixin
from codex_dictation_app_status import AppStatusMixin
from codex_dictation_settings import (
    DEFAULT_AUDIO_PRESET,
    apply_audio_profile,
    audio_preset_label,
    normalize_audio_profile_name,
    save_settings,
    snapshot_audio_profile,
)
from codex_dictation_targeting import APP_PID, fg_info, focus_window
from codex_dictation_utils import filter_history_entries, format_history_entry, read_history_entries


class AppActionsMixin(AppCommandActionsMixin, AppOutputMixin, AppStatusMixin):
    def refresh_audio_profile_choices(self) -> None:
        values = sorted(self.s.audio_profiles.keys())
        if hasattr(self, "audio_profile_combo"):
            self.audio_profile_combo.configure(values=values)
        selected = normalize_audio_profile_name(self.vars["selected_audio_profile"].get())
        if selected and selected not in values:
            self.vars["selected_audio_profile"].set("")
        elif selected:
            self.vars["selected_audio_profile"].set(selected)

    def _sync_audio_controls_from_settings(self) -> None:
        self.vars["input_device"].set(str(self.s.input_device))
        self.vars["input_gain"].set(str(self.s.input_gain))
        self.vars["noise_gate_threshold"].set(str(self.s.noise_gate_threshold))
        self.vars["auto_stop_silence_seconds"].set(str(self.s.auto_stop_silence_seconds))
        self.vars["always_listen_preroll_seconds"].set(str(self.s.always_listen_preroll_seconds))
        self.vars["audio_preset"].set(audio_preset_label(self.s.audio_preset))
        self.bools["always_listen_enabled"].set(bool(self.s.always_listen_enabled))

    def save_audio_profile(self) -> bool:
        self.save_from_ui()
        name = normalize_audio_profile_name(self.audio_profile_name.get())
        if not name:
            self.log("Audio profile: 저장할 이름이 비어 있음")
            return False
        self.s.audio_profiles[name] = snapshot_audio_profile(self.s)
        self.s.selected_audio_profile = name
        self.vars["selected_audio_profile"].set(name)
        save_settings(self.s)
        self.refresh_audio_profile_choices()
        self.log(f"Audio profile saved: {name}")
        return True

    def apply_selected_audio_profile(self) -> bool:
        self.save_from_ui()
        name = normalize_audio_profile_name(self.vars["selected_audio_profile"].get())
        profile = self.s.audio_profiles.get(name)
        if not name or not profile:
            self.log("Audio profile: 적용할 프로필이 없음")
            return False
        apply_audio_profile(self.s, profile)
        self.s.selected_audio_profile = name
        self.vars["selected_audio_profile"].set(name)
        self.s.audio_preset = DEFAULT_AUDIO_PRESET
        save_settings(self.s)
        self._sync_audio_controls_from_settings()
        self.rec.s = self.s
        self.listen.s = self.s
        self.sync_listener()
        self.refresh_audio_profile_choices()
        self.refresh_audio_status()
        self.log(f"Audio profile applied: {name}")
        return True

    def delete_selected_audio_profile(self) -> bool:
        name = normalize_audio_profile_name(self.vars["selected_audio_profile"].get())
        if not name or name not in self.s.audio_profiles:
            self.log("Audio profile: 삭제할 프로필이 없음")
            return False
        self.s.audio_profiles.pop(name, None)
        if self.s.selected_audio_profile == name:
            self.s.selected_audio_profile = ""
        self.vars["selected_audio_profile"].set(self.s.selected_audio_profile)
        if self.audio_profile_name.get().strip() == name:
            self.audio_profile_name.set("")
        save_settings(self.s)
        self.refresh_audio_profile_choices()
        self.log(f"Audio profile deleted: {name}")
        return True

    def _selected_history_entry(self) -> dict | None:
        if not hasattr(self, "history_list"):
            return None
        selection = self.history_list.curselection()
        if not selection:
            return None
        index = int(selection[0])
        if index < 0 or index >= len(self.history_items):
            return None
        return self.history_items[index]

    def refresh_history_browser(self, preserve_selection: bool = True) -> None:
        selected_text = ""
        if preserve_selection:
            selected = self._selected_history_entry()
            selected_text = str(selected.get("text", "")) if selected else ""
        entries = read_history_entries(limit=200)
        self.history_items = filter_history_entries(entries, self.history_query.get(), limit=80)
        self.history_list.delete(0, "end")
        for entry in self.history_items:
            self.history_list.insert("end", format_history_entry(entry))
        if not self.history_items:
            self.history_empty.set("기록이 없습니다.")
            return
        self.history_empty.set(f"{len(self.history_items)}개 기록")
        for index, entry in enumerate(self.history_items):
            if selected_text and entry.get("text") == selected_text:
                self.history_list.selection_set(index)
                self.history_list.see(index)
                return
        self.history_list.selection_set(0)
        self.history_list.see(0)

    def on_history_query_changed(self, *_args) -> None:
        self.refresh_history_browser(preserve_selection=False)

    def load_selected_history(self) -> bool:
        entry = self._selected_history_entry()
        if not entry:
            self.log("History browser: no entry selected")
            return False
        self._update_latest_transcript(str(entry.get("text", "")))
        self.log("History browser: selected entry loaded")
        return True

    def copy_selected_history(self) -> bool:
        entry = self._selected_history_entry()
        if not entry:
            self.log("History browser: no entry selected")
            return False
        self.copy_clip(str(entry.get("text", "")))
        self.log("History browser: selected entry copied")
        return True

    def _focus_history_output_target(self) -> bool:
        current = fg_info()
        if current and current.pid != APP_PID:
            return True
        target = getattr(self, "last_target_window", None) or getattr(self, "launch_target", None)
        if not target or target.pid == APP_PID:
            self.log("History browser: no previous target window to restore")
            return False
        if not focus_window(target.hwnd):
            self.log("History browser: failed to focus previous target window")
            return False
        time.sleep(0.08)
        return True

    def paste_selected_history(self) -> bool:
        entry = self._selected_history_entry()
        if not entry:
            self.log("History browser: no entry selected")
            return False
        text = str(entry.get("text", ""))
        self._update_latest_transcript(text)
        if not self._focus_history_output_target():
            return False
        if not self.emit_text(text):
            self.log("History browser: failed to paste selected entry")
            return False
        self.log("History browser: selected entry pasted")
        return True
