"""Provider transport adapted from Nexo PC; no PC tools or runtime dependency."""
import json
import re
import urllib.request
import time
import urllib.parse
import urllib.error
import uuid
PROVIDERS = {'Groq':'openai/gpt-oss-120b','Gemini':'gemini-3.8-flash','OpenRouter':'google/gemma-4-31b-it:free','Requesty':'google/gemma-4-31b-it','NVIDIA':'google/gemma-4-31b-it','Copilot365':'auto','Ollama':'qwen3:8b'}
BASES={'Groq':'https://api.groq.com/openai/v1','OpenRouter':'https://openrouter.ai/api/v1','Requesty':'https://router.requesty.ai/v1','NVIDIA':'https://integrate.api.nvidia.com/v1'}
class ProviderError(RuntimeError):
    def __init__(self,message,kind='request',retryable=False,retry_after=0):
        super().__init__(message);self.kind=kind;self.retryable=retryable;self.retry_after=retry_after
class NoRemoteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ProviderError('Redirección bloqueada: no se reenviará una clave a otro destino.')
def open_remote(request,timeout=30):
    return urllib.request.build_opener(NoRemoteRedirect()).open(request,timeout=timeout)
def read_bounded(response,limit,deadline,stop=None):
    if not hasattr(response,'read1'):return response.read(limit+1)
    parts=[];total=0
    while total<=limit:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ProviderError('Tiempo de respuesta agotado; resultado no confirmado.',kind='uncertain')
        if stop is not None and stop.is_set():raise ProviderError('Petición detenida después de enviar; resultado no confirmado.',kind='uncertain')
        try:response.fp.raw._sock.settimeout(remaining)
        except AttributeError:pass
        chunk=response.read1(min(65536,limit+1-total))
        if not chunk:break
        total+=len(chunk);parts.append(chunk)
    return b''.join(parts)

def http_error(error,key):
    # Never expose response bodies: providers may echo headers or signed URLs.
    code=error.code
    if code==403:return ProviderError('Acceso a este modelo rechazado (403). Revisa permisos.',kind='access',retryable=True)
    if code==401:return ProviderError(f'Acceso rechazado ({code}). Revisa credencial y permisos del modelo.',kind='auth',retryable=True)
    if code in (402,429):
        delay=60
        try:
            value=error.headers.get('Retry-After','60')
            try:delay=float(value)
            except ValueError:
                import email.utils,time
                delay=max(1,email.utils.parsedate_to_datetime(value).timestamp()-time.time())
        except Exception:pass
        return ProviderError(f'Cuota, saldo o velocidad agotados ({code}).',kind='quota',retryable=True,retry_after=max(1,min(86400*7,delay)))
    if code==404:return ProviderError('Modelo no disponible (404). Revisa el catálogo y la cuenta.',kind='unavailable',retryable=True)
    if code in (500,502,503,504):return ProviderError(f'Servicio no disponible ({code}).',kind='unavailable',retryable=True,retry_after=10)
    return ProviderError(f'El proveedor rechazó la petición (HTTP {code}); no se repitió automáticamente.')

SYSTEM = 'Eres un asistente académico. Devuelve JSON válido.'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise RuntimeError('Redirección bloqueada en la conexión local de Ollama.')

def local_endpoint(value):
    parsed=urllib.parse.urlsplit(value.strip())
    if (parsed.scheme!='http' or parsed.hostname not in ('localhost','127.0.0.1','::1')
        or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/')):
        raise ValueError('Ollama requiere una dirección local: http://127.0.0.1:11434 (sin rutas ni credenciales).')
    try:port=parsed.port
    except ValueError:raise ValueError('Puerto local inválido.') from None
    if port is not None and not 1<=port<=65535:raise ValueError('Puerto local inválido.')
    return value.strip().rstrip('/')

def local_json(endpoint,path,payload=None,timeout=120):
    url=local_endpoint(endpoint)+path
    headers={'Content-Type':'application/json','User-Agent':'NexoTesis/0.1'}
    request=urllib.request.Request(url,json.dumps(payload).encode() if payload is not None else None,headers)
    # Do not route localhost through a system proxy; do not follow remote redirects.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(request,timeout=timeout) as response:raw=response.read(2_000_001)
    except urllib.error.HTTPError as e:
        details=e.read(1500).decode('utf-8','replace')
        raise RuntimeError(f'Ollama HTTP {e.code}: {details}. Comprueba que el modelo esté instalado y admita herramientas.') from None
    except urllib.error.URLError:
        raise RuntimeError('No se pudo conectar con Ollama. Abre Ollama en este PC y comprueba la dirección y el puerto.') from None
    if len(raw)>2_000_000:raise RuntimeError('Respuesta local demasiado grande.')
    body=json.loads(raw)
    if not isinstance(body,dict):raise RuntimeError('Ollama devolvió un formato inválido.')
    if body.get('error'):raise RuntimeError('Ollama: '+str(body['error']))
    return body

def ollama_models(endpoint):
    return [m['name'] for m in local_json(endpoint,'/api/tags',timeout=8).get('models',[]) if isinstance(m,dict) and isinstance(m.get('name'),str)]

class API:
    def __init__(self, provider, key, model, endpoint='http://127.0.0.1:11434', timeout=120):
        if provider not in PROVIDERS or (provider!='Ollama' and not key.strip()):
            if provider=='Copilot365':raise ValueError('Copilot365 no usa API key: falta la conexión a tu sesión de Microsoft 365. En Cuentas pulsa «Conectar escritorio M365».')
            raise ValueError('Selecciona un proveedor e introduce su clave en Configuración. Ollama no necesita clave.')
        if provider=='Gemini' and isinstance(model,str) and model.startswith('models/'):model=model[7:]
        if not re.fullmatch(r'[A-Za-z0-9_./:-]{1,120}',model):raise ValueError('Identificador de modelo inválido.')
        if isinstance(timeout,bool) or not isinstance(timeout,int) or not 10<=timeout<=600:raise ValueError('Tiempo de espera: 10–600 segundos.')
        if provider=='Copilot365':
            from copilot_socket import capture_info
            capture_info(key)
            if model!='auto':raise ValueError('Copilot365 solo admite auto; no se garantizan alias de modelos.')
        self.provider,self.key,self.model=provider,key.strip() if provider!='Ollama' else '',model
        self.endpoint=local_endpoint(endpoint) if provider=='Ollama' else ''
        if provider=='Ollama' and 'cloud' in model.lower():
            raise ValueError('Este perfil es local: los modelos con etiqueta cloud no están permitidos. Selecciona un modelo descargado.')
        self.timeout=timeout;self.instructions=SYSTEM;self.calls=0;self.last_usage={}
    def capture_usage(self,body):
        if self.provider=='Gemini':
            data=body.get('usageMetadata') or {};data=data if isinstance(data,dict) else {};incoming=data.get('promptTokenCount');outgoing=data.get('candidatesTokenCount')
            thoughts=data.get('thoughtsTokenCount',0)
            if type(outgoing) is int and type(thoughts) is int:outgoing+=thoughts
        elif self.provider=='Ollama':incoming=body.get('prompt_eval_count');outgoing=body.get('eval_count')
        else:
            data=body.get('usage') or {};data=data if isinstance(data,dict) else {};incoming=data.get('prompt_tokens');outgoing=data.get('completion_tokens')
        self.last_usage={}
        if type(incoming) is int and incoming>=0:self.last_usage['input_tokens']=incoming
        if type(outgoing) is int and outgoing>=0:self.last_usage['output_tokens']=outgoing
    def request(self, conversation, declarations):
        self.calls+=1;self.last_usage={}
        if self.provider=='Copilot365':
            from copilot_socket import complete
            text='\n'.join(m.get('content','') for m in conversation)
            details={}
            raw=complete(self.key,self.instructions+'\n\n'+text,self.model,self.timeout,getattr(self,'stop',None),getattr(self,'remote',{}),getattr(self,'update_secret',None),details=details)
            return {'role':'assistant','content':raw,'metadata':details},raw,[]
        if self.provider=='Ollama':
            payload={'model':self.model,'messages':[{'role':'system','content':self.instructions}]+conversation,'stream':False,'format':'json','options':{'num_predict':4096}}
            if declarations:payload['tools']=[{'type':'function','function':d} for d in declarations]
            body=local_json(self.endpoint,'/api/chat',payload,self.timeout)
            self.capture_usage(body)
            raw=body.get('message')
            if not isinstance(raw,dict):raise RuntimeError('Ollama no devolvió un mensaje utilizable.')
            message={k:v for k,v in raw.items() if k in ('role','content','tool_calls','thinking')}
            message['role']='assistant';text=message.get('content') or '';calls=[]
            for c in message.get('tool_calls',[]) or []:
                if not isinstance(c,dict):continue
                f=c.get('function')
                if not isinstance(f,dict) or not isinstance(f.get('name'),str):continue
                args=f.get('arguments',{})
                if isinstance(args,str):
                    try:args=json.loads(args)
                    except (ValueError,TypeError):args={}
                if not isinstance(args,dict):args={}
                calls.append({'id':uuid.uuid4().hex,'name':f['name'],'args':args})
            return message,text,calls
        if self.provider=='Gemini':
            url='https://generativelanguage.googleapis.com/v1beta/models/'+urllib.parse.quote(self.model,safe='')+':generateContent'
            payload={'systemInstruction':{'parts':[{'text':self.instructions}]},'contents':conversation,
                     'generationConfig':{'maxOutputTokens':8192,'responseMimeType':'application/json'}}
            if self.model.startswith('gemma-'):
                payload.pop('systemInstruction',None);payload['generationConfig'].pop('responseMimeType',None)
                payload['contents']=[{'role':'user','parts':[{'text':self.instructions+'\n\n'+'\n'.join(p.get('text','') for m in conversation for p in m.get('parts',[]))}]}]
            if declarations:payload['tools']=[{'functionDeclarations':declarations}]
            headers={'x-goog-api-key':self.key}
        else:
            url=BASES[self.provider]+'/chat/completions'
            payload={'model':self.model,'messages':[{'role':'system','content':self.instructions}]+conversation,'max_completion_tokens':4096,'response_format':{'type':'json_object'}}
            if self.provider!='Groq':payload['max_tokens']=payload.pop('max_completion_tokens')
            if declarations:payload.update(tools=[{'type':'function','function':d} for d in declarations],tool_choice='auto',parallel_tool_calls=False)
            headers={'Authorization':'Bearer '+self.key}
        headers['Content-Type']='application/json';headers['User-Agent']='NexoTesis/0.2'
        req=urllib.request.Request(url,json.dumps(payload).encode(),headers)
        deadline=time.monotonic()+self.timeout
        try:
            with open_remote(req,timeout=self.timeout) as response:raw=read_bounded(response,2_000_000,deadline,getattr(self,'stop',None))
            if len(raw)>2_000_000:raise RuntimeError('Respuesta demasiado grande.')
            body=json.loads(raw)
        except urllib.error.HTTPError as e:
            details=e.read(8192).decode('utf-8','replace')
            if self.key:details=details.replace(self.key,'[CLAVE OMITIDA]')
            if e.code==400:
                try:error=json.loads(details).get('error',{})
                except (ValueError,AttributeError):error={}
                if isinstance(error,dict) and error.get('code')=='tool_use_failed':
                    reason=str(error.get('message','Argumentos de herramienta inválidos.'))[:1200]
                    raise RuntimeError('API HTTP 400: el proveedor rechazó una llamada de herramienta. '+reason+
                        '\nLa llamada rechazada no se ejecutó en Nexo. No se reintentaron ni repitieron las acciones anteriores; podrían haber dejado efectos. Revisa el estado antes de continuar.') from None
            if e.code==404 and self.provider=='Gemini':
                try:description=json.loads(details).get('error',{}).get('message','')
                except (ValueError,AttributeError):description=''
                hint=('Selecciona gemini-3.8-flash con el botón Sugerido.' if self.model=='gemini-2.5-flash' else 'Comprueba el identificador y la disponibilidad del modelo en tu cuenta.')
                raise ProviderError(f'Gemini: modelo {self.model} no disponible (HTTP 404). '+hint+' Revisa Modelos y cuentas y sigue en el MISMO proyecto.',kind='unavailable',retryable=True) from None
            raise http_error(e,self.key) from None
        except (urllib.error.URLError,TimeoutError,OSError):
            raise ProviderError('La conexión terminó sin respuesta confirmada. El servidor podría haber procesado la petición; revisa antes de Reanudar.',kind='uncertain') from None
        self.capture_usage(body)
        if self.provider=='Gemini':
            candidates=body.get('candidates',[])
            if not candidates or 'content' not in candidates[0]:raise RuntimeError('El proveedor no devolvió contenido utilizable; revisa filtros, modelo y cuota.')
            message=candidates[0]['content']
            text='\n'.join(p['text'] for p in message.get('parts',[]) if 'text' in p and not p.get('thought'))
            calls=[{'id':p['functionCall'].get('id'),'name':p['functionCall']['name'],'args':p['functionCall'].get('args',{})} for p in message.get('parts',[]) if 'functionCall' in p]
        else:
            message=body['choices'][0]['message'];text=message.get('content') or ''
            calls=[{'id':c['id'],'name':c['function']['name'],'args':json.loads(c['function']['arguments'])} for c in message.get('tool_calls',[])]
            message={k:v for k,v in message.items() if k in ('role','content','tool_calls')}
        return message,text,calls



def list_models(provider,key='',endpoint='http://127.0.0.1:11434'):
    """Explicit metadata request; no inference. No automatic downloads or paid fallback."""
    if provider=='Ollama':return [{'id':x,'cost':'local'} for x in ollama_models(endpoint)]
    if provider=='Copilot365':
        from copilot_socket import capture_info
        capture_info(key)
        return [{'id':'auto','cost':'plan de Microsoft; versión de modelo no verificada'}]
    if provider not in PROVIDERS or not key.strip():raise ValueError('Selecciona una cuenta configurada primero.')
    headers={'x-goog-api-key':key} if provider=='Gemini' else {'Authorization':'Bearer '+key}
    url='https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000' if provider=='Gemini' else BASES[provider]+'/models'
    try:
        with open_remote(urllib.request.Request(url,headers=headers),timeout=15) as response:raw=response.read(5_000_001)
        if len(raw)>5_000_000:raise ValueError('Catálogo demasiado grande.')
        data=json.loads(raw)
    except urllib.error.HTTPError as e:raise http_error(e,key) from None
    except (urllib.error.URLError,TimeoutError,OSError):raise RuntimeError('No se pudo consultar el catálogo; se conserva tu selección.') from None
    if not isinstance(data,dict):raise ValueError('Catálogo inválido.')
    items=data.get('models' if provider=='Gemini' else 'data',[]);result=[]
    if not isinstance(items,list):raise ValueError('Catálogo inválido.')
    for item in items[:3000]:
        if not isinstance(item,dict):continue
        name=item.get('name' if provider=='Gemini' else 'id','')
        if not isinstance(name,str):continue
        if provider=='Gemini':
            name=name.removeprefix('models/')
            methods=item.get('supportedGenerationMethods',[])
            if methods and 'generateContent' not in methods:continue
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_./:-]{1,120}',name):continue
        cost='consultar plan/precio'
        if provider=='OpenRouter':
            price=item.get('pricing') or {}
            try:
                if price and all(float(price.get(k,0))==0 for k in ('prompt','completion','request','image')):cost='tokens gratuitos publicados; sujeto a cuotas'
                else:cost='pago'
            except (ValueError,TypeError):pass
        result.append({'id':name,'cost':cost})
    if not result:raise ValueError('El proveedor no devolvió modelos utilizables. Puedes indicar un ID manual.')
    return result
