import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from adapters import API, Tools, validate_call, workspace_path
from storage import Store, disk_copy
from runtime import Runtime, recover_pending

class ScriptAPI:
    provider='Groq';model='test-model';key='TEST-SECRET-KEY'
    def __init__(self,calls=None):
        self.calls_script=calls;self.requests=[];self.schemas=[]
    def request(self,conv,schemas):
        self.requests.append(copy.deepcopy(conv));self.schemas.append(copy.deepcopy(schemas))
        if len(self.requests)==1 and self.calls_script is not None:
            calls=self.calls_script
            message={'role':'assistant','content':'Propongo acciones','tool_calls':[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':json.dumps(c['args'])}} for c in calls]}
            return message,'Propongo acciones',calls
        return {'role':'assistant','content':'Resultados revisados'},'Resultados revisados',[]

def write_call(path='hola.txt',content='Hola'):
    return {'id':'c-'+path,'name':'write_file','args':{'path':path,'content':content}}

class NexoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.store=Store(self.base/'data');self.stop=threading.Event();self.tools=Tools(self.base/'work',self.stop,'Groq',self.store.root)
        self.session=self.store.new_session('Groq','test-model',self.tools.root,'Prueba');self.events=[]
    def tearDown(self):self.tools.close();self.temp.cleanup()
    def run_agent(self,calls=None,review=lambda *a:True,mode='ACT',enabled=None,api=None):
        api=api or ScriptAPI(calls)
        Runtime(api,self.tools,self.store,review,lambda *x:self.events.append(x),self.stop).run('Haz la tarea',self.session,mode,enabled if enabled is not None else ['write_file','read_file','list_files'])
        return api
    def create(self,path='a.txt',content='uno'):
        preview=self.store.preview(self.tools.root,path,content)
        return self.store.write(self.tools.root,path,content,self.session['id'],preview['expected_hash'])
    def test_approved_write_checkpoint(self):
        self.run_agent([write_call()]);self.assertEqual((self.tools.root/'hola.txt').read_text(),'Hola');self.assertEqual(len(self.store.checkpoints(self.tools.root)),1)
    def test_rejected_never_writes(self):
        self.run_agent([write_call()],lambda *a:False);self.assertFalse((self.tools.root/'hola.txt').exists())
    def test_missing_reviewer_denies(self):
        self.run_agent([write_call()],None);self.assertFalse((self.tools.root/'hola.txt').exists())
    def test_reviewer_exception_denies(self):
        def review(*a):raise ValueError('review offline')
        self.run_agent([write_call()],review);self.assertFalse((self.tools.root/'hola.txt').exists())
    def test_truthy_not_boolean_denied(self):
        self.run_agent([write_call()],lambda *a:1);self.assertFalse((self.tools.root/'hola.txt').exists())
    def test_reviewer_cannot_rewrite_arguments(self):
        def review(name,details):details['arguments']['content']='alterado';return True
        self.run_agent([write_call()],review);self.assertEqual((self.tools.root/'hola.txt').read_text(),'Hola')
    def test_all_prepared_before_execution(self):
        observations=[]
        def review(*a):observations.append(list(self.tools.root.iterdir()));return True
        self.run_agent([write_call('a.txt'),write_call('b.txt')],review)
        self.assertEqual(observations,[[],[]]);self.assertEqual(len(list(self.tools.root.iterdir())),2)
    def test_plan_blocks_mutation_even_requested(self):
        reviews=[];self.run_agent([write_call()],lambda *a:reviews.append(a),mode='PLAN')
        self.assertEqual(reviews,[]);self.assertFalse((self.tools.root/'hola.txt').exists())
    def test_plan_schemas_are_read_only(self):
        api=self.run_agent(mode='PLAN');self.assertEqual({d['name'] for d in api.schemas[0]},{'read_file','list_files'})
    def test_disabled_tool_denied(self):
        self.run_agent([write_call()],enabled=[]);self.assertFalse((self.tools.root/'hola.txt').exists())
    def test_followup_retains_context(self):
        self.run_agent();old=len(self.session['messages']);api=self.run_agent()
        self.assertGreater(len(api.requests[0]),old)
    def test_load_session(self):
        self.run_agent();loaded=self.store.load(self.session['id']);self.assertEqual(loaded['messages'],self.session['messages'])
    def test_pending_recovered_without_replay(self):
        self.session['messages']=[{'role':'assistant','tool_calls':[{'id':'unfinished','type':'function','function':{'name':'write_file','arguments':'{}'}}]}]
        self.session['pending']=[{'id':'unfinished','name':'write_file','args':{'path':'never.txt','content':'x'},'state':'executing','result':None}]
        self.run_agent();self.assertFalse((self.tools.root/'never.txt').exists());self.assertEqual(self.session['pending'],[])
        self.assertTrue(any(m.get('role')=='tool' and 'interrumpida' in m.get('content','') for m in self.session['messages']))
    def test_cancel_approval_closes_tool_protocol(self):
        def review(*a):self.stop.set();return True
        self.run_agent([write_call()],review);self.assertEqual(self.session['status'],'interrupted');self.assertEqual(self.session['pending'],[])
        self.assertEqual(self.session['messages'][-1]['role'],'tool');self.assertFalse((self.tools.root/'hola.txt').exists())
    def test_changed_after_review_not_overwritten(self):
        def review(*a):(self.tools.root/'hola.txt').write_text('cambio manual');return True
        self.run_agent([write_call()],review);self.assertEqual((self.tools.root/'hola.txt').read_text(),'cambio manual')
    def test_new_file_restoration(self):
        c=self.create();self.store.restore(c['checkpoint'],self.tools.root);self.assertFalse((self.tools.root/'a.txt').exists())
    def test_existing_file_restoration(self):
        (self.tools.root/'a.txt').write_text('original');c=self.create();self.store.restore(c['checkpoint'],self.tools.root);self.assertEqual((self.tools.root/'a.txt').read_text(),'original')
    def test_restore_refuses_newer_manual_edit(self):
        c=self.create();(self.tools.root/'a.txt').write_text('manual')
        with self.assertRaises(RuntimeError):self.store.restore(c['checkpoint'],self.tools.root)
        self.assertEqual((self.tools.root/'a.txt').read_text(),'manual')
    def test_checkpoint_chain(self):
        one=self.create(content='1');two=self.create(content='2')
        with self.assertRaises(RuntimeError):self.store.restore(one['checkpoint'],self.tools.root)
        self.store.restore(two['checkpoint'],self.tools.root);self.assertEqual((self.tools.root/'a.txt').read_text(),'1')
        self.store.restore(one['checkpoint'],self.tools.root);self.assertFalse((self.tools.root/'a.txt').exists())
    def test_corrupt_backup_refused(self):
        (self.tools.root/'a.txt').write_text('original');c=self.create()
        (self.store.root/'checkpoints'/c['checkpoint']/'before.bin').write_text('corrupt')
        with self.assertRaises(RuntimeError):self.store.restore(c['checkpoint'],self.tools.root)
    def test_restore_wrong_workspace(self):
        c=self.create()
        with self.assertRaises(ValueError):self.store.restore(c['checkpoint'],self.base/'elsewhere')
    def test_traversal(self):
        with self.assertRaises(ValueError):workspace_path(self.tools.root,'../escape')
    def test_symlink_escape(self):
        try:(self.tools.root/'escape').symlink_to(self.base,target_is_directory=True)
        except OSError:self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError):workspace_path(self.tools.root,'escape/secret')
    def test_ntfs_ads(self):
        with self.assertRaises(ValueError):workspace_path(self.tools.root,'a.txt:secret')
    def test_invalid_args(self):
        with self.assertRaises(ValueError):validate_call('read_file',{'path':1})
    def test_unknown_tool(self):
        with self.assertRaises(ValueError):validate_call('danger',{})
    def test_model_switch_keeps_session(self):
        self.run_agent();id=self.session['id'];api=ScriptAPI();api.model='different'
        self.run_agent(api=api)
        self.assertEqual(self.session['id'],id);self.assertEqual(self.session['model'],'different')
        self.assertTrue(api.requests);self.assertTrue(self.session['history_archives'])
    def test_pictures_not_persisted(self):
        raw={'pending':[{'image':'PRIVATEPIXELS'}],'messages':[{'parts':[{'inlineData':{'data':'PRIVATEPIXELS'}},{'thoughtSignature':'signature'}]}]}
        saved=disk_copy(raw);self.assertNotIn('PRIVATEPIXELS',json.dumps(saved));self.assertIn('signature',json.dumps(saved))
    def test_api_failure_no_retry(self):
        api=ScriptAPI()
        def fail(*a):api.requests.append(1);raise RuntimeError('429 test')
        api.request=fail;self.run_agent(api=api);self.assertEqual(len(api.requests),1);self.assertEqual(self.session['status'],'error')
    def test_api_key_redacted_from_display(self):
        api=ScriptAPI()
        def fail(*a):raise RuntimeError(api.key)
        api.request=fail;self.run_agent(api=api)
        self.assertNotIn(api.key,json.dumps(self.session['display']))
    def test_no_bypass_direct_write(self):
        with self.assertRaises(RuntimeError):self.tools.execute('write_file',{'path':'x','content':'x'})
    def test_read_truncation(self):
        (self.tools.root/'a').write_text('x'*17000);self.assertTrue(self.tools.read_file('a')['truncated'])
    def test_invalid_session_id(self):
        with self.assertRaises(ValueError):self.store.load('../anything')
    def test_iteration_budget(self):
        api=ScriptAPI()
        def always(conv,schemas):
            api.requests.append(1);call={'id':str(len(api.requests)),'name':'list_files','args':{'path':'.'}}
            return {'role':'assistant','tool_calls':[{'id':call['id'],'type':'function','function':{'name':'list_files','arguments':'{"path":"."}'}}]},'', [call]
        api.request=always;self.run_agent(api=api);self.assertEqual(len(api.requests),8);self.assertEqual(self.session['status'],'limit')
    def test_action_budget(self):
        calls=[{'id':str(i),'name':'list_files','args':{'path':'.'}} for i in range(17)];reviews=[]
        def approve(*a):reviews.append(1);return True
        self.run_agent(calls,approve);self.assertEqual(len(reviews),16)
    def test_gemini_pending_recovery(self):
        self.session['provider']='Gemini';self.session['pending']=[{'id':'g1','name':'read_file','state':'executing','result':None}]
        recover_pending(self.session);part=self.session['messages'][-1]['parts'][0]['functionResponse'];self.assertEqual(part['id'],'g1');self.assertTrue(part['response']['interrupted'])
    def test_workspace_cannot_contain_store(self):
        wide=Tools(self.base,self.stop,'Groq',self.store.root);self.session['workspace']=str(self.base)
        with self.assertRaises(ValueError):Runtime(ScriptAPI(),wide,self.store,None,lambda *a:None,self.stop).run('x',self.session,'PLAN',[])
    def test_api_fixed_endpoint_and_signature(self):
        response={'candidates':[{'content':{'role':'model','parts':[{'functionCall':{'id':'native','name':'list_files','args':{'path':'.'}},'thoughtSignature':'sig'}]}}]}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return json.dumps(response).encode()
        with patch('adapters.urllib.request.urlopen',return_value=Response()) as request:
            message,text,calls=API('Gemini','TESTKEY','gemini-3.8-flash').request([],[])
        self.assertEqual(message['parts'][0]['thoughtSignature'],'sig');self.assertEqual(calls[0]['id'],'native');self.assertNotIn('TESTKEY',request.call_args.args[0].full_url)
    @unittest.skipUnless(os.name=='nt','Requires Windows')
    def test_powershell_windows(self):
        result=self.tools.powershell('Write-Output "nexo-check"');self.assertEqual(result['exit_code'],0);self.assertIn('nexo-check',result['output'])

if __name__=='__main__':unittest.main(verbosity=2)
