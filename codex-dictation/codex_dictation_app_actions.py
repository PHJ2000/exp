from __future__ import annotations

from codex_dictation_app_commands import AppCommandActionsMixin
from codex_dictation_app_output import AppOutputMixin
from codex_dictation_app_status import AppStatusMixin


class AppActionsMixin(AppCommandActionsMixin, AppOutputMixin, AppStatusMixin):
    pass
