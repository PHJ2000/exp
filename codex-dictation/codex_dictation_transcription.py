from __future__ import annotations

import threading
from pathlib import Path

from codex_dictation_commands import COMMAND_PROMPT
from codex_dictation_settings import Settings, language_model_arg
from codex_dictation_utils import normalize_text


def initial_prompt_for_commands(settings: Settings) -> str:
    base = (settings.initial_prompt or "").strip()
    return f"{base} {COMMAND_PROMPT}".strip() if base else COMMAND_PROMPT


def pick_compute_type(value: str) -> str:
    if value != "auto":
        return value
    try:
        import torch

        return "float16" if torch.cuda.is_available() else "int8"
    except Exception:
        return "int8"


class WhisperBackend:
    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()

    def _model(self, settings: Settings):
        from faster_whisper import WhisperModel

        device = settings.whisper_device
        if device == "auto":
            try:
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        key = (settings.whisper_model, device, pick_compute_type(settings.whisper_compute_type))
        with self.lock:
            if key not in self.cache:
                self.cache[key] = WhisperModel(settings.whisper_model, device=device, compute_type=key[2])
            return self.cache[key]

    def transcribe(self, path: Path, settings: Settings) -> str:
        segs, _ = self._model(settings).transcribe(
            path.as_posix(),
            language=language_model_arg(settings.language),
            initial_prompt=initial_prompt_for_commands(settings),
            vad_filter=True,
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segs).strip()


def transcribe_file(file_path: Path, settings: Settings) -> str:
    text = WhisperBackend().transcribe(file_path, settings)
    return normalize_text(text) if settings.normalize_whitespace else text
