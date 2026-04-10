from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from codex_dictation_settings import (  # noqa: E402
    DEFAULT_AUDIO_PRESET,
    DEFAULT_LLM_MODEL,
    ROOT,
    Settings,
    apply_audio_profile,
    audio_preset_label,
    display_path,
    language_label,
    language_model_arg,
    normalize_audio_profile_name,
    normalize_audio_profiles,
    llm_profile_label,
    normalize_audio_preset_value,
    normalize_language_value,
    normalize_llm_profile_value,
    resolve_llm_model,
    snapshot_audio_profile,
)
from codex_dictation_utils import normalize_text, short_log_text  # noqa: E402


class SettingsNormalizationTests(unittest.TestCase):
    def test_display_path_prefers_relative_path_when_under_base(self):
        nested = ROOT / "logs" / "session.log"
        self.assertEqual(display_path(nested, base=ROOT), "logs/session.log")

    def test_display_path_falls_back_to_name_outside_base(self):
        outside = Path.cwd().resolve().parent / "outside.txt"
        self.assertEqual(display_path(outside, base=ROOT), "outside.txt")

    def test_language_normalization_and_labels(self):
        self.assertEqual(normalize_language_value("한국어로"), "ko")
        self.assertEqual(normalize_language_value("english"), "en")
        self.assertEqual(normalize_language_value("???"), "auto")
        self.assertEqual(language_label("en"), "영어")
        self.assertEqual(language_model_arg("자동"), None)
        self.assertEqual(language_model_arg("한국어"), "ko")

    def test_llm_profile_normalization_and_resolution(self):
        self.assertEqual(normalize_llm_profile_value("정확도"), "accurate")
        self.assertEqual(llm_profile_label("custom"), "직접지정")
        balanced = Settings(llm_profile="balanced", llm_model="custom:1")
        custom = Settings(llm_profile="custom", llm_model="custom:1")
        empty_custom = Settings(llm_profile="custom", llm_model="  ")
        self.assertEqual(resolve_llm_model(balanced), "gemma3:4b")
        self.assertEqual(resolve_llm_model(custom), "custom:1")
        self.assertEqual(resolve_llm_model(empty_custom), DEFAULT_LLM_MODEL)

    def test_audio_preset_normalization_and_label(self):
        self.assertEqual(normalize_audio_preset_value("조용한 방"), "quiet")
        self.assertEqual(normalize_audio_preset_value("unknown"), DEFAULT_AUDIO_PRESET)
        self.assertEqual(audio_preset_label("noisy"), "시끄러운 방")

    def test_audio_profile_name_and_profile_normalization(self):
        self.assertEqual(normalize_audio_profile_name("  회의 용  "), "회의 용")
        normalized = normalize_audio_profiles(
            {
                "  회의 용  ": {
                    "input_gain": 1.4,
                    "always_listen_enabled": True,
                    "unknown": "ignored",
                }
            }
        )
        self.assertEqual(sorted(normalized.keys()), ["회의 용"])
        self.assertEqual(normalized["회의 용"]["input_gain"], 1.4)
        self.assertNotIn("unknown", normalized["회의 용"])

    def test_snapshot_and_apply_audio_profile(self):
        settings = Settings(
            input_device="USB Mic",
            input_gain=1.7,
            noise_gate_threshold=0.01,
            auto_stop_silence_seconds=0.8,
            always_listen_preroll_seconds=0.35,
            voice_trigger_min_rms=0.02,
            voice_trigger_ratio=2.8,
            voice_trigger_consecutive_blocks=3,
            always_listen_enabled=False,
            audio_preset="quiet",
        )
        profile = snapshot_audio_profile(settings)
        reapplied = Settings(audio_preset="noisy")
        apply_audio_profile(reapplied, profile)
        self.assertEqual(reapplied.input_device, "USB Mic")
        self.assertAlmostEqual(reapplied.input_gain, 1.7)
        self.assertFalse(reapplied.always_listen_enabled)
        self.assertEqual(reapplied.audio_preset, DEFAULT_AUDIO_PRESET)


class UtilsTests(unittest.TestCase):
    def test_normalize_text_compacts_whitespace(self):
        self.assertEqual(normalize_text("  첫째 줄\r\n둘째   줄  "), "첫째 줄 둘째 줄")

    def test_short_log_text_truncates_with_ellipsis(self):
        truncated = short_log_text("하나 둘 셋 넷 다섯 여섯", limit=9)
        self.assertEqual(truncated, "하나 둘 셋...")
        self.assertEqual(short_log_text("짧은 문장", limit=20), "짧은 문장")


if __name__ == "__main__":
    unittest.main()
