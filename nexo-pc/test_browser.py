"""Optional real-browser smoke test against a temporary loopback-only fixture.
No model/API call. Requires the optional Playwright package and Chromium.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
from adapters import Tools

PAGE=b'''<!doctype html><title>Nexo fixture</title><h1>Browser test</h1>
<label>Name<input id="name"></label><button id="hello" onclick="document.querySelector('#result').textContent='Hola '+document.querySelector('#name').value">Saludar</button><p id="result"></p>'''
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(PAGE)
    def log_message(self,*args):pass

def main():
    checks=[];server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with tempfile.TemporaryDirectory() as temp:
            tools=Tools(Path(temp)/'work',threading.Event(),'Groq',Path(temp)/'data')
            try:
                result=tools.execute('browser',{'action':'open','url':f'http://127.0.0.1:{server.server_port}'})
                assert result['title']=='Nexo fixture';checks.append('Launch Chromium and open local page')
                assert any(x['id']=='name' for x in result['controls']);checks.append('Inspect structured controls')
                tools.execute('browser',{'action':'fill','selector':'#name','text':'Nexo'})
                result=tools.execute('browser',{'action':'click','selector':'#hello'})
                assert 'Hola Nexo' in result['text'];checks.append('Fill field and click produces expected DOM result')
                result=tools.execute('browser',{'action':'inspect'})
                assert 'Hola Nexo' in result['text'];checks.append('Inspect with action only')
                tools.execute('browser',{'action':'fill','value':'#name','text':'compatibilidad'})
                result=tools.execute('browser',{'action':'click','value':'#hello','text':''})
                assert 'Hola compatibilidad' in result['text'];checks.append('Legacy fill and click arguments still work')
                result=tools.execute('browser',{'action':'open','value':f'http://127.0.0.1:{server.server_port}','text':''})
                assert result['title']=='Nexo fixture';checks.append('Legacy open arguments still work')
                try:tools.execute('browser',{'action':'click','value':'.missing-selector','text':''})
                except ValueError:checks.append('Missing selector rejected')
                else:raise AssertionError('Missing selector accepted')
                try:tools.execute('browser',{'action':'open','value':'file:///etc/passwd','text':''})
                except ValueError:checks.append('Non-HTTP URL rejected')
                else:raise AssertionError('file URL accepted')
                assert tools.execute('browser',{'action':'close'})['closed'];checks.append('Browser closes')
            finally:tools.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=3)
    report={'passed':True,'environment':'Linux virtual display; Chromium; loopback fixture; no LLM API','checks':checks}
    Path(__file__).with_name('pruebas-navegador.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':True,'checks':len(checks)},indent=2))
if __name__=='__main__':main()
