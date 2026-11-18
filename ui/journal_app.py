"""Touch-friendly journal.

One column: a list of days, then the entry. Buttons are tall enough to hit
on a 3.5 inch panel. Saving writes the same Markdown files as scripts/journal.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from ui.journal_store import (
    current_root_is_encrypted,
    ensure_entry,
    journal_root,
    list_entries,
    read_entry,
    write_entry,
)
from ui.setup_state import clear_stamp

ROOT = Path(__file__).resolve().parents[1]


class JournalApp(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="Journal")
        self.set_default_size(480, 320)
        self.root = journal_root()
        self.current: Path | None = None
        self.loading = False
        self._build()
        self._reload()
        self.maximize()

    def _build(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window { font-size: 16px; }
            button { min-height: 44px; }
            textview { font-size: 18px; }
            """
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        self.banner = Gtk.Label()
        self.banner.set_line_wrap(True)
        self.banner.set_xalign(0)
        if not current_root_is_encrypted():
            self.banner.set_text(
                "This journal is not on an encrypted disk. Anyone with the card can read it."
            )
        box.pack_start(self.banner, False, False, 0)

        self.entries = Gtk.ListBox()
        self.entries.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.entries.connect("row-selected", self._on_row)
        entry_scroll = Gtk.ScrolledWindow()
        entry_scroll.set_min_content_height(100)
        entry_scroll.add(self.entries)
        box.pack_start(entry_scroll, False, False, 0)

        self.buffer = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=self.buffer)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_left_margin(6)
        view.set_right_margin(6)
        view.set_top_margin(6)
        text_scroll = Gtk.ScrolledWindow()
        text_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        text_scroll.add(view)
        box.pack_start(text_scroll, True, True, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        today = Gtk.Button(label="Today")
        today.connect("clicked", self._today)
        save = Gtk.Button(label="Save")
        save.connect("clicked", lambda _b: self._save())
        buttons.pack_start(today, True, True, 0)
        buttons.pack_start(save, True, True, 0)
        if not current_root_is_encrypted():
            again = Gtk.Button(label="Set up encryption")
            again.connect("clicked", self._rerun_setup)
            buttons.pack_start(again, True, True, 0)
        box.pack_start(buttons, False, False, 0)
        self.add(box)

    def _reload(self, prefer: Path | None = None) -> None:
        ensure_entry(self.root, date.today())
        self.loading = True
        for child in self.entries.get_children():
            self.entries.remove(child)
        paths = list_entries(self.root)
        for path in paths:
            label = Gtk.Label(label=path.stem)
            label.set_xalign(0)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            label.set_margin_start(6)
            row = Gtk.ListBoxRow()
            row.add(label)
            row.path = path  # type: ignore[attr-defined]
            self.entries.add(row)
        self.entries.show_all()
        self.loading = False
        target = prefer if prefer in paths else (paths[0] if paths else None)
        if target is not None:
            self._show(target)

    def _today(self, _button: Gtk.Button) -> None:
        self._save()
        self._reload(ensure_entry(self.root, date.today()))

    def _show(self, path: Path) -> None:
        self.loading = True
        for row in self.entries.get_children():
            if getattr(row, "path", None) == path:
                self.entries.select_row(row)
                break
        self.current = path
        self.buffer.set_text(read_entry(path))
        self.loading = False

    def _on_row(self, _box: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None or self.loading:
            return
        path = row.path  # type: ignore[attr-defined]
        if path == self.current:
            return
        self._save()
        self._show(path)

    def _save(self) -> None:
        if self.current is None or self.loading:
            return
        write_entry(self.current, self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False))

    def _rerun_setup(self, _button: Gtk.Button) -> None:
        self._save()
        clear_stamp()
        os.execv(sys.executable, [sys.executable, "-m", "ui.setup_wizard"])


def main() -> None:
    win = JournalApp()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
