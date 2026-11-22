"""Start the journal unit after setup. Tests pass a fake runner."""

from __future__ import annotations

import subprocess

from journal_app.config import Settings


class ServiceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def start_journal(settings: Settings, run=subprocess.run) -> None:
    if not settings.enable_systemctl:
        return
    result = run(
        ["systemctl", "enable", "--now", settings.web_unit],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "systemctl failed").strip()
        raise ServiceError(detail.splitlines()[-1][:300])
