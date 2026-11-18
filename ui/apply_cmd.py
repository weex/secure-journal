"""Build the sudo invocation for setup-apply.sh.

The secrets travel on stdin. They are not placed in the argument list.
"""

from __future__ import annotations


def apply_invocation(script: str, needs_password: bool) -> list[str]:
    if needs_password:
        return ["sudo", "-k", "-S", "-p", "", script, "apply"]
    return ["sudo", "-n", script, "apply"]


def apply_stdin(
    needs_password: bool,
    current: str,
    new_login: str,
    disk: str,
    target: str,
    confirm: str,
) -> str:
    for label, value in (
        ("current password", current),
        ("login password", new_login),
        ("disk passphrase", disk),
        ("target", target),
        ("confirmation", confirm),
    ):
        if "\n" in value or "\r" in value:
            raise ValueError(f"{label} must be a single line")
    body = f"{new_login}\n{disk}\n{target}\n{confirm}\n"
    if needs_password:
        return f"{current}\n{body}"
    return body
