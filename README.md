# Secure Journal

A Raspberry Pi 5 image you write to an SD card. On first boot the official Touch Display 2 asks for Wi-Fi and a security password. After that, the screen shows the address of a journal you open in a browser on the same network.

## What you need

- Raspberry Pi 5
- Official Raspberry Pi Touch Display 2
- microSD card, 16 GB or larger
- The usual Pi 5 power supply
- A USB keyboard is optional. The setup screen has its own keyboard.

## Flash, boot, write

1. Download `secure-journal.img.xz` from a run of the Image workflow, or build it with the steps below.
2. Write the image to the card. Raspberry Pi Imager can do this with "Use custom". On Linux:

   ```bash
   xzcat secure-journal.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
   ```

   Replace `/dev/sdX` with the card. Check the name before you run it.
3. Connect the Touch Display 2, insert the card, and power on. The first boot installs nothing else; the image already has the software.
4. On the screen, choose the Wi-Fi country, scan, and join a network. Type the Wi-Fi password with the on-screen keyboard or a USB keyboard. If an Ethernet cable is already connected, "Use Ethernet" skips Wi-Fi.
5. Set a security password and type it again. It needs 14 characters and three of: lowercase, uppercase, digit, symbol.
6. The screen then shows `https://journal.local` and the Pi's IP address.
7. On a computer on the same network, open that address. Sign in with the security password.

The browser will warn that the certificate is not from a known authority. That warning is expected. The Pi created the certificate itself on first setup, and no public authority signed it. Continue past the warning, then sign in. Prefer `https://journal.local`. Opening the raw IP address can add a name-mismatch warning when that address was not the one present at setup.

The hostname is `journal`. Avahi publishes `journal.local`.

## The journal

The page is a short list of entries by date, and a word processor for the one you have open. You can create, edit, and delete entries. Edits save on their own. The search box looks through titles and text. The editor is [TipTap](https://tiptap.dev/) (ProseMirror), built into `web/journal_app/static/editor.js`. The page does not load anything from a CDN.

## Security

The security password is stored as an Argon2id hash. A second Argon2id derivation, with its own salt, wraps a random 32-byte key, and each entry is encrypted with AES-GCM under that key. The hash is not the wrapping key. After a successful sign-in the unwrapped key is kept in the journal process's memory. Signing out, or a restart of the service, drops it, and the next visit has to sign in again.

The Pi boots to the touchscreen without asking for that password, so setup and the address stay available in the room. Encrypting the entries in the application is what makes that possible. A copied database is not readable without the password. Someone who can change the files on the card can replace the program and capture the password the next time it is typed. That is the limit of this design.

The image also:

- Drops inbound traffic in `ufw` except TCP 443 (the journal) and UDP 5353 (mDNS).
- Leaves OpenSSH installed, because the Trixie minbase includes it, and masks `ssh.service` and `ssh.socket`. The `journal` account has no password.
- Installs daily security updates from Debian security and the Raspberry Pi archive. `rpi-eeprom` is excluded. When an upgrade needs a reboot, the Pi reboots at 04:00. Autosave has already stored the open entry.

SSH stays off. Turning it on means mounting the card on another computer (the `journal` account is locked, and root has no password): unmask `ssh.service` and `ssh.socket`, give `journal` a login password, and allow port 22 in `ufw`. tty1 is the kiosk. A getty is still there on tty2 and above.

If the security password is lost, the entries cannot be decrypted. Deleting `/var/lib/secure-journal` on the card makes the next boot show setup again. That deletes the entries too.

## Develop the web app

From a checkout, with Python 3.12 or newer:

```bash
python3 -m venv .venv
.venv/bin/pip install -r web/requirements.txt
.venv/bin/python -m journal_app.init --password 'Correct-Horse-Battery' --data ./data
JOURNAL_DEV=1 JOURNAL_DATA_DIR=./data .venv/bin/python -m journal_app
```

Open http://127.0.0.1:8000 . Dev mode speaks plain HTTP on localhost and skips the self-signed certificate.

The touchscreen UI is a second process, also localhost only:

```bash
JOURNAL_DEV=1 JOURNAL_DISABLE_SYSTEMCTL=1 JOURNAL_DATA_DIR=./data-setup \
  .venv/bin/python -m journal_app.setup_server
```

That listens on http://127.0.0.1:8080 and exits if asked to bind any other address. Use an empty data directory so it still offers setup.

```bash
.venv/bin/pytest
```

Rebuild the editor after changing `web/editor/src/editor.js`:

```bash
cd web/editor
npm ci
npm run build
```

## Build the image

The image is an [rpi-image-gen](https://github.com/raspberrypi/rpi-image-gen) v2.9.0 definition, `image/config/journal.yaml`. It includes the Trixie minbase (no desktop), targets a Pi 5, and adds NetworkManager with iwd as the Wi-Fi backend. cage and Chromium run a kiosk on tty1 pointed at the setup page. The Touch Display 2 is picked up by `display_auto_detect=1` and the VC4 KMS driver already in that Pi 5 base.

Upstream supports a Debian Bookworm or Trixie arm64 machine. On one:

```bash
git clone --depth 1 --branch v2.9.0 https://github.com/raspberrypi/rpi-image-gen.git
sudo ./rpi-image-gen/install_deps.sh
sudo ./image/build.sh "$PWD/rpi-image-gen"
```

The flashable file is `dist/secure-journal.img.xz`.

The GitHub Actions workflow `Image` runs that script in a privileged Debian Trixie container on `ubuntu-24.04-arm`. Start it from the Actions tab, or push a `v*` tag to attach the image to a release as well. The `Tests` workflow runs pytest, rebuilds the editor bundle, and shellchecks the image scripts. It does not boot a Pi.

## Not covered by the automated tests

The tests check password rules, Argon2id, AES-GCM, entry storage, sessions, login rate limiting, the setup API (with stand-in `nmcli` and `ip` commands), and the image install hook against an empty directory. They do not flash a card, join a real network, light a Touch Display 2, or walk through the browser certificate warning. Those still need a Pi 5 and the display.
