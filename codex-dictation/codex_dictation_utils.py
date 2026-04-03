from __future__ import annotations

import json
from datetime import datetime

from codex_dictation_settings import HISTORY_PATH, LOG_PATH


def append_app_log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        pass


def append_history(text: str, meta: dict) -> None:
    payload = {"timestamp": datetime.now().isoformat(timespec="seconds"), "text": text, **meta}
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def command_key(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch not in " \t\r\n.,!?;:\"'")


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\r", " ").replace("\n", " ").split()).strip()


def short_log_text(text: str, limit: int = 80) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
