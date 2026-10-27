"""Regression: Copilot autonomous mode died after a few passes.

Reported symptom: "funciona bien hasta que lo pongan en modo autónomo. Ahí
funciona un rato y luego deja de funcionar con Copilot". The user suspected the
app did not wait for the answer.

Root cause (reproduced with a real RoutedAPI): `attempt_limit` (default 6) and
`cycle_seconds` (default 180) were accumulated on the RoutedAPI INSTANCE. A
single instance is reused for EVERY pass of the agent loop, so pass 7 failed
with "No quedan rutas listas o se alcanzó el límite del ciclo" and slow Copilot
answers also exhausted the 3-minute clock. The per-attempt timeout was capped
at 90s, cutting long streamed JSON sections short.

Those two settings are a FAILOVER BUDGET FOR ONE REQUEST, not a quota for the
whole turn. This suite pins that contract.

Synthetic fixtures only: no Windows, no real M365 session, no network, no Word.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeProtector, FakeAPI  # noqa: E402
from test_v02 import session  # noqa: E402
from config import Config  # noqa: E402
from routing import RoutedAPI  # noqa: E402
from project_store import ProjectStore, LABELS  # noqa: E402
from agent import Agent  # noqa: E402


def loop_reply(section=None, final=False):
    if final:
        calls = [{'name': 'finalizar', 'arguments': {'motivo': 'Completado'}}]
    else:
        section = section or 'marco_teorico'
        text = 'Contenido provisional bien desarrollado para ' + LABELS[section] + '. ' * 60
        calls = [{'name': 'escribir_apartado',
                  'arguments': {'section': section, 'text': text, 'sources': []}}]
    return json.dumps({'reply': 'Avance del paso', 'tool_calls': calls,
                       'done': final}, ensure_ascii=False)


SECTIONS = ('marco_teorico', 'metodologia', 'instrumentos', 'plan_accion',
            'analisis_previsto', 'cronograma', 'presupuesto', 'referencias',
            'anexos', 'delimitacion', 'problematica', 'objetivos')


class ModoAutonomoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Config(self.tmp.name, FakeProtector())
        self.aid = self.config.account('Copilot365', 'fixture', session())
        self.rid = self.config.route('Copilot365', 'auto', self.aid)
        self.config.select(self.rid)
        self.config.memory[self.aid] = session()
        self.store = ProjectStore(self.tmp.name)

    def factory(self, replies, seen=None):
        """Factory returning FakeAPI instances; records the timeout it received."""
        def make(provider, key, model, endpoint, timeout):
            api = FakeAPI([replies.pop(0)] * 2)
            api.provider = provider
            api.model = model
            api.endpoint = endpoint
            api.key = key
            api.timeout = timeout
            if seen is not None:
                seen.append(timeout)
            return api
        return make

    def test_12_pasos_no_agotan_el_presupuesto_de_intentos(self):
        """One RoutedAPI reused for 12 loop passes must NOT die on pass 7."""
        self.config.data['attempt_limit'] = 1
        replies = [loop_reply()] * 20
        api = RoutedAPI(self.config, self.config.candidates(),
                        self.factory(replies))
        for i in range(12):
            api.request([{'role': 'user', 'content': 'paso ' + str(i)}], [])
        self.assertEqual(api.calls, 12)
        self.assertEqual(api.attempts, 12)

    def test_copilot_recibe_todo_el_ciclo_como_timeout(self):
        """A 90s cap cut long streamed JSON; Copilot gets the full budget."""
        seen = []
        self.config.data['cycle_seconds'] = 180
        api = RoutedAPI(self.config, self.config.candidates(),
                        self.factory([loop_reply()], seen))
        api.request([{'role': 'user', 'content': 'x'}], [])
        self.assertGreater(seen[0], 90, seen)
        self.assertLessEqual(seen[0], 180)

    def test_el_reloj_del_ciclo_se_reinicia_en_cada_peticion(self):
        """A slow first pass must not steal time from the second one."""
        clock = {'now': 1000.0}
        def monotonic():
            return clock['now']
        seen = []
        api = RoutedAPI(self.config, self.config.candidates(),
                        self.factory([loop_reply()] * 4, seen))
        with patch('routing.time.monotonic', monotonic):
            api.request([{'role': 'user', 'content': 'primero'}], [])
            clock['now'] += 170  # almost the whole budget spent on pass 1
            api.request([{'role': 'user', 'content': 'segundo'}], [])
        self.assertEqual(len(seen), 2)
        self.assertGreater(seen[1], 90,
                           'el segundo paso heredó el reloj del primero')

    def test_bucle_real_completa_mas_pasos_que_el_limite_de_intentos(self):
        """End-to-end: Agent.turn(loop=...) with a real RoutedAPI reaches 12."""
        p = self.store.create('Problemáticas de la agrimensura en República Dominicana')
        self.store.save(p, 'seed')
        self.config.data['attempt_limit'] = 2   # deliberately below 12 passes
        replies = [loop_reply(SECTIONS[i % len(SECTIONS)])
                   for i in range(14)] + [loop_reply(final=True)]
        api = RoutedAPI(self.config, self.config.candidates(),
                        self.factory(replies))
        result = Agent(self.store, api).turn(
            p['id'], 'Completa los apartados pendientes', origin='usuario',
            loop={'goal': 'Completar el documento', 'max_passes': 12,
                  'allow_research': False, 'allow_export': False})
        last = result.get('last_loop', {})
        self.assertEqual(last.get('stopped'), 'limite_de_pasos', last)
        self.assertEqual(last.get('passes'), 12, last)
        self.assertGreaterEqual(len(result['drafts']), 8)
        self.assertNotIn('No quedan rutas listas',
                         ' '.join(m['text'] for m in result['messages']
                                  if m['role'] == 'system'))

    def test_fuente_del_codigo_usa_presupuesto_por_peticion(self):
        source = (ROOT / 'routing.py').read_text('utf-8')
        self.assertIn('cycle_attempts', source)
        self.assertIn('cycle_start', source)
        self.assertIn("r['provider']=='Copilot365'", source)

    def test_autochequeo_offline_cubre_el_modo_autonomo(self):
        from verificar_instalacion import check_autonomous_budget
        self.assertEqual(check_autonomous_budget(), [])
        source = (ROOT / 'verificar_instalacion.py').read_text('utf-8')
        self.assertIn('check_autonomous_budget()', source.split('def main():', 1)[1])
        self.assertIn('Modo autonomo: OK', source)


if __name__ == '__main__':
    unittest.main()
