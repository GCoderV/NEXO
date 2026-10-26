"""Offline self-check for the packaged Windows app. No network, no credentials.

Verifies the internal SHA256SUMS.txt, that every runtime module imports, and that
Python/Tk/SQLite are usable. Called by INICIAR-TESIS.cmd and VERIFICAR.cmd.
"""
import hashlib
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ('agent', 'autonomy', 'bibliography', 'config', 'context_policy',
        'conversation_state', 'copilot_metadata', 'copilot_socket', 'guide_rules',
        'materials', 'native_material', 'project_store', 'prompt_policy', 'providers',
        'routing', 'secrets_store', 'word_bridge', 'word_layout', 'pypdf', 'websocket')
UI = ('app', 'material_dialog', 'settings_dialog', 'word_layout_dialog')


def main():
    problems = []
    print('Nexo Tesis 0.4.1-dev - comprobacion local (sin red)')
    print('Python:', sys.version.split()[0])
    if sys.version_info < (3, 11):
        problems.append('Se requiere Python 3.11 o superior.')

    manifest = ROOT / 'SHA256SUMS.txt'
    count = 0
    if not manifest.is_file():
        problems.append('Falta SHA256SUMS.txt; el paquete podria estar incompleto.')
    else:
        for line in manifest.read_text('utf-8').splitlines():
            if '  ' not in line:
                continue
            expected, name = line.split('  ', 1)
            path = (ROOT / name).resolve()
            if (not path.is_relative_to(ROOT) or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                problems.append('Archivo alterado o ausente: ' + name)
            count += 1
    print('Archivos comprobados:', count)

    for name in CORE:
        try:
            importlib.import_module(name)
        except Exception as e:
            problems.append('No se pudo importar ' + name + ': ' + type(e).__name__ + ' ' + str(e)[:100])
    print('Modulos basicos:', len(CORE))

    try:
        import tkinter
        print('Tkinter: disponible (Tk ' + str(tkinter.TkVersion) + ')')
    except Exception as e:
        problems.append('Falta Tkinter / Tcl-Tk: ' + str(e)[:100])
    else:
        for name in UI:
            try:
                importlib.import_module(name)
            except Exception as e:
                problems.append('No se pudo importar ' + name + ': ' + type(e).__name__ + ' ' + str(e)[:100])
        print('Modulos de interfaz:', len(UI))

    try:
        import sqlite3
        print('SQLite:', sqlite3.sqlite_version)
    except Exception as e:
        problems.append('Falta SQLite: ' + str(e)[:100])

    if problems:
        print('')
        print('PROBLEMAS ENCONTRADOS:')
        for item in problems:
            print(' - ' + item)
        print('')
        print('No se iniciara la aplicacion. Revisa lo anterior; no se conecto a ningun servicio.')
        return 1
    print('')
    print('Todo correcto. No se leyeron claves ni se envio nada a Internet.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
