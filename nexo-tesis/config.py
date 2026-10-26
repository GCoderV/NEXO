"""Provider accounts and model routes. Secrets stay account-scoped, never in projects."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
from secrets_store import WindowsProtector
DEFAULT={'provider':'Groq','model':'openai/gpt-oss-120b','endpoint':'http://127.0.0.1:11434','timeout':90}
def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(dir=path.parent,prefix='.tesis-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
class Config:
    def __init__(self,root,protector=None):
        self.path=Path(root)/'config.json';self.protector=protector or WindowsProtector();self.memory={};self.warning='';self.needs_backup=False
        self.data={'schema':2,'current':dict(DEFAULT),'profiles':{},'accounts':{},'routes':[], 'automatic':True,'attempt_limit':6,'cycle_seconds':180,'health':{},'cooldowns':{}}
        defaults=copy.deepcopy(self.data)
        if self.path.exists():
            try:
                if self.path.stat().st_size>2_000_000:raise ValueError('Configuración demasiado grande.')
                d=json.loads(self.path.read_text('utf-8'))
                if not isinstance(d.get('current'),dict) or not isinstance(d.get('profiles'),dict):raise ValueError('Formato incorrecto.')
                if d.get('schema',1)>2:raise ValueError('Configuración de una versión posterior.')
                if d.get('schema',1)==2:
                    if not isinstance(d.get('accounts'),dict) or not isinstance(d.get('routes'),list):raise ValueError('Cuentas o rutas inválidas.')
                    for aid,a in d['accounts'].items():
                        if not isinstance(a,dict) or a.get('id')!=aid or not all(isinstance(a.get(k),str) for k in ('id','provider','alias')):raise ValueError('Cuenta inválida.')
                    for r in d['routes']:
                        if not isinstance(r,dict) or not all(isinstance(r.get(k),str) for k in ('id','provider','model','account_id','endpoint')):raise ValueError('Ruta inválida.')
                    if not isinstance(d.get('health',{}),dict) or not isinstance(d.get('cooldowns',{}),dict):raise ValueError('Estado de rutas inválido.')
                self.data.update(d)
                if d.get('schema',1)==1:self._migrate()
            except Exception as e:self.data=defaults;self.warning='No se pudo cargar la configuración; no se ha sobrescrito: '+type(e).__name__;self.block_save=True
    def flush(self):
        if getattr(self,'block_save',False):raise ValueError(self.warning)
        if self.needs_backup and self.path.exists():
            backup=self.path.with_name('config-v01-respaldo.json')
            if not backup.exists():backup.write_bytes(self.path.read_bytes())
            self.needs_backup=False
        atomic(self.path,self.data)
    @staticmethod
    def key_id(provider,model,endpoint):
        if provider=='Gemini':model=model.removeprefix('models/')
        return hashlib.sha256(json.dumps([provider,model,endpoint if provider=='Ollama' else '']).encode()).hexdigest()
    def _migrate(self):
        self.needs_backup=True;d=self.data;d['schema']=2
        found={}
        for pid,old in list(d['profiles'].items()):
            provider=old.get('provider');model=old.get('model');endpoint=old.get('endpoint','');aid=''
            if not provider or not model:continue
            if old.get('secret'):
                # Keep encrypted secrets if DPAPI cannot be opened on this machine.
                try:
                    secret=self.protector.open(old['secret']);finger=(provider,secret)
                except Exception:finger=(provider,pid);self.warning='Algunas claves migradas requieren el usuario Windows original.'
                if finger in found:aid=found[finger]
                else:
                    aid=uuid.uuid4().hex;found[finger]=aid
                    d['accounts'][aid]={'id':aid,'provider':provider,'alias':'Migrada '+str(len(found)), 'enabled':True,'generation':uuid.uuid4().hex,'secret':old['secret']}
            record={k:v for k,v in old.items() if k!='secret'};record['account_id']=aid;d['profiles'][pid]=record
            rid=uuid.uuid4().hex;d['routes'].append({'id':rid,'provider':provider,'model':model,'endpoint':endpoint,'account_id':aid,'enabled':True,'auto':False})
            c=d['current']
            if pid==self.key_id(c['provider'],c['model'],c.get('endpoint','')):c['route_id']=rid
        self.warning=(self.warning+' Configuración migrada: revisa las cuentas y marca las rutas que desees incluir en rotación.').strip()
    def secret(self,aid):
        if aid in self.memory:return self.memory[aid]
        a=self.data['accounts'].get(aid,{})
        return self.protector.open(a['secret']) if a.get('secret') else ''
    def account(self,provider,alias,key,remember=False,aid=None,enabled=True):
        from providers import PROVIDERS
        if provider not in PROVIDERS or provider=='Ollama':raise ValueError('Proveedor de cuenta inválido.')
        if not isinstance(key,str) or not key.strip():
            if provider=='Copilot365':raise ValueError('Copilot365 no usa API key. Falta la conexión a tu sesión de M365: en Cuentas pulsa «Conectar escritorio M365». No hay que escribir claves, tokens ni URLs.')
            raise ValueError('Configura una credencial antes de guardar la cuenta.')
        if aid and self.data['accounts'].get(aid,{}).get('provider')!=provider:raise ValueError('La cuenta pertenece a otro proveedor.')
        aid=aid or uuid.uuid4().hex
        generation=uuid.uuid4().hex
        try:
            if self.secret(aid)==key.strip():generation=self.data['accounts'].get(aid,{}).get('generation',generation)
        except Exception:pass
        rec={'id':aid,'provider':provider,'alias':alias.strip()[:80] or 'Cuenta','enabled':bool(enabled),'generation':generation}
        if provider=='Copilot365':
            from copilot_socket import capture_info,identity_fingerprint
            capture_info(key)
            # Account scope (oid/tid), stable across credential renewal. Not a token.
            identity=identity_fingerprint(key.strip())
            if identity:rec['identity']=identity
        if remember:rec['secret']=self.protector.seal(key.strip())
        self.data['accounts'][aid]=rec;self.memory[aid]=key.strip();self.data['health'].pop(aid,None);self.flush();return aid
    def remove_account(self,aid):
        self.data['accounts'].pop(aid,None);self.memory.pop(aid,None);self.data['health'].pop(aid,None)
        for r in self.data['routes']:
            if r['account_id']==aid:r['account_id']='';r['auto']=False
        self.flush()
    def route(self,provider,model,aid='',endpoint='http://127.0.0.1:11434',auto=False,rid=None):
        from providers import API
        if provider!='Ollama':
            a=self.data['accounts'].get(aid,{})
            if a.get('provider')!=provider:
                if provider=='Copilot365':raise ValueError('Copilot365 necesita una conexión a tu sesión de Microsoft 365, no una API key. En Cuentas pulsa «Conectar escritorio M365» y vuelve aquí.')
                raise ValueError('Selecciona una cuenta configurada de este proveedor.')
            key=self.secret(aid)
        else:key='';aid=''
        api=API(provider,key,model,endpoint)
        rec={'id':rid or uuid.uuid4().hex,'provider':provider,'model':api.model,'account_id':aid,'endpoint':api.endpoint if provider=='Ollama' else '', 'auto':bool(auto and provider!='Ollama'),'enabled':True}
        old=next((r for r in self.data['routes'] if r['id']==rec['id']),None)
        if old:old.update(rec)
        else:self.data['routes'].append(rec)
        self.data['profiles'][self.key_id(provider,api.model,endpoint)]={**rec}
        self.flush();return rec['id']
    def ensure_account_route(self,aid):
        """Expose an orphan account without changing selection or enabling rotation."""
        from providers import PROVIDERS
        a=self.data['accounts'].get(aid,{})
        if not a.get('enabled') or a.get('provider') not in PROVIDERS:return None
        existing=next((r for r in self.data['routes'] if r['account_id']==aid and r['provider']==a['provider']),None)
        if existing:return existing['id']
        try:
            key=self.secret(aid)
            if not key or not key.strip():return None
        except Exception:return None
        # Suggested, not verified: no network and no automatic selection.
        return self.route(a['provider'],PROVIDERS[a['provider']],aid,auto=False)
    def select(self,rid):
        r=next((r for r in self.data['routes'] if r['id']==rid),None)
        if not r:raise ValueError('Ruta no encontrada.')
        self.data['current']={k:r.get(k,'') for k in ('provider','model','endpoint')};self.data['current'].update(route_id=rid,timeout=90);self.flush()
    def key(self,provider,model,endpoint):
        record=self.data['profiles'].get(self.key_id(provider,model,endpoint),{})
        if record.get('account_id'):return self.secret(record['account_id'])
        for a in self.data['accounts'].values():
            if a['provider']==provider and a['enabled']:return self.secret(a['id'])
        return ''
    def save(self,provider,model,endpoint,key,remember=False,timeout=90):
        # Compatibility entry point; same secret -> same provider account.
        aid=''
        if provider!='Ollama':
            for a in self.data['accounts'].values():
                try:equal=a['provider']==provider and self.secret(a['id'])==key.strip()
                except Exception:equal=False
                if equal:aid=a['id'];break
            aid=self.account(provider,'Cuenta '+str(len(self.data['accounts'])+1),key,remember,aid or None)
        rid=self.route(provider,model,aid,endpoint);self.select(rid);self.data['current']['timeout']=timeout;self.flush()
    def route_key(self,r):
        if r['provider']=='Ollama':return ''
        a=self.data['accounts'].get(r.get('account_id'),{})
        if not a.get('enabled') or a.get('provider')!=r['provider']:return None
        try:
            key=self.secret(a['id'])
            if not isinstance(key,str) or not key.strip():return None
            if r['provider']=='Copilot365':
                from copilot_socket import capture_info
                capture_info(key)
            return key
        except Exception:return None
    def candidates(self):
        current=self.data['current'];rid=current.get('route_id')
        first=next((r for r in self.data['routes'] if r['id']==rid),None)
        if not first:raise ValueError('Configura y selecciona un modelo con cuenta en Modelos y cuentas.')
        result=[copy.deepcopy(first)] if first.get('enabled',True) and self.route_key(first) is not None else []
        if first['provider']!='Ollama' and self.data.get('automatic',True):
            rest=[r for r in self.data['routes'] if r['id']!=rid and r.get('enabled') and r.get('auto') and r['provider']!='Ollama' and self.route_key(r) is not None]
            rest.sort(key=lambda r:0 if r['provider']==first['provider'] and r['model']==first['model'] else 1 if r['provider']==first['provider'] else 2)
            result+=copy.deepcopy(rest)
        # Same account/model/endpoint is a single route, even if configured twice.
        seen=set();out=[]
        for r in result:
            ident=(r['provider'],r['model'],r['account_id'],r['endpoint'])
            if ident not in seen:seen.add(ident);out.append(r)
        if not out:raise ValueError('No hay rutas habilitadas con una credencial utilizable. Configura o selecciona otra.')
        return out
    def api(self):
        from routing import RoutedAPI
        return RoutedAPI(self,self.candidates())
    def redact(self,text):
        text=str(text)
        for aid in self.data['accounts']:
            try:k=self.secret(aid)
            except Exception:continue
            if k:
                text=text.replace(k,'[CLAVE OMITIDA]')
                if k.startswith('{'):
                    try:
                        from urllib.parse import urlsplit,parse_qs
                        token=parse_qs(urlsplit(json.loads(k).get('url','')).query).get('access_token',[''])[0]
                        if token:text=text.replace(token,'[TOKEN OMITIDO]')
                    except Exception:pass
        return text
