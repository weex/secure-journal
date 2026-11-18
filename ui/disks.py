"""Choose a spare disk for the LUKS copy.

In-place encryption is deliberately not offered. The system is running from
the card that would have to be rewritten, and a failed conversion would leave
no bootable copy. The boot ROM also cannot unlock LUKS, so any layout still
keeps a plain FAT boot partition. luks-convert.sh already copies onto a
second disk and leaves the live one alone.
"""

from __future__ import annotations

IN_PLACE_REASON = (
    "Encrypting the card this Pi booted from is not implemented. "
    "The system would have to rewrite the disk it is running from, and a "
    "failed conversion would leave no bootable copy. Use a spare disk. "
    "The FAT boot partition stays unencrypted either way, because the Pi "
    "boot ROM cannot unlock LUKS."
)


def parse_lsblk_pairs(text: str) -> list[dict]:
    """Parse `lsblk -P` lines. Values are double-quoted."""
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        row: dict[str, str] = {}
        rest = line.strip()
        while rest:
            key, sep, rest = rest.partition("=")
            if not sep or not rest.startswith('"'):
                break
            rest = rest[1:]
            value: list[str] = []
            escaped = False
            for index, char in enumerate(rest):
                if escaped:
                    value.append(char)
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    row[key] = "".join(value)
                    rest = rest[index + 1 :].lstrip()
                    break
                else:
                    value.append(char)
            else:
                break
        if row:
            rows.append(row)
    return rows


def spare_candidates(rows: list[dict], source_name: str, *, allow_loop: bool = False) -> list[dict]:
    """Whole disks that are not the live disk and have nothing mounted."""
    source = source_name.removeprefix("/dev/")
    mounted: set[str] = set()
    for row in rows:
        mount = row.get("MOUNTPOINT") or row.get("MOUNTPOINTS") or ""
        if not mount:
            continue
        name = row.get("NAME", "")
        parent = row.get("PKNAME") or name
        mounted.add(name)
        mounted.add(parent)

    chosen: list[dict] = []
    for row in rows:
        kind = row.get("TYPE", "")
        name = row.get("NAME", "")
        if kind == "loop" and not allow_loop:
            continue
        if kind not in {"disk", "loop"}:
            continue
        if not name or name == source:
            continue
        if name in mounted:
            continue
        chosen.append(
            {
                "name": name,
                "path": f"/dev/{name}",
                "size": row.get("SIZE", ""),
                "tran": row.get("TRAN", ""),
            }
        )
    return chosen


def erase_confirmation(path: str) -> str:
    return f"ERASE {path}"


def confirmation_matches(path: str, typed: str) -> bool:
    return typed == erase_confirmation(path)
