"""Voice state, installer, child protocol and native synthesis fixtures.
No physical microphone is opened and no real speech is played by these tests.
"""
import asyncio
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile
from voice import VoiceFlow, command_of, speech_text, MODEL_NAME
from voice_assets import REQUIRED_MODEL_FILES
from prepare_voice import validate_archive, install
from settings import Settings
import speech_native

class FlowTests(unittest.TestCase):
    def setUp(self):self.now=10;self.flow=VoiceFlow(lambda:self.now)
    def test_off_by_default(self):self.assertFalse(self.flow.active)
    def test_inactive_final_cannot_arm_send(self):
        self.flow.final(True,3);self.now=100;self.assertFalse(self.flow.take_due(True))
    def test_deadline_and_single_send(self):
        self.flow.enable();self.flow.final(True,3);self.assertFalse(self.flow.take_due(True));self.now=13
        self.assertTrue(self.flow.take_due(True));self.assertFalse(self.flow.take_due(True))
    def test_partial_extends_deadline(self):
        self.flow.enable();self.flow.final(True,3);self.now=12;self.flow.partial(3);self.now=14
        self.assertFalse(self.flow.take_due(True));self.now=15;self.assertTrue(self.flow.take_due(True))
    def test_low_confidence_requires_manual_review(self):
        self.flow.enable();self.flow.final(True,3,.4);self.now=100;self.assertFalse(self.flow.take_due(True));self.assertTrue(self.flow.review_required)
    def test_later_confident_phrase_does_not_bypass_review(self):
        self.flow.enable();self.flow.final(True,3,.4);self.flow.final(True,3,.99);self.now=100;self.assertFalse(self.flow.take_due(True))
    def test_manual_submission_resets_review(self):
        self.flow.enable();self.flow.final(True,3,.4);self.flow.sent();self.assertFalse(self.flow.review_required)
    def test_dictation_only_does_not_autosend(self):
        self.flow.enable();self.flow.final(False,3);self.now=100;self.assertFalse(self.flow.take_due(True));self.assertTrue(self.flow.pending)
    def test_blocked_conditions_cannot_send(self):
        self.flow.enable();self.flow.final(True,3);self.now=100;self.assertFalse(self.flow.take_due(False))
    def test_cancel_removes_queued_send(self):
        self.flow.enable();self.flow.final(True,3);self.flow.cancel_pending();self.now=100;self.assertFalse(self.flow.take_due(True))
    def test_disable_clears_queue(self):
        self.flow.enable();self.flow.final(True,3);self.flow.disable();self.now=100;self.assertFalse(self.flow.take_due(True))
    def test_enable_does_not_replay_old_pending(self):
        self.flow.enable();self.flow.final(True,3);self.flow.disable();self.flow.enable();self.now=100;self.assertFalse(self.flow.take_due(True))
    def test_commands_need_exact_wake_phrase(self):
        self.assertEqual(command_of('Nexo, apagar micrófono.'),'off');self.assertEqual(command_of('Nexo enviar'),'send')
        self.assertIsNone(command_of('sí'));self.assertIsNone(command_of('aprobar'));self.assertIsNone(command_of('Explícame cómo cancelar una tarea'))
    def test_speech_plain_text(self):
        result=speech_text('# Título\n**Texto** [fuente](https://example.com)\n```python\nprint(1)\n```')
        self.assertIn('Título',result);self.assertNotIn('https://',result);self.assertNotIn('print(1)',result);self.assertIn('omitido',result)
    def test_mic_activation_not_persisted(self):
        with tempfile.TemporaryDirectory() as t:
            settings=Settings(t);settings.save_preferences({'voice_active':True,'voice_auto_send':False})
            loaded=Settings(t);self.assertNotIn('voice_active',loaded.data['preferences']);self.assertFalse(loaded.data['preferences']['voice_auto_send'])

class InstallerTests(unittest.TestCase):
    def archive(self,paths):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            for name,value in paths:z.writestr(name,value)
        data.seek(0);return zipfile.ZipFile(data)
    def test_archive_expected_layout(self):
        with self.archive([(MODEL_NAME+'/am/final.mdl',b'model')]) as z:validate_archive(z)
    def test_archive_escape_rejected(self):
        for bad in ['../escape',MODEL_NAME+'/../../escape','/absolute','wrong-model/am/final.mdl',MODEL_NAME+'\\escape',MODEL_NAME+'/file:ads']:
            with self.subTest(path=bad),self.archive([(MODEL_NAME+'/am/final.mdl',b'model'),(bad,b'x')]) as z,self.assertRaises(ValueError):validate_archive(z)
    def test_archive_symlink_rejected(self):
        info=zipfile.ZipInfo(MODEL_NAME+'/link');info.external_attr=(stat.S_IFLNK|0o777)<<16
        with self.archive([(MODEL_NAME+'/am/final.mdl',b'model'),(info,b'elsewhere')]) as z,self.assertRaises(ValueError):validate_archive(z)
    def test_wrong_hash_never_installed(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);source=p/'wrong.zip';source.write_bytes(b'not the model')
            with self.assertRaises(RuntimeError):install(p/'destination',source)
            self.assertFalse((p/'destination').exists())
    def test_existing_model_not_replaced(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'model'
            for name in REQUIRED_MODEL_FILES:
                file=p/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'existing')
            self.assertIn('no se modificó',install(p));self.assertEqual((p/'am/final.mdl').read_bytes(),b'existing')
    def test_missing_model_child_returns_error_without_mic(self):
        with tempfile.TemporaryDirectory() as t:
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('speech_recorder.py')),'--model',str(Path(t)/'absent')],input='',capture_output=True,text=True,encoding='utf-8',timeout=10)
            event=json.loads(result.stdout.strip());self.assertEqual(event['type'],'error');self.assertEqual(result.returncode,1)

class NativeFixtureTests(unittest.TestCase):
    def invoke(self,mode,payload,voice_language='es-MX'):
        # Fake WinRT projections exercise lifecycle, not Windows audio itself.
        selected=[];closed=[]
        voice=types.SimpleNamespace(id='voice-fixture',display_name='Voz de prueba',language=voice_language)
        class Stream:
            def close(self):closed.append('stream')
        class Synth:
            all_voices=[voice]
            def __init__(self):self.options=types.SimpleNamespace(speaking_rate=1)
            async def synthesize_text_to_stream_async(self,text):selected.append((self.voice.language,text));return Stream()
            def close(self):closed.append('synth')
        class Player:
            def add_media_ended(self,callback):self.callback=callback;return 1
            def add_media_failed(self,callback):return 2
            def set_stream_source(self,stream):pass
            def play(self):self.callback(self,None)
            def pause(self):pass
            def remove_media_ended(self,token):pass
            def remove_media_failed(self,token):pass
            def close(self):closed.append('player')
        modules={}
        for name in ['winrt','winrt.windows','winrt.windows.media','winrt.windows.media.speechsynthesis','winrt.windows.media.playback','winrt.windows.foundation','winrt.windows.foundation.collections','winrt.windows.storage','winrt.windows.storage.streams']:
            modules[name]=types.ModuleType(name)
        modules['winrt.windows.media.speechsynthesis'].SpeechSynthesizer=Synth
        modules['winrt.windows.media.playback'].MediaPlayer=Player
        modules['winrt.windows.media.playback'].MediaPlayerAudioCategory=types.SimpleNamespace(SPEECH=1)
        for name,module in modules.items():
            if '.' in name:
                parent,attr=name.rsplit('.',1);setattr(modules[parent],attr,module)
        with patch.dict(sys.modules,modules),patch('speech_native.os.name','nt'):
            result=asyncio.run(speech_native.native(mode,payload))
        return result,selected,closed
    def test_native_voice_list(self):
        result,selected,_=self.invoke('voices',{});self.assertEqual(result['voices'][0]['language'],'es-MX');self.assertEqual(selected,[])
    def test_speaks_plain_text_with_exact_culture(self):
        result,selected,closed=self.invoke('speak',{'text':'Hola México','language':'es-MX'})
        self.assertTrue(result['ok']);self.assertEqual(selected,[('es-MX','Hola México')]);self.assertEqual(set(closed),{'stream','synth','player'})
    def test_no_silent_english_fallback(self):
        with self.assertRaisesRegex(RuntimeError,'No se encontró'):self.invoke('speak',{'text':'Hola','language':'es-MX'},voice_language='en-US')
    def test_selected_voice_id_explicit(self):
        result,selected,_=self.invoke('speak',{'text':'Hola','language':'es-MX','voice_id':'voice-fixture'},voice_language='es-ES')
        self.assertEqual(result['language'],'es-ES')
    def test_invalid_rate_rejected(self):
        with self.assertRaises(ValueError):self.invoke('speak',{'text':'Hola','rate':100})
    def test_excessive_text_not_silently_truncated(self):
        with self.assertRaises(ValueError):self.invoke('speak',{'text':'a'*12001})

if __name__=='__main__':unittest.main(verbosity=2)
