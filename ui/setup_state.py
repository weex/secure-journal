"""Wizard completion stamp.

The file lives in the admin user's home, which luks-convert.sh copies onto
the new card. The wizard writes it and flushes it before starting the copy,
so the encrypted card does not open the wizard again. If the copy fails, the
wizard deletes the stamp on the card it is still running from.
"""

from __future__ import annotations

import os
from pathlib import Path


def stamp_path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config) if config else Path.home() / ".config"
    return base / "secure-journal" / "setup-complete"


def write_stamp(status: str) -> None:
    path = stamp_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"status={status}\n", encoding="utf-8")
    os.chmod(path, 0o600)
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def clear_stamp() -> None:
    path = stamp_path()
    path.unlink(missing_ok=True)


def setup_is_complete() -> bool:
    return stamp_path().is_file()
