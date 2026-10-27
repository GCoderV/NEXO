"""Regression: the real "Marco teórico" reply that kept failing.

The model returned a perfectly valid JSON object with a long `text`. The host
rejected it because unpack capped drafts at 10000 characters while the editor
allowed 20000 and the task prompt never mentioned any limit. Result: an endless
"La respuesta no cumple el formato académico" loop on the longest section.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_core import FakeAPI  # noqa: E402
from project_store import ProjectStore  # noqa: E402
from agent import Agent, unpack, context, section_id, _coerce_sources, _fit_draft  # noqa: E402
from autonomy import order  # noqa: E402
from limits import MAX_DRAFT_CHARS, MAX_CONTEXT_CHARS  # noqa: E402

SECTIONS_TEXT = (
    'La enseñanza del inglés como lengua extranjera comprende el desarrollo de '
    'habilidades receptivas y productivas. En el contexto escolar, aprender inglés '
    'no debe limitarse a memorizar vocabulario o estructuras gramaticales aisladas: '
    'requiere oportunidades para intercambiar información, formular preguntas, '
    'responder, describir situaciones y expresar ideas con propósitos definidos. '
    'La producción oral se entiende provisionalmente como la capacidad de expresar '
    'mensajes e interactuar verbalmente en inglés mediante los recursos lingüísticos '
    'y comunicativos disponibles, organizando ideas, seleccionando vocabulario, '
    'construyendo enunciados comprensibles y respondiendo al interlocutor. '
    'El aprendizaje cooperativo se concibe como una organización pedagógica en la '
    'que los estudiantes trabajan en grupos pequeños para alcanzar propósitos '
    'compartidos, con interdependencia positiva, responsabilidad individual, '
    'interacción entre compañeros, habilidades sociales y reflexión grupal. '
    'Los juegos de roles son actividades en las que los participantes asumen '
    'personajes o funciones dentro de una situación determinada, lo que permite '
    'simular conversaciones cotidianas o escolares con un propósito comunicativo. '
)


def long_text(characters):
    out = []
    i = 1
    while sum(len(x) for x in out) < characters:
        out.append('#### ' + str(i) + '. Desarrollo del apartado\n\n' + SECTIONS_TEXT)
        i += 1
    return '\n\n'.join(out)[:characters]


TASK = {'section': 'marco_teorico', 'mode': 'crear', 'label': 'Marco teórico'}


def real_payload(characters):
    return json.dumps({
        'text': long_text(characters),
        'sources': [],
        'reply': 'Se entrega el marco teórico completo con la información disponible. '
                 'El borrador distingue los datos conocidos de las propuestas provisionales.'
    }, ensure_ascii=False)


def run_task(raw):
    with tempfile.TemporaryDirectory() as d:
        store = ProjectStore(d)
        p = store.create('Estrategia de aprendizaje cooperativo')
        api = FakeAPI([raw])
        result = Agent(store, api).turn(p['id'], 'Tarea automática autorizada: crear Marco teórico.',
                                        origin='autonomo', task=TASK)
        return result, api


class LongDraftTests(unittest.TestCase):
    def test_real_marco_teorico_over_10000_is_accepted(self):
        body = long_text(11000)
        self.assertGreater(len(body), 10000)
        r = unpack(real_payload(11000), TASK)
        self.assertEqual(len(r['drafts']), 1)
        self.assertEqual(r['drafts'][0]['section'], 'marco_teorico')
        self.assertEqual(r['drafts'][0]['text'], body.strip())

    def test_real_marco_teorico_saves_end_to_end(self):
        p, api = run_task(real_payload(11000))
        self.assertNotEqual(p['run']['status'], 'error_formato')
        self.assertIn('marco_teorico', p['drafts'])
        self.assertGreater(len(p['drafts']['marco_teorico']['text']), 10000)
        self.assertTrue(p['last_step']['progress'])
        self.assertNotIn('pending', p)
        self.assertEqual(len(api.requests), 1)  # no repair call

    def test_oversized_text_is_trimmed_with_a_visible_notice_not_rejected(self):
        p, _ = run_task(real_payload(30000))
        text = p['drafts']['marco_teorico']['text']
        self.assertLessEqual(len(text), MAX_DRAFT_CHARS)
        self.assertIn('Borrador recortado', text)
        self.assertNotEqual(p['run']['status'], 'error_formato')
        self.assertTrue(p['last_step']['progress'])

    def test_long_previous_draft_fits_the_context_limit(self):
        with tempfile.TemporaryDirectory() as d:
            store = ProjectStore(d)
            p = store.create('Tema')
            p['drafts']['marco_teorico'] = {
                'text': long_text(MAX_DRAFT_CHARS), 'status': 'borrador',
                'sources': [], 'material_ids': [], 'producer': {'provider': 'test'}}
            raw = context(p, 'Revisa el marco teórico', origin='autonomo',
                          work_order=order(p, TASK))
            self.assertLessEqual(len(raw), MAX_CONTEXT_CHARS)
            self.assertIn('previous_text', raw)


class NormalizationTests(unittest.TestCase):
    def test_section_accepts_labels_and_accents(self):
        self.assertEqual(section_id('Marco teórico'), 'marco_teorico')
        self.assertEqual(section_id('marco_teorico'), 'marco_teorico')
        self.assertEqual(section_id('Pregunta de investigación'), 'pregunta')
        self.assertEqual(section_id('Metodología'), 'metodologia')
        self.assertIsNone(section_id('no_existe'))

    def test_sources_with_dicts_ints_and_prose_are_normalized(self):
        self.assertEqual(_coerce_sources([{'id': 'F1'}, 2, 'D3', 'Autor (2020)', None]),
                         ['F1', 'F2', 'D3'])

    def test_task_accepts_spanish_aliases_and_label_section(self):
        raw = json.dumps({'borrador': 'Contenido del marco.', 'fuentes': [{'id': 'F9'}],
                          'resumen': 'Listo.', 'apartado': 'Marco teórico'}, ensure_ascii=False)
        r = unpack(raw, TASK)
        self.assertEqual(r['drafts'][0]['section'], 'marco_teorico')
        self.assertEqual(r['drafts'][0]['text'], 'Contenido del marco.')
        self.assertEqual(r['drafts'][0]['sources'], ['F9'])

    def test_task_accepts_drafts_with_wrong_section_and_missing_sources(self):
        raw = json.dumps({'reply': 'Listo', 'drafts': [
            {'section': 'Marco teórico', 'text': 'Cuerpo del apartado.'}]}, ensure_ascii=False)
        r = unpack(raw, TASK)
        self.assertEqual(r['drafts'][0]['section'], 'marco_teorico')
        self.assertEqual(r['drafts'][0]['sources'], [])

    def test_long_reply_is_promoted_to_a_draft_when_no_draft_field_exists(self):
        raw = json.dumps({'reply': long_text(1500)}, ensure_ascii=False)
        r = unpack(raw, TASK)
        self.assertEqual(len(r['drafts']), 1)
        self.assertEqual(r['drafts'][0]['section'], 'marco_teorico')

    def test_short_promise_is_not_promoted(self):
        r = unpack(json.dumps({'reply': 'Puedo continuar con el marco teórico.'}), TASK)
        self.assertEqual(r['drafts'], [])

    def test_fit_draft_cuts_at_a_paragraph_and_marks_it(self):
        text = ('Primer párrafo. ' * 100 + '\n\n' + 'Segundo párrafo. ' * 2000)
        fitted = _fit_draft(text)
        self.assertLessEqual(len(fitted), MAX_DRAFT_CHARS)
        self.assertIn('Borrador recortado', fitted)


if __name__ == '__main__':
    unittest.main()


class SelfCheckTests(unittest.TestCase):
    def test_startup_check_proves_long_drafts_are_accepted(self):
        from verificar_instalacion import check_long_draft
        self.assertEqual(check_long_draft(), [])

    def test_build_label_matches_metadata(self):
        from version import VERSION, BUILD
        meta = json.loads((ROOT / 'VERSION.json').read_text('utf-8'))
        self.assertEqual(meta['version'], VERSION)
        self.assertEqual(meta['build'], BUILD)
        self.assertEqual(BUILD, 'fase6-4')

    def test_exact_shape_of_the_user_reply(self):
        # Same top-level keys and escaped-newline markdown as the reported reply.
        section = ('### Marco teórico\n\nLa enseñanza del inglés como lengua '
                   'extranjera en 3.º de secundaria del Centro Educativo.\n\n'
                   '- **Fluidez:** continuidad del mensaje.\n\n'
                   '- **Interacción oral:** preguntas y respuestas.\n\n')
        text = section * 60
        raw = json.dumps({'text': text, 'sources': [],
                          'reply': 'Se entrega el marco teórico completo.'}, ensure_ascii=False)
        parsed = json.loads(raw)
        self.assertGreater(len(parsed['text']), 10000)
        self.assertIn('\\n', raw)  # saltos escapados, como en la respuesta real
        r = unpack(raw, TASK)
        self.assertEqual(r['drafts'][0]['section'], 'marco_teorico')
        self.assertGreater(len(r['drafts'][0]['text']), 10000)
