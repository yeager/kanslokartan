"""Känslokartan - Emotion recognition training."""
import sys
import os
import json
import random
import gettext
import locale
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk
from kanslokartan import __version__
from kanslokartan.accessibility import apply_large_text
from kanslokartan.accessibility import AccessibilityManager

TEXTDOMAIN = "kanslokartan"
for p in [os.path.join(os.path.dirname(__file__), "locale"), "/usr/share/locale"]:
    if os.path.isdir(p):
        gettext.bindtextdomain(TEXTDOMAIN, p)
        locale.bindtextdomain(TEXTDOMAIN, p)
        break
gettext.textdomain(TEXTDOMAIN)
_ = gettext.gettext

EMOTIONS = [
    {"id": 28530, "name": _("Happy"), "emoji": "\U0001f600"},
    {"id": 28531, "name": _("Sad"), "emoji": "\U0001f622"},
    {"id": 28529, "name": _("Angry"), "emoji": "\U0001f621"},
    {"id": 28534, "name": _("Scared"), "emoji": "\U0001f628"},
    {"id": 28532, "name": _("Surprised"), "emoji": "\U0001f632"},
    {"id": 28533, "name": _("Disgusted"), "emoji": "\U0001f922"},
    {"id": 6730, "name": _("Calm"), "emoji": "\U0001f60c"},
    {"id": 28535, "name": _("Tired"), "emoji": "\U0001f634"},
    {"id": 6726, "name": _("Worried"), "emoji": "\U0001f61f"},
    {"id": 28536, "name": _("Proud"), "emoji": "\U0001f60e"},
]

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "kanslokartan")
RESULTS_FILE = os.path.join(CONFIG_DIR, "results.json")


def _load_results():
    try:
        with open(RESULTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_results(results):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(results[-500:], f, ensure_ascii=False, indent=2)



def _settings_path():
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = os.path.join(xdg, "kanslokartan")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")

def _load_settings():
    p = _settings_path()
    if os.path.exists(p):
        import json
        with open(p) as f:
            return json.load(f)
    return {}

def _save_settings(s):
    import json
    with open(_settings_path(), "w") as f:
        json.dump(s, f, indent=2)

class KansloApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="se.danielnylander.kanslokartan",
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        apply_large_text()
        win = self.props.active_window or KansloWindow(application=self)
        win.present()
        if not self.settings.get("welcome_shown"):
            self._show_welcome(win)


    def do_startup(self):
        Adw.Application.do_startup(self)
        for name, cb, accel in [
            ("quit", lambda *_: self.quit(), "<Control>q"),
            ("about", self._on_about, None),
            ("shortcuts", self._on_shortcuts, "<Control>slash"),
            ("export", self._on_export, "<Control>e"),
        ]:
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", cb)
            self.add_action(a)
            if accel:
                self.set_accels_for_action(f"app.{name}", [accel])

    def _on_about(self, *_args):
        d = Adw.AboutDialog(
            application_name=_("Emotion Map"), application_icon="kanslokartan",
            version=__version__, developer_name="Daniel Nylander",
            website="https://www.autismappar.se",
            issue_url="https://github.com/yeager/kanslokartan/issues",
            license_type=Gtk.License.GPL_3_0, developers=["Daniel Nylander"],
            copyright="\u00a9 2026 Daniel Nylander")
        d.present(self.props.active_window)

    def _on_shortcuts(self, *_args):
        pass  # TODO

    def _on_export(self, *_args):
        w = self.props.active_window
        if w:
            w.do_export()


class KansloWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, default_width=500, default_height=650,
                         title=_("Emotion Map"))
        self.score = 0
        self.total = 0
        self.current = None
        self.results = _load_results()
        self._build_ui()
        self._next_emotion()

    def _build_ui(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(box)
        header = Adw.HeaderBar()
        box.append(header)

        menu = Gio.Menu()
        menu.append(_("Export Results"), "app.export")
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About Emotion Map"), "app.about")
        menu.append(_("Quit"), "app.quit")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))

        theme_btn = Gtk.Button(icon_name="weather-clear-night-symbolic",
                               tooltip_text=_("Toggle dark/light theme"))
        theme_btn.connect("clicked", self._toggle_theme)
        header.pack_end(theme_btn)

        self.score_label = Gtk.Label(label=_("Score: 0 / 0"))
        self.score_label.add_css_class("title-4")
        self.score_label.set_margin_top(12)
        box.append(self.score_label)

        self.emoji_label = Gtk.Label()
        self.emoji_label.set_markup('<span size="120000">\u2753</span>')
        self.emoji_label.set_margin_top(20)
        self.emoji_label.set_margin_bottom(20)
        box.append(self.emoji_label)

        self.prompt_label = Gtk.Label(label=_("What emotion is this?"))
        self.prompt_label.add_css_class("title-2")
        self.prompt_label.set_margin_bottom(16)
        box.append(self.prompt_label)

        self.btn_grid = Gtk.FlowBox(max_children_per_line=2,
                                     selection_mode=Gtk.SelectionMode.NONE,
                                     homogeneous=True, row_spacing=8, column_spacing=8)
        self.btn_grid.set_margin_start(24)
        self.btn_grid.set_margin_end(24)
        box.append(self.btn_grid)

        self.feedback_label = Gtk.Label(label="")
        self.feedback_label.add_css_class("title-3")
        self.feedback_label.set_margin_top(16)
        box.append(self.feedback_label)

        self.next_btn = Gtk.Button(label=_("Next"))
        self.next_btn.add_css_class("suggested-action")
        self.next_btn.add_css_class("pill")
        self.next_btn.set_halign(Gtk.Align.CENTER)
        self.next_btn.set_margin_top(12)
        self.next_btn.set_margin_bottom(16)
        self.next_btn.connect("clicked", lambda *_: self._next_emotion())
        self.next_btn.set_visible(False)
        box.append(self.next_btn)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.add_css_class("dim-label")
        self.status_label.set_margin_start(12)
        self.status_label.set_margin_bottom(4)
        box.append(self.status_label)
        GLib.timeout_add_seconds(1, self._update_clock)
        self._update_clock()

    def _next_emotion(self):
        self.current = random.choice(EMOTIONS)
        self.emoji_label.set_markup(f'<span size="120000">{self.current["emoji"]}</span>')
        self.feedback_label.set_label("")
        self.next_btn.set_visible(False)

        wrong = [e for e in EMOTIONS if e["id"] != self.current["id"]]
        choices = random.sample(wrong, min(3, len(wrong))) + [self.current]
        random.shuffle(choices)

        while (child := self.btn_grid.get_first_child()):
            self.btn_grid.remove(child)

        for em in choices:
            btn = Gtk.Button(label=em["name"])
            btn.add_css_class("pill")
            btn.set_size_request(180, 48)
            btn.connect("clicked", self._on_answer, em)
            self.btn_grid.append(btn)

    def _on_answer(self, btn, chosen):
        self.total += 1
        correct = chosen["id"] == self.current["id"]
        if correct:
            self.score += 1
            self.feedback_label.set_label(_("Correct! \u2705"))
        else:
            self.feedback_label.set_label(_("Not quite. It was: %s") % self.current["name"])

        self.score_label.set_label(_("Score: %d / %d") % (self.score, self.total))

        child = self.btn_grid.get_first_child()
        while child:
            inner = child.get_first_child()
            if inner:
                inner.set_sensitive(False)
            child = child.get_next_sibling()
        self.next_btn.set_visible(True)

        from datetime import datetime
        self.results.append({"date": datetime.now().isoformat(), "emotion": self.current["name"],
                              "chosen": chosen["name"], "correct": correct})
        _save_results(self.results)

    def do_export(self):
        from kanslokartan.export import export_csv, export_json
        os.makedirs(CONFIG_DIR, exist_ok=True)
        ts = GLib.DateTime.new_now_local().format("%Y%m%d_%H%M%S")
        data = [{"date": r["date"], "details": r["emotion"],
                 "result": str(r["correct"])} for r in self.results]
        export_csv(data, os.path.join(CONFIG_DIR, f"export_{ts}.csv"))
        export_json(data, os.path.join(CONFIG_DIR, f"export_{ts}.json"))
        self.feedback_label.set_label(_("Exported to %s") % CONFIG_DIR)

    def _toggle_theme(self, *_args):
        mgr = Adw.StyleManager.get_default()
        mgr.set_color_scheme(
            Adw.ColorScheme.FORCE_LIGHT if mgr.get_dark() else Adw.ColorScheme.FORCE_DARK)

    def _update_clock(self):
        self.status_label.set_label(GLib.DateTime.new_now_local().format("%Y-%m-%d %H:%M:%S"))
        return True


def main():
    app = KansloApp()
    app.run(sys.argv)

if __name__ == "__main__":
    main()

    # ── Welcome Dialog ───────────────────────────────────────

    def _show_welcome(self, win):
        dialog = Adw.Dialog()
        dialog.set_title(_("Welcome"))
        dialog.set_content_width(420)
        dialog.set_content_height(480)

        page = Adw.StatusPage()
        page.set_icon_name("kanslokartan")
        page.set_title(_("Welcome to Emotion Map"))
        page.set_description(_(
            "Explore and understand emotions with visual aids.\n\n✓ Emotion recognition with emoji\n✓ Track how you feel over time\n✓ Learn emotion vocabulary\n✓ Suitable for all ages"
        ))

        btn = Gtk.Button(label=_("Get Started"))
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(12)
        btn.connect("clicked", self._on_welcome_close, dialog)
        page.set_child(btn)

        box = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_show_title(False)
        box.add_top_bar(hb)
        box.set_content(page)
        dialog.present(win)

    def _on_welcome_close(self, btn, dialog):
        self.settings["welcome_shown"] = True
        _save_settings(self.settings)
        dialog.close()



# --- Session restore ---
import json as _json
import os as _os

def _save_session(window, app_name):
    config_dir = _os.path.join(_os.path.expanduser('~'), '.config', app_name)
    _os.makedirs(config_dir, exist_ok=True)
    state = {'width': window.get_width(), 'height': window.get_height(),
             'maximized': window.is_maximized()}
    try:
        with open(_os.path.join(config_dir, 'session.json'), 'w') as f:
            _json.dump(state, f)
    except OSError:
        pass

def _restore_session(window, app_name):
    path = _os.path.join(_os.path.expanduser('~'), '.config', app_name, 'session.json')
    try:
        with open(path) as f:
            state = _json.load(f)
        window.set_default_size(state.get('width', 800), state.get('height', 600))
        if state.get('maximized'):
            window.maximize()
    except (FileNotFoundError, _json.JSONDecodeError, OSError):
        pass


# --- Fullscreen toggle (F11) ---
def _setup_fullscreen(window, app):
    """Add F11 fullscreen toggle."""
    from gi.repository import Gio
    if not app.lookup_action('toggle-fullscreen'):
        action = Gio.SimpleAction.new('toggle-fullscreen', None)
        action.connect('activate', lambda a, p: (
            window.unfullscreen() if window.is_fullscreen() else window.fullscreen()
        ))
        app.add_action(action)
        app.set_accels_for_action('app.toggle-fullscreen', ['F11'])


# --- Plugin system ---
import importlib.util
import os as _pos

def _load_plugins(app_name):
    """Load plugins from ~/.config/<app>/plugins/."""
    plugin_dir = _pos.path.join(_pos.path.expanduser('~'), '.config', app_name, 'plugins')
    plugins = []
    if not _pos.path.isdir(plugin_dir):
        return plugins
    for fname in sorted(_pos.listdir(plugin_dir)):
        if fname.endswith('.py') and not fname.startswith('_'):
            path = _pos.path.join(plugin_dir, fname)
            try:
                spec = importlib.util.spec_from_file_location(fname[:-3], path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                plugins.append(mod)
            except Exception as e:
                print(f"Plugin {fname}: {e}")
    return plugins


# --- Sound notifications ---
def _play_sound(sound_name='complete'):
    """Play a system notification sound."""
    try:
        import subprocess
        # Try canberra-gtk-play first, then paplay
        for cmd in [
            ['canberra-gtk-play', '-i', sound_name],
            ['paplay', f'/usr/share/sounds/freedesktop/stereo/{sound_name}.oga'],
        ]:
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue
    except Exception:
        pass
