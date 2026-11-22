"""Local passphrase policy for the setup wizard.

The gate is this module, not a network call and not libpwquality, so the
same rules run in the tests and on the Pi. libpwquality is still installed
by harden.sh and may reject a password the local list has never seen; the
wizard shows that error if chpasswd returns it.

A passphrase is one line. Newlines are rejected by the scripts that read
stdin, not by this scorer.
"""

from __future__ import annotations

COMMON = frozenset(
    {
        "password",
        "password1",
        "raspberry",
        "raspberrypi",
        "journal",
        "changeme",
        "letmein",
        "qwertyuiop",
        "qwertyuiopasdf",
        "12345678901234",
        "123456789012345",
        "admin",
        "administrator",
        "iloveyou",
        "welcome",
        "passw0rd",
    }
)


def assess(secret: str, username: str = "") -> dict:
    reasons: list[str] = []
    length = len(secret)
    if length < 14:
        reasons.append(f"{length} characters; need at least 14")

    classes = 0
    if any("a" <= c <= "z" for c in secret):
        classes += 1
    if any("A" <= c <= "Z" for c in secret):
        classes += 1
    if any(c.isdigit() for c in secret):
        classes += 1
    if any(not c.isalnum() for c in secret):
        classes += 1
    if classes < 3:
        reasons.append("use at least three of: lowercase, uppercase, digit, symbol")

    folded = secret.casefold()
    if folded in COMMON or folded.strip() in COMMON:
        reasons.append("this is a common password")
    if username and username.casefold() in folded and len(username) >= 3:
        reasons.append("the password contains the account name")

    if secret and len(set(secret)) == 1:
        reasons.append("all characters are the same")
    else:
        unit = _repeated_unit(secret)
        if unit is not None and len(unit) <= 3:
            reasons.append("it repeats a short pattern")

    accepted = not reasons
    score = 0
    if accepted:
        score = 2
        if length >= 18 and classes >= 3:
            score = 3
        if length >= 20 and classes == 4:
            score = 4
    elif length >= 10 and classes >= 2 and folded not in COMMON:
        score = 1

    labels = {
        0: "Too weak",
        1: "Still too weak",
        2: "Acceptable",
        3: "Strong",
        4: "Very strong",
    }
    summary = labels[score]
    if reasons:
        summary = f"{summary}. " + "; ".join(reasons)
    else:
        summary = f"{summary}. {length} characters, {classes} character types."
    return {
        "accepted": accepted,
        "score": score,
        "classes": classes,
        "length": length,
        "reasons": reasons,
        "summary": summary,
    }


def _repeated_unit(secret: str) -> str | None:
    length = len(secret)
    for size in range(1, 5):
        if length < size * 3:
            continue
        unit = secret[:size]
        if unit * (length // size) == secret[: size * (length // size)] and length // size >= 3:
            return unit
    return None
