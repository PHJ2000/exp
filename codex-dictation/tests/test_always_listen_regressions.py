from __future__ import annotations

import queue
import sys
import threading
import time
import unittest
from pathlib import Path

import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from codex_dictation_audio import AlwaysListen  # noqa: E402
from codex_dictation_app_runtime import AppRuntimeMixin  # noqa: E402
from codex_dictation_settings import Settings  # noqa: E402


def _mono_block(values) -> np.ndarray:
    return np.asarray(values, dtype=np.float32).reshape(-1, 1)


class _FakeBackend:
    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.calls = 0

    def transcribe(self, path, settings):
        _ = (path, settings)
        index = self.calls
        self.calls += 1
        return self.outputs[index]


class _RuntimeHarness(AppRuntimeMixin):
    def __init__(self, outputs: list[str]):
        self.jobs = queue.Queue()
        self.log_q = queue.Queue()
        self.res_q = queue.Queue()
        self.backend = _FakeBackend(outputs)
        self.s = Settings(sample_rate=100, trim_silence=False)
        self.logs: list[str] = []
        self.emitted: list[str] = []
        self.history: list[tuple[str, dict]] = []
        self.last = ""
        self.transcribing = False
        self.active_transcription_source = ""
        self.log_text = _NullText()
        self.root = _NullRoot()

    def log(self, message):
        self.logs.append(message)

    def refresh_status(self, activity="Idle"):
        _ = activity

    def beep(self, kind):
        _ = kind

    def is_voice_command_text(self, text):
        _ = text
        return False

    def handle_voice_command(self, text):
        _ = text
        return False

    def _update_latest_transcript(self, text):
        self.last = text

    def emit_text(self, text):
        self.emitted.append(text)


class _NullText:
    def insert(self, *_args, **_kwargs):
        pass

    def see(self, *_args, **_kwargs):
        pass


class _NullRoot:
    def after(self, *_args, **_kwargs):
        pass


class AlwaysListenRegressionTests(unittest.TestCase):
    def setUp(self):
        self.logs: list[str] = []
        self.captured: list[tuple[str, np.ndarray]] = []
        self.settings = Settings(
            sample_rate=100,
            input_gain=1.0,
            noise_gate_threshold=0.0,
            trim_threshold=0.005,
            voice_trigger_min_rms=0.02,
            voice_trigger_ratio=2.0,
            voice_trigger_consecutive_blocks=1,
            min_record_seconds=0.25,
            auto_stop_silence_seconds=0.65,
            max_record_seconds=5,
        )
        self.listen = AlwaysListen(
            self.settings,
            self.logs.append,
            lambda audio, source: self.captured.append((source, audio.copy())),
            lambda: True,
        )

    def _feed(self, values):
        block = _mono_block(values)
        self.listen._cb(block, len(block), None, None)

    def test_always_listen_keeps_segment_order_when_second_phrase_arrives_soon_after_first(self):
        self._feed(np.zeros(20, dtype=np.float32))
        self._feed(np.full(35, 0.12, dtype=np.float32))
        self._feed(np.zeros(66, dtype=np.float32))

        self._feed(np.zeros(10, dtype=np.float32))
        self._feed(np.full(30, 0.14, dtype=np.float32))
        self._feed(np.zeros(66, dtype=np.float32))

        self.assertEqual([source for source, _ in self.captured], ["always_listen", "always_listen"])
        self.assertEqual(len(self.captured), 2)
        self.assertGreater(len(self.captured[0][1]), len(self.captured[1][1]) - 30)
        self.assertTrue(any("Always-listen finalized after" in message for message in self.logs))

    def test_always_listen_preserves_weak_tail_samples_when_finalizing(self):
        self._feed(np.zeros(20, dtype=np.float32))
        self._feed(np.full(40, 0.11, dtype=np.float32))

        trailing = np.concatenate(
            [
                np.full(14, 0.015, dtype=np.float32),
                np.zeros(4, dtype=np.float32),
                np.zeros(56, dtype=np.float32),
            ]
        )
        self._feed(trailing)

        self.assertEqual(len(self.captured), 1)
        captured_audio = self.captured[0][1]

        self.assertGreater(len(captured_audio), 40)
        tail_window = captured_audio[-18:]
        np.testing.assert_allclose(tail_window[:14], np.full(14, 0.015, dtype=np.float32), atol=1e-6)
        np.testing.assert_allclose(tail_window[14:], np.zeros(4, dtype=np.float32), atol=1e-6)

    def test_poll_preserves_capture_order_for_back_to_back_segments(self):
        runtime = _RuntimeHarness(["first result", "second result"])
        worker = threading.Thread(target=runtime._transcription_loop, daemon=True)
        worker.start()

        import codex_dictation_app_runtime as runtime_module
        original_append_history = runtime_module.append_history
        runtime_module.append_history = lambda text, meta: runtime.history.append((text, meta))
        deadline = time.time() + 5.0
        try:
            runtime.res_q.put(
                ("captured", {"audio": np.full(40, 0.12, dtype=np.float32), "source": "always_listen"})
            )
            runtime.res_q.put(
                ("captured", {"audio": np.full(30, 0.11, dtype=np.float32), "source": "always_listen"})
            )

            while len(runtime.emitted) < 2 and time.time() < deadline:
                runtime.poll()
                time.sleep(0.05)
        finally:
            runtime_module.append_history = original_append_history

        self.assertEqual(runtime.emitted, ["first result", "second result"])
        self.assertEqual([meta["source"] for _, meta in runtime.history], ["always_listen", "always_listen"])
        self.assertTrue(any("Queued always_listen audio for background transcription" in message for message in runtime.logs))


if __name__ == "__main__":
    unittest.main()
