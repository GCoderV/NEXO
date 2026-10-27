"""Regression tests for the bounded tool-using agent loop and document export.

Synthetic fixtures only. No Word COM, no network, no real M365 Copilot session.
The design follows three ideas seen in open-source academic agents: bounded
passes with an auditable receipt (loopy), one validated write path over a single
project state (dothesis), and hard boundaries + protected sections
(agentic-thesis-writing / academic-writing-toolkit).
"""
import io
import json
import re
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from xml.dom.minidom import parseString

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeAPI, TOPIC_A  # noqa: E402
from project_store import ProjectStore, set_fact  # noqa: E402
from bibliography import add_fragment  # noqa: E402
from agent import Agent, unpack  # noqa: E402
import agent_tools  # noqa: E402
import document  # noqa: E402


def call(name, **args):
    return {'name': name, 'arguments': args}


def loop_reply(text, calls, done=False):
    return json.dumps({'reply': text, 'tool_calls': calls, 'done': done}, ensure_ascii=False)


def services(**kwargs):
    base = {'allow_research': False, 'allow_export': False, 'export_dir': '',
            'origin': 'usuario', 'user_text': '', 'approve_search': None,
            'searcher': lambda q: [], 'producer': 'test'}
    base.update(kwargs)
    return base


class DocumentModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = ProjectStore(self.tmp.name)
        self.p = self.s.create(TOPIC_A)
        self.addCleanup(self.tmp.cleanup)

    def test_custom_section_is_added_and_hidden_without_deleting_the_draft(self):
        made = document.add_extra(self.p, 'Estado de la cuestión', 'marco_teorico')
        self.assertTrue(made['key'].startswith('x-'))
        keys = document.order(self.p)
        self.assertLess(keys.index('marco_teorico'), keys.index(made['key']))
        document.write_section(self.p, made['key'], 'Contenido del apartado nuevo.')
        document.set_visible(self.p, made['key'], False)
        blocks = {label for label, _b, _s in document.section_blocks(self.p)}
        self.assertNotIn('Estado de la cuestión', blocks)
        self.assertIn(made['key'], self.p['drafts'])  # data preserved
        document.set_visible(self.p, made['key'], True)
        self.assertIn('Estado de la cuestión', {l for l, _b, _s in document.section_blocks(self.p)})

    def test_export_writes_three_valid_offline_files(self):
        document.write_section(self.p, 'delimitacion', 'Una delimitación concreta.')
        add_fragment(self.p, 'Obra de prueba', 'Resumen de prueba', 'p. 3')
        with tempfile.TemporaryDirectory() as out:
            info = document.export(self.p, out)
            self.assertEqual(len(info['files']), 3)
            self.assertEqual({Path(f).suffix for f in info['files']}, {'.md', '.html', '.docx'})
            md = (Path(out) / [f for f in info['files'] if f.endswith('.md')][0]).read_text('utf-8')
            self.assertIn('Una delimitación concreta.', md)
            self.assertIn('Obra de prueba', md)
            self.assertIn('Por redactar', md)  # missing sections are explicit, not invented
            data = (Path(out) / [f for f in info['files'] if f.endswith('.docx')][0]).read_bytes()
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                self.assertEqual(z.testzip(), None)
                self.assertIn('word/document.xml', z.namelist())
                for name in z.namelist():
                    parseString(z.read(name))
                self.assertIn('Una delimitación concreta.', z.read('word/document.xml').decode('utf-8'))

    def test_references_are_built_from_registered_sources_only(self):
        self.assertIn('Sin fuentes registradas', document.references(self.p))
        add_fragment(self.p, 'Obra de prueba', 'Resumen', 'p. 1')
        refs = document.references(self.p)
        self.assertIn('[F1]', refs)
        self.assertIn('Obra de prueba', refs)
        self.assertNotIn('10.9999', refs)  # no invented DOI

    def test_write_section_rejects_unknown_citations_and_invents_nothing(self):
        with self.assertRaises(ValueError):
            document.write_section(self.p, 'marco_teorico', 'Según [F99] todo está probado.')
        self.assertNotIn('marco_teorico', self.p['drafts'])

    def test_empirical_sections_need_confirmed_data(self):
        with self.assertRaises(ValueError):
            document.write_section(self.p, 'resultados', 'Se obtuvo un 95% de eficacia.')
        set_fact(self.p, 'datos', 'Corpus real aportado')
        self.p['data_ready'] = True
        document.write_section(self.p, 'resultados', 'Resultados derivados del corpus aportado.')
        self.assertIn('resultados', self.p['drafts'])

    def test_protected_draft_cannot_be_overwritten_by_a_tool(self):
        document.write_section(self.p, 'delimitacion', 'Texto del usuario.')
        self.p['drafts']['delimitacion']['edited_by_user'] = True
        with self.assertRaises(ValueError):
            document.write_section(self.p, 'delimitacion', 'Texto del agente.')
        self.assertEqual(self.p['drafts']['delimitacion']['text'], 'Texto del usuario.')

    def test_surgical_edit_requires_one_exact_anchor_and_keeps_the_rest(self):
        document.write_section(self.p, 'delimitacion', 'Intro.\n\nCuerpo.\n\nCierre.')
        document.patch_section(self.p, 'delimitacion', 'Cuerpo.', '\n\nCuerpo ampliado con evidencia pendiente.',
                               'insert_after')
        text = self.p['drafts']['delimitacion']['text']
        self.assertIn('Intro.', text)
        self.assertIn('Cierre.', text)
        self.assertIn('Cuerpo ampliado', text)
        with self.assertRaises(ValueError):
            document.patch_section(self.p, 'delimitacion', 'No existe', 'x', 'replace')
        document.patch_section(self.p, 'delimitacion', '\n\nCuerpo ampliado con evidencia pendiente.', '', 'remove')
        self.assertNotIn('Cuerpo ampliado', self.p['drafts']['delimitacion']['text'])

    def test_long_tool_text_is_trimmed_with_a_visible_notice(self):
        document.write_section(self.p, 'marco_teorico', 'Párrafo. ' * 4000)
        text = self.p['drafts']['marco_teorico']['text']
        self.assertLessEqual(len(text), 20000)
        self.assertIn('se recortó', text)

    def test_custom_draft_can_be_edited_through_the_store(self):
        made = document.add_extra(self.p, 'Anexo metodológico')
        document.write_section(self.p, made['key'], 'Borrador inicial.')
        self.s.update_draft(self.p, made['key'], 'Edición manual del usuario.')
        self.assertEqual(self.p['drafts'][made['key']]['text'], 'Edición manual del usuario.')


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = ProjectStore(self.tmp.name)
        self.p = self.s.create(TOPIC_A)
        self.addCleanup(self.tmp.cleanup)

    def test_unknown_tool_and_oversized_arguments_are_rejected(self):
        self.assertEqual(agent_tools.validate_calls([call('ver_documento')])[0]['name'], 'ver_documento')
        with self.assertRaises(ValueError):
            agent_tools.validate_calls([call('borrar_todo_el_proyecto')])
        with self.assertRaises(ValueError):
            agent_tools.validate_calls([call('escribir_apartado', section='x', text='a' * 50000)])
        with self.assertRaises(ValueError):
            agent_tools.validate_calls([call('ver_documento')] * 5)

    def test_unpack_tools_mode_rejects_normal_proposal_keys(self):
        parsed = unpack(loop_reply('ok', [call('ver_estado')]), None, tools=True)
        self.assertEqual(parsed['tool_calls'][0]['name'], 'ver_estado')
        with self.assertRaises(ValueError):
            unpack('{"reply":"ok","drafts":[]}', None, tools=True)
        with self.assertRaises(ValueError):
            unpack('{"reply":"ok","tool_calls":[{"name":"finalizar","arguments":{}}]}')

    def test_tool_failure_is_contained_as_data(self):
        row = agent_tools.execute(self.p, call('leer_apartado', section='no-existe'), services())
        self.assertFalse(row['ok'])
        self.assertIn('No se pudo ejecutar', row['summary'])
        self.assertEqual(len(self.p['drafts']), 0)

    def test_search_tool_requires_explicit_research_permission(self):
        denied = agent_tools.execute(self.p, call('buscar_fuentes', query='role play'), services())
        self.assertFalse(denied['ok'])
        called = []

        def finder(q):
            called.append(q)
            return [dict(title='Obra real de metadatos', authors='A', year='2021',
                         doi='10.1/' + q[:8], url='https://doi.org/10.1/x',
                         status='solo metadatos consultados', excerpt='')]
        ok = agent_tools.execute(self.p,
            call('buscar_fuentes', query='"cooperative learning" AND "role play" AND "speaking"'),
            services(allow_research=True, approve_search=lambda *a: True, searcher=finder))
        self.assertTrue(ok['ok'])
        self.assertTrue(called)
        self.assertEqual(len(self.p['sources']), len(called))
        self.assertEqual(ok['data']['added'], ['F1'] if len(called) == 1 else ok['data']['added'])

    def test_export_tool_requires_authorization(self):
        with tempfile.TemporaryDirectory() as out:
            row = agent_tools.execute(self.p, call('generar_documento'), services(export_dir=out))
            self.assertFalse(row['ok'])
            row = agent_tools.execute(self.p, call('generar_documento'),
                                      services(export_dir=out, allow_export=True))
            self.assertTrue(row['ok'])
            self.assertEqual(len(row['data']['files']), 3)

    def test_automatic_steps_cannot_invent_user_facts(self):
        row = agent_tools.execute(self.p, call('registrar_dato', clave='poblacion', valor='999',
                                               evidencia='999'), services(origin='autonomo'))
        self.assertFalse(row['ok'])
        self.assertNotIn('poblacion', self.p['facts'])
        row = agent_tools.execute(self.p, call('registrar_dato', clave='poblacion', valor='24 estudiantes',
                                               evidencia='24 estudiantes'),
                                  services(origin='usuario', user_text='Tengo 24 estudiantes'))
        self.assertTrue(row['ok'])
        self.assertEqual(self.p['facts']['poblacion']['value'], '24 estudiantes')

    def test_question_is_an_approval_boundary(self):
        row = agent_tools.execute(self.p, call('preguntar_usuario', texto='¿Cuál es la población?'), services())
        self.assertEqual(row['stop'], 'pregunta')
        self.assertEqual(self.p['questions'][0]['status'], 'abierta')

    def test_add_edit_hide_and_restore_through_tools(self):
        cfg = services()
        added = agent_tools.execute(self.p, call('anadir_apartado', titulo='Caso piloto'), cfg)
        key = added['data']['key']
        agent_tools.execute(self.p, call('escribir_apartado', section=key, text='Contenido inicial.'), cfg)
        agent_tools.execute(self.p, call('editar_texto', section=key, fragmento='inicial',
                                         nuevo='inicial y ampliado', modo='reemplazar'), cfg)
        self.assertIn('ampliado', self.p['drafts'][key]['text'])
        agent_tools.execute(self.p, call('quitar_apartado', section=key), cfg)
        self.assertFalse(document.outline_key_visible(self.p, key))
        self.assertIn(key, self.p['drafts'])
        agent_tools.execute(self.p, call('restaurar_apartado', section=key), cfg)
        self.assertTrue(document.outline_key_visible(self.p, key))


class LoopExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = ProjectStore(self.tmp.name)
        self.p = self.s.create(TOPIC_A)
        self.stop = threading.Event()
        self.out = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.out.cleanup)

    def config(self, **kwargs):
        base = {'goal': 'Completa el documento', 'max_passes': 6,
                'allow_export': True, 'export_dir': self.out.name}
        base.update(kwargs)
        return base

    def test_three_pass_loop_writes_a_section_exports_and_leaves_a_receipt(self):
        api = FakeAPI([
            loop_reply('Reviso la estructura', [call('ver_documento')]),
            loop_reply('Escribo la delimitación', [call('escribir_apartado', section='delimitacion',
                                                       text='Delimitación concreta y verificable.')]),
            loop_reply('Genero el documento', [call('generar_documento'),
                                               call('finalizar', motivo='Completado')], True),
        ])
        p = Agent(self.s, api).turn(self.p['id'], 'Completa el documento',
                                    origin='usuario', loop=self.config())
        self.assertEqual(len(api.requests), 3)
        self.assertIn('Delimitación concreta', p['drafts']['delimitacion']['text'])
        self.assertEqual(p['last_loop']['stopped'], 'finalizado')
        self.assertEqual(p['last_loop']['passes'], 3)
        self.assertEqual(p['last_loop']['changes'], 1)
        self.assertEqual(len(p['loop_receipts']), 1)
        self.assertFalse(p.get('pending'))
        self.assertEqual(len(list(Path(self.out.name).iterdir())), 3)
        # The tool guide and the previous receipt reach the model on every pass.
        self.assertIn('ver_documento', api.instructions)
        later = [json.dumps(r, ensure_ascii=False) for r in api.requests[1:]]
        self.assertTrue(any('research_result' in r and '[OK]' in r for r in later),
                        'the previous pass receipt must reach the model')

    def test_loop_stops_at_its_pass_limit_and_still_saves_progress(self):
        api = FakeAPI([loop_reply('añado ' + str(i),
                                  [call('anadir_apartado', titulo='Apartado ' + str(i))])
                       for i in range(4)])
        p = Agent(self.s, api).turn(self.p['id'], 'Objetivo', origin='usuario',
                                    loop=self.config(max_passes=3))
        self.assertEqual(len(api.requests), 3)
        self.assertEqual(p['last_loop']['stopped'], 'limite_de_pasos')
        self.assertEqual(len(p['doc_extra']), 3)
        self.assertFalse(p.get('pending'))

    def test_loop_stops_when_no_measureable_progress(self):
        api = FakeAPI([loop_reply('sin cambios', [call('ver_estado')]) for _ in range(6)])
        p = Agent(self.s, api).turn(self.p['id'], 'Objetivo', origin='usuario',
                                    loop=self.config(max_passes=6))
        self.assertEqual(p['last_loop']['stopped'], 'sin_progreso')
        self.assertLessEqual(len(api.requests), 4)

    def test_question_tool_stops_the_loop_and_waits_for_the_user(self):
        api = FakeAPI([loop_reply('Necesito un dato', [call('preguntar_usuario', texto='¿Población?')]),
                       loop_reply('No debería ejecutarse', [call('ver_estado')])])
        p = Agent(self.s, api).turn(self.p['id'], 'Objetivo', origin='usuario', loop=self.config())
        self.assertEqual(len(api.requests), 1)
        self.assertEqual(p['last_loop']['stopped'], 'pregunta')
        self.assertIn('¿Población?', p['questions'][0]['text'])

    def test_no_tool_calls_stops_without_spinning(self):
        api = FakeAPI([loop_reply('Ya está todo', []), loop_reply('Otra vez', [])])
        p = Agent(self.s, api).turn(self.p['id'], 'Objetivo', origin='usuario', loop=self.config())
        self.assertEqual(len(api.requests), 1)
        self.assertEqual(p['last_loop']['stopped'], 'sin_herramientas')

    def test_bad_tool_name_is_a_contained_error_not_a_crash(self):
        api = FakeAPI([
            '{"reply":"intento","tool_calls":[{"name":"no_existe","arguments":{}}],"done":false}',
            loop_reply('Me corrijo', [call('finalizar', motivo='Herramienta inexistente')], True),
        ])
        p = Agent(self.s, api).turn(self.p['id'], 'Objetivo', origin='usuario', loop=self.config())
        # The first reply fails unpack -> operation stays pending for Reanudar.
        self.assertEqual(len(api.requests), 1)
        self.assertTrue(p.get('pending'))
        self.assertIn('bucle no pudo interpretar', p['messages'][-1]['text'])

    def test_stop_event_prevents_the_next_model_call(self):
        api = FakeAPI([loop_reply('paso 1', [call('ver_estado')]), loop_reply('paso 2', [call('ver_estado')])])
        agent = Agent(self.s, api, stop=self.stop)
        original = agent._loop_pass

        def stopping(*a, **kw):
            result = original(*a, **kw)
            self.stop.set()
            return result
        agent._loop_pass = stopping
        p = agent.turn(self.p['id'], 'Objetivo', origin='usuario', loop=self.config())
        self.assertEqual(len(api.requests), 1)
        self.assertEqual(p['run']['status'], 'detenido')

    def test_loop_instructions_include_the_goal_state_and_receipt(self):
        from prompt_policy import loop_instructions
        text = loop_instructions(agent_tools.TOOL_GUIDE, 2, 6,
                                 document.compact_state(self.p), '[OK] ver_estado', 'Termina la tesis')
        self.assertIn('Termina la tesis', text)
        self.assertIn('[OK] ver_estado', text)
        self.assertIn('Paso 2/6', text)
        self.assertIn('finalizar', text)


class StartupSelfCheckTests(unittest.TestCase):
    def test_startup_check_runs_the_whole_loop_offline(self):
        from verificar_instalacion import check_loop, check_research
        self.assertEqual(check_loop(), [])
        self.assertEqual(check_research(), [])

    def test_build_label_matches_metadata(self):
        from version import VERSION, BUILD
        meta = json.loads((ROOT / 'VERSION.json').read_text('utf-8'))
        self.assertEqual(meta['version'], VERSION)
        self.assertEqual(meta['build'], BUILD)
        self.assertEqual(BUILD, 'fase6-4')


class AppWiringTests(unittest.TestCase):
    def test_ui_has_document_tab_and_bounded_loop_button(self):
        source = (ROOT / 'app.py').read_text('utf-8')
        for needle in ("self.build_document()", "'Generar documento completo',self.generate_document",
                       "'Agente con herramientas',self.start_agent_loop",
                       "def start_agent_loop", "DEFAULT_LOOP_GOAL",
                       "loop=config", "'Ver recibo del agente'"):
            self.assertIn(needle, source)
        self.assertIn("values=('2','4','6','8','12')", source)
        self.assertNotIn('while True:\n            worker.turn(', source)
