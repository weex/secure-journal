#!/usr/bin/env python3
"""Passphrase policy used by the touchscreen wizard."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.passphrase import assess  # noqa: E402


class PassphraseTests(unittest.TestCase):
    def test_rejects_short_and_common(self):
        short = assess("Horse-Battery")
        self.assertFalse(short["accepted"])
        self.assertTrue(any("14" in reason for reason in short["reasons"]))
        common = assess("raspberrypi123")
        self.assertFalse(common["accepted"])

    def test_rejects_exact_common_password(self):
        result = assess("raspberry")
        self.assertFalse(result["accepted"])
        self.assertIn("common password", " ".join(result["reasons"]))

    def test_accepts_a_mixed_passphrase(self):
        result = assess("Correct-Horse-99")
        self.assertTrue(result["accepted"])
        self.assertGreaterEqual(result["score"], 2)
        self.assertNotIn("Correct-Horse-99", result["summary"])

    def test_stronger_passphrase_scores_higher(self):
        ok = assess("Correct-Horse-99")
        strong = assess("Correct-Horse-Battery-99!")
        self.assertGreater(strong["score"], ok["score"])
        self.assertEqual(strong["score"], 4)

    def test_repeated_pattern_is_rejected(self):
        result = assess("abcabcabcabcabc")
        self.assertFalse(result["accepted"])

    def test_username_is_rejected(self):
        result = assess("journal-Password-99", username="journal")
        self.assertFalse(result["accepted"])


if __name__ == "__main__":
    unittest.main()
