"""Regression for provider HTTP 400: browser(open,url) rejected by old schema."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch
from adapters import API, DECLARATIONS, Tools, browser_arguments, validate_call
from runtime import Runtime
from storage import Store

REPORTED={'action':'open','url':'https://www.google.com/search?q=agrimensura+moderna+2026'}
ERROR={'error':{'message':"Tool call validation failed: tool call validation failed: parameters for tool browser did not match schema: errors: [missing properties: 'value', 'text']",'type':'invalid_request_error','code':'tool_use_failed','failed_generation':json.dumps({'name':'browser','arguments':REPORTED})}}

def valid(args):validate_call('browser',args);return browser_arguments(args)
class Response:
    def __init__(self,body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,n):return json.dumps(self.body).encode()[:n]

def answer(name,args):
    return {'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'test-call','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}]}

def rejected():return urllib.error.HTTPError('https://api.groq.com/openai/v1/chat/completions',400,'Bad Request',{},io.BytesIO(json.dumps(ERROR).encode()))

class BrowserContractTests(unittest.TestCase):
    def test_exact_reported_arguments(self):
        self.assertEqual(valid(REPORTED),{'action':'open','value':REPORTED['url'],'text':''})
    def test_provider_schema_accepts_url_without_dummy_fields(self):
        schema=next(d for d in DECLARATIONS if d['name']=='browser')['parameters']
        self.assertEqual(schema['required'],['action']);self.assertIn('url',schema['properties']);self.assertIn('selector',schema['properties'])
    def test_inspect_and_close_action_only(self):
        for action in ('inspect','close'):self.assertEqual(valid({'action':action}),{'action':action,'value':'','text':''})
    def test_click_selector(self):self.assertEqual(valid({'action':'click','selector':'#go'})['value'],'#go')
    def test_fill_selector(self):self.assertEqual(valid({'action':'fill','selector':'#q','text':'agrimensura'})['text'],'agrimensura')
    def test_fill_empty_string_is_deliberate(self):self.assertEqual(valid({'action':'fill','selector':'#q','text':''})['text'],'')
    def test_fill_missing_text_rejected(self):
        with self.assertRaises(ValueError):valid({'action':'fill','selector':'#q'})
    def test_legacy_calls_remain_compatible(self):
        for args in [{'action':'open','value':'https://example.com','text':''},{'action':'click','value':'#go','text':''},{'action':'fill','value':'#q','text':'hello'},{'action':'inspect','value':'','text':''},{'action':'close','value':'','text':''}]:
            self.assertEqual(valid(args),args)
    def test_conflicting_url_alias_rejected(self):
        with self.assertRaises(ValueError):valid({**REPORTED,'value':'https://elsewhere.example'})
    def test_conflicting_selector_alias_rejected(self):
        with self.assertRaises(ValueError):valid({'action':'click','selector':'#buy','value':'#cancel'})
    def test_equal_aliases_are_equivalent(self):
        self.assertEqual(valid({**REPORTED,'value':REPORTED['url']}),valid(REPORTED))
    def test_bad_url_rejected(self):
        for url in ['file:///etc/passwd','javascript:alert(1)','https://user:password@example.com','https://example.com:bad','']:
            with self.subTest(url=url),self.assertRaises(ValueError):valid({'action':'open','url':url})
    def test_unknown_property_and_types_rejected(self):
        for args in [{**REPORTED,'unexpected':1},{'action':'open','url':12},{'action':'nope'},{'action':'click','selector':None}]:
            with self.subTest(args=args),self.assertRaises(ValueError):valid(args)
    def test_wrong_action_fields_rejected(self):
        for args in [{'action':'inspect','url':'https://example.com'},{'action':'open','url':'https://example.com','text':'unexpected'},{'action':'click','selector':'#x','url':'https://example.com'}]:
            with self.subTest(args=args),self.assertRaises(ValueError):valid(args)
    def test_no_implicit_url_or_selector(self):
        for action in ('open','click','fill'):
            with self.subTest(action=action),self.assertRaises(ValueError):valid({'action':action})
    def test_real_api_payload_schema_and_parse(self):
        api=API('Groq','TEST-BROWSER-KEY','test-model')
        declarations=[d for d in DECLARATIONS if d['name']=='browser']
        with patch('adapters.urllib.request.urlopen',return_value=Response(answer('browser',REPORTED))) as send:
            _,_,calls=api.request([],declarations)
        sent=json.loads(send.call_args.args[0].data);schema=sent['tools'][0]['function']['parameters']
        self.assertIn('url',schema['properties']);self.assertNotIn('value',schema['required']);self.assertNotIn('text',schema['required'])
        self.assertEqual(calls[0]['args'],REPORTED);valid(calls[0]['args'])
    def test_failed_generation_never_executed_or_retried_by_adapter(self):
        with patch('adapters.urllib.request.urlopen',side_effect=rejected()) as send:
            with self.assertRaisesRegex(RuntimeError,'No se reintentaron'):
                API('Groq','TEST-BROWSER-KEY','test-model').request([],[])
        self.assertEqual(send.call_count,1)

class RuntimeBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name);self.store=Store(base/'data');self.stop=threading.Event()
        self.tools=Tools(base/'work',self.stop,'Groq',self.store.root);self.session=self.store.new_session('Groq','test-model',self.tools.root,'Test')
    def tearDown(self):self.tools.close();self.temp.cleanup()
    def run_call(self,mode,enabled,review):
        api=API('Groq','TEST-BROWSER-KEY','test-model')
        with patch('adapters.urllib.request.urlopen',side_effect=[Response(answer('browser',REPORTED)),Response({'choices':[{'message':{'role':'assistant','content':'Test finished'}}]})]),patch.object(self.tools,'web',return_value={'url':REPORTED['url'],'text':'fixture'}) as browser:
            Runtime(api,self.tools,self.store,review,lambda *a:None,self.stop).run('Search fixture',self.session,mode,enabled)
        return browser
    def test_exact_report_dispatched_through_permissions(self):
        approvals=[]
        def review(name,details):approvals.append(details);return True
        browser=self.run_call('ACT',['browser'],review)
        browser.assert_called_once_with(action='open',value=REPORTED['url'],text='')
        self.assertEqual(approvals[0]['arguments'],REPORTED)
    def test_plan_still_blocks_browser(self):
        browser=self.run_call('PLAN',['browser'],lambda *a:True);browser.assert_not_called()
    def test_disabled_browser_still_blocked(self):
        browser=self.run_call('ACT',[],lambda *a:True);browser.assert_not_called()
    def test_denial_still_blocks_browser(self):
        browser=self.run_call('ACT',['browser'],lambda *a:False);browser.assert_not_called()
    def test_prior_shell_not_replayed_after_provider_error(self):
        api=API('Groq','TEST-BROWSER-KEY','test-model')
        with patch('adapters.urllib.request.urlopen',side_effect=[Response(answer('powershell',{'command':'Write-Output "fixture"'})),rejected()]),patch.object(self.tools,'execute',return_value={'exit_code':0,'output':'fixture'}) as execute:
            Runtime(api,self.tools,self.store,lambda *a:True,lambda *a:None,self.stop).run('Fixture task',self.session,'ACT',['powershell','browser'],approval='auto',broad=True)
            self.assertEqual(execute.call_count,1);self.assertEqual(self.session['status'],'error');self.assertFalse(self.session['pending'])
            with patch('adapters.urllib.request.urlopen',return_value=Response({'choices':[{'message':{'role':'assistant','content':'Inspect before repeating anything'}}]})):
                Runtime(api,self.tools,self.store,lambda *a:True,lambda *a:None,self.stop).run('Review state only',self.session,'PLAN',['list_files'],approval='plan')
            self.assertEqual(execute.call_count,1)

if __name__=='__main__':unittest.main(verbosity=2)
