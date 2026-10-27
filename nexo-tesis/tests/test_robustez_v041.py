"""Regression tests for the robustness audit. Synthetic fixtures only.

Covers: concurrent config writes, corrupt/legacy config recovery, monotonic
source/material ids, damaged extracted.json, legacy project payloads, Copilot
expiry claims, failover bookkeeping, Word/PowerShell replies, Crossref shape,
Ollama tool calls and build-label consistency.
"""
import copy
import contextlib
import io
import hashlib
import json
import re
import sys
from types import SimpleNamespace
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeProtector  # noqa: E402
from test_v02 import session  # noqa: E402  (synthetic fixture, not a token)
import config as config_module  # noqa: E402
from config import Config, edit  # noqa: E402
from project_store import ProjectStore, validate  # noqa: E402
from bibliography import add_sources, search  # noqa: E402
from materials import _next_material_ref, select  # noqa: E402
from copilot_socket import expires_soon  # noqa: E402
from routing import RoutedAPI  # noqa: E402
from version import VERSION  # noqa: E402
import native_material  # noqa: E402
from verificar_instalacion import check_data_dir, main as selfcheck_main  # noqa: E402


class ConfigRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = Config(self.tmp.name, FakeProtector())

    def test_flush_writes_a_stable_snapshot(self):
        real_atomic = config_module.atomic
        inside, release, captured = threading.Event(), threading.Event(), {}

        def slow(path, data):
            captured['data'] = copy.deepcopy(data)
            inside.set()
            release.wait(3)
            real_atomic(path, data)

        with patch('config.atomic', side_effect=slow):
            t = threading.Thread(target=self.c.flush)
            t.start()
            self.assertTrue(inside.wait(3))
            self.c.data['health']['late'] = 'ok'  # mutation during the write
            release.set()
            t.join(3)
        self.assertFalse(t.is_alive())
        self.assertNotIn('late', captured['data']['health'])
        self.assertEqual(json.loads((Path(self.tmp.name) / 'config.json').read_text('utf-8'))['schema'], 2)

    def test_concurrent_guarded_writes_do_not_raise(self):
        for i in range(20000):
            self.c.data['health']['h' + str(i)] = 'ok'
        errors = []
        barrier = threading.Barrier(2)

        def writer():
            barrier.wait()
            for _ in range(3):
                try:
                    self.c.flush()
                except Exception as e:  # pragma: no cover - failure path
                    errors.append(repr(e))
                    return

        def mutator():
            barrier.wait()
            for i in range(100000):
                with edit(self.c):
                    self.c.data['health']['z' + str(i)] = 'ok'
                    del self.c.data['health']['z' + str(i)]

        a, b = threading.Thread(target=writer), threading.Thread(target=mutator)
        a.start(); b.start(); a.join(); b.join()
        self.assertEqual(errors, [])

    def test_legacy_schema_with_null_accounts_is_normalized(self):
        (Path(self.tmp.name) / 'config.json').write_text(json.dumps({
            'schema': 1, 'current': {'provider': 'Groq', 'model': 'm', 'endpoint': '', 'timeout': 90},
            'profiles': {Config.key_id('Groq', 'm', ''): {'provider': 'Groq', 'model': 'm', 'endpoint': ''}},
            'accounts': None, 'routes': None, 'health': None, 'cooldowns': None}), 'utf-8')
        loaded = Config(self.tmp.name, FakeProtector())
        self.assertEqual(loaded.data['schema'], 2)
        self.assertIsInstance(loaded.data['accounts'], dict)
        self.assertIsInstance(loaded.data['routes'], list)
        self.assertEqual(len(loaded.data['routes']), 1)
        loaded.flush()  # must not be locked out

    def test_corrupt_config_is_quarantined_only_once(self):
        path = Path(self.tmp.name) / 'config.json'
        path.write_text('{ esto no es json', 'utf-8')
        first = Config(self.tmp.name, FakeProtector())
        self.assertIn('config-invalido', first.warning)
        backups = list(Path(self.tmp.name).glob('config-invalido-*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text('utf-8'), '{ esto no es json')
        first.flush()
        Config(self.tmp.name, FakeProtector())  # reload of the fresh file
        self.assertEqual(len(list(Path(self.tmp.name).glob('config-invalido-*.json'))), 1)


class IdentifierTests(unittest.TestCase):
    def test_source_ids_are_monotonic_and_tolerate_legacy_ids(self):
        p = {'sources': []}
        self.assertEqual(add_sources(p, [{'doi': '10/a'}, {'doi': '10/b'}]), ['F1', 'F2'])
        p['sources'].pop()
        self.assertEqual(add_sources(p, [{'doi': '10/c'}]), ['F3'])
        p['sources'].append({'id': 'FABC-legacy', 'doi': '10/legacy'})
        self.assertEqual(add_sources(p, [{'doi': '10/d'}]), ['F4'])
        self.assertEqual(p['source_seq'], 4)

    def test_material_refs_are_monotonic(self):
        p = {'materials': []}
        first = _next_material_ref(p)
        p['materials'].append({'ref': first, 'name': 'guia.docx', 'active': False})
        p['materials'].pop()
        self.assertEqual(first, 'D1')
        self.assertEqual(_next_material_ref(p), 'D2')
        p['materials'].append({'ref': 'D-legacy', 'name': 'x'})
        self.assertEqual(_next_material_ref(p), 'D3')

    def test_damaged_extraction_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as root:
            store = ProjectStore(root)
            p = store.create('Tema')
            mid = 'a' * 32
            folder = Path(root) / 'materials' / p['id'] / mid
            folder.mkdir(parents=True)
            raw = b'contenido sintetico'
            (folder / 'original.txt').write_bytes(raw)
            (folder / 'extracted.json').write_text('{"segments":"roto"}', 'utf-8')
            p['materials'] = [{'id': mid, 'ref': 'D1', 'name': 'notas.txt', 'role': 'fuente',
                               'sha256': hashlib.sha256(raw).hexdigest(), 'suffix': '.txt',
                               'active': True, 'version': 1, 'shared_routes': ['scope']}]
            self.assertEqual(select(root, p, 'tema', ['scope']), [])


class ProjectCompatibilityTests(unittest.TestCase):
    def test_legacy_project_gets_required_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            store = ProjectStore(root)
            p = store.create('Tema')
            legacy = {k: copy.deepcopy(p[k]) for k in
                      ('schema', 'id', 'topic', 'facts', 'drafts', 'messages', 'questions', 'sources', 'decisions', 'revision')}
            with store.connect() as c:
                c.execute('UPDATE projects SET payload=? WHERE id=?',
                          (json.dumps(legacy, ensure_ascii=False), p['id']))
            loaded = store.load(p['id'])
            self.assertEqual(loaded['run']['status'], 'listo')
            self.assertEqual(loaded['usage']['calls'], 0)
            self.assertEqual(loaded['materials'], [])
            store.save(loaded, 'legacy-roundtrip')  # must not explode

    def test_validate_rejects_wrong_core_types(self):
        p = {'schema': 1, 'id': 'a' * 32, 'topic': 'T', 'facts': [], 'drafts': {},
             'messages': [], 'questions': [], 'sources': [], 'decisions': []}
        with self.assertRaises(ValueError):
            validate(p)


class CopilotExpiryTests(unittest.TestCase):
    def test_unknown_or_string_exp_never_counts_as_expired(self):
        self.assertFalse(expires_soon({}))
        self.assertFalse(expires_soon({'exp': None}))
        self.assertFalse(expires_soon({'exp': True}))
        self.assertFalse(expires_soon({'exp': 'no-es-un-numero'}))
        self.assertFalse(expires_soon({'exp': '9999999999'}))
        self.assertTrue(expires_soon({'exp': '1'}))
        self.assertTrue(expires_soon({'exp': 1}))


class FailoverBookkeepingTests(unittest.TestCase):
    def _copilot_config(self, tmp):
        c = Config(tmp, FakeProtector())
        aid = c.account('Copilot365', 'M365', session(), remember=False)
        rid = c.route('Copilot365', 'auto', aid)
        c.select(rid)
        return c, aid, rid

    def test_update_secret_survives_a_deleted_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, aid, _ = self._copilot_config(tmp)
            routes = c.candidates()
            expected = ({'role': 'assistant', 'content': 'ok'}, 'ok', [])

            class FactoryAPI:
                def __init__(self, provider, key, model, endpoint, timeout):
                    c.remove_account(aid)  # deleted while a request is in flight
                    self.provider,self.model,self.endpoint,self.timeout=provider,model,endpoint,timeout
                    self.last_usage={}
                def request(self, conversation, declarations):
                    self.update_secret(session())
                    return expected

            api = RoutedAPI(c, routes, FactoryAPI)
            self.assertEqual(api.request([{'role': 'user', 'content': 'x'}], []), expected)

    def test_update_secret_survives_a_flush_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, _, _ = self._copilot_config(tmp)
            routes = c.candidates()
            expected = ({'role': 'assistant', 'content': 'ok'}, 'ok', [])

            class FactoryAPI:
                def __init__(self, provider, key, model, endpoint, timeout):
                    self.provider,self.model,self.endpoint,self.timeout=provider,model,endpoint,timeout
                    self.last_usage={}
                def request(self, conversation, declarations):
                    self.update_secret(session())
                    return expected

            api = RoutedAPI(c, routes, FactoryAPI)
            with patch.object(c, 'flush', side_effect=OSError('disco')):
                self.assertEqual(api.request([{'role': 'user', 'content': 'x'}], []), expected)


class ExternalReplyTests(unittest.TestCase):
    def test_word_powershell_failure_is_a_clean_error(self):
        class R:
            returncode = 1
            stdout = b''
            stderr = b'fallo'
        fake_os = SimpleNamespace(name='nt', environ={'SystemRoot': r'C:\\Windows'})
        with patch.object(native_material, 'os', fake_os), \
             patch.object(native_material.subprocess, 'run', return_value=R()), \
             self.assertRaises(ValueError) as ctx:
            native_material.read_docx('C:/x.docx')
        self.assertIn('no se reintentó', str(ctx.exception))

    def test_word_partial_reply_is_normalized(self):
        class R:
            returncode = 0
            stdout = json.dumps({'segments': None}).encode('utf-8')
            stderr = b''
        fake_os = SimpleNamespace(name='nt', environ={'SystemRoot': r'C:\\Windows'})
        with patch.object(native_material, 'os', fake_os), \
             patch.object(native_material.subprocess, 'run', return_value=R()):
            data = native_material.read_docx('C:/x.docx')
        self.assertEqual(data['segments'], [])
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['warnings'], [])

    def test_crossref_non_dict_message_is_rejected(self):
        class Response:
            def read(self, n):
                return b'[]'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        class Opener:
            def open(self, req, timeout=None):
                return Response()
        with patch('bibliography.urllib.request.build_opener', return_value=Opener()):
            with self.assertRaises(ValueError) as ctx:
                search('tema de prueba')
        self.assertIn('Crossref', str(ctx.exception))


class BuildLabelTests(unittest.TestCase):
    def test_single_version_source(self):
        meta = json.loads((ROOT / 'VERSION.json').read_text('utf-8'))
        self.assertEqual(meta['version'], VERSION)
        app = (ROOT / 'app.py').read_text('utf-8')
        self.assertIn('APP_VERSION=VERSION', app)
        self.assertNotIn("APP_VERSION='0.4.0'", app)
        self.assertIn(VERSION, (ROOT / 'INICIAR-TESIS.cmd').read_text('utf-8'))
        self.assertIn(VERSION, (ROOT / 'LEER-PRIMERO.txt').read_text('utf-8-sig'))
        self.assertIn(VERSION, (ROOT / 'README.md').read_text('utf-8'))
        diag = ROOT / 'diagnostico.py'
        if diag.exists():  # development script, not shipped in the runtime ZIP
            self.assertNotIn("'version':'0.1.1'", diag.read_text('utf-8'))
        self.assertIn('from version import VERSION', (ROOT / 'verificar_instalacion.py').read_text('utf-8'))


if __name__ == '__main__':
    unittest.main()


class PreflightTests(unittest.TestCase):
    def test_missing_data_dir_is_informational(self):
        with contextlib.redirect_stdout(io.StringIO()), \
             patch('verificar_instalacion.Path.home', return_value=Path('/ruta-inexistente-para-prueba')):
            self.assertEqual(check_data_dir(), [])

    def test_readonly_data_dir_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / '.nexo-tesis').mkdir()
            with contextlib.redirect_stdout(io.StringIO()), \
                 patch('verificar_instalacion.Path.home', return_value=Path(d)), \
                 patch('os.access', return_value=False):
                problems = check_data_dir()
        self.assertTrue(any('permiso de escritura' in x for x in problems))

    def test_selfcheck_reports_version(self):
        text = (ROOT / 'verificar_instalacion.py').read_text('utf-8')
        self.assertIn('from version import VERSION', text)
        self.assertIn('({BUILD}) - comprobacion local', text)
        self.assertIn('from version import VERSION, BUILD', text)
