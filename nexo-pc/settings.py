"""Profile preferences; Windows DPAPI secrets. No plaintext secret fallback."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
from storage import atomic_json

DEFAULTS = {'provider':'Groq','model':'openai/gpt-oss-120b','endpoint':'http://127.0.0.1:11434',
 'workspace':str(Path.home()/'NexoPC-Trabajo'),'approval':'plan','max_calls':16,'max_actions':48,
 'economy':True,'timeout':120,'context_limit':120000,'font_size':11,'remember':True,
 'voice_auto_send':True,'voice_delay':3.0,'voice_auto_read':True,
 'voice_model':str(Path.home()/'.nexo-pc'/'speech-models'/'vosk-model-small-es-0.42'),
 'voice_language':'es-MX','voice_id':'','voice_rate':1.0,
 'flags':{'files':True,'shell':False,'browser':False,'desktop':False}}

class WindowsProtector:
    """DPAPI current user, UI forbidden. Same Windows account can decrypt."""
    def _crypt(self, data, decrypt=False):
        if os.name!='nt':
            raise RuntimeError('Guardar claves requiere Windows DPAPI. No se guardarán en texto plano; puedes usarlas solo durante esta sesión.')
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
        buf=ctypes.create_string_buffer(data)
        src=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
        crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        fn.restype=wintypes.BOOL
        kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
        if not fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:return ctypes.string_at(out.pbData,out.cbData)
        finally:kernel.LocalFree(out.pbData)
    def seal(self,text):return base64.b64encode(self._crypt(text.encode('utf-8'))).decode('ascii')
    def open(self,text):return self._crypt(base64.b64decode(text,validate=True),True).decode('utf-8')

class Settings:
    def __init__(self,root,protector=None):
        self.path=Path(root)/'preferences.json';self.protector=protector or WindowsProtector()
        self.data={'version':1,'preferences':dict(DEFAULTS),'profiles':{}};self.warning=''
        if self.path.exists():
            try:
                if self.path.stat().st_size>2_000_000:raise ValueError('Archivo excesivo.')
                saved=json.loads(self.path.read_text('utf-8'))
                if saved.get('version')!=1 or not isinstance(saved.get('profiles'),dict):raise ValueError('Formato no compatible.')
                self.data['preferences'].update({k:v for k,v in saved.get('preferences',{}).items() if k in DEFAULTS})
                self.data['profiles']=saved['profiles']
            except (ValueError,OSError,TypeError) as e:self.warning='No se pudieron cargar preferencias: '+str(e)
    @staticmethod
    def profile_id(provider,model,endpoint=''):
        endpoint=endpoint.rstrip('/') if provider=='Ollama' else ''
        return hashlib.sha256(json.dumps([provider,model.strip(),endpoint]).encode()).hexdigest()
    def persist(self):atomic_json(self.path,self.data)
    def save_preferences(self,values):
        self.data['preferences'].update({k:v for k,v in values.items() if k in DEFAULTS})
        # Execution grants, consent and autonomy are never restored at startup.
        self.persist()
    def save_profile(self,provider,model,key='',endpoint='',remember=True):
        id=self.profile_id(provider,model,endpoint)
        record={'provider':provider,'model':model.strip(),'endpoint':endpoint if provider=='Ollama' else ''}
        if key and remember and provider!='Ollama':record['secret_dpapi']=self.protector.seal(key.strip())
        self.data['profiles'][id]=record;self.persist()
    def key(self,provider,model,endpoint=''):
        record=self.data['profiles'].get(self.profile_id(provider,model,endpoint),{})
        return self.protector.open(record['secret_dpapi']) if record.get('secret_dpapi') else ''
    def forget(self,provider,model,endpoint=''):
        id=self.profile_id(provider,model,endpoint)
        if id in self.data['profiles']:self.data['profiles'][id].pop('secret_dpapi',None);self.persist()
    def models(self,provider):
        return sorted({r['model'] for r in self.data['profiles'].values() if r.get('provider')==provider})
