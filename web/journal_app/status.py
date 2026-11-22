"""Hostname and addresses shown on the touchscreen after setup."""

from __future__ import annotations

import socket
import subprocess


def hostname() -> str:
    name = socket.gethostname().split(".")[0].strip()
    return name or "journal"


def _addr_text(run) -> str:
    try:
        result = run(["ip", "-4", "-o", "addr", "show"], check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def ipv4_addresses(run=subprocess.run) -> list[str]:
    found: list[str] = []
    for line in _addr_text(run).splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[2] != "inet":
            continue
        iface = parts[1]
        if iface == "lo" or iface.startswith("lo"):
            continue
        address = parts[3].split("/")[0]
        if address not in found:
            found.append(address)
    return found


def ethernet_up(run=subprocess.run) -> bool:
    for line in _addr_text(run).splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[2] != "inet":
            continue
        iface = parts[1]
        if iface == "lo" or iface.startswith(("wlan", "wl")):
            continue
        return True
    return False


def journal_url(name: str, port: int) -> str:
    base = f"https://{name}.local"
    if port == 443:
        return base
    return f"{base}:{port}"
