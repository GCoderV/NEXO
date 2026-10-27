"""Regression tests for the research/autonomy dead end reported by the user.

Synthetic fixtures only: no real Crossref request, no Windows/Word/DPAPI check.
Covers: long boolean queries, real execution of the approved search, optional
sections, instruments unlocked by a methodology draft, and an honest diagnosis
when the project still has pending work.
"""
import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeAPI, reply, TOPIC_A  # noqa: E402
from project_store import ProjectStore, set_fact  # noqa: E402
from agent import Agent, unpack  # noqa: E402
from bibliography import normalize_queries  # noqa: E402
from autonomy import plan, order, fingerprint, AutonomousRunner, route_scope  # noqa: E402

BOOLEAN_QUERY = ('"cooperative learning" AND "role play" AND "English as a foreign language" '
                 'AND ("secondary education" OR "high school") AND ("speaking" OR "oral production" '
                 'OR "oral communication" OR "speaking skills" OR "English speaking") AND '
                 '("academic achievement" OR "learning outcomes" OR "language learning" OR '
                 '"speaking performance" OR "language proficiency") AND '
                 '("2020" OR "2021" OR "2022" OR "2023" OR "2024" OR "2025")')
SITE_QUERY = ('site:eric.ed.gov ("role play" OR "simulation") AND "English speaking" AND '
              '"secondary school" AND (2020 OR 2021 OR 2022 OR 2023 OR 2024) '
              'AND ("cooperative learning" OR "collaborative learning")')


def fixture_source(doi='10.1000/nexo-fixture'):
    return dict(title='Cooperative role play and oral production', authors='A. Researcher',
                year='2022', doi=doi, url='https://doi.org/' + doi,
                status='solo metadatos consultados', excerpt='', locator='',
                supports='Pendiente de comprobar pertinencia y alcance', origin='Crossref')


class QueryNormalizationTests(unittest.TestCase):
    def test_real_414_char_boolean_query_is_not_rejected(self):
        self.assertGreater(len(BOOLEAN_QUERY), 340)
        queries = normalize_queries(BOOLEAN_QUERY)
        self.assertTrue(1 < len(queries) <= 3)
        self.assertTrue(all(2 <= len(q) <= 250 for q in queries), queries)
        self.assertNotIn('AND', ' '.join(queries))
        self.assertNotIn('"', ''.join(queries))
        joined = ' '.join(queries).lower()
        for concept in ('cooperative learning', 'role play', 'secondary education'):
            self.assertIn(concept, joined)

    def test_google_syntax_and_urls_are_removed(self):
        queries = normalize_queries('https://example.org/x ' + SITE_QUERY)
        self.assertTrue(queries)
        joined = ' '.join(queries).lower()
        self.assertNotIn('site:', joined)
        self.assertNotIn('http', joined)
        self.assertTrue(all(len(q) <= 250 for q in queries))

    def test_explicit_semicolons_are_separate_searches(self):
        self.assertEqual(normalize_queries('role play; cooperative learning; English speaking'),
                         ['role play', 'cooperative learning', 'English speaking'])

    def test_short_query_kept_intact_for_existing_behaviour(self):
        self.assertEqual(normalize_queries('English education'), ['English education'])

    def test_empty_or_non_string_returns_no_queries(self):
        self.assertEqual(normalize_queries(''), [])
        self.assertEqual(normalize_queries(None), [])


class SearchExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = ProjectStore(self.tmp.name)
        self.p = self.s.create(TOPIC_A)
        self.stop = threading.Event()
        self.addCleanup(self.tmp.cleanup)

    def test_unpack_accepts_the_long_query_that_used_to_be_rejected(self):
        proposal = reply(search=dict(query=BOOLEAN_QUERY, reason='Ubicar antecedentes'))
        parsed = unpack(json.dumps(proposal, ensure_ascii=False))
        self.assertEqual(parsed['search']['query'], BOOLEAN_QUERY)

    def test_long_query_really_calls_searcher_and_registers_sources(self):
        called = []
        approved = []

        def searcher(q):
            called.append(q)
            return [fixture_source('10.1000/fixture-' + str(len(called)))]

        def approve(q, reason):
            approved.append(q)
            return True

        api = FakeAPI([reply(search=dict(query=BOOLEAN_QUERY, reason='Antecedentes')),
                       reply(drafts=[dict(section='marco_teorico',
                                          text='Antecedentes: candidato bibliográfico [F1]; falta leerlo.',
                                          sources=['F1'])])])
        p = Agent(self.s, api, approve, searcher).turn(self.p['id'], 'Busca fuentes', True)
        self.assertEqual(len(called), 3)
        self.assertTrue(all(len(q) <= 250 for q in called))
        self.assertEqual(len(approved), 1)
        self.assertIn('cooperative learning', approved[0])
        self.assertEqual(len(p['sources']), 3)
        self.assertEqual([s['id'] for s in p['sources']], ['F1', 'F2', 'F3'])
        notices = ' '.join(m['text'] for m in p['messages'] if m['role'] == 'system')
        self.assertIn('Búsqueda completada', notices)
        self.assertIn('F1', notices)
        self.assertIn('marco_teorico', p['drafts'])

    def test_no_results_is_reported_instead_of_silence(self):
        api = FakeAPI([reply(search=dict(query=SITE_QUERY, reason='Antecedentes')),
                       reply('Sin resultados por ahora.')])
        p = Agent(self.s, api, lambda *a: True, lambda q: []).turn(
            self.p['id'], 'Busca fuentes', True)
        notices = ' '.join(m['text'] for m in p['messages'] if m['role'] == 'system')
        self.assertIn('no devolvió fuentes nuevas', notices)
        self.assertIn('Buscar fuentes', notices)
        self.assertEqual(p['sources'], [])

    def test_network_failure_does_not_crash_the_turn(self):
        def broken(q):
            raise OSError('TLS/SSL connection has been closed')

        api = FakeAPI([reply(search=dict(query=BOOLEAN_QUERY, reason='Antecedentes')),
                       reply('No se pudo consultar.')])
        p = Agent(self.s, api, lambda *a: True, broken).turn(
            self.p['id'], 'Busca fuentes', True)
        notices = ' '.join(m['text'] for m in p['messages'] if m['role'] == 'system')
        self.assertIn('no devolvió fuentes nuevas', notices)
        self.assertIn('Avisos', notices)

    def test_research_switched_off_still_makes_no_request(self):
        called = []
        api = FakeAPI([reply(search=dict(query=BOOLEAN_QUERY, reason='Antecedentes'))])
        Agent(self.s, api, lambda *a: True, lambda q: called.append(q)).turn(
            self.p['id'], 'Busca fuentes', False)
        self.assertEqual(called, [])


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = ProjectStore(self.tmp.name)
        self.p = self.s.create(TOPIC_A)
        self.stop = threading.Event()
        self.addCleanup(self.tmp.cleanup)

    def saved_draft(self, k, text='Texto anterior.'):
        self.p['drafts'][k] = {'text': text, 'status': 'borrador', 'sources': [],
                               'producer': {'provider': 'simulated'},
                               'auto_reviewed_for': fingerprint(self.p, text)}

    def test_methodology_draft_unlocks_instruments_without_a_manual_fact(self):
        self.assertNotIn('instrumentos', [t['section'] for t in plan(self.p)[0]])
        self.saved_draft('metodologia')
        self.p['drafts']['instrumentos'] = {'text': 'Borrador previo.', 'status': 'necesita_revision',
                                            'sources': [], 'producer': {'provider': 'simulated'}}
        tasks, _ = plan(self.p)
        self.assertIn('instrumentos', [t['section'] for t in tasks])
        instruction = order(self.p, {'section': 'instrumentos', 'mode': 'revisar',
                                     'label': 'Instrumentos'})['instruction']
        self.assertIn('PROPUESTA', instruction)

    def test_references_are_impossible_without_sources_and_possible_with_them(self):
        self.assertNotIn('referencias', [t['section'] for t in plan(self.p)[0]])
        self.p['sources'].append(dict(fixture_source(), id='F1'))
        self.assertIn('referencias', [t['section'] for t in plan(self.p)[0]])
        instruction = order(self.p, {'section': 'referencias', 'mode': 'crear',
                                     'label': 'Referencias'})['instruction']
        self.assertIn('APA 7', instruction)
        self.assertIn('No anadas obras', instruction)

    def test_antecedentes_is_scoped_inside_marco_teorico(self):
        task = {'section': 'marco_teorico', 'mode': 'crear', 'label': 'Marco teórico'}
        self.assertIn('Antecedentes', order(self.p, task)['instruction'])

    def test_optional_sections_are_off_by_default_and_are_templates_when_enabled(self):
        default = {t['section'] for t in plan(self.p)[0]}
        self.assertFalse({'cronograma', 'presupuesto', 'anexos'} & default)
        optional = {t['section'] for t in plan(self.p, True)[0]}
        self.assertEqual({'cronograma', 'presupuesto', 'anexos'}, optional & {'cronograma', 'presupuesto', 'anexos'})
        for k in ('cronograma', 'presupuesto', 'anexos'):
            task = order(self.p, {'section': k, 'mode': 'crear', 'label': k})
            self.assertTrue(task['provisional'])
            self.assertIn('No inventes', task['instruction'])

    def test_dead_end_project_still_reports_actionable_pending_work(self):
        for k in ('delimitacion', 'problematica', 'pregunta', 'objetivos', 'justificacion',
                  'marco_teorico', 'metodologia', 'instrumentos', 'analisis_previsto'):
            self.saved_draft(k)
        # All fingerprints must match the final project state.
        for k, d in self.p['drafts'].items():
            d['auto_reviewed_for'] = fingerprint(self.p, d['text'])
        tasks, notice = plan(self.p)
        self.assertEqual(tasks, [])
        self.assertIn('FALTAN FUENTES', notice)
        self.assertIn('Resultados/Discusión/Conclusiones', notice)
        self.assertIn('Apartados opcionales pendientes', notice)
        self.assertIn('Buscar fuentes', notice)
        self.assertTrue(plan(self.p, True)[0], 'optional templates must still be work')

    def test_adding_a_source_reopens_the_drafts(self):
        self.saved_draft('marco_teorico')
        self.p['drafts']['marco_teorico']['auto_reviewed_for'] = fingerprint(
            self.p, self.p['drafts']['marco_teorico']['text'])
        self.assertNotIn('marco_teorico', [t['section'] for t in plan(self.p)[0]])
        self.p['sources'].append(dict(fixture_source(), id='F1'))
        self.assertIn('marco_teorico', [t['section'] for t in plan(self.p)[0]])

    def test_autonomous_runner_can_include_optional_sections(self):
        for k in ('delimitacion', 'problematica', 'pregunta', 'objetivos', 'justificacion',
                  'marco_teorico', 'metodologia', 'instrumentos', 'analisis_previsto'):
            self.saved_draft(k)
        for d in self.p['drafts'].values():
            d['auto_reviewed_for'] = fingerprint(self.p, d['text'])
        self.s.save(self.p)

        def draft(k):
            return dict(section=k, text='Estructura provisional. Por definir.', sources=[])

        api = FakeAPI([reply(drafts=[draft('cronograma')]),
                       reply(drafts=[draft('presupuesto')]),
                       reply(drafts=[draft('anexos')])])
        runner = AutonomousRunner(self.s, lambda: api, self.stop)
        result = runner.run(self.p['id'], 3, authorized_scope=route_scope(api),
                            include_optional=True)
        self.assertTrue({'cronograma', 'presupuesto', 'anexos'} <= set(result['drafts']))


class StartupSelfCheckTests(unittest.TestCase):
    def test_startup_check_proves_long_searches_and_optional_sections(self):
        from verificar_instalacion import check_research
        self.assertEqual(check_research(), [])


class AppWiringTests(unittest.TestCase):
    def test_ui_exposes_manual_search_and_optional_sections(self):
        source = (ROOT / 'app.py').read_text('utf-8')
        self.assertIn("'Buscar fuentes',self.search_sources", source)
        self.assertIn('def _do_search(self,id,queries)', source)
        self.assertIn('self.include_optional', source)
        self.assertIn('include_optional=optional', source)
        self.assertIn('authorize'.replace('authorize', 'Autoriza la búsqueda'), source)
