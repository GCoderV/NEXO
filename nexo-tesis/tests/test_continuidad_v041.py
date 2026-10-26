"""Copilot continuity 0.4.1-dev: local, offline verification of the fix.

Covers persistence/rotation/uncertainty/account identity, the isolated affinity
header, incremental context and revocation. These are LOCAL checks with synthetic
fixtures. They are NOT proof of Microsoft server recall, Word COM, DPAPI or an
authenticated Copilot session (see contexto/CONTINUIDAD-COPILOT-IMPLEMENTACION.md).
"""
import base64
import copy
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import conversation_state as cs
from context_policy import incremental, record_ledger, snapshot
from agent import Agent, context
from config import Config
from copilot_socket import (ROUTING_HEADER, RS, SignalDecoder, capture_info, complete,
                            identity_fingerprint, opening_headers, parse_url, sanitize_frame,
                            turn_counter)
from prompt_policy import BASE, incremental_instructions, instructions
from project_store import ProjectStore, set_fact
from test_core import FakeProtector


def make_session(oid='user-1', tid='tenant-1', exp=None):
    """Synthetic capture fixture. It is NOT an authentication token."""
    body = {'oid': oid, 'tid': tid, 'exp': exp or time.time() + 3600}
    token = 'fixture.' + base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip('=') + '.not-a-signature'
    frame = {'type': 4, 'target': 'chat', 'arguments': [
        {'source': 'officedesktop', 'optionsSets': ['test'], 'message': {'text': 'test', 'author': 'user'}}]}
    return json.dumps({'url': 'wss://substrate.office.com/m365Copilot/Chathub/?licenseType=Starter&access_token=' + token,
                       'frame': sanitize_frame(frame)})


def token_of(secret):
    return parse_url(json.loads(secret)['url'])[2]


class FakeConfig:
    def __init__(self, secret, generation='g1', identity=None):
        self.data = {'accounts': {'acc': {'generation': generation}}}
        if identity:
            self.data['accounts']['acc']['identity'] = identity
        self._secret = secret

    def secret(self, aid):
        return self._secret

    def redact(self, text):
        return str(text)


def fake_api(secret=None, generation='g1', identity=None, providers=('Copilot365',)):
    secret = secret or make_session()
    return SimpleNamespace(
        routes=[{'provider': p, 'account_id': 'acc', 'endpoint': '', 'model': 'auto', 'id': 'r' + str(i)}
                for i, p in enumerate(providers)],
        config=FakeConfig(secret, generation, identity), provider=providers[0],
        instructions='', last_usage={}, remote={}, project_id='', neutral=True,
        stop=threading.Event(), emit=lambda s: None, trace=[], attempts=0, route_identity='Copilot365 / test / auto')


def slot(turns=0, **extra):
    value = {'conversation': str(uuid.uuid4()), 'session': str(uuid.uuid4()),
             'turns': turns, 'status': cs.ACTIVE, 'verified': False}
    value.update(extra)
    return value


class RecordingAPI:
    """Model double that keeps the persistent remote slot like the real transport."""
    neutral = True
    provider = 'Copilot365'

    def __init__(self, secret=None, providers=('Copilot365',), fail=None):
        self.routes = [{'provider': p, 'account_id': 'acc', 'endpoint': '', 'model': 'auto', 'id': 'r' + str(i)}
                       for i, p in enumerate(providers)]
        self.config = FakeConfig(secret or make_session())
        self.requests = []
        self.instructions = ''
        self.last_usage = {}
        self.remote = {}
        self.project_id = ''
        self.stop = threading.Event()
        self.emit = lambda s: None
        self.trace = []
        self.attempts = 0
        self.route_identity = 'Copilot365 / test / auto'
        self.fail = fail

    def request(self, conversation, declarations):
        self.requests.append((copy.deepcopy(conversation), self.instructions))
        if self.fail:
            raise self.fail
        for value in self.remote.values():
            if isinstance(value, dict):
                value['turns'] = value.get('turns', 0) + 1
        return {}, json.dumps({'reply': 'De acuerdo.'}), []


class FakeSocket:
    """Minimal SignalR peer: handshake, one text frame, end-of-stream."""
    def __init__(self, turn=None):
        extra = '' if turn is None else ', "turnNumber": %d' % turn
        self.frames = iter(['{}' + RS,
                            json.dumps({'type': 1, 'arguments': [
                                {'writeAtCursor': '{"reply":"ok"}', 'turnNumber': turn} if turn is not None
                                else {'writeAtCursor': '{"reply":"ok"}'}]}) + RS,
                            '{"type":3}' + RS])
        self.sent = []
        self.closed = False
        self.connect_options = None

    def connect(self, url, **options):
        self.connect_options = (url, options)
        return self

    def settimeout(self, t):
        pass

    def send(self, data):
        self.sent.append(data)

    def recv(self):
        return next(self.frames)

    def close(self):
        self.closed = True


class IdentityTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_never_contains_credentials(self):
        a = make_session(exp=time.time() + 1000)
        b = make_session(exp=time.time() + 2000)
        self.assertNotEqual(token_of(a), token_of(b))
        first = identity_fingerprint(a)
        self.assertEqual(first, identity_fingerprint(b))
        self.assertRegex(first, r'^[a-f0-9]{64}$')
        self.assertNotIn(token_of(a), first)
        self.assertNotIn('access_token', first)
        self.assertNotEqual(first, identity_fingerprint(make_session(oid='other-user')))
        self.assertEqual(identity_fingerprint('not json'), '')

    def test_renewal_generation_does_not_change_thread_key(self):
        original = fake_api(make_session(), generation='g1')
        renewed = fake_api(make_session(exp=time.time() + 3000), generation='g2')
        self.assertNotEqual(cs.legacy_keys(original), cs.legacy_keys(renewed))
        self.assertEqual(cs.keys(original), cs.keys(renewed))
        p = {}
        cs.save(p, original, {'acc': slot(7)})
        self.assertEqual(cs.load(p, renewed)['acc']['conversation'], cs.load(p, original)['acc']['conversation'])

    def test_different_microsoft_account_gets_different_thread(self):
        a = fake_api(make_session())
        b = fake_api(make_session(tid='tenant-2'))
        self.assertNotEqual(cs.keys(a), cs.keys(b))
        p = {}
        cs.save(p, a, {'acc': slot()})
        self.assertEqual(cs.load(p, b), {})
        self.assertTrue(cs.load(p, a))

    def test_040_threads_are_migrated_not_orphaned(self):
        api = fake_api(make_session())
        p = {}
        cs.save(p, api, {'acc': slot(3)})
        old_key = cs.legacy_keys(api)['acc']
        new_key = cs.keys(api)['acc']
        self.assertNotEqual(old_key, new_key)
        conversation = p['copilot_threads'][new_key]['conversation']
        p['copilot_threads'] = {old_key: p['copilot_threads'].pop(new_key)}
        self.assertEqual(cs.load(p, api)['acc']['conversation'], conversation)
        self.assertIn(new_key, p['copilot_threads'])
        self.assertNotIn(old_key, p['copilot_threads'])

    def test_config_account_stores_identity_only(self):
        with tempfile.TemporaryDirectory() as d:
            c = Config(d, FakeProtector())
            aid = c.account('Copilot365', 'Cuenta', make_session(), remember=True)
            stored = c.data['accounts'][aid]['identity']
            self.assertEqual(stored, identity_fingerprint(make_session()))
            self.assertNotIn(token_of(make_session()), json.dumps(c.data))
            raw = (Path(d) / 'config.json').read_text('utf-8')
            self.assertNotIn('access_token', raw)
            self.assertNotIn(token_of(make_session()), raw)


class PersistenceTests(unittest.TestCase):
    def test_persistence_is_default(self):
        api = fake_api()
        p = {}
        cs.save(p, api, {'acc': slot()})
        self.assertTrue(cs.load(p, api))
        self.assertNotIn('copilot_continuity', p)

    def test_no_rotation_and_no_secret_in_project(self):
        api = fake_api()
        p = {}
        for turns in (40, 41, 4000):
            cs.save(p, api, {'acc': slot(turns, token='NEVER_STORE')})
            self.assertEqual(cs.load(p, api)['acc']['turns'], turns)
        dump = json.dumps(p)
        for forbidden in ('NEVER_STORE', 'access_token', ROUTING_HEADER, 'wss://', 'affinity'):
            self.assertNotIn(forbidden, dump)

    def test_uncertain_keeps_ids_and_blocks_until_decision(self):
        api = fake_api()
        p = {'copilot_ledger': {'snapshot': {'facts': 'x'}}}
        cs.save(p, api, {'acc': slot(5)})
        before = cs.load(p, api)['acc']['conversation']
        cs.save(p, api, {}, True)
        self.assertEqual(cs.load(p, api)['acc']['conversation'], before)
        self.assertEqual(cs.pending(p, api)['kind'], 'uncertain')
        self.assertNotIn('copilot_ledger', p)
        self.assertFalse(cs.can_increment(p, api))
        cs.resolve(p, api, 'keep')
        self.assertIsNone(cs.pending(p, api))
        self.assertEqual(cs.load(p, api)['acc']['conversation'], before)

    def test_rebind_drops_local_ids_only_on_explicit_decision(self):
        api = fake_api()
        p = {}
        cs.save(p, api, {'acc': slot()})
        cs.flag_rebind(p, 'material revocado')
        self.assertTrue(p['copilot_threads'])
        self.assertEqual(cs.pending(p, api)['kind'], 'rebind')
        cs.resolve(p, api, 'rebind')
        self.assertFalse(p.get('copilot_threads'))
        self.assertIsNone(cs.pending(p, api))

    def test_uncertainty_is_per_account_not_global_under_rotation(self):
        secrets = {'a1': make_session(oid='user-1'), 'a2': make_session(oid='user-2')}
        api = SimpleNamespace(
            routes=[{'provider': 'Copilot365', 'account_id': aid, 'endpoint': '', 'model': 'auto', 'id': aid}
                    for aid in ('a1', 'a2')],
            config=SimpleNamespace(data={'accounts': {'a1': {}, 'a2': {}}}, secret=lambda aid: secrets[aid]))
        # Two config entries for the SAME Microsoft identity share one chat.
        same = SimpleNamespace(
            routes=[{'provider': 'Copilot365', 'account_id': aid, 'endpoint': '', 'model': 'auto', 'id': aid}
                    for aid in ('a1', 'a2')],
            config=SimpleNamespace(data={'accounts': {'a1': {}, 'a2': {}}}, secret=lambda aid: secrets['a1']))
        self.assertEqual(len(set(cs.keys(same).values())), 1)
        p = {}
        cs.save(p, api, {'a1': slot(2), 'a2': slot(2)})
        loaded = cs.load(p, api)
        loaded['a1']['uncertain'] = True  # primera ruta falló tras enviar
        cs.save(p, api, loaded)
        statuses = {v['status'] for v in p['copilot_threads'].values()}
        self.assertEqual(statuses, {cs.ACTIVE, cs.UNCERTAIN})

    def test_switching_away_from_copilot_does_not_block_other_providers(self):
        api = fake_api()
        p = {}
        cs.save(p, api, {'acc': slot()})
        cs.save(p, api, {}, True)
        self.assertEqual(cs.pending(p, api)['kind'], 'uncertain')
        self.assertIsNone(cs.pending(p, SimpleNamespace(routes=[
            {'provider': 'Groq', 'account_id': 'acc', 'endpoint': '', 'model': 'x'}])))
        self.assertEqual(cs.pending(p)['kind'], 'uncertain')  # la UI sí la muestra

    def test_revocation_does_not_silently_start_another_chat(self):
        import materials
        p = {}
        cs.save(p, fake_api(), {'acc': slot()})
        materials.attach(p, {'id': 'D1', 'name': 'guia.txt', 'role': 'fuente'})
        materials.attach(p, {'id': 'D2', 'name': 'guia.txt', 'role': 'fuente'})
        self.assertTrue(p['copilot_rebind'])
        self.assertTrue(p['copilot_threads'])

    def test_verify_cannot_bypass_a_revocation_decision(self):
        api = fake_api()
        p = {}
        cs.save(p, api, {'acc': slot(verified=True)})
        cs.flag_rebind(p, 'archivo retirado')
        with self.assertRaisesRegex(ValueError, 'revocación pendiente'):
            cs.resolve(p, api, 'verify')
        self.assertEqual(cs.pending(p, api)['kind'], 'rebind')
        cs.resolve(p, api, 'keep')  # decisión explícita de conservar
        self.assertIsNone(cs.pending(p, api))
        self.assertFalse(cs.can_increment(p, api))  # exige volver a verificar

    def test_no_rebind_decision_when_no_chat_exists_yet(self):
        p = {}
        self.assertIsNone(cs.flag_rebind(p, 'sin chat previo'))
        self.assertNotIn('copilot_rebind', p)
        self.assertIsNone(cs.pending(p))

    def test_agent_blocks_without_sending_when_decision_pending(self):
        with tempfile.TemporaryDirectory() as d:
            s = ProjectStore(d)
            p = s.create('Tema')
            api = RecordingAPI()
            cs.save(p, api, {'acc': slot(2)})
            cs.flag_rebind(p, 'prueba')
            s.save(p, 'setup')
            a = RecordingAPI()
            with self.assertRaises(cs.ContinuityPending):
                Agent(s, a).turn(p['id'], 'Mensaje nuevo')
            self.assertFalse(a.requests)


class TransportTests(unittest.TestCase):
    def test_opening_header_uses_conversation_id_not_session(self):
        conversation, session = str(uuid.uuid4()), str(uuid.uuid4())
        self.assertEqual(opening_headers(conversation), [ROUTING_HEADER + ': ' + conversation])
        self.assertNotIn(session, opening_headers(conversation)[0])

    def test_complete_passes_header_on_opening_handshake_only_when_enabled(self):
        secret = make_session()
        for enabled in (True, False):
            peer = FakeSocket()
            remote = {'affinity': enabled}
            details = {}
            with patch('copilot_socket.websocket.WebSocket', return_value=peer):
                result = complete(secret, 'hola', 'auto', 10, remote=remote, details=details)
            self.assertEqual(result, '{"reply":"ok"}')
            url, options = peer.connect_options
            self.assertIn('ConversationId=' + remote['conversation'], url)
            params = parse_qs(urlsplit(url).query)
            # URL keeps the legacy session parameter; the header carries the ConversationId.
            self.assertEqual(params['XRoutingParameterSessionKey'], [remote['session']])
            self.assertNotEqual(params['XRoutingParameterSessionKey'], [remote['conversation']])
            if enabled:
                self.assertEqual(options['header'], [ROUTING_HEADER + ': ' + remote['conversation']])
            else:
                self.assertEqual(options['header'], [])
            self.assertEqual(details['continuity']['affinity_header'], enabled)
            self.assertEqual(remote['turns'], 1)

    def test_second_turn_reuses_ids_and_never_rotates_at_40(self):
        secret = make_session()
        remote = slot(40)
        for expected in (41, 42):
            peer = FakeSocket()
            with patch('copilot_socket.websocket.WebSocket', return_value=peer):
                complete(secret, 'mensaje', 'auto', 10, remote=remote)
            self.assertEqual(remote['turns'], expected)
            first = json.loads(peer.sent[1].split(RS)[0])
            self.assertFalse(first['arguments'][0]['isStartOfSession'])
            self.assertEqual(first['arguments'][0]['sessionId'], remote['session'])

    def test_uncertain_result_keeps_ids_initialized_before_send(self):
        secret = make_session()
        remote = {}
        peer = FakeSocket()
        peer.frames = iter(['{}' + RS, ''])
        with self.assertRaises(Exception):
            with patch('copilot_socket.websocket.WebSocket', return_value=peer):
                complete(secret, 'mensaje', 'auto', 10, remote=remote)
        self.assertIn('conversation', remote)
        self.assertIn('session', remote)
        self.assertEqual(remote['turns'], 0)
        self.assertTrue(remote['uncertain'])

    def test_turn_counter_regression_is_observable_not_fatal(self):
        self.assertIsNone(turn_counter({'type': 1}))
        self.assertEqual(turn_counter({'item': {'messages': [{'turnNumber': 4}]}}), 4)
        decoder = SignalDecoder(previous_turn=5)
        decoder.consume({'type': 1, 'turnNumber': 4})
        self.assertTrue(decoder.regression)
        decoder2 = SignalDecoder(previous_turn=3)
        decoder2.consume({'type': 1, 'turnNumber': 4})
        self.assertFalse(decoder2.regression)

    def test_six_messages_six_sockets_one_conversation(self):
        """Local equivalent of acceptance steps 2-4: ids survive, start flag only once."""
        secret = make_session()
        remote = {}
        sessions, conversations, starts = [], [], []
        for i in range(6):
            peer = FakeSocket()
            with patch('copilot_socket.websocket.WebSocket', return_value=peer):
                complete(secret, 'dato sintético %d' % i, 'auto', 10, remote=remote)
            frame = json.loads(peer.sent[1].split(RS)[0])['arguments'][0]
            query = parse_qs(urlsplit(peer.connect_options[0]).query)
            sessions.append(frame['sessionId'])
            conversations.append(query['ConversationId'][0])
            starts.append(frame['isStartOfSession'])
        self.assertEqual(len(set(sessions)), 1)
        self.assertEqual(len(set(conversations)), 1)
        self.assertEqual(starts, [True] + [False] * 5)
        self.assertEqual(remote['turns'], 6)
        self.assertEqual(remote['conversation'], conversations[0])

    def test_project_affinity_flag_applies_even_on_first_turn(self):
        class TransportAPI(RecordingAPI):
            def request(self, conversation, declarations):
                self.requests.append((copy.deepcopy(conversation), self.instructions))
                peer = FakeSocket()
                with patch('copilot_socket.websocket.WebSocket', return_value=peer):
                    complete(make_session(), 'prompt', 'auto', 10, remote=self.remote.get('acc', {}), details={})
                self.connect_options = peer.connect_options
                return {}, json.dumps({'reply': 'De acuerdo.'}), []

        with tempfile.TemporaryDirectory() as d:
            s = ProjectStore(d)
            disabled = s.create('Tema sin cabecera')
            disabled['copilot_affinity'] = False
            s.save(disabled, 'setup')
            a = TransportAPI()
            result = Agent(s, a).turn(disabled['id'], 'Primer mensaje')
            self.assertEqual(a.connect_options[1]['header'], [])
            self.assertTrue(result['copilot_threads'])  # el chat se crea igualmente
            enabled = s.create('Tema con cabecera')
            s.save(enabled, 'setup')
            b = TransportAPI()
            Agent(s, b).turn(enabled['id'], 'Primer mensaje')
            self.assertEqual(len(b.connect_options[1]['header']), 1)

    def test_login_and_capture_validation_unchanged(self):
        self.assertEqual(capture_info(make_session())[1]['oid'], 'user-1')
        with self.assertRaises(ValueError):
            capture_info('{"url":"wss://evil.invalid/x?access_token=a"}')


class IncrementalTests(unittest.TestCase):
    def project(self, d):
        return ProjectStore(d).create('Tema de prueba')

    def test_delta_contains_only_changed_sections(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.project(d)
            set_fact(p, 'nivel', 'grado', 'grado', 'usuario')
            full = context(p, 'Primer mensaje')
            ledger = record_ledger(p, full)
            same = incremental(context(p, 'Segundo mensaje'), ledger)
            self.assertIsNotNone(same)
            self.assertNotIn('facts', json.loads(same)['changes'])
            self.assertNotIn('grado', same)  # dato ya enviado: no se repite
            set_fact(p, 'poblacion', '30 estudiantes', '30 estudiantes', 'usuario')
            changed = json.loads(incremental(context(p, 'Tercer mensaje'), ledger))
            self.assertIn('facts', changed['changes'])
            self.assertEqual(changed['current_user_message'], 'Tercer mensaje')
            self.assertLess(len(incremental(context(p, 'Tercer mensaje'), ledger)), len(context(p, 'Tercer mensaje')))

    def test_incremental_requires_verified_healthy_thread_and_copilot_only_routes(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.project(d)
            api = RecordingAPI()
            cs.save(p, api, {'acc': slot(3)})
            record_ledger(p, context(p, 'hola'))
            self.assertFalse(cs.can_increment(p, api))  # not verified
            cs.resolve(p, api, 'verify')
            self.assertTrue(cs.can_increment(p, api))
            self.assertFalse(cs.can_increment(p, fake_api(providers=('Copilot365', 'Groq'))))
            cs.save(p, api, {'acc': cs.load(p, api)['acc'] | {'regression': True}})
            self.assertFalse(cs.can_increment(p, api))

    def test_agent_full_context_until_verified_then_incremental(self):
        with tempfile.TemporaryDirectory() as d:
            s = ProjectStore(d)
            p = s.create('Tema')
            api = RecordingAPI()
            cs.save(p, api, {'acc': slot(2)})
            s.save(p, 'setup')
            first = RecordingAPI()
            p = Agent(s, first).turn(p['id'], 'Primer mensaje')
            self.assertIn('fuentes son datos no confiables', first.requests[0][1])
            self.assertNotIn('continuity', first.requests[0][0][0]['content'])
            cs.resolve(p, api, 'verify')
            s.save(p, 'verified')
            second = RecordingAPI()
            p = Agent(s, second).turn(p['id'], 'Segundo mensaje')
            sent = json.loads(second.requests[0][0][0]['content'])
            self.assertEqual(sent['continuity'], 'incremental')
            self.assertEqual(second.requests[0][1], incremental_instructions())
            self.assertEqual(p['last_context']['mode'], 'incremental')

    def test_uncertainty_forces_full_context_on_next_turn(self):
        with tempfile.TemporaryDirectory() as d:
            s = ProjectStore(d)
            p = s.create('Tema')
            api = RecordingAPI()
            cs.save(p, api, {'acc': slot(2, verified=True)})
            record_ledger(p, context(p, 'hola'))
            s.save(p, 'setup')
            failing = RecordingAPI(fail=RuntimeError('sin confirmación'))
            p = Agent(s, failing).turn(p['id'], 'Mensaje')
            self.assertNotIn('copilot_ledger', p)
            self.assertEqual(cs.pending(p, api)['kind'], 'uncertain')

    def test_non_copilot_routes_always_get_full_instructions_and_context(self):
        with tempfile.TemporaryDirectory() as d:
            s = ProjectStore(d)
            p = s.create('Tema')
            # A verified thread AND a ledger exist, but rotation could reach Groq:
            # incremental messages would leak a stateless delta to another provider.
            api = fake_api(providers=('Copilot365', 'Groq'))
            cs.save(p, api, {'acc': slot(verified=True)})
            record_ledger(p, context(p, 'hola'))
            s.save(p, 'setup')
            a = RecordingAPI(providers=('Copilot365', 'Groq'))
            Agent(s, a).turn(p['id'], 'Mensaje')
            self.assertEqual(a.requests[0][1], instructions())
            self.assertNotIn('continuity', a.requests[0][0][0]['content'])

    def test_resume_with_refreshed_context_keeps_thread_ids(self):
        with tempfile.TemporaryDirectory() as d:
            s = ProjectStore(d)
            p = s.create('Tema')
            api = RecordingAPI()
            cs.save(p, api, {'acc': slot(6)})
            original = cs.load(p, api)['acc']['conversation']
            p['pending'] = {'id': 'op1', 'text': 'Mensaje original', 'origin': 'usuario', 'mid': 'm1',
                            'stage': 'model', 'iteration': 0, 'searched': False, 'notice': '',
                            'research': False, 'remote': cs.load(p, api), 'inflight': False,
                            'uncertain': False, 'revision': -1}
            s.save(p, 'pending')
            failing = RecordingAPI(fail=RuntimeError('corte'))
            p = Agent(s, failing).turn(p['id'], resume=True, refresh_context=True)
            self.assertEqual(p['pending']['remote']['acc']['conversation'], original)


if __name__ == '__main__':
    unittest.main()
