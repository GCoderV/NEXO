"""Real mouse menus/Tk widgets with simulated ASR/TTS. Never records audio."""
import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
from app import Application
from settings import Settings
from storage import Store
from test_upgrade import TestProtector
from voice import VoiceFlow
from voice_assets import REQUIRED_MODEL_FILES

class FakeRecorder:
    def __init__(self):self.token=0;self.epoch=0;self.paused=True;self.starts=0
    def start(self,model):self.token+=1;self.epoch=0;self.paused=True;self.starts+=1;return self.token
    def pause(self,value):
        if self.paused!=value:self.paused=value;self.epoch+=1
    def stop(self):self.token+=1;self.paused=True;self.epoch+=1
class FakeSpeaker:
    def __init__(self):self.token=0;self.spoken=[]
    def speak(self,text,language,voice_id,rate):self.token+=1;self.spoken.append((text,language,voice_id,rate));return self.token
    def stop(self):self.token+=1

checks=[]
with tempfile.TemporaryDirectory() as temp:
    root=tk.Tk();data=Path(temp)/'data';app=Application(root,Store(data),Settings(data,TestProtector()))
    app.recorder=FakeRecorder();app.speaker=FakeSpeaker();now=[100.0];app.voice_flow=VoiceFlow(lambda:now[0])
    model=Path(temp)/'model'
    for name in REQUIRED_MODEL_FILES:
        file=model/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'fixture')
    app.voice_model.set(str(model))
    def pump(condition,seconds=3):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('Timed out in voice UI test')
    def select_menu(label):
        menu=app.last_text_menu
        for i in range(menu.index('end')+1):
            if menu.type(i)=='command' and menu.entrycget(i,'label')==label:
                menu.invoke(i);menu.unpost();return
        raise AssertionError('Menu command missing: '+label)
    def activate():
        root.focus_force();app.input.focus_force();app.voice_resume_at=0;root.update()
        with patch('voice_ui.messagebox.askyesno',return_value=True):app.mic_button.invoke()
        app.voice_event(app.recorder.token,{'type':'ready'});app.voice_resume_at=0;app.voice_tick()
        assert app.voice_flow.active and not app.recorder.paused
    def final(text,confidence=.99,token=None,epoch=None):
        app.voice_event(app.recorder.token if token is None else token,{'type':'final','text':text,'confidence':confidence,'epoch':app.recorder.epoch if epoch is None else epoch})
    try:
        root.geometry('480x400+20+20');root.update()
        for button in [app.mic_button,app.read_button,app.paste_button,app.native_button,app.send,app.stop_button]:
            assert button.winfo_width()>=button.winfo_reqwidth(),(button.cget('text'),button.winfo_width(),button.winfo_reqwidth())
            assert button.winfo_rootx()+button.winfo_width()<=root.winfo_rootx()+root.winfo_width()
            assert button.winfo_rooty()+button.winfo_height()<=root.winfo_rooty()+root.winfo_height()
        checks.append('Mouse and voice controls fit at 480 x 400 without clipped buttons')
        root.geometry('880x700');root.update();app.clear_ui();message='Respuesta completa con acentos: México, agrimensura y revisión.';app.emit_ui('Nexo',message);root.update()
        assert not app.voice_flow.active and not app.voice_speaking;checks.append('Microphone and playback off on startup')
        buttons=[w for w in app.message_action_widgets[-1].winfo_children() if isinstance(w,ttk.Button)]
        buttons[0].invoke();assert root.clipboard_get()==message;checks.append('Copy response button copies full unmodified response')
        app.log.tag_add('sel','2.0','2.9');app.log.event_generate('<Button-3>',x=25,y=35);root.update();select_menu('Copiar selección')
        assert root.clipboard_get()=='Respuesta';checks.append('Right-click copies selection from read-only chat')
        app.log.tag_remove('sel','1.0','end');app.log.event_generate('<Button-3>',x=25,y=35);root.update();select_menu('Copiar este mensaje')
        assert root.clipboard_get()==message;checks.append('Right-click copies whole message without selecting it')
        app.clipboard_write('Texto pegado\ncon otra línea');app.input.event_generate('<Button-3>',x=10,y=10);root.update();select_menu('Pegar')
        assert app.input.get('1.0','end-1c')=='Texto pegado\ncon otra línea' and not app.busy;checks.append('Right-click pastes multiline text without submitting')
        app.input.event_generate('<Button-3>',x=10,y=10);root.update();select_menu('Seleccionar todo')
        assert app.selected_text(app.input)=='Texto pegado\ncon otra línea';checks.append('Mouse select-all works in editor')
        app.input.event_generate('<Button-3>',x=10,y=10);root.update();select_menu('Cortar')
        assert app.input.get('1.0','end-1c')=='';checks.append('Mouse cut copies and removes selection')
        app.paste_button.invoke();assert app.input.get('1.0','end-1c')=='Texto pegado\ncon otra línea';checks.append('Dedicated Paste button works')
        app.input.delete('1.0','end');app.select_all(app.log);app.paste_text(app.log)
        assert app.log.get('1.0','end-1c').startswith('NEXO\nRespuesta');checks.append('Paste cannot modify read-only chat')
        app.log.tag_remove('sel','1.0','end');activate();checks.append('One microphone click activates opt-in continuous mode')
        final('hola nexo');assert app.input.get('1.0','end-1c')=='hola nexo';checks.append('Final transcription appears in editor')
        sent=[]
        def send():sent.append(app.input.get('1.0','end-1c'));app.input.delete('1.0','end');app.before_voice_send();app.busy=True
        with patch.object(app,'start',side_effect=send):
            now[0]=102;app.voice_tick();assert not sent
            app.voice_event(app.recorder.token,{'type':'partial','epoch':app.recorder.epoch});now[0]=104;app.voice_tick();assert not sent
            checks.append('Continued speech postpones automatic send')
            now[0]=105;app.voice_tick();app.voice_tick();assert sent==['hola nexo'];checks.append('Silence deadline sends exactly once')
            before=app.input.get('1.0','end-1c');final('no se captura mientras trabaja');assert app.input.get('1.0','end-1c')==before
            checks.append('Recognition cannot submit while agent is busy')
            app.busy=False;app.voice_resume_at=0;app.voice_tick();app.session={'status':'idle'};app.voice_last_answer='Esta es la respuesta de prueba.'
            app.after_voice_task();assert app.voice_speaking and app.recorder.paused;checks.append('Response reading pauses microphone first')
            final('eco de la respuesta');assert app.input.get('1.0','end-1c')=='';checks.append('Speech output cannot be transcribed back into chat')
            app.voice_output_event(app.speaker.token,{'ok':True});app.voice_resume_at=0;app.voice_tick()
            assert not app.recorder.paused and app.recorder.starts==1;checks.append('Listening resumes without another microphone click')
            final('segunda pregunta');now[0]+=3;app.voice_tick();assert sent==['hola nexo','segunda pregunta'];checks.append('Second spoken turn works in same continuous session')
            app.busy=False;app.voice_resume_at=0;app.voice_tick();final('no enviar');final('nexo cancelar');now[0]+=20;app.voice_tick()
            assert len(sent)==2 and 'no enviar' in app.input.get('1.0','end-1c');checks.append('Spoken cancel preserves draft and cancels submission')
            final('nexo borrar');assert app.input.get('1.0','end-1c')=='';checks.append('Spoken clear deletes draft without tool action')
            final('texto dudoso',.3);now[0]+=20;app.voice_tick();assert len(sent)==2 and app.voice_flow.review_required
            final('nexo enviar');assert len(sent)==2;checks.append('Low-confidence transcription cannot auto-send or bypass review with voice command')
            app.voice_flow.sent();app.input.delete('1.0','end');final('pregunta válida');final('nexo enviar');assert len(sent)==3
            checks.append('Explicit Nexo enviar sends a confident draft')
            app.busy=False;app.voice_resume_at=0;app.voice_tick();app.pending=('fixture',None,None);final('sí');assert len(sent)==3
            app.pending=None;checks.append('Voice does not approve pending security dialogs')
            app.voice_tick();final('borrador conservado');other=tk.Toplevel(root);entry=tk.Entry(other);entry.pack();entry.focus_force();root.update();app.voice_tick()
            assert app.recorder.paused and app.voice_flow.deadline is None;checks.append('Moving focus to another window pauses mic and cancels countdown')
            previous=app.input.get('1.0','end-1c');final('no dictar en ajustes');assert app.input.get('1.0','end-1c')==previous
            other.destroy();app.input.focus_force();root.update();app.voice_resume_at=0;app.voice_tick();now[0]+=30;app.voice_tick();assert len(sent)==3
            checks.append('Returning focus does not silently send old pending draft')
            stale_epoch=app.recorder.epoch-1;final('audio obsoleto',epoch=stale_epoch);assert app.input.get('1.0','end-1c')==previous
            checks.append('Stale pre-pause recognition results are ignored')
            old_token=app.recorder.token;app.mic_button.invoke();final('audio tardío',token=old_token);now[0]+=30;app.voice_tick();assert len(sent)==3
            checks.append('Same microphone button stops listening and drops late results')
        app.session=None;app.input.delete('1.0','end');app.read_response('Lectura manual')
        assert app.voice_speaking and app.speaker.spoken[-1][1]=='es-MX';checks.append('Manual reading defaults to Mexican Spanish')
        app.read_button.invoke();assert not app.voice_speaking;checks.append('Speaker button stops playback')
        with patch('voice_ui.messagebox.askyesno',return_value=True),patch('voice_ui.open_windows_dictation') as native:
            app.native_button.invoke();pump(lambda:app.native_dictation)
            assert native.call_count==1 and not app.voice_flow.active;checks.append('Native Windows dictation shortcut is separate from local microphone')
            with patch('voice_ui.messagebox.showinfo'):
                before=len(app.speaker.spoken);app.read_response('No leer sobre Win+H');assert len(app.speaker.spoken)==before
            checks.append('Reading blocked while native dictation is marked open to avoid feedback')
            app.native_button.invoke();assert not app.native_dictation and native.call_count==1
            checks.append('Closing Win+H requires user confirmation, never an unsafe blind toggle')
        app.show_settings();root.update()
        with patch('voice_ui.native_voices',return_value=[{'id':'mx-fixture','name':'Voz de prueba México','language':'es-MX'},{'id':'es-fixture','name':'Voz de prueba España','language':'es-ES'}]):
            app.detect_voices();pump(lambda:app.voice_id.get()=='mx-fixture')
        checks.append('Installed voice picker prefers es-MX without inventing a voice')
        app.voice_selected.set('es-ES · Voz de prueba España');app.voice_picker.event_generate('<<ComboboxSelected>>');root.update()
        assert app.voice_language.get()=='es-ES' and app.voice_id.get()=='es-fixture';checks.append('Other speech language requires explicit voice selection')
        app.settings.save_preferences(app.voice_preferences());saved=app.settings.data['preferences'];assert 'voice_active' not in saved
        checks.append('Voice preferences persist but microphone activation does not')
        root.tk.call(app.config_window.protocol('WM_DELETE_WINDOW'));root.update()
        # No native voice or real recognition has been used anywhere in this script.
    finally:
        app.shutdown_voice();root.destroy()

report={'passed':len(checks),'environment':'Real Tk and clipboard; simulated microphone, recognition, synthesis, and Win+H shortcut; no audio captured or played','checks':checks}
Path('pruebas-voz-interfaz.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
