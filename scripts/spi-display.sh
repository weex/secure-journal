#!/usr/bin/env bash
# Enable a 3.5" SPI touchscreen (goodtft LCD35 / Waveshare 3.5 and the usual
# ILI9486 clones) on Raspberry Pi OS Bookworm or Trixie.
#
# The 2021 setup cloned goodtft/LCD-show and ran LCD35-show. That installer
# targets the DispmanX/X11 stack from before Bookworm. On current images it
# fights the KMS driver and Wayland (labwc) and can leave the panel dark.
# The kernel's piscreen overlay, with the drm parameter, registers the panel
# as a normal display. Wayland can use it. Check the parameter list on the
# Pi in /boot/firmware/overlays/README under "piscreen"; clones differ, and
# touch axes often need invx, invy, or swapxy.
#
# Idempotent: the lines live in one marked block, replaced on every run.
# Re-running does not stack overlays. The official DSI Touch Display 2 does
# not need this script; the Pi detects that panel on its own.
#
# Usage:
#   sudo ./scripts/spi-display.sh
#   sudo SPI_DTPARAM='piscreen,drm,rotate=270,speed=16000000,swapxy' ./scripts/spi-display.sh
#   sudo ./scripts/spi-display.sh --reboot
#
# SPI_DTPARAM is the comma-separated overlay argument, without "dtoverlay=".
# SECURE_JOURNAL_CONFIG overrides the config.txt path (used by the test).

set -euo pipefail

BEGIN_MARK='# BEGIN secure-journal spi-display'
END_MARK='# END secure-journal spi-display'
DTPARAM=${SPI_DTPARAM:-piscreen,drm,rotate=90,speed=18000000}
REBOOT=0

info() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: spi-display.sh [--reboot]

Writes a marked dtoverlay block for a 3.5" SPI panel to config.txt.
SPI_DTPARAM overrides the overlay parameters (default:
piscreen,drm,rotate=90,speed=18000000).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --reboot) REBOOT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

if [ -n "${SECURE_JOURNAL_CONFIG:-}" ]; then
  CONFIG=$SECURE_JOURNAL_CONFIG
else
  if [ "$(id -u)" -ne 0 ]; then
    die "run as root so config.txt can be updated"
  fi
  if [ -f /boot/firmware/config.txt ]; then
    CONFIG=/boot/firmware/config.txt
  elif [ -f /boot/config.txt ]; then
    CONFIG=/boot/config.txt
  else
    die "config.txt not found under /boot/firmware or /boot"
  fi
fi

if [ ! -f "$CONFIG" ]; then
  die "config file not found: $CONFIG"
fi

# Refuse a value that would break out of a single config.txt line.
case "$DTPARAM" in
  *[$'\n\r']*) die "SPI_DTPARAM must be a single line" ;;
  dtoverlay=*) die "SPI_DTPARAM is the overlay argument only, without dtoverlay=" ;;
esac

tmp=$(mktemp)
cleanup() { rm -f "$tmp"; }
trap cleanup EXIT

# Drop a previous copy of our block, keep every other line.
awk -v begin="$BEGIN_MARK" -v end="$END_MARK" '
  $0 == begin { skip = 1; next }
  $0 == end { skip = 0; next }
  skip { next }
  { print }
' "$CONFIG" > "$tmp"

cat >> "$tmp" <<EOF
$BEGIN_MARK
[all]
# 3.5" ILI9486-class SPI panel. drm selects the KMS driver so Wayland can
# light the panel. LCD-show is not installed. Clones differ: add invx, invy,
# or swapxy if taps land in the wrong place, and lower speed if colours break.
dtparam=spi=on
dtoverlay=$DTPARAM
$END_MARK
EOF

# Redirect onto the existing inode so ownership of /boot/firmware/config.txt
# stays with root when this is run via sudo.
cat "$tmp" > "$CONFIG"

if grep -E -q '^[[:space:]]*dtoverlay=(tft35a|mhs35|waveshare35)' "$CONFIG"; then
  info "warning: config.txt still has a legacy tft35a/mhs35/waveshare overlay outside this script."
  info "Two drivers on one panel will fight. Remove the old dtoverlay line and reboot."
fi

info "Wrote the SPI panel overlay to $CONFIG."
info "Reboot to apply it. The desktop may also be on HDMI until that cable is unplugged."

if [ "$REBOOT" -eq 1 ]; then
  info "Rebooting."
  reboot
fi
