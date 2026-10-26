"""v0.5 chat portability, bounded context, usage and automatic voice assets.
All unit fixtures are offline. Model bytes are synthetic, never used for ASR.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
from adapters import API,Tools
from conversation import build_context,switch_session,text_message,readable,size
from runtime import Runtime,recover_pending
from storage import Store
from voice_assets import find_model,ensure_model,valid_model,MODEL_NAME,REQUIRED_MODEL_FILES
from test_nexo import ScriptAPI

class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.store=Store(self.base/'data')
        self.stop=threading.Event();self.tools=Tools(self.base/'work',self.stop,'Groq',self.store.root)
        self.s=self.store.new_session('Groq','first',self.tools.root,'Conservar esta conversación')
    def tearDown(self):self.tools.close();self.temp.cleanup()
    def seed(self,n=20):
        self.s['messages']=[m for i in range(n) for m in [{'role':'user','content':f'Objetivo {i}: '+('instrucción '+str(i)+'; ')*240},{'role':'assistant','content':f'Respuesta {i}: '+('dato '+str(i)+'; ')*500}]]
        self.s['messages'].append({'role':'user','content':'Continúa con el documento, sin repetir las acciones.'})
    def test_same_model_is_noop(self):
        self.seed(1);before=copy.deepcopy(self.s);self.assertFalse(switch_session(self.s,'Groq','first'));self.assertEqual(before,self.s)
    def test_model_switch_keeps_id_and_display(self):
        self.seed(2);self.s['display']=[{'who':'Tú','text':'Mi tarea'}];old=copy.deepcopy(self.s)
        self.assertTrue(switch_session(self.s,'Groq','second'))
        self.assertEqual(self.s['id'],old['id']);self.assertEqual(self.s['display'],old['display']);self.assertEqual(self.s['history_archives'][0]['messages'],old['messages'])
    def test_groq_to_gemini_removes_foreign_protocol(self):
        self.s['messages']=[{'role':'assistant','tool_calls':[{'id':'c','function':{'name':'write_file','arguments':'{"path":"x.txt"}'}}]}, {'role':'tool','tool_call_id':'c','name':'write_file','content':'{"written":"x.txt"}'}]
        switch_session(self.s,'Gemini','g')
        for m in self.s['messages']:
            self.assertIn(m['role'],('user','model'));self.assertIn('parts',m);self.assertNotIn('tool_calls',m)
        serialized=json.dumps(self.s['messages']);self.assertIn('x.txt',serialized);self.assertNotIn('functionCall',serialized);self.assertNotIn('tool_call_id',serialized)
    def test_gemini_to_ollama_strips_signatures_and_images(self):
        self.s['provider']='Gemini';self.s['messages']=[{'role':'model','parts':[{'text':'Continuamos','thoughtSignature':'SIG'},{'functionCall':{'name':'read_file','args':{'path':'x.txt'}},'thoughtSignature':'CALLSIG'}]}, {'role':'user','parts':[{'functionResponse':{'name':'read_file','response':{'text':'Contenido'}}},{'inlineData':{'data':'PIXELS'}}]}]
        switch_session(self.s,'Ollama','q','http://127.0.0.1:11434')
        serialized=json.dumps(self.s['messages']);self.assertNotIn('SIG',serialized);self.assertNotIn('PIXELS',serialized);self.assertIn('Contenido',serialized)
        self.assertTrue(all(m['role'] in ('assistant','user') for m in self.s['messages']))
    def test_pending_blocks_transfer_until_recovered(self):
        self.s['pending']=[{'id':'x','name':'write_file','args':{'path':'x.txt','content':'no'},'state':'executing','result':None}]
        with self.assertRaises(ValueError):switch_session(self.s,'Gemini','g')
        recover_pending(self.s);switch_session(self.s,'Gemini','g')
        self.assertIn('interrumpida',json.dumps(self.s['messages'],ensure_ascii=False));self.assertFalse((self.tools.root/'x.txt').exists())
    def test_repeated_switches_archive_only_new_native_messages(self):
        self.seed(1);count=len(self.s['messages']);switch_session(self.s,'Gemini','g')
        self.s['messages'].append(text_message('Gemini','assistant','Nueva respuesta'));switch_session(self.s,'Groq','again')
        self.assertEqual(len(self.s['history_archives'][0]['messages']),count);self.assertEqual(len(self.s['history_archives'][1]['messages']),1)
    def test_transferred_archives_redact_known_keys(self):
        self.s['messages']=[{'role':'user','content':'secret-test-123'}];self.store.secrets.add('secret-test-123')
        switch_session(self.s,'Gemini','g');self.store.save(self.s)
        self.assertNotIn('secret-test-123',(self.store.root/'sessions'/(self.s['id']+'.json')).read_text())
    def test_context_compaction_never_changes_saved_transcript(self):
        self.seed();old=copy.deepcopy(self.s);sent,stats=build_context(self.s)
        self.assertEqual(self.s,old);self.assertLess(stats['sent_chars'],12000);self.assertLess(stats['sent_chars'],stats['stored_chars']//5)
        self.assertIn('Continúa',readable(sent[-1]));self.assertIn('extractos',readable(sent[0]))
    def test_current_groq_tool_batch_is_intact(self):
        self.seed();calls={'role':'assistant','content':'Acción actual','tool_calls':[{'id':'a','function':{'name':'read_file','arguments':'{}'}},{'id':'b','function':{'name':'list_files','arguments':'{}'}}]}
        results=[{'role':'tool','tool_call_id':x,'content':'ok'} for x in ('a','b')];self.s['messages'] +=[calls]+results
        sent,_=build_context(self.s);self.assertEqual(sent[-3:],[calls]+results)
        self.assertTrue(any('Continúa' in readable(m) for m in sent))
    def test_current_gemini_signatures_and_response_preserved(self):
        self.seed();switch_session(self.s,'Gemini','g');self.s['messages'].append(text_message('Gemini','user','Solicitud nueva'))
        group=[{'role':'model','parts':[{'functionCall':{'name':'read_file','args':{'path':'a'}},'thoughtSignature':'EXACT-SIGNATURE'}]}, {'role':'user','parts':[{'functionResponse':{'name':'read_file','response':{'text':'actual'}}}]}]
        self.s['messages']+=group;sent,_=build_context(self.s);self.assertEqual(sent[-2:],group)
    def test_large_latest_group_not_silently_truncated(self):
        self.seed();last={'role':'assistant','content':'x'*20000};self.s['messages'].append(last)
        sent,stats=build_context(self.s,120000);self.assertEqual(sent[-1],last);self.assertTrue(stats['above_economy_target'])
    def test_hard_limit_keeps_chat_and_does_not_require_new(self):
        self.s['messages']=[{'role':'user','content':'x'*20000}];old=copy.deepcopy(self.s)
        with self.assertRaisesRegex(RuntimeError,'no necesitas crear otro chat'):build_context(self.s,10000)
        self.assertEqual(self.s,old)
    def test_disable_economy_sends_full_within_hard_limit(self):
        self.seed(3);sent,stats=build_context(self.s,120000,False);self.assertEqual(sent,self.s['messages']);self.assertFalse(stats['compacted'])
    def test_switch_endpoint_keeps_same_id(self):
        self.s.update(provider='Ollama',endpoint='http://localhost:11434');id=self.s['id']
        self.assertTrue(switch_session(self.s,'Ollama','first','http://localhost:11435'));self.assertEqual(self.s['id'],id)
    def test_runtime_continues_after_rate_error_with_new_model(self):
        first=ScriptAPI();first.model='first'
        def fail(conv,decl):raise RuntimeError('429 cuota agotada')
        first.request=fail
        Runtime(first,self.tools,self.store,lambda *a:False,lambda *a:None,self.stop).run('Escribe el plan',self.s,'PLAN',[])
        id=self.s['id'];second=ScriptAPI();second.model='second'
        Runtime(second,self.tools,self.store,lambda *a:False,lambda *a:None,self.stop).run('Continúa',self.s,'PLAN',[])
        self.assertEqual(self.s['id'],id);self.assertEqual(self.s['status'],'idle');self.assertEqual(len(second.requests),1)
        self.assertIn('Escribe el plan',json.dumps(second.requests[0],ensure_ascii=False))
    def test_changed_workspace_remains_blocked(self):
        self.s['workspace']=str(self.base/'other')
        with self.assertRaises(ValueError):Runtime(ScriptAPI(),self.tools,self.store,None,lambda *a:None,self.stop).run('Sigue',self.s,'PLAN',[])
    def test_usage_totals_only_from_reported_values(self):
        api=ScriptAPI();api.model='first';api.last_usage={'input_tokens':100,'output_tokens':25}
        Runtime(api,self.tools,self.store,None,lambda *a:None,self.stop).run('Hola',self.s,'PLAN',[])
        self.assertEqual(self.s['usage_totals'],{'input_tokens':100,'output_tokens':25,'reported_requests':1})
    def test_usage_provider_mapping_and_missing(self):
        a=API('Groq','fake','m');a.capture_usage({'usage':{'prompt_tokens':100,'completion_tokens':20}});self.assertEqual(a.last_usage,{'input_tokens':100,'output_tokens':20})
        a.provider='Gemini';a.capture_usage({'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':20,'thoughtsTokenCount':5}});self.assertEqual(a.last_usage,{'input_tokens':10,'output_tokens':25})
        a.provider='Ollama';a.capture_usage({'prompt_eval_count':12,'eval_count':8});self.assertEqual(a.last_usage,{'input_tokens':12,'output_tokens':8})
        a.capture_usage({});self.assertEqual(a.last_usage,{})

class AutomaticVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.home=self.base/'home';self.root=self.base/'app';self.home.mkdir();self.root.mkdir()
    def tearDown(self):self.temp.cleanup()
    def model(self,path):
        for name in REQUIRED_MODEL_FILES:
            file=path/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'fixture')
        return path
    def archive(self):
        file=self.root/'models'/(MODEL_NAME+'.zip');file.parent.mkdir()
        with zipfile.ZipFile(file,'w') as z:
            for name in REQUIRED_MODEL_FILES:z.writestr(MODEL_NAME+'/'+name,b'fixture')
        return file,hashlib.sha256(file.read_bytes()).hexdigest()
    def test_stale_saved_folder_falls_back_to_installed_model(self):
        expected=self.model(self.home/'.nexo-pc/speech-models'/MODEL_NAME)
        self.assertEqual(find_model(self.base/'deleted',self.home,self.root),expected)
    def test_parent_and_double_nested_folders_recognized(self):
        expected=self.model(self.root/'models'/MODEL_NAME/MODEL_NAME)
        self.assertEqual(find_model(self.root/'models',self.home,self.root),expected)
    def test_am_subfolder_is_corrected(self):
        expected=self.model(self.base/'chosen');self.assertEqual(find_model(expected/'am',self.home,self.root),expected)
    def test_partial_model_not_mistaken_for_installation(self):
        p=self.home/'.nexo-pc/speech-models'/MODEL_NAME;(p/'am').mkdir(parents=True);(p/'am/final.mdl').write_bytes(b'partial')
        self.assertFalse(valid_model(p));self.assertIsNone(find_model('',self.home,self.root))
    def test_installed_model_no_network_or_download(self):
        expected=self.model(self.home/'.nexo-pc/speech-models'/MODEL_NAME)
        with patch('prepare_voice.urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
            self.assertEqual(ensure_model('',self.home,self.root),expected)
    def test_bundled_model_extracts_offline(self):
        file,sha=self.archive()
        with patch('prepare_voice.MODEL_SHA256',sha),patch('prepare_voice.urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
            result=ensure_model('',self.home,self.root)
        self.assertTrue(valid_model(result))
    def test_partial_model_backed_up_not_deleted(self):
        p=self.home/'.nexo-pc/speech-models'/MODEL_NAME;p.mkdir(parents=True);(p/'keep.txt').write_text('keep')
        file,sha=self.archive()
        with patch('prepare_voice.MODEL_SHA256',sha):result=ensure_model('',self.home,self.root)
        backup=list(p.parent.glob(MODEL_NAME+'-respaldo-*'));self.assertEqual(len(backup),1);self.assertEqual((backup[0]/'keep.txt').read_text(),'keep');self.assertTrue(valid_model(result))
    def test_corrupt_archive_keeps_old_model(self):
        p=self.model(self.home/'.nexo-pc/speech-models'/MODEL_NAME);file,sha=self.archive()
        with self.assertRaisesRegex(RuntimeError,'SHA-256'):ensure_model('',self.home,self.root,repair=True)
        self.assertTrue(valid_model(p));self.assertEqual(list(p.parent.glob('*respaldo*')),[])
    def test_missing_bundle_never_downloads_implicitly(self):
        with patch('prepare_voice.urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
            with self.assertRaisesRegex(RuntimeError,'TODO el paquete'):ensure_model('',self.home,self.root)
    def test_force_repair_preserves_previous_complete_model(self):
        p=self.model(self.home/'.nexo-pc/speech-models'/MODEL_NAME);file,sha=self.archive()
        with patch('prepare_voice.MODEL_SHA256',sha):ensure_model('',self.home,self.root,repair=True)
        self.assertTrue(valid_model(p));self.assertEqual(len(list(p.parent.glob('*respaldo*'))),1)

if __name__=='__main__':unittest.main(verbosity=2)
