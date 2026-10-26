import base64
import json
import os
from pathlib import Path
import subprocess
import unittest
from secrets_store import WindowsProtector
@unittest.skipUnless(os.name=='nt','Requires Windows; no real Word is accessed')
class WindowsSmokeTests(unittest.TestCase):
    def test_dpapi_synthetic_secret(self):
        p=WindowsProtector();value='Nexo-Tesis-test-secret-not-a-real-key';sealed=p.seal(value);self.assertNotEqual(sealed,value);self.assertEqual(p.open(sealed),value)
    def test_windows_powershell_parser_only(self):
        script=Path(__file__).resolve().parent.parent/'word_bridge.ps1'
        b64=base64.b64encode(script.read_bytes()).decode()
        command="$s=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+b64+"'));$t=$null;$e=$null;[void][Management.Automation.Language.Parser]::ParseInput($s,[ref]$t,[ref]$e);if($e.Count){$e|Out-String;exit 1}"
        exe=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        run=subprocess.run([str(exe),'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(command.encode('utf-16-le')).decode()],capture_output=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stdout.decode(errors='replace'))
