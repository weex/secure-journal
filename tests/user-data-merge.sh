#!/usr/bin/env bash
# prepare-card.sh copies the repo and inserts one cloud-init runcmd.
# No Raspberry Pi, no root.

set -euo pipefail
unset CDPATH

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
script=$root/scripts/prepare-card.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }

boot=$work/boot
mkdir -p "$boot"
printf 'arm_64bit=1\n' > "$boot/config.txt"
printf 'console=tty1 root=PARTUUID=1234 rootwait\n' > "$boot/cmdline.txt"

"$script" "$boot"
test -f "$boot/secure-journal/scripts/bootstrap.sh" || fail "repo was not staged"
grep -q 'secure-journal/scripts/bootstrap.sh' "$boot/user-data" || fail "runcmd missing from a new user-data"
# A second run must not duplicate the command.
"$script" "$boot"
count=$(grep -c 'secure-journal/scripts/bootstrap.sh' "$boot/user-data")
if [ "$count" -ne 1 ]; then
  fail "runcmd duplicated: $count"
fi

imager=$work/imager
mkdir -p "$imager"
printf 'arm_64bit=1\n' > "$imager/config.txt"
cat > "$imager/user-data" <<'EOF'
#cloud-config
hostname: journal
users:
  - name: ada
    lock_passwd: false
runcmd:
  - [ systemctl, enable, ssh ]
EOF
"$script" "$imager"
grep -q 'hostname: journal' "$imager/user-data" || fail "hostname dropped"
grep -q 'name: ada' "$imager/user-data" || fail "user dropped"
grep -q 'systemctl, enable, ssh' "$imager/user-data" || fail "existing runcmd dropped"
grep -q 'secure-journal/scripts/bootstrap.sh' "$imager/user-data" || fail "bootstrap not inserted"
# The new command is the first runcmd item, so it runs even if a later one reboots.
awk '
  $0 ~ /^runcmd:/ { inlist = 1; next }
  inlist && $0 ~ /^[^ ]/ { inlist = 0 }
  inlist && $0 ~ /^[[:space:]]+- / { print; exit }
' "$imager/user-data" | grep -q bootstrap.sh || fail "bootstrap is not the first runcmd item"

plain=$work/plain
mkdir -p "$plain"
printf 'kernel=1\n' > "$plain/config.txt"
printf 'this is not cloud-config\n' > "$plain/user-data"
before=$(cat "$plain/user-data")
if "$script" "$plain"; then
  fail "a file cloud-init would ignore was accepted"
fi
after=$(cat "$plain/user-data")
if [ "$before" != "$after" ]; then
  fail "rejected user-data was modified"
fi

inline=$work/inline
mkdir -p "$inline"
printf 'kernel=1\n' > "$inline/config.txt"
printf '%s\n' '#cloud-config' 'runcmd: ["/bin/true"]' > "$inline/user-data"
if "$script" "$inline"; then
  fail "an inline runcmd was rewritten"
fi
grep -q '/bin/true' "$inline/user-data" || fail "inline runcmd lost"

printf 'user-data-merge: ok\n'
