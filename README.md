# secure-journal

A small Wi-Fi journal: a Raspberry Pi with a touchscreen, an encrypted root filesystem, daily security updates, and an SSH login that uses keys.

The current target is [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/) 64-bit, based on Debian 13 (Trixie). The images published on 6 October 2026 use kernel 6.18. The desktop image is the one this setup expects. Lite has no touchscreen session. The "Full" image adds applications a journal does not need.

This is a one-machine setup for a Pi 3, 4, or 5. It is not a managed fleet, and it does not program the Pi's one-time memory.

## What is protected

| Threat | What holds |
| --- | --- |
| The microSD card (or SSD) is removed and read on another computer | The root filesystem is LUKS2. The journal is on that filesystem. |
| The Pi is stolen while it is switched off | The same passphrase is required before Linux starts. |
| Someone is on the network | The firewall drops inbound connections other than rate-limited SSH. SSH rejects passwords once a key is installed, and rejects root login. |
| Packages with security fixes | `unattended-upgrades` installs Debian security updates and Raspberry Pi archive updates every day. |

Two limits are structural:

* The FAT boot partition stays readable. The Pi's boot ROM cannot unlock LUKS, so the kernel and initramfs sit in the clear. Someone with the card can replace those files. They still cannot read the journal without the passphrase. Raspberry Pi's [Secure Boot Provisioner](https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/security/secure-boot-provisioner/secure-boot-provisioner.adoc) can go further (signed boot, unlock from a device-unique OTP secret, no passphrase). Programming OTP is permanent, and that unlock has no passphrase, so it is a different tool than this one.
* After the passphrase is entered, the disk stays open until shutdown. Locking or blanking the screen locks the session. Shut the Pi down to lock the disk.

The disk passphrase and the login password are different secrets. Write the disk passphrase down and keep it away from the Pi. There is no recovery copy on the card. A lost passphrase is a lost journal.

## Hardware

US list prices after the memory adjustments announced on 1 December 2025, 2 February 2026, 1 April 2026, and 1 October 2026. The 16GB Pi 5 at $305 is the figure on the [Pi 5 product page](https://www.raspberrypi.com/products/raspberry-pi-5/). The 4GB and 8GB figures are those increases added up, and they match approved-reseller listings in November 2026. Raspberry Pi has described the increases as temporary. Check the product page before buying.

| Part | Price | Why this one |
| --- | --- | --- |
| Raspberry Pi 5, 4GB | $110 | Comfortable Wayland desktop. 2GB ($77.50) is enough for text. 8GB is $175 and 16GB is $305; a journal does not need either. The 1GB Pi 5 is still $45 and is tight for this desktop. |
| [Touch Display 2](https://www.raspberrypi.com/products/touch-display-2/), 5-inch | $40 | Official DSI panel. Pi 3, 4, and 5 detect the 5-inch and 7-inch models. The 7-inch is $60. The 10-inch is $80 and works with Pi 5 only. |
| Raspberry Pi 27W USB-C supply | about $13 | The supply Raspberry Pi recommends for a Pi 5. A Pi 4 supply can leave a Pi 5 short. |
| 64GB A2 microSD card | current card price | The October 2026 desktop image wants about 6.4GB. 64GB leaves room for the journal. |

A 4GB Pi 5, the 5-inch display, and the official supply are about $163 before the card and any case. The display is powered from the Pi (the GPIO power cable plus the flat cable in the box). Disconnect power before plugging those in, and follow the [Touch Display 2 installation steps](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html): on a Pi 5 the flat cable is the supplied 22-way to 15-way cable, larger end into the display; on a Pi 4 or earlier it is the 15-way cable. With the USB sockets facing down, the red wire goes to the top-right GPIO pin (pin 2, 5V) and the black wire to pin 6 (ground).

A Pi 4 2GB is $67.50 if you already have a display and a USB-C supply. A Pi 3 still runs the 64-bit image and was left out of the memory price rises; 1GB of RAM makes the desktop slow, and the disk unlock below is tuned so that a Pi 3 can still open the volume.

### A 3.5" SPI panel you already own

The GPIO touchscreens sold with `LCD-show` instructions (goodtft LCD35, Waveshare 3.5, and the ILI9486 clones) still work, using the kernel overlay in `scripts/spi-display.sh`. They occupy the GPIO header, so they are an alternative to the official display, not a second screen beside it. Expect a dim, slow panel. It is fine for text.

### January 2021 list

Kept so the old total is still readable. Those steps are not the setup procedure anymore.

* Raspberry Pi 3, $38.33
* 16GB microSD card, $7.65
* Touchscreen module and case, $26.25
* Power supply, $7.65
* Total, $79.88

## What changed since that procedure

The January 2021 notes matched Raspberry Pi OS at the time: flash with balenaEtcher, drop an empty file named `ssh` on the boot partition, log in as `pi` / `raspberry`, set Wi-Fi in `raspi-config`, and run `LCD35-show`. The pieces that replaced that path:

* There is no default `pi` / `raspberry` account. It was removed in April 2022. You create the user while writing the card. The name `pi` with the password `raspberry` is still accepted if you type it, and the first-boot wizard warns you; use a real password.
* [Raspberry Pi Imager](https://www.raspberrypi.com/software/) writes the user, Wi-Fi, locale, and SSH key. Use Imager 2.x. Imager 1.x does not understand the customisation format on current Trixie images (`cloudinit-rpi`) and the settings are silently ignored. The format note is in the [Imager repository](https://github.com/raspberrypi/rpi-imager/blob/main/doc/os_customisation_formats.md). Current Trixie images apply that customisation with [cloud-init](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/).
* The boot partition on a running Bookworm or Trixie system is mounted at `/boot/firmware`. `config.txt` and `cmdline.txt` live there. An empty file named `ssh` on that FAT partition still enables the SSH server, which is the [manual method](https://www.raspberrypi.com/documentation/computers/remote-access.html) in the official docs. It does not create a user.
* Wi-Fi is NetworkManager, from Bookworm onward. The desktop network menu and `nmcli` are the tools. `raspi-config` can still set a network.
* The desktop is Wayland (labwc). `LCD-show` installs the older framebuffer driver and points the session at X11. On a current image that leaves the SPI panel dark and breaks the desktop. The in-tree `piscreen` overlay with `drm` is the replacement.
* Official [install steps](https://www.raspberrypi.com/documentation/computers/getting-started.html) are Imager, then the first boot.

## 1. Write the card

On a computer with an SD reader:

1. Install Raspberry Pi Imager **2.x** from the [software page](https://www.raspberrypi.com/software/). On Raspberry Pi OS the package is `rpi-imager`. On other Linux, use the AppImage from that page.
2. Choose the Pi model, then **Raspberry Pi OS (64-bit)** with the desktop (the recommended entry). Choose the microSD card.
3. In OS customisation, set:
   * hostname, for example `journal` (you will use `journal.local`)
   * a lowercase username and a long password (14 characters or more; this is also the `sudo` password)
   * the Wi-Fi network, and the country when Imager asks for it (Wi-Fi stays down until a regulatory country is set)
   * SSH enabled, **public-key authentication** (the key from this computer)
   * timezone and keyboard
   * Raspberry Pi Connect left off
4. Write the card, put it in the Pi, connect the display, and power it.

The first boot runs cloud-init before SSH answers. Give it a couple of minutes. Then, from the computer that holds the private key:

```bash
ssh USER@journal.local
```

`USER` is the name you set. If mDNS does not resolve, use the address from the router.

A wired Ethernet cable is a useful first boot when the Wi-Fi country or the SSID needs another try. Once you are in, NetworkManager is the configuration tool:

```bash
nmcli dev wifi list
sudo nmcli dev wifi connect "SSID" --ask
```

## 2. Harden the system

On the Pi:

```bash
sudo apt update
sudo apt full-upgrade
git clone https://github.com/weex/secure-journal.git
cd secure-journal
sudo ./scripts/harden.sh
```

The script is safe to run again. It:

* installs daily security updates, including the Raspberry Pi archive (kernel and firmware), and leaves `rpi-eeprom` out of that automatic set
* turns on `ufw`, default deny inbound, rate-limited SSH
* turns off SSH root login and, when `~/.ssh/authorized_keys` already has a key, turns off SSH password login
* makes `sudo` ask for the login password
* boots to the desktop and asks for that password (console autologin is off as well, so a text console is not a way around the screen lock)
* enables the on-screen keyboard when a touchscreen is present, and blanks the screen after 10 idle minutes
* requires 14 mixed characters the next time the login password is changed
* creates `~/journal` mode `0700` and installs a `journal` command

Open a second SSH session with the key before closing the first one, so a mistake in the client config does not lock you out. The script does not enable passwordless SSH by itself: the key has to be the one Imager installed, or one you added to `~/.ssh/authorized_keys`.

`rpi-update` is not part of this. It installs pre-release firmware. Updates come from `apt`.

Check the result:

```bash
sudo ufw status
sudo sshd -T | grep -E '^(passwordauthentication|permitrootlogin|pubkeyauthentication) '
sudo unattended-upgrade --dry-run --debug
```

`passwordauthentication` should be `no`, and `permitrootlogin` should be `no`. If `unattended-upgrade` reports allowed origins that do not include `Debian-Security` and `Raspberry Pi Foundation`, compare them with `apt-cache policy` and edit `/etc/apt/apt.conf.d/52secure-journal-unattended`. The strings written by the script match the Trixie and Bookworm archives as documented in 2026; a renamed origin would match nothing and would fail silently.

The Pi does not reboot for those updates. A kernel update sits in `/var/run/reboot-required` until you reboot, and an encrypted root will ask for the disk passphrase at that reboot. Update the bootloader EEPROM when you are ready to do that on purpose:

```bash
sudo apt install --only-upgrade rpi-eeprom
```

## 3. Display

**Touch Display 2.** No driver install. The panel is detected. The on-screen keyboard appears when a text field needs it. If the picture is sideways, the Screen Configuration tool (or `wlr-randr`) rotates it.

**3.5" SPI panel.** From the cloned repository:

```bash
sudo ./scripts/spi-display.sh
sudo reboot
```

That writes one block to `/boot/firmware/config.txt`:

```
dtoverlay=piscreen,drm,rotate=90,speed=18000000
```

`drm` is what makes the panel a KMS display under Wayland. The parameter list is the `piscreen` section of `/boot/firmware/overlays/README` on the Pi. Clones disagree about rotation and which touch axis is which. If the colours break, lower `speed`. If taps land in the wrong place, re-run with something like:

```bash
sudo SPI_DTPARAM='piscreen,drm,rotate=270,speed=16000000,invx,swapxy' ./scripts/spi-display.sh
sudo reboot
```

Running `LCD-show` on this image is the step that breaks the desktop. The script does not clone that repository.

The passphrase prompt at boot is not this desktop. Have an HDMI cable and a USB keyboard for the first encrypted boot. An SPI panel often stays dark until the desktop starts.

## 4. Encrypt the root filesystem

You need a second disk at least as large as the used space plus about 1GB: another microSD card in a USB reader, or a USB SSD. The script copies the running system onto that disk, with the root inside LUKS2, and does not write to the disk you booted from. If the copy fails, the original card still boots.

```bash
lsblk
sudo ./scripts/luks-prepare.sh
sudo ./scripts/luks-convert.sh /dev/sda
```

`lsblk` is how you tell the spare disk from the one you booted from. The script refuses if you name the live disk, a partition, or a disk that is mounted. It asks you to type `ERASE /dev/sda` (with the real name) and then a passphrase of at least 14 characters, twice. The passphrase is not a command-line argument.

What the script pins, and why:

* LUKS2, `aes-xts-plain64`, 512-bit key, Argon2id.
* Argon2 memory is fixed at 64MB and the iteration time at 2 seconds. cryptsetup's default memory cost follows the RAM of the machine doing the format. A cost picked on a Pi 5 can then fail in the initramfs, and a Pi 3 has 1GB total. Two seconds per guess is the cost an offline attacker pays; unlock on a Pi 3 stays possible.
* `/etc/crypttab` points at the partition's `PARTUUID`, so the same card works in the SD slot or a USB reader.
* The initramfs is built with `MODULES=most` and `CRYPTSETUP=y`. The stock `MODULES=dep` image only copies modules the running system is using, and `dm-crypt` is not one of them until the disk is already encrypted.
* The boot partition is FAT, 512MB, with the boot flag set. `cmdline.txt` sets `root=/dev/mapper/cryptroot`. `auto_initramfs=1` (the Trixie default) makes the bootloader load the initramfs. Raspberry Pi documents initramfs as an advanced mechanism and does not ship an encryption tutorial; this uses Debian's `cryptsetup-initramfs`, which Raspberry Pi OS includes.

Power off. Move the new card into the Pi's slot (or leave a USB disk attached and set the boot order if you intend to boot from it). Connect HDMI and a USB keyboard. Power on, type the disk passphrase at the text prompt, then the login password at the desktop.

Confirm the journal file is there. The original card is still unencrypted. It is the backup until that check passes. Then wipe it (`wipefs -a` on each partition, or Imager's erase) before it lives in a drawer next to the Pi.

Re-running `luks-convert.sh` on the same spare disk erases it and writes a fresh copy. It does not "continue" a half-finished card.

To change the passphrase later, on the running system:

```bash
lsblk -o NAME,TYPE,PARTUUID
sudo cryptsetup luksChangeKey /dev/disk/by-partuuid/PARTUUID-OF-THE-LUKS-PARTITION
```

`cryptsetup luksAddKey` adds a second keyslot if you want a recovery passphrase stored somewhere other than the Pi. Do not put a key file on the FAT boot partition.

## Daily use

On the desktop, **Journal** opens today's file. From a terminal, `journal` does the same. Entries are Markdown files under `~/journal/YYYY/MM/YYYY-MM-DD.md`, mode `0600`, in a directory mode `0700`.

* Step away: lock the screen from the desktop menu (Shutdown, then Lock Screen). Blanking after 10 minutes hides the picture and does not ask for the password.
* Finished for the day: shut down. That is what locks the disk.
* The on-screen keyboard is for the desktop and the greeter. It is not available at the disk-unlock prompt.

## Scripts

| Script | Runs | What it does |
| --- | --- | --- |
| `scripts/harden.sh` | Repeat safely | Updates, firewall, SSH, sudo password, autologin, keyboard, journal directory |
| `scripts/spi-display.sh` | Repeat safely | One `config.txt` block for a 3.5" SPI panel |
| `scripts/luks-prepare.sh` | Repeat safely | Installs cryptsetup and rebuilds the initramfs. Does not encrypt |
| `scripts/luks-convert.sh` | Erases the disk you name | Writes a LUKS root onto a spare disk |
| `scripts/journal` | | Opens today's entry |

`tests/spi-display.sh` checks that the config block can be rewritten without losing the rest of `config.txt`. `tests/luks-metadata.sh` checks the cmdline and fstab rewrite and that the LUKS header is the pinned cipher and Argon2 cost. `tests/luks-convert-loop.sh` runs the copy onto loop devices when the kernel has device-mapper. None of these is a substitute for booting a Pi.

## Needs a real Pi

The steps were checked against Raspberry Pi's documentation for installing an image, SSH, `config.txt`, the Touch Display 2, the 2022 removal of the default user, cloud-init on Trixie, and Imager's customisation formats. `shellcheck` is clean on the scripts. In this environment the kernel has no device-mapper, so the tests covered the `config.txt` block, the convert script's refusals, the cmdline and fstab rewrite, and a real LUKS2 header with the pinned cipher and Argon2 cost. They did not boot a Pi. These still need hardware:

* Imager 2 customisation on a current Trixie image: user, Wi-Fi country, and SSH key, then SSH to `hostname.local`.
* `harden.sh` on the Pi: `ufw`, `sshd -T`, a second key-based login, sudo prompting, the desktop asking for a password, the on-screen keyboard, and `unattended-upgrade --dry-run`.
* Touch Display 2: picture, touch, and the on-screen keyboard in a text field, including the greeter after a lock.
* A 3.5" SPI panel: `scripts/spi-display.sh`, then rotation and touch axes for that exact clone. Confirm whether the disk passphrase prompt appears on that panel.
* `luks-convert.sh` onto a spare card, then a real boot: passphrase on HDMI, desktop login, journal file present, reboot asks again. Time the unlock on a Pi 3 if that is the board.
* A kernel update from unattended-upgrades, then a manual reboot, to confirm the new initramfs still unlocks.

## Layout

```
scripts/harden.sh          first-boot hardening
scripts/spi-display.sh     optional 3.5" SPI panel
scripts/luks-prepare.sh    initramfs support, no encryption yet
scripts/luks-convert.sh    LUKS root on a spare disk
scripts/journal            open today's entry
tests/                     config.txt, LUKS header, and loopback checks
```
