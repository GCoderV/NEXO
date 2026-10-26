"""Narrow Windows COM adapter, through a fixed Windows PowerShell script.
No SDK install or policy change. Commands are never constructed from document text.
"""
import base64
import hashlib
import gzip
import copy
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import threading
import uuid
from datetime import datetime, timezone

class WordError(RuntimeError): pass

def validate_snapshot(s,path):
    if not isinstance(s,dict) or s.get('path')!=path:raise WordError('Documento inesperado.')
    for k in ('start','end','hwnd'):
        if isinstance(s.get(k),bool) or not isinstance(s.get(k),int):raise WordError('Rango de Word inválido.')
    if s['start']<0 or s['end']<s['start'] or not isinstance(s.get('text'),str) or not 0<=len(s['text'])<=12000:
        raise WordError('Selección inválida o demasiado larga.')
    if hashlib.sha256(s['text'].encode('utf-8')).hexdigest()!=s.get('hash'):raise WordError('Huella de selección inválida.')
    return s

def native_script():
    root=Path(__file__).parent
    return (root/'word_layout.ps1').read_text('utf-8')+'\n'+(root/'word_bridge.ps1').read_text('utf-8')

def encoded_native_command():
    # Compress ONLY trusted packaged program code, not stdin/document/model text.
    # This avoids the Windows 32767-character command line limit as the adapter grows.
    packed=base64.b64encode(gzip.compress(native_script().encode('utf-8'),mtime=0)).decode('ascii')
    loader="$b=[Convert]::FromBase64String('"+packed+"');$m=New-Object IO.MemoryStream(,$b);$g=New-Object IO.Compression.GZipStream($m,[IO.Compression.CompressionMode]::Decompress);$r=New-Object IO.StreamReader($g,[Text.Encoding]::UTF8);$s=$r.ReadToEnd();$r.Dispose();& ([ScriptBlock]::Create($s))"
    encoded=base64.b64encode(loader.encode('utf-16-le')).decode('ascii')
    if len(encoded)>31000:raise WordError('Adaptador supera el limite de la linea de comandos. No se ejecuto.')
    return encoded

class WordBridge:
    def __init__(self,journal,transport=None):
        self.journal=Path(journal);self.transport=transport or self._native
        self.snapshot=None;self.structure=None;self.prepared_plan=None;self.path=None;self.lock=threading.Lock()
    @staticmethod
    def _native(request):
        if os.name!='nt':raise WordError('La conexión nativa requiere Windows y Word de escritorio abierto. No está disponible en este sistema.')
        exe=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        encoded=encoded_native_command()
        try:
            run=subprocess.run([str(exe),'-NoLogo','-NoProfile','-NonInteractive','-STA','-EncodedCommand',encoded],
                               input=json.dumps(request,ensure_ascii=False).encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               timeout=180 if request.get('action')=='layout' else 90 if request.get('action')=='inspect' else 35,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as e:
            raise WordError('Word no respondió a tiempo. Si la operación podía cambiar Word, el resultado es desconocido: revisa Word. No se reintentó.') from e
        try:result=json.loads(run.stdout.decode('utf-8-sig'))
        except (ValueError,UnicodeError) as e:raise WordError('Respuesta de Word no válida. Revisa Word antes de repetir; no se reintentó.') from e
        if not isinstance(result,dict) or not result.get('ok'):
            message=str(result.get('error','Error de Word')) if isinstance(result,dict) else 'Respuesta no válida.'
            if request.get('action') in ('layout','insert','comment','create','open'):message+=' Si pudo haber cambios, inspecciona Word: el efecto puede ser parcial. No se reintentó.'
            raise WordError(message)
        return result
    def documents(self):
        result=self.transport({'action':'list'})
        if not result.get('ok'):raise WordError(result.get('error','No se pudieron listar documentos.'))
        docs=result.get('documents',[])
        if not isinstance(docs,list):raise WordError('Lista de documentos inválida.')
        return docs
    def create_document(self,approved=False):return self._document_action('create',None,approved)
    def open_document(self,path,approved=False):return self._document_action('open',path,approved)
    def _document_action(self,action,path,approved):
        if approved is not True:raise WordError('Falta aprobación explícita para abrir o crear en Word.')
        if action=='open' and (not isinstance(path,str) or not path.lower().endswith('.docx') or not PureWindowsPath(path).is_absolute()):raise WordError('Elige un archivo DOCX existente con una ruta completa de Windows.')
        if not self.lock.acquire(blocking=False):raise WordError('Ya hay una operación de Word en curso.')
        try:
            self.snapshot=None;self.structure=None;self.prepared_plan=None;operation=uuid.uuid4().hex;self._log('intent-'+action,operation)
            request={'action':action,'operation':operation,'approved':True}
            if path:request['path']=path
            try:
                result=self.transport(request)
                if not result.get('ok') or result.get('operation')!=operation:raise WordError('No se confirmó la operación. Inspecciona Word; no se reintentó.')
                if action=='open' and (not result.get('opened') or str(result.get('path','')).casefold()!=path.casefold()):raise WordError('Word no confirmó el archivo elegido.')
                if action=='create' and (not result.get('created') or result.get('saved') is not False):raise WordError('No se confirmó un documento nuevo sin guardar.')
            except Exception:self._log('unknown-or-failed',operation);raise
            self._log('confirmed-'+action,operation);return result
        finally:self.lock.release()
    def bind(self,path):
        if not isinstance(path,str) or not path.lower().endswith('.docx'):raise WordError('Confirma un archivo DOCX.')
        self.path=path;self.snapshot=None;self.structure=None;self.prepared_plan=None
    def inspect_document(self):
        from word_layout import validate_state
        if not self.path:raise WordError('Selecciona y autoriza el documento que se analizara.')
        self.snapshot=None;self.structure=None;self.prepared_plan=None
        result=self.transport({'action':'inspect','path':self.path})
        if not result.get('ok'):raise WordError(result.get('error','No se pudo analizar la estructura.'))
        self.structure=validate_state(result.get('structure'),self.path);return copy.deepcopy(self.structure)
    def prepare_layout(self,project,selected=(),format_all=True,index=True):
        from word_layout import build_plan
        if not self.structure:raise WordError('Analiza de nuevo el documento antes de preparar cambios.')
        self.prepared_plan=build_plan(self.structure,project,selected,format_all,index)
        return copy.deepcopy(self.prepared_plan)
    def apply_layout(self,plan,approved=False):
        if approved is not True:raise WordError('Falta aprobar la vista previa del conjunto.')
        if not self.prepared_plan or plan!=self.prepared_plan:raise WordError('El plan cambió o ya fue consumido. Prepara otra vista previa.')
        if not self.lock.acquire(blocking=False):raise WordError('Ya hay una operación Word en curso.')
        try:
            self.prepared_plan=None;self.snapshot=None;self.structure=None
            operation=uuid.uuid4().hex;self._log('intent-layout',operation,selection_hash=plan['snapshot']['hash'])
            try:
                result=self.transport({'action':'layout','path':self.path,'plan':plan,'approved':True,'operation':operation})
                if not result.get('ok') or result.get('operation')!=operation or result.get('text_verified') is not True or result.get('saved') is not False:raise WordError(result.get('error','Word no confirmó el conjunto. Inspecciona el documento antes de repetir.'))
            except Exception:self._log('unknown-or-failed',operation);raise
            self._log('confirmed-layout',operation);return result
        finally:self.lock.release()
    def read(self):
        if not self.path:raise WordError('Primero confirma un documento.')
        self.snapshot=None
        result=self.transport({'action':'read','path':self.path})
        if not result.get('ok'):raise WordError(result.get('error','No se pudo leer.'))
        self.snapshot=validate_snapshot(result.get('snapshot'),self.path)
        return dict(self.snapshot)
    def _log(self,event,operation,**extra):
        self.journal.parent.mkdir(parents=True,exist_ok=True)
        # No document text, file path, comment or key in the audit log.
        record={'time':datetime.now(timezone.utc).isoformat(),'event':event,'operation':operation,**extra}
        with self.journal.open('a',encoding='utf-8') as f:
            f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    def comment(self,text,approved=False):
        if self.snapshot and self.snapshot['start']==self.snapshot['end']:raise WordError('Selecciona texto para comentar.')
        return self._mutate('comment',text,approved)
    def insert(self,text,approved=False,section=None,format_profile=None):
        return self._mutate('insert',text,approved,section,format_profile)
    def _mutate(self,action,text,approved=False,section=None,format_profile=None):
        if approved is not True:raise WordError('Falta aprobación explícita de la operación.')
        if not isinstance(text,str) or not text.strip() or len(text)>(10000 if action=='insert' else 6000):raise WordError('Texto vacío o superior al límite de la operación.')
        blocks=None
        if action=='insert':
            from word_layout import paragraphs
            blocks=paragraphs(text,section,drop_main=False,base_level=0)
        if not self.lock.acquire(blocking=False):raise WordError('Ya hay una operación de Word en curso.')
        try:
            if not self.snapshot:raise WordError('Lee una selección nueva antes de comentar.')
            snapshot=validate_snapshot(self.snapshot,self.path);self.snapshot=None
            operation=uuid.uuid4().hex
            self._log('intent',operation,selection_hash=snapshot['hash'])
            try:
                request={'action':action,'path':self.path,'snapshot':snapshot,('comment' if action=='comment' else 'text'):text,'operation':operation}
                if blocks is not None:request['blocks']=blocks;request['format_profile']=format_profile
                result=self.transport(request)
                if not result.get('ok'):raise WordError(result.get('error','No se confirmó la inserción.'))
                if result.get('operation')!=operation:raise WordError('No se confirmó el identificador de la operación; revisa Word.')
                if not result.get('duplicate'):
                    valid=(result.get('text_unchanged') is True) if action=='comment' else (result.get('text_verified') is True and result.get('tracked') is True)
                    if not valid:raise WordError('No se confirmó la operación; revisa Word.')
            except Exception:
                self._log('unknown-or-failed',operation)
                raise
            self._log('confirmed',operation)
            return result
        finally:self.lock.release()
