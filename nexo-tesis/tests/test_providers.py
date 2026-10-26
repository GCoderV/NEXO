import copy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from providers import API,local_endpoint,local_json,ollama_models
class Response:
    def __init__(self,data):self.raw=json.dumps(data).encode()
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,n):return self.raw[:n]
class ProviderTests(unittest.TestCase):
    def test_groq_json_mode_no_tools(self):
        captured=[]
        def fetch(req,timeout):captured.append(json.loads(req.data));return Response({'choices':[{'message':{'role':'assistant','content':'{"reply":"hi"}'}}],'usage':{'prompt_tokens':20,'completion_tokens':5}})
        api=API('Groq','fake','test');api.instructions='Academic rules'
        with patch('providers.open_remote',fetch):_,text,calls=api.request([{'role':'user','content':'context'}],[])
        self.assertEqual(captured[0]['response_format'],{'type':'json_object'});self.assertNotIn('tools',captured[0]);self.assertEqual(captured[0]['messages'][0]['content'],'Academic rules');self.assertEqual(api.last_usage['input_tokens'],20)
    def test_gemini_json_mode(self):
        captured=[]
        def fetch(req,timeout):captured.append(json.loads(req.data));return Response({'candidates':[{'content':{'role':'model','parts':[{'text':'{"reply":"hola"}'}]}}]})
        with patch('providers.open_remote',fetch):_,text,calls=API('Gemini','fake','test').request([{'role':'user','parts':[{'text':'context'}]}],[])
        self.assertEqual(captured[0]['generationConfig']['responseMimeType'],'application/json');self.assertNotIn('tools',captured[0])
    def test_real_loopback_ollama_protocol_not_inference(self):
        captured=[]
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));captured.append(payload)
                body=json.dumps({'message':{'role':'assistant','content':'{"reply":"fixture"}'},'prompt_eval_count':12,'eval_count':4}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'{"models":[{"name":"fixture:1b"}]}')
            def log_message(self,*a):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            endpoint=f'http://127.0.0.1:{server.server_port}';api=API('Ollama','','fixture:1b',endpoint)
            _,text,_=api.request([{'role':'user','content':'ctx'}],[])
            self.assertEqual(captured[0]['format'],'json');self.assertFalse(captured[0]['stream']);self.assertEqual(api.last_usage,{'input_tokens':12,'output_tokens':4});self.assertEqual(ollama_models(endpoint),['fixture:1b'])
        finally:server.shutdown();server.server_close();thread.join()
    def test_invalid_endpoint_no_request(self):
        with self.assertRaises(ValueError):API('Ollama','','test','http://external.example:11434')
    def test_invalid_provider(self):
        with self.assertRaises(ValueError):API('Unknown','fake','model')
if __name__=='__main__':unittest.main()
