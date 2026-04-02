from __future__ import annotations

import sys

from codex_dictation_audio import get_input_devices
from codex_dictation_settings import (
    APP_NAME,
    HISTORY_PATH,
    LOG_PATH,
    SETTINGS_PATH,
    Settings,
    audio_preset_label,
    language_label,
    llm_profile_label,
    normalize_audio_preset_value,
    normalize_language_value,
    normalize_llm_profile_value,
    resolve_llm_model,
)
from codex_dictation_targeting import (
    fg_info,
    fmt_info,
    gui_focus_info,
    is_codex_terminal,
    is_general_input_target,
    is_target_window,
    is_terminal,
)


def doctor(settings: Settings | None = None) -> str:
    lines = [
        f"{APP_NAME} doctor",
        "-" * 40,
        f"Python: {sys.version.split()[0]}",
        f"Settings: {SETTINGS_PATH}",
        f"History: {HISTORY_PATH}",
        f"Log: {LOG_PATH}",
    ]
    if settings:
        lines += [
            f"Always listen enabled: {settings.always_listen_enabled}",
            f"Audio preset: {audio_preset_label(settings.audio_preset)} ({normalize_audio_preset_value(settings.audio_preset)})",
            f"Input gain: {float(settings.input_gain):.2f}",
            f"Noise gate threshold: {float(settings.noise_gate_threshold):.4f}",
            f"Language: {language_label(settings.language)} ({normalize_language_value(settings.language)})",
            f"LLM correction enabled: {settings.llm_correction_enabled}",
            f"LLM profile: {llm_profile_label(settings.llm_profile)} ({normalize_llm_profile_value(settings.llm_profile)})",
            f"LLM model: {resolve_llm_model(settings)}",
            f"LLM base URL: {settings.llm_base_url}",
        ]
    try:
        devices = get_input_devices()
        lines.append(f"Input devices: {len(devices)}")
        for device in devices[:10]:
            lines.append(f"  - [{device['index']}] {device['name']} ({device['sample_rate']} Hz)")
    except Exception as exc:
        lines.append(f"Input devices: failed ({exc})")
    info = fg_info()
    focus = gui_focus_info(info)
    lines += [
        f"Foreground window: {fmt_info(info)}",
        f"Focused child hwnd: {getattr(focus, 'focus_hwnd', 0)} | class={getattr(focus, 'focus_cls', '') or 'none'}",
        f"Caret hwnd: {getattr(focus, 'caret_hwnd', 0)} | class={getattr(focus, 'caret_cls', '') or 'none'} | visible={getattr(focus, 'caret_visible', False)}",
        f"Looks like terminal: {is_terminal(info)}",
        f"Looks like Codex terminal: {is_codex_terminal(info)}",
        f"Looks like general input target: {is_general_input_target(info)}",
        f"Accepts as target window: {is_target_window(info)}",
    ]
    for name, module_name in [("keyboard", "keyboard"), ("faster-whisper", "faster_whisper"), ("psutil", "psutil")]:
        try:
            __import__(module_name)
            lines.append(f"{name}: OK")
        except Exception as exc:
            lines.append(f"{name}: missing ({exc})")
    try:
        import torch

        lines += [f"torch: {torch.__version__}", f"torch cuda available: {torch.cuda.is_available()}"]
        if torch.cuda.is_available():
            lines.append(f"torch cuda device: {torch.cuda.get_device_name(0)}")
    except Exception as exc:
        lines.append(f"torch: unavailable ({exc})")
    return "\n".join(lines)
