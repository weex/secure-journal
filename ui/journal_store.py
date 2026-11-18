"""Markdown journal files.

The layout matches scripts/journal: ~/journal/YYYY/MM/YYYY-MM-DD.md, the
directory mode 0700, the file mode 0600. This is not a second layer of
encryption. The protection is the LUKS root the file lives on.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path


def journal_root(home: Path | None = None) -> Path:
    override = os.environ.get("JOURNAL_DIR")
    if override:
        return Path(override)
    if home is None:
        home = Path.home()
    return home / "journal"


def entry_path(root: Path, day: date) -> Path:
    return root / f"{day:%Y}" / f"{day:%m}" / f"{day:%Y-%m-%d}.md"


def _tighten(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)


def ensure_entry(root: Path, day: date | None = None) -> Path:
    if day is None:
        day = date.today()
    path = entry_path(root, day)
    _tighten(root)
    _tighten(path.parent.parent)
    _tighten(path.parent)
    if not path.exists():
        path.write_text(f"# {day:%Y-%m-%d}\n\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def list_entries(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.glob("*/*/*.md"), reverse=True)


def read_entry(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_entry(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def root_source_from_mounts(text: str) -> str:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "/":
            return parts[0]
    return ""


def root_is_encrypted(source: str) -> bool:
    return source.startswith("/dev/mapper/")


def current_root_is_encrypted() -> bool:
    try:
        mounts = Path("/proc/mounts").read_text(encoding="utf-8")
    except OSError:
        return False
    return root_is_encrypted(root_source_from_mounts(mounts))
