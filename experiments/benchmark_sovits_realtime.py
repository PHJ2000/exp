from __future__ import annotations

import json
import logging
import math
import statistics
import time
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch

from so_vits_svc_fork.inference.core import RealtimeVC2, Svc


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "pinkie" / "G_166400.pth"
CONFIG_PATH = ROOT / "models" / "pinkie" / "config.json"
SOURCE_DIR = ROOT / "external" / "so-vits-svc-fork" / "tests" / "dataset_raw" / "test"
GENERATED_DIR = ROOT / "inputs"
RESULT_PATH = ROOT / "experiments" / "results_sovits_realtime.json"
OUTPUT_DIR = ROOT / "outputs"


def build_test_clip(target_seconds: float, sample_rate: int, *, gap_seconds: float = 0.2) -> Path:
    files = sorted(SOURCE_DIR.glob("LJ*.wav"))
    if not files:
        raise FileNotFoundError(f"No source wav files found in {SOURCE_DIR}")

    pieces: list[np.ndarray] = []
    total_samples = 0
    gap = np.zeros(int(sample_rate * gap_seconds), dtype=np.float32)
    target_samples = int(target_seconds * sample_rate)
    index = 0

    while total_samples < target_samples:
        audio, _ = librosa.load(files[index % len(files)], sr=sample_rate, mono=True)
        pieces.append(audio.astype(np.float32))
        total_samples += len(audio)
        if total_samples < target_samples:
            pieces.append(gap)
            total_samples += len(gap)
        index += 1

    merged = np.concatenate(pieces)[:target_samples]
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GENERATED_DIR / f"benchmark_{target_seconds:.1f}s.wav"
    sf.write(out_path, merged, sample_rate)
    return out_path


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.nan
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def run_offline_case(
    svc_model: Svc,
    audio: np.ndarray,
    duration_seconds: float,
    *,
    speaker: str,
) -> dict[str, float]:
    torch.cuda.synchronize()
    started = time.perf_counter()
    converted = svc_model.infer_silence(
        audio,
        speaker=speaker,
        transpose=0,
        auto_predict_f0=False,
        cluster_infer_ratio=0,
        noise_scale=0.4,
        f0_method="dio",
        db_thresh=-40,
        pad_seconds=0.5,
        chunk_seconds=0.5,
        absolute_thresh=False,
        max_chunk_seconds=40,
    )
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    return {
        "input_seconds": duration_seconds,
        "output_seconds": len(converted) / svc_model.target_sample,
        "elapsed_seconds": elapsed,
        "rtf": elapsed / duration_seconds,
    }


def run_streaming_case(
    svc_model: Svc,
    audio: np.ndarray,
    *,
    speaker: str,
    block_seconds: float,
) -> dict[str, float | int]:
    realtime = RealtimeVC2(svc_model)
    block_samples = int(block_seconds * svc_model.target_sample)
    block_runtimes: list[float] = []
    over_realtime = 0

    for start in range(0, len(audio), block_samples):
        block = audio[start : start + block_samples]
        if len(block) < block_samples:
            block = np.pad(block, (0, block_samples - len(block)))
        torch.cuda.synchronize()
        started = time.perf_counter()
        _ = realtime.process(
            input_audio=block.astype(np.float32),
            speaker=speaker,
            transpose=0,
            cluster_infer_ratio=0,
            auto_predict_f0=False,
            noise_scale=0.4,
            f0_method="dio",
            db_thresh=-40,
            chunk_seconds=0.5,
        )
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        rtf = elapsed / block_seconds
        block_runtimes.append(rtf)
        if rtf > 1.0:
            over_realtime += 1

    return {
        "block_seconds": block_seconds,
        "blocks": len(block_runtimes),
        "mean_rtf": statistics.fmean(block_runtimes),
        "median_rtf": statistics.median(block_runtimes),
        "p95_rtf": percentile(block_runtimes, 0.95),
        "max_rtf": max(block_runtimes),
        "blocks_over_1x": over_realtime,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not MODEL_PATH.exists():
        raise FileNotFoundError(MODEL_PATH)
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)

    svc_model = Svc(
        net_g_path=MODEL_PATH.as_posix(),
        config_path=CONFIG_PATH.as_posix(),
        device="cuda:0" if torch.cuda.is_available() else "cpu",
    )

    speaker = "Pinkie {neutral}"
    sample_rate = svc_model.target_sample
    durations = [1.0, 3.0, 6.0, 12.0]
    input_paths = [build_test_clip(seconds, sample_rate) for seconds in durations]

    # Warm the model once to separate cold-start from steady-state behavior.
    warm_audio = np.zeros(sample_rate, dtype=np.float32)
    _ = svc_model.infer(
        speaker=speaker,
        transpose=0,
        audio=warm_audio,
        cluster_infer_ratio=0,
        auto_predict_f0=False,
        noise_scale=0.4,
        f0_method="dio",
    )

    offline_results = []
    streaming_results = []
    for input_path, duration_seconds in zip(input_paths, durations):
        audio, _ = librosa.load(input_path, sr=sample_rate, mono=True)
        offline = run_offline_case(svc_model, audio, duration_seconds, speaker=speaker)
        offline["input_path"] = input_path.as_posix()
        offline_results.append(offline)

        if math.isclose(duration_seconds, 12.0):
            streaming_results.append(
                {
                    "input_path": input_path.as_posix(),
                    **run_streaming_case(svc_model, audio, speaker=speaker, block_seconds=0.5),
                }
            )
            streaming_results.append(
                {
                    "input_path": input_path.as_posix(),
                    **run_streaming_case(svc_model, audio, speaker=speaker, block_seconds=1.0),
                }
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "environment": {
            "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
            "model_path": MODEL_PATH.as_posix(),
            "config_path": CONFIG_PATH.as_posix(),
            "speaker": speaker,
            "sample_rate": sample_rate,
        },
        "offline_after_warmup": offline_results,
        "streaming_realtimevc2_after_warmup": streaming_results,
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
