from __future__ import annotations

from pathlib import Path

import pytest

from journal_app.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        secure_cookies=True,
        argon_time=1,
        argon_memory=8192,
        argon_parallelism=1,
        enable_systemctl=False,
        dev=True,
        web_port=443,
        owner="",
    )
