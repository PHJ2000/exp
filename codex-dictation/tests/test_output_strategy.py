from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from codex_dictation_targeting import (  # noqa: E402
    WinInfo,
    classify_output_target,
    recommended_output_mode_for_target,
)


class OutputStrategyTests(unittest.TestCase):
    def test_browser_targets_prefer_paste(self):
        info = WinInfo(hwnd=1, pid=100, title="Chrome", cls="Chrome_WidgetWin_1", proc="chrome.exe")
        self.assertEqual(classify_output_target(info, precise_focus=False, terminal=False, general_input=True), "browser")
        self.assertEqual(recommended_output_mode_for_target(info, precise_focus=False, terminal=False, general_input=True), "paste")

    def test_messenger_targets_prefer_paste(self):
        info = WinInfo(hwnd=1, pid=100, title="Slack", cls="Chrome_WidgetWin_1", proc="slack.exe")
        self.assertEqual(classify_output_target(info, precise_focus=False, terminal=False, general_input=True), "messenger")
        self.assertEqual(recommended_output_mode_for_target(info, precise_focus=False, terminal=False, general_input=True), "paste")

    def test_terminal_targets_prefer_type(self):
        info = WinInfo(hwnd=1, pid=100, title="Windows Terminal", cls="CASCADIA_HOSTING_WINDOW_CLASS", proc="windowsterminal.exe")
        self.assertEqual(classify_output_target(info, precise_focus=False, terminal=True, general_input=False), "terminal")
        self.assertEqual(recommended_output_mode_for_target(info, precise_focus=False, terminal=True, general_input=False), "type")

    def test_precise_text_focus_prefers_type(self):
        info = WinInfo(hwnd=1, pid=100, title="메모장", cls="Notepad", proc="notepad.exe")
        self.assertEqual(classify_output_target(info, precise_focus=True, terminal=False, general_input=True), "text")
        self.assertEqual(recommended_output_mode_for_target(info, precise_focus=True, terminal=False, general_input=True), "type")

    def test_general_targets_stay_conservative_with_type(self):
        info = WinInfo(hwnd=1, pid=100, title="Some App", cls="MainWindow", proc="custom-editor.exe")
        self.assertEqual(classify_output_target(info, precise_focus=False, terminal=False, general_input=True), "general")
        self.assertEqual(recommended_output_mode_for_target(info, precise_focus=False, terminal=False, general_input=True), "type")

    def test_unknown_targets_stay_conservative_with_type(self):
        info = WinInfo(hwnd=1, pid=100, title="", cls="MysteryClass", proc="mystery.exe")
        self.assertEqual(classify_output_target(info, precise_focus=False, terminal=False, general_input=False), "unknown")
        self.assertEqual(recommended_output_mode_for_target(info, precise_focus=False, terminal=False, general_input=False), "type")

    def test_system_targets_prefer_paste(self):
        info = WinInfo(hwnd=1, pid=100, title="설정", cls="ApplicationFrameWindow", proc="systemsettings.exe")
        self.assertEqual(classify_output_target(info, precise_focus=False, terminal=False, general_input=True), "system")
        self.assertEqual(recommended_output_mode_for_target(info, precise_focus=False, terminal=False, general_input=True), "paste")


if __name__ == "__main__":
    unittest.main()
