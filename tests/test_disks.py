#!/usr/bin/env python3
"""Spare-disk selection. No real devices."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.disks import (  # noqa: E402
    IN_PLACE_REASON,
    confirmation_matches,
    parse_lsblk_pairs,
    spare_candidates,
)


SAMPLE = """
NAME="mmcblk0" TYPE="disk" SIZE="64G" TRAN="" PKNAME="" MOUNTPOINT=""
NAME="mmcblk0p1" TYPE="part" SIZE="512M" TRAN="" PKNAME="mmcblk0" MOUNTPOINT="/boot/firmware"
NAME="mmcblk0p2" TYPE="part" SIZE="63G" TRAN="" PKNAME="mmcblk0" MOUNTPOINT="/"
NAME="sda" TYPE="disk" SIZE="32G" TRAN="usb" PKNAME="" MOUNTPOINT=""
NAME="sda1" TYPE="part" SIZE="32G" TRAN="" PKNAME="sda" MOUNTPOINT=""
NAME="sdb" TYPE="disk" SIZE="8G" TRAN="usb" PKNAME="" MOUNTPOINT=""
NAME="sdb1" TYPE="part" SIZE="8G" TRAN="" PKNAME="sdb" MOUNTPOINT="/media/card"
NAME="loop0" TYPE="loop" SIZE="2G" TRAN="" PKNAME="" MOUNTPOINT=""
"""


class DiskTests(unittest.TestCase):
    def test_spare_is_the_unmounted_usb_disk(self):
        rows = parse_lsblk_pairs(SAMPLE)
        spare = spare_candidates(rows, "mmcblk0")
        self.assertEqual([item["path"] for item in spare], ["/dev/sda"])
        self.assertEqual(spare[0]["tran"], "usb")

    def test_loops_are_hidden_unless_a_test_asks(self):
        rows = parse_lsblk_pairs(SAMPLE)
        self.assertEqual(spare_candidates(rows, "mmcblk0", allow_loop=True)[1]["path"], "/dev/loop0")

    def test_confirmation_is_exact(self):
        self.assertTrue(confirmation_matches("/dev/sda", "ERASE /dev/sda"))
        self.assertFalse(confirmation_matches("/dev/sda", "erase /dev/sda"))

    def test_in_place_is_described_as_unavailable(self):
        self.assertIn("not implemented", IN_PLACE_REASON)
        self.assertIn("boot ROM", IN_PLACE_REASON)


if __name__ == "__main__":
    unittest.main()
