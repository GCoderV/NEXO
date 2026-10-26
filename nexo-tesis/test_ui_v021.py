"""User-reported regressions in real Tk. No real credentials or Office COM."""
import json,sys,tempfile,time,tkinter as tk
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'tests'))
from test_core import FakeProtector,FakeAPI,reply
from test_v02 import session
from config import Config
from project_store import ProjectStore
from app import Application
checks=[]
with tempfile.TemporaryDirectory() as t:
    c=Config(t,FakeProtector());c.save('Gemini','gemini-2.5-flash','','OLD-FAKE');root=tk.Tk();store=ProjectStore(t);responses=[];apis=[]
    def factory():
        api=FakeAPI(responses.pop(0));apis.append(api);return api
    app=Application(root,store,c,api_factory=factory);errors=[];root.report_callback_exception=lambda *e:errors.append(str(e))
    def pump(condition=lambda:True):
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('Tk timeout')
    try:
        app.settings();dlg=app.settings_window;pump()
        dlg.ap.set('Copilot365');dlg.alias.set('Institucional de prueba')
        with patch('settings_dialog.messagebox.askyesno',return_value=True),patch('copilot_socket.launch_desktop',return_value=7777),patch('copilot_socket.capture_connection',return_value=session()):
            dlg.connect_copilot();pump(lambda:not dlg.working);pump()
        assert dlg.provider.get()=='Copilot365',dlg.provider.get();assert dlg.model.get()=='auto';checks.append('Copilot capture callback does not revert to previously selected Gemini after queued Tk events')
        aid=dlg.account_id;assert any(r['provider']=='Copilot365' and r['account_id']==aid for r in c.data['routes']);checks.append('Observed Copilot account has a visible selectable route immediately')
        assert c.data['current']['provider']=='Gemini';checks.append('Adding account alone does not silently switch recipient or enable automatic rotation')
        dlg.use_route();pump();assert c.data['current']['provider']=='Copilot365';assert 'Copilot365' in app.provider_label['text'];checks.append('Guardar y usar selects Copilot and updates main window')
        dlg.new_account();dlg.ap.set('Groq');dlg.alias.set('Nueva Groq');dlg.secret.set('NEW-FAKE');dlg.save_account();pump()
        assert dlg.provider.get()=='Groq';assert dlg.account_map[dlg.account_choice.get()]==dlg.account_id;checks.append('New API account immediately appears in matching provider model list')
        dlg.model.set('typed-compatible-model');dlg.use_route();pump();assert c.data['current']['model']=='typed-compatible-model';checks.append('Guardar y usar saves the visible edited model instead of silently selecting old table row')
        dlg.refresh();pump();assert dlg.provider.get()=='Groq';checks.append('Programmatic table refresh does not overwrite provider/model editor')
        dlg.close();app.project=None;app.render()
        text='Tema: Lectura crítica\nNivel: grado\nInstitución: Universidad indicada\nMétodo: revisión documental\nDatos: corpus todavía no disponible'
        r=reply(topic={'text':'Lectura crítica','evidence':'Tema: Lectura crítica'},facts=[{'key':'nivel','value':'grado','evidence':'grado'},{'key':'institucion','value':'Universidad indicada','evidence':'Universidad indicada'},{'key':'metodologia','value':'revisión documental','evidence':'revisión documental'}],questions=[{'key':'guia','text':'¿Qué guía o requisitos deben aplicarse?','clarify':False},{'key':'alcance','text':'¿Qué periodo y alcance deseas?','clarify':False}])
        responses.append([r]);app.put(app.input,text)
        with patch('app.messagebox.askyesno',return_value=True):app.send();pump(lambda:not app.busy)
        assert app.project['topic']=='Lectura crítica';assert len(apis)==1;assert len(app.project['facts'])==3;checks.append('Pasted initial multi-line data creates project and extracts explicit topic/facts in one model call')
        assert len(app.project['questions'])==2;assert app.project['messages'][-1]['text'].count('¿')==2;assert len([m for m in app.project['messages'] if m['role']=='user'])==1;checks.append('Only missing initial questions appear together without duplicate user message')
        class Native:
            calls=[]
            def __call__(self,q):
                self.calls.append(q)
                if q['action']=='create':return {'ok':True,'operation':q['operation'],'created':True,'saved':False,'name':'Documento1'}
                if q['action']=='open':return {'ok':True,'operation':q['operation'],'opened':True,'path':q['path'],'name':'copy.docx','readonly':False,'saved':False}
                return {'ok':True,'documents':[]}
        from word_bridge import WordBridge
        native=Native();app.bridge=WordBridge(Path(t)/'word-audit',native)
        with patch('app.messagebox.askyesno',return_value=False):app.word_create()
        assert native.calls==[];checks.append('Declining native document creation sends no Word action')
        with patch('app.messagebox.askyesno',return_value=True):app.word_create();pump(lambda:not app.busy)
        assert native.calls[-1]['action']=='create';assert 'Guárdalo' in app.status.get();checks.append('Approved creation requests native unsaved Word document and explains save requirement')
        with patch('app.messagebox.askyesno',return_value=True),patch('app.filedialog.askopenfilename',return_value='C:/Copies/copy.docx'):app.word_open();pump(lambda:not app.busy)
        assert app.word_choice.get()==r'C:\Copies\copy.docx';assert native.calls[-1]['action']=='open';assert app.bridge.snapshot is None;checks.append('Opening an exact DOCX selects it without reading content or auto-inserting')
        app.word_list();pump(lambda:not app.busy);assert 'no hay DOCX' in app.status.get();checks.append('Empty Word list is reported as empty rather than Documents found')
        root.geometry('740x560');app.tabs.select(4);pump()
        for w in app.controls:
            if w.winfo_exists() and w.winfo_viewable():
                assert w.winfo_rootx()+w.winfo_width()<=root.winfo_rootx()+root.winfo_width()+1,str(w)
                assert w.winfo_rooty()+w.winfo_height()<=root.winfo_rooty()+root.winfo_height()+1,str(w)
        checks.append('Additional native Word buttons fit minimum window size')
        assert not errors,errors;checks.append('No Tk callback exceptions in regression scenarios')
    finally:
        root.after_cancel(app.timer);root.destroy()
Path('reports/ui-v021.json').write_text(json.dumps({'passed':len(checks),'checks':checks},indent=2));print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
