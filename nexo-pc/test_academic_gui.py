"""Real Tk / fake Word transport. No model, no Word, no user files."""
import copy
import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
from unittest.mock import patch
from app import Application
from academic import ProjectStore
from academic_ui import AcademicWindow
from settings import Settings
from storage import Store
from test_upgrade import TestProtector
from test_academic import FakeWord
from word_bridge import WordBridge

checks=[]
with tempfile.TemporaryDirectory() as temp:
    base=Path(temp);root=tk.Tk();app=Application(root,Store(base/'data'),Settings(base/'data',TestProtector()))
    store=ProjectStore(base/'project');fake=FakeWord();bridge=WordBridge(base/'audit.jsonl',fake)
    p=AcademicWindow(app,store,bridge);app.academic_window=p
    def pump(condition):
        end=time.monotonic()+5
        while time.monotonic()<end:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('GUI timeout')
    try:
        root.update();assert len(p.tabs.tabs())==6;checks.append('Panel opens six tabs without model or Word calls')
        assert not fake.calls;checks.append('Opening panel does not connect to Word or read a document')
        assert p.participants.get()=='24';checks.append('Confirmed participant count preloaded')
        p.window.geometry('720x530');root.update()
        for child in p.window.winfo_children():
            assert child.winfo_rooty()+child.winfo_height()<=p.window.winfo_rooty()+p.window.winfo_height()+2
        checks.append('Footer and notebook inside minimum-size window')
        for i in range(6):
            p.tabs.select(i);root.update()
            for b in p.controls:
                if b.winfo_viewable():
                    assert b.winfo_rootx()+b.winfo_width()<=p.window.winfo_rootx()+p.window.winfo_width()
                    assert b.winfo_rooty()+b.winfo_height()<=p.window.winfo_rooty()+p.window.winfo_height()
        checks.append('Buttons fit all six tabs at minimum window size')
        assert not app.voice_foreground();checks.append('Academic modal blocks voice capture and autosend foreground condition')
        p.window.geometry('900x730');root.update()
        p.field_choice.set('Observaciones y aclaraciones');p.change_field();assert 'miedo' in p.editor.get('1.0','end');checks.append('Updated diagnosis includes fear and limited English mastery')
        p.editor.insert('end',' Nota de prueba.');p.field_choice.set('Título');p.change_field();assert 'Nota de prueba.' in p.data['observations'];checks.append('Changing field preserves edits')
        p.action_field_choice.set('Duración');p.change_action();p.put(p.action_editor,'20 minutos, propuesta de prueba');p.action_choice.set('Actividad 2');p.change_action();assert '20 minutos' in p.data['actions'][0]['duration'];checks.append('Action field edits retained independently')
        p.add_source();p.put(p.source_editor,'Fuente de prueba, no real');p.source_field_choice.set('Autoría');p.change_source();assert p.data['sources'][0]['title']=='Fuente de prueba, no real';checks.append('Source fields saved independently')
        p.put(p.source_editor,'Autor de prueba');p.save();assert store.path.exists();checks.append('Local project saved with no provider calls')
        p.review();text=p.review_text.get('1.0','end');assert 'Márgenes' in text and 'metadatos' in text.lower();checks.append('Review reports incomplete profile and source metadata')
        assert 'porcentajes' in text;checks.append('Narrative results are not converted to invented percentages')
        with patch('academic_ui.filedialog.asksaveasfilename',return_value=str(base/'report.md')):
            p.export()
        assert (base/'report.md').exists() and not list(base.glob('*.docx'));checks.append('Export is explicitly Markdown, not Python-generated Word')
        with patch('academic_ui.filedialog.asksaveasfilename',return_value=str(base/'wrong.docx')):
            try:p.export();raise AssertionError('Should reject Word export')
            except ValueError:pass
        checks.append('Export cannot masquerade as DOCX')
        p.tabs.select(5);p.list_word();pump(lambda:not p.busy);assert p.document_choice.get()==fake.path;checks.append('Word enumeration only lists paths until explicit reading approval')
        with patch('academic_ui.messagebox.askyesno',return_value=False):p.read_word()
        assert all(c['action']=='list' for c in fake.calls);checks.append('Declined selection read does not access text')
        with patch('academic_ui.messagebox.askyesno',return_value=True):p.read_word();pump(lambda:not p.busy)
        assert p.word_text.get('1.0','end-1c')==fake.text;checks.append('Approved read displays exact authorized selection')
        assert not app.input.get('1.0','end-1c');checks.append('Word selection is not copied or sent to chat')
        p.put(p.comment_text,'Propuesta para revisar en Word.')
        with patch('academic_ui.messagebox.askyesno',return_value=False):p.comment_word()
        assert not fake.comments;checks.append('Declined comment makes no mutation')
        with patch('academic_ui.messagebox.askyesno',return_value=True):p.comment_word();pump(lambda:not p.busy)
        assert len(fake.comments)==1 and p.bridge.snapshot is None;checks.append('Approved comment consumes snapshot; repeat requires fresh read')
        assert not fake.calls[-1].get('save');checks.append('No document save requested')
        with patch('academic_ui.messagebox.askyesno',return_value=True):p.read_word();pump(lambda:not p.busy)
        fake.text='Changed after review'
        with patch('academic_ui.messagebox.askyesno',return_value=True),patch('academic_ui.messagebox.showerror') as error:
            p.comment_word();pump(lambda:not p.busy)
            assert error.called
        assert len(fake.comments)==1;checks.append('Stale selection rejected and failure displayed without replay')
        p.invalidate_word();assert not p.bridge.path and not p.word_text.get('1.0','end-1c');checks.append('Changing document invalidates old selection')
        # Save a real Tk screenshot when Pillow is available.
        p.tabs.select(4);p.review();root.update()
        try:
            from PIL import ImageGrab
            box=(p.window.winfo_rootx(),p.window.winfo_rooty(),p.window.winfo_rootx()+p.window.winfo_width(),p.window.winfo_rooty()+p.window.winfo_height())
            ImageGrab.grab().crop(box).save('vista-tesis.png');checks.append('Real academic panel screenshot captured')
        except ImportError:pass
        app.input.insert('1.0','Existing draft')
        try:p.handoff('diagnosis');raise AssertionError('Should preserve draft')
        except ValueError:pass
        assert app.input.get('1.0','end-1c')=='Existing draft';checks.append('Chat handoff cannot overwrite existing draft')
        app.input.delete('1.0','end');app.autonomous.set(True);app.broad.set(True);app.mode.set('ACT')
        for flag in ('files','shell','browser','desktop'):app.flags[flag].set(True)
        with patch('academic_ui.messagebox.askyesno',return_value=True):p.handoff('diagnosis')
        assert app.mode.get()=='PLAN' and not app.autonomous.get() and not app.broad.get();checks.append('Academic handoff switches to Plan and revokes broad/autonomous mode')
        assert not any(app.flags[k].get() for k in ('files','shell','browser','desktop'));checks.append('Academic handoff disables file, shell, browser and desktop flags')
        assert app.input.get('1.0','end-1c') and not app.busy and app.session is None;checks.append('Context is a draft only; no model call, task or session created')
        assert 'Changed after review' not in app.input.get('1.0','end-1c');checks.append('Word selection excluded from project context')
        # Regression: external edit cannot be bypassed by closing the panel.
        p=AcademicWindow(app,store,bridge);app.academic_window=p
        p.put(p.editor,'Local unsaved title')
        external=ProjectStore(base/'project');q=external.load();q['title']='External title';external.save(q)
        with patch('academic_ui.messagebox.askyesnocancel',return_value=True):
            try:p.close();raise AssertionError('Should detect conflict')
            except ValueError:pass
        assert external.load()['title']=='External title';checks.append('Close does not bypass optimistic write conflict protection')
        with patch('academic_ui.messagebox.askyesnocancel',return_value=False):p.close()
        app.input.delete('1.0','end');root.geometry('480x400');root.update()
        for child in app.send.master.winfo_children():
            assert child.winfo_rootx()+child.winfo_width()<=root.winfo_rootx()+root.winfo_width()
        checks.append('Main compact chat remains usable after panel closes')
    finally:
        app.shutdown_voice();root.destroy()
report={'release':'0.6.0-academic-pilot','environment':'Linux real Tk; scripted Word transport, no native Word or authenticated API','passed':len(checks),'checks':checks}
Path('pruebas-academico-interfaz.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
