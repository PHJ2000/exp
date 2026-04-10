from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import codex_dictation_app_actions as actions_module  # noqa: E402
from codex_dictation_app_actions import AppActionsMixin  # noqa: E402
from codex_dictation_targeting import WinInfo  # noqa: E402


class _ListBoxStub:
    def __init__(self):
        self._selection = (0,)

    def curselection(self):
        return self._selection

    def set_selection(self, selection):
        self._selection = selection


class _HistoryHarness(AppActionsMixin):
    def __init__(self):
        self.history_list = _ListBoxStub()
        self.history_items = [{"text": "최근 기록 테스트"}]
        self.logs: list[str] = []
        self.updated: list[str] = []
        self.emitted: list[str] = []
        self.clipboard: list[str] = []
        self.launch_target = None
        self.last_target_window = None

    def log(self, message):
        self.logs.append(message)

    def _update_latest_transcript(self, text):
        self.updated.append(text)

    def emit_text(self, text):
        self.emitted.append(text)
        return True

    def copy_clip(self, text):
        self.clipboard.append(text)


class HistoryBrowserTests(unittest.TestCase):
    def setUp(self):
        self.original_fg_info = actions_module.fg_info
        self.original_focus_window = actions_module.focus_window
        self.addCleanup(self._restore)

    def _restore(self):
        actions_module.fg_info = self.original_fg_info
        actions_module.focus_window = self.original_focus_window

    def test_paste_selected_history_restores_last_target_window_before_emitting(self):
        harness = _HistoryHarness()
        harness.last_target_window = WinInfo(hwnd=77, pid=200, title="메모장", cls="Notepad", proc="notepad.exe")
        focused: list[int] = []

        actions_module.fg_info = lambda: WinInfo(hwnd=1, pid=actions_module.APP_PID, title="Codex Dictation", cls="TkTopLevel", proc="pythonw.exe")
        actions_module.focus_window = lambda hwnd: focused.append(hwnd) or True

        result = harness.paste_selected_history()

        self.assertTrue(result)
        self.assertEqual(focused, [77])
        self.assertEqual(harness.updated, ["최근 기록 테스트"])
        self.assertEqual(harness.emitted, ["최근 기록 테스트"])

    def test_paste_selected_history_rejects_when_no_target_window_can_be_restored(self):
        harness = _HistoryHarness()

        actions_module.fg_info = lambda: WinInfo(hwnd=1, pid=actions_module.APP_PID, title="Codex Dictation", cls="TkTopLevel", proc="pythonw.exe")
        actions_module.focus_window = lambda hwnd: True

        result = harness.paste_selected_history()

        self.assertFalse(result)
        self.assertEqual(harness.updated, ["최근 기록 테스트"])
        self.assertEqual(harness.emitted, [])
        self.assertTrue(any("no previous target window" in message for message in harness.logs))


if __name__ == "__main__":
    unittest.main()
