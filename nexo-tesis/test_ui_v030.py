import sys,tempfile,time,tkinter as tk,json,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'tests'))
from test_core import FakeProtector
from test_v030 import state
from app import Application
from project_store import ProjectStore
from config import Config
from word_bridge import WordBridge,WordError
checks=[]
with tempfile.TemporaryDirectory() as t:
    root=tk.Tk();store=ProjectStore(t);app=Application(root,store,Config(t,FakeProtector()));errors=[];root.report_callback_exception=lambda *e:errors.append(str(e))
    app.project=store.create('Tema');app.project['drafts']['objetivos']={'text':'Propuesta nueva.','status':'borrador','sources':[]};store.save(app.project,'test');app.render()
    st=state('Portada','Objetivos','Contenido existente','Metodología','Método');calls=[]
    def transport(r):
        calls.append(r)
        if r['action']=='inspect':return {'ok':True,'structure':copy.deepcopy(st)}
        if r['action']=='layout':return {'ok':True,'operation':r['operation'],'text_verified':True,'saved':False,'inserted':[o['section'] for o in r['plan']['operations']]}
        raise WordError('Unexpected action')
    app.bridge=WordBridge(Path(t)/'log',transport);app.documents=[{'path':st['path']}];app.word_choice.set(st['path'])
    def pump(condition=lambda:True):
        end=time.monotonic()+6
        while time.monotonic()<end:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('Tk timeout')
    def open_dialog():
        with patch('app.messagebox.askyesno',return_value=True):app.word_organize();pump(lambda:not app.busy)
        pump();return app.layout_window
    try:
        with patch('app.messagebox.askyesno',return_value=False):app.word_organize()
        assert not calls;checks.append('Declining local structure inspection reads nothing')
        dlg=open_dialog();assert [r['action'] for r in calls]==['inspect'];checks.append('Automatic placement inspection does not mutate Word or call a model')
        assert dlg.format_all.get() is True and dlg.index.get() is True;checks.append('Entire-document APA and automatic index are defaults requested by user')
        assert dlg.apply_button.instate(['disabled']);checks.append('Approval disabled until a concrete preview exists')
        dlg.list.selection_set(0);pump();dlg.prepare();pump();assert dlg.plan['operations'][0]['position']==st['paragraphs'][3]['start'];checks.append('Preview places selected draft before next section without manual cursor')
        text=dlg.text.get('1.0','end');assert 'Propuesta nueva.' in text and 'Times New Roman 12' in text and 'ENCABEZADOS DETECTADOS' in text;checks.append('Preview contains new text, exact target, detected headings and layout details')
        with patch('word_layout_dialog.messagebox.askyesno',return_value=False):dlg.apply()
        assert len(calls)==1;checks.append('Declining batch approval produces no Word writes')
        dlg.index.set(False);assert dlg.plan is None and dlg.apply_button.instate(['disabled']);checks.append('Changing scope invalidates prior preview')
        dlg.prepare();pump();assert dlg.plan['toc']['mode']=='none';checks.append('Index can be excluded explicitly without changing other approved scope')
        dlg.index.set(True);dlg.prepare();pump()
        with patch('word_layout_dialog.messagebox.askyesno',return_value=True):dlg.apply();pump(lambda:not app.busy)
        assert [r['action'] for r in calls]==['inspect','layout'];assert app.project['drafts']['objetivos']['status']=='insertado_pendiente_revision_word';checks.append('Single batch call and only confirmed insertion marked pending Word review')
        assert app.bridge.prepared_plan is None;checks.append('Applied plan cannot be replayed by UI')
        dlg=open_dialog();dlg.prepare();pump();before=len(calls);store.save(app.project,'changed while preview open')
        with patch('word_layout_dialog.messagebox.showerror') as error:dlg.apply();assert error.called
        assert len(calls)==before;checks.append('Project revision change blocks approval before native call')
        dlg.win.geometry('720x560');pump()
        assert dlg.apply_button.winfo_rootx()+dlg.apply_button.winfo_width()<=dlg.win.winfo_rootx()+dlg.win.winfo_width();assert dlg.apply_button.winfo_rooty()+dlg.apply_button.winfo_height()<=dlg.win.winfo_rooty()+dlg.win.winfo_height();checks.append('Batch approval remains visible at minimum dialog size')
        dlg.win.destroy();assert not errors,errors;checks.append('No Tk callback exceptions in new Word flow')
    finally:root.after_cancel(app.timer);root.destroy()
Path('reports/ui-v030.json').write_text(json.dumps({'passed':len(checks),'checks':checks},indent=2));print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
