"""Regression: selecting Copilot365 must never look like an API-key requirement.

Reported by the user: "cuando elijo Copilot no deja guardarlo, pide api o
credenciales". Copilot365 is a session connector, not an API: the only setup is
"Conectar escritorio M365", which observes the signed-in user's own session.

This sandbox has no Tk/Xvfb, so a minimal in-memory Tk double stands in for the
widgets. No network, no Microsoft session, no real credential and no DPAPI are
used; all values are synthetic fixtures.
"""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeProtector  # noqa: E402
from test_v02 import session  # noqa: E402  (synthetic fixture, not a token)
from config import Config  # noqa: E402


class Var:
    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class StringVar(Var):
    def __init__(self, master=None, value='', **kw):
        super().__init__(value if value is not None else '')


class BooleanVar(Var):
    def __init__(self, master=None, value=False, **kw):
        super().__init__(bool(value))


class IntVar(Var):
    def __init__(self, master=None, value=0, **kw):
        super().__init__(int(value))


class Widget:
    def __init__(self, master=None, **kw):
        self.master = master
        self.opts = dict(kw)
        self.text = kw.get('text', '')
        self._states = []
        self.visible = True

    def __getattr__(self, name):
        def noop(*a, **k):
            return None
        return noop

    def grid(self, *a, **k):
        self.visible = True

    def grid_remove(self):
        self.visible = False

    def pack(self, *a, **k):
        return None

    def configure(self, **kw):
        self.opts.update(kw)
        self.text = kw.get('text', self.text)

    config = configure

    def state(self, spec=None):
        if spec is not None:
            self._states = list(spec)
        return self._states

    def winfo_exists(self):
        return 1

    def after(self, *a, **k):
        return 'after-id'

    def after_cancel(self, *a, **k):
        return None

    def clipboard_clear(self):
        return None

    def clipboard_append(self, value):
        return None


class Treeview(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.items = {}
        self.sel = []

    def insert(self, parent, index, iid=None, **kw):
        key = iid or 'item-' + str(len(self.items))
        self.items[key] = kw
        return key

    def get_children(self, item=None):
        return list(self.items)

    def delete(self, *iids):
        for i in iids:
            self.items.pop(i, None)

    def selection(self):
        return tuple(self.sel)

    def selection_set(self, *iids):
        self.sel = list(iids)

    def selection_remove(self, *iids):
        self.sel = [i for i in self.sel if i not in iids]

    def exists(self, iid):
        return iid in self.items

    def focus(self, iid=None):
        return iid

    def see(self, iid):
        return None


def install_fake_tk():
    tk = types.ModuleType('tkinter')
    ttk = types.ModuleType('tkinter.ttk')
    mb = types.ModuleType('tkinter.messagebox')
    tk.StringVar, tk.BooleanVar, tk.IntVar = StringVar, BooleanVar, IntVar
    tk.Toplevel = tk.Tk = Widget
    for name in ('Frame', 'Label', 'Button', 'Entry', 'Checkbutton',
                 'Spinbox', 'Notebook', 'Style'):
        setattr(ttk, name, type(name, (Widget,), {}))
    ttk.Combobox = type('Combobox', (Widget,), {})
    ttk.Treeview = Treeview
    mb.askyesno = lambda *a, **k: True
    mb.showerror = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    tk.ttk, tk.messagebox = ttk, mb
    sys.modules['tkinter'] = tk
    sys.modules['tkinter.ttk'] = ttk
    sys.modules['tkinter.messagebox'] = mb
    return tk, ttk, mb


# Install before importing the dialog; keep a handle so the suite stays isolated.
FAKE_TK = install_fake_tk()
sys.modules.pop('settings_dialog', None)
import settings_dialog  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402


class FakeApp:
    def __init__(self, config):
        self.root = object()
        self.config = config
        self.store = types.SimpleNamespace(root=object())
        self.updates = 0

    def update_provider(self):
        self.updates += 1


class CopilotSinApiKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(self.temp.name, FakeProtector())
        self.app = FakeApp(self.config)
        self.dlg = SettingsDialog(self.app)

    def choose_copilot(self):
        self.dlg.ap.set('Copilot365')
        self.dlg.sync_account_provider()

    def test_form_never_shows_api_key_for_copilot(self):
        self.choose_copilot()
        self.assertFalse(self.dlg.api_label.visible, 'the API key label must be hidden')
        self.assertFalse(self.dlg.api_entry.visible, 'the API key entry must be hidden')
        self.assertEqual(self.dlg.secret.get(), '')
        self.assertIn('Conectar', self.dlg.save_account_button.text)
        self.assertIn('NO usa API key', self.dlg.probe.get())
        self.assertIn('Conectar escritorio M365', self.dlg.probe.get())

    def test_form_restores_api_key_for_regular_provider(self):
        self.choose_copilot()
        self.dlg.ap.set('Groq')
        self.dlg.sync_account_provider()
        self.assertTrue(self.dlg.api_label.visible)
        self.assertTrue(self.dlg.api_entry.visible)
        self.assertEqual(self.dlg.save_account_button.text, 'Guardar cuenta')

    def test_save_account_starts_connection_instead_of_demanding_a_key(self):
        self.choose_copilot()
        self.dlg.alias.set('Mi M365')
        with patch.object(self.dlg, 'connect_copilot') as connect:
            self.dlg.save_account()
        connect.assert_called_once_with()
        self.assertEqual(self.config.data['accounts'], {})
        self.assertIsNone(self.dlg.account_id)

    def test_existing_connection_can_be_saved_without_typing_anything(self):
        aid = self.config.account('Copilot365', 'Mi M365', session(), remember=False)
        self.choose_copilot()
        self.dlg.account_id = aid
        self.dlg.alias.set('Otro nombre')
        with patch.object(self.dlg, 'connect_copilot') as connect:
            self.dlg.save_account()
        connect.assert_not_called()
        self.assertEqual(self.config.data['accounts'][aid]['alias'], 'Otro nombre')
        self.assertEqual(self.dlg.secret.get(), '')

    def test_save_route_offers_connection_instead_of_asking_for_credentials(self):
        self.dlg.provider.set('Copilot365')
        self.dlg.change_provider()
        with patch('settings_dialog.messagebox.askyesno', return_value=False) as ask:
            rid = self.dlg.save_route()
        ask.assert_called_once()
        self.assertIsNone(rid)
        self.assertEqual(self.config.data['routes'], [])
        self.assertIn('sin API key', ask.call_args[0][0] + ask.call_args[0][1])
        self.assertIn('Conectar escritorio M365', self.dlg.note.get())

    def test_use_route_does_not_select_a_route_when_connection_was_declined(self):
        self.dlg.provider.set('Copilot365')
        self.dlg.change_provider()
        with patch('settings_dialog.messagebox.askyesno', return_value=False):
            self.dlg.use_route()
        self.assertNotIn('route_id', self.config.data['current'])

    def test_accepting_offer_prepares_copilot_account_form(self):
        self.dlg.provider.set('Copilot365')
        self.dlg.change_provider()
        with patch('settings_dialog.messagebox.askyesno', return_value=True), \
             patch.object(self.dlg, 'connect_copilot') as connect:
            self.dlg.save_route()
        connect.assert_called_once_with()
        self.assertEqual(self.dlg.ap.get(), 'Copilot365')
        self.assertEqual(self.dlg.alias.get(), 'Microsoft 365')
        self.assertFalse(self.dlg.api_entry.visible)

    def test_config_messages_name_the_connection_not_a_key(self):
        with self.assertRaises(ValueError) as ctx:
            self.config.account('Copilot365', 'M365', '')
        self.assertIn('no usa API key', str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.config.route('Copilot365', 'auto', '')
        self.assertIn('conexión', str(ctx.exception))
        self.assertNotIn('credencial', str(ctx.exception))

    def test_regular_api_provider_still_requires_its_key(self):
        self.dlg.ap.set('Groq')
        self.dlg.sync_account_provider()
        with self.assertRaises(ValueError) as ctx:
            self.dlg.save_account()
        self.assertIn('credencial', str(ctx.exception))
        self.dlg.secret.set('UI-FAKE-KEY')
        self.dlg.alias.set('Trabajo')
        self.dlg.save_account()
        self.assertEqual(len(self.config.data['accounts']), 1)


if __name__ == '__main__':
    unittest.main()
