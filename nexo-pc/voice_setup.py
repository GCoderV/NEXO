"""Find an already installed compatible Python and isolate voice in .venv-voz.
The bootstrap may run under Python 3.15. It never installs/replaces a base Python.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

PROBE_CODE="import sys,sysconfig,struct,json; print(json.dumps({'version':list(sys.version_info[:3]),'bits':struct.calcsize('P')*8,'platform':sysconfig.get_platform(),'implementation':sys.implementation.name,'gil_disabled':bool(sysconfig.get_config_var('Py_GIL_DISABLED'))}))"

def parse_launcher(text):
    paths=[]
    for line in text.splitlines():
        match=re.search(r'(?i)([a-z]:\\.*\\python\.exe)"?\s*$',line)
        if match:paths.append(match.group(1))
    return paths

def compatible(info):
    version=info.get('version',[])
    return (isinstance(version,list) and len(version)>=2 and all(type(x) is int for x in version)
            and (3,11)<=tuple(version[:2])<=(3,14) and info.get('bits')==64 and info.get('platform')=='win-amd64'
            and info.get('implementation')=='cpython' and info.get('gil_disabled') is False)

def probe(executable):
    result=subprocess.run([str(executable),'-I','-S','-c',PROBE_CODE],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=12)
    if result.returncode!=0:raise RuntimeError('No se pudo iniciar este Python para comprobarlo.')
    info=json.loads(result.stdout.strip())
    if not isinstance(info,dict):raise ValueError('Respuesta de diagnóstico inválida.')
    return info

def deduplicate(paths):
    seen=set();result=[]
    for path in paths:
        normalized=os.path.normcase(os.path.realpath(str(path)))
        if normalized not in seen:seen.add(normalized);result.append(Path(path))
    return result

def discover(root):
    # Listing the registry/launcher does not request installation of a runtime.
    candidates=[Path(root)/'.venv-voz'/'Scripts'/'python.exe',Path(root)/'.venv'/'Scripts'/'python.exe',Path(sys.executable)]
    launcher=shutil.which('py')
    if launcher:
        try:
            listed=subprocess.run([launcher,'-0p'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=12)
            candidates.extend(Path(p) for p in parse_launcher(listed.stdout))
        except (OSError,subprocess.TimeoutExpired):pass
    for variable in ('APPDATA','LOCALAPPDATA'):
        value=os.environ.get(variable)
        if value:
            directory=Path(value)/'uv'/'python'
            try:candidates.extend(directory.glob('*/python.exe'))
            except OSError:pass
    return [p for p in deduplicate(candidates) if p.is_file()]

def choose_runtime(records,existing=None):
    available=[r for r in records if compatible(r)]
    if not available:return None
    if existing is not None:
        for record in available:
            if os.path.normcase(os.path.abspath(record['path']))==os.path.normcase(os.path.abspath(str(existing))):return record
    return max(available,key=lambda r:tuple(r['version']))

def app_is_open():
    if os.name!='nt':return False
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenMutexW.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR];kernel.OpenMutexW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.OpenMutexW(0x00100000,False,'Local\\NexoPC_0_2_single_instance')
    if handle:kernel.CloseHandle(handle);return True
    # Access denied may also indicate an existing mutex; do not install over a live app.
    return ctypes.get_last_error()==5

def confirm(text):return input(text+' [s/N] ').strip().lower() in ('s','si','sí')

def ensure_environment(root,record,approve=confirm,run=subprocess.run,inspect=probe):
    if not compatible(record):raise ValueError('No se creará un entorno con un Python incompatible para voz.')
    root=Path(root).resolve();environment=root/'.venv-voz';python=environment/'Scripts'/'python.exe'
    if python.is_file():
        try:
            if compatible(inspect(python)):return python
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):pass
    if environment.exists():
        if not approve('El entorno de voz anterior es incompleto o incompatible. ¿Conservarlo como respaldo y crear uno nuevo?'):
            raise RuntimeError('No se modificó el entorno de voz existente.')
        backup=root/('.venv-voz-respaldo-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
        environment.rename(backup);print('Respaldo conservado en:',backup)
    run([record['path'],'-I','-m','venv',str(environment)],check=True)
    if not python.is_file() or not compatible(inspect(python)):
        raise RuntimeError('El entorno de voz no quedó compatible. No se tocó el Python de Nexo ni el predeterminado.')
    return python

def install_voice(root,python,run=subprocess.run):
    root=Path(root).resolve()
    # Repair a previous interrupted venv/ensurepip step using bundled wheels only.
    run([str(python),'-I','-m','ensurepip','--upgrade'],check=True)
    run([str(python),'-I','-m','pip','--isolated','install','-r',str(root/'requirements-voice.txt')],check=True)
    # Import check loads libraries only: no microphone or playback is started.
    check="import vosk,sounddevice; from winrt.windows.media.speechsynthesis import SpeechSynthesizer; from winrt.windows.media.playback import MediaPlayer; print('Componentes de voz importados correctamente.')"
    run([str(python),'-I','-c',check],check=True)
    run([str(python),str(root/'prepare_voice.py'),'--yes'],check=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--diagnose',action='store_true');args=parser.parse_args()
    if os.name!='nt':print('Este instalador está destinado a Windows x64.');return 2
    root=Path(__file__).resolve().parent
    print('Nexo 0.5.0 — entorno independiente para voz')
    print('La interfaz conserva su Python; la voz necesita CPython 3.11–3.14 x64.')
    records=[]
    for path in discover(root):
        try:
            info=probe(path);record={'path':str(path),**info};records.append(record)
            version='.'.join(map(str,info.get('version',[])))
            print(('COMPATIBLE' if compatible(info) else 'No compatible para voz'),'- Python',version,'-',str(info.get('bits'))+' bits -',info.get('platform'))
            print(' ',path)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:print('No se pudo comprobar:',path,'-',str(error))
    chosen=choose_runtime(records,root/'.venv-voz'/'Scripts'/'python.exe')
    if not chosen:
        print('No se encontró un Python de voz compatible. Puedes instalar Python 3.11–3.14 x64 en paralelo; este instalador no lo descargará ni reemplazará tu Python.');return 2
    print('\nPython seleccionado para voz:',chosen['path'])
    print('Versión:','.'.join(map(str,chosen['version'])))
    print('Entorno separado:',root/'.venv-voz')
    if args.diagnose:print('Solo diagnóstico: no se cambió ningún entorno ni se descargó nada.');return 0
    if app_is_open():print('Nexo está abierto. Ciérralo completamente y vuelve a ejecutar instalar-VOZ.cmd.');return 2
    print('\nSe prepararán dependencias opcionales desde PyPI y el modelo español incluido en el paquete. Si falta el ZIP incluido, se descargará desde alphacephei.com (40 MB).')
    print('No se reemplaza Python, no se modifica .venv de Nexo y no se cambian claves, sesiones ni permisos del micrófono.')
    if not confirm('¿Preparar el entorno separado de voz?'):print('Cancelado sin instalar componentes.');return 0
    try:
        python=ensure_environment(root,chosen);install_voice(root,python)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        print('\nInstalación de voz incompleta:',error)
        print('Revisa el error anterior. Esta etapa no usa el micrófono; no es una prueba de permisos de audio.')
        return 1
    print('\nListo. Abre INICIAR.cmd. Nexo usará automáticamente .venv-voz para micrófono y lectura.')
    print('En Ajustes → Voz, pulsa Detectar voces instaladas y comprueba es-MX. El micrófono sigue apagado.');return 0

if __name__=='__main__':raise SystemExit(main())
