#!/usr/bin/env bash
# Install the boot-time unlock UI into a root filesystem.
#
# Copies the keyscript and the initramfs hook. With --with-packages, also
# installs Debian's unl0kr. Packages are optional: without the binary the
# keyscript asks on the text console instead of failing closed.
#
#   sudo ./scripts/luks-unlock-ui.sh --with-packages
#   ./scripts/luks-unlock-ui.sh --root /mnt/newroot
#
# Does not format a disk and does not rebuild the initramfs. luks-prepare.sh
# and luks-convert.sh do that after this script returns.

set -euo pipefail
unset CDPATH

KEYSCRIPT_PATH=/usr/local/lib/secure-journal/unlock-keyscript
HOOK_PATH=/etc/initramfs-tools/hooks/secure-journal-unlock

info() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

ROOT=/
WITH_PACKAGES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --root)
      [ $# -ge 2 ] || die "--root needs a path"
      ROOT=$2
      shift
      ;;
    --with-packages) WITH_PACKAGES=1 ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

script_dir=$(cd -- "$(dirname -- "$0")" && pwd)

if [ "$WITH_PACKAGES" -eq 1 ]; then
  if [ "$(id -u)" -ne 0 ]; then
    die "run as root to install packages"
  fi
  export DEBIAN_FRONTEND=noninteractive
  if ! apt-get update; then
    info "warning: apt-get update failed. The keyscript is still installed; the prompt will use a USB keyboard until unl0kr is installed."
  elif ! apt-get install -y \
    -o Dpkg::Options::=--force-confdef \
    -o Dpkg::Options::=--force-confold \
    unl0kr; then
    info "warning: unl0kr did not install. The boot prompt will use a USB keyboard."
  else
    info "unl0kr is installed. The boot prompt can use the touchscreen."
  fi
fi

mkdir -p "$ROOT"

install -D -m 0755 "$script_dir/unlock-keyscript" "$ROOT$KEYSCRIPT_PATH"
install -D -m 0755 "$script_dir/initramfs-hook" "$ROOT$HOOK_PATH"
info "Unlock keyscript: $ROOT$KEYSCRIPT_PATH"
info "Initramfs hook: $ROOT$HOOK_PATH"
