"""SQLite storage for encrypted journal entries."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from journal_app.config import Settings
from journal_app.crypto import decrypt_entry, encrypt_entry
from journal_app.db import Database

MAX_DOC_BYTES = 500_000
MAX_TITLE = 200


class StoreError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def connect(settings: Settings) -> Database:
    conn = Database(settings.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            nonce BLOB NOT NULL,
            ciphertext BLOB NOT NULL
        )
        """
    )
    return conn


def validate_document(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise StoreError("The document must be a TipTap document.")
    raw = _dump(doc)
    if len(raw.encode("utf-8")) > MAX_DOC_BYTES:
        raise StoreError("That entry is too large.")
    return doc


def normalize_title(title: Any) -> str:
    if title is None:
        text = ""
    elif isinstance(title, str):
        text = title.strip()
    else:
        raise StoreError("The title must be text.")
    if len(text) > MAX_TITLE:
        raise StoreError(f"The title must be {MAX_TITLE} characters or fewer.")
    return text or "Untitled"


def create_entry(
    conn: Database,
    dek: bytes,
    *,
    title: str,
    doc: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    title = normalize_title(title)
    doc = validate_document(doc)
    moment = _iso(now or _now())
    entry_id = str(uuid.uuid4())
    nonce, ciphertext = encrypt_entry(dek, entry_id, {"title": title, "doc": doc})
    with conn.lock:
        conn.execute(
            """
            INSERT INTO entries (id, created_at, updated_at, nonce, ciphertext)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entry_id, moment, moment, nonce, ciphertext),
        )
        conn.commit()
    return {"id": entry_id, "title": title, "doc": doc, "created_at": moment, "updated_at": moment}


def update_entry(
    conn: Database,
    dek: bytes,
    entry_id: str,
    *,
    title: str,
    doc: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    row = _row(conn, entry_id)
    title = normalize_title(title)
    doc = validate_document(doc)
    moment = _iso(now or _now())
    nonce, ciphertext = encrypt_entry(dek, entry_id, {"title": title, "doc": doc})
    with conn.lock:
        conn.execute(
            """
            UPDATE entries SET updated_at = ?, nonce = ?, ciphertext = ? WHERE id = ?
            """,
            (moment, nonce, ciphertext, entry_id),
        )
        conn.commit()
    return {
        "id": entry_id,
        "title": title,
        "doc": doc,
        "created_at": row["created_at"],
        "updated_at": moment,
    }


def delete_entry(conn: Database, entry_id: str) -> None:
    _row(conn, entry_id)
    with conn.lock:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.commit()


def get_entry(conn: Database, dek: bytes, entry_id: str) -> dict[str, Any]:
    row = _row(conn, entry_id)
    return _public(dek, row)


def list_entries(
    conn: Database,
    dek: bytes,
    *,
    query: str = "",
) -> list[dict[str, Any]]:
    with conn.lock:
        rows = conn.execute(
            "SELECT id, created_at, updated_at, nonce, ciphertext FROM entries ORDER BY updated_at DESC"
        ).fetchall()
    needle = query.casefold().strip()
    found: list[dict[str, Any]] = []
    for row in rows:
        item = _public(dek, row)
        text = f"{item['title']}\n{plain_text(item['doc'])}"
        if needle and needle not in text.casefold():
            continue
        public = {
            "id": item["id"],
            "title": item["title"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }
        if needle:
            public["snippet"] = snippet(text, needle)
        found.append(public)
    return found


def plain_text(node: Any, depth: int = 0) -> str:
    if depth > 40 or node is None:
        return ""
    if isinstance(node, dict):
        parts: list[str] = []
        if node.get("type") == "text" and isinstance(node.get("text"), str):
            parts.append(node["text"])
        content = node.get("content")
        if isinstance(content, list):
            parts.extend(plain_text(child, depth + 1) for child in content)
        return " ".join(part for part in parts if part)
    if isinstance(node, list):
        return " ".join(plain_text(child, depth + 1) for child in node)
    return ""


def snippet(text: str, needle: str, radius: int = 48) -> str:
    flat = " ".join(text.split())
    index = flat.casefold().find(needle)
    if index < 0:
        return flat[: radius * 2]
    start = max(0, index - radius)
    end = min(len(flat), index + len(needle) + radius)
    chunk = flat[start:end]
    if start > 0:
        chunk = "…" + chunk
    if end < len(flat):
        chunk = chunk + "…"
    return chunk


def _public(dek: bytes, row) -> dict[str, Any]:
    payload = decrypt_entry(dek, row["id"], row["nonce"], row["ciphertext"])
    return {
        "id": row["id"],
        "title": normalize_title(payload.get("title")),
        "doc": payload.get("doc") if isinstance(payload.get("doc"), dict) else {"type": "doc", "content": []},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row(conn: Database, entry_id: str):
    with conn.lock:
        row = conn.execute(
            "SELECT id, created_at, updated_at, nonce, ciphertext FROM entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
    if row is None:
        raise StoreError("No entry with that id.", 404)
    return row


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _dump(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False)
