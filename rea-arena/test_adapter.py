import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import rea_arena as adapter

class AdapterTests(unittest.TestCase):
    def test_valid_directory(self):
        self.assertEqual(adapter.validate_target(adapter.ROOT / 'examples/demo', 'javascript'), adapter.ROOT / 'examples/demo')

    def test_reject_workspace_root(self):
        with self.assertRaises(ValueError): adapter.validate_target(adapter.WORKSPACE, 'javascript')

    def test_reject_outside_workspace(self):
        with self.assertRaises(ValueError): adapter.validate_target('/etc/passwd', 'managed')

    def test_reject_single_js_for_application(self):
        with self.assertRaises(ValueError): adapter.validate_target(adapter.ROOT / 'examples/demo/index.js', 'javascript')

    def test_reject_directory_for_managed(self):
        with self.assertRaises(ValueError): adapter.validate_target(adapter.ROOT / 'examples/demo', 'managed')

    def test_reject_missing_file(self):
        with self.assertRaises(FileNotFoundError): adapter.validate_target(adapter.ROOT / 'not-a-target', 'javascript')

    def test_escape_target_markdown(self):
        escaped = adapter.md('<script>alert(1)</script> [link](https://example.com)\n# command')
        self.assertNotIn('<script>', escaped)
        self.assertNotIn('\n', escaped)
        self.assertIn('\\[', escaped)

    def test_missing_installation_status(self):
        with patch.object(adapter, 'installed', return_value=False):
            result = adapter.status()
        self.assertFalse(result['cli_ready'])
        self.assertFalse(result['native_arena_mcp_connected'])

    def test_timeout(self):
        with tempfile.TemporaryDirectory(dir=adapter.ROOT) as temp:
            root = Path(temp)
            code, reason = adapter.bounded_run([sys.executable, '-c', 'import time; time.sleep(20)'], root/'stdout', root/'stderr', timeout=0.2)
            self.assertNotEqual(code, 0)
            self.assertIn('tiempo', reason)

    def test_no_shell_interpolation(self):
        with tempfile.TemporaryDirectory(dir=adapter.ROOT) as temp:
            root = Path(temp)
            text = 'hello; $(echo injected)'
            code, reason = adapter.bounded_run([sys.executable, '-c', 'import sys; print(sys.argv[1])', text], root/'stdout', root/'stderr')
            self.assertEqual(code, 0)
            self.assertIsNone(reason)
            self.assertEqual((root/'stdout').read_text().strip(), text)

    def test_failed_report_is_not_success(self):
        with tempfile.TemporaryDirectory(dir=adapter.ROOT) as temp:
            root = Path(temp)
            adapter.write_report(root, {'status':'failed','started_at':'test','mode':'managed','target':'sample','duration_seconds':0,'error':'unsupported'}, {'error':'failure'})
            report = (root/'informe.md').read_text()
            self.assertIn('Análisis no completado', report)
            self.assertNotIn('Análisis completado', report)

if __name__ == '__main__':
    unittest.main(verbosity=2)
