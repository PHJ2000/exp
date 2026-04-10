from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import sounddevice as sd

from codex_dictation_settings import Settings


def get_input_devices():
    out = []
    for index, device in enumerate(sd.query_devices()):
        if int(device["max_input_channels"]) > 0:
            out.append({"index": index, "name": str(device["name"]), "sample_rate": int(device["default_samplerate"])})
    return out


def default_input_device_name():
    try:
        default_in = sd.default.device[0]
        for device in get_input_devices():
            if int(device["index"]) == int(default_in):
                return device["name"]
    except Exception:
        pass
    devices = get_input_devices()
    return devices[0]["name"] if devices else ""


def resolve_input_device(value):
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    for device in get_input_devices():
        if device["name"] == value:
            return int(device["index"])
    try:
        return int(value)
    except Exception:
        return None


def trim_silence(audio: np.ndarray, threshold: float) -> np.ndarray:
    if audio.size == 0:
        return audio
    voiced = np.where(np.abs(audio) > threshold)[0]
    if voiced.size == 0:
        return audio
    start = max(int(voiced[0]) - 1600, 0)
    end = min(int(voiced[-1]) + 1600, len(audio))
    return audio[start:end]


def rms_level(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def apply_input_gain(audio: np.ndarray, gain: float) -> np.ndarray:
    if audio.size == 0:
        return audio
    gain = max(float(gain), 0.0)
    if gain == 1.0:
        return audio
    return np.clip((audio * gain).astype(np.float32, copy=False), -1.0, 1.0).astype(np.float32, copy=False)


def apply_noise_gate(audio: np.ndarray, threshold: float) -> np.ndarray:
    if audio.size == 0:
        return audio
    threshold = max(float(threshold), 0.0)
    if threshold <= 0.0:
        return audio
    gated = audio.copy()
    gated[np.abs(gated) < threshold] = 0.0
    return gated


@dataclass
class AlwaysListenTuningStats:
    observed_blocks: int = 0
    near_threshold_waits: int = 0
    weak_voice_starts: int = 0
    split_events: int = 0
    finalize_events: int = 0
    short_segments: int = 0
    last_reason: str = ""


@dataclass
class AlwaysListenTuningSuggestion:
    summary: str
    changes: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return bool(self.changes)

    def describe_changes(self) -> str:
        if not self.changes:
            return "변경 없음"
        return ", ".join(f"{key}={value:.2f}" for key, value in self.changes.items())


def recommend_always_listen_tuning(settings: Settings, stats: AlwaysListenTuningStats) -> AlwaysListenTuningSuggestion:
    if stats.observed_blocks < 24:
        remaining = max(24 - stats.observed_blocks, 0)
        return AlwaysListenTuningSuggestion(
            summary=f"추천 대기 중: always-listen 표본 {stats.observed_blocks}개 수집 ({remaining}개 더 필요)",
            reasons=["최근 always-listen 표본이 더 쌓이면 추천을 계산합니다."],
        )
    changes: dict[str, float] = {}
    reasons: list[str] = []
    if stats.near_threshold_waits >= 6 or stats.weak_voice_starts >= 3:
        next_gain = round(min(max(settings.input_gain, 1.0) + 0.15, 3.0), 2)
        next_preroll = round(min(max(settings.always_listen_preroll_seconds, 0.45) + 0.05, 0.9), 2)
        if next_gain != round(settings.input_gain, 2):
            changes["input_gain"] = next_gain
        if next_preroll != round(settings.always_listen_preroll_seconds, 2):
            changes["always_listen_preroll_seconds"] = next_preroll
        reasons.append("시작 음절이 약하거나 감지 직전까지 임계값에 자주 걸려서 입력 gain / preroll 상향을 추천합니다.")
    if stats.short_segments >= 2 or stats.split_events >= 2:
        next_silence = round(min(max(settings.auto_stop_silence_seconds, 0.65) + 0.15, 1.4), 2)
        if next_silence != round(settings.auto_stop_silence_seconds, 2):
            changes["auto_stop_silence_seconds"] = next_silence
        reasons.append("짧은 구간 분할이 반복돼서 문장 종료 침묵 기준 완화를 추천합니다.")
    if not changes:
        return AlwaysListenTuningSuggestion(
            summary="현재 always-listen 감도는 크게 건드릴 필요가 없어 보여요.",
            reasons=["최근 표본 기준으로 시작/끝음 문제나 과분할 징후가 두드러지지 않았습니다."],
        )
    summary = "추천 준비됨: " + ", ".join(
        f"{key} -> {value:.2f}" for key, value in changes.items()
    )
    return AlwaysListenTuningSuggestion(summary=summary, changes=changes, reasons=reasons)


class Recorder:
    def __init__(self, settings: Settings, log):
        self.s = settings
        self.log = log
        self.stream = None
        self.chunks = []
        self.lock = threading.Lock()
        self.t0 = 0.0
        self.last_voice = 0.0
        self.on = False
        self.noise_floor = max(self.s.trim_threshold * 0.8, 0.003)
        self.last_rms = 0.0
        self.last_peak = 0.0
        self.last_threshold = 0.0
        self.last_voice_detected = False
        self.last_updated = 0.0

    def start(self):
        if self.on:
            return
        self.chunks = []
        self.t0 = time.monotonic()
        self.last_voice = self.t0
        self.noise_floor = max(self.s.trim_threshold * 0.8, 0.003)
        self.stream = sd.InputStream(
            samplerate=self.s.sample_rate,
            channels=self.s.channels,
            dtype="float32",
            device=resolve_input_device(self.s.input_device),
            callback=self._cb,
        )
        self.stream.start()
        self.on = True
        self.log("Recording started")

    def stop(self) -> np.ndarray:
        if not self.on:
            return np.zeros(0, dtype=np.float32)
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.on = False
        with self.lock:
            audio = np.concatenate(self.chunks).astype(np.float32) if self.chunks else np.zeros(0, dtype=np.float32)
        self.log(f"Recording stopped: {len(audio) / self.s.sample_rate:.2f}s")
        return audio

    def duration(self) -> float:
        return time.monotonic() - self.t0 if self.on else 0.0

    def should_stop(self) -> bool:
        return (
            self.on
            and self.s.enable_auto_stop
            and self.duration() >= self.s.min_record_seconds
            and time.monotonic() - self.last_voice >= self.s.auto_stop_silence_seconds
        )

    def meter_snapshot(self) -> tuple[float, float, float, bool, float]:
        with self.lock:
            return self.last_rms, self.last_peak, self.last_threshold, self.last_voice_detected, self.last_updated

    def _cb(self, indata, frames, time_info, status):
        if status:
            self.log(f"Audio status: {status}")
        mono = apply_input_gain(indata[:, 0].copy(), self.s.input_gain)
        mono = apply_noise_gate(mono, self.s.noise_gate_threshold)
        rms = rms_level(mono)
        peak = float(np.max(np.abs(mono))) if mono.size else 0.0
        threshold = max(self.s.trim_threshold, self.s.voice_trigger_min_rms, self.noise_floor * self.s.voice_trigger_ratio)
        voice = rms >= threshold
        with self.lock:
            self.chunks.append(mono)
            self.last_rms = rms
            self.last_peak = peak
            self.last_threshold = threshold
            self.last_voice_detected = voice
            self.last_updated = time.monotonic()
        if voice:
            self.last_voice = time.monotonic()
        else:
            self.noise_floor = (self.noise_floor * 0.96) + (rms * 0.04)


class AlwaysListen:
    def __init__(self, settings: Settings, log, on_audio, target_active):
        self.s = settings
        self.log = log
        self.on_audio = on_audio
        self.target_active = target_active
        self.stream = None
        self.on = False
        self.lock = threading.Lock()
        self.pre = deque()
        self.pre_n = 0
        self.chunks = []
        self.n = 0
        self.trailing_silence = deque()
        self.trailing_silence_n = 0
        self.last_voice = 0.0
        self.noise_floor = max(self.s.trim_threshold * 0.8, 0.003)
        self.voice_hits = 0
        self.last_rms = 0.0
        self.last_peak = 0.0
        self.last_threshold = 0.0
        self.last_voice_detected = False
        self.last_updated = 0.0
        self.tuning_stats = AlwaysListenTuningStats()

    def start(self):
        if self.on:
            return
        self.reset()
        self.stream = sd.InputStream(
            samplerate=self.s.sample_rate,
            channels=self.s.channels,
            dtype="float32",
            device=resolve_input_device(self.s.input_device),
            blocksize=max(int(self.s.sample_rate * 0.06), 512),
            callback=self._cb,
        )
        self.stream.start()
        self.on = True
        self.log("Always-listen started")

    def stop(self):
        if not self.on:
            return
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.on = False
        self.reset()
        self.log("Always-listen stopped")

    def reset(self):
        with self.lock:
            self.pre.clear()
            self.pre_n = 0
            self.chunks = []
            self.n = 0
            self.trailing_silence.clear()
            self.trailing_silence_n = 0
            self.last_voice = 0.0
            self.noise_floor = max(self.s.trim_threshold * 0.8, 0.003)
            self.voice_hits = 0
            self.last_rms = 0.0
            self.last_peak = 0.0
            self.last_threshold = 0.0
            self.last_voice_detected = False
            self.last_updated = 0.0

    def meter_snapshot(self) -> tuple[float, float, float, bool, float]:
        with self.lock:
            return self.last_rms, self.last_peak, self.last_threshold, self.last_voice_detected, self.last_updated

    def tuning_snapshot(self) -> AlwaysListenTuningSuggestion:
        with self.lock:
            stats = AlwaysListenTuningStats(
                observed_blocks=self.tuning_stats.observed_blocks,
                near_threshold_waits=self.tuning_stats.near_threshold_waits,
                weak_voice_starts=self.tuning_stats.weak_voice_starts,
                split_events=self.tuning_stats.split_events,
                finalize_events=self.tuning_stats.finalize_events,
                short_segments=self.tuning_stats.short_segments,
                last_reason=self.tuning_stats.last_reason,
            )
        return recommend_always_listen_tuning(self.s, stats)

    def reset_tuning_stats(self):
        with self.lock:
            self.tuning_stats = AlwaysListenTuningStats()

    def _push_pre(self, mono):
        self.pre.append(mono)
        self.pre_n += len(mono)
        # Always-listen tends to clip weak first syllables, so keep a slightly
        # larger minimum pre-roll even when the configured value is small.
        limit = int(self.s.sample_rate * max(self.s.always_listen_preroll_seconds, 0.45))
        while self.pre and self.pre_n > limit:
            self.pre_n -= len(self.pre.popleft())

    def _tail_padding_seconds(self) -> float:
        # Keep a small amount of post-voice tail so weak final syllables or
        # 받침-like endings are less likely to be cut off with the silence.
        return 0.18

    def _tail_post_silence_seconds(self) -> float:
        return 0.04

    def _finalize(self, drop_trailing: int = 0):
        if not self.chunks:
            return
        kept_chunks = self.chunks[:-drop_trailing] if drop_trailing > 0 else list(self.chunks)
        if not kept_chunks:
            self.chunks = []
            self.n = 0
            self.trailing_silence.clear()
            self.trailing_silence_n = 0
            self.last_voice = 0.0
            return
        segments = [np.concatenate(kept_chunks).astype(np.float32)]
        if drop_trailing > 0:
            trailing_chunks = self.chunks[-drop_trailing:]
            keep_tail_samples = int(self.s.sample_rate * self._tail_padding_seconds())
            if keep_tail_samples > 0 and trailing_chunks:
                trailing_audio = np.concatenate(trailing_chunks).astype(np.float32)
                if trailing_audio.size:
                    activity_threshold = max(float(self.s.trim_threshold), float(self.s.noise_gate_threshold), 0.003)
                    active_indices = np.flatnonzero(np.abs(trailing_audio) >= activity_threshold)
                    if active_indices.size:
                        last_active = int(active_indices[-1]) + 1
                        keep_after = int(self.s.sample_rate * self._tail_post_silence_seconds())
                        start = max(last_active - keep_tail_samples, 0)
                        end = min(last_active + keep_after, trailing_audio.size)
                        tail = trailing_audio[start:end]
                    else:
                        tail = trailing_audio[-keep_tail_samples:]
                    if tail.size:
                        segments.append(tail)
        audio = np.concatenate(segments).astype(np.float32)
        self.chunks = []
        self.n = 0
        self.trailing_silence.clear()
        self.trailing_silence_n = 0
        self.last_voice = 0.0
        self.on_audio(audio, "always_listen")

    def _split_silence_seconds(self) -> float:
        # Keep separation responsive enough for queued async use while still
        # avoiding ultra-short accidental splits.
        return max(float(self.s.auto_stop_silence_seconds), 0.65)

    def _min_split_duration_seconds(self) -> float:
        return max(float(self.s.min_record_seconds), 0.3)

    def _cb(self, indata, frames, time_info, status):
        if status:
            self.log(f"Always-listen audio status: {status}")
        mono = apply_input_gain(indata[:, 0].copy(), self.s.input_gain)
        mono = apply_noise_gate(mono, self.s.noise_gate_threshold)
        if not self.target_active():
            self.reset()
            return
        rms = rms_level(mono)
        peak = float(np.max(np.abs(mono))) if mono.size else 0.0
        threshold = max(self.s.trim_threshold, self.s.voice_trigger_min_rms, self.noise_floor * self.s.voice_trigger_ratio)
        voice = rms >= threshold
        now = time.monotonic()
        with self.lock:
            self.last_rms = rms
            self.last_peak = peak
            self.last_threshold = threshold
            self.last_voice_detected = voice
            self.last_updated = now
            self.tuning_stats.observed_blocks += 1
            if not self.chunks:
                self._push_pre(mono)
                if voice:
                    self.voice_hits += 1
                    if rms <= threshold * 1.12:
                        self.tuning_stats.weak_voice_starts += 1
                else:
                    self.voice_hits = 0
                    self.noise_floor = (self.noise_floor * 0.96) + (rms * 0.04)
                    if rms >= threshold * 0.82:
                        self.tuning_stats.near_threshold_waits += 1
                if self.voice_hits >= max(int(self.s.voice_trigger_consecutive_blocks), 1):
                    self.chunks = list(self.pre)
                    self.n = sum(len(chunk) for chunk in self.chunks)
                    self.pre.clear()
                    self.pre_n = 0
                    self.last_voice = now
                    self.voice_hits = 0
                    self.log(f"Voice detected in target window (rms={rms:.4f}, threshold={threshold:.4f})")
            else:
                sample_rate = max(self.s.sample_rate, 1)
                split_silence = self._split_silence_seconds()
                min_split_duration = self._min_split_duration_seconds()
                if voice:
                    gap_duration = self.trailing_silence_n / sample_rate
                    active_duration = max((self.n - self.trailing_silence_n) / sample_rate, 0.0)
                    if self.trailing_silence and gap_duration >= split_silence and active_duration >= min_split_duration:
                        carry_chunks = list(self.trailing_silence)
                        carry_n = self.trailing_silence_n
                        self.tuning_stats.split_events += 1
                        if active_duration < 0.9:
                            self.tuning_stats.short_segments += 1
                        self.log(
                            f"Always-listen split after {gap_duration:.2f}s silence "
                            f"(active={active_duration:.2f}s)"
                        )
                        self._finalize(drop_trailing=len(carry_chunks))
                        self.chunks = carry_chunks
                        self.n = carry_n
                    self.trailing_silence.clear()
                    self.trailing_silence_n = 0
                    self.chunks.append(mono)
                    self.n += len(mono)
                    self.last_voice = now
                else:
                    self.chunks.append(mono)
                    self.n += len(mono)
                    self.trailing_silence.append(mono)
                    self.trailing_silence_n += len(mono)
                    self.noise_floor = (self.noise_floor * 0.98) + (rms * 0.02)
                total_duration = self.n / sample_rate
                active_duration = max((self.n - self.trailing_silence_n) / sample_rate, 0.0)
                gap_duration = self.trailing_silence_n / sample_rate
                if total_duration >= self.s.max_record_seconds:
                    self._finalize(drop_trailing=len(self.trailing_silence))
                elif (
                    self.trailing_silence
                    and active_duration >= min_split_duration
                    and gap_duration >= split_silence
                ):
                    self.tuning_stats.finalize_events += 1
                    if active_duration < 0.9:
                        self.tuning_stats.short_segments += 1
                    self.log(
                        f"Always-listen finalized after {gap_duration:.2f}s silence "
                        f"(active={active_duration:.2f}s)"
                    )
                    self._finalize(drop_trailing=len(self.trailing_silence))
