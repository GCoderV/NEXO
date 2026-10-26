import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from project_store import ProjectStore,Conflict,set_fact,message,export_markdown,SECTIONS
from agent import Agent,unpack,context,apply_proposal
from bibliography import add_fragment,add_sources,search
from config import Config
from providers import API,local_endpoint
from word_bridge import WordBridge,WordError,validate_snapshot

TOPIC_A='Juegos de roles cooperativos para producción oral en inglés en secundaria'
TOPIC_B='Revisión documental de la eficiencia energética en edificios residenciales'

def reply(text='Propuesta de trabajo.',**kwargs):return dict(reply=text,facts=[],drafts=[],question=None,search=None,**kwargs) if not kwargs else {**dict(reply=text,facts=[],drafts=[],question=None,search=None),**kwargs}
class FakeAPI:
    provider='Groq';model='simulated';key='TEST-SECRET';endpoint='';last_usage={}
    def __init__(self,responses):self.responses=list(responses);self.requests=[];self.instructions=''
    def request(self,conversation,declarations):
        self.requests.append(copy.deepcopy(conversation));self.last_usage={'input_tokens':100,'output_tokens':30}
        v=self.responses.pop(0)
        if isinstance(v,Exception):raise v
        return {},v if isinstance(v,str) else json.dumps(v,ensure_ascii=False),[]
class FakeProtector:
    def seal(self,s):return s[::-1]
    def open(self,s):return s[::-1]

class StoreTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.s=ProjectStore(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_empty_start(self):self.assertEqual(self.s.list(),[])
    def test_no_case_seed(self):
        p=self.s.create('Un tema nuevo');self.assertEqual(p['facts'],{});self.assertIsNone(p['profile']);self.assertEqual(p['sources'],[])
    def test_two_project_isolation(self):
        a=self.s.create(TOPIC_A);b=self.s.create(TOPIC_B);set_fact(a,'poblacion','24 estudiantes');self.s.save(a)
        self.assertNotIn('poblacion',self.s.load(b['id'])['facts']);self.assertNotIn('24 estudiantes',context(self.s.load(b['id']),'continúa'))
    def test_restart_keeps_state(self):
        p=self.s.create(TOPIC_A);set_fact(p,'nivel','grado');self.s.save(p);s=ProjectStore(self.temp.name);self.assertEqual(s.load(p['id'])['facts']['nivel']['value'],'grado')
    def test_optimistic_conflict(self):
        p=self.s.create('tema');q=self.s.load(p['id']);set_fact(p,'nivel','grado');self.s.save(p)
        with self.assertRaises(Conflict):self.s.save(q)
    def test_invalid_id(self):
        with self.assertRaises(ValueError):self.s.load('../../other')
    def test_recovery_no_replay(self):
        p=self.s.create('tema');p['run']['status']='modelo';self.s.save(p);q=self.s.recover(self.s.load(p['id']));self.assertEqual(q['run']['status'],'interrumpido')
    def test_six_checkpoints(self):
        p=self.s.create('tema')
        for _ in range(12):self.s.save(p)
        with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM checkpoints').fetchone()[0],6)
    def test_change_invalidates(self):
        p=self.s.create('tema');set_fact(p,'metodologia','mixta');self.s.update_draft(p,'metodologia','Un borrador');set_fact(p,'metodologia','cualitativa');self.assertEqual(p['drafts']['metodologia']['status'],'necesita_revision')
    def test_new_fact_invalidates_existing_drafts(self):
        p=self.s.create('tema');self.s.update_draft(p,'objetivos','Objetivos provisionales');set_fact(p,'metodologia','documental')
        self.assertEqual(p['drafts']['objetivos']['status'],'necesita_revision')
    def test_same_fact_no_invalidation(self):
        p=self.s.create('tema');set_fact(p,'nivel','grado');self.s.update_draft(p,'objetivos','Texto');set_fact(p,'nivel','grado');self.assertEqual(p['drafts']['objetivos']['status'],'borrador')
    def test_stale_cannot_approve(self):
        p=self.s.create('tema');self.s.update_draft(p,'objetivos','Texto');self.s.change_topic(p,'Otro tema')
        with self.assertRaises(ValueError):self.s.approve_draft(p,'objetivos')
    def test_manual_revision_keeps_versions(self):
        p=self.s.create('tema');self.s.update_draft(p,'objetivos','Original');self.s.update_draft(p,'objetivos','Nuevo');self.assertEqual(p['drafts']['objetivos']['versions'][0]['text'],'Original')
    def test_approve_only_explicit(self):
        p=self.s.create('tema');self.s.update_draft(p,'objetivos','Texto');self.assertEqual(p['drafts']['objetivos']['status'],'borrador');self.s.approve_draft(p,'objetivos');self.assertEqual(p['drafts']['objetivos']['status'],'aprobado_usuario')
    def test_export_not_docx(self):
        p=self.s.create('tema');self.assertIn('ni un DOCX',export_markdown(p))
    def test_data_correction_revokes_ready(self):
        p=self.s.create('tema');set_fact(p,'datos','Datos reales');p['data_ready']=True;set_fact(p,'datos','Datos corregidos');self.assertFalse(p['data_ready'])

class AgentTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.s=ProjectStore(self.temp.name);self.p=self.s.create(TOPIC_A)
    def tearDown(self):self.temp.cleanup()
    def run_agent(self,r,text='Continúa',**kwargs):
        api=FakeAPI(r if isinstance(r,list) else [r]);agent=Agent(self.s,api,**kwargs);p=agent.turn(self.p['id'],text,allow_research=kwargs.pop('allow_research',False)) if 'allow_research' in kwargs else agent.turn(self.p['id'],text);return p,api
    def test_topic_to_draft_and_question(self):
        r=reply(drafts=[dict(section='delimitacion',text='Propuesta delimitada a este tema, pendiente de contexto.',sources=[])],question=dict(key='nivel',text='¿Para qué nivel académico?',clarify=False))
        p,api=self.run_agent(r);self.assertIn('delimitacion',p['drafts']);self.assertEqual(p['questions'][0]['status'],'abierta');self.assertEqual(len(api.requests),1)
    def test_extract_user_facts_only(self):
        r=reply(facts=[dict(key='nivel',value='grado',evidence='Es de grado')]);p,_=self.run_agent(r,'Es de grado');self.assertEqual(p['facts']['nivel']['value'],'grado')
    def test_invented_fact_rejected(self):
        r=reply(facts=[dict(key='poblacion',value='24 estudiantes',evidence='24 estudiantes')]);p,_=self.run_agent(r,'No he elegido población');self.assertNotIn('poblacion',p['facts'])
    def test_known_question_not_repeated(self):
        set_fact(self.p,'nivel','grado');self.s.save(self.p);p,_=self.run_agent(reply(question=dict(key='nivel',text='¿Qué nivel?',clarify=False)));self.assertEqual(p['questions'],[])
    def test_clarifying_question_allowed(self):
        set_fact(self.p,'contexto','escuela');self.s.save(self.p);p,_=self.run_agent(reply(question=dict(key='contexto',text='¿En qué nivel de esa escuela?',clarify=True)));self.assertEqual(len(p['questions']),1)
    def test_answer_resolves_pending(self):
        p,_=self.run_agent(reply(question=dict(key='nivel',text='¿Qué nivel?',clarify=False)));self.p=p
        p,_=self.run_agent(reply(facts=[dict(key='nivel',value='grado',evidence='grado')]),'grado');self.assertEqual(p['questions'][0]['status'],'respondida')
    def test_deferred_not_repeated(self):
        self.p['questions']=[dict(key='nivel',text='¿Nivel?',status='aplazada')];self.s.save(self.p);p,_=self.run_agent(reply(question=dict(key='nivel',text='¿Nivel?',clarify=False)));self.assertEqual(len(p['questions']),1)
    def test_unknown_source_blocks_draft(self):
        p,_=self.run_agent(reply(drafts=[dict(section='marco_teorico',text='Se comprobó [F99].',sources=['F99'])]));self.assertNotIn('marco_teorico',p['drafts'])
    def test_known_source_allowed_but_not_verified(self):
        add_fragment(self.p,'Fuente','Fragmento de prueba','p. 2');self.s.save(self.p)
        p,_=self.run_agent(reply(drafts=[dict(section='marco_teorico',text='Interpretación provisional [F1].',sources=['F1'])]));self.assertEqual(p['drafts']['marco_teorico']['status'],'borrador')
    def test_no_empirical_results_without_data(self):
        for key in ('resultados','discusion','conclusiones'):
            p,_=self.run_agent(reply(drafts=[dict(section=key,text='Mejora del 80 %',sources=[])]));self.assertNotIn(key,p['drafts'])
    def test_no_data_claim_does_not_unlock_results(self):
        p,_=self.run_agent(reply(facts=[dict(key='datos',value='No hay datos',evidence='No hay datos')],drafts=[dict(section='resultados',text='Resultados ficticios',sources=[])]),'No hay datos');self.assertNotIn('resultados',p['drafts'])
    def test_confirmed_data_allows_proposal(self):
        set_fact(self.p,'datos','Registros aportados');self.p['data_ready']=True;self.s.save(self.p)
        p,_=self.run_agent(reply(drafts=[dict(section='resultados',text='Resumen de los registros, por revisar.',sources=[])]));self.assertIn('resultados',p['drafts'])
    def test_invalid_json_no_state_changes(self):
        p,api=self.run_agent('not json');self.assertEqual(p['facts'],{});self.assertEqual(p['drafts'],{});self.assertEqual(len(api.requests),1)
    def test_no_extra_command(self):
        with self.assertRaises(ValueError):unpack(json.dumps({**reply(),'powershell':'bad'}))
    def test_no_automatic_retry_429(self):
        p,api=self.run_agent(RuntimeError('429 quota'));self.assertEqual(len(api.requests),1);self.assertEqual(p['run']['status'],'error')
    def test_no_secret_persistence(self):
        p,_=self.run_agent(reply(text='TEST-SECRET'),'Mi clave TEST-SECRET');self.assertNotIn('TEST-SECRET',json.dumps(p))
    def test_stop_prevents_call(self):
        e=threading.Event();e.set();p,api=self.run_agent(reply(),stop=e);self.assertEqual(api.requests,[]);self.assertEqual(p['run']['status'],'detenido')
    def test_usage_counts(self):
        p,_=self.run_agent(reply());self.assertEqual(p['usage'],dict(calls=1,input_tokens=100,output_tokens=30))
    def test_research_off_no_network(self):
        called=[];p,api=self.run_agent(reply(search=dict(query='role play English',reason='Ubicar antecedentes')),searcher=lambda q:called.append(q));self.assertEqual(called,[])
    def test_research_denied_no_network(self):
        called=[];api=FakeAPI([reply(search=dict(query='English education',reason='Antecedentes'))]);a=Agent(self.s,api,lambda *x:False,lambda q:called.append(q));p=a.turn(self.p['id'],'Busca antecedentes',True);self.assertEqual(called,[]);self.assertEqual(len(api.requests),1)
    def test_research_budget_and_followup(self):
        query=dict(query='English education',reason='Antecedentes');called=[]
        def searcher(q):called.append(q);return [dict(title='Fixture',authors='A',year='2020',doi='10.1/test',url='https://doi.org/10.1/test',status='solo metadatos consultados',excerpt='',locator='')]
        api=FakeAPI([reply(search=query),reply(drafts=[dict(section='justificacion',text='Hay un candidato bibliográfico [F1]; falta leerlo.',sources=['F1'])],search=query)])
        p=Agent(self.s,api,lambda *x:True,searcher).turn(self.p['id'],'Busca antecedentes',True)
        self.assertEqual(len(called),1);self.assertEqual(len(api.requests),2);self.assertEqual(len(p['sources']),1);self.assertIn('justificacion',p['drafts'])
    def test_context_no_other_project(self):
        b=self.s.create(TOPIC_B);set_fact(b,'contexto','PRIVATE-B');self.s.save(b)
        p,api=self.run_agent(reply());self.assertNotIn('PRIVATE-B',json.dumps(api.requests));self.assertNotIn(TOPIC_B,json.dumps(api.requests))
    def test_context_excludes_word_path(self):
        self.p['word_path']='C:/SECRET/doc.docx';self.assertNotIn('SECRET',context(self.p,'Sigue'))
    def test_context_limit_preserves_message(self):
        for i in range(100):message(self.p,'assistant','old'*1000)
        self.assertLessEqual(len(context(self.p,'LATEST MESSAGE')),24000);self.assertIn('LATEST MESSAGE',context(self.p,'LATEST MESSAGE'))
    def test_history_kept_locally(self):
        for i in range(15):message(self.p,'user',f'Unique item {i}')
        self.s.save(self.p);p,_=self.run_agent(reply());self.assertTrue(any(m['text']=='Unique item 0' for m in p['messages']))
    def test_same_project_new_provider(self):
        api=FakeAPI([reply()]);api.provider='Gemini';p=Agent(self.s,api).turn(self.p['id'],'Continúa');self.assertEqual(p['id'],self.p['id']);self.assertIn('parts',api.requests[0][0])
    def test_references_are_host_generated(self):
        p,_=self.run_agent(reply(drafts=[dict(section='referencias',text='Invented author 2025',sources=[])]));self.assertEqual(p['drafts']['referencias']['text'],'Sin fuentes registradas.')

class ConfigTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory()
    def tearDown(self):self.temp.cleanup()
    def test_no_pc_import(self):
        c=Config(self.temp.name,FakeProtector());self.assertEqual(c.data['profiles'],{})
    def test_memory_only_secret(self):
        c=Config(self.temp.name,FakeProtector());c.save('Groq','model','', 'abc-secret',False);self.assertNotIn('abc-secret',c.path.read_text());self.assertEqual(c.key('Groq','model',''),'abc-secret')
    def test_separate_model_keys(self):
        c=Config(self.temp.name,FakeProtector());c.save('Groq','one','','FIRST');c.save('Groq','two','','SECOND');self.assertEqual(c.key('Groq','one',''),'FIRST')
    def test_persisted_protected(self):
        c=Config(self.temp.name,FakeProtector());c.save('Groq','one','','SECRET',True);c2=Config(self.temp.name,FakeProtector());self.assertEqual(c2.key('Groq','one',''),'SECRET')
    def test_no_plaintext_fallback(self):
        from secrets_store import WindowsProtector
        if __import__('os').name=='nt':self.skipTest('DPAPI tested separately on Windows')
        with self.assertRaises(RuntimeError):WindowsProtector().seal('secret')
    def test_ollama_loopback_only(self):
        for value in ('https://example.com','http://localhost:11434/path','http://user:pass@localhost:11434'):
            with self.assertRaises(ValueError):local_endpoint(value)
    def test_cloud_model_rejected(self):
        with self.assertRaises(ValueError):API('Ollama','','gpt-cloud')

class BibliographyTests(unittest.TestCase):
    def test_duplicate_doi(self):
        p={'sources':[]};item=dict(doi='10.1/X',title='title');add_sources(p,[item]);add_sources(p,[dict(doi='10.1/x',title='duplicate')]);self.assertEqual(len(p['sources']),1)
    def test_fragment_requires_locator(self):
        with self.assertRaises(ValueError):add_fragment({'sources':[]},'Title','Text','')
    def test_fragment_no_complete_claim(self):
        p={'sources':[]};add_fragment(p,'Title','Text','p2');self.assertIn('no verificada',p['sources'][0]['status'])
    def test_query_bound(self):
        with self.assertRaises(ValueError):search('a'*251)
    def test_rows_bound(self):
        with self.assertRaises(ValueError):search('test',6)

class FakeWord:
    def __init__(self):self.path=r'C:\test.docx';self.text='Texto';self.start=1;self.hwnd=4;self.active=self.path;self.effects=[];self.fail=False
    def snapshot(self):return dict(path=self.path,text=self.text,start=self.start,end=self.start+len(self.text),hwnd=self.hwnd,hash=hashlib.sha256(self.text.encode()).hexdigest())
    def __call__(self,r):
        if r['action']=='list':return dict(ok=True,documents=[dict(path=self.path)])
        if r['path']!=self.active:raise WordError('Documento distinto')
        if r['action']=='read':return dict(ok=True,snapshot=self.snapshot())
        if r['snapshot']!=self.snapshot():raise WordError('Rango cambió')
        self.effects.append(r['action'])
        if self.fail:raise WordError('Fallo después del efecto')
        return dict(ok=True,operation=r['operation'],text_unchanged=True,text_verified=True,tracked=True,saved=False)
class WordTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.f=FakeWord();self.b=WordBridge(Path(self.temp.name)/'log',self.f);self.b.bind(self.f.path)
    def tearDown(self):self.temp.cleanup()
    def test_explicit_approval(self):
        self.b.read()
        with self.assertRaises(WordError):self.b.insert('text')
        self.assertFalse(self.f.effects)
    def test_comment(self):self.b.read();self.b.comment('text',True);self.assertEqual(self.f.effects,['comment'])
    def test_insert(self):self.b.read();r=self.b.insert('text',True);self.assertTrue(r['tracked']);self.assertFalse(r['saved'])
    def test_insert_at_cursor(self):self.f.text='';self.b.read();self.b.insert('text',True);self.assertEqual(self.f.effects,['insert'])
    def test_comment_requires_selection(self):
        self.f.text='';self.b.read()
        with self.assertRaises(WordError):self.b.comment('text',True)
    def test_stale_range(self):
        self.b.read();self.f.start=8
        with self.assertRaises(WordError):self.b.insert('text',True)
        self.assertFalse(self.f.effects)
    def test_other_document(self):
        self.b.read();self.f.active='other'
        with self.assertRaises(WordError):self.b.insert('text',True)
    def test_no_replay(self):
        self.b.read();self.b.insert('text',True)
        with self.assertRaises(WordError):self.b.insert('text',True)
        self.assertEqual(len(self.f.effects),1)
    def test_failure_consumes_snapshot(self):
        self.b.read();self.f.fail=True
        with self.assertRaises(WordError):self.b.insert('text',True)
        self.assertIsNone(self.b.snapshot);self.assertEqual(len(self.f.effects),1)
    def test_log_no_sensitive_text(self):
        self.b.read();self.b.insert('SECRET-CONTENT',True);self.assertNotIn('SECRET-CONTENT',self.b.journal.read_text());self.assertNotIn(self.f.path,self.b.journal.read_text())
    def test_static_no_replacement(self):
        script=Path('word_bridge.ps1').read_text();self.assertIn('.TrackRevisions=$true',script);self.assertIn('.InsertAfter(',script);self.assertNotIn('.Save(',script);self.assertNotIn('.SaveAs',script);self.assertNotIn('Invoke-Expression',script)

if __name__=='__main__':unittest.main()
