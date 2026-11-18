#!/usr/bin/env bash
# Check the LUKS parameters and the cmdline/fstab rewrite without device-mapper.
# The full copy is tests/luks-convert-loop.sh, which needs dm_mod to mount the
# new root. This kernel in CI may not have that module; the header still can
# be written and read back.

set -euo pipefail
unset CDPATH

if [ "$(id -u)" -ne 0 ]; then
  printf 'error: run as root\n' >&2
  exit 1
fi

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
# Path is computed; shellcheck cannot follow it.
# shellcheck disable=SC1091
source "$root/scripts/luks-convert.sh"

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }

work=$(mktemp -d)
loop=""
finish() {
  set +e
  if [ -n "$loop" ]; then
    losetup -d "$loop" 2>/dev/null
  fi
  rm -rf "$work"
}
trap finish EXIT

cmdline=$work/cmdline.txt
printf '%s\n' 'console=tty1 root=PARTUUID=12345678-02 rootfstype=ext4 fsck.repair=yes rootwait cfg80211.ieee80211_regdom=US' > "$cmdline"
rewrite_cmdline "$cmdline"
line=$(tr -d '\n' < "$cmdline")
case "$line" in
  *' root=/dev/mapper/cryptroot') ;;
  *) fail "mapper root not at the end: $line" ;;
esac
case "$line" in
  *root=PARTUUID*) fail "old root= kept: $line" ;;
esac
case "$line" in
  *rootwait*) ;;
  *) fail "rootwait dropped: $line" ;;
esac
case "$line" in
  *cfg80211.ieee80211_regdom=US*) ;;
  *) fail "unrelated token dropped: $line" ;;
esac
# One line, one rootwait.
if [ "$(printf '%s' "$line" | grep -o rootwait | wc -l)" -ne 1 ]; then
  fail "rootwait count is wrong: $line"
fi

printf '%s\n' 'console=tty1 root=/dev/mmcblk0p2' > "$cmdline"
rewrite_cmdline "$cmdline"
line=$(tr -d '\n' < "$cmdline")
case "$line" in
  *'root=/dev/mapper/cryptroot'*rootwait) ;;
  *) fail "rootwait was not added: $line" ;;
esac

fstab=$work/fstab
cat > "$fstab" <<'EOF'
# keep this comment
proc            /proc           proc    defaults          0       0
PARTUUID=aaaaaaaa-01  /boot/firmware  vfat    defaults          0       2
PARTUUID=aaaaaaaa-02  /               ext4    defaults,noatime  0       1
EOF
rewrite_fstab "$fstab" bbbbbbbb-01
grep -q '^# keep this comment$' "$fstab" || fail "comment dropped"
grep -q 'proc' "$fstab" || fail "proc line dropped"
grep -q '/dev/mapper/cryptroot' "$fstab" || fail "root mapper missing"
grep -q 'defaults,noatime' "$fstab" || fail "root options not kept"
grep -q 'PARTUUID=bbbbbbbb-01' "$fstab" || fail "boot PARTUUID not rewritten"
if grep -q 'aaaaaaaa' "$fstab"; then
  fail "old PARTUUID survived"
fi

printf 'proc /proc proc defaults 0 0\n' > "$fstab"
rewrite_fstab "$fstab" cccccccc-01
grep -q '/dev/mapper/cryptroot' "$fstab" || fail "missing root line was not added"
grep -q 'PARTUUID=cccccccc-01' "$fstab" || fail "missing boot line was not added"

image=$work/header.img
truncate -s 64M "$image"
loop=$(losetup -f --show "$image")
key=$work/key
printf '%s' 'test-passphrase-1234' > "$key"
cryptsetup luksFormat --batch-mode "${LUKS_ARGS[@]}" --key-file "$key" "$loop"
dump=$(cryptsetup luksDump "$loop")
printf '%s\n' "$dump" | grep -q 'aes-xts-plain64' || fail "cipher"
printf '%s\n' "$dump" | grep -q 'argon2id' || fail "pbkdf"
printf '%s\n' "$dump" | grep -q '512 bits' || fail "key size"
printf '%s\n' "$dump" | grep -E -q 'Memory:[[:space:]]+65536' || fail "argon2 memory"
printf '%s\n' "$dump" | grep -E -q 'Threads:[[:space:]]+1$' || fail "argon2 threads"
printf '%s\n' "$dump" | grep -E -q 'Label:[[:space:]]+secure-journal' || fail "label"
printf '%s\n' "$dump" | grep -q 'sha256' || fail "hash"

printf 'luks-metadata: ok\n'
