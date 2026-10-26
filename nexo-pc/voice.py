"""Opt-in speech helpers. No network, API keys, or task permissions here."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import unicodedata

from voice_assets import MODEL_NAME, MODEL_URL, MODEL_SHA256, DEFAULT_MODEL

def command_of(text):
    normalized=''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')
    normalized=' '.join(re.sub(r'[^a-z\s]',' ',normalized).split())
    return {'nexo enviar':'send','nexo cancelar':'cancel','nexo borrar':'clear',
            'nexo apagar microfono':'off','nexo silenciar':'off'}.get(normalized)

class VoiceFlow:
    """UI-thread state machine: only final dictation can arm a one-shot send."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.active=False;self.pending=False;self.deadline=None;self.review_required=False
    def enable(self):self.active=True;self.cancel_pending();self.review_required=False
    def disable(self):self.active=False;self.cancel_pending();self.review_required=False
    def cancel_pending(self):self.pending=False;self.deadline=None
    def partial(self,delay):
        if self.active and self.pending and self.deadline is not None:self.deadline=self.clock()+delay
    def final(self,auto,delay,confidence=1.0):
        if not self.active:return
        if confidence<0.65:self.review_required=True
        self.pending=True
        self.deadline=self.clock()+delay if auto and not self.review_required else None
    def take_due(self,allowed):
        if not allowed or not self.active or not self.pending or self.deadline is None:return False
        if self.clock()<self.deadline:return False
        self.cancel_pending();return True
    def sent(self):self.cancel_pending();self.review_required=False

def speech_text(text):
    # Plain text synthesis, never SSML or executable markup.
    text=re.sub(r'```.*?```',' Bloque de código omitido en la lectura. ',text,flags=re.S)
    text=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',text)
    text=re.sub(r'https?://\S+',' enlace ',text)
    text=re.sub(r'(?m)^\s*#{1,6}\s*','',text).replace('**','').replace('`','')
    return text.strip()

def child_options():
    return {'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0)} if os.name=='nt' else {}

def voice_python(root=None,windows=None):
    """Prefer the independent voice environment, keeping the UI interpreter intact.
    Legacy installs into the UI's .venv remain supported when no voice env exists.
    """
    root=Path(root) if root is not None else Path(__file__).resolve().parent
    windows=os.name=='nt' if windows is None else windows
    directory=root/'.venv-voz'
    candidate=directory/('Scripts' if windows else 'bin')/('python.exe' if windows else 'python')
    if candidate.is_file():return str(candidate)
    if directory.exists():raise RuntimeError('El entorno .venv-voz está incompleto. Cierra Nexo y ejecuta instalar-VOZ.cmd para repararlo sin cambiar el Python de la interfaz.')
    return sys.executable

def native_voices():
    if os.name!='nt':raise RuntimeError('Las voces nativas requieren Windows. Copiar/pegar no necesita instalar voz.')
    result=subprocess.run([voice_python(),'-I','-u',str(Path(__file__).with_name('speech_native.py')),'voices'],
                          capture_output=True,text=True,encoding='utf-8',timeout=25,**child_options())
    try:data=json.loads(result.stdout)
    except ValueError:raise RuntimeError('No se pudo consultar las voces. Ejecuta instalar-VOZ.cmd y revisa los paquetes de voz de Windows.') from None
    if not data.get('ok'):raise RuntimeError(data.get('error','No se pudieron listar las voces.'))
    return data['voices']

class Recorder:
    def __init__(self,emit):
        self.emit=emit;self.process=None;self.token=0;self.epoch=0;self.paused=True;self.lock=threading.Lock()
    def start(self,model):
        self.stop();self.token+=1;token=self.token;self.epoch=0;self.paused=True
        self.process=subprocess.Popen([voice_python(),'-I','-u',str(Path(__file__).with_name('speech_recorder.py')),'--model',str(model)],
                                      stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                      text=True,encoding='utf-8',bufsize=1,**child_options())
        process=self.process
        def watch():
            reported_error=False
            try:
                for line in process.stdout:
                    try:item=json.loads(line)
                    except ValueError:continue
                    if not isinstance(item,dict):continue
                    if item.get('type')=='error':reported_error=True
                    if token==self.token:self.emit(token,item)
                code=process.wait()
                if token==self.token and not reported_error:self.emit(token,{'type':'error','text':f'El micrófono se detuvo (código {code}). Actívalo de nuevo cuando esté disponible.'})
            finally:
                if process.stdout:process.stdout.close()
                if process.stdin:
                    try:process.stdin.close()
                    except OSError:pass
        threading.Thread(target=watch,daemon=True).start()
        return token
    def pause(self,paused):
        if paused==self.paused:return
        self.paused=paused;self.epoch+=1
        if self.process and self.process.poll() is None:
            try:
                with self.lock:
                    self.process.stdin.write(json.dumps({'pause':paused,'epoch':self.epoch})+'\n');self.process.stdin.flush()
            except (OSError,ValueError):pass
    def stop(self):
        self.token+=1;self.paused=True;self.epoch+=1
        process=self.process;self.process=None
        if process and process.poll() is None:
            try:process.terminate()
            except OSError:pass
            threading.Thread(target=self._reap,args=(process,),daemon=True).start()
    @staticmethod
    def _reap(process):
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:process.kill();process.wait()

class Speaker:
    def __init__(self,emit):self.emit=emit;self.token=0;self.process=None;self.lock=threading.Lock()
    def speak(self,text,language='es-MX',voice_id='',rate=1.0):
        self.stop();self.token+=1;token=self.token
        payload={'text':speech_text(text),'language':language,'voice_id':voice_id,'rate':rate}
        if not payload['text']:return None
        if len(payload['text'])>12000:raise ValueError('La lectura supera 12 000 caracteres. Selecciona una respuesta más corta; no se truncó silenciosamente.')
        process=subprocess.Popen([voice_python(),'-I','-u',str(Path(__file__).with_name('speech_native.py')),'speak'],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                 text=True,encoding='utf-8',**child_options())
        self.process=process
        def wait():
            try:
                output,_=process.communicate(json.dumps(payload,ensure_ascii=False),timeout=1800)
                try:result=json.loads(output)
                except ValueError:result={'ok':False,'error':'No se pudo iniciar la voz nativa. Ejecuta instalar-VOZ.cmd y Detectar voces en Ajustes.'}
                if token==self.token:self.emit(token,result)
            except subprocess.TimeoutExpired:
                process.kill();process.communicate()
                if token==self.token:self.emit(token,{'ok':False,'error':'Lectura detenida por tiempo máximo.'})
            except (OSError,ValueError) as e:
                if token==self.token:self.emit(token,{'ok':False,'error':str(e)})
        threading.Thread(target=wait,daemon=True).start();return token
    def stop(self):
        self.token+=1;process=self.process;self.process=None
        if process and process.poll() is None:
            try:process.terminate()
            except OSError:pass

def open_windows_dictation():
    if os.name!='nt':raise RuntimeError('El acceso Win+H requiere Windows.')
    import ctypes
    from ctypes import wintypes
    ULONG_PTR=ctypes.c_size_t
    class Mouse(ctypes.Structure):
        _fields_=[('dx',wintypes.LONG),('dy',wintypes.LONG),('mouseData',wintypes.DWORD),('dwFlags',wintypes.DWORD),('time',wintypes.DWORD),('dwExtraInfo',ULONG_PTR)]
    class Keyboard(ctypes.Structure):
        _fields_=[('wVk',wintypes.WORD),('wScan',wintypes.WORD),('dwFlags',wintypes.DWORD),('time',wintypes.DWORD),('dwExtraInfo',ULONG_PTR)]
    class Hardware(ctypes.Structure):
        _fields_=[('uMsg',wintypes.DWORD),('wParamL',wintypes.WORD),('wParamH',wintypes.WORD)]
    class Union(ctypes.Union):_fields_=[('mi',Mouse),('ki',Keyboard),('hi',Hardware)]
    class Input(ctypes.Structure):_fields_=[('type',wintypes.DWORD),('union',Union)]
    keys=(Input*4)()
    for item,(vk,flags) in zip(keys,[(0x5B,0),(0x48,0),(0x48,2),(0x5B,2)]):item.type=1;item.union.ki=Keyboard(vk,0,flags,0,0)
    user=ctypes.WinDLL('user32',use_last_error=True);user.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(Input),ctypes.c_int];user.SendInput.restype=wintypes.UINT
    if user.SendInput(4,keys,ctypes.sizeof(Input))!=4:
        # Best effort release avoids leaving a modifier pressed after partial injection.
        user.keybd_event(0x48,0,2,0);user.keybd_event(0x5B,0,2,0)
        raise RuntimeError('Windows no aceptó el atajo. Puedes usar Win+H manualmente.')


_user32_foreground=None
def process_has_foreground():
    """Additional Windows check: Tk's remembered focus alone is not sufficient."""
    if os.name!='nt':return True
    import ctypes
    from ctypes import wintypes
    global _user32_foreground
    if _user32_foreground is None:
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.GetForegroundWindow.restype=wintypes.HWND
        user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowThreadProcessId.restype=wintypes.DWORD
        _user32_foreground=user
    handle=_user32_foreground.GetForegroundWindow()
    if not handle:return False
    pid=wintypes.DWORD();_user32_foreground.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    return pid.value==os.getpid()
