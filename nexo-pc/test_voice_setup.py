"""Regression: py -3 selects 3.15, while uv/Astral CPython 3.11 is installed.
No Windows installation is performed by these tests.
"""
import io
import contextlib
import os
import types
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from voice_setup import parse_launcher, compatible, choose_runtime, ensure_environment, install_voice, probe, deduplicate
import voice
import voice_setup

REPORTED=r''' -V:3.15[-64] *   C:\Users\viter\AppData\Local\Python\pythoncore-3.15-64\python.exe
 -V:Astral\CPython3.11.16 C:\Users\viter\AppData\Roaming\uv\python\cpython-3.11.16-windows-x86_64-none\python.exe
'''

def record(path,version=(3,11,16),bits=64,platform='win-amd64',implementation='cpython',gil_disabled=False):
    return {'path':str(path),'version':list(version),'bits':bits,'platform':platform,'implementation':implementation,'gil_disabled':gil_disabled}

class RuntimeSelectionTests(unittest.TestCase):
    def test_reported_launcher_finds_both_paths(self):
        found=parse_launcher(REPORTED);self.assertEqual(len(found),2);self.assertIn('pythoncore-3.15-64',found[0]);self.assertIn('uv\\python\\cpython-3.11.16',found[1])
    def test_chooses_reported_uv_311_not_default_315(self):
        paths=parse_launcher(REPORTED);result=choose_runtime([record(paths[0],(3,15,1)),record(paths[1])])
        self.assertEqual(result['path'],paths[1]);self.assertEqual(result['version'],[3,11,16])
    def test_default_315_is_not_compatible(self):self.assertFalse(compatible(record('p',(3,15,1))))
    def test_supported_cpython_versions(self):
        for v in [(3,11,16),(3,12,0),(3,13,5),(3,14,1)]:self.assertTrue(compatible(record('p',v)))
    def test_rejects_older_32bit_arm_and_pypy(self):
        for info in [record('p',(3,10,9)),record('p',bits=32,platform='win32'),record('p',platform='win-arm64'),record('p',implementation='pypy'),record('p',gil_disabled=True)]:self.assertFalse(compatible(info))
    def test_no_compatible_does_not_invent_or_download_runtime(self):self.assertIsNone(choose_runtime([record('p',(3,15,1))]))
    def test_prefer_existing_compatible_voice_env(self):
        result=choose_runtime([record('existing',(3,11,16)),record('newer',(3,14,1))],existing='existing');self.assertEqual(result['path'],'existing')
    def test_new_install_prefers_highest_compatible(self):
        result=choose_runtime([record('older'),record('newer',(3,14,1)),record('unsupported',(3,15,1))]);self.assertEqual(result['path'],'newer')
    def test_launcher_path_with_spaces_and_quotes(self):
        result=parse_launcher(' -V:3.13 "C:\\Program Files\\Python 3.13\\python.exe"\n')
        self.assertEqual(result,['C:\\Program Files\\Python 3.13\\python.exe'])
    def test_deduplicates_repeated_user_output(self):
        paths=parse_launcher(REPORTED+REPORTED);self.assertEqual(len(deduplicate(paths)),2)
    def test_live_probe_uses_stdlib_only(self):
        info=probe(sys.executable);self.assertEqual(info['version'],list(sys.version_info[:3]));self.assertEqual(info['implementation'],'cpython')
    def test_probe_is_isolated(self):
        info=record('p')
        with patch('voice_setup.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(info),'')) as run:probe('some-python.exe')
        self.assertEqual(run.call_args.args[0][:3],['some-python.exe','-I','-S']);self.assertNotIn('pip',run.call_args.args[0])

class IsolatedEnvironmentTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.calls=[]
    def tearDown(self):self.temp.cleanup()
    def create(self,args,**kwargs):
        self.calls.append(args)
        if 'venv' in args:
            file=self.root/'.venv-voz/Scripts/python.exe';file.parent.mkdir(parents=True);file.write_text('fixture')
    def test_creates_voice_env_without_touching_ui_venv(self):
        (self.root/'.venv').mkdir();marker=self.root/'.venv/do-not-touch';marker.write_text('original')
        result=ensure_environment(self.root,record('existing-311.exe'),run=self.create,inspect=lambda p:record(p))
        self.assertEqual(result,self.root/'.venv-voz/Scripts/python.exe');self.assertEqual(marker.read_text(),'original')
        self.assertEqual(self.calls[0],['existing-311.exe','-I','-m','venv',str(self.root/'.venv-voz')])
    def test_compatible_existing_env_reused_without_install_step(self):
        file=self.root/'.venv-voz/Scripts/python.exe';file.parent.mkdir(parents=True);file.write_text('fixture')
        ensure_environment(self.root,record('base'),run=self.create,inspect=lambda p:record(p));self.assertEqual(self.calls,[])
    def test_incompatible_env_not_overwritten_without_approval(self):
        folder=self.root/'.venv-voz';folder.mkdir();(folder/'keep').write_text('original')
        with self.assertRaises(RuntimeError):ensure_environment(self.root,record('base'),approve=lambda text:False,run=self.create)
        self.assertEqual((folder/'keep').read_text(),'original');self.assertEqual(self.calls,[])
    def test_incomplete_env_preserved_as_backup(self):
        folder=self.root/'.venv-voz';folder.mkdir();(folder/'keep').write_text('original')
        ensure_environment(self.root,record('base'),approve=lambda text:True,run=self.create,inspect=lambda p:record(p))
        backups=list(self.root.glob('.venv-voz-respaldo-*'));self.assertEqual(len(backups),1);self.assertEqual((backups[0]/'keep').read_text(),'original')
    def test_pip_and_model_use_voice_python_not_launcher(self):
        python=self.root/'.venv-voz/Scripts/python.exe';install_voice(self.root,python,run=self.create)
        self.assertEqual(len(self.calls),4)
        for args in self.calls:self.assertEqual(args[0],str(python));self.assertNotIn('py',args)
        self.assertIn('ensurepip',self.calls[0]);self.assertIn('requirements-voice.txt',self.calls[1][-1]);self.assertEqual(self.calls[-1][-1],'--yes')
    def test_failure_creating_env_does_not_change_ui(self):
        folder=self.root/'.venv';folder.mkdir();(folder/'keep').write_text('original')
        def fail(*a,**k):raise subprocess.CalledProcessError(1,'fixture')
        with self.assertRaises(subprocess.CalledProcessError):ensure_environment(self.root,record('base'),run=fail)
        self.assertEqual((folder/'keep').read_text(),'original')
    def test_voice_runner_prefers_sidecar(self):
        python=self.root/'.venv-voz/Scripts/python.exe';python.parent.mkdir(parents=True);python.write_text('fixture')
        self.assertEqual(voice.voice_python(self.root,windows=True),str(python))
    def test_legacy_runner_fallback_if_no_sidecar(self):self.assertEqual(voice.voice_python(self.root,windows=True),sys.executable)
    def test_incomplete_sidecar_does_not_fall_back_silently(self):
        (self.root/'.venv-voz').mkdir()
        with self.assertRaisesRegex(RuntimeError,'incompleto'):voice.voice_python(self.root,windows=True)
    def test_speaker_uses_selected_voice_runtime(self):
        finished=threading.Event();result=[]
        class Process:
            def __init__(self,args,**kwargs):result.append(args)
            def communicate(self,*args,**kwargs):return '{"ok":true}',None
            def poll(self):return 0
        with patch('voice.voice_python',return_value='voice-311.exe'),patch('voice.subprocess.Popen',Process):
            speaker=voice.Speaker(lambda *a:finished.set());speaker.speak('Hola México');self.assertTrue(finished.wait(2))
        self.assertEqual(result[0][:3],['voice-311.exe','-I','-u'])
    def test_recorder_uses_selected_voice_runtime(self):
        finished=threading.Event();result=[]
        class Process:
            def __init__(self,args,**kwargs):result.append(args);self.stdout=io.StringIO('{"type":"error","text":"fixture"}\n');self.stdin=io.StringIO()
            def wait(self,*a,**k):return 0
            def poll(self):return 0
        with patch('voice.voice_python',return_value='voice-311.exe'),patch('voice.subprocess.Popen',Process):
            recorder=voice.Recorder(lambda *a:finished.set());recorder.start('fixture-model');self.assertTrue(finished.wait(2))
        self.assertEqual(result[0][:3],['voice-311.exe','-I','-u'])

class MainApprovalTests(unittest.TestCase):
    def call_main(self,diagnose=False,approve=True,opened=False,compatible_installed=True):
        output=io.StringIO()
        paths=[Path('default-315.exe')]+([Path('uv-311.exe')] if compatible_installed else [])
        def inspect(path):return record(path,(3,15,1) if str(path)=='default-315.exe' else (3,11,16))
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch('voice_setup.os',types.SimpleNamespace(name='nt',path=os.path)))
            stack.enter_context(patch('voice_setup.sys.argv',['voice_setup.py']+(['--diagnose'] if diagnose else [])))
            stack.enter_context(patch('voice_setup.discover',return_value=paths))
            stack.enter_context(patch('voice_setup.probe',side_effect=inspect))
            stack.enter_context(patch('voice_setup.app_is_open',return_value=opened))
            confirm=stack.enter_context(patch('voice_setup.confirm',return_value=approve))
            ensure=stack.enter_context(patch('voice_setup.ensure_environment',return_value=Path('voice-311.exe')))
            install=stack.enter_context(patch('voice_setup.install_voice'))
            stack.enter_context(contextlib.redirect_stdout(output))
            result=voice_setup.main()
        return result,output.getvalue(),confirm,ensure,install
    def test_diagnose_never_asks_or_installs(self):
        result,output,confirm,ensure,install=self.call_main(diagnose=True)
        self.assertEqual(result,0);confirm.assert_not_called();ensure.assert_not_called();install.assert_not_called();self.assertIn('Python seleccionado para voz: uv-311.exe',output)
    def test_user_declines_no_environment_or_download(self):
        result,output,confirm,ensure,install=self.call_main(approve=False)
        self.assertEqual(result,0);confirm.assert_called_once();ensure.assert_not_called();install.assert_not_called()
    def test_open_app_blocks_install(self):
        result,output,confirm,ensure,install=self.call_main(opened=True)
        self.assertEqual(result,2);confirm.assert_not_called();ensure.assert_not_called();install.assert_not_called()
    def test_no_compatible_runtime_never_installs_python(self):
        result,output,confirm,ensure,install=self.call_main(compatible_installed=False)
        self.assertEqual(result,2);confirm.assert_not_called();ensure.assert_not_called();install.assert_not_called()
    def test_approval_uses_311_environment_and_installer(self):
        result,output,confirm,ensure,install=self.call_main()
        self.assertEqual(result,0);confirm.assert_called_once();self.assertEqual(ensure.call_args.args[1]['path'],'uv-311.exe');self.assertEqual(install.call_args.args[1],Path('voice-311.exe'))

class NativeDispatchTests(unittest.TestCase):
    def test_native_voice_listing_uses_voice_runtime(self):
        with patch('voice.os',types.SimpleNamespace(name='nt')),patch('voice.voice_python',return_value='voice-311.exe'),patch('voice.subprocess.run',return_value=subprocess.CompletedProcess([],0,'{"ok":true,"voices":[]}','')) as run:
            self.assertEqual(voice.native_voices(),[])
        self.assertEqual(run.call_args.args[0][:3],['voice-311.exe','-I','-u']);self.assertEqual(run.call_args.args[0][-1],'voices')

if __name__=='__main__':unittest.main(verbosity=2)

