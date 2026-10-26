import base64,json,os,subprocess
from pathlib import Path

def read_docx(path):
    if os.name!='nt':raise ValueError('DOCX requiere Microsoft Word de escritorio en Windows.')
    code=Path(__file__).with_name('material_word.ps1').read_text('utf-8')
    encoded=base64.b64encode(code.encode('utf-16-le')).decode('ascii')
    exe=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:r=subprocess.run([str(exe),'-NoProfile','-NonInteractive','-STA','-EncodedCommand',encoded],input=json.dumps({'path':path,'approved':True},ensure_ascii=False).encode('utf-8'),capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:raise ValueError('Lectura agotó el tiempo. Revisa Word: la copia puede seguir abierta. No se reintentó ni se guardó.') from None
    data=json.loads(r.stdout.decode('utf-8-sig'))
    if 'error' in data:raise ValueError(data['error'])
    return data
