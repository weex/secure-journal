"""Local password rules for the security password.

Nothing here calls the network. The same function runs in the tests and on
the Pi. Argon2id is the stored hash; this module only decides what may be
hashed.
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
        "securejournal",
    }
)

MIN_LENGTH = 14


def assess(secret: str) -> dict:
    reasons: list[str] = []
    length = len(secret)
    if length < MIN_LENGTH:
        reasons.append(f"{length} characters; need at least {MIN_LENGTH}")
    if length > 1024:
        reasons.append("shorter than 1024 characters")

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

    if secret and len(set(secret)) == 1:
        reasons.append("all characters are the same")
    else:
        unit = _repeated_unit(secret)
        if unit is not None and len(unit) <= 3:
            reasons.append("it repeats a short pattern")

    accepted = not reasons
    return {
        "accepted": accepted,
        "length": length,
        "classes": classes,
        "reasons": reasons,
        "summary": "Acceptable." if accepted else " ".join(reasons),
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
