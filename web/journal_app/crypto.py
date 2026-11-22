"""Encryption at rest.

The security password is checked with an Argon2id password hash. A second
Argon2id derivation, with its own salt, wraps a random 32-byte data key.
Entries are AES-GCM under that data key. The password hash is not the
wrapping key, so the two jobs stay separate.

The wrapped key and the ciphertext both sit on the SD card. Reading an
entry still takes the password, which is only available after login, and
the unwrapped key is kept in process memory for that session. This is not
full-disk encryption: someone who can rewrite the card can replace this
program and capture the password on the next login.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

WRAP_AAD = b"secure-journal-dek-v1"
ENTRY_AAD_PREFIX = b"secure-journal-entry-v1:"


def b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def new_dek() -> bytes:
    return os.urandom(32)


def derive_wrap_key(
    password: str,
    salt: bytes,
    *,
    time_cost: int,
    memory_cost: int,
    parallelism: int,
) -> bytes:
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=32,
        type=Type.ID,
    )


def wrap_dek(
    password: str,
    dek: bytes,
    *,
    time_cost: int,
    memory_cost: int,
    parallelism: int,
) -> dict[str, Any]:
    salt = os.urandom(16)
    key = derive_wrap_key(
        password,
        salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
    )
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, dek, WRAP_AAD)
    return {
        "kdf": "argon2id",
        "time_cost": time_cost,
        "memory_cost": memory_cost,
        "parallelism": parallelism,
        "salt": b64encode(salt),
        "nonce": b64encode(nonce),
        "ciphertext": b64encode(ciphertext),
    }


def unwrap_dek(password: str, wrap: dict[str, Any]) -> bytes:
    key = derive_wrap_key(
        password,
        b64decode(wrap["salt"]),
        time_cost=int(wrap["time_cost"]),
        memory_cost=int(wrap["memory_cost"]),
        parallelism=int(wrap["parallelism"]),
    )
    return AESGCM(key).decrypt(b64decode(wrap["nonce"]), b64decode(wrap["ciphertext"]), WRAP_AAD)


def encrypt_entry(dek: bytes, entry_id: str, payload: dict[str, Any]) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ciphertext = AESGCM(dek).encrypt(nonce, body, _entry_aad(entry_id))
    return nonce, ciphertext


def decrypt_entry(dek: bytes, entry_id: str, nonce: bytes, ciphertext: bytes) -> dict[str, Any]:
    body = AESGCM(dek).decrypt(nonce, ciphertext, _entry_aad(entry_id))
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("entry payload is not an object")
    return data


def _entry_aad(entry_id: str) -> bytes:
    return ENTRY_AAD_PREFIX + entry_id.encode("utf-8")
