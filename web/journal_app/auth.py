"""Password hash, session cookies, and login rate limiting."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from journal_app.config import Settings
from journal_app.crypto import new_dek, unwrap_dek, wrap_dek
from journal_app.db import Database

COOKIE = "sj_session"
ATTEMPT_LIMIT = 8
ATTEMPT_WINDOW = timedelta(minutes=15)


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Session:
    token_hash: str
    dek: bytes


class KeyCache:
    """Unwrapped data keys, keyed by the hash of the session token.

    A process restart drops the cache. Sessions are cleared at startup so a
    cookie from before the restart cannot be paired with a missing key.
    """

    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def put(self, token_hash: str, dek: bytes) -> None:
        with self._lock:
            self._keys[token_hash] = dek

    def get(self, token_hash: str) -> bytes | None:
        with self._lock:
            return self._keys.get(token_hash)

    def drop(self, token_hash: str) -> None:
        with self._lock:
            self._keys.pop(token_hash, None)

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()


def hasher_for(settings: Settings) -> PasswordHasher:
    return PasswordHasher(
        time_cost=settings.argon_time,
        memory_cost=settings.argon_memory,
        parallelism=settings.argon_parallelism,
        hash_len=32,
        salt_len=16,
    )


def provision_password(settings: Settings, password: str) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(settings.data_dir, 0o750)
    record = {
        "version": 1,
        "password_hash": hasher_for(settings).hash(password),
        "wrap": wrap_dek(
            password,
            new_dek(),
            time_cost=settings.argon_time,
            memory_cost=settings.argon_memory,
            parallelism=settings.argon_parallelism,
        ),
    }
    path = settings.auth_path
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.chmod(tmp, 0o640)
    tmp.replace(path)


def load_auth(settings: Settings) -> dict[str, Any]:
    path = settings.auth_path
    if not path.is_file():
        raise AuthError("Journal is not set up.", 503)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "password_hash" not in data or "wrap" not in data:
        raise AuthError("Password record is unreadable.", 500)
    return data


def verify_password(settings: Settings, password: str) -> bytes:
    record = load_auth(settings)
    try:
        hasher_for(settings).verify(record["password_hash"], password)
    except VerifyMismatchError as exc:
        raise AuthError("Wrong password.", 401) from exc
    try:
        return unwrap_dek(password, record["wrap"])
    except Exception as exc:
        raise AuthError("Could not unlock the journal.", 401) from exc


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def open_auth_db(settings: Settings) -> Database:
    conn = Database(settings.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY,
            ip TEXT NOT NULL,
            at TEXT NOT NULL
        )
        """
    )
    return conn


def clear_sessions(conn: Database) -> None:
    with conn.lock:
        conn.execute("DELETE FROM sessions")
        conn.commit()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def login_locked(conn: Database, ip: str, now: datetime | None = None) -> bool:
    moment = now or _now()
    cutoff = _iso(moment - ATTEMPT_WINDOW)
    with conn.lock:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM login_attempts WHERE ip = ? AND at >= ?",
            (ip, cutoff),
        ).fetchone()
    return int(row["n"]) >= ATTEMPT_LIMIT


def record_failure(conn: Database, ip: str, now: datetime | None = None) -> None:
    with conn.lock:
        conn.execute(
            "INSERT INTO login_attempts (ip, at) VALUES (?, ?)",
            (ip, _iso(now or _now())),
        )
        conn.commit()


def clear_failures(conn: Database, ip: str) -> None:
    with conn.lock:
        conn.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
        conn.commit()


def start_session(
    conn: Database,
    cache: KeyCache,
    dek: bytes,
    *,
    hours: int,
    now: datetime | None = None,
) -> str:
    moment = now or _now()
    token = secrets.token_urlsafe(32)
    digest = token_hash(token)
    with conn.lock:
        conn.execute(
            "INSERT INTO sessions (token_hash, created_at, expires_at) VALUES (?, ?, ?)",
            (digest, _iso(moment), _iso(moment + timedelta(hours=hours))),
        )
        conn.commit()
    cache.put(digest, dek)
    return token


def end_session(conn: Database, cache: KeyCache, token: str) -> None:
    digest = token_hash(token)
    with conn.lock:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
        conn.commit()
    cache.drop(digest)


def read_session(
    conn: Database,
    cache: KeyCache,
    token: str,
    *,
    now: datetime | None = None,
) -> Session | None:
    if not token:
        return None
    digest = token_hash(token)
    with conn.lock:
        row = conn.execute(
            "SELECT expires_at FROM sessions WHERE token_hash = ?",
            (digest,),
        ).fetchone()
        if row is None:
            return None
        expires = datetime.fromisoformat(row["expires_at"])
        if expires <= (now or _now()):
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
            conn.commit()
            cache.drop(digest)
            return None
    dek = cache.get(digest)
    if dek is None:
        return None
    return Session(token_hash=digest, dek=dek)


def cookie_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "key": COOKIE,
        "httponly": True,
        "secure": settings.secure_cookies,
        "samesite": "strict",
        "path": "/",
        "max_age": settings.session_hours * 3600,
    }
