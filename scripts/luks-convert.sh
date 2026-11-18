#!/usr/bin/env bash
# Build a bootable copy of this Raspberry Pi OS system on another disk, with
# the root filesystem inside a LUKS2 volume.
#
# The disk you are booted from is only read. A failed run leaves it bootable.
# The target disk is erased. Re-running erases the target again; it does not
# skip work, because a half-written card is not something to trust.
#
# What "full disk" means on a Pi: the bootloader in ROM can read a FAT boot
# partition and nothing else. That partition (kernel, initramfs, config.txt)
# stays unencrypted. Someone with the card can replace those files (an "evil
# maid" boot) but cannot read the journal without the passphrase. Raspberry
# Pi's Secure Boot Provisioner can bind unlock to a one-time key in OTP and
# does not ask for a passphrase. This script asks for a passphrase, which is
# the property a journal wants. OTP programming is permanent and is out of
# scope here.
#
# The boot prompt is scripts/unlock-keyscript. It waits for a framebuffer and
# runs Debian's unl0kr (an on-screen keyboard in the initramfs). The Pi boot
# ROM still cannot do this; the kernel has to be running. A 3.5" SPI panel
# often stays dark until the desktop, and the official DSI panel only lights
# once its kernel driver is loaded. If the panel stays dark, add
# sj.unlock=console to cmdline.txt on the FAT boot partition and type the
# passphrase with a USB keyboard on HDMI. That file is editable without the
# passphrase.
#
# Usage:
#   sudo ./scripts/luks-prepare.sh
#   sudo ./scripts/luks-convert.sh /dev/sda
#
# The passphrase is read from the terminal. It is not accepted as an argument,
# because arguments are visible to other users via ps. A key file is supported
# for the loopback test only:
#   SECURE_JOURNAL_LUKS_KEY_FILE=/path SECURE_JOURNAL_ASSUME_YES=1
# The key file is the exact passphrase bytes. A single trailing newline, as
# from `echo`, is ignored. The file is not copied onto the card.
#
# Test hooks, unsupported for a real card:
#   SECURE_JOURNAL_SOURCE_ROOT   directory to copy instead of /
#   SECURE_JOURNAL_SOURCE_DISK   block device to treat as the live disk
#   SECURE_JOURNAL_BOOT_DIR      boot files, default /boot/firmware
#   SECURE_JOURNAL_SKIP_PREPARE=1
#   SECURE_JOURNAL_SKIP_INITRAMFS=1

set -euo pipefail
unset CDPATH

MAPPER_NAME=sj-newroot
MIN_PASSPHRASE=14
# Fixed Argon2id cost. cryptsetup's default scales with the host's RAM and
# can then be too large for the initramfs, especially on a 1GB Pi 3.
# 64 MiB and a 2 second iteration time unlock on a Pi 3 and still cost a
# guesser two seconds per try. aes-xts-plain64 512 is the ordinary LUKS2
# cipher; a Pi 5 has AES instructions, a Pi 3 or 4 does this in software,
# which is enough for a journal.
LUKS_ARGS=(
  --type luks2
  --cipher aes-xts-plain64
  --key-size 512
  --hash sha256
  --pbkdf argon2id
  --pbkdf-memory 65536
  --pbkdf-parallel 1
  --iter-time 2000
  --label secure-journal
)

info() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: luks-convert.sh /dev/DISK

DISK is a whole spare disk (microSD in a USB reader, or a USB SSD), not a
partition and not the disk this system booted from. The script erases it
and writes a LUKS2 root plus a small unencrypted FAT boot partition.

You will be asked to type ERASE /dev/DISK and then a passphrase of at least
14 characters. Boot the new card, enter that passphrase on the touchscreen
or with a USB keyboard, and only then wipe the original card.
EOF
}

ROOTMNT=""
KEY_TEMP=""

cleanup() {
  set +e
  if [ -n "$ROOTMNT" ] && [ -d "$ROOTMNT" ]; then
    if mountpoint -q "$ROOTMNT/boot/firmware" 2>/dev/null; then
      umount "$ROOTMNT/boot/firmware"
    fi
    for sub in run sys proc dev; do
      if mountpoint -q "$ROOTMNT/$sub" 2>/dev/null; then
        umount "$ROOTMNT/$sub"
      fi
    done
    if mountpoint -q "$ROOTMNT" 2>/dev/null; then
      umount "$ROOTMNT"
    fi
    rmdir "$ROOTMNT" 2>/dev/null
  fi
  if [ -e "/dev/mapper/$MAPPER_NAME" ]; then
    cryptsetup close "$MAPPER_NAME"
  fi
  if [ -n "$KEY_TEMP" ] && [ -f "$KEY_TEMP" ]; then
    dd if=/dev/urandom of="$KEY_TEMP" bs=64 count=1 status=none 2>/dev/null
    rm -f "$KEY_TEMP"
  fi
}

# mmcblk0p1, nvme0n1p1, loop0p1; sda1. A trailing digit means the partition
# node inserts a "p".
part_node() {
  local disk=$1 num=$2
  case "$disk" in
    *[0-9]) printf '%sp%s\n' "$disk" "$num" ;;
    *) printf '%s%s\n' "$disk" "$num" ;;
  esac
}

wait_node() {
  local node=$1 tries=0
  while [ "$tries" -lt 50 ]; do
    if [ -b "$node" ]; then
      return 0
    fi
    tries=$((tries + 1))
    sleep 0.1
  done
  die "device node $node did not appear"
}

partuuid_of() {
  local node=$1 id
  # blkid reads the partition table itself. lsblk's PARTUUID comes from udev,
  # which has not always scanned a just-created loop device. -c /dev/null
  # skips the cache so a re-run sees the new disk id.
  id=$(blkid -c /dev/null -s PARTUUID -o value "$node" 2>/dev/null || true)
  id=${id%%$'\n'*}
  if [ -z "$id" ]; then
    id=$(lsblk -no PARTUUID "$node" 2>/dev/null || true)
    id=${id%%$'\n'*}
  fi
  if [ -z "$id" ]; then
    die "no PARTUUID for $node"
  fi
  printf '%s\n' "$id"
}

rewrite_cmdline() {
  local file=$1 line token out has_rootwait
  line=$(tr -d '\n' < "$file")
  if [ -z "$line" ]; then
    die "cmdline.txt is empty: $file"
  fi
  out=""
  has_rootwait=0
  # The Pi cmdline is a single line of space-separated tokens. None of them
  # contain spaces. read splits on IFS and does not glob.
  read -r -a tokens <<< "$line"
  for token in "${tokens[@]}"; do
    case "$token" in
      root=*|cryptdevice=*) continue ;;
    esac
    if [ "$token" = "rootwait" ]; then
      has_rootwait=1
    fi
    out="${out}${out:+ }${token}"
  done
  out="${out} root=/dev/mapper/cryptroot"
  if [ "$has_rootwait" -eq 0 ]; then
    out="${out} rootwait"
  fi
  printf '%s\n' "$out" > "$file"
}

rewrite_fstab() {
  local file=$1 boot_partuuid=$2 tmp
  tmp=$(mktemp)
  awk -v boot="PARTUUID=${boot_partuuid}" '
    /^[ \t]*#/ || /^[ \t]*$/ { print; next }
    {
      n = split($0, a, /[ \t]+/)
      if (n >= 2 && a[2] == "/") {
        opts = (n >= 4 ? a[4] : "defaults,noatime")
        dump = (n >= 5 ? a[5] : "0")
        pass = (n >= 6 ? a[6] : "1")
        printf "/dev/mapper/cryptroot\t/\text4\t%s\t%s\t%s\n", opts, dump, pass
        next
      }
      if (n >= 2 && a[2] == "/boot/firmware") {
        opts = (n >= 4 ? a[4] : "defaults")
        dump = (n >= 5 ? a[5] : "0")
        pass = (n >= 6 ? a[6] : "2")
        printf "%s\t/boot/firmware\tvfat\t%s\t%s\t%s\n", boot, opts, dump, pass
        next
      }
      print
    }
  ' "$file" > "$tmp"
  if ! awk 'NF >= 2 && $2 == "/" { found = 1 } END { exit !found }' "$tmp"; then
    printf '/dev/mapper/cryptroot\t/\text4\tdefaults,noatime\t0\t1\n' >> "$tmp"
  fi
  if ! awk 'NF >= 2 && $2 == "/boot/firmware" { found = 1 } END { exit !found }' "$tmp"; then
    printf 'PARTUUID=%s\t/boot/firmware\tvfat\tdefaults\t0\t2\n' "$boot_partuuid" >> "$tmp"
  fi
  cat "$tmp" > "$file"
  rm -f "$tmp"
}

ensure_crypt_initramfs_config() {
  local root=$1 conf modules hook
  conf=$root/etc/initramfs-tools/initramfs.conf
  if [ -f "$conf" ] && grep -q '^MODULES=' "$conf"; then
    sed -i 's/^MODULES=.*/MODULES=most/' "$conf"
  fi
  modules=$root/etc/initramfs-tools/modules
  if [ -f "$modules" ]; then
    for mod in dm-crypt dm-mod; do
      if ! grep -q "^${mod}\$" "$modules"; then
        printf '%s\n' "$mod" >> "$modules"
      fi
    done
  fi
  hook=$root/etc/cryptsetup-initramfs/conf-hook
  mkdir -p "$(dirname "$hook")"
  touch "$hook"
  if grep -q '^CRYPTSETUP=' "$hook"; then
    sed -i 's/^CRYPTSETUP=.*/CRYPTSETUP=y/' "$hook"
  else
    printf 'CRYPTSETUP=y\n' >> "$hook"
  fi
}

read_passphrase() {
  local source_file content
  if [ -n "${SECURE_JOURNAL_LUKS_KEY_FILE:-}" ]; then
    source_file=$SECURE_JOURNAL_LUKS_KEY_FILE
    if [ ! -f "$source_file" ]; then
      die "key file not found: $source_file"
    fi
    # Command substitution drops every trailing newline. `echo secret > file`
    # and a file written with printf both work. Newlines in the middle of a
    # passphrase are not supported.
    content=$(cat "$source_file")
  else
    if [ "${SECURE_JOURNAL_ASSUME_YES:-}" = 1 ]; then
      die "SECURE_JOURNAL_ASSUME_YES requires SECURE_JOURNAL_LUKS_KEY_FILE"
    fi
    local first second
    info "The disk passphrase is separate from the login password."
    info "Nothing in this script stores a recovery copy. A lost passphrase means a lost journal."
    read -r -s -p "Disk passphrase (${MIN_PASSPHRASE}+ characters): " first </dev/tty
    printf '\n'
    read -r -s -p "Repeat disk passphrase: " second </dev/tty
    printf '\n'
    if [ "$first" != "$second" ]; then
      die "passphrases did not match"
    fi
    content=$first
    first=""
    second=""
  fi
  if [ "${#content}" -lt "$MIN_PASSPHRASE" ]; then
    die "passphrase must be at least ${MIN_PASSPHRASE} characters"
  fi
  KEY_TEMP=$(mktemp)
  chmod 600 "$KEY_TEMP"
  printf '%s' "$content" > "$KEY_TEMP"
  content=""
  KEY_FILE=$KEY_TEMP
}

confirm_erase() {
  local target=$1 expected answer
  info "This will erase $target and write a new encrypted Raspberry Pi root."
  info "The disk you are booted from is not modified."
  if [ "${SECURE_JOURNAL_ASSUME_YES:-}" = 1 ]; then
    info "SECURE_JOURNAL_ASSUME_YES=1, so the typed confirmation was skipped."
    return 0
  fi
  expected="ERASE ${target}"
  printf 'Type %s to continue: ' "$expected" >/dev/tty
  read -r answer </dev/tty
  if [ "$answer" != "$expected" ]; then
    die "confirmation did not match; the target was not changed"
  fi
}

detect_source_disk() {
  local src pk
  src=$(findmnt -n -o SOURCE /)
  if [ -z "$src" ]; then
    die "could not find the root filesystem device"
  fi
  case "$src" in
    /dev/mapper/*)
      die "root is already unlocked from $src. Refusing to stack another copy."
      ;;
  esac
  pk=$(lsblk -no PKNAME "$src")
  pk=${pk%%$'\n'*}
  if [ -z "$pk" ]; then
    die "could not find the disk that holds $src"
  fi
  printf '/dev/%s\n' "$pk"
}

# tests/luks-metadata.sh sources this file for the helpers and LUKS_ARGS.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  return 0
fi

trap cleanup EXIT

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi
if [ "$#" -ne 1 ]; then
  usage >&2
  exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
  die "run as root"
fi

for tool in parted mkfs.vfat mkfs.ext4 cryptsetup rsync lsblk blkid partprobe; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    die "required command not found: $tool"
  fi
done

if [ -n "${SECURE_JOURNAL_SOURCE_ROOT:-}" ] || [ -n "${SECURE_JOURNAL_SOURCE_DISK:-}" ]; then
  if [ -z "${SECURE_JOURNAL_SOURCE_ROOT:-}" ] || [ -z "${SECURE_JOURNAL_SOURCE_DISK:-}" ]; then
    die "set both SECURE_JOURNAL_SOURCE_ROOT and SECURE_JOURNAL_SOURCE_DISK, or neither"
  fi
  SOURCE_ROOT=$SECURE_JOURNAL_SOURCE_ROOT
  SOURCE_DISK=$(readlink -f "$SECURE_JOURNAL_SOURCE_DISK")
else
  SOURCE_ROOT=/
  SOURCE_DISK=$(detect_source_disk)
fi

if [ -n "${SECURE_JOURNAL_BOOT_DIR:-}" ]; then
  BOOT_DIR=$SECURE_JOURNAL_BOOT_DIR
elif [ "$SOURCE_ROOT" = / ]; then
  if [ -d /boot/firmware ]; then
    BOOT_DIR=/boot/firmware
  else
    BOOT_DIR=/boot
  fi
else
  BOOT_DIR=$SOURCE_ROOT/boot/firmware
fi

TARGET=$(readlink -f "$1")
if [ ! -b "$TARGET" ]; then
  die "target is not a block device: $TARGET"
fi
# loop is a whole-disk image (the test uses one). part is a slice of a disk.
target_type=$(lsblk -dno TYPE "$TARGET")
case "$target_type" in
  disk|loop) ;;
  *) die "target must be a whole disk, for example /dev/sda, not a partition ($TARGET)" ;;
esac
if [ "$TARGET" = "$SOURCE_DISK" ]; then
  die "refusing to erase $TARGET because it is the disk this system is using"
fi
if lsblk -nr -o MOUNTPOINT "$TARGET" | grep -q '[^[:space:]]'; then
  die "refusing to erase $TARGET because a filesystem on it is mounted"
fi
if [ ! -f "$BOOT_DIR/cmdline.txt" ]; then
  die "boot cmdline not found at $BOOT_DIR/cmdline.txt"
fi
if [ ! -d "$SOURCE_ROOT" ]; then
  die "source root not found: $SOURCE_ROOT"
fi

info "Measuring used space on $SOURCE_ROOT (this reads the filesystem, it does not change it)."
used_bytes=$(du -sx -B1 "$SOURCE_ROOT" | awk '{print $1}')
target_bytes=$(blockdev --getsize64 "$TARGET")
# 512MiB boot + 64MiB LUKS header slack + 256MiB copy margin.
need_bytes=$((used_bytes + 512 * 1024 * 1024 + 64 * 1024 * 1024 + 256 * 1024 * 1024))
if [ "$target_bytes" -lt "$need_bytes" ]; then
  die "target is ${target_bytes} bytes; need at least ${need_bytes} for the data, the boot partition, and LUKS"
fi

info "Source root: $SOURCE_ROOT"
info "Source disk (not modified): $SOURCE_DISK"
info "Target disk (will be erased): $TARGET"
info "Used data: ${used_bytes} bytes. Target size: ${target_bytes} bytes."

read_passphrase
confirm_erase "$TARGET"

# cryptsetup loads dm_mod when it opens a volume. Load it now so a Pi that
# has the module, but has never used it, is not refused. A kernel built
# without device-mapper still fails the check below, before the target is
# erased.
if ! grep -q 'device-mapper' /proc/devices; then
  modprobe dm_mod 2>/dev/null || true
fi
if ! grep -q 'device-mapper' /proc/devices; then
  die "this kernel has no device-mapper. Raspberry Pi OS provides dm_mod; without it the LUKS volume cannot be opened to copy the system. The target was not modified."
fi

if [ "${SECURE_JOURNAL_SKIP_PREPARE:-}" != 1 ]; then
  script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
  info "Preparing cryptsetup on the running system before copying it."
  "$script_dir/luks-prepare.sh"
fi

info "Partitioning $TARGET."
# Drop any kernel partition nodes first. On a re-run, or on a loop device,
# parted's table is not visible until partx reloads it. partprobe is enough
# on a Pi with udev; partx covers the loopback test and a quiet udev.
if command -v partx >/dev/null 2>&1; then
  partx -d "$TARGET" 2>/dev/null || true
fi
# 4MiB-aligned first partition, 512MiB, matching the room current Pi images
# leave for the boot firmware. The second partition holds the LUKS container.
parted -s -a optimal "$TARGET" mklabel msdos
parted -s -a optimal "$TARGET" mkpart primary fat32 4MiB 516MiB
parted -s -a optimal "$TARGET" mkpart primary 516MiB 100%
parted -s "$TARGET" set 1 boot on
partprobe "$TARGET" || true
if command -v partx >/dev/null 2>&1; then
  partx -u "$TARGET" 2>/dev/null || partx -a "$TARGET"
fi
if command -v udevadm >/dev/null 2>&1; then
  udevadm settle || true
fi

BOOT_PART=$(part_node "$TARGET" 1)
ROOT_PART=$(part_node "$TARGET" 2)
wait_node "$BOOT_PART"
wait_node "$ROOT_PART"

if findmnt -n "$BOOT_PART" >/dev/null 2>&1; then
  umount "$BOOT_PART"
fi
if findmnt -n "$ROOT_PART" >/dev/null 2>&1; then
  umount "$ROOT_PART"
fi

BOOT_PARTUUID=$(partuuid_of "$BOOT_PART")
ROOT_PARTUUID=$(partuuid_of "$ROOT_PART")

info "Formatting the boot partition and the LUKS container."
wipefs -a "$BOOT_PART" >/dev/null
wipefs -a "$ROOT_PART" >/dev/null
mkfs.vfat -F 32 -n bootfs "$BOOT_PART" >/dev/null
cryptsetup luksFormat --batch-mode "${LUKS_ARGS[@]}" --key-file "$KEY_FILE" "$ROOT_PART"
cryptsetup open --key-file "$KEY_FILE" "$ROOT_PART" "$MAPPER_NAME"
mkfs.ext4 -F -L rootfs "/dev/mapper/$MAPPER_NAME" >/dev/null

ROOTMNT=$(mktemp -d /mnt/secure-journal.XXXXXX)
mkdir -p "$ROOTMNT"
mount "/dev/mapper/$MAPPER_NAME" "$ROOTMNT"

info "Copying the system. This takes as long as a full read and write of the card."
# -x stays on the source filesystem, so a mount of the target under /mnt or
# /tmp cannot be copied into itself. Boot files are copied separately onto
# the FAT partition, which cannot store Unix permissions.
rsync -aH -x --numeric-ids \
  --exclude=/boot/firmware \
  --exclude=/proc \
  --exclude=/sys \
  --exclude=/dev \
  --exclude=/run \
  --exclude=/tmp \
  --exclude=/mnt \
  --exclude=/media \
  --exclude=/lost+found \
  --exclude=/var/swap \
  --exclude=/swapfile \
  "$SOURCE_ROOT"/ "$ROOTMNT"/

mkdir -p "$ROOTMNT/proc" "$ROOTMNT/sys" "$ROOTMNT/dev" "$ROOTMNT/run" \
  "$ROOTMNT/tmp" "$ROOTMNT/mnt" "$ROOTMNT/media" "$ROOTMNT/boot/firmware"
chmod 1777 "$ROOTMNT/tmp"

mount "$BOOT_PART" "$ROOTMNT/boot/firmware"
rsync -rt "$BOOT_DIR"/ "$ROOTMNT/boot/firmware"/
rewrite_cmdline "$ROOTMNT/boot/firmware/cmdline.txt"

if [ ! -f "$ROOTMNT/etc/fstab" ]; then
  die "copied system has no /etc/fstab"
fi
rewrite_fstab "$ROOTMNT/etc/fstab" "$BOOT_PARTUUID"
# keyscript is our wrapper, not unl0kr's own script: a missing display then
# falls back to the console instead of failing the unlock.
printf 'cryptroot PARTUUID=%s none luks,initramfs,keyscript=/usr/local/lib/secure-journal/unlock-keyscript\n' \
  "$ROOT_PARTUUID" > "$ROOTMNT/etc/crypttab"
chmod 644 "$ROOTMNT/etc/crypttab"
ensure_crypt_initramfs_config "$ROOTMNT"

script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
"$script_dir/luks-unlock-ui.sh" --root "$ROOTMNT"

if [ "${SECURE_JOURNAL_SKIP_INITRAMFS:-}" = 1 ]; then
  info "Skipping initramfs rebuild (SECURE_JOURNAL_SKIP_INITRAMFS=1)."
else
  if [ ! -x "$ROOTMNT/usr/sbin/update-initramfs" ]; then
    die "the copy has no update-initramfs. Run scripts/luks-prepare.sh on the Pi and start again."
  fi
  mount --bind /dev "$ROOTMNT/dev"
  mount --bind /proc "$ROOTMNT/proc"
  mount --bind /sys "$ROOTMNT/sys"
  if [ -d /run ]; then
    mkdir -p "$ROOTMNT/run"
    mount --bind /run "$ROOTMNT/run"
  fi
  info "Building the initramfs on the new card so it contains cryptsetup and this crypttab."
  chroot "$ROOTMNT" update-initramfs -u -k all
fi

sync

info "Finished."
info "  Boot partition: $BOOT_PART (PARTUUID=$BOOT_PARTUUID)"
info "  LUKS partition: $ROOT_PART (PARTUUID=$ROOT_PARTUUID)"
info "  Unlocked mapper name at boot: /dev/mapper/cryptroot"
info "Power off and boot this card. The touchscreen asks for the disk passphrase when a display device is up; otherwise use HDMI and a USB keyboard."
info "If the panel stays dark, add sj.unlock=console to cmdline.txt on the boot partition and use the USB keyboard."
info "The original card is still unencrypted. Keep it as the backup until the new card has booted and the journal is there, then wipe it."
info "Shut the Pi down to lock the disk again. A locked screen does not lock the disk."
