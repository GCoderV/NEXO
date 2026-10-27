"""Regression for the other two errors in the user's log.

- Gemini 404 "model no longer available": the provider itself names the
  replacement, so the route is healed and the request is sent once to the new
  model instead of failing forever (same account, same provider).
- HTTP 400 caused by JSON-mode parameters: one safe retry without that optional
  flag; any other 400 reports a redacted, bounded reason.
"""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeProtector  # noqa: E402
from test_providers import Response  # noqa: E402
from config import Config  # noqa: E402
from routing import RoutedAPI  # noqa: E402
from providers import API, ProviderError  # noqa: E402

NOT_FOUND_BODY = json.dumps({'error': {
    'code': 404, 'status': 'NOT_FOUND',
    'message': 'This model models/gemini-2.5-flash is no longer available to new users. '
               'Please update your code to use models/gemini-3.8-flash for the latest features.'}}).encode()

GEMINI_OK = {'candidates': [{'content': {'role': 'model',
             'parts': [{'text': '{"reply":"Marco teórico listo."}'}]}}]}
GROQ_OK = {'choices': [{'message': {'role': 'assistant', 'content': '{"reply":"ok"}'}}],
           'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}


def http_error(code, body):
    return urllib.error.HTTPError('https://example.invalid', code, 'ERR', {}, io.BytesIO(body))


class ModelHealingTests(unittest.TestCase):
    def _config(self, tmp):
        c = Config(tmp, FakeProtector())
        aid = c.account('Gemini', 'Cuenta', 'CLAVE-SINTETICA', remember=False)
        rid = c.route('Gemini', 'gemini-2.5-flash', aid)
        c.select(rid)
        return c, rid

    def test_404_heals_route_and_returns_the_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, rid = self._config(tmp)
            seen = []

            def fetch(req, timeout):
                seen.append(req.full_url)
                if len(seen) == 1:
                    raise http_error(404, NOT_FOUND_BODY)
                return Response(GEMINI_OK)

            api = RoutedAPI(c, c.candidates())
            with patch('providers.open_remote', fetch):
                message, text, calls = api.request([{'role': 'user', 'content': 'x'}], [])
            self.assertEqual(text, '{"reply":"Marco teórico listo."}')
            self.assertEqual(len(seen), 2)
            self.assertIn('gemini-2.5-flash', seen[0])
            self.assertIn('gemini-3.8-flash', seen[1])
            self.assertEqual(c.data['routes'][0]['model'], 'gemini-3.8-flash')
            self.assertEqual(c.data['current']['model'], 'gemini-3.8-flash')
            reloaded = Config(tmp, FakeProtector())
            self.assertEqual(reloaded.data['current']['model'], 'gemini-3.8-flash')

    def test_404_without_a_fixer_keeps_the_actionable_error(self):
        api = API('Gemini', 'fake-secret', 'gemini-2.5-flash')
        with patch('providers.open_remote', side_effect=http_error(404, NOT_FOUND_BODY)) as fetch:
            with self.assertRaises(ProviderError) as caught:
                api.request([], [])
        self.assertEqual(fetch.call_count, 1)
        self.assertIn('gemini-3.8-flash', str(caught.exception))
        self.assertNotIn('fake-secret', str(caught.exception))

    def test_other_404_is_not_rewritten(self):
        body = json.dumps({'error': {'message': 'Unknown model.'}}).encode()
        api = API('Gemini', 'key', 'some-other-model')
        with patch('providers.open_remote', side_effect=http_error(404, body)) as fetch:
            with self.assertRaises(ProviderError):
                api.request([], [])
        self.assertEqual(fetch.call_count, 1)


class BadRequestTests(unittest.TestCase):
    def test_400_from_response_format_retries_once_without_it(self):
        body = json.dumps({'error': {'message': 'response_format is not supported by this model'}}).encode()
        seen = []

        def fetch(req, timeout):
            seen.append(json.loads(req.data))
            if len(seen) == 1:
                raise http_error(400, body)
            return Response(GROQ_OK)

        api = API('Groq', 'fake', 'test')
        with patch('providers.open_remote', fetch):
            _, text, _ = api.request([{'role': 'user', 'content': 'x'}], [])
        self.assertEqual(text, '{"reply":"ok"}')
        self.assertEqual(len(seen), 2)
        self.assertIn('response_format', seen[0])
        self.assertNotIn('response_format', seen[1])

    def test_other_400_reports_a_redacted_reason(self):
        body = json.dumps({'error': {'message': 'Invalid value at https://example.invalid/aaa SECRET-KEY-LITERAL'}}).encode()
        api = API('Groq', 'SECRET-KEY-LITERAL', 'test')
        with patch('providers.open_remote', side_effect=http_error(400, body)) as fetch:
            with self.assertRaises(ProviderError) as caught:
                api.request([], [])
        self.assertEqual(fetch.call_count, 1)
        message = str(caught.exception)
        self.assertIn('HTTP 400', message)
        self.assertNotIn('SECRET-KEY-LITERAL', message)
        self.assertNotIn('https://example.invalid', message)


if __name__ == '__main__':
    unittest.main()
