"""Offline self-check for the packaged Windows app. No network, no credentials.

Verifies the internal SHA256SUMS.txt, that every runtime module imports, and that
Python/Tk/SQLite are usable. Called by INICIAR-TESIS.cmd and VERIFICAR.cmd.
"""
import hashlib
import importlib
import sys
from pathlib import Path
from version import VERSION, BUILD

ROOT = Path(__file__).resolve().parent
CORE = ('agent', 'autonomy', 'bibliography', 'config', 'context_policy',
        'conversation_state', 'copilot_metadata', 'copilot_socket', 'guide_rules',
        'materials', 'native_material', 'project_store', 'prompt_policy', 'providers',
        'document', 'agent_tools', 'diagnostics', 'process_guard',
        'project_state', 'gates', 'research', 'run_loop', 'empirical',
        'routing', 'secrets_store', 'word_bridge', 'word_layout', 'pypdf', 'websocket')
UI = ('app', 'material_dialog', 'settings_dialog', 'word_layout_dialog')


def check_data_dir():
    """Preflight the user data folder WITHOUT reading keys or projects.

    A read-only ~/.nexo-tesis makes every save fail at runtime with an opaque
    error; detecting it here gives an actionable message before the app opens.
    """
    import os
    path = Path.home() / '.nexo-tesis'
    label = '~/.nexo-tesis'
    if not path.exists():
        print('Datos: ' + label + ' se creara al abrir Nexo (no se crea ahora).')
        return []
    if not os.access(path, os.W_OK):
        return ['Sin permiso de escritura en ' + label + ': Nexo no podra guardar proyectos ni configuracion. Revisa los permisos de tu carpeta de usuario.']
    print('Datos: carpeta accesible; no se leyeron claves ni proyectos.')
    return []


def check_long_draft():
    """Functional proof that THIS copy accepts the user's long task reply.

    The recurring "La respuesta no cumple el formato académico" was caused by a
    10000-character cap in an older build. Running this at startup tells the user
    immediately whether they opened the corrected ZIP or a stale folder.
    """
    import json
    from limits import MAX_DRAFT_CHARS
    from agent import unpack
    text = ('### Marco teórico\n\n'
            + 'Párrafo de prueba con acentos, 3.º de secundaria y\n\n'
            * 260)
    raw = json.dumps({'text': text, 'sources': [],
                      'reply': 'Borrador de prueba, sin fuentes.'}, ensure_ascii=False)
    assert len(json.loads(raw)['text']) > 10000
    result = unpack(raw, {'section': 'marco_teorico'})
    drafts = result.get('drafts', [])
    if (len(drafts) != 1 or drafts[0]['section'] != 'marco_teorico'
            or len(drafts[0]['text']) <= 10000):
        return ['Esta copia sigue rechazando borradores largos: descarga el ZIP nuevo y descomprímelo en una carpeta vacía.']
    return []


def check_research():
    """Functional proof that THIS copy executes long searches and keeps planning.

    The dead end was caused by a 250-character cap on `search.query` (which
    rejected the model's boolean query before Crossref) and by a planner that
    dropped optional sections. No network is used here: only normalization,
    validation and planning are exercised.
    """
    import json
    from agent import unpack
    from autonomy import plan
    from bibliography import normalize_queries
    query = ('"cooperative learning" AND "role play" AND "English as a foreign language" '
             'AND ("secondary education" OR "high school") AND ("speaking" OR "oral production" '
             'OR "oral communication" OR "speaking skills" OR "English speaking") AND '
             '("academic achievement" OR "learning outcomes" OR "language learning" OR '
             '"speaking performance" OR "language proficiency") AND '
             '("2020" OR "2021" OR "2022" OR "2023" OR "2024" OR "2025")')
    queries = normalize_queries(query)
    if not (2 <= len(queries) <= 3) or any(not 2 <= len(q) <= 250 for q in queries):
        return ['Esta copia no divide las consultas largas: descarga el ZIP nuevo.']
    result = unpack(json.dumps({'reply': 'ok', 'search': {'query': query,
                    'reason': 'Antecedentes'}}, ensure_ascii=False))
    if result['search']['query'] != query:
        return ['Esta copia sigue rechazando consultas bibliograficas largas.']
    project = {'topic': 'Tema', 'topic_pending': False, 'facts': {}, 'drafts': {},
               'sources': [], 'data_ready': False, 'materials': [],
               'format_profile': None, 'guide': None}
    tasks, _notice = plan(project, True)
    if not {'cronograma', 'presupuesto', 'anexos'} <= {t['section'] for t in tasks}:
        return ['Esta copia sigue declarando que no hay tareas con apartados pendientes.']
    return []


def check_loop():
    """Functional proof of the bounded tool loop, offline, with a stub model.

    If the user opened an older folder, `Agent.turn(..., loop=...)` or the new
    modules would fail. This exercises inspect -> write -> export -> finalize
    and validates the generated OOXML package without Word or network.
    """
    import io
    import json
    import tempfile
    import zipfile
    from pathlib import Path
    from agent import Agent
    from project_store import ProjectStore

    def response(text, calls, done=False):
        return json.dumps({'reply': text, 'tool_calls': [
            {'name': name, 'arguments': args} for name, args in calls], 'done': done},
            ensure_ascii=False)

    class StubAPI:
        provider = 'verificacion-local'
        model = 'sin-red'
        key = ''
        endpoint = ''
        last_usage = {}

        def __init__(self):
            self.requests = []
            self.instructions = ''

        def request(self, conversation, declarations):
            self.requests.append(conversation)
            step = len(self.requests)
            if step == 1:
                raw = response('Reviso', [('ver_documento', {})])
            elif step == 2:
                raw = response('Escribo', [('escribir_apartado', {
                    'section': 'delimitacion', 'text': 'Borrador de comprobacion.', 'sources': []})])
            else:
                raw = response('Genero', [('generar_documento', {}),
                                          ('finalizar', {'motivo': 'Comprobacion completada'})], True)
            return {}, raw, []

    with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as out:
        store = ProjectStore(data)
        project = store.create('Tema de comprobacion local')
        api = StubAPI()
        result = Agent(store, api, lambda *a: True, lambda q: []).turn(
            project['id'], 'Comprueba el bucle', origin='usuario',
            loop={'goal': 'Comprueba el bucle', 'max_passes': 4,
                  'allow_export': True, 'export_dir': out})
        if len(api.requests) != 3:
            return ['El bucle del agente no completo sus tres pasos acotados.']
        if 'Borrador de comprobacion' not in result.get('drafts', {}).get('delimitacion', {}).get('text', ''):
            return ['Las herramientas del agente no pudieron escribir un apartado.']
        if result.get('last_loop', {}).get('stopped') != 'finalizado':
            return ['El agente no emitio un recibo de parada verificable.']
        files = sorted(Path(out).glob('*.docx'))
        if not files:
            return ['No se genero el documento DOCX completo.']
        with zipfile.ZipFile(io.BytesIO(files[0].read_bytes())) as z:
            if z.testzip() is not None or 'word/document.xml' not in z.namelist():
                return ['El DOCX generado no es un paquete OOXML valido.']
    return []


def check_fase6():
    """Offline proof of the Fase 1–6 core: state, gates, research, continuous loop."""
    import json
    import tempfile
    from agent import Agent
    from project_store import ProjectStore
    import project_state as ps
    import gates
    import research
    import run_loop

    with tempfile.TemporaryDirectory() as data:
        store = ProjectStore(data)
        p = store.create('Tema de comprobacion local')
        from project_store import set_fact
        # set_fact invalidates drafts; do it BEFORE seeding them so the
        # derived status map reflects content, not a stale review flag.
        set_fact(p, 'datos', 'Corpus de prueba: 68%')
        p['data_ready'] = True
        p['sources'] = [{'id': 'F1', 'title': 'Obra', 'doi': '10.1/x',
                         'url': 'https://doi.org/10.1/x', 'status': 'metadatos'}]
        for key in ('delimitacion', 'problematica', 'pregunta', 'objetivos',
                    'justificacion', 'marco_teorico', 'metodologia', 'instrumentos',
                    'plan_accion', 'analisis_previsto', 'cronograma', 'presupuesto',
                    'anexos', 'referencias'):
            p['drafts'][key] = {'text': 'Contenido de comprobacion [F1]. ' * 6,
                                'status': 'borrador', 'sources': ['F1']}
        verification = ps.verify(p)
        if not verification['done']:
            return ['La verificacion determinista no reconocio un proyecto completo: ' +
                    str(verification['missing'][:3]) + str(verification['blocked'][:3])]
        hard = gates.evaluate(p)['hard']
        if hard:
            return ['Las puertas duras bloquearon un proyecto limpio: ' + str(hard[:2])]
        merged = research.dedupe([
            {'title': 'Paper', 'doi': '10.1/a', 'origin': 'Crossref'},
            {'title': 'Paper', 'doi': '10.1/A', 'origin': 'OpenAlex'}])
        if len(merged) != 1 or len(merged[0]['verified_by']) != 2:
            return ['La deduplicacion con proveniencia no funciona.']
        offline = research.discover(p, queries=['role play'], allow_network=False,
                                    providers=[('Crossref', research._crossref)])
        if offline['items'] or not offline['errors']:
            return ['La investigacion sin red no se contuvo correctamente.']
        profile = run_loop.RunProfile(max_passes=None, allow_research=False,
                                      auto_research=False, allow_export=False)
        if profile.max_passes is not None or 'Sin cuota' not in profile.describe():
            return ['El modo continuo tiene una cuota de pasos.']

        def response(text, calls):
            return json.dumps({'reply': text, 'tool_calls': [
                {'name': n, 'arguments': a} for n, a in calls], 'done': False})

        class StubAPI:
            provider = 'verificacion-local'
            model = 'sin-red'
            key = ''
            endpoint = ''
            last_usage = {}
            def __init__(self):
                self.requests = []
                self.instructions = ''
            def request(self, conversation, declarations):
                self.requests.append(conversation)
                return {}, response('Verifico', [('verificar', {})]), []

        store.save(p)
        api = StubAPI()
        result = Agent(store, api).turn(p['id'], 'Termina', origin='usuario',
                                        loop=profile.loop_config())
        if result.get('last_loop', {}).get('stopped') != 'trabajo_completado':
            return ['El bucle continuo no se detuvo por verificacion: ' +
                    str(result.get('last_loop', {}).get('stopped'))]
    return []


def check_copilot_stays_open():
    """Offline proof: a captured session is NOT closed by this copy.

    Regression for "luego de capturar la sesión de Copilot el bot cierra
    automáticamente Copilot". Uses a synthetic Popen double; no Windows
    process, browser, credential or network is touched.
    """
    import subprocess
    import process_guard

    class FakeProc:
        def __init__(self):
            self.terminated = False
        def poll(self): return None
        def terminate(self): self.terminated = True
        def wait(self, timeout=None): return 0
        def kill(self): self.terminated = True

    real = subprocess.Popen
    issues = []
    try:
        ok_proc = FakeProc()
        subprocess.Popen = lambda *a, **k: ok_proc
        def launch():
            subprocess.Popen(['M365Copilot.exe'])
            return 9222
        process_guard.guarded_capture(launch, lambda port: 'sesion-sintetica')
        if ok_proc.terminated:
            issues.append('Esta copia CIERRA Copilot tras capturar la sesion: '
                          'descarga el ZIP corregido y descomprimelo en una carpeta vacia.')
        if process_guard.count():
            issues.append('El seguimiento de procesos no se libero tras la captura.')

        bad_proc = FakeProc()
        subprocess.Popen = lambda *a, **k: bad_proc
        def fail(port):
            raise ValueError('cancelado')
        try:
            process_guard.guarded_capture(launch, fail)
        except ValueError:
            pass
        if not bad_proc.terminated:
            issues.append('Un intento fallido deja ventanas huerfanas abiertas.')

        dialog = (ROOT / 'settings_dialog.py').read_text('utf-8')
        if 'process_guard.close_all()' in dialog:
            issues.append('El dialogo aun cierra Copilot al guardar o al cerrar la ventana.')
    finally:
        process_guard.stop_tracking()
        with process_guard._lock:
            process_guard._tracked.clear()
        process_guard._original = None
        subprocess.Popen = real
    return issues


def check_empirical_boundary():
    """Offline proof: no invented results and no filler conclusions.

    Reproduces the reported turn ("intento completar otro apartado pendiente no
    basado en hallazgos del estudio") with synthetic projects. Verifies that
    the host asks the user for a corpus instead of looping on blocked writes.
    """
    import tempfile
    import empirical
    import gates
    import run_loop
    from project_store import ProjectStore, set_fact

    filler = ('Conclusiones (provisional). Este apartado permanece condicionado '
              'a la obtención y análisis de datos del estudio. En la fase actual '
              'no existen evidencias empíricas que permitan establecer '
              'conclusiones. Toda afirmación permanece con apoyo pendiente.')
    issues = []
    if not empirical.placeholder(filler):
        issues.append('No se detecta el texto provisional de Conclusiones.')

    with tempfile.TemporaryDirectory() as data:
        store = ProjectStore(data)
        p = store.create('Tema de comprobacion local')
        p['sources'] = [{'id': 'F1', 'title': 'Obra', 'doi': '10.1/x',
                         'url': 'https://doi.org/10.1/x', 'status': 'metadatos'}]
        set_fact(p, 'datos', 'Corpus de prueba: 68%')
        p['data_ready'] = True
        for key in ('delimitacion', 'problematica', 'pregunta', 'objetivos',
                    'justificacion', 'marco_teorico', 'metodologia',
                    'instrumentos', 'plan_accion', 'analisis_previsto',
                    'cronograma', 'presupuesto', 'anexos', 'referencias'):
            p['drafts'][key] = {'text': 'Contenido de comprobacion [F1]. ' * 6,
                                'status': 'borrador', 'sources': ['F1']}
        p['drafts']['conclusiones'] = {'text': filler, 'status': 'borrador',
                                       'sources': []}
        if not any('provisional' in x for x in gates.evaluate(p)['hard']):
            issues.append('Las puertas aceptaron Conclusiones provisionales.')
        del p['drafts']['conclusiones']

        p['data_ready'] = False
        p['facts'].pop('datos', None)
        question = empirical.data_question(p)
        if not question or 'corpus' not in question.lower():
            issues.append('El agente no formula la pregunta sobre el corpus.')
        decision = run_loop.evaluate(
            p, {'passes': 1, 'stalls': 0},
            run_loop.RunProfile(max_seconds=600, hard_fuse=40))
        if decision['stop'] != 'pregunta':
            issues.append('El bucle no se detiene a preguntar al usuario: ' +
                          str(decision['stop']))

        p['facts']['tipo_trabajo'] = {'value': 'Anteproyecto de investigacion'}
        if empirical.data_question(p) is not None:
            issues.append('Un anteproyecto no debe exigir resultados empiricos.')
    return issues


def main():
    problems = []
    print(f'Nexo Tesis {VERSION} ({BUILD}) - comprobacion local (sin red)')
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

    problems += check_data_dir()
    try:
        draft_issues = check_long_draft()
    except Exception as e:
        problems.append('No se pudo comprobar el validador de borradores: ' + type(e).__name__ + ' ' + str(e)[:100])
    else:
        if draft_issues:
            problems += draft_issues
        else:
            from limits import MAX_DRAFT_CHARS
            print('Borradores largos: OK (hasta ' + str(MAX_DRAFT_CHARS) + ' caracteres).')
    try:
        research_issues = check_research()
    except Exception as e:
        problems.append('No se pudo comprobar busqueda y plan: ' + type(e).__name__ + ' ' + str(e)[:100])
    else:
        if research_issues:
            problems += research_issues
        else:
            print('Busqueda y plan: OK (consultas largas + apartados pendientes).')
    try:
        loop_issues = check_loop()
    except Exception as e:
        problems.append('No se pudo comprobar el agente con herramientas: ' + type(e).__name__ + ' ' + str(e)[:100])
    else:
        if loop_issues:
            problems += loop_issues
        else:
            print('Agente con herramientas: OK (inspeccionar, escribir, exportar, recibo).')
    try:
        fase6_issues = check_fase6()
    except Exception as e:
        problems.append('No se pudo comprobar el nucleo de las fases 1-6: ' + type(e).__name__ + ' ' + str(e)[:100])
    else:
        if fase6_issues:
            problems += fase6_issues
        else:
            print('Fases 1-6: OK (estado, puertas, investigacion, bucle continuo sin cuota).')
    try:
        copilot_issues = check_copilot_stays_open()
    except Exception as e:
        problems.append('No se pudo comprobar que Copilot sigue abierto: ' + type(e).__name__ + ' ' + str(e)[:100])
    else:
        if copilot_issues:
            problems += copilot_issues
        else:
            print('Sesion Copilot: OK (no se cierra tras capturar; solo se limpian fallos).')
    try:
        empirical_issues = check_empirical_boundary()
    except Exception as e:
        problems.append('No se pudo comprobar la frontera de datos empiricos: ' + type(e).__name__ + ' ' + str(e)[:100])
    else:
        if empirical_issues:
            problems += empirical_issues
        else:
            print('Datos empiricos: OK (pregunta al usuario; no rellena Conclusiones).')
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
