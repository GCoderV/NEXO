import sys,tempfile,time,json,tkinter as tk
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'tests'))
from test_core import FakeAPI,FakeProtector
from app import Application
from config import Config
from project_store import ProjectStore
checks=[]
with tempfile.TemporaryDirectory() as t:
    root=tk.Tk();store=ProjectStore(t);calls=[]
    def factory():a=FakeAPI([]);calls.append(a);return a
    app=Application(root,store,Config(t,FakeProtector()),api_factory=factory);errors=[];root.report_callback_exception=lambda *x:errors.append(str(x))
    def pump(cond=lambda:True):
        end=time.monotonic()+8
        while time.monotonic()<end:
            root.update()
            if cond():return
            time.sleep(.01)
        raise AssertionError('UI timeout')
    try:
        app.put(app.input,'hola');app.send();pump();assert app.project is None and not store.list() and not calls;checks.append('Greeting does not become research title or trigger model')
        app.new_project('Producción oral');app.materials();pump();dlg=app.material_window
        path=Path(t)/'guia.txt';path.write_text('Times New Roman 12\nInterlineado 1.5\nTítulos 14 en mayúscula\nPapel A4\nCronograma de actividades',encoding='utf-8')
        with patch('material_dialog.filedialog.askopenfilename',return_value=str(path)),patch('material_dialog.messagebox.askyesno',return_value=False):dlg.add()
        assert not app.project.get('materials');checks.append('Declining file reading leaves library unchanged')
        with patch('material_dialog.filedialog.askopenfilename',return_value=str(path)),patch('material_dialog.messagebox.askyesno',return_value=True):dlg.add();pump(lambda:not app.busy)
        pump();m=app.project['materials'][0];assert m['status']=='texto_extraido' and not m['shared_routes'] and not calls;checks.append('Attachment extracted locally without provider call or sharing')
        assert 'Interlineado 1.5' in dlg.text.get('1.0','end');checks.append('Full extracted text and reading status visible in library')
        with patch('app.messagebox.askyesno',return_value=True),patch('material_dialog.messagebox.askyesno',return_value=True):dlg.share()
        m=app.project['materials'][0];assert m['shared_routes'] and all(not a.requests for a in calls);checks.append('Sharing requires explicit grant and does not itself send model request')
        dlg.tree.selection_set(m['id']);dlg.revoke();assert not app.project['materials'][0]['shared_routes'];checks.append('Revocation clears future excerpt sharing')
        dlg.tree.selection_set(m['id']);dlg.rules();pump()
        w=next(w for w in dlg.win.winfo_children() if isinstance(w,tk.Toplevel));tree=next(w for w in w.winfo_children() if isinstance(w, __import__('tkinter').ttk.Treeview))
        tree.selection_set(tree.get_children());button=next(w for w in w.winfo_children() if isinstance(w,__import__('tkinter').ttk.Button));button.invoke();pump()
        assert app.project['format_profile']['effective']['spacing']==1.5 and app.project['format_profile']['effective']['heading_size']==14;checks.append('Selected evidenced guide rules approved into project, no Word mutation')
        with patch('material_dialog.messagebox.askyesno',return_value=True):dlg.clear_profile()
        assert not app.project.get('format_profile');checks.append('Restoring APA base is explicit and preserves file')
        dlg.tree.selection_set(m['id'])
        with patch('material_dialog.messagebox.askyesno',return_value=True):dlg.retire()
        assert not app.project['materials'][0]['active'];checks.append('Retiring version keeps original but excludes future retrieval')
        dlg.close();app.thread_settings();pump();w=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel));check=next(w for w in w.winfo_children() if isinstance(w,__import__('tkinter').ttk.Checkbutton));assert check.instate(['selected']);checks.append('Persistent thread is default; only the unverified affinity header is switchable')
        check.invoke();button=next(w for w in w.winfo_children() if isinstance(w,__import__('tkinter').ttk.Button) and w.cget('text')=='Guardar');button.invoke();pump();assert app.project['copilot_affinity'] is False;checks.append('Continuity settings saved without Microsoft network call')
        app.project['provider_references']=[{'title':'Referencia de prueba','url':'https://example.org/paper','status':'contenido no verificado'}];app.tabs.select(3);app.provider_references();assert 'no verificado' in app.source_text.get('1.0','end');checks.append('Structured provider references displayed without upgrading evidence status')
        root.geometry('740x560');pump()
        for i in range(5):
            app.tabs.select(i);pump()
            for widget in app.controls:
                if widget.winfo_exists() and widget.winfo_viewable():
                    assert widget.winfo_rootx()+widget.winfo_width()<=root.winfo_rootx()+root.winfo_width()+1,str(widget)
                    assert widget.winfo_rooty()+widget.winfo_height()<=root.winfo_rooty()+root.winfo_height()+1,str(widget)
        checks.append('New file, thread and reference controls fit minimum main window')
        assert not errors,errors;checks.append('No Tk callback exceptions')
    finally:root.after_cancel(app.timer);root.destroy()
Path('reports/ui-v040.json').write_text(json.dumps({'passed':len(checks),'checks':checks},indent=2));print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
