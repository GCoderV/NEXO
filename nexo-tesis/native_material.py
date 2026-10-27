import base64,json,os,subprocess
from pathlib import Path

def read_docx(path):
    if os.name!='nt':raise ValueError('DOCX requiere Microsoft Word de escritorio en Windows.')
    code=Path(__file__).with_name('material_word.ps1').read_text('utf-8')
    encoded=base64.b64encode(code.encode('utf-16-le')).decode('ascii')
    exe=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:r=subprocess.run([str(exe),'-NoProfile','-NonInteractive','-STA','-EncodedCommand',encoded],input=json.dumps({'path':path,'approved':True},ensure_ascii=False).encode('utf-8'),capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:raise ValueError('Lectura agotó el tiempo. Revisa Word: la copia puede seguir abierta. No se reintentó ni se guardó.') from None
    except OSError:raise ValueError('No se pudo iniciar Windows PowerShell para leer el DOCX.') from None
    if r.returncode:raise ValueError('Word no pudo leer el DOCX. Revisa el documento; no se reintentó.')
    try:data=json.loads(r.stdout.decode('utf-8-sig'))
    except (ValueError,UnicodeError):raise ValueError('Word devolvió una respuesta no válida; no se reintentó.') from None
    if not isinstance(data,dict):raise ValueError('Word devolvió datos inesperados; no se reintentó.')
    if data.get('error'):raise ValueError(str(data['error'])[:300])
    # materials.extract indexes these directly; a partial Word reply must not
    # surface as an opaque KeyError in the middle of an import.
    if not isinstance(data.get('segments'),list):data['segments']=[]
    for key in ('total','omitted'):
        if type(data.get(key)) is not int:data[key]=0
    if not isinstance(data.get('warnings'),list):data['warnings']=[]
    return data
