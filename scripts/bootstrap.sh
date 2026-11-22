#!/usr/bin/env bash
# Install the touchscreen setup onto the running system.
#
# cloud-init runs this once from the FAT boot partition. A timer runs it
# again until the Python GTK libraries are installed, so a first boot with
# no network yet can succeed after Wi-Fi comes up. Safe to run again.
#
# The wizard itself is not started here. A desktop autostart entry starts
# it in the login session, which is where the on-screen keyboard works.

set -euo pipefail
unset CDPATH

info() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  die "run as root"
fi

exec 9>/var/lock/secure-journal-bootstrap.lock
if ! flock -n 9; then
  info "Another bootstrap is running."
  exit 0
fi

STAMP=/var/lib/secure-journal/bootstrapped
OPT=/opt/secure-journal

copy_tree() {
  local src=""
  if [ -f /boot/firmware/secure-journal/scripts/bootstrap.sh ]; then
    src=/boot/firmware/secure-journal
  elif [ -f /boot/secure-journal/scripts/bootstrap.sh ]; then
    src=/boot/secure-journal
  elif [ -f "$OPT/scripts/bootstrap.sh" ]; then
    src=""
  else
    die "secure-journal files not found on the boot partition or in $OPT"
  fi
  if [ -n "$src" ]; then
    mkdir -p "$OPT"
    tar -C "$src" -cf - . | tar -C "$OPT" -xf -
  fi
  find "$OPT/scripts" -type f \
    \( -name '*.sh' -o -name 'unlock-keyscript' -o -name 'initramfs-hook' \
       -o -name 'launch-session' -o -name 'journal' \) \
    -exec chmod 755 {} +
}

install_units() {
  install -D -m 0644 "$OPT/scripts/secure-journal-bootstrap.service" \
    /etc/systemd/system/secure-journal-bootstrap.service
  install -D -m 0644 "$OPT/scripts/secure-journal-bootstrap.timer" \
    /etc/systemd/system/secure-journal-bootstrap.timer
  install -D -m 0644 "$OPT/scripts/secure-journal-setup.desktop" \
    /etc/xdg/autostart/secure-journal-setup.desktop
  install -m 0755 "$OPT/scripts/journal" /usr/local/bin/journal
  install -d -m 0755 /usr/local/share/applications
  if [ -f "$OPT/scripts/journal.desktop" ]; then
    install -m 0644 "$OPT/scripts/journal.desktop" /usr/local/share/applications/journal.desktop
  fi
  systemctl daemon-reload
  systemctl enable secure-journal-bootstrap.timer
}

gtk_ready() {
  python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' >/dev/null 2>&1
}

copy_tree
install_units

if [ -f "$STAMP" ] && gtk_ready && command -v unl0kr >/dev/null 2>&1; then
  systemctl disable --now secure-journal-bootstrap.timer >/dev/null 2>&1 || true
  info "Bootstrap already finished."
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
if ! apt-get update; then
  info "warning: no package index yet. The timer will try again."
  exit 1
fi
if ! apt-get install -y \
  -o Dpkg::Options::=--force-confdef \
  -o Dpkg::Options::=--force-confold \
  python3-gi \
  gir1.2-gtk-3.0 \
  unl0kr \
  cryptsetup \
  cryptsetup-initramfs \
  initramfs-tools \
  libpam-pwquality; then
  info "warning: package install failed. The timer will try again."
  exit 1
fi

if command -v raspi-config >/dev/null 2>&1; then
  # S2 follows a touchscreen, which is what the desktop image documents.
  # A missing subcommand (newer raspi-config builds dropped it; squeekboard
  # then starts on its own) is a warning, not a failed setup.
  if ! raspi-config nonint do_squeekboard S2; then
    info "warning: could not enable the on-screen keyboard through raspi-config."
  fi
fi

install -d -m 0755 /var/lib/secure-journal
touch "$STAMP"
systemctl disable --now secure-journal-bootstrap.timer >/dev/null 2>&1 || true
info "Setup components are installed. The wizard opens at the next graphical login."
