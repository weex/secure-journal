#!/usr/bin/env bash
# The unlock files land in a fake root, and the crypttab path matches.

set -euo pipefail
unset CDPATH

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }

"$root/scripts/luks-unlock-ui.sh" --root "$work/root"
key=$work/root/usr/local/lib/secure-journal/unlock-keyscript
hook=$work/root/etc/initramfs-tools/hooks/secure-journal-unlock
test -x "$key" || fail "keyscript not installed executable"
test -x "$hook" || fail "hook not installed executable"
cmp -s "$root/scripts/unlock-keyscript" "$key" || fail "keyscript contents differ"

if ! grep -q '/usr/local/lib/secure-journal/unlock-keyscript' "$root/scripts/luks-convert.sh"; then
  fail "luks-convert.sh does not reference the keyscript path"
fi
if ! grep -q 'KEYSCRIPT_PATH=/usr/local/lib/secure-journal/unlock-keyscript' "$root/scripts/luks-unlock-ui.sh"; then
  fail "installer path drifted from luks-convert.sh"
fi

printf 'luks-unlock-ui: ok\n'
