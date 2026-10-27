"""Build a clean, downloadable Windows runtime ZIP for Nexo Tesis 0.4.1-dev.

Offline, no installs. The runtime file list comes from the published 0.4.0 package
so the new build cannot accidentally include tests, caches, reports or credentials.
Run from anywhere:  python3 tools/empaquetar_tesis.py
"""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'nexo-tesis'
BASE = ROOT / 'releases' / 'nexo-tesis-v0.4.0-windows.zip'
OUT = ROOT / 'releases' / 'nexo-tesis-v0.4.1-dev-windows.zip'
PREFIX = 'Nexo-Tesis-0.4.1-dev/'

NOTICE = '''# Nexo Tesis 0.4.1-dev · build de DESARROLLO, listo para usar

**Esto no es una release publicada ni una versión validada con Microsoft.**
Es el código de Nexo Tesis 0.4.0 con la corrección local de continuidad de
Microsoft 365 Copilot aplicada. Se construyó sin red y sin instalar dependencias.

**Inicio rápido:** descomprime TODO el ZIP en una carpeta vacía y haz doble clic
en `INICIAR-TESIS.cmd`. El lanzador busca Python, comprueba la integridad del
paquete y abre la app. Requisito único: Python 3.11+ con Tkinter y SQLite (el
instalador de python.org ya los incluye). No se instala ni modifica nada.
`VERIFICAR.cmd` hace solo la comprobación; `LEER-PRIMERO.txt` resume estos pasos.
Las librerías `websocket` y `pypdf` ya vienen incluidas: no hay que instalar nada.

- Corregido: hilo persistente por defecto, sin rotación a los 40 turnos,
  conservación de IDs ante errores/reanudaciones, identidad de cuenta estable
  (oid/tid), cabecera de afinidad aislada para A/B y mensajes incrementales
  solo después de que TÚ verifiques la continuidad.
- Corregido: al elegir **Copilot365 ya no se pide API key**. El campo desaparece,
  «Guardar cuenta» inicia la conexión a tu sesión de M365 y «Guardar y usar»
  ofrece «Conectar escritorio M365» si aún no hay cuenta. Copilot365 no es una
  API: usa TU sesión, sin pegar claves, tokens ni URLs. Ver LEER-PRIMERO.txt.
- Corregido: «La respuesta no cumple el formato académico» ya no se produce
  cuando un modelo de chat (Copilot365) envuelve un JSON válido en texto o en
  un bloque ```json. Se valida un único objeto completo, sin llamada de
  reparación; el aviso indica ahora el motivo exacto sin mostrar la respuesta.
  Las instrucciones de tarea y de hilo incremental comparten el mismo contrato.
- Auditoría de robustez: configuración concurrente con bloqueo e instantánea,
  recuperación ante `config.json` dañado, ids `F#`/`D#` monótonos, tolerancia a
  extracciones y proyectos antiguos, expiración de Copilot robusta, bookkeeping
  de rutas que no pierde respuestas, versión única y comprobación previa de la
  carpeta de datos. Detalle: `contexto/AUDITORIA-ROBUSTEZ.md` en el repo.
- Corregido el error real «La respuesta no cumple el formato académico» en
  apartados largos: límites unificados en `limits.py` (borrador 20 000
  caracteres), recorte visible en vez de rechazo, normalización de etiquetas,
  alias en español y fuentes irregulares, y prompt que informa del límite.
  También se curan automáticamente el 404 de modelo Gemini obsoleto y el 400
  por `response_format`, con una sola repetición segura en cada caso.
- Pruebas locales: 366 superadas / 2 omitidas con fixtures sintéticas.
- **NO verificado**: sesión real de Copilot, recuerdo del servidor, Word COM,
  DPAPI, PowerShell de Windows ni la interfaz Tk en este entorno.
- La cabecera `X-RoutingParameter-SessionKey` es evidencia de terceros sin
  confirmar. Puedes activarla/desactivarla en «Hilo Copilot» para comparar.

Para probar: descomprime en una carpeta vacía y ejecuta `INICIAR-TESIS.cmd`
(Python 3.11+ con Tkinter). Usa un proyecto de prueba SIN datos personales y
sigue la «Prueba de aceptación real» de `CONTINUIDAD-COPILOT.md`. No pegues
tokens ni URLs autenticadas; Nexo guarda su configuración en `~/.nexo-tesis`.

Mantén este paquete en un lugar privado: el código incluye el piloto académico
con institución y centro educativo.

---

'''

FORBIDDEN_PREFIXES = ('tests/', 'reports/', '__pycache__/', 'copilot-login/', 'models/')
FORBIDDEN_NAMES = ('.gitignore', '.env', 'config.json', 'preferences.json',
                   'projects.sqlite3', 'SHA256SUMS.txt')
# Conveniencias de "listo para usar" añadidas en 0.4.1-dev.
READY_EXTRAS = ('LEER-PRIMERO.txt', 'VERIFICAR.cmd', 'verificar_instalacion.py', 'version.py', 'limits.py')


def runtime_paths():
    with zipfile.ZipFile(BASE) as z:
        entries = {n.split('/', 1)[1] for n in z.namelist() if not n.endswith('/')}
    entries.discard('SHA256SUMS.txt')
    entries.update(READY_EXTRAS)
    for rel in entries:
        assert not rel.startswith(FORBIDDEN_PREFIXES), rel
        assert Path(rel).name not in FORBIDDEN_NAMES, rel
        assert not rel.endswith(('.pyc', '.pyo', '.log', '.db')), rel
        assert (SRC / rel).is_file(), 'Falta en el código actual: ' + rel
    return sorted(entries)


def build():
    entries = {}
    for rel in runtime_paths():
        data = (SRC / rel).read_bytes()
        if rel == 'README.md':
            data = NOTICE.encode('utf-8') + data
        entries[rel] = data
    # Metadata and the implementation report travel with the runtime build.
    entries['VERSION.json'] = (SRC / 'VERSION.json').read_bytes()
    entries['CONTINUIDAD-COPILOT.md'] = (
        ROOT / 'contexto' / 'CONTINUIDAD-COPILOT-IMPLEMENTACION.md').read_bytes()
    entries['INCIDENCIA-FORMATO-BORRADOR.md'] = (
        ROOT / 'contexto' / 'INCIDENCIA-FORMATO-BORRADOR.md').read_bytes()
    manifest = ''.join(
        hashlib.sha256(entries[rel]).hexdigest() + '  ' + rel + '\n'
        for rel in sorted(entries))
    entries['SHA256SUMS.txt'] = manifest.encode('utf-8')

    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in sorted(entries):
            z.writestr(PREFIX + rel, entries[rel])

    with zipfile.ZipFile(OUT) as z:
        assert z.testzip() is None
        for rel, data in entries.items():
            assert z.read(PREFIX + rel) == data, rel
    report = {
        'file': str(OUT), 'prefix': PREFIX.rstrip('/'),
        'files': len(entries), 'bytes': OUT.stat().st_size,
        'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
        'source_equality_checked': True, 'crc_checked': True,
        'runtime_only': True, 'network_used': False,
        'status': 'development build; NOT a verified release; remote Copilot continuity untested',
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    build()
