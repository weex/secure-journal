"""One SQLite connection shared across the request threads."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.raw = sqlite3.connect(path, check_same_thread=False)
        self.raw.row_factory = sqlite3.Row
        self.lock = threading.RLock()

    def execute(self, sql: str, params: tuple = ()):
        return self.raw.execute(sql, params)

    def commit(self) -> None:
        self.raw.commit()
