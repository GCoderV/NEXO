"""In-memory Tk double complete enough to instantiate app.Application.

The sandbox has no display and no real tkinter. This module is NOT named
`test_*` on purpose: unittest must not import it on its own. A test imports it
and calls `install()` BEFORE importing `app`, because app.py binds `tk`/`ttk`
at module import time.

These widgets keep real text/state so a regression can prove that opening a
new project does not leave the previous project's text on screen. No Windows,
no X server, no Word, no network and no credentials are involved.
"""
import sys
import types


class TclError(Exception):
    pass


class Var:
    def __init__(self, value=None, **kw):
        self.v = value

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class Widget:
    """Generic widget with real text, options and a no-op for everything else."""

    def __init__(self, master=None, **kw):
        self.master = master
        self.opts = dict(kw)
        self.text = kw.get('text', '')
        self.buf = ''
        self._state = []
        self.visible = True

    def configure(self, *args, **kw):
        self.opts.update(kw)
        if 'text' in kw:
            self.text = kw['text']

    config = configure

    def cget(self, key):
        return self.opts.get(key, '')

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

    def state(self, spec=None):
        if spec is not None:
            self._state = list(spec)
        return self._state

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

    # --- Text-like behaviour -------------------------------------------------
    def insert(self, index, text, *a):
        if index in ('1.0', 'insert') and not self.buf:
            self.buf = text
        else:
            self.buf = self.buf + text

    def delete(self, start, end=None):
        if start == '1.0' and end in ('end', 'end-1c', None):
            self.buf = ''

    def get(self, start='1.0', end=None):
        if end == 'end-1c':
            return self.buf[:-1] if self.buf.endswith('\n') else self.buf
        return self.buf


class Combo(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.values = list(kw.get('values', ()) or ())
        self.idx = -1
        self._set = ''

    def configure(self, *args, **kw):
        if 'values' in kw:
            self.values = list(kw['values'])
        super().configure(*args, **kw)

    def current(self, i=None):
        if i is None:
            return self.idx
        self.idx = i
        self._set = self.values[i] if 0 <= i < len(self.values) else ''
        return i

    def get(self):
        return self._set or (self.values[self.idx] if 0 <= self.idx < len(self.values) else '')

    def set(self, value):
        self._set = value


class Tree(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.items = {}
        self.children = []
        self.sel = []

    def insert(self, parent, index, iid=None, **kw):
        key = iid or 'i' + str(len(self.items))
        self.items[key] = kw
        self.children.append(key)
        return key

    def get_children(self, item=None):
        return list(self.children)

    def delete(self, *ids):
        if not ids:
            return
        for i in ids:
            self.items.pop(i, None)
            if i in self.children:
                self.children.remove(i)

    def selection(self):
        return tuple(self.sel)

    def selection_set(self, *ids):
        self.sel = list(ids)


class Listbox(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.rows = []
        self.sel = []

    def insert(self, index, text, *a):
        self.rows.append(text)

    def delete(self, start, end=None):
        self.rows = []

    def curselection(self):
        return tuple(self.sel)

    def selection_set(self, *ids):
        self.sel = list(ids)

    def get(self, start='1.0', end=None):
        if isinstance(start, int):
            return self.rows[start] if 0 <= start < len(self.rows) else ''
        return super().get(start, end)


class Notebook(Widget):
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self._tabs = []

    def add(self, child, **kw):
        self._tabs.append(child)

    def select(self, index=None):
        return None

    def tabs(self):
        return list(self._tabs)


def install():
    """Install the doubles and return (tk, ttk). Idempotent."""
    tk = types.ModuleType('tkinter')
    ttk = types.ModuleType('tkinter.ttk')
    mb = types.ModuleType('tkinter.messagebox')
    fd = types.ModuleType('tkinter.filedialog')
    sd = types.ModuleType('tkinter.simpledialog')
    st = types.ModuleType('tkinter.scrolledtext')
    font = types.ModuleType('tkinter.font')

    tk.StringVar = tk.BooleanVar = tk.IntVar = Var
    tk.Tk = tk.Toplevel = tk.Menu = Widget
    tk.Listbox = Listbox
    tk.TclError = TclError
    tk.END = 'end'
    tk.WORD = 'word'
    tk.NORMAL = 'normal'
    tk.DISABLED = 'disabled'

    for name in ('Frame', 'Label', 'Button', 'Entry', 'Checkbutton',
                 'Spinbox', 'Style', 'Scrollbar', 'PanedWindow',
                 'Separator', 'Progressbar'):
        setattr(ttk, name, type(name, (Widget,), {}))
    ttk.Combobox = Combo
    ttk.Treeview = Tree
    ttk.Notebook = Notebook

    mb.askyesno = lambda *a, **k: True
    mb.showerror = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    fd.askdirectory = lambda *a, **k: ''
    fd.askopenfilename = lambda *a, **k: ''
    fd.asksaveasfilename = lambda *a, **k: ''
    sd.askstring = lambda *a, **k: ''
    st.ScrolledText = Widget

    tk.ttk, tk.messagebox, tk.filedialog = ttk, mb, fd
    tk.simpledialog, tk.scrolledtext, tk.font = sd, st, font
    for name, mod in (('tkinter', tk), ('tkinter.ttk', ttk),
                      ('tkinter.messagebox', mb), ('tkinter.filedialog', fd),
                      ('tkinter.simpledialog', sd),
                      ('tkinter.scrolledtext', st), ('tkinter.font', font)):
        sys.modules[name] = mod
    return tk, ttk
