#!/usr/bin/env bash
# Apply the choices from the touchscreen wizard. Secrets arrive on stdin,
# one per line, never as arguments:
#   1. new login password, or an empty line to leave the current one
#   2. disk passphrase, or an empty line to skip encryption
#   3. target disk (for example /dev/sda), or "-" when not encrypting
#   4. confirmation: "ERASE /dev/sda", or "SKIP" when not encrypting
#
# Passwords are a single line. A newline inside a password is not supported,
# matching luks-convert.sh.
#
# SECURE_JOURNAL_APPLY_CHECK_ONLY=1 validates and exits without changing the
# system. The loopback tests use it.

set -euo pipefail
unset CDPATH

info() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  die "run as root (the wizard starts this with sudo)"
fi

if [ "${1:-}" != "apply" ]; then
  die "usage: setup-apply.sh apply   (secrets on stdin)"
fi

IFS= read -r new_login || die "missing login password line"
IFS= read -r disk_pass || die "missing disk passphrase line"
IFS= read -r target || die "missing target disk line"
IFS= read -r confirm || die "missing confirmation line"

script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$script_dir/.." && pwd)
export PYTHONPATH=$repo${PYTHONPATH:+:$PYTHONPATH}

assess() {
  local secret=$1 what=$2
  # The secret is stdin, not an argument, so it does not show up in ps.
  printf '%s' "$secret" | python3 -c '
import sys
from ui.passphrase import assess
what = sys.argv[1]
secret = sys.stdin.read()
result = assess(secret)
if not result["accepted"]:
    sys.stderr.write(what + " is not strong enough: " + "; ".join(result["reasons"]) + "\n")
    sys.exit(1)
' "$what"
}

if [ -n "$new_login" ]; then
  assess "$new_login" "Login password"
fi
if [ -n "$disk_pass" ]; then
  assess "$disk_pass" "Disk passphrase"
  if [ -n "$new_login" ] && [ "$disk_pass" = "$new_login" ]; then
    die "the disk passphrase and the login password must be different secrets"
  fi
  if [ "$target" = "-" ] || [ -z "$target" ]; then
    die "a disk passphrase was set but no target disk was given"
  fi
  case "$target" in
    /dev/*) ;;
    *) die "target must be a /dev path" ;;
  esac
  expected="ERASE ${target}"
  if [ "$confirm" != "$expected" ]; then
    die "confirmation did not match; the target was not changed"
  fi
  if [ ! -b "$target" ]; then
    die "target is not a block device: $target"
  fi
else
  if [ "$confirm" != "SKIP" ] || [ "$target" != "-" ]; then
    die "encryption was skipped, so the confirmation must be SKIP and the target -"
  fi
fi

if [ "${SECURE_JOURNAL_APPLY_CHECK_ONLY:-}" = 1 ]; then
  info "Check only. No password change, no hardening, no disk copy."
  exit 0
fi

if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
  admin=$SUDO_USER
else
  admin=$(getent passwd 1000 | cut -d: -f1)
fi
if [ -z "${admin:-}" ]; then
  die "could not find the admin user"
fi

info "Applying hardening."
"$script_dir/harden.sh"

if [ -n "$new_login" ]; then
  info "Setting the login password for $admin."
  printf '%s:%s\n' "$admin" "$new_login" | chpasswd
  new_login=""
  info "Login password updated."
fi

if [ -n "$disk_pass" ]; then
  key=$(mktemp)
  chmod 600 "$key"
  cleanup() {
    if [ -n "${key:-}" ] && [ -f "$key" ]; then
      if command -v shred >/dev/null 2>&1; then
        shred -u "$key" 2>/dev/null || rm -f "$key"
      else
        rm -f "$key"
      fi
    fi
  }
  trap cleanup EXIT
  printf '%s' "$disk_pass" > "$key"
  disk_pass=""
  info "Copying the system onto $target. The disk you booted from is not modified."
  SECURE_JOURNAL_LUKS_KEY_FILE=$key SECURE_JOURNAL_ASSUME_YES=1 \
    "$script_dir/luks-convert.sh" "$target"
  info "Encrypted copy finished."
fi

info "Setup apply finished."
