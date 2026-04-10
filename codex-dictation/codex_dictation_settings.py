from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _legacy_runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _user_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data).resolve() / "CodexDictation"
    if sys.platform.startswith("win"):
        return Path.home().resolve() / "AppData" / "Local" / "CodexDictation"
    return Path.home().resolve() / ".codex-dictation"


APP_NAME = "Codex Dictation"
LEGACY_ROOT = _legacy_runtime_root()
DATA_ROOT = _user_data_root()
ROOT = DATA_ROOT
SETTINGS_FILENAME = "codex_dictation.settings.json"
HISTORY_FILENAME = "codex_dictation.history.jsonl"
LOG_FILENAME = "codex_dictation.log"
SETTINGS_PATH = DATA_ROOT / SETTINGS_FILENAME
HISTORY_PATH = DATA_ROOT / HISTORY_FILENAME
LOG_PATH = DATA_ROOT / LOG_FILENAME
LEGACY_SETTINGS_PATH = LEGACY_ROOT / SETTINGS_FILENAME
LEGACY_HISTORY_PATH = LEGACY_ROOT / HISTORY_FILENAME
LEGACY_LOG_PATH = LEGACY_ROOT / LOG_FILENAME
AI_PREFETCH_CACHE_SIZE = 3
DEFAULT_LLM_MODEL = "gemma3:4b"


def display_path(path: Path | str, *, base: Path | None = None) -> str:
    candidate = Path(path)
    resolved_base = (base or ROOT).resolve()
    try:
        return candidate.resolve().relative_to(resolved_base).as_posix()
    except ValueError:
        return candidate.name


def ensure_runtime_data_dir() -> Path:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return DATA_ROOT


def _migrate_legacy_file(legacy_path: Path, target_path: Path) -> None:
    if target_path.exists() or not legacy_path.exists():
        return
    ensure_runtime_data_dir()
    try:
        shutil.copy2(legacy_path, target_path)
    except Exception:
        pass


def ensure_runtime_paths() -> None:
    ensure_runtime_data_dir()
    _migrate_legacy_file(LEGACY_SETTINGS_PATH, SETTINGS_PATH)
    _migrate_legacy_file(LEGACY_HISTORY_PATH, HISTORY_PATH)
    _migrate_legacy_file(LEGACY_LOG_PATH, LOG_PATH)

LANGUAGE_UI_LABELS = {"auto": "자동", "ko": "한국어", "en": "영어"}
LLM_PROFILE_MODELS = {"balanced": "gemma3:4b", "accurate": "gemma3:12b"}
LLM_PROFILE_UI_LABELS = {"balanced": "균형", "accurate": "정확도", "custom": "직접지정"}
AUDIO_PRESET_UI_LABELS = {"manual": "직접 조정", "quiet": "조용한 방", "normal": "보통", "noisy": "시끄러운 방"}
DEFAULT_AUDIO_PRESET = "manual"
AUDIO_PROFILE_SETTING_KEYS = (
    "input_device",
    "input_gain",
    "noise_gate_threshold",
    "auto_stop_silence_seconds",
    "always_listen_preroll_seconds",
    "voice_trigger_min_rms",
    "voice_trigger_ratio",
    "voice_trigger_consecutive_blocks",
    "always_listen_enabled",
)
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
    selected_audio_profile: str = ""
    audio_profiles: dict[str, dict[str, object]] = field(default_factory=dict)


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


def normalize_output_mode_value(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "": "auto",
        "auto": "auto",
        "자동": "auto",
        "automatic": "auto",
        "paste": "paste",
        "붙여넣기": "paste",
        "clipboard": "clipboard",
        "클립보드": "clipboard",
        "type": "type",
        "typing": "type",
        "직접입력": "type",
        "직접 입력": "type",
    }
    return aliases.get(raw, "auto")


def normalize_audio_profile_name(value: str | None) -> str:
    return " ".join((value or "").strip().split())[:40]


def snapshot_audio_profile(settings: Settings) -> dict[str, object]:
    profile: dict[str, object] = {}
    for key in AUDIO_PROFILE_SETTING_KEYS:
        profile[key] = getattr(settings, key)
    return profile


def normalize_audio_profiles(profiles: object) -> dict[str, dict[str, object]]:
    if not isinstance(profiles, dict):
        return {}
    normalized: dict[str, dict[str, object]] = {}
    for raw_name, raw_values in profiles.items():
        name = normalize_audio_profile_name(str(raw_name))
        if not name or not isinstance(raw_values, dict):
            continue
        values: dict[str, object] = {}
        for key in AUDIO_PROFILE_SETTING_KEYS:
            if key in raw_values:
                values[key] = raw_values[key]
        if values:
            normalized[name] = values
    return normalized


def apply_audio_profile(settings: Settings, profile: dict[str, object]) -> None:
    for key in AUDIO_PROFILE_SETTING_KEYS:
        if key not in profile:
            continue
        current = getattr(settings, key)
        value = profile[key]
        if isinstance(current, bool):
            setattr(settings, key, bool(value))
        elif isinstance(current, int):
            setattr(settings, key, int(value))
        elif isinstance(current, float):
            setattr(settings, key, float(value))
        else:
            setattr(settings, key, str(value))
    settings.audio_preset = DEFAULT_AUDIO_PRESET


def resolve_llm_model(settings: Settings) -> str:
    profile = normalize_llm_profile_value(settings.llm_profile)
    if profile in LLM_PROFILE_MODELS:
        return LLM_PROFILE_MODELS[profile]
    custom = (settings.llm_model or "").strip()
    return custom or DEFAULT_LLM_MODEL


def load_settings() -> Settings:
    ensure_runtime_paths()
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
    settings.output_mode = normalize_output_mode_value(settings.output_mode)
    settings.selected_audio_profile = normalize_audio_profile_name(settings.selected_audio_profile)
    settings.audio_profiles = normalize_audio_profiles(settings.audio_profiles)
    return settings


def save_settings(settings: Settings) -> None:
    ensure_runtime_paths()
    SETTINGS_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
