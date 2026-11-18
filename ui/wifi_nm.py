"""Parse `nmcli -t` Wi-Fi listings.

nmcli separates fields with colons and escapes a colon or a backslash in a
value with a backslash. Hidden networks have an empty SSID and are dropped.
"""

from __future__ import annotations


def split_nmcli(line: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            buf.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    parts.append("".join(buf))
    return parts


def parse_wifi_list(text: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = split_nmcli(line.rstrip("\n"))
        while len(fields) < 4:
            fields.append("")
        ssid = fields[1].strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        signal_text = fields[2].strip()
        try:
            signal = int(signal_text)
        except ValueError:
            signal = 0
        rows.append(
            {
                "in_use": fields[0].strip() == "*",
                "ssid": ssid,
                "signal": signal,
                "security": fields[3].strip() or "open",
            }
        )
    rows.sort(key=lambda row: row["signal"], reverse=True)
    return rows
