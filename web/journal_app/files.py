"""Give the journal account ownership of files the setup server wrote as root."""

from __future__ import annotations

import grp
import os
import pwd
from pathlib import Path


def adopt_tree(path: Path, owner: str) -> None:
    if not owner or not path.exists():
        return
    try:
        uid = pwd.getpwnam(owner).pw_uid
        gid = grp.getgrnam(owner).gr_gid
    except KeyError:
        return
    os.chown(path, uid, gid)
    if path.is_dir():
        for child in path.rglob("*"):
            os.chown(child, uid, gid)
