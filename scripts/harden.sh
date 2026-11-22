#!/usr/bin/env bash
# Idempotent hardening for a Raspberry Pi OS journal (Bookworm or Trixie).
#
# What this changes, and why:
#   * Daily security updates through unattended-upgrades. The Pi archive is
#     included because that is where kernel and firmware fixes are published.
#     The bootloader EEPROM package is left out; a bad EEPROM update is painful
#     to recover, so it stays a deliberate apt install. The machine does not
#     reboot itself: with a LUKS root, a reboot waits for a passphrase, and an
#     unattended reboot would sit there until somebody is in the room.
#   * A firewall that drops inbound connections except rate-limited SSH.
#   * SSH: no root login, no keyboard-interactive login, and no password login
#     once an SSH key is installed for the admin user. Without a key, password
#     login is left on and the script says so. Re-run it after adding a key.
#   * sudo asks for the login password. Raspberry Pi OS has often shipped a
#     NOPASSWD rule for the first user.
#   * Desktop and console autologin are off, so a reboot needs the login
#     password as well as the disk passphrase.
#   * The on-screen keyboard follows a touchscreen, and the screen blanks after
#     10 minutes. Blanking is not a lock. The desktop lock is a lock. Neither
#     one seals the disk; shutdown does.
#   * New passwords have to be at least 14 characters and mixed. That applies
#     the next time the password is changed, not retroactively to the Imager
#     password.
#   * ~/journal is mode 0700, and `journal` opens today's entry.
#
# Run it again after any of this; it rewrites its own config files and does
# not append duplicates.
#
#   sudo ./scripts/harden.sh

set -euo pipefail
unset CDPATH

info() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  die "run as root (sudo ./scripts/harden.sh)"
fi

if [ ! -r /proc/device-tree/model ]; then
  die "this script is for a Raspberry Pi"
fi
model=$(tr -d '\0' < /proc/device-tree/model)
case "$model" in
  Raspberry\ Pi*) info "Running on $model." ;;
  *) die "this script is for a Raspberry Pi (model is: $model)" ;;
esac

if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
  admin=$SUDO_USER
else
  admin=$(getent passwd 1000 | cut -d: -f1)
fi
if [ -z "${admin:-}" ]; then
  die "could not find the admin user. Create the account in Imager and re-run with sudo."
fi
admin_home=$(getent passwd "$admin" | cut -d: -f6)
if [ -z "$admin_home" ] || [ ! -d "$admin_home" ]; then
  die "no home directory for $admin"
fi
info "Admin user is $admin ($admin_home)."

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

info "Installing firewall, unattended upgrades, password checks, and cryptsetup."
apt-get update
apt-get install -y \
  -o Dpkg::Options::=--force-confdef \
  -o Dpkg::Options::=--force-confold \
  unattended-upgrades \
  ufw \
  libpam-pwquality \
  cryptsetup \
  cryptsetup-initramfs \
  openssh-server

# --- unattended upgrades ---------------------------------------------------
# Origins are appended across apt conf files, so this drop-in adds the Pi
# archive without deleting Debian's own security lines. Duplicates are
# harmless. Confirm on the machine with:
#   apt-cache policy | grep -E 'o=|l='
#   sudo unattended-upgrade --dry-run --debug
# unattended-upgrades expands ${distro_codename} itself. Build that token
# without leaving a shell expansion in this script.
dollar='$'
code_token="${dollar}{distro_codename}"
pi_origin=""
if apt-cache policy | grep -q 'o=Raspberry Pi Foundation'; then
  pi_origin="Raspberry Pi Foundation,codename=${code_token},label=Raspberry Pi Foundation"
elif apt-cache policy | grep -q 'o=Raspbian'; then
  pi_origin="Raspbian,codename=${code_token},label=Raspbian"
else
  warn "apt does not currently show a Raspberry Pi origin. Writing the usual Trixie/Bookworm origin anyway."
  pi_origin="Raspberry Pi Foundation,codename=${code_token},label=Raspberry Pi Foundation"
fi

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

cat > /etc/apt/apt.conf.d/52secure-journal-unattended <<EOF
// secure-journal. Debian security plus the Raspberry Pi archive, which is
// where kernel and firmware updates are published. rpi-eeprom is excluded:
// update that package on purpose, with a keyboard attached.
// Automatic reboot is off so a LUKS passphrase prompt is never left waiting.
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::SyslogEnable "true";
Unattended-Upgrade::Package-Blacklist {
        "rpi-eeprom";
};
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,codename=\${distro_codename}-security,label=Debian-Security";
        "origin=Debian,codename=\${distro_codename},label=Debian-Security";
        "origin=PI_ORIGIN";
};
EOF
# Insert the archive origin without a second round of shell expansion.
sed -i "s/PI_ORIGIN/${pi_origin}/" /etc/apt/apt.conf.d/52secure-journal-unattended
info "Security updates will be installed daily. The Pi will not reboot by itself."

# --- password quality ------------------------------------------------------
install -d -m 0755 /etc/security/pwquality.conf.d
cat > /etc/security/pwquality.conf.d/50-secure-journal.conf <<'EOF'
# Applied the next time a password is changed. The Imager password is not
# re-checked until then. Pick a long one there as well.
minlen = 14
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1
dictcheck = 1
enforcing = 1
EOF
if [ -f /etc/pam.d/common-password ] && ! grep -q pam_pwquality /etc/pam.d/common-password; then
  pam-auth-update --package --enable pwquality || warn "pam_pwquality is installed but not enabled in PAM"
fi

# --- sudo password ---------------------------------------------------------
# raspi-config removes the NOPASSWD drop-ins. The user stays in group sudo,
# and Debian's sudoers grants that group passworded sudo. If they are not in
# the group, removing the drop-in would remove their only admin path.
if id -nG "$admin" | tr ' ' '\n' | grep -qx sudo; then
  if ! raspi-config nonint do_sudo_pass 0; then
    warn "could not enable the sudo password through raspi-config"
  fi
  if sudo -n -l -U "$admin" 2>/dev/null | grep -q 'NOPASSWD'; then
    warn "$admin can still sudo without a password. Check /etc/sudoers and /etc/sudoers.d."
  else
    info "sudo now asks for $admin's password."
  fi
else
  warn "$admin is not in group sudo. Leaving sudo rules unchanged."
fi

# --- firewall --------------------------------------------------------------
# Add the SSH rule before enabling, so a re-run cannot cut off the session
# that is applying the change. Existing connections survive either way.
if [ ! -f /etc/ufw/user.rules ] || ! grep -E -q 'dport 22([^0-9]|$)' /etc/ufw/user.rules; then
  ufw limit 22/tcp comment 'rate-limit SSH'
fi
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
info "Firewall is on. Inbound SSH is rate-limited; other inbound ports are closed."

# --- SSH -------------------------------------------------------------------
# Drop-ins in sshd_config.d are included from the top of sshd_config on
# Debian, and the first value wins. 00- sorts before cloud-init's 50- file,
# which otherwise re-enables password login. sshd -T checks the result.
install -d -m 0755 /etc/ssh/sshd_config.d
keys="$admin_home/.ssh/authorized_keys"
password_auth=yes
if [ -s "$keys" ]; then
  password_auth=no
  chmod 700 "$admin_home/.ssh"
  chmod 600 "$keys"
fi

cat > /etc/ssh/sshd_config.d/00-secure-journal.conf <<EOF
# secure-journal
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication ${password_auth}
KbdInteractiveAuthentication no
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
DebianBanner no
MaxAuthTries 3
EOF
chmod 644 /etc/ssh/sshd_config.d/00-secure-journal.conf

if ! sshd -t; then
  die "sshd rejected the new config. The previous config is still what will be loaded after you fix /etc/ssh/sshd_config.d/00-secure-journal.conf"
fi

effective_password=$(sshd -T -C "user=${admin},host=localhost,addr=127.0.0.1" | awk '$1 == "passwordauthentication" { print $2; exit }')
effective_root=$(sshd -T -C "user=${admin},host=localhost,addr=127.0.0.1" | awk '$1 == "permitrootlogin" { print $2; exit }')
if [ "$effective_root" != "no" ]; then
  die "PermitRootLogin is '$effective_root' after the drop-in. Another sshd config file is overriding it."
fi
if [ "$effective_password" != "$password_auth" ]; then
  die "PasswordAuthentication is '$effective_password', wanted '$password_auth'. Another sshd config file is overriding 00-secure-journal.conf."
fi

if systemctl is-active --quiet ssh; then
  systemctl reload ssh
elif systemctl is-active --quiet sshd; then
  systemctl reload sshd
fi

if [ "$password_auth" = "no" ]; then
  info "SSH password login is off. This session stays up."
  info "Before you disconnect, open a second session with the key to confirm it works."
else
  warn "No SSH public key in $keys."
  warn "Password login is still on. Add a key, then run this script again."
fi

# --- login, keyboard, blanking --------------------------------------------
if [ -e /etc/init.d/lightdm ] || [ -x /usr/sbin/lightdm ]; then
  if ! raspi-config nonint do_boot_behaviour B3; then
    die "could not turn off autologin. Set Desktop (not autologin) in raspi-config."
  fi
  info "Boot goes to the desktop and asks for the login password."
else
  warn "lightdm is not installed. This image has no desktop to log into."
  warn "Use the Raspberry Pi OS desktop image, not Lite, for the touchscreen."
fi

if ! raspi-config nonint do_squeekboard S2; then
  warn "the on-screen keyboard was not enabled. Install squeekboard and re-run, or set it in raspi-config."
fi

# do_blanking appends a swayidle line every time it is asked to enable
# blanking. Only call it when that line is not already there.
labwc_autostart="$admin_home/.config/labwc/autostart"
if [ ! -f "$labwc_autostart" ] || ! grep -q 'swayidle' "$labwc_autostart"; then
  if ! raspi-config nonint do_blanking 0; then
    warn "screen blanking was not enabled"
  else
    info "The screen blanks after 10 idle minutes. That does not lock the session."
  fi
else
  info "Screen blanking is already configured."
fi

# --- journal ---------------------------------------------------------------
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
if [ ! -f "$script_dir/journal" ]; then
  die "journal helper not found next to this script"
fi
install -m 0755 "$script_dir/journal" /usr/local/bin/journal
install -d -m 0755 /usr/local/share/applications
if [ -f "$script_dir/journal.desktop" ]; then
  install -m 0644 "$script_dir/journal.desktop" /usr/local/share/applications/journal.desktop
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/local/share/applications >/dev/null 2>&1 || true
  fi
fi
install -d -m 0700 -o "$admin" -g "$admin" "$admin_home/journal"
info "Journal directory is $admin_home/journal. The 'journal' command opens today's entry."

install -d -m 0755 /etc/motd.d
cat > /etc/motd.d/secure-journal <<'EOF'
secure-journal
  Security updates install daily. This Pi does not reboot itself: an encrypted
  disk waits for its passphrase, and nobody may be there to type it.
  After a kernel update, reboot when you can type that passphrase.
  Blanking the screen does not lock the session. Use the desktop lock when
  you step away. Shut down to lock the disk.

EOF

# --- sysctl ----------------------------------------------------------------
cat > /etc/sysctl.d/60-secure-journal.conf <<'EOF'
# Host defaults: don't accept redirects or source-routed packets.
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
EOF
if ! sysctl -q -p /etc/sysctl.d/60-secure-journal.conf; then
  warn "some sysctl settings were not applied"
fi

info "Done. Next, if this root is not encrypted yet:"
info "  sudo $script_dir/luks-prepare.sh"
info "  sudo $script_dir/luks-convert.sh /dev/sdX"
info "A 3.5\" SPI panel, if you are using one instead of the official display:"
info "  sudo $script_dir/spi-display.sh"
