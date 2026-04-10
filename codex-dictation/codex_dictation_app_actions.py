from __future__ import annotations

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
