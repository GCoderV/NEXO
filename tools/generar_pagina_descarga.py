"""Build the standalone download page with the ZIP embedded (no server, no GitHub).

Run: python3 tools/generar_pagina_descarga.py
Writes descarga/descargar-nexo-tesis.html and a copy in ~/descarga/.
The browser verifies SHA-256 locally before offering the download.
"""
import base64
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / 'releases' / 'nexo-tesis-v0.4.1-dev-windows.zip'
OUT = ROOT / 'descarga' / 'descargar-nexo-tesis.html'
MIRROR = Path.home() / 'descarga'

CSS = """
*{box-sizing:border-box}body{margin:0;font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#0f1420;color:#e8edf7}
main{max-width:760px;margin:0 auto;padding:44px 22px 70px}
h1{font-size:29px;margin:0 0 6px;color:#fff}h2{font-size:18px;margin:32px 0 8px;color:#fff}
p{margin:10px 0}.sub{color:#9fb0cc;margin-top:0}
.btn{display:inline-block;margin:22px 0 6px;padding:16px 30px;border-radius:12px;background:#3b82f6;color:#fff;text-decoration:none;font-weight:700;font-size:18px;cursor:pointer;border:0}
.btn:hover{background:#2563eb}.btn2{display:inline-block;margin:0 0 6px 12px;padding:16px 20px;border-radius:12px;background:#243049;color:#cfe0ff;text-decoration:none;font-weight:600;font-size:15px;cursor:pointer;border:0}
.meta{color:#9fb0cc;font-size:14px}code{background:#1b2436;padding:2px 6px;border-radius:5px;word-break:break-all;color:#a5d6ff;font-size:12.5px}
ol{padding-left:22px}li{margin:8px 0}
.warn{margin-top:28px;padding:15px 18px;border-left:4px solid #f59e0b;background:#2a2416;border-radius:8px;font-size:14.5px}
.box{margin-top:26px;padding:16px 18px;background:#161f31;border:1px solid #26334d;border-radius:10px;font-size:14.5px}
.news{margin-top:24px;padding:16px 18px;border-left:4px solid #38bdf8;background:#122437;border-radius:8px;font-size:14.5px}
.ok{color:#6ee7a8;font-weight:600}
textarea{width:100%;height:120px;background:#0b1120;color:#9fb0cc;border:1px solid #26334d;border-radius:8px;font-family:monospace;font-size:11px}
details{margin-top:26px}summary{cursor:pointer;color:#cfe0ff}
"""

BODY = """<body><main>
<h1>Nexo Tesis 0.4.1-dev · {build}</h1>
<p class="sub">Build de desarrollo. Este archivo <strong>contiene el ZIP completo</strong>: no necesita servidor, proxy ni GitHub.</p>

<a id="raw" class="btn" download="Nexo-Tesis-0.4.1-dev-windows.zip" href="data:application/zip;base64,{b64}">⬇ Descargar el ZIP</a>
<button class="btn2" id="blob" type="button">Descarga alternativa</button>
<p class="meta">{size} bytes · {files} archivos · <span id="hash">verificando integridad…</span></p>
<p class="meta">SHA-256 esperado: <code>{sha}</code></p>

<div class="news"><strong>Novedad de esta copia ({build}):</strong> <strong>un proyecto nuevo YA NO asume nada del proyecto anterior.</strong> Al crear o abrir otro proyecto se borran el recibo del agente, el apartado seleccionado, los límites del modo agente, los permisos de búsqueda, los consentimientos y el texto pendiente: cada proyecto empieza verdaderamente en blanco (los datos guardados del proyecto anterior se conservan al volver a abrirlo). Esto corrige el caso en que el bot parecía seguir trabajando con la universidad, población o método de la tesis previa. También siguen corregidos: el agente continuo <strong>no rellena Conclusiones sin datos</strong> (pregunta por el corpus; <em>fase6-3</em>) y Copilot <strong>no se cierra</strong> tras capturar la sesión (<em>fase6-2</em>) —déjalo abierto mientras uses la cuenta—. Se mantienen el agente continuo sin cuota de pasos, la búsqueda de fuentes en Crossref y la pestaña <strong>Documento</strong> (Markdown, HTML y DOCX sin Word ni internet). <strong>Para confirmar que abres esta copia:</strong> ejecuta <code>VERIFICAR.cmd</code> y comprueba que dice <code>({build})</code> y las siete líneas <code>OK</code>, incluidas <em>«Datos empiricos: OK»</em> y <em>«Aislamiento de proyectos: OK»</em>. Si no aparecen, estás usando una carpeta antigua.</div>

<div class="box">
<strong>Si el botón no descarga</strong> (algunos visores bloquean descargas):
<ul style="margin:8px 0 0;padding-left:20px">
<li>Prueba el botón <em>Descarga alternativa</em>.</li>
<li>O haz clic derecho sobre <em>Descargar el ZIP</em> → <em>Guardar enlace como…</em>.</li>
<li>O abre <code>descargar-nexo-tesis.html</code> directamente en tu navegador (doble clic) y pulsa el botón.</li>
</ul>
</div>

<h2>Para usarlo en Windows</h2>
<ol>
<li>Descomprime <strong>todo</strong> el contenido en una carpeta vacía (no lo ejecutes desde dentro del ZIP).</li>
<li>Haz doble clic en <code>INICIAR-TESIS.cmd</code>: se autoverifica y abre la aplicación.</li>
<li>Requiere Python 3.11+ con Tkinter y SQLite (el instalador de python.org ya los incluye). <span class="ok">No hay que instalar dependencias</span>: <code>websocket</code> y <code>pypdf</code> van incluidos.</li>
<li>En la pestaña <strong>Documento</strong> pulsa <em>Generar documento completo</em> para obtener .md, .html y .docx, o <em>Completar lo que falta</em> para lanzar el agente.</li>
</ol>

<div class="warn"><strong>Importante:</strong> es un build de desarrollo, no una release publicada ni una versión validada con Microsoft. La continuidad real de Copilot, Word COM, DPAPI y la apertura del DOCX en Word aún no se han comprobado en este entorno. El DOCX es OOXML estándar validado estructuralmente; verifícalo en tu Word. Prueba primero con un proyecto sin datos personales. No pegues tokens ni URLs autenticadas.</div>

<details><summary>Último recurso: copiar el ZIP en base64</summary>
<p class="meta">Si ningún botón funciona, copia este texto y pégalo en un decodificador base64 guardando la salida como <code>Nexo-Tesis-0.4.1-dev-windows.zip</code>.</p>
<textarea id="b64text" readonly></textarea>
<button class="btn2" id="copy" type="button">Copiar base64</button>
</details>

<script>
(function(){{
  var a=document.getElementById('raw');
  var href=a.getAttribute('href');
  var b64=href.slice(href.indexOf(',')+1);
  var bin,bytes,i;
  try{{
    bin=atob(b64);
    bytes=new Uint8Array(bin.length);
    for(i=0;i<bin.length;i++)bytes[i]=bin.charCodeAt(i);
  }}catch(e){{document.getElementById('hash').textContent='error al decodificar';return;}}
  document.getElementById('b64text').value=b64;
  if(window.crypto&&window.crypto.subtle){{
    window.crypto.subtle.digest('SHA-256',bytes).then(function(buf){{
      var h=Array.prototype.map.call(new Uint8Array(buf),function(x){{return ('0'+x.toString(16)).slice(-2);}}).join('');
      document.getElementById('hash').innerHTML = (h==='{sha}') ? '<span class="ok">✓ integridad verificada en tu navegador</span>' : '<span style="color:#f87171">✗ hash distinto</span>';
    }}).catch(function(){{}});
  }}
  document.getElementById('blob').addEventListener('click',function(){{
    var url=URL.createObjectURL(new Blob([bytes],{{type:'application/zip'}}));
    var t=document.createElement('a');t.href=url;t.download='Nexo-Tesis-0.4.1-dev-windows.zip';document.body.appendChild(t);t.click();t.remove();
    setTimeout(function(){{URL.revokeObjectURL(url);}},60000);
  }});
  document.getElementById('copy').addEventListener('click',function(){{
    var ta=document.getElementById('b64text');ta.select();
    try{{document.execCommand('copy');this.textContent='Copiado';}}catch(e){{this.textContent='Selecciona y copia manualmente';}}
  }});
}})();
</script>
</main></body></html>"""


def build():
    import zipfile
    data = ZIP.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    with zipfile.ZipFile(ZIP) as z:
        files = len(z.namelist())
    page = ('<!doctype html>\n<html lang="es"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            '<title>Descarga directa · Nexo Tesis 0.4.1-dev</title>\n'
            '<style>' + CSS + '</style>\n</head>\n' +
            BODY.format(build='fase6-4', b64=base64.b64encode(data).decode('ascii'),
                        size='{:,}'.format(len(data)).replace(',', '.'), files=files, sha=sha))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, 'utf-8')
    shutil.copy2(ZIP, OUT.parent / ZIP.name)
    MIRROR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT, MIRROR / OUT.name)
    shutil.copy2(ZIP, MIRROR / ZIP.name)
    return {'page': str(OUT), 'page_bytes': OUT.stat().st_size,
            'zip_bytes': len(data), 'zip_files': files, 'sha256': sha}


if __name__ == '__main__':
    import json
    print(json.dumps(build(), ensure_ascii=False, indent=2))
