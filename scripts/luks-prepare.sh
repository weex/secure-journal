#!/usr/bin/env bash
# Prepare a running Raspberry Pi OS (Bookworm or Trixie) so it can boot a
# LUKS root later. This does not encrypt anything and does not wipe a disk.
#
# Raspberry Pi OS Trixie loads an initramfs when config.txt says
# auto_initramfs=1, which the Trixie images set. Debian's cryptsetup-initramfs
# puts cryptsetup into that initramfs and, at boot, unlocks the root listed in
# /etc/crypttab. Two Pi-specific catches:
#
#   * The stock initramfs is built with MODULES=dep, which copies only the
#     modules the running system is using. dm-crypt is not one of them until
#     the disk is already encrypted, so the first encrypted boot would have
#     no way to unlock the disk. MODULES=most puts the crypt modules in.
#   * cryptsetup's default Argon2 memory cost follows the RAM of the machine
#     that formats the disk. A cost chosen on a Pi 5 can then fail inside the
#     smaller initramfs, or be unusable on a Pi 3. The convert script pins
#     the cost; this script only makes sure the initramfs can run cryptsetup.
#
# Safe to run more than once.

set -euo pipefail
unset CDPATH

info() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  die "run as root"
fi

if [ ! -r /proc/device-tree/model ]; then
  die "this script is for a Raspberry Pi (no /proc/device-tree/model)"
fi
model=$(tr -d '\0' < /proc/device-tree/model)
case "$model" in
  Raspberry\ Pi*) ;;
  *) die "this script is for a Raspberry Pi (model is: $model)" ;;
esac

if findmnt -n -o SOURCE / | grep -q '^/dev/mapper/'; then
  info "Root is already unlocked through device-mapper. Nothing to prepare."
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
info "Installing cryptsetup and the initramfs integration."
apt-get update
apt-get install -y \
  -o Dpkg::Options::=--force-confdef \
  -o Dpkg::Options::=--force-confold \
  cryptsetup \
  cryptsetup-initramfs \
  initramfs-tools \
  busybox

conf=/etc/initramfs-tools/initramfs.conf
if [ ! -f "$conf" ]; then
  die "$conf is missing; initramfs-tools did not install the way Raspberry Pi OS ships it"
fi

# MODULES=most makes a larger initramfs. The Trixie boot partition is 512MB,
# which has room. dep is smaller and, here, wrong: see the header comment.
if grep -q '^MODULES=most$' "$conf"; then
  info "initramfs MODULES is already most."
else
  if [ ! -f "${conf}.bak-secure-journal" ]; then
    cp -a "$conf" "${conf}.bak-secure-journal"
  fi
  if grep -q '^MODULES=' "$conf"; then
    sed -i 's/^MODULES=.*/MODULES=most/' "$conf"
  else
    printf '\nMODULES=most\n' >> "$conf"
  fi
  info "Set MODULES=most in $conf (previous file kept as ${conf}.bak-secure-journal)."
fi

modules=/etc/initramfs-tools/modules
touch "$modules"
for mod in dm-crypt dm-mod; do
  if ! grep -q "^${mod}\$" "$modules"; then
    printf '%s\n' "$mod" >> "$modules"
  fi
done

hook_dir=/etc/cryptsetup-initramfs
hook=$hook_dir/conf-hook
mkdir -p "$hook_dir"
touch "$hook"
# The hook file is shell. A later CRYPTSETUP=y wins over the commented default.
if grep -q '^CRYPTSETUP=' "$hook"; then
  sed -i 's/^CRYPTSETUP=.*/CRYPTSETUP=y/' "$hook"
else
  printf 'CRYPTSETUP=y\n' >> "$hook"
fi

if [ -f /boot/firmware/config.txt ]; then
  config=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
  config=/boot/config.txt
else
  die "config.txt not found; the bootloader would not load the initramfs"
fi

if grep -E -q '^[[:space:]]*auto_initramfs=0([[:space:]]|$)' "$config"; then
  die "auto_initramfs=0 in $config. The bootloader will not load the initramfs that unlocks LUKS. Set auto_initramfs=1 first."
fi
if ! grep -E -q '^[[:space:]]*auto_initramfs=1([[:space:]]|$)' "$config"; then
  printf '\n# secure-journal: load the initramfs so a LUKS root can be unlocked.\nauto_initramfs=1\n' >> "$config"
  info "Set auto_initramfs=1 in $config."
fi

info "Rebuilding the initramfs."
update-initramfs -u -k all

info "Preparation finished. The root filesystem is still unencrypted."
info "Next, with a spare disk that can be erased (a microSD card in a USB reader):"
info "  sudo $(cd -- "$(dirname -- "$0")" && pwd)/luks-convert.sh /dev/sdX"
info "Replace /dev/sdX with the spare disk. lsblk shows the name."
