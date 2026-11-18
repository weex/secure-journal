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

SSH is optional. The next section is the touchscreen path: the same card, no second computer after this one is ejected.

## Touchscreen setup

Writing the card still needs another computer. The boot ROM only starts from a card that already has firmware, so it cannot download this setup by itself. After the card is written, the first boot can be done from the touchscreen.

1. In Imager 2, write the desktop image. Set a username and a temporary password, or leave customisation empty so the official first-boot wizard creates the account on the screen. Wi-Fi and SSH can be left unset.
2. While the boot partition is still mounted (the volume that contains `config.txt` and `user-data`):

```bash
git clone https://github.com/weex/secure-journal.git
cd secure-journal
./scripts/prepare-card.sh /path/to/boot/partition
```

`prepare-card.sh` copies this repository onto that FAT partition and adds one `runcmd` to `user-data`. It does not change the user, the password, or the Wi-Fi block Imager wrote. Cloud-init only reads the file when the first line is `#cloud-config`, which is what Imager 2 and the current Trixie images write. The format is described in [Cloud-init on Raspberry Pi OS](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/). If the file is not in that form, the script stops and leaves it unchanged.

3. Put the card in the Pi, connect the touchscreen, and power on. Log in. The wizard opens in the desktop session, which is where the on-screen keyboard can follow a text field.

The wizard is GTK 3. That is the toolkit on the Raspberry Pi OS desktop, and squeekboard is wired to its text fields. A browser would be a second stack, and it is slow on a Pi 3. The window is one column inside a scrolled view, so a 3.5" panel can still reach the buttons when the keyboard is open.

On the screen:

* Set the Wi-Fi country (the radio stays off until a country is set) and join a network, or skip this when Ethernet is already connected. The Wi-Fi password is handed to NetworkManager with `nmcli connection up ... passwd-file`. `nmcli device wifi connect` only accepts the password as an argument, so the wizard does not use that form.
* Choose a login password and a disk passphrase. Each needs 14 characters and three of lowercase, uppercase, digit, and symbol. A short common-password list is rejected. The two secrets have to be different. The meter runs on the Pi. The passphrase is not sent anywhere.
* Pick a spare disk. The wizard runs `harden.sh`, then `luks-convert.sh`. Encrypting the card the Pi booted from is not implemented. That would rewrite the disk the system is running from, and a failed conversion would leave nothing that boots. The FAT boot partition stays unencrypted either way: the boot ROM cannot unlock LUKS.
* Continuing without a spare disk is a separate button, and the journal then says the disk is not encrypted. There is no silent skip.

The spare disk is the encrypted copy. Power off, move that card into the Pi, and power on. The original card is still the backup until the new one has unlocked and the journal is there.

The passphrase prompt at that boot is not the desktop. Debian Trixie ships `unl0kr` 2.0.3+dfsg-2, a small touch keyboard that draws on the framebuffer from the initramfs. `scripts/unlock-keyscript` runs it and, if there is no display device or it fails, asks on the text console instead. The Pi firmware does not drive the Touch Display 2 (Raspberry Pi's display documentation and the firmware authors are explicit that the panel comes up with the kernel driver). The keyscript loads `panel-ilitek-ili9881c` and `goodix` when the kernel has them, which is the Touch Display 2 overlay (`vc4-kms-dsi-ili9881`, Goodix GT911), or `ili9486` and `ads7846` for a 3.5" SPI panel, then waits up to 20 seconds for `/dev/dri/card0` or `/dev/fb0`. Raspberry Pi documents the initramfs as an advanced mechanism and does not ship this integration. It has to be confirmed on the hardware.

If the passphrase screen never appears, power off and add one token to the end of `cmdline.txt` on the FAT boot partition. That file is readable without the passphrase:

```
sj.unlock=console
```

Boot with HDMI and a USB keyboard. A 3.5" SPI panel often stays dark until the desktop even when the modules are in the initramfs. Use the HDMI fallback for the first encrypted boot on that panel.

The official Touch Display 2 does not need an overlay. The SPI button in the wizard runs `scripts/spi-display.sh` and reboots. It is the same block as the manual step in the display section.

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

The passphrase prompt at boot is the initramfs keyboard described in the touchscreen section, not this desktop. An SPI panel often stays dark until the desktop starts. Have an HDMI cable and a USB keyboard for that first encrypted boot, or add `sj.unlock=console` to `cmdline.txt`.

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

Power off. Move the new card into the Pi's slot (or leave a USB disk attached and set the boot order if you intend to boot from it). Power on. Enter the disk passphrase on the touchscreen keyboard, or with a USB keyboard if you set `sj.unlock=console` or the panel stayed dark. Then enter the login password at the desktop.

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
* The on-screen keyboard at the disk prompt is `unl0kr`, inside the initramfs. The desktop keyboard is squeekboard, including the greeter. They are different programs. If the disk prompt does not appear on the panel, use `sj.unlock=console` and a USB keyboard.

## Scripts

| Script | Runs | What it does |
| --- | --- | --- |
| `scripts/prepare-card.sh` | On the computer that wrote the card | Copies this repository to the FAT boot partition and adds a cloud-init runcmd |
| `scripts/bootstrap.sh` | Root, on the Pi, safe to repeat | Installs the wizard's packages and the desktop autostart |
| `scripts/launch-session` | Graphical login | Opens the wizard until setup is finished, then the journal |
| `scripts/harden.sh` | Repeat safely | Updates, firewall, SSH, sudo password, autologin, keyboard, journal directory |
| `scripts/spi-display.sh` | Repeat safely | One `config.txt` block for a 3.5" SPI panel |
| `scripts/luks-prepare.sh` | Repeat safely | Installs cryptsetup and the unlock UI, and rebuilds the initramfs. Does not encrypt |
| `scripts/luks-unlock-ui.sh` | Repeat safely | Installs the initramfs keyscript and, with `--with-packages`, `unl0kr` |
| `scripts/luks-convert.sh` | Erases the disk you name | Writes a LUKS root onto a spare disk |
| `scripts/wifi-join.sh` | | Country, scan, and a NetworkManager connection. The Wi-Fi password is a file |
| `scripts/setup-apply.sh` | Root, from the wizard | Checks the passphrases, runs harden, then the LUKS copy |
| `scripts/journal` | | Opens today's entry in the touchscreen app, or Mousepad, or nano |

`tests/spi-display.sh` checks that the config block can be rewritten without losing the rest of `config.txt`. `tests/luks-metadata.sh` checks the cmdline and fstab rewrite and that the LUKS header is the pinned cipher and Argon2 cost. `tests/luks-convert-loop.sh` runs the copy onto loop devices when the kernel has device-mapper. `tests/python.sh` checks the passphrase meter, the Wi-Fi and disk parsers, and the journal files. `tests/user-data-merge.sh`, `tests/wifi-join.sh`, `tests/unlock-keyscript.sh`, and `tests/setup-apply.sh` cover the wizard's shell without a radio, a display, or a Pi. None of these is a substitute for booting a Pi.

## Needs a real Pi

The steps were checked against Raspberry Pi's documentation for installing an image, SSH, `config.txt`, the Touch Display 2, the 2022 removal of the default user, cloud-init on Trixie, Imager's customisation formats, and Debian Trixie's `unl0kr` package. `shellcheck` is clean on the scripts. In this environment the kernel has no device-mapper, so the tests covered the `config.txt` block, the convert script's refusals, the cmdline and fstab rewrite, a real LUKS2 header with the pinned cipher and Argon2 cost, the cloud-init runcmd merge, the passphrase rules, the Wi-Fi and disk parsers, the unlock keyscript's console fallback, and `setup-apply.sh` refusing a weak or mismatched passphrase before it changes anything. They did not boot a Pi, join a network, or open the GTK windows. These still need hardware:

* Imager 2 customisation on a current Trixie image: user, Wi-Fi country, and SSH key, then SSH to `hostname.local`.
* Touchscreen path: `prepare-card.sh` on the boot partition, first boot, log in with the on-screen keyboard, wizard opens without an SSH session.
* Wizard Wi-Fi: country code, scan, join, and Ethernet skip. Confirm the password is not required on a second boot.
* Wizard passphrases: the meter rejects a short password and accepts a long mixed one; the disk passphrase and the login password have to differ.
* `harden.sh` from the wizard or by hand: `ufw`, `sshd -T`, a second key-based login if SSH is in use, sudo prompting, the desktop asking for a password, the on-screen keyboard, and `unattended-upgrade --dry-run`.
* Touch Display 2: picture and touch in the wizard, squeekboard in a text field and on the greeter, then the disk passphrase on `unl0kr` after the encrypted card is booted. Time how long the panel stays dark.
* A 3.5" SPI panel: the wizard's SPI button or `scripts/spi-display.sh`, then rotation and touch axes. Expect the disk prompt to need HDMI. Confirm whether `unl0kr` appears on that panel at all.
* `sj.unlock=console` on `cmdline.txt`: the on-screen UI is skipped and a USB keyboard on HDMI can unlock.
* `luks-convert.sh` onto a spare card, from the wizard or the shell: passphrase, desktop login, journal file present, reboot asks again. Time the unlock on a Pi 3 if that is the board. Confirm a wrong passphrase is rejected and the right one still works.
* Continue without encryption: the journal shows that the disk is not encrypted, and "Set up encryption" opens the wizard again.
* A kernel update from unattended-upgrades, then a manual reboot, to confirm the new initramfs still runs `unl0kr` and unlocks.

## Layout

```
scripts/prepare-card.sh    stage the wizard onto a freshly written card
scripts/bootstrap.sh       install packages and the desktop autostart
scripts/launch-session     wizard, then the journal
ui/                        GTK wizard, journal app, and the testable rules
scripts/harden.sh          firewall, updates, SSH, passwords
scripts/spi-display.sh     optional 3.5" SPI panel
scripts/luks-prepare.sh    initramfs support, no encryption yet
scripts/luks-unlock-ui.sh  unl0kr keyscript and display modules
scripts/luks-convert.sh    LUKS root on a spare disk
scripts/journal            open today's entry
tests/                     parsers, cloud-init merge, LUKS header, loopback
```
