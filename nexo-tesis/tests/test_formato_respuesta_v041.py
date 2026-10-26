"""Regression: chat models often wrap the academic JSON in prose or fences.

The host must still validate exactly one complete object (no repair call, no
invented content), but a correct draft buried in a polite preamble was being
rejected with "La respuesta no cumple el formato académico". All fixtures are
synthetic; no network, credentials or Microsoft session are used.
"""
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

from test_core import FakeAPI, reply  # noqa: E402
from project_store import ProjectStore  # noqa: E402
from agent import unpack, parse_json, format_reason, Agent  # noqa: E402
from autonomy import plan, order, AutonomousRunner, route_scope  # noqa: E402

TASK = {'section': 'delimitacion'}
GOOD = {'text': 'Delimitación concreta del proyecto de prueba.', 'sources': [], 'reply': 'Borrador listo.'}


def run_one_task(raw):
    """Run one autonomous task with a scripted response; return project and API."""
    tmp = tempfile.TemporaryDirectory()
    store = ProjectStore(tmp.name)
    p = store.create('Tema del proyecto')
    api = FakeAPI([raw])
    runner = AutonomousRunner(store, lambda: api, threading.Event())
    result = runner.run(p['id'], 1, authorized_scope=route_scope(api))
    tmp.cleanup()
    return result, api


class ParseJsonTests(unittest.TestCase):
    def test_plain_object_still_parses(self):
        self.assertEqual(parse_json(json.dumps(GOOD)), GOOD)

    def test_prose_before_and_after(self):
        raw = 'Claro, aquí tienes el apartado solicitado:\n' + json.dumps(GOOD, ensure_ascii=False) + '\n\nEspero que te sirva.'
        self.assertEqual(parse_json(raw)['text'], GOOD['text'])

    def test_fenced_block_with_language_and_trailing_note(self):
        raw = '```json\n' + json.dumps(GOOD, ensure_ascii=False) + '\n```\nNota: revisa las fuentes.'
        self.assertEqual(parse_json(raw)['text'], GOOD['text'])

    def test_braces_inside_strings_are_not_structure(self):
        obj = {'text': 'Se usa la notación {corchetes} y "comillas" en el texto.', 'reply': 'ok'}
        raw = 'Respuesta:\n' + json.dumps(obj, ensure_ascii=False) + '\nFin.'
        self.assertEqual(parse_json(raw)['text'], obj['text'])

    def test_trailing_comma_is_tolerated(self):
        raw = '{"text":"Borrador con coma final","sources":[],"reply":"Listo",}'
        self.assertEqual(parse_json(raw)['text'], 'Borrador con coma final')

    def test_stray_empty_object_in_prose_is_ignored(self):
        raw = 'El esquema es {} y el resultado:\n' + json.dumps(GOOD, ensure_ascii=False)
        self.assertEqual(parse_json(raw)['text'], GOOD['text'])

    def test_plain_prose_is_still_rejected(self):
        with self.assertRaises(ValueError):
            parse_json('Puedo ayudarte con ese apartado, pero necesito más datos.')
        with self.assertRaises(ValueError):
            parse_json('')


class UnpackTaskTests(unittest.TestCase):
    def test_minimal_task_contract_without_reply(self):
        r = unpack('{"text":"Objetivo concreto.","sources":[]}', TASK)
        self.assertEqual(r['drafts'][0]['section'], 'delimitacion')
        self.assertTrue(r['reply'])

    def test_drafts_without_section_sources_or_reply(self):
        raw = json.dumps({'drafts': [{'text': 'Texto del apartado.'}]})
        r = unpack(raw, TASK)
        self.assertEqual(r['drafts'][0]['section'], 'delimitacion')
        self.assertEqual(r['drafts'][0]['sources'], [])
        self.assertTrue(r['reply'])

    def test_facts_from_automatic_task_are_discarded_not_fatal(self):
        raw = json.dumps({'text': 'Texto válido.', 'facts': [{'key': 'metodologia', 'value': 'X', 'evidence': 'X'}]})
        r = unpack(raw, TASK)
        self.assertEqual(r.get('facts', []), [])
        self.assertEqual(r['drafts'][0]['text'], 'Texto válido.')

    def test_wrapped_task_response_unpacks(self):
        raw = 'Aquí está el borrador:\n```json\n' + json.dumps(GOOD) + '\n```\nUn saludo.'
        self.assertEqual(unpack(raw, TASK)['drafts'][0]['text'], GOOD['text'])

    def test_unknown_keys_still_rejected_in_dialogue(self):
        with self.assertRaises(ValueError):
            unpack(json.dumps({**reply(), 'powershell': 'bad'}))

    def test_unknown_keys_still_rejected_in_task(self):
        with self.assertRaises(ValueError):
            unpack(json.dumps({'text': 'Texto.', 'exec': 'rm -rf'}), TASK)

    def test_invalid_draft_still_rejected(self):
        with self.assertRaises(ValueError):
            unpack(json.dumps({'text': ''}), TASK)
        with self.assertRaises(ValueError):
            unpack(json.dumps({'drafts': [{'section': 'no_existe', 'text': 'Texto.'}]}), TASK)

    def test_reason_never_contains_model_output(self):
        secretish = 'NuncaMostrarEsteTexto'
        reason = format_reason(ValueError(secretish))
        self.assertNotIn(secretish, reason)
        self.assertIn('JSON', reason)
        self.assertIn('JSON', format_reason(KeyError(secretish)))


class EndToEndFormatTests(unittest.TestCase):
    def test_wrapped_response_saves_draft_instead_of_error_formato(self):
        raw = 'Por supuesto, aquí tienes el apartado:\n```json\n' + json.dumps(GOOD, ensure_ascii=False) + '\n```\nQuedo atento.'
        p, _ = run_one_task(raw)
        self.assertNotEqual(p['run']['status'], 'error_formato')
        self.assertIn('delimitacion', p['drafts'])
        self.assertEqual(p['drafts']['delimitacion']['text'], GOOD['text'])
        self.assertEqual(p['autonomy']['status'], 'completado')

    def test_truly_bad_response_still_stops_with_a_specific_reason(self):
        p, api = run_one_task('Lo siento, no puedo generar ese apartado.')
        self.assertEqual(p['run']['status'], 'error_formato')
        self.assertIn('pending', p)
        self.assertEqual(len(api.requests), 1)  # no repair call, no rotation
        system = '\n'.join(m['text'] for m in p['messages'] if m['role'] == 'system')
        self.assertIn('no se encontró un JSON completo', system)
        self.assertNotIn('Lo siento, no puedo', system)  # raw output never logged


if __name__ == '__main__':
    unittest.main()
