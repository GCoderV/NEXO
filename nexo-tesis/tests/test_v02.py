import base64,copy,io,json,tempfile,threading,time,unittest,urllib.error,uuid
from pathlib import Path
from unittest.mock import patch
from config import Config,atomic
from providers import API,ProviderError,list_models,NoRemoteRedirect,http_error
from routing import RoutedAPI
from project_store import ProjectStore,set_fact
from agent import Agent
from test_core import FakeProtector,FakeAPI,reply
from test_providers import Response
from copilot_socket import SignalDecoder,RS,complete,sanitize_frame,parse_url,capture_info,cdp_socket

def session(exp=None):
    # Synthetic fixture, not an authentication token.
    body={'oid':'fixture-user','tid':'fixture-tenant','exp':exp or time.time()+3600}
    token='fixture.'+base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip('=')+'.not-a-signature'
    frame={'type':4,'target':'chat','arguments':[{'source':'officedesktop','tone':'observed-fixture','optionsSets':['test'], 'message':{'text':'test','author':'user'}}]}
    return json.dumps({'url':'wss://substrate.office.com/m365Copilot/Chathub/?licenseType=Starter&isEdu=true&source=officedesktop&access_token='+token,'frame':sanitize_frame(frame)})
class AccountTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.c=Config(self.temp.name,FakeProtector())
    def tearDown(self):self.temp.cleanup()
    def add(self,p='Groq',model='a',key='KEY',auto=True,remember=False):
        aid=self.c.account(p,key,key,remember);rid=self.c.route(p,model,aid,auto=auto);return aid,rid
    def test_key_reused_across_models(self):
        aid,r=self.add();r2=self.c.route('Groq','b',aid,auto=True);self.c.select(r)
        self.assertEqual(len(self.c.data['accounts']),1);self.assertEqual([self.c.route_key(r) for r in self.c.candidates()],['KEY','KEY'])
    def test_session_only_expires_on_restart(self):
        aid,r=self.add();self.c.select(r);loaded=Config(self.temp.name,FakeProtector())
        self.assertEqual(loaded.secret(aid),'');self.assertNotIn('KEY',Path(self.c.path).read_text().replace('"alias": "KEY"',''))
        with self.assertRaises(ValueError):loaded.api()
    def test_encrypted_account_survives_restart(self):
        aid,r=self.add(key='FAKE-UNIQUE-SECRET',remember=True);self.c.select(r)
        self.assertEqual(Config(self.temp.name,FakeProtector()).secret(aid),'FAKE-UNIQUE-SECRET')
    def test_blank_key_not_saved(self):
        with self.assertRaises(ValueError):self.c.account('Groq','none','  ')
        self.assertEqual(self.c.data['accounts'],{})
    def test_cross_provider_account_rejected(self):
        aid,r=self.add()
        with self.assertRaises(ValueError):self.c.route('Gemini','b',aid)
    def test_disabled_blank_deleted_wrong_accounts_zero_candidates(self):
        aid,r=self.add(key='GOOD');self.c.select(r)
        for kind in ('disabled','blank','deleted','wrong','unreadable'):
            a,rr=self.add(model=kind,key=kind,remember=True)
            if kind=='disabled':self.c.data['accounts'][a]['enabled']=False
            if kind=='blank':self.c.memory.pop(a);self.c.data['accounts'][a].pop('secret')
            if kind=='deleted':self.c.remove_account(a)
            if kind=='wrong':self.c.data['accounts'][a]['provider']='Gemini'
            if kind=='unreadable':self.c.memory.pop(a);self.c.data['accounts'][a]['secret']={'unreadable':True}
        self.assertEqual([x['id'] for x in self.c.candidates()],[r])
    def test_current_missing_is_skipped_without_call(self):
        a,r=self.add();a2,r2=self.add(key='SECOND');self.c.select(r);self.c.remove_account(a)
        self.assertEqual([x['id'] for x in self.c.candidates()],[r2])
    def test_catalog_never_becomes_route(self):
        a,r=self.add();self.c.select(r);self.c.data['catalog']={'NVIDIA':[{'id':'listed'}]}
        self.assertEqual(len(self.c.candidates()),1)
    def test_order_same_model_accounts_provider_then_other_provider(self):
        a,r=self.add(key='one');self.c.select(r)
        _,external=self.add('Gemini','g','external');_,other=self.add(model='b',key='other');_,same=self.add(key='two')
        self.assertEqual([x['id'] for x in self.c.candidates()],[r,same,other,external])
    def test_unmarked_route_excluded(self):
        a,r=self.add();self.c.select(r);self.add(key='TWO',auto=False);self.assertEqual(len(self.c.candidates()),1)
    def test_duplicate_account_model_collapsed(self):
        a,r=self.add();self.c.select(r);self.c.route('Groq','a',a,auto=True);self.assertEqual(len(self.c.candidates()),1)
    def test_ollama_no_remote_fallback(self):
        self.add();r=self.c.route('Ollama','local',endpoint='http://127.0.0.1:11434',auto=True);self.c.select(r)
        self.assertEqual([x['provider'] for x in self.c.candidates()],['Ollama']);self.assertFalse(self.c.data['routes'][-1]['auto'])
    def test_ollama_never_auto_from_remote(self):
        _,r=self.add();self.c.select(r);self.c.route('Ollama','local',auto=True);self.assertEqual([x['provider'] for x in self.c.candidates()],['Groq'])
    def test_corrupt_config_quarantined_and_recoverable(self):
        # The damaged bytes are preserved once, but the app must NOT be locked out
        # of every future save: the user can reconfigure from the UI and continue.
        bad='{"schema":2,"current":{},"profiles":{},"accounts":[],"routes":[]}'
        self.c.path.write_text(bad)
        loaded=Config(self.temp.name,FakeProtector())
        self.assertTrue(loaded.warning);self.assertEqual(loaded.data['accounts'],{})
        backups=list(Path(self.temp.name).glob('config-invalido-*.json'))
        self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text('utf-8'),bad)
        loaded.account('Groq','Nueva','CLAVE-SINTETICA');loaded.flush()
        self.assertEqual(backups[0].read_text('utf-8'),bad)
        self.assertEqual(len(Config(self.temp.name,FakeProtector()).data['accounts']),1)
    def test_legacy_migration_merges_provider_secrets_and_preserves_backup(self):
        profiles={}
        for m in ('a','b'):
            profiles[Config.key_id('Groq',m,'')]={'provider':'Groq','model':m,'endpoint':'','secret':'TERCES'}
        old={'current':{'provider':'Groq','model':'b','endpoint':'','timeout':90},'profiles':profiles};atomic(self.c.path,old)
        loaded=Config(self.temp.name,FakeProtector());self.assertEqual(len(loaded.data['accounts']),1);self.assertEqual(loaded.data['current']['model'],'b');self.assertFalse(any(r['auto'] for r in loaded.data['routes']))
        loaded.flush();self.assertEqual(json.loads(self.c.path.with_name('config-v01-respaldo.json').read_text()),old);self.assertNotIn('SECRET',self.c.path.read_text())
    def test_copilot_rejects_plain_key_and_model_alias(self):
        with self.assertRaises(ValueError):self.c.account('Copilot365','institution','ordinary-api-key')
        aid=self.c.account('Copilot365','institution',session())
        with self.assertRaises(ValueError):self.c.route('Copilot365','guessed-premium-model',aid)
    def test_all_saved_keys_redacted(self):
        a,_=self.add(key='UNIQUE_KEY_ONE',remember=True);b,_=self.add(key='UNIQUE_KEY_TWO',remember=True);self.c.memory.clear()
        self.assertEqual(self.c.redact('UNIQUE_KEY_ONE UNIQUE_KEY_TWO'),'[CLAVE OMITIDA] [CLAVE OMITIDA]')

class RoutingTests(unittest.TestCase):
    setUp=AccountTests.setUp
    tearDown=AccountTests.tearDown
    add=AccountTests.add
    def factory(self,results,seen):
        def make(p,k,m,e,t):
            api=FakeAPI([results.pop(0)]);api.provider=p;api.model=m;api.endpoint=e;api.key=k;api.timeout=t
            original=api.request
            def request(conv,dec):seen.append((p,k,m,copy.deepcopy(conv)));return original(conv,dec)
            api.request=request;return api
        return make
    def ready(self):
        a,r=self.add(key='ONE');self.c.select(r);b,r2=self.add(key='TWO');return a,r,b,r2
    def test_quota_rotates_next_selected_account(self):
        a,r,b,r2=self.ready();seen=[];api=RoutedAPI(self.c,self.c.candidates(),self.factory([ProviderError('limit','quota',True,100),reply()],seen))
        api.request([{'role':'user','content':'ctx'}],[]);self.assertEqual([v[1] for v in seen],['ONE','TWO']);self.assertGreater(self.c.data['cooldowns'][r],time.time());self.assertEqual(api.attempts,2)
    def test_auth_failure_skips_every_model_of_bad_account(self):
        a,r,b,r2=self.ready();self.c.route('Groq','other',a,auto=True);seen=[]
        api=RoutedAPI(self.c,self.c.candidates(),self.factory([ProviderError('bad','auth',True),ProviderError('limit','quota',True)],seen))
        with self.assertRaises(ProviderError):api.request([],[])
        self.assertEqual(len(seen),2);self.assertEqual(self.c.data['health'][a],'auth')
    def test_ambiguous_timeout_no_automatic_retry(self):
        self.ready();seen=[];api=RoutedAPI(self.c,self.c.candidates(),self.factory([ProviderError('timeout','uncertain'),reply()],seen))
        with self.assertRaises(ProviderError):api.request([],[])
        self.assertEqual(len(seen),1)
    def test_attempt_budget_across_two_phases(self):
        self.ready();self.c.data['attempt_limit']=1;seen=[];api=RoutedAPI(self.c,self.c.candidates(),self.factory([reply(),reply()],seen));api.request([],[])
        with self.assertRaises(ProviderError):api.request([],[])
        self.assertEqual(len(seen),1)
    def test_cancelled_before_first_request(self):
        self.ready();seen=[];api=RoutedAPI(self.c,self.c.candidates(),self.factory([reply()],seen));api.stop.set()
        with self.assertRaises(RuntimeError):api.request([],[])
        self.assertEqual(seen,[])
    def test_cooldowns_survive_restart(self):
        a,r=self.add(key='ONE',remember=True);self.c.select(r);self.c.data['cooldowns'][r]=time.time()+100;self.c.flush();loaded=Config(self.temp.name,FakeProtector());seen=[]
        api=RoutedAPI(loaded,loaded.candidates(),self.factory([reply()],seen))
        with self.assertRaises(ProviderError):api.request([],[])
        self.assertEqual(seen,[])
    def test_same_neutral_context_adapted_to_gemini(self):
        a,r=self.add();self.c.select(r);self.add('Gemini','gemma-4-31b-it','TWO');seen=[];api=RoutedAPI(self.c,self.c.candidates(),self.factory([ProviderError('limit','quota',True),reply()],seen))
        api.request([{'role':'user','content':'identical academic context'}],[])
        self.assertEqual(seen[0][3][0]['content'],seen[1][3][0]['parts'][0]['text'])
    def test_next_phase_prioritizes_current_successful_provider(self):
        a,r=self.add();self.c.select(r)
        self.add('Gemini','g','GOOGLE1');self.add('OpenRouter','o','ROUTER');self.add('Gemini','g','GOOGLE2');seen=[]
        api=RoutedAPI(self.c,self.c.candidates(),self.factory([ProviderError('quota','quota',True),reply(),ProviderError('quota','quota',True),reply()],seen))
        api.request([{'role':'user','content':'ctx'}],[]);api.request([{'role':'user','content':'ctx2'}],[])
        self.assertEqual([x[1] for x in seen],['KEY','GOOGLE1','GOOGLE1','GOOGLE2'])
    def test_bad_format_is_not_repaired_by_rotation(self):
        self.ready();seen=[];api=RoutedAPI(self.c,self.c.candidates(),self.factory(['plain non JSON',reply()],seen));store=ProjectStore(self.temp.name);p=store.create('topic');p=Agent(store,api).turn(p['id'],'continue')
        self.assertEqual(p['run']['status'],'error_formato');self.assertEqual(len(seen),1);self.assertIn('pending',p)

class ResumeTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.store=ProjectStore(self.temp.name);self.p=self.store.create('topic')
    def tearDown(self):self.temp.cleanup()
    def test_restart_resume_no_duplicate_user_message(self):
        p=Agent(self.store,FakeAPI([ProviderError('quota','quota')])).turn(self.p['id'],'original instruction');op=p['pending']['id']
        api=FakeAPI([reply()]);p=Agent(ProjectStore(self.temp.name),api).turn(p['id'],resume=True)
        self.assertNotIn('pending',p);self.assertEqual([m['text'] for m in p['messages'] if m['role']=='user'],['original instruction']);self.assertEqual(p['messages'][-1]['producer']['operation_id'],op)
    def test_completed_search_not_repeated_after_second_phase_failure(self):
        searches=[]
        def search(q):searches.append(q);return []
        r=reply(search={'query':'education methods','reason':'metadata'})
        p=Agent(self.store,FakeAPI([r,ProviderError('quota','quota')]),lambda *a:True,search).turn(self.p['id'],'Find sources',True)
        self.assertTrue(p['pending']['searched']);self.assertEqual(p['pending']['iteration'],1)
        p=Agent(self.store,FakeAPI([reply()]),lambda *a:(_ for _ in ()).throw(AssertionError('approval repeated')),lambda q:(_ for _ in ()).throw(AssertionError('search repeated'))).turn(p['id'],resume=True)
        self.assertEqual(len(searches),1);self.assertEqual(len([m for m in p['messages'] if m['role']=='user']),1)
    def test_committed_proposal_not_repeated_while_search_pending(self):
        stop=threading.Event()
        class StopAPI(FakeAPI):
            pass
        # Stop upon search approval: first model proposal has already committed.
        def approve(*args):stop.set();return True
        r=reply(drafts=[{'section':'objetivos','text':'Saved draft','sources':[]}],search={'query':'source','reason':'context'})
        p=Agent(self.store,FakeAPI([r]),approve,lambda q:[],stop).turn(self.p['id'],'Find source',True)
        self.assertEqual(p['pending']['stage'],'search');self.assertIn('objetivos',p['drafts'])
        api=FakeAPI([reply()]);p=Agent(self.store,api,lambda *a:True,lambda q:[]).turn(p['id'],resume=True)
        self.assertEqual(len(api.requests),1);self.assertEqual(p['drafts']['objetivos']['versions'],[])
    def test_context_changes_require_explicit_refresh(self):
        p=Agent(self.store,FakeAPI([ProviderError('quota','quota')])).turn(self.p['id'],'continue');set_fact(p,'nivel','grado');self.store.save(p)
        with self.assertRaises(ValueError):Agent(self.store,FakeAPI([reply()])).turn(p['id'],resume=True)
        p=Agent(self.store,FakeAPI([reply()])).turn(p['id'],resume=True,refresh_context=True)
        self.assertEqual(len([m for m in p['messages'] if m['role']=='user']),1)
    def test_crash_inflight_recovery_marks_ambiguity(self):
        p=Agent(self.store,FakeAPI([ProviderError('quota','quota')])).turn(self.p['id'],'continue');p['run']['status']='modelo';p['pending']['inflight']=True;self.store.save(p)
        p=self.store.recover(self.store.load(p['id']));self.assertTrue(p['pending']['uncertain']);self.assertEqual(p['pending']['revision'],p['revision'])
    def test_word_origin_survives_resume(self):
        p=Agent(self.store,FakeAPI([ProviderError('quota','quota')])).turn(self.p['id'],'200 participants',origin='seleccion_word')
        p=Agent(self.store,FakeAPI([reply(facts=[{'key':'poblacion','value':'200 participants','evidence':'200 participants'}])])).turn(p['id'],resume=True)
        self.assertNotIn('poblacion',p['facts']);self.assertEqual([m['origin'] for m in p['messages'] if m['role']=='user'],['seleccion_word'])
    def test_project_isolation_resume(self):
        p=Agent(self.store,FakeAPI([ProviderError('quota','quota')])).turn(self.p['id'],'secret project A');b=self.store.create('other project')
        with self.assertRaises(ValueError):Agent(self.store,FakeAPI([reply()])).turn(b['id'],resume=True)
        self.assertNotIn('secret project A',json.dumps(self.store.load(b['id'])))
    def test_rejected_draft_keeps_previous_producer(self):
        p=Agent(self.store,FakeAPI([reply(drafts=[{'section':'objetivos','text':'old','sources':[]}])])).turn(self.p['id'],'first')
        old=copy.deepcopy(p['drafts']['objetivos']['producer'])
        p=Agent(self.store,FakeAPI([reply(drafts=[{'section':'objetivos','text':'bad [F99]','sources':['F99']}])])).turn(p['id'],'second')
        self.assertEqual(p['drafts']['objetivos']['producer'],old)
    def test_context_change_does_not_reuse_old_search_approval(self):
        p=Agent(self.store,FakeAPI([ProviderError('quota','quota')])).turn(self.p['id'],'sources',True)
        p['pending'].update(stage='search',search_approved=True,query={'query':'OLD QUERY','reason':'old'})
        set_fact(p,'nivel','grado');self.store.save(p);asked=[]
        def approve(q,why):asked.append(q);return True
        p=Agent(self.store,FakeAPI([reply(search={'query':'NEW QUERY','reason':'new'}),reply()]),approve,lambda q:[]).turn(p['id'],resume=True,refresh_context=True)
        self.assertEqual(asked,['NEW QUERY'])
    def test_no_resume_after_completed_turn(self):
        p=Agent(self.store,FakeAPI([reply()])).turn(self.p['id'],'continue')
        with self.assertRaises(ValueError):Agent(self.store,FakeAPI([reply()])).turn(p['id'],resume=True)

class TransportTests(unittest.TestCase):
    def test_rest_provider_endpoints(self):
        for p,host in [('OpenRouter','openrouter.ai'),('Requesty','router.requesty.ai'),('NVIDIA','integrate.api.nvidia.com')]:
            seen=[]
            with patch('providers.open_remote',side_effect=lambda req,timeout:(seen.append(req) or Response({'choices':[{'message':{'content':'{}'}}]}))):API(p,'FAKE','model').request([],[])
            self.assertIn(host,seen[0].full_url);self.assertEqual(seen[0].get_header('Authorization'),'Bearer FAKE');self.assertNotIn('max_completion_tokens',json.loads(seen[0].data))
    def test_gemma_google_does_not_send_unsupported_system_role(self):
        seen=[];api=API('Gemini','FAKE','gemma-4-31b-it');api.instructions='Return valid academic JSON'
        with patch('providers.open_remote',side_effect=lambda req,timeout:(seen.append(json.loads(req.data)) or Response({'candidates':[{'content':{'parts':[{'text':'{}'}]}}]}))):api.request([{'role':'user','parts':[{'text':'context'}]}],[])
        self.assertNotIn('systemInstruction',seen[0]);self.assertIn('Return valid academic JSON',seen[0]['contents'][0]['parts'][0]['text'])
    def test_catalog_does_not_infer_or_require_default_model(self):
        with patch('providers.open_remote',return_value=Response({'data':[{'id':'alternative','pricing':{'prompt':'0','completion':'0'}}]})) as request:
            models=list_models('OpenRouter','FAKE')
        self.assertEqual(models[0]['id'],'alternative');self.assertTrue(request.call_args.args[0].full_url.endswith('/models'));self.assertIsNone(request.call_args.args[0].data)
    def test_ollama_list_local_only(self):
        with patch('providers.local_json',return_value={'models':[{'name':'installed:8b'},None,{'name':None}]}):self.assertEqual(list_models('Ollama'),[{'id':'installed:8b','cost':'local'}])
    def test_redirect_does_not_forward_secret(self):
        with self.assertRaises(ProviderError):NoRemoteRedirect().redirect_request(None,None,None,None,None,'https://foreign.invalid')
    def test_retry_after_and_http_classification(self):
        e=http_error(urllib.error.HTTPError('u',429,'limited',{'Retry-After':'120'},None),'FAKE');self.assertEqual(e.retry_after,120);self.assertTrue(e.retryable)
        e=http_error(urllib.error.HTTPError('u',403,'forbidden',{},None),'FAKE');self.assertEqual(e.kind,'access')
    def test_copilot_limits_destination(self):
        for url in ('wss://evil.invalid/m365Copilot/Chathub/?access_token=x','http://substrate.office.com/m365Copilot/Chathub/?access_token=x','wss://substrate.office.com.evil.invalid/m365Copilot/Chathub/?access_token=x'):
            with self.assertRaises(ValueError):parse_url(url)
    def test_cdp_refuses_nonlocal_or_wrong_port(self):
        for url in ('ws://external.invalid:7777/devtools/page/x','ws://localhost:8888/devtools/page/x'):
            with self.assertRaises(ValueError):cdp_socket(url,7777)
    def test_frame_sanitizer_drops_old_text_files_identities(self):
        f=json.loads(session())['frame'];a=f['arguments'][0];a['message'].update(text='DO NOT RETAIN',entityAnnotationTypes=[{'file':'PRIVATE'}]);a['clientInfo']={'userId':'PRIVATE','clientPlatform':'observed'};a['plugins']=[{'Id':'FileSearch'}]
        clean=sanitize_frame(f);text=json.dumps(clean);self.assertNotIn('DO NOT RETAIN',text);self.assertNotIn('PRIVATE',text);self.assertNotIn('FileSearch',text);self.assertIn('officedesktop',text)
    def test_signal_fragmented_and_combined_records(self):
        d=SignalDecoder();self.assertEqual(d.feed('{"ty'),[]);frames=d.feed('pe":1,"arguments":[{"writeAtCursor":"hello"}]}'+RS+'{"type":3}'+RS)
        for f in frames:d.consume(f)
        self.assertEqual(d.text(),'hello');self.assertTrue(d.done)
    def test_signal_final_snapshot_not_duplicated(self):
        d=SignalDecoder();d.consume({'type':1,'arguments':[{'writeAtCursor':'abc'}]});d.consume({'type':2,'item':{'result':{'value':'Success'},'messages':[{'author':'bot','text':'abcdef'}]}});self.assertEqual(d.text(),'abcdef')
    def test_signal_error_not_treated_as_answer(self):
        d=SignalDecoder()
        with self.assertRaises(ProviderError):d.consume({'type':2,'item':{'result':{'value':'ContentFiltered'}}})
    def test_signal_throttle_classification(self):
        with self.assertRaises(ProviderError) as caught:SignalDecoder().consume({'type':2,'item':{'result':{'value':'Throttled'}}})
        self.assertEqual(caught.exception.kind,'quota')
    def test_complete_handshake_metrics_and_remote_continuity(self):
        class Socket:
            def __init__(self):self.frames=iter(['{}'+RS,json.dumps({'type':1,'arguments':[{'writeAtCursor':'{"reply":"fixture"}'}]})+RS+'{"type":3}'+RS]);self.sent=[];self.closed=False
            def settimeout(self,t):pass
            def send(self,x):self.sent.append(x)
            def recv(self):return next(self.frames)
            def close(self):self.closed=True
        sockets=[];urls=[];remote={}
        def connect(url):urls.append(url);s=Socket();sockets.append(s);return s
        for _ in range(2):self.assertEqual(complete(session(),'academic context','auto',10,remote=remote,connector=connect),' {"reply":"fixture"}'.strip())
        self.assertTrue(all(s.closed for s in sockets));self.assertEqual(remote['turns'],2);self.assertNotIn('Premium',urls[0]);self.assertIn('Starter',urls[0]);self.assertNotIn('access_token',json.dumps(remote))
        f=[json.loads(x) for x in sockets[0].sent[1].split(RS) if x];self.assertEqual([x['target'] for x in f],['chat','Metrics']);self.assertTrue(f[0]['arguments'][0]['isStartOfSession']);self.assertEqual(f[0]['arguments'][0]['message']['text'],'academic context')
        second=json.loads(sockets[1].sent[1].split(RS)[0]);self.assertFalse(second['arguments'][0]['isStartOfSession'])
    def test_token_removed_from_copilot_failure(self):
        secret=session();token=parse_url(json.loads(secret)['url'])[2]
        def broken(url):raise RuntimeError(url)
        with self.assertRaises(ProviderError) as caught:complete(secret,'context','auto',10,connector=broken)
        self.assertNotIn(token,str(caught.exception));self.assertNotIn('access_token',str(caught.exception))
    def test_expired_session_requires_reconnect(self):
        with self.assertRaises(ProviderError) as caught:complete(session(time.time()-1),'context','auto',10)
        self.assertEqual(caught.exception.kind,'auth')
    def test_cancelled_copilot_does_not_send_chat(self):
        class Socket:
            sent=[]
            def settimeout(self,t):pass
            def send(self,x):self.sent.append(x)
            def close(self):pass
        stop=threading.Event();stop.set();s=Socket()
        with self.assertRaises(ProviderError):complete(session(),'context','auto',10,stop=stop,connector=lambda u:s)
        self.assertFalse(any('"target": "chat"' in x for x in s.sent))

if __name__=='__main__':unittest.main()

class ObservationTests(unittest.TestCase):
    def test_capture_only_the_explicit_probe_not_other_messages(self):
        from copilot_socket import capture_connection
        source=json.loads(session());probe='NEXO FIXTURE';frame=source['frame'];frame['arguments'][0]['message']['text']=probe
        events=[{'method':'Network.webSocketCreated','params':{'requestId':'s1','url':source['url']}},
                {'method':'Network.webSocketFrameSent','params':{'requestId':'other','response':{'payloadData':json.dumps(frame)+RS}}},
                {'method':'Network.webSocketFrameSent','params':{'requestId':'s1','response':{'payloadData':json.dumps(frame)+RS}}}]
        class FakeSocket:
            def send(self,x):pass
            def recv(self):return json.dumps(events.pop(0))
            def close(self):pass
        class Opener:
            def open(self,*a,**kw):return Response([{'type':'page','url':'https://m365.cloud.microsoft/chat','webSocketDebuggerUrl':'ws://127.0.0.1:7777/devtools/page/test'}])
        with patch('copilot_socket.urllib.request.build_opener',return_value=Opener()),patch('copilot_socket.cdp_socket',return_value=FakeSocket()):captured=capture_connection(7777,probe,timeout=2)
        data=json.loads(captured);self.assertEqual(data['frame']['arguments'][0]['message']['text'],'');self.assertNotIn(probe,captured);self.assertEqual(data['cdp_port'],7777)
    def test_renewal_refuses_account_identity_change(self):
        from copilot_socket import capture_connection
        old=json.loads(session());new=copy.deepcopy(old);token=parse_url(new['url'])[2];payload={'oid':'DIFFERENT','tid':'fixture-tenant','exp':time.time()+3600};replacement='fixture.'+base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')+'.not-a-signature';new['url']=new['url'].replace(token,replacement)
        class FakeSocket:
            def send(self,x):pass
            def recv(self):return json.dumps({'method':'Network.webSocketCreated','params':{'requestId':'s1','url':new['url']}})
            def close(self):pass
        class Opener:
            def open(self,*a,**kw):return Response([{'type':'page','url':'https://m365.cloud.microsoft/chat','webSocketDebuggerUrl':'ws://127.0.0.1:7777/devtools/page/test'}])
        with patch('copilot_socket.urllib.request.build_opener',return_value=Opener()),patch('copilot_socket.cdp_socket',return_value=FakeSocket()):
            with self.assertRaisesRegex(ProviderError,'cuenta'):capture_connection(7777,previous=old,timeout=2)
    def test_local_websocket_emulator_only(self):
        import hashlib,socketserver,struct,websocket
        observations=[]
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(3);headers={};self.rfile.readline()
                while True:
                    line=self.rfile.readline().decode().strip()
                    if not line:break
                    k,v=line.split(':',1);headers[k.lower()]=v.strip()
                accept=base64.b64encode(hashlib.sha1((headers['sec-websocket-key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                self.wfile.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n').encode());self.wfile.flush()
                def readframe():
                    a,b=self.rfile.read(2);size=b&127
                    if size==126:size=struct.unpack('!H',self.rfile.read(2))[0]
                    elif size==127:size=struct.unpack('!Q',self.rfile.read(8))[0]
                    mask=self.rfile.read(4) if b&128 else None;data=self.rfile.read(size)
                    if mask:data=bytes(c^mask[i%4] for i,c in enumerate(data))
                    return a&15,data
                def sendframe(text,op=1):
                    data=text.encode();n=len(data);head=bytes([128|op,n]) if n<126 else bytes([128|op,126])+struct.pack('!H',n)
                    self.wfile.write(head+data);self.wfile.flush()
                _,data=readframe();observations.append(json.loads(data.decode().strip(RS)));sendframe('{}'+RS)
                _,data=readframe();observations.extend(json.loads(x) for x in data.decode().split(RS) if x)
                result=json.dumps({'type':1,'arguments':[{'writeAtCursor':'{"reply":"emulator"}'}]})+RS+'{"type":3}'+RS
                sendframe(result[:17]);sendframe(result[17:])
                try:
                    op,data=readframe()
                    if op==8:sendframe('',8)
                except Exception:pass
        server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Handler);server.daemon_threads=True;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            def connect(_):
                ws=websocket.WebSocket();ws.connect(f'ws://127.0.0.1:{server.server_address[1]}/fixture',timeout=2,http_no_proxy=['127.0.0.1']);return ws
            text=complete(session(),'fixture context','auto',5,connector=connect)
            self.assertEqual(text,'{"reply":"emulator"}');self.assertEqual(observations[0],{'protocol':'json','version':1});self.assertEqual([o.get('target') for o in observations[1:]],['chat','Metrics'])
        finally:server.shutdown();server.server_close();thread.join()
