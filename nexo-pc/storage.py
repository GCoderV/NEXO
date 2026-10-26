"""Local sessions and per-file checkpoints. Independent implementation, not Cline code."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
from adapters import workspace_path

def now(): return datetime.now(timezone.utc).isoformat()
def digest(data): return hashlib.sha256(data).hexdigest()
def safe_id(value):
    if not isinstance(value,str) or len(value)!=32 or any(c not in '0123456789abcdef' for c in value): raise ValueError('Identificador inválido.')
    return value

def atomic_bytes(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.nexo-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def atomic_json(path,data):atomic_bytes(path,json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8'))

def disk_copy(value):
    """Keep thought signatures and text; do not persist screenshot pixels."""
    if isinstance(value,dict):
        if 'inlineData' in value:return {'text':'[Captura omitida del historial guardado. Solicita una nueva si necesitas inspección visual.]'}
        return {k:disk_copy(v) for k,v in value.items() if k not in ('image_base64','image','api_key','apiKey')}
    if isinstance(value,list):return [disk_copy(v) for v in value]
    return value

class Store:
    def __init__(self,root=None):
        self.root=Path(root or Path.home()/'.nexo-pc').resolve();self.secrets=set()
        for name in ('sessions','checkpoints'):(self.root/name).mkdir(parents=True,exist_ok=True)
    def new_session(self,provider,model,workspace,title):
        record={'version':1,'id':uuid.uuid4().hex,'created':now(),'updated':now(),'provider':provider,'model':model,
                'workspace':str(Path(workspace).resolve()),'title':title[:80], 'messages':[], 'display':[], 'pending':[], 'status':'idle','api_calls':0}
        self.save(record);return record
    def save(self,record):
        record['updated']=now();target=self.root/'sessions'/(safe_id(record['id'])+'.json')
        def redact(value):
            if isinstance(value,str):
                for secret in self.secrets:
                    if secret:value=value.replace(secret,'[CLAVE OMITIDA]')
                return value
            if isinstance(value,list):return [redact(v) for v in value]
            if isinstance(value,dict):return {k:redact(v) for k,v in value.items()}
            return value
        data=disk_copy(record)
        for field in ('messages','display','pending','title','history_archives'):
            if field in data:data[field]=redact(data[field])
        atomic_json(target,data)
    def load(self,id):
        p=self.root/'sessions'/(safe_id(id)+'.json')
        if p.stat().st_size>8_000_000:raise ValueError('La sesión supera el límite de 8 MB.')
        r=json.loads(p.read_text('utf-8'))
        if r.get('version')!=1 or r.get('id')!=id:raise ValueError('Sesión incompatible.')
        if not isinstance(r.get('messages'),list) or not isinstance(r.get('pending'),list):raise ValueError('Sesión inválida.')
        return r
    def sessions(self):
        entries=[]
        for p in (self.root/'sessions').glob('*.json'):
            try:r=self.load(p.stem);entries.append({k:r.get(k) for k in ('id','title','updated','workspace','provider','model','status')})
            except (OSError,ValueError):continue
        return sorted(entries,key=lambda x:x['updated'],reverse=True)
    def audit(self,session,kind,**fields):
        with (self.root/'audit.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'time':now(),'session':session,'event':kind,**fields},ensure_ascii=False)+'\n')
    def preview(self,workspace,path,content):
        import difflib
        p=workspace_path(workspace,path)
        if p.exists() and (not p.is_file() or p.stat().st_size>1_000_000):raise ValueError('Solo se editan archivos de hasta 1 MB.')
        before=p.read_bytes() if p.exists() else None
        old=(before or b'').decode('utf-8')
        diff=''.join(difflib.unified_diff(old.splitlines(True),content.splitlines(True),fromfile=str(p)+' (antes)',tofile=str(p)+' (propuesto)'))
        return {'expected_hash':digest(before) if before is not None else None,'diff':diff,'path':str(p)}
    def write(self,workspace,path,content,session,expected_hash):
        if len(content)>32000:raise ValueError('Edición demasiado grande.')
        p=workspace_path(workspace,path)
        if p.exists() and (not p.is_file() or p.stat().st_size>1_000_000):raise ValueError('Archivo inválido o demasiado grande.')
        before=p.read_bytes() if p.exists() else None
        if (digest(before) if before is not None else None)!=expected_hash:raise RuntimeError('El archivo cambió desde la revisión. Se requiere un nuevo diff y aprobación.')
        after=content.encode('utf-8');id=uuid.uuid4().hex;folder=self.root/'checkpoints'/id;folder.mkdir()
        meta={'id':id,'session':session,'time':now(),'workspace':str(Path(workspace).resolve()),'path':str(p.relative_to(Path(workspace).resolve())),
              'before_hash':digest(before) if before is not None else None,'after_hash':digest(after),'state':'prepared'}
        if before is not None:atomic_bytes(folder/'before.bin',before)
        atomic_json(folder/'metadata.json',meta)
        atomic_bytes(p,after)
        meta['state']='applied';atomic_json(folder/'metadata.json',meta)
        self.audit(session,'checkpoint-created',checkpoint=id,path=meta['path'])
        return {'written':str(p),'checkpoint':id,'bytes':len(after),'scope':'Solo este archivo; no incluye efectos externos.'}
    def checkpoints(self,workspace):
        result=[];root=str(Path(workspace).resolve())
        for p in (self.root/'checkpoints').glob('*/metadata.json'):
            try:
                r=json.loads(p.read_text('utf-8'))
                if r.get('workspace')==root:result.append(r)
            except (OSError,ValueError):continue
        return sorted(result,key=lambda x:x['time'],reverse=True)
    def restore(self,id,workspace):
        folder=self.root/'checkpoints'/safe_id(id);meta=json.loads((folder/'metadata.json').read_text('utf-8'))
        if meta['workspace']!=str(Path(workspace).resolve()):raise ValueError('El checkpoint pertenece a otra carpeta.')
        if meta['state'] not in ('applied','prepared'):raise ValueError('Checkpoint ya restaurado o no aplicable.')
        p=workspace_path(workspace,meta['path'])
        if not p.is_file() or p.stat().st_size>1_000_000 or digest(p.read_bytes())!=meta['after_hash']:
            raise RuntimeError('El archivo cambió después del checkpoint. No se sobrescribieron tus cambios; restaura primero los checkpoints más recientes o revisa el archivo.')
        if meta['before_hash'] is None:p.unlink()
        else:
            before=(folder/'before.bin').read_bytes()
            if digest(before)!=meta['before_hash']:raise RuntimeError('Copia de seguridad alterada o corrupta.')
            atomic_bytes(p,before)
        meta['state']='restored';meta['restored_at']=now();atomic_json(folder/'metadata.json',meta)
        self.audit(meta['session'],'checkpoint-restored',checkpoint=id,path=meta['path'])
        return {'restored':str(p),'removed_new_file':meta['before_hash'] is None}
