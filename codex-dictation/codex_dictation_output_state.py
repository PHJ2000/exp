from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutputState:
    last_emitted: str = ""
    last_emitted_context: Any = None
    last_submitted: bool = False
    pending_text: str = ""
    pending_segments: list[str] = field(default_factory=list)
    pending_context: Any = None
    pending_context_mismatch_since: float = 0.0
    output_grace_until: float = 0.0
    last_paste_payload: str = ""
    last_replace_state: dict[str, Any] | None = None

    def clear_pending(self, *, clear_last_emitted: bool = False, clear_last_submitted: bool = False) -> None:
        self.pending_text = ""
        self.pending_segments.clear()
        self.pending_context = None
        if clear_last_emitted:
            self.last_emitted = ""
            self.last_emitted_context = None
        if clear_last_submitted:
            self.last_submitted = False

    def note_output(self, payload: str, *, sent_enter: bool, target_context: Any) -> None:
        self.last_emitted = payload
        self.last_emitted_context = target_context
        self.last_submitted = bool(sent_enter)
        if sent_enter:
            self.clear_pending()
            return
        if target_context and self.pending_context and target_context != self.pending_context and self.pending_text:
            self.pending_text = ""
            self.pending_segments.clear()
        self.pending_context = target_context
        self.pending_text = f"{self.pending_text}{payload}"
        self.pending_segments.append(payload)

    def clear_after_submit(self) -> None:
        self.last_submitted = True
        self.pending_text = ""
        self.pending_segments.clear()
        self.pending_context = None

    def reset_context_mismatch(self) -> None:
        self.pending_context_mismatch_since = 0.0
