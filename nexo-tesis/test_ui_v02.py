"""Real Tk interactions; fake providers, no Microsoft login or inference."""
import json,sys,tempfile,time,tkinter as tk,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'tests'))
from test_core import FakeAPI,FakeProtector,reply
from project_store import ProjectStore
from config import Config
from app import Application
from providers import ProviderError
checks=[]
with tempfile.TemporaryDirectory() as d:
    root=tk.Tk();store=ProjectStore(d);c=Config(d,FakeProtector());responses=[];apis=[]
    def factory():
        api=FakeAPI(responses.pop(0));apis.append(api);return api
    app=Application(root,store,c,api_factory=factory)
    errors=[];root.report_callback_exception=lambda *e:errors.append(str(e))
    def pump(condition=lambda:True):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('UI timed out')
    try:
        app.settings();dlg=app.settings_window;pump();checks.append('Account/routing settings open in actual Tk without network')
        dlg.ap.set('Groq');dlg.alias.set('Trabajo');dlg.secret.set('UI-FAKE-KEY');dlg.save_account();aid=dlg.account_id
        dlg.provider.set('Groq');dlg.change_provider();dlg.model.set('fixture-one');dlg.auto.set(True);dlg.save_route();dlg.use_route();pump()
        rid=c.data['current']['route_id'];assert c.data['current']['model']=='fixture-one';checks.append('Named account saved and explicitly selected route')
        dlg.model.set('fixture-two');dlg.save_route();assert len(c.data['accounts'])==1 and {'fixture-one','fixture-two'}.issubset({r['model'] for r in c.data['routes']});checks.append('Same provider key reused for second selectable model')
        dlg.model.set('fixture-two');dlg.refresh_accounts();dlg.model_combo.configure(values=['fixture-one','fixture-two']);assert dlg.model.get()=='fixture-two';checks.append('Model selection is not reset while listing accounts')
        dlg.provider.set('Ollama');dlg.change_provider()
        with patch('settings_dialog.list_models',return_value=[{'id':'downloaded:8b','cost':'local'}]) as listed:
            dlg.refresh_models();pump(lambda:not dlg.working)
        assert tuple(dlg.model_combo['values'])==('downloaded:8b',);assert listed.call_args.args[0]=='Ollama';checks.append('Ollama refresh fills model dropdown asynchronously')
        dlg.tabs.select(dlg.accounts_tab);dlg.win.geometry('720x590');pump()
        for tab in (dlg.routes_tab,dlg.accounts_tab,dlg.policy_tab):
            dlg.tabs.select(tab);pump()
            for w in dlg.widgets:
                if w.winfo_viewable():
                    assert w.winfo_rootx()+w.winfo_width()<=dlg.win.winfo_rootx()+dlg.win.winfo_width()+1,('horizontal',str(w),w.cget('text') if 'text' in w.keys() else '')
                    assert w.winfo_rooty()+w.winfo_height()<=dlg.win.winfo_rooty()+dlg.win.winfo_height()+1,('vertical',str(w))
        checks.append('Settings controls fit all tabs at minimum geometry')
        dlg.win.geometry('840x650');dlg.tabs.select(dlg.routes_tab);pump()
        try:
            from PIL import ImageGrab
            ImageGrab.grab().crop((dlg.win.winfo_rootx(),dlg.win.winfo_rooty(),dlg.win.winfo_rootx()+dlg.win.winfo_width(),dlg.win.winfo_rooty()+dlg.win.winfo_height())).save('reports/settings-v02.png')
            checks.append('Fresh screenshot of settings captured')
        except ImportError:pass
        dlg.close();c.select(rid);app.new_project('Un tema sin caso predeterminado');pid=app.project['id']
        responses.append([ProviderError('quota','quota')]);app.input.insert('1.0','Original pending instruction')
        with patch('app.messagebox.askyesno',return_value=True):app.send();pump(lambda:not app.busy)
        assert app.project.get('pending') and not app.input.get('1.0','end-1c');checks.append('Failed message remains pending without restoring duplicate composer text')
        before=len([m for m in app.project['messages'] if m['role']=='user']);responses.append([reply()])
        with patch('app.messagebox.askyesno',return_value=True):app.resume_button.invoke();pump(lambda:not app.busy)
        assert not app.project.get('pending');assert len([m for m in app.project['messages'] if m['role']=='user'])==before;checks.append('Reanudar button finishes pending request without duplicate user message')
        # Real routed API authorization path, with no request sent.
        routed=c.api();app.project=store.load(pid)
        with patch('app.messagebox.askyesno',return_value=True) as ask:
            assert app.authorize(routed);n=ask.call_count;assert app.authorize(routed);assert ask.call_count==n
        checks.append('Recipient consent persists per project and is not repeatedly requested')
        c.account('Groq','Trabajo','NEW-FAKE-KEY',aid=aid)
        with patch('app.messagebox.askyesno',return_value=False) as ask:assert not app.authorize(c.api());assert ask.call_count==1
        checks.append('Replacing a credential invalidates old recipient consent')
        app.settings();dlg=app.settings_window;gate=threading.Event();dlg.async_job(lambda:gate.wait(2),lambda v:(_ for _ in ()).throw(AssertionError('stale callback')));dlg.close();gate.set();pump();time.sleep(.15);pump();checks.append('Closing settings cancels callback without stale UI writes')
        assert not errors,errors;checks.append('No Python Tk callback exceptions')
    finally:
        root.after_cancel(app.timer);root.destroy()
Path('reports/ui-v02.json').write_text(json.dumps({'passed':len(checks),'checks':checks},indent=2),encoding='utf8');print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
