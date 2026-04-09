from __future__ import annotations

import sys
import tempfile
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
    audio_preset_label,
    display_path,
    language_label,
    language_model_arg,
    llm_profile_label,
    normalize_audio_preset_value,
    normalize_language_value,
    normalize_llm_profile_value,
    resolve_llm_model,
)
from codex_dictation_utils import (  # noqa: E402
    filter_history_entries,
    format_history_entry,
    normalize_text,
    read_history_entries,
    short_log_text,
)


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


class UtilsTests(unittest.TestCase):
    def test_normalize_text_compacts_whitespace(self):
        self.assertEqual(normalize_text("  첫째 줄\r\n둘째   줄  "), "첫째 줄 둘째 줄")

    def test_short_log_text_truncates_with_ellipsis(self):
        truncated = short_log_text("하나 둘 셋 넷 다섯 여섯", limit=9)
        self.assertEqual(truncated, "하나 둘 셋...")
        self.assertEqual(short_log_text("짧은 문장", limit=20), "짧은 문장")

    def test_read_history_entries_returns_latest_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.jsonl"
            history_path.write_text(
                '\n'.join(
                    [
                        '{"timestamp":"2026-04-09T10:00:00","text":"첫 문장"}',
                        '{"timestamp":"2026-04-09T10:01:00","text":"둘째 문장"}',
                    ]
                ),
                encoding="utf-8",
            )
            entries = read_history_entries(history_path)
        self.assertEqual([entry["text"] for entry in entries], ["둘째 문장", "첫 문장"])

    def test_filter_history_entries_matches_normalized_query(self):
        entries = [
            {"timestamp": "2026-04-09T10:00:00", "text": "회의 메모 정리"},
            {"timestamp": "2026-04-09T10:01:00", "text": "장보기 목록"},
        ]
        filtered = filter_history_entries(entries, "회의   메모")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["text"], "회의 메모 정리")

    def test_format_history_entry_includes_timestamp_and_text(self):
        formatted = format_history_entry({"timestamp": "2026-04-09T10:01:02", "text": "최근 기록 테스트"})
        self.assertEqual(formatted, "2026-04-09 10:01:02 | 최근 기록 테스트")


if __name__ == "__main__":
    unittest.main()
