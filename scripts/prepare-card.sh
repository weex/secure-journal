#!/usr/bin/env bash
# Stage the touchscreen setup onto a freshly written Raspberry Pi OS card.
#
# The Pi boot ROM only reads a card that already has firmware. Writing the
# image still happens on another computer. This script is the last step on
# that computer: it copies this repository onto the FAT boot partition and
# adds one cloud-init runcmd. The first boot on the Pi then installs the
# setup and opens it on the touchscreen. No SSH session is required.
#
# Raspberry Pi OS Trixie reads /boot/firmware/user-data as cloud-init
# user-data. The first line must be #cloud-config. Imager 2 writes that
# file. This script inserts a runcmd and does not change the user, the
# password, or the Wi-Fi block. A file that cloud-init would ignore is left
# untouched.
#
# Usage:
#   ./scripts/prepare-card.sh /path/to/boot/partition

set -euo pipefail
unset CDPATH

BOOT_CMD='/bin/sh /boot/firmware/secure-journal/scripts/bootstrap.sh'

info() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: prepare-card.sh /path/to/boot/partition

The path is the FAT boot partition of a Raspberry Pi OS Trixie card
(the volume that contains config.txt and user-data), not the root
filesystem. Run it after Imager has written the card and before the
first boot.
EOF
}

# Insert the bootstrap runcmd into a cloud-init user-data file.
# Prints nothing. Exits non-zero without modifying the file when the file
# is not a #cloud-config document this script can extend safely.
merge_user_data() {
  local file=$1
  local first tmp

  if [ ! -f "$file" ]; then
    printf '%s\n' '#cloud-config' 'runcmd:' "  - \"${BOOT_CMD}\"" > "$file"
    return 0
  fi

  if grep -F -q -- "$BOOT_CMD" "$file"; then
    return 0
  fi

  first=$(head -n 1 "$file" | tr -d '\r')
  if [ "$first" != "#cloud-config" ]; then
    die "user-data does not start with #cloud-config, so cloud-init would ignore a runcmd added to it. Left the file unchanged. Add this line under runcmd, with the same indentation as the other commands: - \"${BOOT_CMD}\""
  fi

  if grep -E -q '^runcmd:[[:space:]]*\[' "$file"; then
    die "user-data has an inline runcmd list. Left the file unchanged. Add the bootstrap command to that list: ${BOOT_CMD}"
  fi

  tmp=$(mktemp)
  if grep -E -q '^runcmd:[[:space:]]*(#.*)?$' "$file"; then
    awk -v cmd="$BOOT_CMD" '
      $0 ~ /^runcmd:[[:space:]]*(#.*)?$/ && !inserted {
        print
        print "  - \"" cmd "\""
        inserted = 1
        next
      }
      { print }
    ' "$file" > "$tmp"
  else
    cat "$file" > "$tmp"
    # The leading newline separates the block when the file has no trailing one.
    printf '\nruncmd:\n  - "%s"\n' "$BOOT_CMD" >> "$tmp"
  fi
  cat "$tmp" > "$file"
  rm -f "$tmp"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi
if [ "$#" -ne 1 ]; then
  usage >&2
  exit 1
fi

BOOT=$1
if [ ! -d "$BOOT" ]; then
  die "boot directory not found: $BOOT"
fi
if [ ! -f "$BOOT/config.txt" ] && [ ! -f "$BOOT/cmdline.txt" ]; then
  die "$BOOT has neither config.txt nor cmdline.txt. This should be the FAT boot partition."
fi

repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
dest=$BOOT/secure-journal
rm -rf "$dest"
mkdir -p "$dest"
tar -C "$repo" \
  --exclude .git \
  --exclude __pycache__ \
  --exclude '*.pyc' \
  -cf - . | tar -C "$dest" -xf -

if [ -f "$BOOT/user-data" ]; then
  merge_user_data "$BOOT/user-data"
else
  merge_user_data "$BOOT/user-data"
  info "There was no user-data file. Wrote one that only runs the setup."
  info "The official first-boot wizard still has to create the login, unless Imager already did."
fi

info "Staged the setup at $dest."
info "On first boot, cloud-init runs: $BOOT_CMD"
info "Eject the card, put it in the Pi with the touchscreen connected, and power on."
info "Log in on the screen (the on-screen keyboard follows a text field). The setup wizard opens after that."
