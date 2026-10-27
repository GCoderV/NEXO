"""Regression: a NEW project must not inherit anything from the previous one.

Reported by the user: "cuando creó un nuevo proyecto sigue asumiendo cosas del
proyecto anterior". ProjectStore.create() already stores an empty project; the
leak was in `Application`'s in-memory, project-scoped state: the last agent
receipt label, the selected section, work-mode toggles, consents, pending text
and several widgets that were never cleared when switching projects.

This suite builds the REAL Application on an in-memory Tk double (no display,
no Windows, no Word, no network, no credentials) and asserts that opening a
second project starts from exactly the same blank slate as the first one.
"""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from fake_tk_app import Widget, install  # noqa: E402
install()  # MUST happen before importing app: it binds tk/ttk at import time

from test_core import FakeAPI, FakeProtector, reply  # noqa: E402
from project_store import ProjectStore, set_fact, message, SECTIONS  # noqa: E402
from config import Config  # noqa: E402
from agent import Agent  # noqa: E402
from app import Application  # noqa: E402

MARKERS = (
    'Universidad Ejemplo A', '24 estudiantes', 'Enfoque mixto A',
    'Paper solo de A', 'Mensaje exclusivo del proyecto A', 'Tema A',
    'Último agente: 7 pasos',
)


def text_of(widget):
    return widget.get('1.0', 'end-1c')


def label_of(widget):
    return str(widget.opts.get('text', ''))


class AislamientoProyectosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ProjectStore(self.tmp.name)
        self.config = Config(self.tmp.name, FakeProtector())
        self.root = Widget()
        self.app = Application(
            self.root, self.store, self.config,
            api_factory=lambda: FakeAPI([reply()]),
            word_factory=lambda path: types.SimpleNamespace(snapshot=None))
        self.app.root.after_cancel(self.app.timer)

    def seed_project_a(self):
        """Create project A with facts, drafts, sources, messages and a receipt."""
        self.app.new_project('Tema A: juegos de roles en inglés')
        a = self.app.project
        set_fact(a, 'institucion', 'Universidad Ejemplo A')
        set_fact(a, 'poblacion', '24 estudiantes de secundaria')
        set_fact(a, 'metodologia', 'Enfoque mixto A')
        a['drafts']['marco_teorico'] = {
            'text': 'Texto exclusivo del proyecto A. ' * 8,
            'status': 'borrador', 'sources': []}
        a['sources'] = [{'id': 'F1', 'title': 'Paper solo de A',
                         'authors': 'Autor A', 'year': '2022',
                         'status': 'metadatos', 'url': '', 'excerpt': '',
                         'locator': '', 'supports': ''}]
        message(a, 'user', 'Mensaje exclusivo del proyecto A')
        a['last_loop'] = {'passes': 7, 'changes': 5, 'stopped': 'pregunta',
                          'verification': {'score': 88}}
        self.store.save(a, 'seed-A')
        # Dirty the whole project-scoped UI state on purpose.
        self.app.render()
        self.app.doc_status.configure(
            text='Último agente: 7 pasos · 5 cambios · motivo: pregunta · 88/100')
        self.app.include_optional.set(False)
        self.app.loop_passes.set('12')
        self.app.continuous_research.set(False)
        self.app.continuous_minutes.set('15')
        self.app.auto_limit.set('2')
        self.app.draft_key.set('conclusiones')
        self.app.consent.add(('firma-de-A', 'Groq', 'm', ''))
        self.app.pending_user_text = (a['id'], 'texto pendiente de A', 'usuario')
        self.app.documents = ['documento-de-A.docx']
        self.app.status.set('Estado exclusivo de A')
        return a

    def test_proyecto_nuevo_no_arrastra_estado_del_anterior(self):
        a = self.seed_project_a()
        self.app.new_project('Tema B: otro tema distinto')
        b = self.app.project
        self.assertNotEqual(b['id'], a['id'])
        # Stored data was already isolated; keep proving it.
        self.assertEqual(b['facts'], {})
        self.assertEqual(b['drafts'], {})
        self.assertEqual(b['sources'], [])
        self.assertIsNone(b.get('last_loop'))
        self.assertEqual(len(b['messages']), 1)
        # No widget may show any marker from project A.
        widgets = ('chat', 'draft_text', 'memory_text', 'source_text', 'input',
                   'word_selection', 'word_proposal')
        for name in widgets:
            value = text_of(getattr(self.app, name))
            for marker in MARKERS:
                self.assertNotIn(marker, value, name + ' conserva: ' + marker)
        for name in ('title', 'project_state', 'module_status', 'doc_status',
                     'draft_status', 'status'):
            obj = getattr(self.app, name)
            value = obj.get() if hasattr(obj, 'get') and not hasattr(obj, 'opts') \
                else label_of(obj)
            for marker in MARKERS:
                self.assertNotIn(marker, str(value), name + ' conserva: ' + marker)
        self.assertEqual(label_of(self.app.doc_status), '',
                         'el recibo del agente del proyecto anterior sigue visible')
        self.assertEqual(label_of(self.app.title), 'Tema B: otro tema distinto')
        # Work-mode defaults must be restored, not inherited.
        self.assertTrue(self.app.include_optional.get())
        self.assertEqual(self.app.loop_passes.get(), '6')
        self.assertTrue(self.app.continuous_research.get())
        self.assertEqual(self.app.continuous_minutes.get(), '60')
        self.assertEqual(self.app.auto_limit.get(), '6')
        self.assertFalse(self.app.allow_research.get())
        self.assertEqual(self.app.draft_key.get(), SECTIONS[0])
        # Ephemeral session state must be empty.
        self.assertEqual(self.app.consent, set())
        self.assertIsNone(self.app.pending_user_text)
        self.assertEqual(self.app.documents, [])
        self.assertIsNone(self.app.word_origin)
        self.assertEqual(self.app.input_origin, 'usuario')

    def test_volver_al_proyecto_a_no_pierde_sus_datos(self):
        a = self.seed_project_a()
        self.app.new_project('Tema B: otro tema distinto')
        self.app.open_project(a['id'])
        self.assertEqual(self.app.project['facts']['institucion']['value'],
                         'Universidad Ejemplo A')
        self.assertIn('marco_teorico', self.app.project['drafts'])
        self.assertEqual(self.app.project['sources'][0]['title'], 'Paper solo de A')
        self.assertIn('Último agente', label_of(self.app.doc_status))

    def test_refresh_document_borra_recibo_cuando_no_hay_ultimo_bucle(self):
        self.app.new_project('Proyecto sin agente')
        self.app.doc_status.configure(text='Último agente: 99 pasos · motivo: viejo')
        self.app.refresh_document()
        self.assertEqual(label_of(self.app.doc_status), '')
        self.app.project['last_loop'] = {'passes': 2, 'changes': 1,
                                        'stopped': 'finalizado'}
        self.app.refresh_document()
        self.assertIn('2 pasos', label_of(self.app.doc_status))

    def test_new_project_no_crea_proyecto_si_hay_trabajo_en_curso(self):
        before = len(self.store.list())
        self.app.busy = True
        self.app.new_project('No debería crearse')
        self.assertEqual(len(self.store.list()), before,
                         'se creó un proyecto que open_project no podía abrir')

    def test_contexto_del_modelo_para_b_no_contiene_datos_de_a(self):
        self.seed_project_a()
        self.app.new_project('Tema B: otro tema distinto')
        b = self.app.project

        class CaptureAPI(FakeAPI):
            def __init__(self):
                super().__init__([reply()])
                self.conversations = []

            def request(self, conversation, declarations):
                self.conversations.append(
                    [str(m.get('content', '')) for m in conversation])
                return super().request(conversation, declarations)

        api = CaptureAPI()
        Agent(self.store, api).turn(b['id'], '¿Qué datos tienes del proyecto?',
                                    origin='usuario')
        sent = ' '.join(c for conv in api.conversations for c in conv)
        self.assertTrue(api.conversations, 'no se envió ninguna petición')
        for marker in ('Universidad Ejemplo A', '24 estudiantes',
                       'Enfoque mixto A', 'Paper solo de A',
                       'Mensaje exclusivo del proyecto A', 'Tema A'):
            self.assertNotIn(marker, sent)
        self.assertIn('Tema B', sent)

    def test_open_project_invoca_el_reset_antes_de_cargar(self):
        source = (ROOT / 'app.py').read_text('utf-8')
        block = source.split('    def open_project(self,id):', 1)[1].split('\n    def ', 1)[0]
        self.assertIn('self.reset_project_scope()', block)
        self.assertLess(block.index('self.reset_project_scope()'),
                        block.index('self.project=self.store.recover'))

    def test_autochequeo_offline_cubre_el_aislamiento(self):
        from verificar_instalacion import check_project_isolation
        self.assertEqual(check_project_isolation(), [])
        source = (ROOT / 'verificar_instalacion.py').read_text('utf-8')
        self.assertIn('check_project_isolation()', source.split('def main():', 1)[1])
        self.assertIn('Aislamiento de proyectos: OK', source)


if __name__ == '__main__':
    unittest.main()
