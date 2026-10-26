import io,json,tempfile,unittest,urllib.error
from unittest.mock import patch
from providers import API,PROVIDERS
from config import Config
from test_core import FakeProtector
from test_providers import Response

class GeminiUpdateTests(unittest.TestCase):
    def test_default_matches_reported_replacement(self):self.assertEqual(PROVIDERS['Gemini'],'gemini-3.8-flash')
    def test_models_prefix_normalized(self):self.assertEqual(API('Gemini','fake','models/gemini-3.8-flash').model,'gemini-3.8-flash')
    def test_current_endpoint_and_json_payload(self):
        captured=[]
        def fetch(req,timeout):captured.append(req);return Response({'candidates':[{'content':{'role':'model','parts':[{'text':'{"reply":"fixture"}'}]}}]})
        with patch('providers.open_remote',fetch):API('Gemini','fake','models/gemini-3.8-flash').request([{'role':'user','parts':[{'text':'test'}]}],[])
        self.assertEqual(captured[0].full_url,'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent')
        self.assertEqual(json.loads(captured[0].data)['generationConfig']['responseMimeType'],'application/json')
    def test_404_actionable_and_no_retry(self):
        body=json.dumps({'error':{'message':'This model is no longer available to new users. fake-secret'}}).encode()
        error=urllib.error.HTTPError('https://example.invalid',404,'NOT_FOUND',{},io.BytesIO(body))
        with patch('providers.open_remote',side_effect=error) as fetch:
            with self.assertRaisesRegex(RuntimeError,'gemini-3.8-flash') as caught:API('Gemini','fake-secret','gemini-2.5-flash').request([],[])
            self.assertEqual(fetch.call_count,1);self.assertIn('MISMO proyecto',str(caught.exception));self.assertNotIn('fake-secret',str(caught.exception))
    def test_other_model_not_forcibly_migrated(self):
        error=urllib.error.HTTPError('https://example.invalid',404,'NOT_FOUND',{},io.BytesIO(b'not json'))
        with patch('providers.open_remote',side_effect=error):
            with self.assertRaisesRegex(RuntimeError,'Comprueba el identificador'):API('Gemini','key','some-other-model').request([],[])
    def test_normalized_profile_and_old_profile_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            c=Config(d,FakeProtector());c.save('Gemini','gemini-2.5-flash','','OLD',True)
            c.save('Gemini','models/gemini-3.8-flash','','NEW',True)
            self.assertEqual(c.data['current']['model'],'gemini-3.8-flash');self.assertEqual(c.key('Gemini','gemini-2.5-flash',''),'OLD');self.assertEqual(c.key('Gemini','models/gemini-3.8-flash',''),'NEW')
    def test_load_does_not_switch_current_model_without_action(self):
        with tempfile.TemporaryDirectory() as d:
            c=Config(d,FakeProtector());c.save('Gemini','gemini-2.5-flash','','KEY',True)
            loaded=Config(d,FakeProtector());self.assertEqual(loaded.data['current']['model'],'gemini-2.5-flash')
