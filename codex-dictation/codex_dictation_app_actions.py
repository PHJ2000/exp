from __future__ import annotations

from codex_dictation_app_commands import AppCommandActionsMixin
from codex_dictation_app_output import AppOutputMixin
from codex_dictation_app_status import AppStatusMixin
from codex_dictation_utils import filter_history_entries, format_history_entry, read_history_entries


class AppActionsMixin(AppCommandActionsMixin, AppOutputMixin, AppStatusMixin):
    def _selected_history_entry(self) -> dict | None:
        if not hasattr(self, "history_list"):
            return None
        selection = self.history_list.curselection()
        if not selection:
            return None
        index = int(selection[0])
        if index < 0 or index >= len(self.history_items):
            return None
        return self.history_items[index]

    def refresh_history_browser(self, preserve_selection: bool = True) -> None:
        selected_text = ""
        if preserve_selection:
            selected = self._selected_history_entry()
            selected_text = str(selected.get("text", "")) if selected else ""
        entries = read_history_entries(limit=200)
        self.history_items = filter_history_entries(entries, self.history_query.get(), limit=80)
        self.history_list.delete(0, "end")
        for entry in self.history_items:
            self.history_list.insert("end", format_history_entry(entry))
        if not self.history_items:
            self.history_empty.set("기록이 없습니다.")
            return
        self.history_empty.set(f"{len(self.history_items)}개 기록")
        for index, entry in enumerate(self.history_items):
            if selected_text and entry.get("text") == selected_text:
                self.history_list.selection_set(index)
                self.history_list.see(index)
                return
        self.history_list.selection_set(0)
        self.history_list.see(0)

    def on_history_query_changed(self, *_args) -> None:
        self.refresh_history_browser(preserve_selection=False)

    def load_selected_history(self) -> bool:
        entry = self._selected_history_entry()
        if not entry:
            self.log("History browser: no entry selected")
            return False
        self._update_latest_transcript(str(entry.get("text", "")))
        self.log("History browser: selected entry loaded")
        return True

    def copy_selected_history(self) -> bool:
        entry = self._selected_history_entry()
        if not entry:
            self.log("History browser: no entry selected")
            return False
        self.copy_clip(str(entry.get("text", "")))
        self.log("History browser: selected entry copied")
        return True

    def paste_selected_history(self) -> bool:
        entry = self._selected_history_entry()
        if not entry:
            self.log("History browser: no entry selected")
            return False
        text = str(entry.get("text", ""))
        self._update_latest_transcript(text)
        if not self.emit_text(text):
            self.log("History browser: failed to paste selected entry")
            return False
        self.log("History browser: selected entry pasted")
        return True
