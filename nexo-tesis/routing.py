"""Bounded sequential failover over explicitly configured routes."""
import threading,time,copy
from config import edit
from providers import API,ProviderError
class RoutedAPI:
    neutral=True
    def __init__(self,config,routes,factory=API):
        self.config=config;self.routes=routes;self.factory=factory
        self.provider=routes[0]['provider'];self.model=routes[0]['model'];self.endpoint=routes[0]['endpoint'];self.key=''
        self.instructions='';self.last_usage={};self.calls=0;self.attempts=0;self.trace=[];self.stop=threading.Event();self.emit=lambda s:None;self.started=None;self.remote={};self.project_id='';self.route_identity=''
    def redact(self,text):return self.config.redact(text)
    def request(self,conversation,declarations):
        if self.started is None:self.started=time.monotonic()
        self.last_usage={};last=None
        limit=max(1,min(30,int(self.config.data.get('attempt_limit',6))))
        budget=max(10,min(600,int(self.config.data.get('cycle_seconds',180))))
        for r in self.routes:
            if self.stop.is_set():raise RuntimeError('Detenido; no se iniciaron más peticiones.')
            remaining=budget-(time.monotonic()-self.started)
            if self.attempts>=limit or remaining<1:break
            aid=r['account_id'];rid=r['id']
            if self.config.data['cooldowns'].get(rid,0)>time.time():continue
            if self.config.data['health'].get(aid)=='auth':continue
            key=self.config.route_key(r)
            if key is None:continue
            alias=self.config.data['accounts'].get(aid,{}).get('alias','Local')
            self.emit(f"Intento {self.attempts+1}/{limit} · {r['provider']} · {alias} · {r['model']}")
            api=self.factory(r['provider'],key,r['model'],r['endpoint'],max(10,min(90,int(remaining))))
            api.timeout=max(1,min(api.timeout,remaining));api.instructions=self.instructions;api.stop=self.stop
            api.remote=self.remote.setdefault(aid,{}) if aid else {};api.project_id=self.project_id
            if r['provider']=='Copilot365':
                def update(secret,aid=aid):
                    from copilot_socket import identity_fingerprint
                    # Bookkeeping must never discard a response Microsoft already
                    # confirmed: the account may have been deleted mid-flight.
                    with edit(self.config):
                        account=self.config.data['accounts'].get(aid)
                        if not account:return
                        try:
                            if account.get('secret'):account['secret']=self.config.protector.seal(secret)
                            identity=identity_fingerprint(secret)
                            if identity:account['identity']=identity
                            self.config.memory[aid]=secret;self.config.flush()
                        except Exception:
                            self.emit('La sesión se renovó pero no se pudo guardar la credencial; reconecta si se pierde.')
                api.update_secret=update
            text='\n'.join(m.get('content','') for m in conversation)
            payload=[{'role':'user','parts':[{'text':text}]}] if r['provider']=='Gemini' else conversation
            self.attempts+=1;self.calls+=1
            try:
                response=api.request(payload,declarations)
                if aid:
                    # A confirmed answer outranks a bookkeeping write failure.
                    try:
                        with edit(self.config):
                            self.config.data['health'][aid]='ok';self.config.flush()
                    except Exception:pass
                self.last_usage=copy.deepcopy(api.last_usage);self.provider=api.provider;self.model=api.model;self.endpoint=api.endpoint;self.route_identity=f'{api.provider} / {alias} / {api.model}'
                self.trace.append({'route':rid,'status':'ok'});self.routes=[r]+sorted([x for x in self.routes if x['id']!=rid],key=lambda x:0 if x['provider']==r['provider'] and x['model']==r['model'] else 1 if x['provider']==r['provider'] else 2)
                return response
            except ProviderError as e:
                self.trace.append({'route':rid,'status':e.kind});last=e
                try:
                    with edit(self.config):
                        if e.kind in ('quota','unavailable'):
                            self.config.data['cooldowns'][rid]=time.time()+max(1,e.retry_after or (60 if e.kind=='quota' else 10));self.config.flush()
                        elif e.kind=='access':self.config.data['cooldowns'][rid]=time.time()+300;self.config.flush()
                        elif e.kind=='auth':self.config.data['health'][aid]='auth';self.config.flush()
                except Exception:pass  # never replace the original ProviderError
                if not e.retryable:raise
        if last:raise last
        raise ProviderError('No quedan rutas listas o se alcanzó el límite del ciclo. La petición queda disponible en Reanudar.',kind='quota',retryable=False)
