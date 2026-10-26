"""No network, no keys, no project text or personal path output."""
import json, platform, sys, sqlite3, importlib.util
from pathlib import Path
print(json.dumps({'product':'Nexo Tesis','version':'0.1.1','python':platform.python_version(),'python_supported':sys.version_info>=(3,11),'platform':platform.system(),'sqlite_version':sqlite3.sqlite_version,'tkinter_present':importlib.util.find_spec('tkinter') is not None,'word_script_present':Path(__file__).with_name('word_bridge.ps1').exists(),'word_runtime_verified':False,'authenticated_model_verified':False,'notes':['No requiere Nexo PC ni importa sus datos.','No se realizo ninguna llamada de red ni se conecto a Word.','La presencia de componentes no demuestra su funcionamiento nativo.']},ensure_ascii=False,indent=2))
