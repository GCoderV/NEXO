"""Real Tk continuity and automatic voice-preparation controls; simulated APIs/ASR.
Temporary settings, no personal credentials, no network or physical microphone.
"""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from unittest.mock import patch
from app import Application
from conversation import text_message
from settings import Settings
from storage import Store
from test_upgrade import TestProtector
from voice_assets import REQUIRED_MODEL_FILES

checks=[];requests=[]
class FakeAPI:
    def __init__(self,provider,key,model,endpoint='',timeout=120):
        self.provider,self.key,self.model,self.endpoint=provider,key,model,endpoint;self.last_usage={}
    def request(self,messages,declarations):
        requests.append((self.provider,self.model,copy.deepcopy(messages)))
        self.last_usage={'input_tokens':100,'output_tokens':20}
        return text_message(self.provider,'assistant','Respuesta de prueba para '+self.model),'Respuesta de prueba para '+self.model,[]
with tempfile.TemporaryDirectory() as temp:
    base=Path(temp);root=tk.Tk();app=Application(root,Store(base/'data'),Settings(base/'data',TestProtector()))
    def pump(condition):
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('Timeout in continuity GUI')
    try:
        root.update();app.workspace.set(str(base/'work'));app.key.set('FAKE-GROQ-KEY');app.consent.set(True);app.consent_provider='Groq'
        with patch('app.API',FakeAPI),patch('app.messagebox.showerror') as error,patch('app.messagebox.askyesno',return_value=True) as confirm:
            def send(text):
                app.input.insert('1.0',text);app.start();pump(lambda:not app.busy)
            send('Prepara el trabajo de agrimensura y conserva esta referencia.');id=app.session['id'];initial_display=len(app.session['display'])
            app.model.set('second-model');app.model_changed();app.key.set('FAKE-SECOND-KEY');send('Continúa desde el mismo punto.')
            assert app.session['id']==id and app.session['model']=='second-model';checks.append('Changing model continues same session without New button')
            assert len(app.session['display'])>initial_display and 'agrimensura' in json.dumps(requests[-1][2]);checks.append('Original request and visible conversation remain after model switch')
            assert not error.called;checks.append('No model/server mismatch error blocks Send')
            app.provider.set('Gemini');app.provider_changed();app.key.set('FAKE-GEMINI-KEY');send('Continúa ahora con otro proveedor.')
            assert app.session['id']==id and app.session['provider']=='Gemini';checks.append('Changing provider continues same session')
            assert confirm.called;checks.append('Sending prior context to another provider requires data consent')
            assert all('parts' in m and m['role'] in ('user','model') for m in requests[-1][2]);checks.append('Gemini receives native text format, not foreign tool messages')
            app.provider.set('Groq');app.provider_changed();assert app.key.get()=='FAKE-SECOND-KEY';checks.append('Returning to model restores its distinct key')
            send('Última comprobación de continuidad.');assert app.session['id']==id;checks.append('Roundtrip provider switch keeps one chat')
            assert app.session['usage_totals']=={'input_tokens':400,'output_tokens':80,'reported_requests':4};checks.append('Reported token counts accumulate and appear in UI status')
            assert '480 tokens reportados' in app.status.get()
            root.geometry('480x400');root.update()
            for child in app.status_label.master.winfo_children():
                assert child.winfo_rootx()+child.winfo_width()<=root.winfo_rootx()+root.winfo_width(),child
            checks.append('Token counter does not push footer buttons outside compact window')
            root.geometry('880x700');root.update()
            app.refresh_sessions();app.sessions_list.selection_set(0);app.load_session();assert app.session['id']==id and 'agrimensura' in app.log.get('1.0','end');checks.append('Reloading saved switched session restores original visible history')
            app.workspace.set(str(base/'different-work'));app.input.insert('1.0','No ejecutar aquí');count=len(requests);app.start()
            assert error.called and len(requests)==count;checks.append('Different workspace remains blocked without an API call')
        model=base/'local-model'
        for name in REQUIRED_MODEL_FILES:
            file=model/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'fixture')
        app.input.delete('1.0','end');app.voice_model.set(str(base/'deleted-old-path'))
        with patch('voice_ui.find_model',return_value=model),patch('voice_ui.messagebox.askyesno',return_value=False):
            app.toggle_microphone()
        assert app.voice_model.get()==str(model) and not app.voice_flow.active;checks.append('Stale voice path replaced automatically; microphone consent retained')
        gate=threading.Event();started=threading.Event()
        def prepare(*a,**kw):started.set();assert gate.wait(3);return model
        with patch('voice_ui.find_model',return_value=None),patch('voice_ui.ensure_model',side_effect=prepare),patch('voice_ui.messagebox.askyesno') as consent:
            app.toggle_microphone();assert started.wait(2) and app.voice_preparing
            app.toggle_microphone();gate.set();pump(lambda:not app.voice_preparing)
            assert not app.voice_flow.active and not consent.called;checks.append('Second Mic click cancels deferred activation while local data preparation finishes')
        assert app.settings.data['preferences']['voice_model']==str(model);checks.append('Automatically prepared path persisted without folder chooser')
        app.show_settings();root.update();assert app.economy.get();checks.append('Economy mode is enabled by default and settings open normally')
        root.tk.call(app.config_window.protocol('WM_DELETE_WINDOW'));root.update()
    finally:app.shutdown_voice();root.destroy()
report={'release':'0.5.0','environment':'Real Linux Tk; simulated providers and model preparation; temporary files; no physical audio or authenticated API','passed':len(checks),'checks':checks}
Path('pruebas-continuidad-interfaz.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
