from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from codex_dictation_commands import (  # noqa: E402
    is_voice_command_text,
    parse_correction_text,
    parse_delete_count_text,
    parse_language_switch_text,
    parse_media_command_text,
    parse_slot_command_text,
)
from codex_dictation_utils import command_key  # noqa: E402


class CommandParsingTests(unittest.TestCase):
    def test_command_key_removes_spacing_and_punctuation(self):
        self.assertEqual(command_key(" 보내 줘! "), "보내줘")

    def test_parse_language_switch_supports_korean_aliases(self):
        self.assertEqual(parse_language_switch_text("자동 감지"), "auto")
        self.assertEqual(parse_language_switch_text("한국어로"), "ko")
        self.assertEqual(parse_language_switch_text("잉글리시"), "en")

    def test_parse_correction_trims_known_prefix_and_punctuation(self):
        self.assertEqual(parse_correction_text("다시 말해줘 테스트 문장."), "테스트 문장")
        self.assertEqual(parse_correction_text("다시, 끝음 처리"), "끝음 처리")
        self.assertEqual(parse_correction_text("그냥 일반 문장"), "")

    def test_parse_slot_command_handles_copy_cut_and_paste(self):
        self.assertEqual(parse_slot_command_text("세번 복사"), ("copy", 3))
        self.assertEqual(parse_slot_command_text("잘라 두번"), ("cut", 2))
        self.assertEqual(parse_slot_command_text("붙여넣기 열번"), ("paste", 10))

    def test_parse_media_command_supports_escape_and_seek(self):
        self.assertEqual(parse_media_command_text("전체 화면 나가기"), ("escape", 1))
        self.assertEqual(parse_media_command_text("앞으로 감기 세번"), ("forward", 3))
        self.assertEqual(parse_media_command_text("두번 뒤로 감아"), ("backward", 2))

    def test_parse_delete_count_supports_alias_and_numeric_variants(self):
        self.assertEqual(parse_delete_count_text("지워줘"), 1)
        self.assertEqual(parse_delete_count_text("3번 지워"), 3)
        self.assertEqual(parse_delete_count_text("두 번만 치워"), 2)
        self.assertEqual(parse_delete_count_text("지울래"), 0)

    def test_is_voice_command_text_detects_representative_cases(self):
        self.assertTrue(is_voice_command_text("보내 줘"))
        self.assertTrue(is_voice_command_text("교정해"))
        self.assertTrue(is_voice_command_text("네번 붙여넣기"))
        self.assertTrue(is_voice_command_text("영어로"))
        self.assertFalse(is_voice_command_text("오늘 점심 뭐 먹지"))


if __name__ == "__main__":
    unittest.main()

