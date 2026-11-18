#!/usr/bin/env python3
"""Construct the GTK windows. Skipped without a display or PyGObject.

This does not drive a touchscreen. It only checks that the wizard's pages
and the journal's first entry can be built.
"""

import os
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class GtkWindowTests(unittest.TestCase):
    def test_windows_construct(self):
        if not os.environ.get("DISPLAY"):
            self.skipTest("no display")
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            gi.require_version("Gdk", "3.0")
            from gi.repository import Gtk  # noqa: F401
        except (ImportError, ValueError) as exc:
            self.skipTest(f"GTK not available: {exc}")

        import tempfile

        from ui.journal_app import JournalApp
        from ui.setup_wizard import SetupWizard

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["JOURNAL_DIR"] = str(Path(tmp) / "journal")
            os.environ["XDG_CONFIG_HOME"] = str(Path(tmp) / "config")
            try:
                wizard = SetupWizard()
                journal = JournalApp()
                self.assertEqual(wizard.get_title(), "Journal setup")
                for name in ("welcome", "wifi", "secrets", "encrypt", "working", "done"):
                    self.assertIsNotNone(wizard.stack.get_child_by_name(name), name)
                self.assertTrue(list(Path(os.environ["JOURNAL_DIR"]).glob("*/*/*.md")))
                self.assertEqual(journal.get_title(), "Journal")
            finally:
                os.environ.pop("JOURNAL_DIR", None)
                os.environ.pop("XDG_CONFIG_HOME", None)


if __name__ == "__main__":
    unittest.main()
