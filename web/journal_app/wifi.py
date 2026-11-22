"""NetworkManager helpers for the touchscreen setup.

The Wi-Fi passphrase is written to a passwd-file and handed to
``nmcli connection up``. It is not placed on the nmcli command line.
NetworkManager is configured, in the image, to use iwd as its Wi-Fi
backend. iwd keeps the regulatory country; NetworkManager keeps the
connection.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

CON_NAME = "secure-journal-wifi"


class WifiError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def split_nmcli(line: str) -> list[str]:
    """Split an ``nmcli -t`` line. Colons inside fields are escaped as \\:."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.rstrip("\n"):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def parse_wifi_list(text: str) -> list[dict]:
    by_ssid: dict[str, dict] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = split_nmcli(line)
        if len(fields) < 4:
            continue
        in_use, ssid, signal, security = fields[0], fields[1], fields[2], fields[3]
        ssid = ssid.strip()
        if not ssid:
            continue
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        row = {
            "ssid": ssid,
            "signal": strength,
            "security": security.strip(),
            "in_use": in_use.strip() == "*",
        }
        previous = by_ssid.get(ssid)
        if previous is None or row["signal"] > previous["signal"] or row["in_use"]:
            if previous and previous["in_use"]:
                row["in_use"] = True
            by_ssid[ssid] = row
    rows = list(by_ssid.values())
    rows.sort(key=lambda row: (row["in_use"], row["signal"]), reverse=True)
    return rows


def render_iwd_conf(existing: str, country: str) -> str:
    country = _country(country)
    lines = existing.splitlines()
    output: list[str] = []
    in_general = False
    replaced = False
    saw_general = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_general and not replaced:
                output.append(f"Country={country}")
                replaced = True
            in_general = stripped.lower() == "[general]"
            if in_general:
                saw_general = True
            output.append(line)
            continue
        if in_general and stripped.lower().startswith("country="):
            output.append(f"Country={country}")
            replaced = True
            continue
        output.append(line)
    if in_general and not replaced:
        output.append(f"Country={country}")
        replaced = True
    if not saw_general:
        block = ["[General]", f"Country={country}", "EnableNetworkConfiguration=false"]
        if output and output[-1] != "":
            output.append("")
        output.extend(block)
    text = "\n".join(output).strip() + "\n"
    return text


def set_country(country: str, *, conf_path: Path, run=subprocess.run) -> str:
    country = _country(country)
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    existing = conf_path.read_text(encoding="utf-8") if conf_path.is_file() else ""
    conf_path.write_text(render_iwd_conf(existing, country), encoding="utf-8")
    os.chmod(conf_path, 0o644)
    _run(run, ["iw", "reg", "set", country], check=False)
    _run(run, ["nmcli", "radio", "wifi", "on"])
    return country


def scan(*, run=subprocess.run) -> list[dict]:
    result = _run(
        run,
        ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"],
    )
    return parse_wifi_list(result.stdout or "")


def connect(ssid: str, password: str, *, iface: str, run=subprocess.run) -> None:
    ssid = ssid.strip()
    if not ssid or "\n" in ssid or "\r" in ssid:
        raise WifiError("Enter the network name.")
    if "\n" in password or "\r" in password:
        raise WifiError("The Wi-Fi password cannot contain a newline.")
    _run(run, ["nmcli", "connection", "delete", CON_NAME], check=False)
    if password:
        _run(
            run,
            [
                "nmcli",
                "connection",
                "add",
                "type",
                "wifi",
                "con-name",
                CON_NAME,
                "ifname",
                iface,
                "ssid",
                ssid,
                "wifi-sec.key-mgmt",
                "wpa-psk",
                "wifi-sec.psk-flags",
                "1",
            ],
        )
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        path = handle.name
        try:
            os.chmod(path, 0o600)
            handle.write(f"802-11-wireless-security.psk:{password}\n")
            handle.close()
            _run(run, ["nmcli", "-w", "40", "connection", "up", CON_NAME, "passwd-file", path])
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    else:
        _run(
            run,
            [
                "nmcli",
                "connection",
                "add",
                "type",
                "wifi",
                "con-name",
                CON_NAME,
                "ifname",
                iface,
                "ssid",
                ssid,
            ],
        )
        _run(run, ["nmcli", "-w", "40", "connection", "up", CON_NAME])


def _country(country: str) -> str:
    code = country.strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise WifiError("The Wi-Fi country must be two letters, for example US.")
    return code


class _Result:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _run(run, argv: list[str], check: bool = True):
    result = run(argv, check=False, capture_output=True, text=True)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise WifiError(detail.splitlines()[-1][:300])
    return result
