"""Narrow Windows COM adapter, through a fixed Windows PowerShell script.
No SDK install or policy change. Commands are never constructed from document text.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import uuid
from datetime import datetime, timezone

class WordError(RuntimeError): pass

def validate_snapshot(s,path):
    if not isinstance(s,dict) or s.get('path')!=path:raise WordError('Documento inesperado.')
    for k in ('start','end','hwnd'):
        if isinstance(s.get(k),bool) or not isinstance(s.get(k),int):raise WordError('Rango de Word inválido.')
    if s['start']<0 or s['end']<=s['start'] or not isinstance(s.get('text'),str) or not 0<len(s['text'])<=12000:
        raise WordError('Selección inválida o demasiado larga.')
    if hashlib.sha256(s['text'].encode('utf-8')).hexdigest()!=s.get('hash'):raise WordError('Huella de selección inválida.')
    return s

class WordBridge:
    def __init__(self,journal,transport=None):
        self.journal=Path(journal);self.transport=transport or self._native
        self.snapshot=None;self.path=None;self.lock=threading.Lock()
    @staticmethod
    def _native(request):
        if os.name!='nt':raise WordError('La conexión nativa requiere Windows y Word de escritorio abierto. No está disponible en este sistema.')
        exe=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        script=Path(__file__).with_suffix('.ps1').read_text(encoding='utf-8')
        encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        try:
            run=subprocess.run([str(exe),'-NoLogo','-NoProfile','-NonInteractive','-STA','-EncodedCommand',encoded],
                               input=json.dumps(request,ensure_ascii=False).encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               timeout=35,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as e:
            raise WordError('Word no respondió a tiempo. Si estabas comentando, el resultado es desconocido: revisa Word. No se reintentó.') from e
        try:result=json.loads(run.stdout.decode('utf-8-sig'))
        except (ValueError,UnicodeError) as e:raise WordError('Respuesta de Word no válida. Revisa Word antes de repetir; no se reintentó.') from e
        if not isinstance(result,dict) or not result.get('ok'):
            raise WordError(str(result.get('error','Error de Word')) if isinstance(result,dict) else 'Respuesta no válida.')
        return result
    def documents(self):
        result=self.transport({'action':'list'})
        if not result.get('ok'):raise WordError(result.get('error','No se pudieron listar documentos.'))
        docs=result.get('documents',[])
        if not isinstance(docs,list):raise WordError('Lista de documentos inválida.')
        return docs
    def bind(self,path):
        if not isinstance(path,str) or not path.lower().endswith('.docx'):raise WordError('Confirma un archivo DOCX.')
        self.path=path;self.snapshot=None
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
        if approved is not True:raise WordError('Falta aprobación explícita del comentario.')
        if not isinstance(text,str) or not text.strip() or len(text)>6000:raise WordError('Comentario de 1 a 6000 caracteres requerido.')
        if not self.lock.acquire(blocking=False):raise WordError('Ya hay una operación de Word en curso.')
        try:
            if not self.snapshot:raise WordError('Lee una selección nueva antes de comentar.')
            snapshot=validate_snapshot(self.snapshot,self.path);self.snapshot=None
            operation=uuid.uuid4().hex
            self._log('intent',operation,selection_hash=snapshot['hash'])
            try:
                result=self.transport({'action':'comment','path':self.path,'snapshot':snapshot,'comment':text,'operation':operation})
                if not result.get('ok'):raise WordError(result.get('error','No se confirmó la inserción.'))
                if result.get('operation')!=operation:raise WordError('No se confirmó el identificador de la operación; revisa Word.')
                if not result.get('duplicate') and result.get('text_unchanged') is not True:raise WordError('No se confirmó la conservación del texto; revisa Word.')
            except Exception:
                self._log('unknown-or-failed',operation)
                raise
            self._log('confirmed',operation)
            return result
        finally:self.lock.release()
