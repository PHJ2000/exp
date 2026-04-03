from __future__ import annotations

import argparse
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from codex_dictation_app import App
from codex_dictation_diagnostics import doctor
from codex_dictation_settings import APP_NAME, load_settings, normalize_language_value
from codex_dictation_targeting import acquire_single_instance, fg_info
from codex_dictation_transcription import transcribe_file
from codex_dictation_utils import append_app_log


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--transcribe-file", type=Path)
    parser.add_argument("--model", type=str)
    parser.add_argument("--language", type=str)
    parser.add_argument("--show-window", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    if args.model:
        settings.whisper_model = args.model
    if args.language is not None:
        settings.language = normalize_language_value(args.language)
    if args.doctor:
        print(doctor(settings))
        return
    if args.transcribe_file:
        print(transcribe_file(args.transcribe_file, settings))
        return
    if not acquire_single_instance():
        append_app_log("Another instance is already running; exiting duplicate launch")
        return
    launch_target = fg_info()
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except Exception:
        pass
    App(root, launch_target=launch_target, show_window=args.show_window)
    root.mainloop()


if __name__ == "__main__":
    main()
