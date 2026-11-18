#!/usr/bin/env bash
# wifi-join.sh against fake nmcli, raspi-config, and iw. No radio.

set -euo pipefail
unset CDPATH

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
script=$root/scripts/wifi-join.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }

mkdir -p "$work/bin"
cat > "$work/bin/nmcli" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$WIFI_LOG"
prev=
for arg in "$@"; do
  if [ "$prev" = "passwd-file" ] && [ -f "$arg" ]; then
    cat "$arg" >> "$WIFI_LOG"
  fi
  prev=$arg
done
if [ "$1" = "-t" ]; then
  printf '%s\n' '*:Cafe:70:WPA2'
fi
exit 0
EOF
cat > "$work/bin/raspi-config" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$WIFI_LOG"
exit 0
EOF
cat > "$work/bin/iw" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$WIFI_LOG"
exit 0
EOF
chmod 755 "$work/bin/nmcli" "$work/bin/raspi-config" "$work/bin/iw"

export PATH="$work/bin:$PATH"
export WIFI_LOG=$work/log
: > "$WIFI_LOG"

scan=$("$script" scan)
printf '%s\n' "$scan" | grep -q 'Cafe' || fail "scan did not return nmcli output"

"$script" country gb
grep -q 'do_wifi_country GB' "$WIFI_LOG" || fail "country was not uppercased"
grep -q 'reg set GB' "$WIFI_LOG" || fail "iw reg set was not called"

secret='p@ss:word 99'
printf '%s\n' "$secret" | "$script" connect 'My Network'
if grep -F -q "$secret" "$WIFI_LOG"; then
  # The secret is allowed in the passwd-file contents that the fake nmcli
  # appended. It must not appear as an nmcli argument. The argument log lines
  # are the ones that do not start with the psk key.
  if grep -F "$secret" "$WIFI_LOG" | grep -vq '802-11-wireless-security.psk:'; then
    fail "passphrase appeared outside the passwd-file"
  fi
else
  fail "passwd-file contents were not recorded"
fi
grep -q 'passwd-file' "$WIFI_LOG" || fail "connection up did not get a passwd-file"
grep -q 'ssid My Network' "$WIFI_LOG" || fail "ssid was not passed to nmcli"

if "$script" country 'G;B'; then
  fail "country code with a semicolon was accepted"
fi
if printf '\n' | "$script" connect ''; then
  fail "empty ssid was accepted"
fi

printf 'wifi-join: ok\n'
