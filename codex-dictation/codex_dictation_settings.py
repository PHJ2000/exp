from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_NAME = "Codex Dictation"
ROOT = _runtime_root()
SETTINGS_PATH = ROOT / "codex_dictation.settings.json"
HISTORY_PATH = ROOT / "codex_dictation.history.jsonl"
LOG_PATH = ROOT / "codex_dictation.log"
AI_PREFETCH_CACHE_SIZE = 3
DEFAULT_LLM_MODEL = "gemma3:4b"

LANGUAGE_UI_LABELS = {"auto": "자동", "ko": "한국어", "en": "영어"}
LLM_PROFILE_MODELS = {"balanced": "gemma3:4b", "accurate": "gemma3:12b"}
LLM_PROFILE_UI_LABELS = {"balanced": "균형", "accurate": "정확도", "custom": "직접지정"}
AUDIO_PRESET_UI_LABELS = {"manual": "직접 조정", "quiet": "조용한 방", "normal": "보통", "noisy": "시끄러운 방"}
DEFAULT_AUDIO_PRESET = "manual"
AUDIO_PRESET_VALUES = {
    "manual": {},
    "quiet": {"input_gain": 1.35, "noise_gate_threshold": 0.003, "voice_trigger_min_rms": 0.014, "voice_trigger_ratio": 2.0},
    "normal": {"input_gain": 1.0, "noise_gate_threshold": 0.006, "voice_trigger_min_rms": 0.018, "voice_trigger_ratio": 2.2},
    "noisy": {"input_gain": 1.0, "noise_gate_threshold": 0.012, "voice_trigger_min_rms": 0.03, "voice_trigger_ratio": 3.0},
}


@dataclass
class Settings:
    input_device: str = ""
    sample_rate: int = 16000
    channels: int = 1
    input_gain: float = 1.0
    audio_preset: str = DEFAULT_AUDIO_PRESET
    noise_gate_threshold: float = 0.0
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    language: str = "auto"
    initial_prompt: str = ""
    record_hotkey: str = "f8"
    always_listen_hotkey: str = "f7"
    paste_last_hotkey: str = "f9"
    toggle_output_hotkey: str = "f10"
    toggle_enter_hotkey: str = "f11"
    output_mode: str = "type"
    paste_hotkey: str = "ctrl+v"
    auto_enter: bool = False
    trim_silence: bool = True
    trim_threshold: float = 0.008
    normalize_whitespace: bool = True
    max_record_seconds: int = 45
    min_record_seconds: float = 0.25
    beep_feedback: bool = False
    keep_window_on_top: bool = False
    enable_auto_stop: bool = False
    auto_stop_silence_seconds: float = 0.65
    always_listen_enabled: bool = True
    always_listen_preroll_seconds: float = 0.25
    voice_trigger_min_rms: float = 0.018
    voice_trigger_ratio: float = 2.2
    voice_trigger_consecutive_blocks: int = 2
    llm_correction_enabled: bool = False
    llm_profile: str = "balanced"
    llm_model: str = DEFAULT_LLM_MODEL
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_timeout_seconds: float = 8.0


def normalize_language_value(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "": "auto",
        "auto": "auto",
        "자동": "auto",
        "자동으로": "auto",
        "자동감지": "auto",
        "자동 감지": "auto",
        "오토": "auto",
        "ko": "ko",
        "kr": "ko",
        "한국어": "ko",
        "한국어로": "ko",
        "한글": "ko",
        "한글로": "ko",
        "korean": "ko",
        "en": "en",
        "영어": "en",
        "영어로": "en",
        "english": "en",
        "잉글리시": "en",
    }
    return aliases.get(raw, "auto")


def language_label(value: str | None) -> str:
    return LANGUAGE_UI_LABELS.get(normalize_language_value(value), "자동")


def language_model_arg(value: str | None) -> str | None:
    normalized = normalize_language_value(value)
    return None if normalized == "auto" else normalized


def normalize_llm_profile_value(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "balanced": "balanced",
        "균형": "balanced",
        "accurate": "accurate",
        "정확도": "accurate",
        "custom": "custom",
        "직접지정": "custom",
        "직접 지정": "custom",
    }
    return aliases.get(raw, "balanced")


def llm_profile_label(value: str | None) -> str:
    return LLM_PROFILE_UI_LABELS.get(normalize_llm_profile_value(value), "균형")


def normalize_audio_preset_value(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "manual": "manual",
        "직접": "manual",
        "직접조정": "manual",
        "직접 조정": "manual",
        "quiet": "quiet",
        "조용한방": "quiet",
        "조용한 방": "quiet",
        "normal": "normal",
        "보통": "normal",
        "noisy": "noisy",
        "시끄러운방": "noisy",
        "시끄러운 방": "noisy",
    }
    return aliases.get(raw, DEFAULT_AUDIO_PRESET)


def audio_preset_label(value: str | None) -> str:
    normalized = normalize_audio_preset_value(value)
    return AUDIO_PRESET_UI_LABELS.get(normalized, AUDIO_PRESET_UI_LABELS[DEFAULT_AUDIO_PRESET])


def resolve_llm_model(settings: Settings) -> str:
    profile = normalize_llm_profile_value(settings.llm_profile)
    if profile in LLM_PROFILE_MODELS:
        return LLM_PROFILE_MODELS[profile]
    custom = (settings.llm_model or "").strip()
    return custom or DEFAULT_LLM_MODEL


def load_settings() -> Settings:
    if not SETTINGS_PATH.exists():
        settings = Settings()
        save_settings(settings)
        return settings
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    allowed = {field.name for field in Settings.__dataclass_fields__.values()}
    settings = Settings(**{key: value for key, value in data.items() if key in allowed})
    settings.input_gain = max(float(settings.input_gain), 0.0)
    settings.audio_preset = normalize_audio_preset_value(settings.audio_preset)
    settings.noise_gate_threshold = max(float(settings.noise_gate_threshold), 0.0)
    settings.language = normalize_language_value(settings.language)
    settings.llm_profile = normalize_llm_profile_value(settings.llm_profile)
    return settings


def save_settings(settings: Settings) -> None:
    SETTINGS_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
