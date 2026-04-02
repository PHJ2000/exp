from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from codex_dictation_settings import APP_NAME, AUDIO_PRESET_UI_LABELS, audio_preset_label


class AppUIMixin:
    def _ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)
        head = ttk.Frame(self.root, padding=12)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text=APP_NAME, font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(head, textvariable=self.status, font=("Segoe UI", 10, "bold")).grid(row=0, column=1, sticky="e")
        ttk.Label(head, textvariable=self.target).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(
            head,
            text="F7 항상 듣기, F8 수동 녹음, F9 마지막 문장, F10 출력 모드, F11 Enter 전환 | 음성 명령: 보내, 지워, 다 지워, 전체 비워, 다시 ..., 복사, 붙여넣기, 잘라, 취소, 되돌려, 자동/한국어/영어, 최대화/최소화/복원, 이스케이프/나가기, 일시정지/재생, 앞으로/뒤로 감기",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(head, textvariable=self.audio_status, font=("Consolas", 9)).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(head, textvariable=self.llm_status, font=("Consolas", 9)).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        top = ttk.Frame(self.root, padding=(12, 0, 12, 0))
        top.grid(row=1, column=0, sticky="nsew")
        top.columnconfigure((0, 1), weight=1)
        left = ttk.LabelFrame(top, text="Recording", padding=12)
        right = ttk.LabelFrame(top, text="Output, Target, Hotkeys", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._combo(left, "Input Device", "input_device", self.devices, 0)
        self._entry(left, "Sample Rate", "sample_rate", 1)
        self._entry(left, "Input Gain", "input_gain", 2)
        self._combo(left, "Audio Preset", "audio_preset", [audio_preset_label(key) for key in AUDIO_PRESET_UI_LABELS], 3)
        self._entry(left, "Noise Gate Threshold", "noise_gate_threshold", 4)
        self._combo(left, "Whisper Model", "whisper_model", ["tiny", "base", "small", "medium", "large-v3-turbo"], 5)
        self._combo(left, "Whisper Device", "whisper_device", ["auto", "cpu", "cuda"], 6)
        self._combo(left, "Compute Type", "whisper_compute_type", ["auto", "int8", "int8_float16", "float16", "float32"], 7)
        self._combo(left, "Language", "language", ["자동", "한국어", "영어"], 8)
        self._entry(left, "Initial Prompt", "initial_prompt", 9)
        self._entry(left, "Max Record Seconds", "max_record_seconds", 10)
        self._entry(left, "Speech End Silence Seconds", "auto_stop_silence_seconds", 11)
        self._entry(left, "Always Listen Pre-roll Seconds", "always_listen_preroll_seconds", 12)
        self._check(left, "Trim leading and trailing silence", "trim_silence", 13)
        self._check(left, "Normalize whitespace", "normalize_whitespace", 14)
        self._check(left, "Enable manual mode auto stop", "enable_auto_stop", 15)
        self._check(left, "Play feedback beeps", "beep_feedback", 16)
        self._check(left, "Keep window on top", "keep_window_on_top", 17)
        ttk.Button(left, text="Apply Audio Preset", command=self.apply_audio_preset).grid(row=18, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self._combo(right, "Output Mode", "output_mode", ["paste", "clipboard", "type"], 0)
        self._entry(right, "Paste Hotkey", "paste_hotkey", 1)
        self._check(right, "Press Enter after output", "auto_enter", 2)
        self._check(right, "Always listen when target input window is focused", "always_listen_enabled", 3)
        self._entry(right, "Always Listen Hotkey", "always_listen_hotkey", 4)
        self._entry(right, "Record Hotkey", "record_hotkey", 5)
        self._entry(right, "Paste Last Hotkey", "paste_last_hotkey", 6)
        self._entry(right, "Toggle Output Hotkey", "toggle_output_hotkey", 7)
        self._entry(right, "Toggle Enter Hotkey", "toggle_enter_hotkey", 8)
        self._check(right, "Enable local LLM correction command", "llm_correction_enabled", 9)
        self._combo(right, "LLM Profile", "llm_profile", ["균형", "정확도", "직접지정"], 10)
        self._entry(right, "LLM Model", "llm_model", 11)
        self._entry(right, "LLM Base URL", "llm_base_url", 12)
        self._entry(right, "LLM Timeout Seconds", "llm_timeout_seconds", 13)
        btn = ttk.Frame(right)
        btn.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        [btn.columnconfigure(i, weight=1) for i in range(3)]
        for row, col, text, cmd in [
            (0, 0, "Start / Stop Manual", self.toggle_recording),
            (0, 1, "Toggle Always Listen", self.toggle_always_listen),
            (0, 2, "Paste Last", self.paste_last),
            (1, 0, "Save Settings", self.save_from_ui),
            (1, 1, "Doctor", self.show_doctor),
            (1, 2, "Refresh Hotkeys", self.register_hotkeys),
            (2, 0, "Copy Last", self.copy_last),
        ]:
            ttk.Button(btn, text=text, command=cmd).grid(row=row, column=col, sticky="ew", padx=6 if col == 1 else (0 if col == 0 else 6), pady=(8 if row else 0, 0))
        tf = ttk.LabelFrame(self.root, text="Latest Transcript", padding=12)
        tf.grid(row=2, column=0, sticky="nsew", padx=12, pady=(12, 6))
        tf.columnconfigure(0, weight=1)
        self.txt = tk.Text(tf, wrap="word", height=8, font=("Segoe UI", 10))
        self.txt.grid(row=0, column=0, sticky="nsew")
        lf = ttk.LabelFrame(self.root, text="Activity", padding=12)
        lf.grid(row=3, column=0, sticky="nsew", padx=12, pady=(6, 12))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.log_text = tk.Text(lf, wrap="word", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def _entry(self, parent, label, key, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(parent, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        parent.columnconfigure(1, weight=1)

    def _combo(self, parent, label, key, values, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(parent, textvariable=self.vars[key], values=values, state="normal").grid(row=row, column=1, sticky="ew", pady=(6, 0), padx=(8, 0))
        parent.columnconfigure(1, weight=1)

    def _check(self, parent, label, key, row):
        ttk.Checkbutton(parent, text=label, variable=self.bools[key]).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8 if row in {2, 3, 10} else 0, 0))
