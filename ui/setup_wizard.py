"""First-boot wizard for the touchscreen.

GTK 3 is what the Raspberry Pi OS desktop ships, and squeekboard shows for
a focused Gtk.Entry. The window is a single column inside a scrolled view
so a 3.5 inch panel can still reach the buttons when the keyboard is open.

Encryption is the spare-disk copy in luks-convert.sh. There is no in-place
path; ui.disks explains why.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from ui.apply_cmd import apply_invocation, apply_stdin
from ui.disks import (
    IN_PLACE_REASON,
    confirmation_matches,
    erase_confirmation,
    parse_lsblk_pairs,
    spare_candidates,
)
from ui.passphrase import assess
from ui.setup_state import clear_stamp, write_stamp
from ui.wifi_nm import parse_wifi_list

ROOT = Path(__file__).resolve().parents[1]
WIFI = ROOT / "scripts" / "wifi-join.sh"
APPLY = ROOT / "scripts" / "setup-apply.sh"
SPI = ROOT / "scripts" / "spi-display.sh"


def wrapping(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_line_wrap(True)
    label.set_xalign(0)
    label.set_max_width_chars(42)
    return label


def section(title: str) -> Gtk.Label:
    label = Gtk.Label(label=title)
    label.set_xalign(0)
    label.get_style_context().add_class("title")
    return label


class SetupWizard(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="Journal setup")
        self.set_default_size(480, 320)
        self._selected_disk = ""
        self._busy = False
        self._build()
        self.maximize()

    def _build(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window { font-size: 16px; }
            entry { min-height: 36px; }
            button { min-height: 44px; }
            .title { font-size: 20px; font-weight: bold; }
            """
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_margin_top(8)
        outer.set_margin_bottom(8)
        outer.set_margin_start(8)
        outer.set_margin_end(8)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.add_named(self._welcome(), "welcome")
        self.stack.add_named(self._wifi(), "wifi")
        self.stack.add_named(self._secrets(), "secrets")
        self.stack.add_named(self._encrypt(), "encrypt")
        self.stack.add_named(self._working(), "working")
        self.stack.add_named(self._done(), "done")
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.stack)
        outer.pack_start(scroll, True, True, 0)
        self.error = wrapping("")
        self.error.get_style_context().add_class("error")
        outer.pack_start(self.error, False, False, 0)
        self.add(outer)

    def _set_error(self, text: str) -> None:
        self.error.set_text(text)

    def _page(self, *rows: Gtk.Widget) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)
        for row in rows:
            box.pack_start(row, False, False, 0)
        return box

    def _welcome(self) -> Gtk.Box:
        spi = Gtk.Button(label="This is a 3.5 inch SPI panel")
        spi.connect("clicked", self._on_spi)
        nxt = Gtk.Button(label="Continue")
        nxt.connect("clicked", lambda _b: self.stack.set_visible_child_name("wifi"))
        return self._page(
            section("Set up this journal"),
            wrapping(
                "Use the on-screen keyboard. You will join Wi-Fi, choose a "
                "login password and a separate disk passphrase, turn on "
                "security updates and the firewall, and copy the system onto "
                "a spare disk with the root encrypted."
            ),
            wrapping(
                "The official Touch Display 2 works without an extra driver. "
                "A 3.5 inch SPI panel stays dark on a stock image until its "
                "overlay is installed. That button writes the overlay and reboots."
            ),
            spi,
            nxt,
        )

    def _on_spi(self, _button: Gtk.Button) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Enable the 3.5 inch SPI panel and reboot?",
        )
        dialog.format_secondary_text(
            "The official Touch Display 2 does not need this. The Pi reboots immediately."
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        result = self._sudo([str(SPI), "--reboot"])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "sudo failed").strip()
            self._set_error(detail)

    def _wifi(self) -> Gtk.Box:
        self.country = Gtk.Entry()
        self.country.set_placeholder_text("Country code, for example GB")
        self.country.set_max_length(2)
        self.country.set_input_purpose(Gtk.InputPurpose.ALPHA)
        self.wifi_sudo = Gtk.Entry()
        self.wifi_sudo.set_visibility(False)
        self.wifi_sudo.set_placeholder_text("Current login password, if sudo asks")
        self.wifi_sudo.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        country_btn = Gtk.Button(label="Set country and scan")
        country_btn.connect("clicked", self._on_country)
        self.networks = Gtk.ListBox()
        self.networks.set_selection_mode(Gtk.SelectionMode.SINGLE)
        net_scroll = Gtk.ScrolledWindow()
        net_scroll.set_min_content_height(120)
        net_scroll.add(self.networks)
        self.wifi_pass = Gtk.Entry()
        self.wifi_pass.set_visibility(False)
        self.wifi_pass.set_placeholder_text("Wi-Fi password, empty if the network is open")
        self.wifi_pass.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        show = Gtk.CheckButton(label="Show Wi-Fi password")
        show.connect("toggled", lambda b: self.wifi_pass.set_visibility(b.get_active()))
        join = Gtk.Button(label="Join selected network")
        join.connect("clicked", self._on_join)
        nxt = Gtk.Button(label="Continue")
        nxt.connect("clicked", self._go_secrets)
        return self._page(
            section("Wi-Fi"),
            wrapping(
                "Wi-Fi stays off until a country is set. Ethernet can skip this page. "
                "The password is passed to NetworkManager in a file, not on the command line."
            ),
            self.country,
            self.wifi_sudo,
            country_btn,
            net_scroll,
            self.wifi_pass,
            show,
            join,
            nxt,
        )

    def _sudo(self, args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        # Imager's first user can sudo without a password. Only read the
        # password field when that is not the case, so a filled-in field
        # does not become the Wi-Fi password by mistake.
        if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0:
            return subprocess.run(["sudo", "-n", *args], input=stdin, capture_output=True, text=True)
        password = self.wifi_sudo.get_text()
        if not password:
            return subprocess.run(["sudo", "-n", *args], input=stdin, capture_output=True, text=True)
        return subprocess.run(
            ["sudo", "-k", "-S", "-p", "", *args],
            input=password + "\n" + (stdin or ""),
            capture_output=True,
            text=True,
        )

    def _go_secrets(self, _button: Gtk.Button) -> None:
        if not self.current.get_text():
            self.current.set_text(self.wifi_sudo.get_text())
        self.stack.set_visible_child_name("secrets")

    def _on_country(self, _button: Gtk.Button) -> None:
        code = self.country.get_text().strip()
        result = self._sudo([str(WIFI), "country", code])
        if result.returncode != 0:
            self._set_error((result.stderr or result.stdout or "could not set the country").strip())
            return
        self._set_error("")
        self._refresh_networks()

    def _refresh_networks(self) -> None:
        result = subprocess.run([str(WIFI), "scan"], capture_output=True, text=True)
        if result.returncode != 0:
            self._set_error((result.stderr or "Wi-Fi scan failed").strip())
            return
        for child in self.networks.get_children():
            self.networks.remove(child)
        for row in parse_wifi_list(result.stdout):
            mark = "connected, " if row["in_use"] else ""
            label = Gtk.Label(
                label=f"{row['ssid']}  ({mark}{row['signal']}%, {row['security']})"
            )
            label.set_xalign(0)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            label.set_margin_start(6)
            holder = Gtk.ListBoxRow()
            holder.add(label)
            holder.ssid = row["ssid"]  # type: ignore[attr-defined]
            self.networks.add(holder)
        self.networks.show_all()

    def _on_join(self, _button: Gtk.Button) -> None:
        selected = self.networks.get_selected_row()
        if selected is None:
            self._set_error("Select a network first.")
            return
        ssid = selected.ssid  # type: ignore[attr-defined]
        result = self._sudo([str(WIFI), "connect", ssid], self.wifi_pass.get_text() + "\n")
        if result.returncode != 0:
            self._set_error((result.stderr or result.stdout or "could not join").strip())
            return
        self.wifi_pass.set_text("")
        self._set_error(f"Joined {ssid}.")
        self._refresh_networks()

    def _secrets(self) -> Gtk.Box:
        self.current = Gtk.Entry()
        self.current.set_visibility(False)
        self.current.set_placeholder_text("Current login password, if sudo asks")
        self.current.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.login = Gtk.Entry()
        self.login.set_visibility(False)
        self.login.set_placeholder_text("New login password")
        self.login.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.login2 = Gtk.Entry()
        self.login2.set_visibility(False)
        self.login2.set_placeholder_text("Repeat login password")
        self.login2.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.login_meter = Gtk.LevelBar()
        self.login_meter.set_max_value(4)
        self.login_summary = wrapping("Login password: not entered yet.")
        self.login.connect("changed", lambda _e: self._show_strength(self.login, self.login_meter, self.login_summary, "Login password"))
        self.disk = Gtk.Entry()
        self.disk.set_visibility(False)
        self.disk.set_placeholder_text("Disk passphrase")
        self.disk.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.disk2 = Gtk.Entry()
        self.disk2.set_visibility(False)
        self.disk2.set_placeholder_text("Repeat disk passphrase")
        self.disk2.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.disk_meter = Gtk.LevelBar()
        self.disk_meter.set_max_value(4)
        self.disk_summary = wrapping("Disk passphrase: not entered yet.")
        self.disk.connect("changed", lambda _e: self._show_strength(self.disk, self.disk_meter, self.disk_summary, "Disk passphrase"))
        show = Gtk.CheckButton(label="Show passwords")
        show.connect("toggled", self._toggle_secrets)
        nxt = Gtk.Button(label="Continue")
        nxt.connect("clicked", self._on_secrets_continue)
        back = Gtk.Button(label="Back")
        back.connect("clicked", lambda _b: self.stack.set_visible_child_name("wifi"))
        return self._page(
            section("Passphrases"),
            wrapping(
                "The login password unlocks the desktop and sudo. The disk "
                "passphrase unlocks the journal after a shutdown. They are "
                "different secrets. Nothing stores a recovery copy of the disk passphrase."
            ),
            self.current,
            self.login,
            self.login2,
            self.login_meter,
            self.login_summary,
            self.disk,
            self.disk2,
            self.disk_meter,
            self.disk_summary,
            show,
            back,
            nxt,
        )

    def _toggle_secrets(self, button: Gtk.CheckButton) -> None:
        visible = button.get_active()
        for entry in (self.current, self.login, self.login2, self.disk, self.disk2):
            entry.set_visibility(visible)

    def _show_strength(self, entry: Gtk.Entry, meter: Gtk.LevelBar, label: Gtk.Label, title: str) -> None:
        result = assess(entry.get_text())
        meter.set_value(result["score"])
        label.set_text(f"{title}: {result['summary']}")

    def _on_secrets_continue(self, _button: Gtk.Button) -> None:
        login = self.login.get_text()
        disk = self.disk.get_text()
        if login != self.login2.get_text():
            self._set_error("The login passwords do not match.")
            return
        if disk != self.disk2.get_text():
            self._set_error("The disk passphrases do not match.")
            return
        login_result = assess(login)
        disk_result = assess(disk)
        if not login_result["accepted"]:
            self._set_error("Login password: " + "; ".join(login_result["reasons"]))
            return
        if not disk_result["accepted"]:
            self._set_error("Disk passphrase: " + "; ".join(disk_result["reasons"]))
            return
        if login == disk:
            self._set_error("Use a different secret for the disk than for the login.")
            return
        self._set_error("")
        self._load_disks()
        self.stack.set_visible_child_name("encrypt")

    def _encrypt(self) -> Gtk.Box:
        self.disk_list = Gtk.ListBox()
        self.disk_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.disk_list.connect("row-selected", self._on_disk_selected)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(100)
        scroll.add(self.disk_list)
        refresh = Gtk.Button(label="Refresh disk list")
        refresh.connect("clicked", lambda _b: self._load_disks())
        self.erase = Gtk.Entry()
        self.erase.set_placeholder_text("Type ERASE and the device name")
        go = Gtk.Button(label="Encrypt onto the selected disk")
        go.connect("clicked", self._on_encrypt)
        skip = Gtk.Button(label="Continue without encryption")
        skip.connect("clicked", self._on_skip_encrypt)
        back = Gtk.Button(label="Back")
        back.connect("clicked", lambda _b: self.stack.set_visible_child_name("secrets"))
        return self._page(
            section("Encrypt the journal"),
            wrapping(IN_PLACE_REASON),
            wrapping(
                "Plug in a spare microSD card or USB disk at least as large as "
                "the used space plus about 1GB. The copy can take a long time. "
                "If it fails, this card still boots."
            ),
            scroll,
            refresh,
            self.erase,
            go,
            skip,
            back,
        )

    def _load_disks(self) -> None:
        listing = subprocess.run(
            ["lsblk", "-P", "-o", "NAME,TYPE,SIZE,TRAN,PKNAME,MOUNTPOINT"],
            capture_output=True,
            text=True,
        )
        source = ""
        found = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "/"], capture_output=True, text=True)
        if found.returncode == 0:
            device = found.stdout.strip()
            parent = subprocess.run(["lsblk", "-no", "PKNAME", device], capture_output=True, text=True)
            source = parent.stdout.strip().splitlines()[0] if parent.stdout.strip() else ""
        rows = spare_candidates(parse_lsblk_pairs(listing.stdout), source)
        for child in self.disk_list.get_children():
            self.disk_list.remove(child)
        self._selected_disk = ""
        for row in rows:
            via = f", {row['tran']}" if row["tran"] else ""
            label = Gtk.Label(label=f"{row['path']}  {row['size']}{via}")
            label.set_xalign(0)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            label.set_margin_start(6)
            holder = Gtk.ListBoxRow()
            holder.add(label)
            holder.device = row["path"]  # type: ignore[attr-defined]
            self.disk_list.add(holder)
        self.disk_list.show_all()
        if not rows:
            self._set_error("No spare disk yet. Plug one in and tap Refresh.")

    def _on_disk_selected(self, _box: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            self._selected_disk = ""
            return
        self._selected_disk = row.device  # type: ignore[attr-defined]
        self.erase.set_placeholder_text(erase_confirmation(self._selected_disk))

    def _on_encrypt(self, _button: Gtk.Button) -> None:
        if not self._selected_disk:
            self._set_error("Select the spare disk. The disk this Pi booted from is not in the list.")
            return
        if not confirmation_matches(self._selected_disk, self.erase.get_text().strip()):
            self._set_error(f"Type {erase_confirmation(self._selected_disk)} to confirm.")
            return
        self._start_apply(self._selected_disk, self.erase.get_text().strip(), "copied")

    def _on_skip_encrypt(self, _button: Gtk.Button) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Leave the journal unencrypted?",
        )
        dialog.format_secondary_text(
            "Anyone with the card can read it. You can run setup again from the journal later."
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        self._start_apply("-", "SKIP", "deferred")

    def _working(self) -> Gtk.Box:
        self.log_buffer = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=self.log_buffer)
        view.set_editable(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(200)
        scroll.add(view)
        back = Gtk.Button(label="Back")
        back.connect("clicked", self._back_from_working)
        box = self._page(
            section("Working"),
            wrapping("This can take a long time. Leave the power connected."),
            scroll,
            back,
        )
        return box

    def _back_from_working(self, _button: Gtk.Button) -> None:
        if self._busy:
            self._set_error("Still working. Leave the power connected.")
            return
        self.stack.set_visible_child_name("encrypt")

    def _done(self) -> Gtk.Box:
        self.done_text = wrapping("")
        journal = Gtk.Button(label="Open the journal")
        journal.connect("clicked", lambda _b: self._open_journal())
        return self._page(section("Next"), self.done_text, journal)

    def _sudo_needs_password(self) -> bool:
        result = subprocess.run(["sudo", "-n", "true"], capture_output=True)
        return result.returncode != 0

    def _start_apply(self, target: str, confirm: str, status: str) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_error("")
        self.log_buffer.set_text("")
        self.stack.set_visible_child_name("working")
        try:
            write_stamp(status)
        except OSError as exc:
            self._busy = False
            self._set_error(f"Could not record setup progress: {exc}")
            self.stack.set_visible_child_name("encrypt")
            return
        needs_password = self._sudo_needs_password()
        try:
            payload = apply_stdin(
                needs_password,
                self.current.get_text(),
                self.login.get_text(),
                self.disk.get_text() if target != "-" else "",
                target,
                confirm,
            )
        except ValueError as exc:
            clear_stamp()
            self._busy = False
            self._set_error(str(exc))
            self.stack.set_visible_child_name("encrypt")
            return
        command = apply_invocation(str(APPLY), needs_password)

        def worker() -> None:
            try:
                result = subprocess.run(command, input=payload, capture_output=True, text=True)
                output = (result.stdout or "") + (result.stderr or "")
                GLib.idle_add(self._apply_finished, result.returncode, output, status)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._apply_finished, 1, str(exc), status)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_finished(self, code: int, output: str, status: str) -> bool:
        self._busy = False
        self.log_buffer.set_text(output.strip())
        if code != 0:
            clear_stamp()
            self._set_error("Setup did not finish. The log is above. This card was not encrypted.")
            self.stack.set_visible_child_name("working")
            return False
        if status == "copied":
            self.done_text.set_text(
                "Power off, move the new card into the Pi, and power on. "
                "The touchscreen asks for the disk passphrase when the display "
                "comes up in the initramfs (unl0kr). A 3.5 inch SPI panel often "
                "stays dark until the desktop starts: connect HDMI and a USB "
                "keyboard for that boot, or add sj.unlock=console to the end of "
                "cmdline.txt on the boot partition and use the keyboard. "
                "The original card is still unencrypted. Keep it until the new "
                "card has unlocked and the journal is there, then wipe it. "
                "Shut down to lock the disk. A locked screen does not."
            )
        else:
            self.done_text.set_text(
                "Hardening is on. The journal is not encrypted, so anyone with "
                "the card can read it. The journal screen says so, and it can "
                "run this setup again once a spare disk is plugged in."
            )
        self.stack.set_visible_child_name("done")
        return False

    def _open_journal(self) -> None:
        subprocess.Popen(["python3", "-m", "ui.journal_app"], cwd=str(ROOT))
        self.destroy()


def main() -> None:
    win = SetupWizard()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
