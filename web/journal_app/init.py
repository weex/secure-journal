"""Create a local password record and certificate for development.

    python -m journal_app.init --password 'a long mixed passphrase'
"""

from __future__ import annotations

import argparse
import os

from journal_app.auth import provision_password
from journal_app.cert import generate_certificate
from journal_app.config import Settings
from journal_app.password import assess


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local journal password record.")
    parser.add_argument("--password", required=True)
    parser.add_argument("--data", default="")
    args = parser.parse_args()
    result = assess(args.password)
    if not result["accepted"]:
        raise SystemExit(result["summary"])
    if args.data:
        os.environ["JOURNAL_DATA_DIR"] = args.data
    os.environ.setdefault("JOURNAL_DEV", "1")
    settings = Settings.from_env()
    if settings.auth_path.exists():
        raise SystemExit(f"{settings.auth_path} already exists.")
    provision_password(settings, args.password)
    generate_certificate(
        settings.cert_path.parent,
        hostnames=["localhost", "journal.local"],
        ips=["127.0.0.1"],
    )
    print(f"Wrote {settings.auth_path}")
    print("Start the app with: JOURNAL_DEV=1 python -m journal_app")


if __name__ == "__main__":
    main()
