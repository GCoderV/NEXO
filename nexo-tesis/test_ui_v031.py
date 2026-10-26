"""Real Tk autonomous execution with scripted APIs, no authenticated provider or Word COM."""
import sys,json,tempfile,time,threading,tkinter as tk
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'tests'))
from test_core import FakeAPI,FakeProtector,FakeWord,reply
from test_v031 import draft
from app import Application
from config import Config
from project_store import ProjectStore
from word_bridge import WordBridge
checks=[]
with tempfile.TemporaryDirectory() as t:
    root=tk.Tk();store=ProjectStore(t);pool=[];made=[];native=FakeWord()
    def factory():
        api=pool.pop(0);made.append(api);return api
    app=Application(root,store,Config(t,FakeProtector()),api_factory=factory,word_factory=lambda p:WordBridge(p,native));errors=[];root.report_callback_exception=lambda *e:errors.append(str(e))
    def pump(condition=lambda:True):
        end=time.monotonic()+6
        while time.monotonic()<end:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('Tk timeout')
    try:
        app.new_project('Lectura crítica');pump();assert not made;checks.append('Opening a project never starts autonomous calls')
        app.auto_limit.set('2');declined=FakeAPI([]);pool.append(declined)
        with patch('app.messagebox.askyesno',return_value=False):app.autonomous()
        assert not declined.requests and not app.busy;checks.append('Declining batch plan sends no model request')
        a=FakeAPI([reply(drafts=[draft('delimitacion','Delimitación nueva.')])]);b=FakeAPI([reply(drafts=[draft('problematica','Problema desarrollado.')])]);pool.extend([a,b])
        with patch('app.messagebox.askyesno',return_value=True):app.autonomous();pump(lambda:not app.busy)
        assert app.project['autonomy']['completed']==['delimitacion','problematica'];assert len(a.requests)==len(b.requests)==1;checks.append('One approval executes two concrete tasks without additional Continue clicks')
        assert '2/2' in app.status.get() and 'Word' in app.status.get();checks.append('Final batch summary reports saved changes and no Word edits')
        assert not native.effects;assert not [m for m in app.project['messages'] if m['role']=='user'];checks.append('Synthetic steps neither mutate Word nor masquerade as user declarations')
        before=len(made);pid=app.project['id'];app.open_project(pid);pump();assert len(made)==before;checks.append('Reopening completed project performs no automatic work')
        app.put(app.input,'Texto todavía no enviado')
        try:app.autonomous();raise AssertionError('unsent input accepted')
        except ValueError:pass
        assert app.input.get('1.0','end-1c')=='Texto todavía no enviado';app.put(app.input,'');checks.append('Unsent input is preserved and blocks starting a batch')
        # Manual Continue now dispatches an explicit target and verifies a changed draft.
        c=FakeAPI([reply('Puedo continuar.'),reply(drafts=[draft('pregunta','¿Cómo se desarrolla la lectura crítica en el contexto indicado?')])]);pool.append(c)
        with patch('app.messagebox.askyesno',return_value=True):app.continue_work();pump(lambda:not app.busy)
        assert len(c.requests)==2 and 'pregunta' in app.project['drafts'];checks.append('Manual Continue targets next section and corrects one empty promise')
        assert app.status.get().startswith('Paso guardado');checks.append('Old batch summary does not mask a later manual turn result')
        app.new_project('Otra investigación');pump();gate=threading.Event();entered=threading.Event()
        class Waiting(FakeAPI):
            def request(self,*a):entered.set();gate.wait(4);return super().request(*a)
        first=FakeAPI([reply(drafts=[draft('delimitacion','Avance guardado antes de detener.')])]);second=Waiting([reply(drafts=[draft('problematica','No aplicar después de detener.')])]);pool.extend([first,second])
        with patch('app.messagebox.askyesno',return_value=True):
            app.autonomous();pump(lambda:entered.is_set() and 'delimitacion' in app.project['drafts'])
            assert app.busy and app.input.cget('state')=='disabled' and str(app.stop_button.cget('state'))!='disabled';checks.append('Saved progress is visible during batch; editor locked and Stop available')
            app.cancel();gate.set();pump(lambda:not app.busy)
        assert 'delimitacion' in app.project['drafts'] and 'problematica' not in app.project['drafts'];assert app.project.get('pending');checks.append('Stop preserves completed task and never applies a response arriving after cancellation')
        before=len(made);app.open_project(app.project['id']);pump();assert len(made)==before;checks.append('Opening interrupted work does not replay the pending request')
        root.geometry('740x560');app.tabs.select(0);pump()
        for w in app.controls:
            if w.winfo_exists() and w.winfo_viewable():
                assert w.winfo_rootx()+w.winfo_width()<=root.winfo_rootx()+root.winfo_width()+1,str(w)
                assert w.winfo_rooty()+w.winfo_height()<=root.winfo_rooty()+root.winfo_height()+1,str(w)
        checks.append('Autonomy controls fit minimum window size')
        from test_v030 import state
        from word_layout_dialog import WordLayoutDialog
        st=state('Índice','Objetivos 1','Objetivos','Texto');st['tocs']=[{'start':st['paragraphs'][1]['start'],'end':st['paragraphs'][1]['end']}];word_calls=[]
        def inspect(r):word_calls.append(r);return {'ok':True,'structure':st}
        app.bridge=WordBridge(Path(t)/'repair-log',inspect);app.bridge.bind(st['path']);app.bridge.inspect_document();dialog=WordLayoutDialog(app,st);pump()
        assert not dialog.index_button.instate(['disabled']);checks.append('Index-only recovery shortcut enabled for one existing TOC')
        if dialog.keys:dialog.list.selection_set(0)
        dialog.index_only();pump();assert dialog.plan['format_all'] is False and dialog.plan['operations']==[] and dialog.plan['toc']['mode']=='update';checks.append('Index-only preview clears insertions and whole-document reformatting')
        with patch('word_layout_dialog.messagebox.askyesno',return_value=False):dialog.apply()
        assert [r['action'] for r in word_calls]==['inspect'];dialog.win.destroy();checks.append('Index-only repair still requires explicit approval and makes no pre-approval changes')
        assert not errors,errors;checks.append('No Tk callback exceptions')
    finally:
        root.after_cancel(app.timer);root.destroy()
Path('reports/ui-v031.json').write_text(json.dumps({'passed':len(checks),'checks':checks},indent=2));print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
