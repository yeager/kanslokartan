"""Känslokartan — Emotion recognition and journal."""

import gettext
import json
import locale
import os
import subprocess
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from kanslokartan import __version__
from kanslokartan.export import show_export_dialog

try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass
for d in [Path(__file__).parent.parent / "po", Path("/usr/share/locale")]:
    if d.is_dir():
        locale.bindtextdomain("kanslokartan", str(d))
        gettext.bindtextdomain("kanslokartan", str(d))
        break
gettext.textdomain("kanslokartan")
_ = gettext.gettext

APP_ID = "se.danielnylander.kanslokartan"

EMOTIONS = [
    ("😊", "Happy", "Feeling good, content and joyful"),
    ("😢", "Sad", "Feeling down, unhappy or tearful"),
    ("😠", "Angry", "Feeling frustrated, irritated or furious"),
    ("😨", "Scared", "Feeling afraid, anxious or worried"),
    ("😲", "Surprised", "Feeling startled or amazed"),
    ("🤢", "Disgusted", "Feeling repulsed or uncomfortable"),
    ("😴", "Tired", "Feeling sleepy, exhausted or drained"),
    ("😌", "Calm", "Feeling peaceful, relaxed and at ease"),
    ("😤", "Frustrated", "Feeling stuck, annoyed or impatient"),
    ("🤩", "Excited", "Feeling thrilled, eager and full of energy"),
    ("😕", "Confused", "Feeling uncertain or puzzled"),
    ("🥰", "Loved", "Feeling cared for, safe and appreciated"),
]

STRATEGIES = {
    "Angry": ["Take 5 deep breaths", "Count to 10 slowly", "Squeeze a stress ball", "Walk away and cool down"],
    "Scared": ["Tell someone you trust", "Breathe slowly", "Think of your safe place", "Hold something soft"],
    "Sad": ["Talk to someone", "Draw or write about it", "Listen to music", "Give yourself a hug"],
    "Frustrated": ["Take a break", "Try again later", "Ask for help", "Do something you enjoy first"],
    "Tired": ["Rest for a few minutes", "Drink water", "Take a short walk", "Listen to calm music"],
}


def _config_dir():
    p = Path(GLib.get_user_config_dir()) / "kanslokartan"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _load_journal():
    path = _config_dir() / "journal.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return []

def _save_journal(journal):
    path = _config_dir() / "journal.json"
    path.write_text(json.dumps(journal[-500:], indent=2, ensure_ascii=False))

def _speak(text):
    for cmd in [["piper", "--model", "sv_SE-nst-medium", "--output_raw"], ["espeak-ng", "-v", "sv"]]:
        try:
            subprocess.Popen(cmd + [text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("Emotion Map"))
        self.set_default_size(550, 700)
        self.journal = _load_journal()

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        header = Adw.HeaderBar()
        main_box.append(header)

        export_btn = Gtk.Button(icon_name="document-save-symbolic", tooltip_text=_("Export (Ctrl+E)"))
        export_btn.connect("clicked", lambda *_: self._on_export())
        header.pack_end(export_btn)

        menu = Gio.Menu()
        menu.append(_("Export Journal"), "win.export")
        menu.append(_("About Emotion Map"), "app.about")
        menu.append(_("Quit"), "app.quit")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)

        export_action = Gio.SimpleAction.new("export", None)
        export_action.connect("activate", lambda *_: self._on_export())
        self.add_action(export_action)

        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-pressed", self._on_key)
        self.add_controller(ctrl)

        # View stack
        stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcherBar()
        switcher.set_stack(stack)
        switcher.set_reveal(True)

        # Emotions grid page
        emotions_page = self._build_emotions_page()
        stack.add_titled(emotions_page, "emotions", _("Emotions"))
        stack.get_page(emotions_page).set_icon_name("face-smile-symbolic")

        # Journal page
        journal_page = self._build_journal_page()
        stack.add_titled(journal_page, "journal", _("Journal"))
        stack.get_page(journal_page).set_icon_name("document-edit-symbolic")

        main_box.append(stack)
        main_box.append(switcher)

        # Status bar
        self.status = Gtk.Label(label="", xalign=0)
        self.status.add_css_class("dim-label")
        self.status.set_margin_start(12)
        self.status.set_margin_bottom(4)
        main_box.append(self.status)
        GLib.timeout_add_seconds(1, self._tick)
        self._tick()

    def _tick(self):
        self.status.set_label(GLib.DateTime.new_now_local().format("%Y-%m-%d %H:%M:%S"))
        return True

    def _on_key(self, ctrl, keyval, keycode, state):
        if state & Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_e, Gdk.KEY_E):
            self._on_export()
            return True
        return False

    def _on_export(self):
        show_export_dialog(self, self.journal, _("Emotion Journal"), lambda m: self.status.set_label(m))

    def _build_emotions_page(self):
        scroll = Gtk.ScrolledWindow(vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_bottom(16)

        title = Gtk.Label(label=_("How are you feeling?"))
        title.add_css_class("title-2")
        box.append(title)

        grid = Gtk.FlowBox()
        grid.set_max_children_per_line(4)
        grid.set_min_children_per_line(2)
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_homogeneous(True)
        grid.set_column_spacing(8)
        grid.set_row_spacing(8)

        for emoji, name, desc in EMOTIONS:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.set_size_request(100, 100)

            btn = Gtk.Button()
            btn.add_css_class("flat")
            btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl_emoji = Gtk.Label(label=emoji)
            lbl_emoji.add_css_class("title-1")
            btn_box.append(lbl_emoji)
            lbl_name = Gtk.Label(label=_(name))
            lbl_name.add_css_class("heading")
            btn_box.append(lbl_name)
            btn.set_child(btn_box)
            btn.connect("clicked", self._on_emotion_clicked, emoji, name, desc)
            card.append(btn)
            grid.insert(card, -1)

        box.append(grid)
        scroll.set_child(box)
        return scroll

    def _on_emotion_clicked(self, btn, emoji, name, desc):
        # Log to journal
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "emotion": _(name),
            "emoji": emoji,
        }
        self.journal.append(entry)
        _save_journal(self.journal)
        self._refresh_journal()

        # Show strategies if available
        strategies = STRATEGIES.get(name, [])
        body = _(desc)
        if strategies:
            body += "\n\n" + _("Try this:") + "\n"
            body += "\n".join(f"• {_(s)}" for s in strategies)

        dialog = Adw.AlertDialog.new(f"{emoji} {_(name)}", body)
        dialog.add_response("ok", _("OK"))
        dialog.add_response("speak", "🔊 " + _("Listen"))
        dialog.connect("response", lambda d, r: _speak(_(name)) if r == "speak" else None)
        dialog.present(self)

        self.status.set_label(_("Logged: %s %s") % (emoji, _(name)))

    def _build_journal_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        title = Gtk.Label(label=_("Emotion Journal"))
        title.add_css_class("title-3")
        box.append(title)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.journal_list = Gtk.ListBox()
        self.journal_list.add_css_class("boxed-list")
        self.journal_list.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.journal_list)
        box.append(scroll)

        clear_btn = Gtk.Button(label=_("Clear Journal"))
        clear_btn.add_css_class("destructive-action")
        clear_btn.set_halign(Gtk.Align.CENTER)
        clear_btn.set_margin_bottom(12)
        clear_btn.connect("clicked", self._on_clear_journal)
        box.append(clear_btn)

        self._refresh_journal()
        return box

    def _refresh_journal(self):
        child = self.journal_list.get_first_child()
        while child:
            nc = child.get_next_sibling()
            self.journal_list.remove(child)
            child = nc
        for entry in reversed(self.journal[-50:]):
            row = Adw.ActionRow()
            row.set_title(f"{entry.get('emoji', '')} {entry.get('emotion', '')}")
            row.set_subtitle(entry.get("date", ""))
            self.journal_list.append(row)

    def _on_clear_journal(self, *_args):
        self.journal = []
        _save_journal(self.journal)
        self._refresh_journal()


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.connect("activate", self._on_activate)

    def _on_activate(self, *_args):
        win = self.props.active_window or MainWindow(self)
        self._add_action("about", self._on_about)
        quit_a = Gio.SimpleAction(name="quit")
        quit_a.connect("activate", lambda *_: self.quit())
        self.add_action(quit_a)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        win.present()

    def _add_action(self, name, cb):
        a = Gio.SimpleAction(name=name)
        a.connect("activate", cb)
        self.add_action(a)

    def _on_about(self, *_args):
        dialog = Adw.AboutDialog(
            application_name=_("Emotion Map"),
            application_icon=APP_ID,
            version=__version__,
            developer_name="Daniel Nylander",
            license_type=Gtk.License.GPL_3_0,
            website="https://www.autismappar.se",
            developers=["Daniel Nylander <daniel@danielnylander.se>"],
            comments=_("Emotion recognition and journal for autism and ADHD"),
        )
        dialog.present(self.props.active_window)


def main():
    app = App()
    return app.run()
