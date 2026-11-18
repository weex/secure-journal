#!/usr/bin/env python3
"""Journal files and the encrypted-root check. No GTK."""

import os
import stat
import tempfile
import unittest
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.journal_store import (  # noqa: E402
    ensure_entry,
    list_entries,
    read_entry,
    root_is_encrypted,
    root_source_from_mounts,
    write_entry,
)
from ui.setup_state import clear_stamp, setup_is_complete, write_stamp  # noqa: E402
from ui.apply_cmd import apply_invocation, apply_stdin  # noqa: E402


class JournalStoreTests(unittest.TestCase):
    def test_creates_a_private_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "journal"
            path = ensure_entry(root, date(2026, 11, 18))
            self.assertEqual(path.name, "2026-11-18.md")
            self.assertTrue(path.read_text(encoding="utf-8").startswith("# 2026-11-18"))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            write_entry(path, "# 2026-11-18\n\nhello\n")
            self.assertIn("hello", read_entry(path))
            self.assertEqual(list_entries(root), [path])
            again = ensure_entry(root, date(2026, 11, 18))
            self.assertEqual(again.read_text(encoding="utf-8"), path.read_text(encoding="utf-8"))

    def test_root_encryption_flag(self):
        mounts = "\n".join(
            [
                "/dev/mmcblk0p1 /boot/firmware vfat rw 0 0",
                "/dev/mapper/cryptroot / ext4 rw 0 0",
            ]
        )
        self.assertEqual(root_source_from_mounts(mounts), "/dev/mapper/cryptroot")
        self.assertTrue(root_is_encrypted(root_source_from_mounts(mounts)))
        plain = root_source_from_mounts("/dev/mmcblk0p2 / ext4 rw 0 0\n")
        self.assertFalse(root_is_encrypted(plain))


class StampTests(unittest.TestCase):
    def test_stamp_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["XDG_CONFIG_HOME"] = tmp
            try:
                self.assertFalse(setup_is_complete())
                write_stamp("deferred")
                self.assertTrue(setup_is_complete())
                text = Path(tmp, "secure-journal", "setup-complete").read_text(encoding="utf-8")
                self.assertEqual(text, "status=deferred\n")
                clear_stamp()
                self.assertFalse(setup_is_complete())
            finally:
                os.environ.pop("XDG_CONFIG_HOME", None)


class ApplyCommandTests(unittest.TestCase):
    def test_secrets_stay_on_stdin(self):
        command = apply_invocation("/opt/secure-journal/scripts/setup-apply.sh", True)
        stdin = apply_stdin(True, "current-secret", "Login-Password-99", "Disk-Passphrase-99", "/dev/sda", "ERASE /dev/sda")
        self.assertNotIn("Login-Password-99", " ".join(command))
        self.assertNotIn("Disk-Passphrase-99", " ".join(command))
        self.assertTrue(command[0] == "sudo" and "-S" in command)
        self.assertEqual(
            stdin,
            "current-secret\nLogin-Password-99\nDisk-Passphrase-99\n/dev/sda\nERASE /dev/sda\n",
        )

    def test_passwordless_sudo_omits_the_current_password(self):
        stdin = apply_stdin(False, "", "Login-Password-99", "", "-", "SKIP")
        self.assertEqual(stdin, "Login-Password-99\n\n-\nSKIP\n")
        command = apply_invocation("setup-apply.sh", False)
        self.assertIn("-n", command)
        self.assertNotIn("-S", command)

    def test_newlines_are_rejected(self):
        with self.assertRaises(ValueError):
            apply_stdin(False, "", "one\ntwo", "", "-", "SKIP")


if __name__ == "__main__":
    unittest.main()
