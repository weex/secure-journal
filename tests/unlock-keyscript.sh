#!/usr/bin/env bash
# The keyscript's stdout is the passphrase and nothing else.
# unl0kr and askpass are fakes. Nothing is installed into an initramfs.

set -euo pipefail
unset CDPATH

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
script=$root/scripts/unlock-keyscript
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }

if "$script" >"$work/out" 2>"$work/err"; then
  fail "ran without crypttab variables"
fi

cat > "$work/unl0kr" <<'EOF'
#!/bin/sh
printf '%s\n' 'touch-passphrase'
EOF
cat > "$work/askpass" <<'EOF'
#!/bin/sh
printf '%s\n' 'keyboard-passphrase'
EOF
chmod 755 "$work/unl0kr" "$work/askpass"

export CRYPTTAB_SOURCE=/dev/sda2
export CRYPTTAB_NAME=cryptroot
export SECURE_JOURNAL_UNL0KR=$work/unl0kr
export SECURE_JOURNAL_ASKPASS=$work/askpass
export SECURE_JOURNAL_UNLOCK_NO_WAIT=1
export SECURE_JOURNAL_CMDLINE=$work/cmdline
printf 'console=tty1 rootwait\n' > "$work/cmdline"

out=$( "$script" </dev/null 2>"$work/err" )
if [ "$out" != "touch-passphrase" ]; then
  fail "unl0kr output was '$out'"
fi

printf 'console=tty1 sj.unlock=console rootwait\n' > "$work/cmdline"
out=$( "$script" </dev/null 2>"$work/err" )
if [ "$out" != "keyboard-passphrase" ]; then
  fail "console fallback output was '$out'"
fi
grep -q 'sj.unlock=console' "$work/err" || fail "console path was silent"

cat > "$work/unl0kr" <<'EOF'
#!/bin/sh
echo 'unl0kr broke' >&2
exit 1
EOF
printf 'console=tty1 rootwait\n' > "$work/cmdline"
out=$( "$script" </dev/null 2>"$work/err" )
if [ "$out" != "keyboard-passphrase" ]; then
  fail "failed unl0kr did not fall back, got '$out'"
fi

# prereqs mode must not need the initramfs hook library.
hook_out=$( "$root/scripts/initramfs-hook" prereqs )
if [ -n "$hook_out" ]; then
  fail "hook prereqs should be empty, got '$hook_out'"
fi

printf 'unlock-keyscript: ok\n'
