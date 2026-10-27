"""Experimental M365 desktop-session transport. Independent implementation.
Only captures a user-authorized probe in a loopback diagnostic session.
No cookie store, passwords, refresh-token cache, TLS interception or DOM chat automation.
"""
import base64,copy,hashlib,json,os,socket,subprocess,threading,time,uuid
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,urlencode,urlunsplit
import urllib.request
import websocket
import logging
logging.getLogger("websocket").disabled=True
from providers import ProviderError
RS='\x1e'
HOSTS={'substrate.office.com','substrate.svc.cloud.microsoft'}
PAGES={'m365.cloud.microsoft','copilot.cloud.microsoft','m365copilot.com'}
MAX_FRAME=2_000_000
# Third-party observation (cramt/m365-copilot-proxy PR #49), NOT Microsoft documentation.
# Isolated behind a project flag so it can be compared without touching login or capture.
ROUTING_HEADER='X-RoutingParameter-SessionKey'
TURN_KEYS=('turnNumber','turnIndex','conversationTurn','turnCounter')

def parse_url(url):
    if not isinstance(url,str) or len(url)>50000:raise ValueError('Conexión Copilot inválida.')
    p=urlsplit(url)
    if p.scheme!='wss' or p.hostname not in HOSTS or p.port not in (None,443) or p.username or p.password or p.fragment or not p.path.startswith('/m365Copilot/Chathub/'):
        raise ValueError('El destino no es un ChatHub Microsoft permitido.')
    q=parse_qs(p.query)
    token=q.get('access_token',[''])[0]
    if not token or len(token)>32000:raise ValueError('No se encontró autenticación en la conexión observada.')
    return p,q,token

def claims(token):
    try:
        part=token.split('.')[1];d=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
        return d if isinstance(d,dict) else {}
    except Exception:return {}

def capture_info(secret):
    try:
        data=json.loads(secret)
        if not isinstance(data,dict):raise ValueError()
        _,_,token=parse_url(data.get('url'))
        frame=data.get('frame',{})
        if frame.get('type')!=4 or str(frame.get('target','')).lower()!='chat' or not isinstance(frame.get('arguments'),list) or not frame['arguments']:raise ValueError()
        return data,claims(token)
    except Exception:raise ValueError('Sesión Copilot inválida. Usa Conectar escritorio; no pegues tokens ni URLs del navegador.') from None

def identity_fingerprint(secret):
    """Stable, non-reversible scope for the signed-in Microsoft account (tenant + object id).

    Deliberately independent of the credential *generation*: renewing the captured
    session must not look like a different account. Returns '' when claims are absent.
    Never returns or stores a token, URL, header or cookie.
    """
    try:
        data=json.loads(secret)
        if not isinstance(data,dict):return ''
        _,_,token=parse_url(data.get('url',''))
        c=claims(token)
        tid=str(c.get('tid','') or '');oid=str(c.get('oid','') or '')
        if not tid or not oid or len(tid)>200 or len(oid)>200:return ''
        return hashlib.sha256(('m365|'+tid+'|'+oid).encode('utf-8')).hexdigest()
    except Exception:return ''

def expires_soon(identity,margin=30):
    """Some tenants issue exp as a string and some tokens omit it.

    An unknown expiry must NOT be treated as expired: that produced a false
    "Sesión de Copilot caducada" before any request reached Microsoft. A truly
    expired session is still handled by the auth error from the handshake.
    """
    value=identity.get('exp') if isinstance(identity,dict) else None
    if isinstance(value,bool):return False
    try:expires=float(value)
    except (TypeError,ValueError):return False
    return expires<time.time()+margin

def opening_headers(conversation):
    """Affinity header applied to the opening handshake only; value is the ConversationId.

    The existing URL parameter is left untouched. This is unverified external evidence,
    kept separate from authentication so it can be switched off for an isolated A/B test.
    """
    return [f'{ROUTING_HEADER}: {conversation}']

def turn_counter(obj,depth=0):
    """Optional server-provided turn counter. Heuristic; absence is normal, never fatal."""
    if not isinstance(obj,dict) or depth>2:return None
    for k in TURN_KEYS:
        value=obj.get(k)
        if type(value) is int and 0<=value<=10_000_000:return value
    for key in ('item','messages','result'):
        nested=obj.get(key)
        if isinstance(nested,dict):nested=[nested]
        if isinstance(nested,list):
            for item in nested[:10]:
                found=turn_counter(item,depth+1) if isinstance(item,dict) else None
                if found is not None:return found
    return None

def sanitize_frame(frame):
    a=frame['arguments'][0]
    if not isinstance(a,dict) or not isinstance(a.get('message'),dict):raise ValueError('Invocación no compatible.')
    keep=('source','optionsSets','streamingMode','spokenTextMode','allowedMessageTypes','clientInfo','tone','renderReferencesBehindEOS','isSbsSupported')
    clean={k:copy.deepcopy(a[k]) for k in keep if k in a}
    for name in ('optionsSets','allowedMessageTypes'):
        if name in clean and (not isinstance(clean[name],list) or any(not isinstance(x,str) or len(x)>300 for x in clean[name])):raise ValueError('Configuración de socket inválida.')
    # No local tools are exposed; observed file/user annotations aren't retained.
    clean['plugins']=[];clean['options']={};clean['extraExtensionParameters']={};clean['sliceIds']=[];clean['threadLevelGptId']={}
    m=a['message'];clean['message']={k:copy.deepcopy(m[k]) for k in ('inputMethod','locale','messageType','experienceType') if k in m}
    clean['message'].update(author='user',text='',entityAnnotationTypes=[],adaptiveCards=[],clientPreferences={})
    # clientInfo keeps only protocol labels, not old user/device/session identifiers.
    ci=clean.get('clientInfo',{})
    clean['clientInfo']={k:v for k,v in ci.items() if k in ('clientPlatform','clientAppName','clientEntrypoint','clientAppType','deviceOS','deviceType') and isinstance(v,str) and len(v)<200} if isinstance(ci,dict) else {}
    out={'type':4,'target':'chat','invocationId':'0','arguments':[clean]}
    if len(json.dumps(out))>60000:raise ValueError('Invocación demasiado grande.')
    return out

def launch_desktop():
    if os.name!='nt':raise ValueError('Conectar la aplicación de escritorio requiere Windows. No se ha iniciado ningún programa.')
    script="$p=Get-AppxPackage -Name Microsoft.MicrosoftOfficeHub | Select-Object -First 1; if($p){Join-Path $p.InstallLocation 'M365Copilot.exe'}"
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=15,creationflags=0x08000000)
    path=Path(r.stdout.strip())
    if not path.is_file() or path.name.lower()!='m365copilot.exe':raise ValueError('No se encontró M365Copilot.exe en el paquete instalado. Esta conexión no admite todavía otras variantes de la aplicación.')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    # Caller explicitly approves restarting/launching their own desktop client.
    # No process is killed, no app is installed, no security policy is changed.
    env={**os.environ,'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS':f'--remote-debugging-port={port} --remote-debugging-address=127.0.0.1'}
    subprocess.Popen([str(path),f'--edge-webview-switches=--remote-debugging-port={port} --remote-debugging-address=127.0.0.1'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return port

def launch_auth_window(root):
    if os.name!='nt':raise ValueError('La ventana de acceso requiere Microsoft Edge instalado en Windows.')
    candidates=[Path(os.environ.get(v,''))/'Microsoft/Edge/Application/msedge.exe' for v in ('PROGRAMFILES(X86)','PROGRAMFILES','LOCALAPPDATA') if os.environ.get(v)]
    exe=next((p for p in candidates if p.is_file()),None)
    if not exe:raise ValueError('No se encontró Microsoft Edge. Nexo no lo instalará automáticamente.')
    profile=Path(root)/'copilot-login';profile.mkdir(parents=True,exist_ok=True)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    subprocess.Popen([str(exe),'--user-data-dir='+str(profile),'--remote-debugging-port='+str(port),'--remote-debugging-address=127.0.0.1','--no-first-run','--no-default-browser-check','https://m365.cloud.microsoft/chat/'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return port

def verify_loopback_listener(port):
    if os.name!='nt':return
    if type(port)!=int:raise ValueError('Puerto inválido.')
    script=f'[System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object {{$_.Port -eq {port}}} | ForEach-Object {{$_.Address.ToString()}}'
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=10,creationflags=0x08000000)
    addresses=set(result.stdout.strip().splitlines())
    if result.returncode or not addresses or not addresses<={'127.0.0.1','::1'}:
        raise ProviderError('No se confirmó un puerto de diagnóstico exclusivamente local. Cierra la ventana de Copilot/Edge; no se capturará su sesión.',kind='auth')

def cdp_socket(url,port):
    p=urlsplit(url)
    if p.scheme!='ws' or p.hostname not in ('127.0.0.1','localhost','::1') or p.port!=port or p.username or p.password:raise ValueError('Destino de diagnóstico local inválido.')
    # Preconnected socket bypasses all environment proxy settings for local secrets.
    conn=socket.create_connection(('127.0.0.1',port),timeout=3)
    ws=websocket.WebSocket()
    try:ws.connect(url,socket=conn,suppress_origin=True,timeout=2,redirect_limit=0);return ws
    except Exception:conn.close();raise

def capture_connection(port,probe=None,previous=None,stop=None,timeout=180,on_ready=None):
    if type(port)!=int or not 1<=port<=65535:raise ValueError('Puerto de diagnóstico inválido.')
    stop=stop or threading.Event();deadline=time.monotonic()+timeout;ws=None;seen={};frame=None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPRedirectHandler())
    try:
        while time.monotonic()<deadline and not stop.is_set():
            try:
                # Explicit loopback only. Reject HTTP redirects before sending anything sensitive.
                from providers import NoRemoteRedirect
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRemoteRedirect())
                with opener.open(f'http://127.0.0.1:{port}/json/list',timeout=2) as r:raw=r.read(1_000_001)
                if len(raw)>1_000_000:raise ValueError('Diagnóstico excesivo.')
                tabs=json.loads(raw)
                target=next((t for t in tabs if isinstance(t,dict) and t.get('type')=='page' and urlsplit(t.get('url','')).hostname in PAGES),None)
                if target:
                    verify_loopback_listener(port)
                    ws=cdp_socket(target['webSocketDebuggerUrl'],port);break
            except ProviderError:raise
            except Exception:pass
            stop.wait(.5)
        if not ws:raise ProviderError('No se pudo conectar al diagnóstico de Copilot. Cierra la app de Copilot, vuelve a Conectar escritorio e inicia sesión en la ventana que se abra. No se forzó ningún proceso.',kind='auth')
        # Desktop WebViews may lose their host context on a forced Page.reload.
        # Observe only; the user opens a NEW chat and sends the probe manually.
        ws.send(json.dumps({'id':1,'method':'Network.enable'}))
        if on_ready:on_ready()
        while time.monotonic()<deadline and not stop.is_set():
            try:raw=ws.recv()
            except websocket.WebSocketTimeoutException:continue
            if not raw:break
            if len(raw)>MAX_FRAME:continue
            e=json.loads(raw);params=e.get('params',{});method=e.get('method')
            if method=='Network.webSocketCreated':
                url=params.get('url','')
                try:parse_url(url)
                except Exception:continue
                seen[params['requestId']]=url
                if previous is not None:
                    old_claim=capture_info(json.dumps(previous))[1];new_claim=claims(parse_url(url)[2])
                    if not old_claim.get('oid') or any(new_claim.get(k)!=old_claim.get(k) for k in ('oid','tid')):
                        raise ProviderError('La cuenta de la ventana cambió. Reconecta y selecciona la cuenta correcta.',kind='auth')
                    return json.dumps({**previous,'url':url,'captured_at':time.time()})
            if method=='Network.webSocketFrameSent' and params.get('requestId') in seen:
                payload=params.get('response',{}).get('payloadData','')
                for part in payload.split(RS):
                    try:f=json.loads(part)
                    except Exception:continue
                    if not isinstance(f,dict) or f.get('type')!=4 or str(f.get('target','')).lower()!='chat':continue
                    try:text=f['arguments'][0]['message']['text']
                    except (KeyError,IndexError,TypeError):continue
                    if probe is None or text.strip()!=probe.strip():continue
                    frame=sanitize_frame(f)
                    return json.dumps({'url':seen[params['requestId']],'frame':frame,'cdp_port':port,'captured_at':time.time()})
        raise ProviderError('No se observó una conexión nueva con la frase. Abre un chat NUEVO en la ventana de Microsoft y vuelve a conectar. No se recargó ni se borró su sesión.',kind='auth')
    except ProviderError:raise
    except Exception:raise ProviderError('La conexión de diagnóstico se interrumpió. No se incluyen URLs ni credenciales en el error.',kind='auth') from None
    finally:
        if ws:ws.close()

class SignalDecoder:
    def __init__(self,previous_turn=None):
        self.buffer='';self.delta='';self.snapshot='';self.done=False;self.citations=[]
        self.server_turn=previous_turn if type(previous_turn) is int else None;self.regression=False
    def feed(self,raw):
        if isinstance(raw,bytes):raw=raw.decode('utf-8')
        if not isinstance(raw,str) or len(raw)>MAX_FRAME:raise ProviderError('Trama Copilot inválida o excesiva.')
        self.buffer+=raw
        if len(self.buffer)>MAX_FRAME:raise ProviderError('Trama Copilot incompleta demasiado grande.')
        frames=[]
        while RS in self.buffer:
            part,self.buffer=self.buffer.split(RS,1)
            if not part.strip():continue
            try:f=json.loads(part)
            except Exception:raise ProviderError('El protocolo de Copilot cambió: trama no válida.') from None
            if not isinstance(f,dict):raise ProviderError('Trama de Copilot inesperada.')
            frames.append(f)
        return frames
    def collect(self,obj):
        from copilot_metadata import references
        for item in references(obj):
            if len(self.citations)<30 and not any(x['url']==item['url'] for x in self.citations):self.citations.append(item)
    def consume(self,f):
        self.collect(f)
        observed=turn_counter(f)
        if observed is not None:
            if self.server_turn is not None and observed<self.server_turn:self.regression=True
            self.server_turn=observed
        t=f.get('type')
        if f.get('error'):raise ProviderError('Copilot rechazó la invocación; revisa la conexión y la ruta elegida.')
        if t==2:
            item=f.get('item') or {};self.collect(item);result=item.get('result') or {}
            value=str(result.get('value','Success')).lower()
            if value not in ('success','ok',''):
                quota=any(x in value for x in ('throttl','limit','quota'))
                raise ProviderError('Copilot informó un límite.' if quota else 'Copilot no completó la petición.',kind='quota' if quota else 'request',retryable=quota,retry_after=60)
            self._messages(item.get('messages',[]))
        if t==1:
            for a in f.get('arguments',[]):
                if not isinstance(a,dict):continue
                self.collect(a)
                if isinstance(a.get('writeAtCursor'),str):self.delta+=a['writeAtCursor']
                self._messages(a.get('messages',[]))
        if len(self.delta)>100000 or len(self.snapshot)>100000:raise ProviderError('Respuesta de Copilot demasiado grande.')
        if t==3:self.done=True
        if t==7:raise ProviderError('Copilot cerró la conexión antes de confirmar el final.',kind='uncertain')
    def _messages(self,items):
        if isinstance(items,dict):items=[items]
        if not isinstance(items,list):return
        for m in items:
            self.collect(m)
            if isinstance(m,dict) and m.get('author') in ('bot','assistant') and m.get('messageType','Chat') in ('Chat','') and isinstance(m.get('text'),str):self.snapshot=m['text']
    def text(self):return self.snapshot or self.delta

def complete(secret,prompt,model,timeout,stop=None,remote=None,update_secret=None,connector=None,details=None,affinity=None):
    """One transport connection on an existing conversation. A new socket is NOT a new chat.

    `remote` is the persistent per-account slot. `affinity=None` reads the project flag
    from that slot; the header can be disabled for an isolated comparison.
    """
    data,identity=capture_info(secret);stop=stop or threading.Event();remote=remote if remote is not None else {};start=time.monotonic()
    if expires_soon(identity,30):
        if not data.get('cdp_port'):raise ProviderError('Sesión de Copilot caducada: pulsa Conectar escritorio.',kind='auth',retryable=True)
        try:secret=capture_connection(data['cdp_port'],previous=data,stop=stop,timeout=min(30,timeout))
        except ProviderError:raise ProviderError('No se observó una renovación de Microsoft 365. Reconecta la cuenta desde Nexo y envía la frase en un chat nuevo; no se forzó ninguna recarga.',kind='auth',retryable=not stop.is_set()) from None
        data,identity=capture_info(secret)
        if expires_soon(identity,10):raise ProviderError('Microsoft todavía no renovó la sesión. Vuelve a conectar.',kind='auth',retryable=True)
        if update_secret:update_secret(secret)
    if len(prompt)>60000:raise ProviderError('Contexto Copilot demasiado grande.')
    if model!='auto':raise ProviderError('Solo se admite la selección auto observada en tu sesión.')
    p,q,token=parse_url(data['url']);conversation=remote.setdefault('conversation',str(uuid.uuid4()));session=remote.setdefault('session',str(uuid.uuid4()));remote.setdefault('turns',0);request=str(uuid.uuid4())
    for name,value in {'chatsessionid':session,'clientrequestid':request,'X-SessionId':session,'ConversationId':conversation,'XRoutingParameterSessionKey':session}.items():q[name]=[value]
    url=urlunsplit((p.scheme,p.netloc,p.path,urlencode(q,doseq=True),''))
    use_affinity=bool(remote.get('affinity',True)) if affinity is None else bool(affinity)
    headers=opening_headers(conversation) if use_affinity else []
    frame=copy.deepcopy(data['frame']);a=frame['arguments'][0]
    a.update(sessionId=session,clientCorrelationId=request,traceId=request,isStartOfSession=not remote.get('turns',0))
    client_info=a.get('clientInfo')
    if not isinstance(client_info,dict):client_info={};a['clientInfo']=client_info
    client_info['clientSessionId']=session
    a['message'].update(text=prompt,author='user',requestId=request)
    if model!='auto':a['tone']=model
    from datetime import datetime,timezone
    now=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
    metrics={'type':1,'target':'Metrics','arguments':[{'Timestamps':{k:now for k in ('ConnectionStart','UserInputStart','ConnectionEstablished','UserInputSubmit')}}]}
    ws=None;sent=False;confirmed=False;decoder=SignalDecoder(previous_turn=remote.get('server_turn'));last_ping=time.monotonic()
    try:
        if connector is None:
            ws=websocket.WebSocket();ws.connect(url,origin='https://m365.cloud.microsoft',timeout=max(1,min(20,timeout)),redirect_limit=0,header=headers)
        else:ws=connector(url)
        ws.settimeout(1);ws.send(json.dumps({'protocol':'json','version':1})+RS)
        handshake=False
        while time.monotonic()-start<timeout and not stop.is_set():
            try:raw=ws.recv()
            except websocket.WebSocketTimeoutException:
                if sent and time.monotonic()-last_ping>10:ws.send('{"type":6}'+RS);last_ping=time.monotonic()
                continue
            if not raw:raise ProviderError('Copilot desconectó sin confirmar la respuesta.',kind='uncertain' if sent else 'unavailable',retryable=not sent)
            for f in decoder.feed(raw):
                if not handshake:
                    if f.get('error') or f!={}:raise ProviderError('Handshake SignalR no aceptado; protocolo pendiente de revisión.')
                    handshake=True;ws.send(json.dumps(frame,ensure_ascii=False)+RS+json.dumps(metrics)+RS);sent=True;continue
                decoder.consume(f)
                if f.get('type')==6:ws.send('{"type":6}'+RS)
                if decoder.done:
                    text=decoder.text()
                    if not text:raise ProviderError('Copilot confirmó el final pero no devolvió texto utilizable.')
                    remote['turns']=remote.get('turns',0)+1
                    if decoder.server_turn is not None:remote['server_turn']=decoder.server_turn
                    remote['regression']=bool(decoder.regression)
                    remote.pop('uncertain',None)
                    confirmed=True
                    if details is not None:details.update(citations=decoder.citations,complete=True,continuity={
                        'turns':remote['turns'],'affinity_header':use_affinity,'server_turn':decoder.server_turn,
                        'regression':decoder.regression,'confirmed':True})
                    return text
        raise ProviderError('Petición Copilot detenida o sin final confirmado. Reanudar podría generar otra respuesta.',kind='uncertain' if sent else 'unavailable',retryable=False)
    except ProviderError:raise
    except Exception as e:
        code=getattr(e,'status_code',None)
        if not sent and code in (401,403):raise ProviderError('Copilot rechazó la sesión. Vuelve a Conectar escritorio.',kind='auth',retryable=True) from None
        raise ProviderError('Fallo de conexión Copilot; no se muestran detalles que puedan incluir autenticación.',kind='uncertain' if sent else 'unavailable',retryable=not sent) from None
    finally:
        # A message may have reached Microsoft even without a confirmation. Keep the
        # identifiers and mark the result; never silently open a different chat.
        if sent and not confirmed:
            remote['uncertain']=True
            if details is not None:details['continuity']={'turns':remote.get('turns',0),'affinity_header':use_affinity,'confirmed':False}
        if ws:
            try:ws.close()
            except Exception:pass
