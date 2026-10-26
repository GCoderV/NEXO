"""Real Tk regression checks, scripted model, temporary files; no provider key.
Linux: xvfb-run -a python test_gui.py. Windows: py -3 test_gui.py.
"""
import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
from app import Application
from storage import Store
from settings import Settings
from test_upgrade import SequenceAPI, TestProtector, plan_call
from test_nexo import write_call

checks=[]
with tempfile.TemporaryDirectory() as temp:
    data=Path(temp)/'data';work=Path(temp)/'work'
    root=tk.Tk();app=Application(root,Store(data),Settings(data,TestProtector()))
    def pump(condition,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('Timed out waiting for GUI condition')
    def walk(widget):
        for child in widget.winfo_children():
            yield child
            yield from walk(child)
    def find_button(parent,text):return next(w for w in walk(parent) if isinstance(w,ttk.Button) and w.cget('text')==text)
    instances=[]
    def fake_api(provider,key,model,endpoint='',timeout=120):
        batches=([[plan_call()]] if app.approval.get()=='plan' and not app.autonomous.get() else [])+[[write_call('a.txt','Prueba de Nexo 0.3\n')],[write_call('b.txt','Segunda acción\n')]]
        api=SequenceAPI(batches);api.provider=provider;api.model=model;api.key=key;api.endpoint=endpoint;instances.append(api);return api
    try:
        root.update();checks.append('Real Tk initialized')
        root.geometry('480x400+20+20');root.update()
        assert root.winfo_width()==480 and root.winfo_height()==400;checks.append('Window shrinks to 480 x 400')
        assert app.send.winfo_rooty()+app.send.winfo_height()<=root.winfo_rooty()+root.winfo_height()
        assert app.send.winfo_rootx()+app.send.winfo_width()<=root.winfo_rootx()+root.winfo_width()
        assert app.stop_button.winfo_viewable() and app.log.winfo_height()>25;checks.append('Send, stop and chat visible at minimum size')
        root.geometry('880x700');root.update()
        app.workspace.set(str(work));app.consent.set(True);app.key.set('GUI-TEST-SECRET');app.mode.set('ACT');app.update_mode()
        app.input.focus_force();root.update();app.input.insert('1.0','Primera línea')
        app.input.event_generate('<Shift-Return>');root.update()
        assert app.input.get('1.0','end-1c')=='Primera línea\n' and not app.busy;checks.append('Shift+Enter inserts newline without sending')
        app.input.insert('end','Crea los dos archivos de prueba.')
        approval_count=[];original_dialog=app.approval_dialog
        def count_dialog(*args):approval_count.append(args[0]);return original_dialog(*args)
        app.approval_dialog=count_dialog
        with patch('app.API',side_effect=fake_api):
            app.input.event_generate('<Return>');root.update()
            pump(lambda:app.pending is not None)
            assert app.busy and app.input.get('1.0','end-1c')=='';checks.append('Enter sends and consumes key instead of inserting newline')
            assert not (work/'a.txt').exists();checks.append('Plan approval happens before writes')
            app.input.event_generate('<Return>');root.update();assert len(instances)==1;checks.append('Repeated Enter while busy does not enqueue another task')
            dialog=app.pending[0]
            tabs=next(w for w in walk(dialog) if isinstance(w,ttk.Notebook));assert len(tabs.tabs())==2;checks.append('Plan and exact capability scope shown')
            find_button(dialog,'Aprobar plan y ejecutar').invoke()
            pump(lambda:not app.busy)
            assert (work/'a.txt').exists() and (work/'b.txt').exists();checks.append('One approved plan executes two separate tool rounds')
            assert approval_count==['execution_plan'];checks.append('No repeated approvals for covered actions')
            assert len(app.store.checkpoints(work))==2;checks.append('Automatic checkpoint for both writes')
            assert 'disabled' not in app.send.state();checks.append('Send button re-enabled after task')
            assert 'GUI-TEST-SECRET' not in (data/'preferences.json').read_text();checks.append('Profile persistence uses protector, not plaintext')
            app.new_session();app.key.set('');app.sessions_list.selection_set(0);app.load_session()
            assert app.key.get()=='GUI-TEST-SECRET' and app.session;checks.append('Session reload restores profile key')
            app.show_sessions();root.update();assert app.sessions_list.size()==1;checks.append('History opens in separate resizable window')
            app.session_window.event_generate('<<Noop>>');app.session_window.protocol('WM_DELETE_WINDOW')
            # Use the window close protocol, preserving the hidden selection widget.
            root.tk.call(app.session_window.protocol('WM_DELETE_WINDOW'));root.update()
            app.new_session()
            with patch('app.messagebox.askyesno',return_value=True):app.auto_toggle.invoke()
            assert app.autonomous.get() and app.mode.get()=='ACT';checks.append('Autonomy can be explicitly activated')
            app.input.insert('1.0','Haz la prueba otra vez.');app.send.invoke()
            pump(lambda:not app.busy)
            assert len(instances)==2 and approval_count==['execution_plan'];checks.append('Send button works and autonomous file actions require no dialogs')
            with patch('app.messagebox.askyesno',return_value=True):app.auto_toggle.invoke()
            assert not app.autonomous.get();checks.append('Autonomy can be disabled')
            app.new_session();app.approval.set('step');app.input.insert('1.0','Tarea para detener.');app.send.invoke()
            pump(lambda:app.pending is not None);app.cancel();pump(lambda:not app.busy)
            assert app.session['status']=='interrupted' and app.pending is None;checks.append('Stop closes pending approval without executing it')
        # Per-model keys and profile switching are tested in the actual widgets.
        app.new_session();app.show_settings();root.update()
        assert len(next(w for w in walk(app.config_window) if isinstance(w,ttk.Notebook)).tabs())==4;checks.append('Configuration split into four tabs including Voice')
        app.config_window.geometry('450x400');root.update()
        save=find_button(app.config_window,'Guardar perfil y ajustes')
        assert save.winfo_rooty()+save.winfo_height()<=app.config_window.winfo_rooty()+app.config_window.winfo_height();checks.append('Settings save button visible at compact size')
        app.model.set('profile-b');app.model_changed();assert app.key.get()==''
        app.key.set('SECOND-KEY');assert app.save_preferences();app.model.set('openai/gpt-oss-120b');app.model_changed()
        assert app.key.get()=='GUI-TEST-SECRET';checks.append('Switching model restores the correct distinct key')
        app.provider.set('Ollama');app.provider_changed();root.update();assert app.key.get()=='';checks.append('Ollama profile does not inherit a cloud API key')
        assert 'disabled' in app.config_widgets['key'].state();checks.append('API key field disabled for Ollama')
        with patch('app.ollama_models',return_value=['fixture:small']):
            app.detect_models();pump(lambda:'1 modelos' in app.settings_status.get())
        assert 'fixture:small' in app.config_widgets['model'].cget('values');checks.append('Ollama discovery updates model picker asynchronously')
        root.tk.call(app.config_window.protocol('WM_DELETE_WINDOW'));root.update()
        app.show_details();root.update()
        for w in root.winfo_children():
            if isinstance(w,tk.Toplevel):w.destroy()
        # Screenshot is explicitly labelled simulation. Pillow is optional for running these tests.
        app.provider.set('Groq');app.model.set('openai/gpt-oss-120b');app.restore_key();app.update_profile_label()
        app.approval.set('plan');app.mode.set('ACT');app.update_mode();app.clear_ui();app.session_label.configure(text='Vista de prueba · modelo simulado, sin API real')
        app.emit_ui('Tú','Organiza las notas del proyecto y prepara un resumen.')
        app.emit_ui('Nexo','Te propongo tres pasos:\n\n1. Leer las notas de la carpeta elegida.\n2. Crear un resumen con tareas pendientes.\n3. Comprobar el archivo y conservar un checkpoint.\n\nEn modo por plan, apruebas una vez. Después continúo sin interrumpirte por cada archivo.')
        app.emit_ui('Prueba de interfaz','Esta captura usa una respuesta simulada. No se ha consultado un modelo real.')
        app.input.insert('1.0','Empieza con las notas de esta semana.');app.status.set('Listo · tú eliges el nivel de control');root.geometry('880x700+20+20');root.update()
        try:
            from PIL import ImageGrab
            ImageGrab.grab().crop((root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save('vista-interfaz.png')
            root.geometry('480x400+20+20');root.update()
            ImageGrab.grab().crop((root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save('vista-compacta.png')
        except ImportError:pass
        # A fresh application must not resume autonomy or broad rights, but can restore a profile.
        app.settings.save_preferences({'provider':'Groq','model':'profile-b'})
        second=tk.Toplevel(root);other=Application(second,Store(data),Settings(data,TestProtector()));root.update()
        assert other.key.get()=='SECOND-KEY';checks.append('Fresh application restores saved per-model key (test protector)')
        assert not other.autonomous.get() and not other.broad.get();checks.append('Fresh application does not restore autonomous or broad permissions')
        second.destroy()
    finally:root.destroy()

report={'environment':'Real Tk on current OS; scripted API; temporary files; test protector, NOT actual Windows DPAPI','passed':len(checks),'checks':checks}
Path('pruebas-interfaz.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
