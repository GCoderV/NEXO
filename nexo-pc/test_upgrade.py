"""v0.3 policy/profile/transport regression tests. No live model required."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from adapters import API, Tools, local_endpoint, ollama_models
from permissions import Authorization
from runtime import Runtime, response_parts
from settings import Settings, WindowsProtector
from storage import Store
from test_nexo import write_call

class TestProtector:
    """Test double ONLY, never used by the application. Not encryption."""
    def seal(self,text):return 'fixture:'+text.encode().hex()
    def open(self,text):return bytes.fromhex(text.removeprefix('fixture:')).decode()

class SequenceAPI:
    provider='Groq';model='test-model';key='TEST-KEY-UPGRADE'
    def __init__(self,batches):self.batches=list(batches);self.requests=[]
    def request(self,conversation,declarations):
        self.requests.append(copy.deepcopy(conversation))
        calls=self.batches.pop(0) if self.batches else []
        text='Resultados de prueba simulada.' if not calls else 'Trabajo en el siguiente paso.'
        msg={'role':'assistant','content':text}
        if calls:msg['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':json.dumps(c['args'])}} for c in calls]
        return msg,text,calls

def plan_call():return {'id':'plan1','name':'submit_plan','args':{'summary':'Crear dos archivos de prueba.','steps':'1. Crear a.txt.\n2. Crear b.txt.\n3. Comprobar resultados.'}}

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.store=Store(self.base/'data');self.stop=threading.Event()
        self.tools=Tools(self.base/'work',self.stop,'Groq',self.store.root);self.session=self.store.new_session('Groq','test-model',self.tools.root,'Test')
        self.reviews=[]
    def tearDown(self):self.tools.close();self.temp.cleanup()
    def run_script(self,batches,approval='plan',review=None,**kwargs):
        def approved(name,details):self.reviews.append((name,details));return True
        api=SequenceAPI(batches)
        Runtime(api,self.tools,self.store,review or approved,lambda *a:None,self.stop).run('Crea archivos de prueba',self.session,'ACT',['read_file','list_files','write_file'],approval=approval,**kwargs)
        return api
    def test_one_plan_covers_separate_rounds(self):
        self.run_script([[plan_call()],[write_call('a.txt')],[write_call('b.txt')]])
        self.assertEqual([r[0] for r in self.reviews],['execution_plan']);self.assertEqual(len(self.store.checkpoints(self.tools.root)),2)
    def test_plan_does_not_grant_before_approval(self):
        self.run_script([[write_call('forbidden.txt')]])
        self.assertFalse((self.tools.root/'forbidden.txt').exists());self.assertEqual(self.reviews,[])
    def test_autonomous_no_dialog_for_files(self):
        self.run_script([[write_call('a.txt')],[write_call('b.txt')]],approval='auto')
        self.assertEqual(self.reviews,[]);self.assertTrue((self.tools.root/'b.txt').exists())
    def test_step_preserved(self):
        self.run_script([[write_call('a.txt')],[write_call('b.txt')]],approval='step');self.assertEqual(len(self.reviews),2)
    def test_rejected_plan_stops_task(self):
        api=self.run_script([[plan_call()],[write_call('a.txt')]],review=lambda *a:False)
        self.assertEqual(len(api.requests),1);self.assertEqual(self.session['status'],'denied');self.assertFalse((self.tools.root/'a.txt').exists())
    def test_truthy_plan_response_is_not_approval(self):
        self.run_script([[plan_call()],[write_call('a.txt')]],review=lambda *a:'yes');self.assertEqual(self.session['status'],'denied')
    def test_stop_during_plan_confirmation(self):
        def approve(*a):self.stop.set();return True
        self.run_script([[plan_call(),write_call('a.txt')]],review=approve)
        self.assertFalse((self.tools.root/'a.txt').exists());self.assertEqual(self.session['status'],'interrupted')
    def test_grant_not_carried_to_next_turn(self):
        self.run_script([[plan_call()],[write_call('a.txt')]])
        self.run_script([[write_call('b.txt')]])
        self.assertFalse((self.tools.root/'b.txt').exists())
    def test_autonomy_cannot_escape_workspace(self):
        self.run_script([[write_call('../outside.txt')]],approval='auto');self.assertFalse((self.base/'outside.txt').exists())
    def test_autonomy_keeps_hash_conflict_guard(self):
        calls=[write_call('a.txt','one'),write_call('a.txt','two')]
        self.run_script([calls],approval='auto');self.assertEqual((self.tools.root/'a.txt').read_text(),'one')
    def test_budget_configurable(self):
        self.run_script([[write_call('a.txt')],[write_call('b.txt')]],approval='auto',max_actions=1)
        self.assertTrue((self.tools.root/'a.txt').exists());self.assertFalse((self.tools.root/'b.txt').exists());self.assertEqual(self.session['status'],'limit')
    def test_invalid_policy_fails(self):
        with self.assertRaises(ValueError):self.run_script([],approval='invented')
    def test_invalid_limits_fail(self):
        with self.assertRaises(ValueError):self.run_script([],max_calls=100000)
    def test_secret_redacted_from_persisted_messages(self):
        self.store.secrets={'a-secret"quoted'};self.session['messages']=[{'role':'user','content':'a-secret"quoted'}];self.store.save(self.session)
        self.assertNotIn('a-secret',self.store.load(self.session['id'])['messages'][0]['content'])
    def test_plan_read_only_no_repeated_review(self):
        api=SequenceAPI([[{'id':'read','name':'list_files','args':{'path':'.'}}]])
        Runtime(api,self.tools,self.store,lambda *a:self.fail('No read dialog expected'),lambda *a:None,self.stop).run('Lista',self.session,'PLAN',['list_files'],approval='plan')
        self.assertEqual(self.session['status'],'idle')
    def test_pending_ollama_protocol(self):
        result=response_parts('Ollama',[{'id':'x','name':'list_files','result':{'ok':True}}])[0]
        self.assertEqual(result['tool_name'],'list_files');self.assertNotIn('tool_call_id',result)

class CapabilityTests(unittest.TestCase):
    def policy(self,broad=False,policy='auto',review=None):
        self.reviewed=[]
        def approve(*args):self.reviewed.append(args);return True
        return Authorization('ACT',policy,['powershell','browser','desktop','read_file'],'/work',review or approve,broad)
    def test_wide_tools_require_individual_permission_by_default(self):
        p=self.policy();self.assertTrue(p.authorize('powershell',{'arguments':{'command':'echo hi'}}));self.assertEqual(len(self.reviewed),1)
    def test_explicit_wide_scope_avoids_repeated_prompts(self):
        p=self.policy(True);self.assertTrue(p.authorize('powershell',{'arguments':{'command':'echo hi'}}));self.assertEqual(self.reviewed,[])
    def test_broad_string_not_true(self):
        p=self.policy('true');p.authorize('desktop',{'arguments':{'action':'windows'}});self.assertEqual(len(self.reviewed),1)
    def test_disabled_tool_still_denied(self):
        p=self.policy(True);self.assertFalse(p.authorize('write_file',{'arguments':{}}))
    def test_browser_click_wide_inspect_not_wide(self):
        p=self.policy();p.authorize('browser',{'arguments':{'action':'inspect'}});p.authorize('browser',{'arguments':{'action':'click'}})
        self.assertEqual(len(self.reviewed),1)
    def test_plan_scope_isolated_from_reviewer_mutation(self):
        def reviewer(name,details):details['tools'].append('write_file');return True
        p=self.policy(True,'plan',reviewer);p.authorize('submit_plan',{'arguments':plan_call()['args']})
        self.assertFalse(p.authorize('write_file',{'arguments':{}}))
    def test_plan_denial_also_denies_reads_in_same_batch(self):
        p=self.policy(False,'plan',lambda *a:False);p.authorize('submit_plan',{'arguments':plan_call()['args']})
        self.assertFalse(p.authorize('read_file',{'arguments':{'path':'x'}}))
    def test_plan_mode_blocks_power_even_autonomous(self):
        p=Authorization('PLAN','auto',['powershell'],'/work',lambda *a:True,True)
        self.assertFalse(p.authorize('powershell',{'arguments':{}}))

class ProfileTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.p=Settings(self.root,TestProtector())
    def tearDown(self):self.temp.cleanup()
    def test_profiles_survive_restart(self):
        self.p.save_profile('Groq','model-a','KEY-A');self.p.save_profile('Groq','model-b','KEY-B');other=Settings(self.root,TestProtector())
        self.assertEqual(other.key('Groq','model-a'),'KEY-A');self.assertEqual(other.key('Groq','model-b'),'KEY-B')
        self.assertNotIn('KEY-A',self.p.path.read_text())
    def test_provider_separation(self):
        self.p.save_profile('Groq','model-a','G');self.p.save_profile('Gemini','model-a','M')
        self.assertEqual(self.p.key('Groq','model-a'),'G');self.assertEqual(self.p.key('Gemini','model-a'),'M')
    def test_forget_one_does_not_erase_another(self):
        self.p.save_profile('Groq','a','A');self.p.save_profile('Groq','b','B');self.p.forget('Groq','a')
        self.assertEqual(self.p.key('Groq','a'),'');self.assertEqual(self.p.key('Groq','b'),'B')
    def test_memory_only_removes_saved_key(self):
        self.p.save_profile('Groq','a','A');self.p.save_profile('Groq','a','A',remember=False);self.assertEqual(self.p.key('Groq','a'),'')
    def test_no_plaintext_on_protector_failure(self):
        class Broken:
            def seal(self,text):raise RuntimeError('Unavailable')
        self.p.protector=Broken()
        with self.assertRaises(RuntimeError):self.p.save_profile('Groq','a','SECRET')
        self.assertFalse(self.p.path.exists())
    def test_no_ollama_key_saved(self):
        self.p.save_profile('Ollama','qwen3:8b','SECRET','http://127.0.0.1:11434');self.assertNotIn('secret_dpapi',self.p.path.read_text())
    def test_autonomous_grants_never_persisted(self):
        self.p.save_preferences({'autonomous':True,'broad':True,'consent':True,'max_calls':20})
        p=Settings(self.root,TestProtector());self.assertNotIn('autonomous',p.data['preferences']);self.assertNotIn('broad',p.data['preferences'])
    def test_corrupt_preferences_warning(self):
        self.p.path.write_text('{invalid');self.assertTrue(Settings(self.root).warning)
    @unittest.skipUnless(os.name=='nt','Windows DPAPI roundtrip requires Windows')
    def test_actual_windows_dpapi_roundtrip(self):
        protector=WindowsProtector();cipher=protector.seal('nexo-test-secret');self.assertNotIn('nexo-test-secret',cipher);self.assertEqual(protector.open(cipher),'nexo-test-secret')
    @unittest.skipIf(os.name=='nt','Non-Windows fail-closed behavior')
    def test_windows_crypto_has_no_linux_plaintext_fallback(self):
        with self.assertRaises(RuntimeError):WindowsProtector().seal('secret')

class OllamaHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,value):
                data=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
            def do_GET(self):
                if self.path=='/api/tags':self.reply({'models':[{'name':'fixture:small'}]})
                else:
                    self.send_response(302);self.send_header('Location','https://example.com/');self.end_headers()
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));cls.requests.append((self.path,body,dict(self.headers)))
                if body['messages'][-1]['role']=='tool':self.reply({'message':{'role':'assistant','content':'Verificado'}})
                else:self.reply({'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'list_files','arguments':{'path':'.'}}}]}})
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.endpoint=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
    def test_model_discovery_http(self):self.assertEqual(ollama_models(self.endpoint),['fixture:small'])
    def test_native_chat_tool_roundtrip(self):
        api=API('Ollama','','fixture:small',endpoint=self.endpoint)
        message,text,calls=api.request([{'role':'user','content':'List files'}],[])
        self.assertEqual(calls[0]['args'],{'path':'.'});self.assertTrue(calls[0]['id'])
        conversation=[{'role':'user','content':'List files'},message]+response_parts('Ollama',[{**calls[0],'result':{'entries':[]}}])
        _,text,calls=api.request(conversation,[]);self.assertEqual(text,'Verificado');self.assertEqual(calls,[])
        self.assertEqual(self.requests[-1][0],'/api/chat');self.assertFalse(self.requests[-1][1]['stream']);self.assertNotIn('Authorization',self.requests[-1][2])
    def test_remote_endpoint_rejected(self):
        for url in ['https://ollama.com','http://example.com','http://localhost@evil.com','http://127.0.0.1:11434/api','http://localhost:11434?x=1']:
            with self.subTest(url=url),self.assertRaises(ValueError):local_endpoint(url)
    def test_empty_key_allowed_only_local(self):
        API('Ollama','','fixture',endpoint=self.endpoint)
        with self.assertRaises(ValueError):API('Groq','','fixture')
    def test_cloud_label_blocked(self):
        with self.assertRaises(ValueError):API('Ollama','','gpt-oss:120b-cloud')
    def test_local_redirect_refused(self):
        from adapters import local_json
        with self.assertRaises(RuntimeError):local_json(self.endpoint,'/redirect')
    def test_timeout_validated(self):
        with self.assertRaises(ValueError):API('Ollama','','fixture',timeout=0)

if __name__=='__main__':unittest.main(verbosity=2)
