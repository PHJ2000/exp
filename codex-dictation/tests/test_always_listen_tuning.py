from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from codex_dictation_audio import AlwaysListenTuningStats, recommend_always_listen_tuning  # noqa: E402
from codex_dictation_settings import Settings  # noqa: E402


class AlwaysListenTuningTests(unittest.TestCase):
    def test_waits_for_enough_samples_before_recommending(self):
        suggestion = recommend_always_listen_tuning(Settings(), AlwaysListenTuningStats(observed_blocks=8))
        self.assertFalse(suggestion.ready)
        self.assertIn("표본", suggestion.summary)

    def test_recommends_gain_and_preroll_for_weak_voice_starts(self):
        settings = Settings(input_gain=1.0, always_listen_preroll_seconds=0.25)
        stats = AlwaysListenTuningStats(observed_blocks=48, near_threshold_waits=7, weak_voice_starts=3)
        suggestion = recommend_always_listen_tuning(settings, stats)
        self.assertTrue(suggestion.ready)
        self.assertGreater(suggestion.changes["input_gain"], settings.input_gain)
        self.assertGreater(suggestion.changes["always_listen_preroll_seconds"], settings.always_listen_preroll_seconds)

    def test_recommends_longer_silence_for_short_segments(self):
        settings = Settings(auto_stop_silence_seconds=0.65)
        stats = AlwaysListenTuningStats(observed_blocks=52, split_events=2, short_segments=2)
        suggestion = recommend_always_listen_tuning(settings, stats)
        self.assertTrue(suggestion.ready)
        self.assertGreater(suggestion.changes["auto_stop_silence_seconds"], settings.auto_stop_silence_seconds)


if __name__ == "__main__":
    unittest.main()
