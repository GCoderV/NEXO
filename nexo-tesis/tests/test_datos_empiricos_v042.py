"""Regression: the continuous agent must ASK for data, not fill empirical chapters.

Reproduces the exact model output the user pasted::

    "Persisten como pendientes Resultados, Discusión y Conclusiones. Dado que
     Resultados no puede redactarse sin datos empíricos confirmados, intento
     completar otro apartado pendiente no basado en hallazgos del estudio."
     -> escribir_apartado('conclusiones', 'Conclusiones (provisional). Este
        apartado permanece condicionado a la obtención y análisis de datos...')

Before the fix: the write was refused but the loop had no deterministic exit,
so it kept retrying until a stall/fuse; the semantic placeholder also passed
all quality gates. Now the host stops with `pregunta` and registers ONE
concrete question about the corpus.

Synthetic fixtures only: no Windows, no Word, no network, no M365 session.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeAPI  # noqa: E402
from test_fases_1_6_v042 import call, loop_reply, seeded_project  # noqa: E402
from project_store import ProjectStore  # noqa: E402
from agent import Agent  # noqa: E402
import agent_tools  # noqa: E402
import empirical  # noqa: E402
import gates  # noqa: E402
import project_state as ps  # noqa: E402
import run_loop  # noqa: E402

FILLER = (
    'Conclusiones (provisional). Este apartado permanece condicionado a la '
    'obtención y análisis de datos del estudio. En la fase actual no existen '
    'evidencias empíricas que permitan establecer conclusiones sobre la '
    'producción oral en inglés ni sobre la incidencia de la estrategia de '
    'aprendizaje cooperativo basada en juegos de roles. Las conclusiones '
    'definitivas deberán fundamentarse en los datos recopilados, los objetivos '
    'alcanzados y el análisis correspondiente. Toda afirmación sobre '
    'efectividad, mejora o impacto permanece con apoyo pendiente hasta contar '
    'con evidencia verificable.')

USER_TURN = json.dumps({
    'reply': ('Persisten como pendientes Resultados, Discusión y Conclusiones. '
              'Dado que Resultados no puede redactarse sin datos empíricos '
              'confirmados, intento completar otro apartado pendiente no basado '
              'en hallazgos del estudio.'),
    'tool_calls': [{'name': 'escribir_apartado',
                    'arguments': {'section': 'conclusiones', 'text': FILLER,
                                  'sources': []}}],
    'done': False}, ensure_ascii=False)


class DatosEmpiricosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ProjectStore(self.tmp.name)

    def config(self, **kwargs):
        base = run_loop.RunProfile(
            goal='Terminar el trabajo', max_passes=None, max_seconds=600,
            max_stalls=3, hard_fuse=40, allow_research=False,
            auto_research=False, allow_export=False, include_optional=True,
            export_dir=self.tmp.name)
        for key, value in kwargs.items():
            setattr(base, key, value)
        return base.loop_config()

    def without_data(self):
        p = seeded_project(self.store)
        p['data_ready'] = False
        p['facts'].pop('datos', None)
        self.store.save(p)
        return p

    def test_el_texto_provisional_del_reporte_es_reconocido(self):
        self.assertTrue(empirical.placeholder(FILLER))
        p = seeded_project(self.store)
        p['drafts']['conclusiones'] = {'text': FILLER, 'status': 'borrador',
                                       'sources': []}
        hard = gates.evaluate(p)['hard']
        self.assertTrue(any('provisional' in x for x in hard), hard)
        self.assertFalse(ps.verify(p)['done'])

    def test_escribir_conclusiones_sin_corpus_da_error_accionable(self):
        p = self.store.create('Tema de prueba')
        row = agent_tools.execute(
            p, {'name': 'escribir_apartado',
                'arguments': {'section': 'conclusiones', 'text': FILLER,
                              'sources': []}},
            {'origin': 'usuario', 'user_text': '', 'producer': 'test'})
        self.assertFalse(row['ok'])
        self.assertFalse(row['changed'])
        self.assertIn('preguntar_usuario', row['summary'])
        self.assertNotIn('conclusiones', p['drafts'])

    def test_bucle_pregunta_al_usuario_en_vez_de_rellenar(self):
        """The exact reported turn must stop after ONE model call, not 300."""
        p = self.without_data()
        api = FakeAPI([USER_TURN] + [loop_reply('insisto', [call('verificar')])
                                     for _ in range(10)])
        result = Agent(self.store, api).turn(
            p['id'], 'Termina', origin='usuario', loop=self.config())
        self.assertEqual(result['last_loop']['stopped'], 'pregunta')
        self.assertEqual(len(api.requests), 1, 'no debe quemar llamadas insistiendo')
        self.assertIn('corpus', result['last_loop'].get('question', '').lower())
        questions = [q['text'] for q in result['questions']
                     if q.get('status') == 'abierta']
        self.assertTrue(any('corpus' in q.lower() for q in questions), questions)
        self.assertNotIn('conclusiones', result['drafts'],
                         'el texto provisional no debió guardarse')

    def test_no_se_pregunta_mientras_queden_apartados_por_hacer(self):
        p = seeded_project(self.store, complete=False)  # falta justificacion
        p['data_ready'] = False
        p['facts'].pop('datos', None)
        self.assertIsNone(empirical.data_question(p),
                          'primero debe redactar lo que sí puede redactar')

    def test_anteproyecto_no_requiere_resultados_empiricos(self):
        p = self.without_data()
        p['facts']['tipo_trabajo'] = {'value': 'Anteproyecto de investigación'}
        self.assertFalse(empirical.requires_results(p))
        self.assertIsNone(empirical.data_question(p))
        self.assertEqual(gates.check_empirical(p)[0], [])
        hard = gates.evaluate(p)['hard']
        self.assertFalse(any('empíric' in x for x in hard), hard)

    def test_corpus_confirmado_y_borradores_reales_no_disparan_pregunta(self):
        p = seeded_project(self.store)
        for key in empirical.EMPIRICAL:
            p['drafts'][key] = {
                'text': ('Con el corpus confirmado se observa una tendencia '
                         'coherente con los objetivos del estudio. ' * 4),
                'status': 'borrador', 'sources': []}
        self.assertTrue(empirical.confirmed(p))
        self.assertEqual(empirical.placeholder_sections(p), [])
        self.assertIsNone(empirical.data_question(p))
        self.assertFalse([x for x in gates.evaluate(p)['hard']
                          if 'empíric' in x])
        self.assertTrue(ps.verify(p)['done'], ps.verify(p))

    def test_pregunta_del_anfitrion_no_se_duplica(self):
        p = self.without_data()
        api = FakeAPI([USER_TURN] + [loop_reply('insisto', [call('verificar')])
                                     for _ in range(6)])
        result = Agent(self.store, api).turn(
            p['id'], 'Termina', origin='usuario', loop=self.config())
        asked = [q for q in result['questions'] if q.get('key') == 'datos']
        self.assertEqual(len(asked), 1)

    def test_estrategia_del_bucle_desaconseja_el_relleno(self):
        joined = ' '.join(run_loop.STRATEGIES)
        self.assertIn('NO escribas texto provisional', joined)
        self.assertIn('preguntar_usuario', joined)

    def test_autochequeo_offline_cubre_la_frontera_empirica(self):
        """VERIFICAR.cmd must prove THIS copy asks for data."""
        from verificar_instalacion import check_empirical_boundary
        self.assertEqual(check_empirical_boundary(), [])
        source = (ROOT / 'verificar_instalacion.py').read_text('utf-8')
        self.assertIn('check_empirical_boundary()', source.split('def main():', 1)[1])
        self.assertIn('Datos empiricos: OK', source)
        self.assertIn("'empirical'", source)


if __name__ == '__main__':
    unittest.main()
