#!/usr/bin/env bash
# Wi-Fi actions for the touchscreen wizard.
#
# The passphrase is read from stdin, not taken as an argument, and is handed
# to NetworkManager through a passwd-file. `nmcli device wifi connect`
# only accepts the secret on its command line; `nmcli connection up` accepts
# a file (see nmcli(1), "passwd-file"). The file is removed before this
# script exits.
#
#   wifi-join.sh scan
#   wifi-join.sh country GB
#   wifi-join.sh connect "My Network"    # passphrase on stdin; empty = open
#
# SECURE_JOURNAL_WIFI_IFACE overrides wlan0, the name Raspberry Pi OS uses.

set -euo pipefail
unset CDPATH

IFACE=${SECURE_JOURNAL_WIFI_IFACE:-wlan0}
CON_NAME=secure-journal-wifi

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: wifi-join.sh scan
       wifi-join.sh country CC
       wifi-join.sh connect SSID    (passphrase on stdin, empty for an open network)
EOF
}

require_nmcli() {
  if ! command -v nmcli >/dev/null 2>&1; then
    die "nmcli is not installed. The desktop image provides NetworkManager."
  fi
}

case "${1:-}" in
  scan)
    require_nmcli
    exec nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY dev wifi list
    ;;
  country)
    cc=${2:-}
    case "$cc" in
      [A-Za-z][A-Za-z]) ;;
      *) die "country must be two letters, for example GB" ;;
    esac
    cc=$(printf '%s' "$cc" | tr '[:lower:]' '[:upper:]')
    if command -v raspi-config >/dev/null 2>&1; then
      raspi-config nonint do_wifi_country "$cc"
    fi
    if command -v iw >/dev/null 2>&1; then
      iw reg set "$cc" || true
    fi
    require_nmcli
    nmcli radio wifi on
    printf 'Wi-Fi country set to %s\n' "$cc"
    ;;
  connect)
    ssid=${2:-}
    if [ -z "$ssid" ]; then
      die "connect needs the network name"
    fi
    case "$ssid" in
      *[$'\n\r']*) die "the network name cannot contain a newline" ;;
    esac
    require_nmcli
    IFS= read -r pass || true
    case "$pass" in
      *[$'\n']*) die "the passphrase cannot contain a newline" ;;
    esac
    nmcli connection delete "$CON_NAME" >/dev/null 2>&1 || true
    if [ -z "$pass" ]; then
      nmcli connection add type wifi con-name "$CON_NAME" ifname "$IFACE" ssid "$ssid" >/dev/null
      nmcli -w 25 connection up "$CON_NAME"
    else
      # psk-flags 1: the secret is supplied at activation, not stored by the
      # add command, so it is not part of this process's arguments.
      nmcli connection add type wifi con-name "$CON_NAME" ifname "$IFACE" ssid "$ssid" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk-flags 1 >/dev/null
      secret=$(mktemp)
      chmod 600 "$secret"
      cleanup() { rm -f "$secret"; }
      trap cleanup EXIT
      printf '802-11-wireless-security.psk:%s\n' "$pass" > "$secret"
      pass=""
      nmcli -w 25 connection up "$CON_NAME" passwd-file "$secret"
    fi
    printf 'Joined %s\n' "$ssid"
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
