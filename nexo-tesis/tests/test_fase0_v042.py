"""Fase 0 regressions: the exact user-reported crash, diagnostics and windows."""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

import diagnostics
import process_guard
import conversation_state as cs
from autonomy import route_scope
from project_store import ProjectStore
from agent import Agent


class Config:
    def __init__(self, bad=False):
        self.data = {'accounts': {'acct': {'id': 'acct', 'provider': 'Copilot365',
                                          'alias': 'M365', 'generation': 'g1'}},
                     'routes': [{'provider': 'Copilot365', 'model': 'm', 'endpoint': '',
                                 'account_id': {'url': 'wss://example'} if bad else 'acct'}]}
    def secret(self, aid):
        return 'secret-value'
    def redact(self, text):
        return str(text).replace('secret-value', '[OMITIDO]')


class FakeAPI:
    provider = 'Copilot365'
    model = 'm'
    endpoint = ''
    key = ''
    last_usage = {}
    neutral = False
    def __init__(self, bad=False):
        self.config = Config(bad)
        self.routes = self.config.data['routes']
    def request(self, conversation, declarations):
        return {}, json.dumps({'reply': 'ok'}), []


class TypeBoundaryTests(unittest.TestCase):
    def setUp(self):
        diagnostics.clear_rejections()

    def test_as_key_never_hashes_a_dict_or_list(self):
        self.assertEqual(diagnostics.as_key({'a': 1}, 'x'), '')
        self.assertEqual(diagnostics.as_key([1, 2], 'y', 'fallback'), 'fallback')
        self.assertEqual(diagnostics.as_key('hola'), 'hola')
        self.assertEqual(len(diagnostics.rejections()), 2)

    def test_corrupt_account_id_no_longer_raises_unhashable(self):
        api = FakeAPI(bad=True)
        self.assertEqual(cs.keys(api), {})
        self.assertIsNone(cs.pending({}, api))
        self.assertTrue(any(r['field'] == 'route.account_id' for r in diagnostics.rejections()))

    def test_valid_account_id_still_works(self):
        keys = cs.keys(FakeAPI())
        self.assertEqual(len(keys), 1)
        self.assertIn('acct', keys)

    def test_agent_turn_does_not_raise_unhashable_with_corrupt_config(self):
        with tempfile.TemporaryDirectory() as d:
            store = ProjectStore(d)
            p = store.create('Tema de prueba')
            store.save(p)
            try:
                Agent(store, FakeAPI(bad=True)).turn(p['id'], 'Hola')
            except TypeError as e:
                self.assertNotIn('unhashable', str(e))
            except Exception:
                pass  # any other controlled failure is acceptable; no raw hash error
        self.assertFalse(any('unhashable' in r['shape'] for r in diagnostics.rejections()))

    def test_route_scope_with_dict_account_id_returns_strings(self):
        scope = route_scope(FakeAPI(bad=True))
        self.assertTrue(all(isinstance(x, str) for item in scope for x in item))

    def test_guide_rule_with_dict_key_is_normalized(self):
        from guide_rules import approve
        p = {'facts': {}, 'materials': []}
        result = approve(p, {'name': 'Guía', 'id': 'x', 'sha256': 'y'},
                         [{'key': {'bad': 1}, 'value': 'A4', 'evidence': 'A4', 'status': 'ok'}], [0])
        self.assertIsInstance(result, dict)

    def test_config_redact_accepts_a_dict(self):
        self.assertIsInstance(Config().redact({'a': 1}), str)


class DiagnosticsTests(unittest.TestCase):
    def test_log_is_redacted_and_readable(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config()
            err = RuntimeError('fallo con secret-value y sk-ABCDEFGHIJKLMNOP')
            try:
                raise err
            except RuntimeError:
                path, record = diagnostics.log_exception(err, err.__traceback__,
                                                        {'action': 'click'}, cfg, d)
            self.assertTrue(path and path.is_file())
            raw = path.read_text('utf-8')
            self.assertNotIn('secret-value', raw)
            self.assertNotIn('sk-ABCDEFGHIJKLMNOP', raw)
            self.assertEqual(record['context']['action'], 'click')
            self.assertEqual(record['kind'], 'RuntimeError')
            self.assertEqual(len(diagnostics.recent(1, d)), 1)
            self.assertIn('Diagnóstico', diagnostics.friendly(err, path, cfg))

    def test_friendly_never_includes_raw_interpreter_message(self):
        e = TypeError("cannot use 'dict' as a dict key (unhashable type: 'dict')")
        text = diagnostics.friendly(e, Path('/tmp/x.json'))
        self.assertNotIn('unhashable type', text)
        self.assertIn('TypeError', text)

    def test_wrap_excepthook_restores(self):
        old = sys.excepthook
        previous = diagnostics.wrap_excepthook(Config(), tempfile.mkdtemp())
        try:
            self.assertIs(previous, old)
            self.assertIsNot(sys.excepthook, old)
        finally:
            sys.excepthook = old


class ProcessGuardTests(unittest.TestCase):
    def test_close_all_terminates_only_tracked_children(self):
        class FakeProc:
            def __init__(self):
                self.terminated = False
                self.killed = False
            def poll(self): return None
            def terminate(self): self.terminated = True
            def wait(self, timeout=None): return 0
            def kill(self): self.killed = True
        import subprocess
        original = subprocess.Popen
        proc = FakeProc()
        try:
            process_guard.start_tracking()
            process_guard._original = lambda *a, **k: proc
            subprocess.Popen(['fake.exe'])
            self.assertEqual(process_guard.count(), 1)
            self.assertEqual(process_guard.close_all(), 1)
            self.assertTrue(proc.terminated)
            self.assertEqual(process_guard.count(), 0)
        finally:
            subprocess.Popen = original
            process_guard.stop_tracking()

    def test_settings_dialog_closes_children_on_failure(self):
        source = (ROOT / 'settings_dialog.py').read_text('utf-8')
        self.assertIn('process_guard.close_all()', source)
        self.assertIn('finally:', source)


class AppWiringTests(unittest.TestCase):
    def test_app_logs_instead_of_showing_raw_exception(self):
        source = (ROOT / 'app.py').read_text('utf-8')
        self.assertIn('diagnostics.wrap_excepthook', source)
        self.assertIn('diagnostics.friendly', source)
        self.assertIn('diagnostics.log_exception', source)
        self.assertIn("'Copiar diagnóstico',self.copy_diagnostic", source)

    def test_agent_turn_wraps_preparation_in_logging(self):
        source = (ROOT / 'agent.py').read_text('utf-8')
        self.assertIn("'origin':'Agent.turn'", source)
        self.assertIn('return self._turn(', source)
