"""Regression (end-to-end, synthetic): capturing a session must NOT close Copilot.

User report: "luego de capturar la sesión de Copilot el bot cierra
automáticamente Copilot". The captured session lives inside the Copilot/Edge
process Nexo launched with a local debugging port; terminating it right after
saving the secret makes the very next turn fail with "Fallo de conexión".

These tests drive the real `SettingsDialog.connect_copilot()` flow with an
in-memory Tk double and a fake `subprocess.Popen`. No Windows, no Edge, no
M365 session, no credential and no network are involved: every value is a
synthetic fixture. `async_job` is replaced by a synchronous version so the
assertions are deterministic instead of racing a background thread.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

# Importing this module installs the fake Tk modules BEFORE settings_dialog is
# imported. It is also a real test module, so its own suite keeps running.
from test_copilot_sin_api_key import FakeApp, install_fake_tk  # noqa: E402
from test_v02 import session  # noqa: E402  (synthetic fixture, not a token)
from test_core import FakeProtector  # noqa: E402
from config import Config  # noqa: E402
import copilot_socket  # noqa: E402
import process_guard  # noqa: E402
import settings_dialog  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

SESSION = session()  # synthetic captured-session JSON, valid for config.account()


class FakeProc:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self.args = None

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def synchronous_async_job(self, fn, done):
    """Stand-in for SettingsDialog.async_job: run fn() and done() inline."""
    self.working = True
    self.cancel.clear()
    try:
        value = fn()
    except Exception as e:
        self.working = False
        self.note.set(self.config.redact(e))
        return
    done(value)
    self.working = False


class CapturaNoCierraCopilotTests(unittest.TestCase):
    def setUp(self):
        install_fake_tk()
        self._real_popen = subprocess.Popen
        process_guard.stop_tracking()
        with process_guard._lock:
            process_guard._tracked.clear()
        process_guard._original = None
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(self.temp.name, FakeProtector())
        self.app = FakeApp(self.config)
        self.dlg = SettingsDialog(self.app)
        self.dlg.ap.set('Copilot365')
        self.dlg.sync_account_provider()
        self.dlg.alias.set('M365 de prueba')
        self.dlg.copilot_mode.set('Escritorio M365')
        self.proc = FakeProc()

    def tearDown(self):
        process_guard.stop_tracking()
        with process_guard._lock:
            process_guard._tracked.clear()
        process_guard._original = None
        subprocess.Popen = self._real_popen

    def _connect(self, capture_result=SESSION, capture_error=None):
        """Run connect_copilot() with a fake launched Copilot process."""
        proc = self.proc
        def fake_launch_desktop():
            proc.args = ['M365Copilot.exe', '--remote-debugging-port=9222']
            subprocess.Popen(proc.args)
            return 9222
        def fake_capture(port, **kwargs):
            self.assertEqual(port, 9222)
            if capture_error:
                raise capture_error
            return capture_result
        subprocess.Popen = lambda *a, **k: proc
        with patch('settings_dialog.messagebox.askyesno', return_value=True), \
             patch.object(copilot_socket, 'launch_desktop', fake_launch_desktop), \
             patch.object(copilot_socket, 'capture_connection', fake_capture), \
             patch.object(SettingsDialog, 'async_job', synchronous_async_job):
            self.dlg.connect_copilot()
        return proc

    def test_captura_exitosa_deja_copilot_abierto(self):
        proc = self._connect()
        self.assertIsNotNone(proc.args, 'Nexo debía lanzar Copilot')
        self.assertFalse(proc.terminated,
                         'ERROR: Nexo cerró Copilot tras capturar la sesión')
        self.assertFalse(proc.killed)
        self.assertEqual(process_guard.count(), 0,
                         'el proceso debía dejar de estar seguido, no terminado')

    def test_cerrar_ventana_tras_captura_no_cierra_copilot(self):
        """Reproduces the exact sequence: capture, then close the dialog."""
        proc = self._connect()
        self.dlg.close()
        self.assertFalse(proc.terminated,
                         'cerrar el diálogo no debe matar la sesión capturada')
        self.assertFalse(proc.killed)

    def test_la_cuenta_guardada_sigue_siendo_utilizable(self):
        self._connect()
        accounts = self.config.data['accounts']
        self.assertEqual(len(accounts), 1)
        aid = next(iter(accounts))
        self.assertEqual(self.config.secret(aid), SESSION)
        self.assertTrue(self.dlg.copilot_account_ready(aid))

    def test_fallo_de_captura_si_cierra_ventanas_huerfanas(self):
        proc = self._connect(capture_error=ValueError('frase de prueba no observada'))
        self.assertTrue(proc.terminated,
                        'un intento fallido sí debe limpiar la ventana huérfana')
        self.assertEqual(process_guard.count(), 0)
        self.assertIn('frase de prueba no observada', self.dlg.note.get())

    def test_usuario_cancela_antes_de_autorizar_no_lanza_nada(self):
        with patch('settings_dialog.messagebox.askyesno', return_value=False), \
             patch.object(SettingsDialog, 'async_job', synchronous_async_job):
            self.dlg.connect_copilot()
        self.assertIsNone(self.proc.args)
        self.assertFalse(self.proc.terminated)
        self.assertEqual(process_guard.count(), 0)

    def test_autochequeo_offline_detecta_la_regresion(self):
        """VERIFICAR.cmd must prove THIS copy keeps Copilot open."""
        from verificar_instalacion import check_copilot_stays_open
        self.assertEqual(check_copilot_stays_open(), [])
        source = (ROOT / 'verificar_instalacion.py').read_text('utf-8')
        self.assertIn('check_copilot_stays_open()', source.split('def main():', 1)[1])
        self.assertIn('Sesion Copilot: OK', source)


if __name__ == '__main__':
    unittest.main()
