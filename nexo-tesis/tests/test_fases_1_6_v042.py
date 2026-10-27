"""Fases 1–6: single write path, gates, research, continuous loop, verification.

Synthetic fixtures only. No network, no Word COM, no DPAPI, no M365 session.
"""
import copy
import io
import json
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.dom.minidom import parseString

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeAPI, TOPIC_A  # noqa: E402
from project_store import ProjectStore, set_fact  # noqa: E402
from agent import Agent  # noqa: E402
import agent_tools  # noqa: E402
import document  # noqa: E402
import gates  # noqa: E402
import project_state as ps  # noqa: E402
import research  # noqa: E402
import run_loop  # noqa: E402


def loop_reply(text, calls, done=False):
    return json.dumps({'reply': text, 'tool_calls': [
        {'name': n, 'arguments': a} for n, a in calls], 'done': done}, ensure_ascii=False)


def call(name, **args):
    return (name, args)


def seeded_project(store, complete=True):
    """A project with real-looking content in every required section."""
    p = store.create(TOPIC_A)
    source = {'id': 'F1', 'title': 'Cooperative learning and oral production',
              'authors': 'A. Researcher', 'year': '2022', 'doi': '10.1000/nexo',
              'url': 'https://doi.org/10.1000/nexo', 'status': 'metadatos Crossref',
              'excerpt': ''}
    p['sources'] = [source]
    set_fact(p, 'datos', 'Corpus de 24 estudiantes: 68% mejora')
    p['data_ready'] = True
    sections = ('delimitacion', 'problematica', 'pregunta', 'objetivos',
                'justificacion', 'marco_teorico', 'metodologia', 'instrumentos',
                'plan_accion', 'analisis_previsto', 'cronograma', 'presupuesto',
                'anexos', 'referencias')
    for key in sections:
        text = ('Contenido bien desarrollado para ' + key + '. ' * 8 +
                'Se apoya en la fuente registrada [F1].')
        p['drafts'][key] = {'text': text, 'status': 'borrador', 'sources': ['F1'],
                            'producer': {'provider': 'fixture'}}
    if not complete:
        p['drafts'].pop('justificacion', None)
    return p


class SingleWritePathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProjectStore(self.tmp.name)
        self.p = self.store.create(TOPIC_A)
        self.addCleanup(self.tmp.cleanup)

    def test_commit_slice_is_the_only_path_and_validates_ownership(self):
        with self.assertRaises(ValueError):
            ps.commit_slice(self.p, 'M1', {'drafts': {'resultados': 'texto'}}, 'mala')
        receipt = ps.commit_slice(self.p, 'M1',
                                  {'drafts': {'delimitacion': 'Texto suficientemente largo. ' * 4}},
                                  'Redactar delimitación', actor='prueba')
        self.assertTrue(receipt['ok'])
        self.assertIn('delimitacion', self.p['drafts'])
        self.assertIn('modules', self.p)
        self.assertEqual(self.p['last_commit']['module'], 'M1')

    def test_snapshot_before_apply_and_undo(self):
        ps.commit_slice(self.p, 'M1', {'drafts': {'delimitacion': 'Versión uno. ' * 8}}, 'v1')
        ps.commit_slice(self.p, 'M1', {'drafts': {'delimitacion': 'Versión dos. ' * 8}}, 'v2')
        self.assertEqual(len(self.p['state_history']), 2)
        undone = ps.undo_last(self.p)
        self.assertTrue(undone['ok'])
        self.assertIn('Versión uno', self.p['drafts']['delimitacion']['text'])

    def test_dag_flags_downstream_modules(self):
        ps.commit_slice(self.p, 'M3', {'drafts': {'metodologia': 'Diseño mixto. ' * 8}}, 'diseño')
        ps.commit_slice(self.p, 'M5', {'drafts': {'cronograma': 'Fases. ' * 10}}, 'cronograma')
        before = ps.status_map(self.p)['M5']
        ps.commit_slice(self.p, 'M3', {'drafts': {'metodologia': 'Diseño cualitativo. ' * 8}}, 'cambio')
        self.assertEqual(self.p['modules']['M5']['status'], 'needs_review')
        self.assertFalse(ps.verify(self.p)['done'])
        self.assertIn('M5', ps.status_map(self.p))

    def test_protected_draft_cannot_be_overwritten(self):
        ps.commit_slice(self.p, 'M1', {'drafts': {'delimitacion': 'Texto del usuario. ' * 8}}, 'v1')
        self.p['drafts']['delimitacion']['edited_by_user'] = True
        with self.assertRaises(ValueError):
            ps.commit_slice(self.p, 'M1', {'drafts': {'delimitacion': 'Texto del agente. ' * 8}}, 'intento')
        self.assertIn('Texto del usuario', self.p['drafts']['delimitacion']['text'])

    def test_citation_and_empirical_guards(self):
        with self.assertRaises(ValueError):
            ps.commit_slice(self.p, 'M2', {'drafts': {'marco_teorico': 'Según [F99]. ' * 8}}, 'cita')
        with self.assertRaises(ValueError):
            ps.commit_slice(self.p, 'M4', {'drafts': {'resultados': 'Mejoró 95%. ' * 8}}, 'datos')

    def test_confirm_module_requires_content(self):
        with self.assertRaises(ValueError):
            ps.confirm_module(self.p, 'M2')

    def test_document_write_section_goes_through_commit(self):
        made = document.write_section(self.p, 'objetivos', 'Objetivo concreto. ' * 8)
        self.assertTrue(made['commits'])
        self.assertIn('last_commit', self.p)

    def test_legacy_project_migrates_without_losing_drafts(self):
        self.p['drafts']['delimitacion'] = {'text': 'Texto antiguo. ' * 8,
                                           'status': 'borrador', 'sources': []}
        ps.ensure(self.p)
        self.assertEqual(len(self.p['modules']), 5)
        self.assertIn('Texto antiguo', self.p['drafts']['delimitacion']['text'])


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProjectStore(self.tmp.name)
        self.p = seeded_project(self.store)
        self.addCleanup(self.tmp.cleanup)

    def test_clean_project_passes_hard_gates(self):
        result = gates.evaluate(self.p)
        self.assertEqual(result['hard'], [], result['hard'])
        self.assertTrue(result['passes'])

    def test_unknown_citation_and_fabricated_doi_are_hard_blocks(self):
        self.p['drafts']['marco_teorico']['text'] += ' Véase [F77] y 10.9999/falso.'
        result = gates.evaluate(self.p)
        self.assertTrue(any('inexistentes' in x or 'DOI' in x for x in result['hard']))

    def test_numbers_without_confirmed_data_are_blocked(self):
        self.p['data_ready'] = False
        self.p['facts'].pop('datos', None)
        self.p['drafts']['resultados'] = {'text': 'Se obtuvo 95% de mejora. ' * 8,
                                          'status': 'borrador', 'sources': []}
        result = gates.evaluate(self.p)
        self.assertTrue(any('sin datos' in x for x in result['hard']))

    def test_impossible_percentage_is_blocked(self):
        self.p['drafts']['resultados'] = {'text': 'Se obtuvo 140% de mejora. ' * 8,
                                          'status': 'borrador', 'sources': []}
        result = gates.evaluate(self.p)
        self.assertTrue(any('imposible' in x for x in result['hard']))

    def test_export_guard_refuses_missing_mandatory_chapter(self):
        self.p['drafts'].pop('metodologia', None)
        result = gates.check_export(self.p)
        self.assertTrue(any('obligatorio' in x for x in result[0]))

    def test_export_includes_quality_in_all_formats(self):
        with tempfile.TemporaryDirectory() as out:
            info = document.export(self.p, out)
            self.assertIn('quality', info)
            md = (Path(out) / [f for f in info['files'] if f.endswith('.md')][0]).read_text('utf-8')
            self.assertIn('Estado del documento', md)
            self.assertIn('Puertas de calidad', md)
            html_text = (Path(out) / [f for f in info['files'] if f.endswith('.html')][0]).read_text('utf-8')
            self.assertIn('Puertas de calidad', html_text)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProjectStore(self.tmp.name)
        self.p = self.store.create(TOPIC_A)
        self.addCleanup(self.tmp.cleanup)

    def test_facets_come_from_the_project_topic_only(self):
        queries = research.facets(self.p, 4)
        self.assertTrue(queries)
        self.assertTrue(any('cooperativ' in q for q in queries))
        self.assertLessEqual(len(queries), 4)

    def test_dedupe_records_provenance_and_two_provider_verification(self):
        merged = research.dedupe([
            {'title': 'Same paper', 'doi': '10.1/x', 'origin': 'Crossref', 'year': '2020'},
            {'title': 'Same Paper.', 'doi': '10.1/X', 'origin': 'OpenAlex', 'year': '2021'},
        ])
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]['verified_by']), 2)
        self.assertIn('2+ bases', merged[0]['status'])

    def test_offline_discovery_is_contained_and_reports_errors(self):
        outcome = research.discover(self.p, queries=['role play speaking'],
                                    allow_network=False, providers=[('Crossref', research._crossref)])
        self.assertEqual(outcome['items'], [])
        self.assertTrue(outcome['errors'])
        self.assertIn('sin red', outcome['errors'][0])

    def test_research_for_commits_through_the_single_write_path(self):
        fake = [{'title': 'Obra real', 'doi': '10.1/a', 'origin': 'Crossref', 'year': '2020',
                 'verified_by': ['Crossref', 'OpenAlex'], 'verification': '2+ bases'}]
        with patch.object(research, 'discover', return_value={
                'items': fake, 'attempted': 2, 'errors': [], 'queries': ['x'],
                'providers': ['Crossref', 'OpenAlex'], 'verified': 1,
                'note': 'solo metadatos'}):
            outcome = research.research_for(self.p, approve=lambda qs: True,
                                           allow_network=False, queries=['role play'])
        self.assertTrue(outcome['ok'])
        self.assertEqual(len(self.p['sources']), 1)
        self.assertEqual(self.p['last_commit']['module'], 'M2')
        self.assertEqual(len(self.p['sources'][0]['verified_by']), 2)

    def test_research_requires_explicit_approval(self):
        outcome = research.research_for(self.p, approve=lambda qs: False, queries=['role play'])
        self.assertFalse(outcome['ok'])
        self.assertIn('no autorizada', outcome['reason'])


class ContinuousLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProjectStore(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def config(self, **kwargs):
        base = run_loop.RunProfile(
            goal='Terminar el trabajo', max_passes=None, max_seconds=600,
            max_stalls=3, hard_fuse=40, allow_research=False, auto_research=False,
            allow_export=False, include_optional=True, export_dir=self.tmp.name)
        for key, value in kwargs.items():
            setattr(base, key, value)
        return base.loop_config()

    def test_profile_has_no_step_quota_but_has_safety_limits(self):
        profile = run_loop.RunProfile()
        self.assertIsNone(profile.max_passes)
        self.assertIn('Sin cuota de pasos', profile.describe())
        self.assertGreater(profile.max_seconds, 0)
        self.assertGreater(profile.hard_fuse, 0)
        config = profile.loop_config()
        self.assertIsNone(config['max_passes'])
        self.assertTrue(config['continuous'])

    def test_continuous_stops_with_trabajo_completado_on_verified_project(self):
        p = seeded_project(self.store)
        self.store.save(p)
        verification = ps.verify(p)
        self.assertTrue(verification['done'], verification)
        api = FakeAPI([loop_reply('Verifico el estado', [call('verificar')])])
        result = Agent(self.store, api).turn(
            p['id'], 'Termina', origin='usuario', loop=self.config())
        self.assertEqual(result['last_loop']['stopped'], 'trabajo_completado')
        self.assertEqual(len(api.requests), 1)
        self.assertEqual(result['last_loop']['verification']['done'], True)

    def test_no_step_quota_allows_many_passes_and_stops_on_stalls(self):
        p = self.store.create(TOPIC_A)
        self.store.save(p)
        api = FakeAPI([loop_reply('sin cambios', [call('verificar')]) for _ in range(6)])
        result = Agent(self.store, api).turn(
            p['id'], 'Objetivo', origin='usuario',
            loop=self.config(max_stalls=3))
        self.assertGreaterEqual(len(api.requests), 3)
        self.assertEqual(result['last_loop']['stopped'],
                         'sin_progreso_tras_cambiar_estrategia')
        self.assertIn('ESTRATEGIA', api.requests[-1][0]['content'])

    def test_model_saying_done_does_not_stop_before_verification(self):
        p = self.store.create(TOPIC_A)
        self.store.save(p)
        api = FakeAPI([
            loop_reply('Ya terminé', [], done=True),
            loop_reply('sigo', [call('verificar')]),
            loop_reply('sigo', [call('verificar')]),
            loop_reply('sigo', [call('verificar')]),
            loop_reply('sigo', [call('verificar')]),
        ])
        result = Agent(self.store, api).turn(
            p['id'], 'Objetivo', origin='usuario', loop=self.config(max_stalls=3))
        self.assertGreater(len(api.requests), 1)
        self.assertNotEqual(result['last_loop']['stopped'], 'finalizado')

    def test_hard_fuse_and_wall_clock_are_non_quota_safety_stops(self):
        p = self.store.create(TOPIC_A)
        self.store.save(p)
        api = FakeAPI([loop_reply('sigo', [call('verificar')]) for _ in range(12)])
        result = Agent(self.store, api).turn(
            p['id'], 'Objetivo', origin='usuario', loop=self.config(hard_fuse=2, max_stalls=99))
        self.assertEqual(result['last_loop']['stopped'], 'fusible_de_seguridad')
        decision = run_loop.evaluate(p, {'passes': 1, 'stalls': 0,
                                        'started_at': time.monotonic() - 3600},
                                     run_loop.RunProfile(max_seconds=60))
        self.assertEqual(decision['stop'], 'tiempo_agotado')

    def test_host_investigates_in_place_without_model_prompt(self):
        p = self.store.create(TOPIC_A)
        self.store.save(p)
        api = FakeAPI([loop_reply('sigo', [call('verificar')]) for _ in range(6)])
        profile = self.config(auto_research=True, allow_research=True, max_stalls=3)
        with patch.object(research, 'research_for', return_value={
                'ok': True, 'added': 2, 'verified': 1, 'attempted': 4,
                'errors': [], 'queries': ['x'], 'providers': ['Crossref']}) as mocked:
            result = Agent(self.store, api, approve_search=lambda *a: True,
                           searcher=lambda q: []).turn(
                p['id'], 'Objetivo', origin='usuario', loop=profile)
        self.assertTrue(mocked.called)
        self.assertGreaterEqual(result['last_loop']['research_rounds'], 1)
        self.assertTrue(any(a['tool'] == 'investigar' for a in result['last_loop']['actions']))

    def test_human_question_is_an_approval_boundary_even_when_continuous(self):
        p = self.store.create(TOPIC_A)
        self.store.save(p)
        api = FakeAPI([loop_reply('Necesito un dato',
                                  [call('preguntar_usuario', texto='¿Población?')])])
        result = Agent(self.store, api).turn(
            p['id'], 'Objetivo', origin='usuario', loop=self.config())
        self.assertEqual(result['last_loop']['stopped'], 'pregunta')
        self.assertEqual(len(api.requests), 1)

    def test_receipt_is_auditable(self):
        p = seeded_project(self.store)
        self.store.save(p)
        api = FakeAPI([loop_reply('Verifico', [call('verificar')])])
        result = Agent(self.store, api).turn(
            p['id'], 'Termina', origin='usuario', loop=self.config())
        receipt = result['last_loop']
        for key in ('goal', 'passes', 'changes', 'stopped', 'actions', 'verification', 'profile', 'state'):
            self.assertIn(key, receipt)
        self.assertIsNone(receipt['profile']['max_passes'])

    def test_continuous_prompt_forbids_done_before_verification(self):
        from prompt_policy import loop_instructions
        text = loop_instructions(agent_tools.TOOL_GUIDE, 1, None, {}, '', 'Meta', continuous=True)
        self.assertIn('MODO CONTINUO', text)
        self.assertIn('NO hay cuota de pasos', text)
        self.assertIn('verificar()', text)


class NewToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProjectStore(self.tmp.name)
        self.p = seeded_project(self.store)
        self.addCleanup(self.tmp.cleanup)

    def services(self, **kwargs):
        base = {'allow_research': True, 'allow_export': True, 'export_dir': self.tmp.name,
                'approve_search': lambda *a: True, 'allow_network': False,
                'include_optional': True, 'origin': 'usuario', 'user_text': '',
                'producer': 'test', 'store': self.store}
        base.update(kwargs)
        return base

    def test_verificar_estado_siguiente_paso_and_confirmar(self):
        for name in ('verificar', 'estado_modulos', 'siguiente_paso'):
            row = agent_tools.execute(self.p, {'name': name, 'arguments': {}}, self.services())
            self.assertTrue(row['ok'], (name, row['summary']))
        row = agent_tools.execute(self.p, {'name': 'confirmar_modulo',
                                           'arguments': {'modulo': 'M5'}}, self.services())
        self.assertTrue(row['ok'])
        self.assertEqual(row['data']['status']['M5'], 'done')

    def test_deshacer_tool(self):
        ps.commit_slice(self.p, 'M1', {'drafts': {'delimitacion': 'Nuevo texto. ' * 8}}, 'cambio')
        row = agent_tools.execute(self.p, {'name': 'deshacer', 'arguments': {}}, self.services())
        self.assertTrue(row['ok'])
        self.assertTrue(row['changed'])

    def test_investigar_tool_requires_authorization(self):
        row = agent_tools.execute(self.p,
            {'name': 'investigar', 'arguments': {'terminos': 'role play; cooperative learning'}},
            self.services(approve_search=None))
        self.assertFalse(row['ok'])

    def test_investigar_tool_commits_when_approved(self):
        with patch.object(research, 'research_for', return_value={
                'ok': True, 'added': 1, 'verified': 1, 'attempted': 2,
                'errors': [], 'queries': ['x'], 'providers': ['Crossref'], 'note': ''}):
            row = agent_tools.execute(self.p,
                {'name': 'investigar', 'arguments': {'terminos': 'role play'}}, self.services())
        self.assertTrue(row['ok'])
        self.assertIn('Investigación:', row['summary'])

    def test_tool_registry_has_21_bounded_tools(self):
        self.assertEqual(len(agent_tools.TOOLS), 21)
        self.assertLessEqual(agent_tools.MAX_CALLS_PER_PASS, 4)


class VersionAndWiringTests(unittest.TestCase):
    def test_build_label_is_fase6(self):
        from version import VERSION, BUILD
        meta = json.loads((ROOT / 'VERSION.json').read_text('utf-8'))
        self.assertEqual(VERSION, '0.4.1-dev')
        self.assertEqual(BUILD, 'fase6-5')
        self.assertEqual(meta['build'], BUILD)

    def test_app_wires_continuous_and_module_panel(self):
        source = (ROOT / 'app.py').read_text('utf-8')
        for needle in ("'Agente continuo · hasta terminar',self.start_continuous",
                       'run_loop.RunProfile', 'project_state.status_map',
                       'def confirm_module_dialog', 'def undo_commit',
                       'diagnostics.friendly'):
            self.assertIn(needle, source)

    def test_fase6_offline_self_check_passes(self):
        from verificar_instalacion import check_fase6
        self.assertEqual(check_fase6(), [])

    def test_all_new_modules_listed_in_selfcheck(self):
        source = (ROOT / 'verificar_instalacion.py').read_text('utf-8')
        for name in ('diagnostics', 'process_guard', 'project_state', 'gates',
                     'research', 'run_loop'):
            self.assertIn("'" + name + "'", source)
