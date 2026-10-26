"""Actual Tk UI, simulated language model and Word. Temporary project database."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'tests'))
from test_core import FakeAPI,FakeProtector,FakeWord,reply,TOPIC_A,TOPIC_B
from project_store import ProjectStore,set_fact
from config import Config
from app import Application
from word_bridge import WordBridge
checks=[]
with tempfile.TemporaryDirectory() as temp:
    store=ProjectStore(temp);config=Config(temp,FakeProtector());config.save('Groq','fake','','FAKE-KEY')
    apis=[];responses=[];fakeword=FakeWord()
    def api_factory():
        api=FakeAPI(responses.pop(0));apis.append(api);return api
    root=tk.Tk();app=Application(root,store,config,api_factory=api_factory,word_factory=lambda path:WordBridge(path,fakeword))
    def pump(condition):
        until=time.monotonic()+6
        while time.monotonic()<until:
            root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('Tk timeout')
    try:
        root.update();assert app.project is None and not store.list();checks.append('Starts empty, no fixed investigation and no network/model call')
        assert len(app.tabs.tabs())==5;checks.append('Independent conversational workspace with five supporting tabs')
        app.input.insert('1.0',TOPIC_A);app.send();root.update();aid=app.project['id'];assert app.project['topic']==TOPIC_A and not apis;checks.append('A topic alone creates a project without provider requirement')
        responses.append([reply(facts=[dict(key='nivel',value='grado',evidence='grado')],drafts=[dict(section='delimitacion',text='Borrador del proyecto A',sources=[])],question=dict(key='contexto',text='¿En qué contexto se trabajará?',clarify=False))])
        app.input.insert('1.0','Es de grado')
        with patch('app.messagebox.askyesno',return_value=True):app.send();pump(lambda:not app.busy)
        assert app.project['facts']['nivel']['value']=='grado';assert 'Borrador del proyecto A' in app.project['drafts']['delimitacion']['text'];checks.append('Conversation records explicitly supported facts and produces a draft')
        assert app.project['questions'][0]['status']=='abierta';checks.append('The next adaptive question is persisted')
        app.defer_question();assert app.project['questions'][0]['status']=='aplazada';checks.append('Question can be deferred without fabricating an answer')
        app.tabs.select(1);app.draft_text.insert('end',' — revisión humana');app.save_draft();assert 'revisión humana' in store.load(aid)['drafts']['delimitacion']['text'];checks.append('Human draft revision saved without calling a provider')
        with patch('app.messagebox.askyesno',return_value=True):app.approve_draft()
        assert app.project['drafts']['delimitacion']['status']=='aprobado_usuario';checks.append('User approval is explicit and does not write to Word')
        app.to_word();assert not fakeword.effects and 'Borrador del proyecto A' in app.word_proposal.get('1.0','end');checks.append('Preparing Word proposal has no native mutation')
        app.word_list();pump(lambda:not app.busy)
        with patch('app.messagebox.askyesno',return_value=True):app.word_read();pump(lambda:not app.busy)
        assert app.project['word_path']==fakeword.path;checks.append('Word binding is scoped to the current project after explicit read approval')
        before_calls=len(apis)
        with patch('app.messagebox.askyesno',return_value=False):app.word_to_chat()
        assert not app.input.get('1.0','end-1c');checks.append('Declining Word-to-chat preparation leaves the composer empty')
        with patch('app.messagebox.askyesno',return_value=True):app.word_to_chat()
        assert app.input_origin=='seleccion_word' and fakeword.text in app.input.get('1.0','end-1c') and len(apis)==before_calls;checks.append('Approved Word excerpt becomes an unsent document-origin message, no API call')
        app.put(app.input,'');app.input_origin='usuario';app.tabs.select(4)
        with patch('app.messagebox.askyesno',return_value=False):app.word_apply('insert')
        assert not fakeword.effects;checks.append('Rejecting insertion prevents a native mutation')
        with patch('app.messagebox.askyesno',return_value=True):app.word_apply('insert');pump(lambda:not app.busy)
        assert fakeword.effects==['insert'];assert app.project['drafts']['delimitacion']['status']=='insertado_pendiente_revision_word';checks.append('Approved insertion is marked pending Word review, not final thesis completion')
        assert app.bridge.snapshot is None;checks.append('Word read authorization consumed; no duplicate insertion on repeated click')
        app.new_project(TOPIC_B);bid=app.project['id'];assert aid!=bid and app.project['facts']=={} and app.project['sources']==[];checks.append('Second unrelated project has no first-project facts or sources')
        assert app.bridge.path is None and not app.word_proposal.get('1.0','end-1c');checks.append('Switching projects clears Word binding and proposal')
        responses.append([reply(facts=[dict(key='tipo_trabajo',value='revisión documental',evidence='revisión documental')],drafts=[dict(section='delimitacion',text='Borrador documental sobre energía',sources=[])])])
        app.input.insert('1.0','Es una revisión documental')
        with patch('app.messagebox.askyesno',return_value=True):app.send();pump(lambda:not app.busy)
        ctx=json.dumps(apis[-1].requests,ensure_ascii=False);assert TOPIC_A not in ctx and 'grado' not in ctx;checks.append('Second-project model request excludes first-project topic and level')
        assert 'documental' in app.project['facts']['tipo_trabajo']['value'];checks.append('Different work type retained without forcing action research')
        app.open_project(aid);assert app.project['facts']['nivel']['value']=='grado';assert app.project['questions'][0]['status']=='aplazada';checks.append('Reopening restores decisions and deferred question')
        set_fact(app.project,'metodologia','investigación-acción');store.save(app.project);app.render();assert app.project['drafts']['delimitacion']['status']=='necesita_revision';checks.append('New methodological decision invalidates dependent draft')
        try:app.to_word();raise AssertionError('Should reject stale draft')
        except ValueError:pass
        checks.append('Stale draft cannot be prepared for native insertion')
        root.geometry('740x560');root.update()
        for i in range(5):
            app.tabs.select(i);root.update()
            for w in app.controls:
                if w.winfo_exists() and w.winfo_viewable():
                    assert w.winfo_rootx()+w.winfo_width()<=root.winfo_rootx()+root.winfo_width()+1,(i,getattr(w,'cget')('text') if 'text' in w.keys() else str(w))
                    assert w.winfo_rooty()+w.winfo_height()<=root.winfo_rooty()+root.winfo_height()+1,i
        checks.append('All visible controls fit the minimum-size window on all tabs')
        root.geometry('1040x750');app.tabs.select(0);root.update()
        try:
            from PIL import ImageGrab
            ImageGrab.grab().crop((root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save('reports/interfaz.png');checks.append('Actual Tk screenshot captured')
        except ImportError:pass
        # Native calls are simulated; no secret imported from another product.
        assert not app.allow_research.get();checks.append('Research permissions reset on project switch')
        responses.append([RuntimeError('quota')]);app.input.insert('1.0','Continúa')
        with patch('app.messagebox.askyesno',return_value=True):app.send();pump(lambda:not app.busy)
        assert app.project['run']['status']=='error';assert len(apis[-1].requests)==1;checks.append('Provider error is visible, stored and not automatically retried')
        assert app.input.cget('state')=='normal';checks.append('Composer becomes usable after an error')
    finally:
        root.after_cancel(app.timer);root.destroy()
Path('reports/ui.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'environment':'Actual Linux Tk, fake provider and Word, temporary SQLite projects'},ensure_ascii=False,indent=2))
print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False,indent=2))
