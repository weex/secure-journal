#!/usr/bin/env bash
# setup-apply.sh rejects weak input before it touches the system.
# The accept path uses SECURE_JOURNAL_APPLY_CHECK_ONLY so it does not call
# harden.sh or luks-convert.sh. Needs root for the script's own check.

set -euo pipefail
unset CDPATH

if [ "$(id -u)" -ne 0 ]; then
  printf 'error: run as root\n' >&2
  exit 1
fi

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
script=$root/scripts/setup-apply.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }

expect_fail() {
  local label=$1
  shift
  if "$@" >"$work/out" 2>"$work/err"; then
    printf 'FAIL %s: command succeeded\n' "$label" >&2
    exit 1
  fi
  printf 'ok %s\n' "$label"
}

expect_fail "short login password" \
  env SECURE_JOURNAL_APPLY_CHECK_ONLY=1 "$script" apply <<'EOF'
short
Disk-Passphrase-99
-
SKIP
EOF

expect_fail "disk passphrase matches the login" \
  env SECURE_JOURNAL_APPLY_CHECK_ONLY=1 "$script" apply <<'EOF'
Correct-Horse-99
Correct-Horse-99
/dev/sda
ERASE /dev/sda
EOF

expect_fail "confirmation does not match" \
  env SECURE_JOURNAL_APPLY_CHECK_ONLY=1 "$script" apply <<'EOF'
Login-Password-99x
Disk-Passphrase-99
/dev/sda
ERASE /dev/sdb
EOF

expect_fail "skip confirmation is wrong" \
  env SECURE_JOURNAL_APPLY_CHECK_ONLY=1 "$script" apply <<'EOF'
Login-Password-99x

-
ERASE /dev/sda
EOF

if ! env SECURE_JOURNAL_APPLY_CHECK_ONLY=1 "$script" apply >"$work/out" <<'EOF'
Login-Password-99x

-
SKIP
EOF
then
  cat "$work/out" >&2
  fail "valid skip was rejected"
fi
grep -q 'Check only' "$work/out" || fail "check-only did not say so"

printf 'setup-apply: ok\n'
