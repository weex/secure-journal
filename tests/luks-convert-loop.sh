#!/usr/bin/env bash
# Exercise luks-convert.sh against loop devices. Requires root, cryptsetup,
# and a kernel that can create device-mapper targets. Does not touch real disks.

set -euo pipefail
unset CDPATH

if [ "$(id -u)" -ne 0 ]; then
  printf 'error: run as root\n' >&2
  exit 1
fi

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
script=$root/scripts/luks-convert.sh
work=$(mktemp -d)
loops=()

cleanup() {
  set +e
  if [ -n "${mounted_on:-}" ] && mountpoint -q "$mounted_on"; then
    umount "$mounted_on"
  fi
  if [ -e /dev/mapper/sj-check ]; then
    cryptsetup close sj-check
  fi
  if [ -e /dev/mapper/sj-newroot ]; then
    cryptsetup close sj-newroot
  fi
  local loop
  for loop in "${loops[@]+"${loops[@]}"}"; do
    losetup -d "$loop" 2>/dev/null
  done
  rm -rf "$work"
}
trap cleanup EXIT

add_loop() {
  local image=$1 size=$2 loop
  truncate -s "$size" "$image"
  loop=$(losetup -f -P --show "$image")
  loops+=("$loop")
  printf '%s\n' "$loop"
}

expect_fail() {
  local label=$1
  shift
  if "$@" >"$work/out" 2>"$work/err"; then
    printf 'FAIL %s: command succeeded\n' "$label" >&2
    cat "$work/err" >&2
    exit 1
  fi
  printf 'ok %s\n' "$label"
}

fixture=$work/src
mkdir -p "$fixture/boot/firmware" "$fixture/etc" "$fixture/home/journaluser/journal"
printf 'console=serial0,115200 console=tty1 root=PARTUUID=12345678-02 rootfstype=ext4 fsck.repair=yes rootwait cfg80211.ieee80211_regdom=US\n' \
  > "$fixture/boot/firmware/cmdline.txt"
printf 'auto_initramfs=1\ndtoverlay=vc4-kms-v3d\n' > "$fixture/boot/firmware/config.txt"
printf 'keep-this-kernel\n' > "$fixture/boot/firmware/kernel.img"
cat > "$fixture/etc/fstab" <<'EOF'
proc            /proc           proc    defaults          0       0
PARTUUID=12345678-01  /boot/firmware  vfat    defaults          0       2
PARTUUID=12345678-02  /               ext4    defaults,noatime  0       1
EOF
printf 'original note\n' > "$fixture/home/journaluser/journal/note.txt"
chmod 600 "$fixture/home/journaluser/journal/note.txt"
mkdir -p "$fixture/etc/initramfs-tools"
printf 'MODULES=dep\n' > "$fixture/etc/initramfs-tools/initramfs.conf"

pass_file=$work/pass
printf '%s' 'test-passphrase-1234' > "$pass_file"
short_file=$work/short
printf '%s' 'too-short' > "$short_file"

export SECURE_JOURNAL_SOURCE_ROOT=$fixture
export SECURE_JOURNAL_SKIP_PREPARE=1
export SECURE_JOURNAL_SKIP_INITRAMFS=1
export SECURE_JOURNAL_ASSUME_YES=1

source_disk=$(add_loop "$work/source.img" 1M)
export SECURE_JOURNAL_SOURCE_DISK=$source_disk
source_sum=$(sha256sum "$work/source.img")

expect_fail "rejects the live disk" \
  env SECURE_JOURNAL_LUKS_KEY_FILE="$pass_file" "$script" "$source_disk"

small=$(add_loop "$work/small.img" 64M)
expect_fail "rejects a disk that cannot hold the copy" \
  env SECURE_JOURNAL_LUKS_KEY_FILE="$pass_file" "$script" "$small"

part_parent=$(add_loop "$work/parts.img" 64M)
parted -s "$part_parent" mklabel msdos
parted -s "$part_parent" mkpart primary 1MiB 100%
partx -u "$part_parent" 2>/dev/null || partx -a "$part_parent"
part_node=${part_parent}p1
tries=0
while [ ! -b "$part_node" ] && [ "$tries" -lt 30 ]; do
  sleep 0.1
  tries=$((tries + 1))
done
if [ ! -b "$part_node" ]; then
  printf 'FAIL could not create a partition node for the refusal test\n' >&2
  exit 1
fi
expect_fail "rejects a partition" \
  env SECURE_JOURNAL_LUKS_KEY_FILE="$pass_file" "$script" "$part_node"

target=$(add_loop "$work/target.img" 2G)

mounted_on=$work/mounted
mkdir -p "$mounted_on"
mkfs.ext4 -F -q "$target"
mount "$target" "$mounted_on"
printf 'keep\n' > "$mounted_on/marker"
expect_fail "refuses a mounted disk" \
  env SECURE_JOURNAL_LUKS_KEY_FILE="$pass_file" "$script" "$target"
if ! grep -q keep "$mounted_on/marker"; then
  printf 'FAIL mounted disk was modified\n' >&2
  exit 1
fi
umount "$mounted_on"
mounted_on=""
wipefs -a "$target" >/dev/null

expect_fail "rejects a short passphrase" \
  env SECURE_JOURNAL_LUKS_KEY_FILE="$short_file" "$script" "$target"
# Match the type, not the name: "loop1" contains the letters p1.
if lsblk -nr -o TYPE "$target" | grep -qx part; then
  printf 'FAIL short passphrase still partitioned the disk\n' >&2
  exit 1
fi

if ! grep -q 'device-mapper' /proc/devices; then
  printf 'luks-convert-loop: copy skipped (this kernel has no device-mapper)\n'
  exit 0
fi

run_convert() {
  env SECURE_JOURNAL_LUKS_KEY_FILE="$pass_file" "$script" "$target"
}

run_convert
# A second run must erase and rewrite, not refuse or stack a broken table.
run_convert

boot=${target}p1
rootp=${target}p2
if [ ! -b "$boot" ] || [ ! -b "$rootp" ]; then
  printf 'FAIL partition nodes missing after convert\n' >&2
  exit 1
fi

boot_id=$(blkid -c /dev/null -s PARTUUID -o value "$boot")
root_id=$(blkid -c /dev/null -s PARTUUID -o value "$rootp")

inspect=$work/inspect
mkdir -p "$inspect"
cryptsetup open --key-file "$pass_file" "$rootp" sj-check
mount /dev/mapper/sj-check "$inspect"

fstab=$inspect/etc/fstab
crypttab=$inspect/etc/crypttab
note=$inspect/home/journaluser/journal/note.txt
conf=$inspect/etc/initramfs-tools/initramfs.conf

grep -q '/dev/mapper/cryptroot' "$fstab"
grep -q "PARTUUID=${boot_id}" "$fstab"
grep -q "cryptroot PARTUUID=${root_id} none luks,initramfs,keyscript=/usr/local/lib/secure-journal/unlock-keyscript" "$crypttab"
grep -q 'original note' "$note"
if [ "$(stat -c '%a' "$note")" != "600" ]; then
  printf 'FAIL journal note mode is %s\n' "$(stat -c '%a' "$note")" >&2
  exit 1
fi
grep -q '^MODULES=most$' "$conf"

mkdir -p "$work/boot"
mount "$boot" "$work/boot"
cmdline=$(tr -d '\n' < "$work/boot/cmdline.txt")
case "$cmdline" in
  *root=/dev/mapper/cryptroot*) ;;
  *) printf 'FAIL cmdline missing mapper root: %s\n' "$cmdline" >&2; exit 1 ;;
esac
case "$cmdline" in
  *root=PARTUUID=12345678-02*) printf 'FAIL old root= survived: %s\n' "$cmdline" >&2; exit 1 ;;
esac
case "$cmdline" in
  *rootwait*) ;;
  *) printf 'FAIL rootwait missing: %s\n' "$cmdline" >&2; exit 1 ;;
esac
case "$cmdline" in
  *cfg80211.ieee80211_regdom=US*) ;;
  *) printf 'FAIL unrelated cmdline token dropped: %s\n' "$cmdline" >&2; exit 1 ;;
esac
grep -q 'keep-this-kernel' "$work/boot/kernel.img"
grep -q 'auto_initramfs=1' "$work/boot/config.txt"
umount "$work/boot"

dump=$(cryptsetup luksDump "$rootp")
printf '%s\n' "$dump" | grep -q 'aes-xts-plain64'
printf '%s\n' "$dump" | grep -q 'argon2id'
printf '%s\n' "$dump" | grep -q '512'

umount "$inspect"
cryptsetup close sj-check

if [ "$(sha256sum "$work/source.img")" != "$source_sum" ]; then
  printf 'FAIL source disk image changed\n' >&2
  exit 1
fi

printf 'luks-convert-loop: ok\n'
