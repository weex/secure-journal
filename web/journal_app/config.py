"""Runtime settings. Production values are the defaults; tests pass a Settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    setup_host: str = "127.0.0.1"
    setup_port: int = 8080
    web_host: str = "0.0.0.0"
    web_port: int = 443
    secure_cookies: bool = True
    session_hours: int = 12
    argon_time: int = 2
    argon_memory: int = 65536
    argon_parallelism: int = 1
    wifi_iface: str = "wlan0"
    enable_systemctl: bool = True
    web_unit: str = "secure-journal.service"
    owner: str = ""
    dev: bool = False

    @property
    def auth_path(self) -> Path:
        return self.data_dir / "auth.json"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "journal.db"

    @property
    def cert_path(self) -> Path:
        return self.data_dir / "tls" / "cert.pem"

    @property
    def key_path(self) -> Path:
        return self.data_dir / "tls" / "key.pem"

    @classmethod
    def from_env(cls) -> Settings:
        dev = _flag("JOURNAL_DEV")
        data = os.environ.get("JOURNAL_DATA_DIR")
        if data:
            data_dir = Path(data)
        elif dev:
            data_dir = Path.cwd() / "data"
        else:
            data_dir = Path("/var/lib/secure-journal")
        return cls(
            data_dir=data_dir,
            setup_host=os.environ.get("JOURNAL_SETUP_HOST", "127.0.0.1"),
            setup_port=int(os.environ.get("JOURNAL_SETUP_PORT", "8080")),
            web_host=os.environ.get("JOURNAL_WEB_HOST", "127.0.0.1" if dev else "0.0.0.0"),
            web_port=int(os.environ.get("JOURNAL_WEB_PORT", "8000" if dev else "443")),
            secure_cookies=not dev and not _flag("JOURNAL_INSECURE_COOKIES"),
            session_hours=int(os.environ.get("JOURNAL_SESSION_HOURS", "12")),
            argon_time=int(os.environ.get("JOURNAL_ARGON_TIME", "2")),
            argon_memory=int(os.environ.get("JOURNAL_ARGON_MEMORY", "65536")),
            argon_parallelism=int(os.environ.get("JOURNAL_ARGON_PARALLELISM", "1")),
            wifi_iface=os.environ.get("JOURNAL_WIFI_IFACE", "wlan0"),
            enable_systemctl=not dev and not _flag("JOURNAL_DISABLE_SYSTEMCTL"),
            web_unit=os.environ.get("JOURNAL_WEB_UNIT", "secure-journal.service"),
            owner=os.environ.get("JOURNAL_OWNER", "" if dev else "journal"),
            dev=dev,
        )


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
