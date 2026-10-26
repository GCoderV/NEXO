"""Non-network diagnostic: no keys, environment variables or user paths printed."""
import importlib.util
import json
import platform
import subprocess
import sys
from voice import voice_python, child_options
from voice_setup import probe, compatible
from voice_assets import find_model, bundled_archive

modules=['tkinter','playwright','pyautogui','PIL','pyperclip','pywinauto']
audio={}
try:
    python=voice_python()
    info=probe(python)
    audio={'runtime':'interfaz (instalación anterior o voz sin preparar)' if python==sys.executable else '.venv-voz independiente',
           'python':'.'.join(map(str,info['version'])),'bits':info['bits'],'platform':info['platform'],
           'compatible_windows_voice_runtime':compatible(info)}
    code="import importlib.util,json; print(json.dumps({n:importlib.util.find_spec(n) is not None for n in ['vosk','sounddevice','winrt']}))"
    result=subprocess.run([python,'-I','-c',code],capture_output=True,text=True,encoding='utf-8',timeout=12,**child_options())
    if result.returncode==0:audio['modules_in_voice_python']=json.loads(result.stdout)
    else:audio['error']='No se pudo comprobar la presencia de módulos en el Python de voz.'
except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
    audio['error']='No se pudo comprobar el entorno de voz. Ejecuta DIAGNOSTICO-VOZ.cmd para ver los intérpretes disponibles.'
audio['model_detected_automatically']=find_model() is not None
audio['bundled_model_available']=bundled_archive().is_file()
print(json.dumps({'app':'Nexo PC 0.6.0','python':platform.python_version(),
 'python_supported':sys.version_info>=(3,11),'platform':platform.system(),
 'windows_dpapi_expected':platform.system()=='Windows','architecture':platform.machine(),
 'modules_in_ui_python':{name:importlib.util.find_spec(name) is not None for name in modules},'optional_voice':audio,
 'academic':{'local_panel_available':importlib.util.find_spec('academic') is not None,'word_native_requires_windows':True,'word_native_verified_on_this_pc':False},
 'notes':['Word nativo requiere una prueba separada sobre una copia; este diagnóstico no se conecta a Word.',
          'La presencia de un paquete no demuestra que funcione.',
          'La voz se comprueba en su propio Python, no en el de la interfaz.',
          'Este diagnóstico no realiza llamadas API, no controla el escritorio, no abre el micrófono ni reproduce audio.']},ensure_ascii=False,indent=2))
