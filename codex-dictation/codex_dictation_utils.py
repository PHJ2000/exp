from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from codex_dictation_settings import HISTORY_PATH, LOG_PATH, ensure_runtime_paths


def append_app_log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        ensure_runtime_paths()
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        pass


def append_history(text: str, meta: dict) -> None:
    payload = {"timestamp": datetime.now().isoformat(timespec="seconds"), "text": text, **meta}
    ensure_runtime_paths()
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_history_entries(path: Path | None = None, limit: int | None = None) -> list[dict]:
    target = path or HISTORY_PATH
    if not target.exists():
        return []
    entries: list[dict] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            text = normalize_text(str(payload.get("text", "")))
            if not text:
                continue
            entries.append({"timestamp": str(payload.get("timestamp", "")), "text": text, **payload})
    entries.reverse()
    if limit is not None and limit > 0:
        return entries[:limit]
    return entries


def filter_history_entries(entries: list[dict], query: str, limit: int | None = None) -> list[dict]:
    normalized_query = normalize_text(query).lower()
    if normalized_query:
        filtered = [entry for entry in entries if normalized_query in normalize_text(str(entry.get("text", ""))).lower()]
    else:
        filtered = list(entries)
    if limit is not None and limit > 0:
        return filtered[:limit]
    return filtered


def format_history_entry(entry: dict, limit: int = 72) -> str:
    timestamp = str(entry.get("timestamp", "")).replace("T", " ")[:19]
    text = short_log_text(str(entry.get("text", "")), limit=limit)
    return f"{timestamp} | {text}" if timestamp else text


def command_key(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch not in " \t\r\n.,!?;:\"'")


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\r", " ").replace("\n", " ").split()).strip()


def short_log_text(text: str, limit: int = 80) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
