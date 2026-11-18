#!/usr/bin/env python3
"""nmcli -t parser. No radio."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wifi_nm import parse_wifi_list, split_nmcli  # noqa: E402


class WifiParseTests(unittest.TestCase):
    def test_split_unescapes_colons(self):
        self.assertEqual(split_nmcli(r"*:My\: Network:80:WPA2"), ["*", "My: Network", "80", "WPA2"])

    def test_parse_skips_hidden_and_sorts_by_signal(self):
        text = "\n".join(
            [
                " :Cafe:40:WPA2",
                r"*:My\: Network:80:WPA1 WPA2",
                ": :55:WPA2",
                " :Cafe:20:WPA2",
            ]
        )
        rows = parse_wifi_list(text)
        self.assertEqual([row["ssid"] for row in rows], ["My: Network", "Cafe"])
        self.assertTrue(rows[0]["in_use"])
        self.assertEqual(rows[0]["signal"], 80)
        self.assertFalse(rows[1]["in_use"])


if __name__ == "__main__":
    unittest.main()
