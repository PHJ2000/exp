from __future__ import annotations

import queue
import threading

import tkinter as tk

from codex_dictation_audio import AlwaysListen, Recorder, default_input_device_name, get_input_devices
from codex_dictation_app_actions import AppActionsMixin
from codex_dictation_app_runtime import AppRuntimeMixin
from codex_dictation_app_ui import AppUIMixin
from codex_dictation_output_state import OutputState
from codex_dictation_postedit import AICorrectionPrefetchState, OllamaPostEditor
from codex_dictation_settings import APP_NAME, audio_preset_label, language_label, llm_profile_label, load_settings, save_settings
from codex_dictation_targeting import WinInfo
from codex_dictation_transcription import WhisperBackend


class App(AppRuntimeMixin, AppActionsMixin, AppUIMixin):
    def __init__(self, root: tk.Tk, launch_target: WinInfo | None = None, show_window: bool = False):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("980x780")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.launch_target = launch_target
        self.show_window = show_window
        self.s = load_settings()
        if not self.s.input_device:
            self.s.input_device = default_input_device_name()
        save_settings(self.s)
        self.log_q = queue.Queue()
        self.res_q = queue.Queue()
        self.jobs = queue.Queue()
        self.backend = WhisperBackend()
        self.audio_status = tk.StringVar(value="Audio | waiting for input")
        self.llm_status = tk.StringVar(value="LLM | 대기")
        self.posteditor = OllamaPostEditor(self.log, self._set_llm_status)
        self.rec = Recorder(self.s, self.log)
        self.listen = AlwaysListen(self.s, self.log, self.enqueue_audio, self.target_active)
        self.transcribing = False
        self.active_transcription_source = ""
        self.last = ""
        self.output_state = OutputState()
        self.last_target = None
        self.last_target_context = None
        self.startup_minimized = False
        self.internal_buffer = ""
        self.buffer_slots = {i: "" for i in range(1, 11)}
        self.ai_correction_seq = 0
        self.ai_prefetch_lock = threading.Lock()
        self.ai_prefetch = AICorrectionPrefetchState()
        self.transcription_worker = threading.Thread(target=self._transcription_loop, daemon=True)
        self.transcription_worker.start()
        self.vars = {key: tk.StringVar(value=str(getattr(self.s, key))) for key in [
            "input_device",
            "sample_rate",
            "input_gain",
            "noise_gate_threshold",
            "whisper_model",
            "whisper_device",
            "whisper_compute_type",
            "initial_prompt",
            "record_hotkey",
            "always_listen_hotkey",
            "paste_last_hotkey",
            "toggle_output_hotkey",
            "toggle_enter_hotkey",
            "output_mode",
            "paste_hotkey",
            "max_record_seconds",
            "auto_stop_silence_seconds",
            "always_listen_preroll_seconds",
            "llm_model",
            "llm_base_url",
            "llm_timeout_seconds",
        ]}
        self.vars["audio_preset"] = tk.StringVar(value=audio_preset_label(self.s.audio_preset))
        self.vars["language"] = tk.StringVar(value=language_label(self.s.language))
        self.vars["llm_profile"] = tk.StringVar(value=llm_profile_label(self.s.llm_profile))
        self.bools = {key: tk.BooleanVar(value=getattr(self.s, key)) for key in [
            "auto_enter",
            "trim_silence",
            "normalize_whitespace",
            "beep_feedback",
            "keep_window_on_top",
            "enable_auto_stop",
            "always_listen_enabled",
            "llm_correction_enabled",
        ]}
        self.status = tk.StringVar(value="Idle")
        self.target = tk.StringVar(value="")
        self.devices = [device["name"] for device in get_input_devices()]
        self._ui()
        self.refresh_target()
        self.refresh_status("Starting")
        self._sync_llm_status_idle()
        self.root.after(20, self.ensure_window_visible_on_startup)
        self.root.after(50, self.bootstrap_after_launch)
        self.root.after(80, self.poll)
        self.root.after(120, self.poll_record)
        self.root.after(120, self.poll_diagnostics)
        self.root.after(150, self.poll_target)
