import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from agent import Agent,unpack,SYSTEM,context
from project_store import ProjectStore,FACT_KEYS
from config import Config
from word_bridge import WordBridge,WordError
from test_core import FakeAPI,FakeProtector,reply
from test_v02 import session

class IntakeTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.s=ProjectStore(self.tmp.name);self.p=self.s.create('Un tema propio')
    def tearDown(self):self.tmp.cleanup()
    def test_all_fields_from_one_text_one_call_no_repeated_questions(self):
        values=['maestría','Universidad aportada','Educación','anteproyecto','método mixto','Centro aportado','24 estudiantes','Diagnóstico narrativo, sin conteos','Guía aportada de tres páginas','periodo 2026–2027','comprender la dificultad, sin inventar resultados']
        text='\n'.join(k+': '+v for k,v in zip(FACT_KEYS,values))
        facts=[{'key':k,'value':v,'evidence':v} for k,v in zip(FACT_KEYS,values)]
        questions=[{'key':k,'text':'¿Cuál es '+k+'?','clarify':False} for k in FACT_KEYS]
        api=FakeAPI([reply(facts=facts,questions=questions)]);p=Agent(self.s,api).turn(self.p['id'],text)
        self.assertEqual(len(api.requests),1);self.assertEqual(len(p['facts']),len(FACT_KEYS));self.assertEqual(p['questions'],[])
        for k,v in zip(FACT_KEYS,values):self.assertEqual(p['facts'][k]['value'],v)
        self.assertFalse(p['data_ready']);self.assertEqual(len(ProjectStore(self.tmp.name).load(p['id'])['facts']),len(FACT_KEYS))
    def test_missing_questions_in_one_answer_and_one_call(self):
        q=[{'key':k,'text':'Pregunta '+k,'clarify':False} for k in ('nivel','institucion','tipo_trabajo','metodologia','guia')]
        api=FakeAPI([reply(questions=q)]);p=Agent(self.s,api).turn(self.p['id'],'Continúa')
        self.assertEqual(len(api.requests),1);self.assertEqual(len(p['questions']),5)
        for item in q:self.assertIn(item['text'],p['messages'][-1]['text'])
        self.assertIn('un único texto',p['messages'][-1]['text'])
    def test_single_text_answers_several_pending_questions(self):
        q=[{'key':k,'text':'Pregunta '+k,'clarify':False} for k in ('nivel','institucion','metodologia')]
        p=Agent(self.s,FakeAPI([reply(questions=q)])).turn(self.p['id'],'Continúa')
        facts=[{'key':k,'value':v,'evidence':v} for k,v in [('nivel','grado'),('institucion','Universidad indicada'),('metodologia','documental')]]
        p=Agent(self.s,FakeAPI([reply(facts=facts,questions=q)])).turn(p['id'],'Grado: grado, Universidad indicada, estudio documental')
        self.assertEqual([q['status'] for q in p['questions']],['respondida']*3)
        self.assertEqual(len(p['questions']),3)
    def test_same_missing_field_not_asked_again_with_different_wording(self):
        p=Agent(self.s,FakeAPI([reply(questions=[{'key':'nivel','text':'¿Nivel?'}])])).turn(self.p['id'],'continúa')
        p=Agent(self.s,FakeAPI([reply(questions=[{'key':'nivel','text':'¿Qué grado cursas?'}])])).turn(p['id'],'continúa')
        self.assertEqual(len(p['questions']),1)
    def test_paste_up_to_12000_kept_whole_in_current_message(self):
        text='Datos aportados. '+('a'*11000)
        api=FakeAPI([reply()]);p=Agent(self.s,api).turn(self.p['id'],text)
        self.assertEqual(json.loads(api.requests[0][0]['content'])['current_user_message'],text)
        self.assertEqual([m['text'] for m in p['messages'] if m['role']=='user'],[text])
    def test_over_limit_not_saved_or_called(self):
        api=FakeAPI([reply()])
        with self.assertRaises(ValueError):Agent(self.s,api).turn(self.p['id'],'a'*12001)
        self.assertEqual(api.requests,[])
    def test_new_paste_topic_requires_literal_evidence(self):
        self.p['topic_pending']=True;self.s.save(self.p)
        p=Agent(self.s,FakeAPI([reply(topic={'text':'Lectura crítica','evidence':'Tema: Lectura crítica'})])).turn(self.p['id'],'Tema: Lectura crítica\nNivel: grado')
        self.assertEqual(p['topic'],'Lectura crítica');self.assertFalse(p['topic_pending'])
    def test_existing_topic_not_silently_replaced(self):
        p=Agent(self.s,FakeAPI([reply(topic={'text':'Otro tema','evidence':'Otro tema'})])).turn(self.p['id'],'Ejemplo de otra investigación: Otro tema')
        self.assertEqual(p['topic'],'Un tema propio')
    def test_no_invented_topic(self):
        self.p['topic_pending']=True;self.s.save(self.p)
        p=Agent(self.s,FakeAPI([reply(topic={'text':'Inventado','evidence':'Tema inventado'})])).turn(self.p['id'],'No definí el tema')
        self.assertEqual(p['topic'],'Un tema propio')
    def test_word_excerpt_not_promoted_to_facts_or_topic(self):
        self.p['topic_pending']=True;self.s.save(self.p)
        p=Agent(self.s,FakeAPI([reply(topic={'text':'grado','evidence':'grado'},facts=[{'key':'nivel','value':'grado','evidence':'grado'}])])).turn(self.p['id'],'grado',origin='seleccion_word')
        self.assertEqual(p['topic'],'Un tema propio');self.assertEqual(p['facts'],{})
    def test_invalid_question_batch_rejected_whole(self):
        for q in ('text',[{'key':'unexpected','text':'question'}],[{'key':'nivel','text':'q'}]*12):
            with self.assertRaises(ValueError):unpack(json.dumps(reply(questions=q)))
    def test_no_single_question_constraint_in_system(self):
        self.assertNotIn('máximo UNA pregunta',SYSTEM);self.assertIn('UN SOLO BLOQUE',SYSTEM);self.assertIn('questions',SYSTEM)

class AccountAvailabilityTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.c=Config(self.tmp.name,FakeProtector())
    def tearDown(self):self.tmp.cleanup()
    def test_orphan_account_becomes_visible_without_network_auto_or_selection(self):
        aid=self.c.account('Gemini','Nueva','FAKE');before=dict(self.c.data['current'])
        with patch('providers.open_remote',side_effect=AssertionError('network')):rid=self.c.ensure_account_route(aid)
        self.assertEqual(len(self.c.data['routes']),1);self.assertEqual(self.c.data['current'],before);self.assertFalse(self.c.data['routes'][0]['auto']);self.assertEqual(rid,self.c.ensure_account_route(aid))
    def test_copilot_capture_becomes_selectable_without_alias_guess(self):
        aid=self.c.account('Copilot365','Microsoft',session());rid=self.c.ensure_account_route(aid);self.c.select(rid)
        self.assertEqual(self.c.data['current']['provider'],'Copilot365');self.assertEqual(self.c.data['current']['model'],'auto')
    def test_ensure_does_not_reactivate_disabled_routes(self):
        aid=self.c.account('Groq','Cuenta','FAKE');rid=self.c.route('Groq','manual',aid);self.c.data['routes'][0]['enabled']=False
        self.assertEqual(rid,self.c.ensure_account_route(aid));self.assertFalse(self.c.data['routes'][0]['enabled']);self.assertEqual(len(self.c.data['routes']),1)
    def test_missing_session_key_not_made_available(self):
        aid=self.c.account('Groq','Cuenta','FAKE');self.c.memory.clear();self.assertIsNone(self.c.ensure_account_route(aid));self.assertEqual(self.c.data['routes'],[])

class WordRegressionTests(unittest.TestCase):
    def test_read_input_from_textreader_not_console_static_type(self):
        text=(Path(__file__).resolve().parents[1]/'word_bridge.ps1').read_text()
        self.assertIn('[Console]::In.ReadToEnd()',text);self.assertNotIn('[Console]::ReadToEnd()',text)
    def test_create_requires_approval_no_calls_on_rejection(self):
        with tempfile.TemporaryDirectory() as t:
            calls=[];bridge=WordBridge(Path(t)/'audit',lambda q:calls.append(q))
            with self.assertRaises(WordError):bridge.create_document()
            self.assertEqual(calls,[])
    def test_create_native_request_not_save_as(self):
        with tempfile.TemporaryDirectory() as t:
            calls=[]
            def native(q):calls.append(q);return {'ok':True,'operation':q['operation'],'created':True,'saved':False,'name':'Documento1'}
            r=WordBridge(Path(t)/'audit',native).create_document(True)
            self.assertEqual(calls[0]['action'],'create');self.assertTrue(calls[0]['approved']);self.assertNotIn('path',calls[0]);self.assertFalse(r['saved'])
    def test_open_exact_path_and_confirm_operation(self):
        with tempfile.TemporaryDirectory() as t:
            calls=[]
            def native(q):calls.append(q);return {'ok':True,'operation':q['operation'],'opened':True,'path':q['path'],'saved':False}
            bridge=WordBridge(Path(t)/'audit',native);path=r'C:\Copies\Research.docx';bridge.open_document(path,True)
            self.assertEqual(calls[0]['path'],path)
    def test_open_no_approval_or_url_no_calls(self):
        with tempfile.TemporaryDirectory() as t:
            calls=[];bridge=WordBridge(Path(t)/'audit',lambda q:calls.append(q))
            for path,approved in [(r'C:\copy.docx',False),('https://example.invalid/file.docx',True),('relative.docx',True),(r'C:\bad.exe',True)]:
                with self.assertRaises(WordError):bridge.open_document(path,approved)
            self.assertEqual(calls,[])
    def test_document_failure_never_retried(self):
        with tempfile.TemporaryDirectory() as t:
            calls=[]
            def native(q):calls.append(q);raise WordError('failure')
            with self.assertRaises(WordError):WordBridge(Path(t)/'audit',native).create_document(True)
            self.assertEqual(len(calls),1)
    def test_open_temporarily_disables_macros_and_link_updates(self):
        text=(Path(__file__).resolve().parents[1]/'word_bridge.ps1').read_text()
        self.assertIn('$word.AutomationSecurity=3',text);self.assertIn('$word.Options.UpdateLinksAtOpen=$false',text);self.assertIn('$word.AutomationSecurity=$oldSecurity',text)
        self.assertNotIn('SaveAs',text)
