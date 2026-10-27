"""Fase 6-3: honest boundary around the empirical chapters.

Reported behaviour (pasted from the running agent)::

    {"reply": "Persisten como pendientes Resultados, Discusión y Conclusiones.
      Dado que Resultados no puede redactarse sin datos empíricos confirmados,
      intento completar otro apartado pendiente no basado en hallazgos del
      estudio.",
     "tool_calls": [{"name": "escribir_apartado", "arguments": {
        "section": "conclusiones",
        "text": "Conclusiones (provisional). Este apartado permanece condicionado
                 a la obtención y análisis de datos del estudio...",
        "sources": []}}], "done": false}

`document.write_section()` already REFUSES empirical drafts without a confirmed
corpus, so the write itself fails. The real bug is that the continuous loop had
no deterministic exit for "the only remaining work needs data from the user":
it kept retrying, wrote polite filler, and burned calls until a stall/fuse.
`gates` also only recognised literal markers ([Por redactar], TODO, TBD), so
this semantic placeholder passed as a real chapter.

This module is the SINGLE source of truth for:

* whether a project legitimately needs empirical results (an anteproyecto /
  protocolo does not);
* whether a confirmed corpus exists;
* detecting semantic placeholders (prose that only says "no data yet");
* deciding when the ONLY remaining work is to ask the user for data;
* the concrete question the agent must ask.

No network, no model judgement, no Windows/Word/Tk dependency. The user's
standing rule "no inventar resultados" is enforced here, not in a prompt.
"""
from __future__ import annotations

import re
import unicodedata

from diagnostics import as_text

EMPIRICAL = ('resultados', 'discusion', 'conclusiones')
MIN_DRAFT = 60

# Folded (accent-free) markers. An anteproyecto may legitimately contain
# "resultados esperados", so these only apply when results ARE required.
PROPOSAL_WORDS = (
    'anteproyecto', 'protocolo', 'propuesta de investigacion',
    'propuesta de tesis', 'proyecto de investigacion',
)
PLACEHOLDER_WORDS = re.compile(
    r'(?i)(provisional|condicionad|pendiente|no existen?|no hay|a la espera|'
    r'sin datos|sin evidenc|apoyo pendiente|por redactar|por definir|'
    r'evidencia pendiente|a[uú]n no|todav[ií]a no|fase actual|'
    r'cuando se (?:obteng|dispong|teng)|deber[aá]n? fundamentarse|'
    r'no permiten? establecer|no se pueden? establecer|'
    r'permanece condicionado|requiere evidencia|sin hallazgos)')


def fold(text):
    """Lower-case, strip accents, collapse whitespace. Never raises on odd types."""
    raw = as_text(text, 'empirical.text')
    flat = ''.join(c for c in unicodedata.normalize('NFD', raw.lower())
                   if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', flat).strip()


def confirmed(p):
    """True only when the user supplied a corpus AND marked it ready.

    `set_fact('datos', ...)` deliberately sets `data_ready=False` again, so a
    stale corpus can never silently satisfy this check.
    """
    if not isinstance(p, dict) or not p.get('data_ready'):
        return False
    facts = p.get('facts')
    if not isinstance(facts, dict):
        return False
    record = facts.get('datos')
    value = record.get('value', '') if isinstance(record, dict) else ''
    return bool(as_text(value, 'facts.datos.value').strip())


def is_proposal(p):
    """A protocol/anteproyecto has NO empirical results by design."""
    facts = p.get('facts') if isinstance(p, dict) else None
    if not isinstance(facts, dict):
        return False
    parts = []
    for key in ('tipo_trabajo', 'metodologia', 'alcance', 'objetivo_usuario'):
        record = facts.get(key)
        if isinstance(record, dict):
            parts.append(as_text(record.get('value', ''), 'facts.' + key))
    text = fold(' '.join(parts))
    return any(word in text for word in PROPOSAL_WORDS)


def requires_results(p):
    """False for an anteproyecto/protocolo, True for an empirical study."""
    return not is_proposal(p)


def placeholder(text):
    """Detect prose that only narrates the absence of data (semantic filler)."""
    return bool(PLACEHOLDER_WORDS.search(fold(text)[:1500]))


def placeholder_sections(p):
    drafts = p.get('drafts') if isinstance(p, dict) else None
    if not isinstance(drafts, dict):
        return []
    return [key for key in EMPIRICAL
            if isinstance(drafts.get(key), dict)
            and placeholder(drafts[key].get('text', ''))]


def _other_work_remains(p):
    """True while the agent can still do useful work WITHOUT user data.

    We deliberately do not require M4 here: M4 is precisely the module that is
    blocked waiting for a corpus. M5 excludes empirical sections on its own
    when no data exists, so it can legitimately be done.
    """
    from project_state import status_map, section_order, OPTIONAL
    status = status_map(p)
    if not all(status.get(m) == 'done' for m in ('M1', 'M2', 'M3', 'M5')):
        return True
    if not p.get('sources'):
        return True
    drafts = p.get('drafts')
    if not isinstance(drafts, dict):
        return True
    for section in section_order(p):
        if section in OPTIONAL or section in EMPIRICAL:
            continue
        draft = drafts.get(section)
        if not isinstance(draft, dict):
            return True
        text = as_text(draft.get('text', ''), 'drafts.text')
        if len(text.strip()) < MIN_DRAFT or placeholder(text[:400]):
            return True
    return False


def _already_asked(p):
    for question in p.get('questions', []) or []:
        if isinstance(question, dict) and question.get('status') == 'abierta' \
                and 'datos' in fold(question.get('text', '')):
            return True
    return False


NO_DATA_QUESTION = (
    'Para redactar Resultados, Discusión y Conclusiones necesito el corpus del '
    'estudio (datos crudos, transcripciones, mediciones, tablas o el archivo con '
    'los resultados). No puedo inferirlos ni escribir conclusiones sin evidencia. '
    '¿Puedes aportarlos ahora, o indicarme con precisión dónde están para '
    'registrarlos en Memoria?')

FILLER_QUESTION = (
    'Hay un corpus registrado, pero Resultados/Discusión/Conclusiones siguen '
    'con texto provisional que no aporta evidencia. ¿Confirmas que esos datos '
    'son los definitivos, o puedes ampliar el corpus para que reescriba esos '
    'apartados con hallazgos verificables?')


def data_question(p, verification=None):
    """Return the question the loop MUST ask, or None if it should keep working.

    This is a HUMAN BOUNDARY (one of the declared non-quota safety stops), not
    a step quota. It fires only when the project legitimately needs empirical
    results, the corpus is missing or the empirical drafts are placeholders,
    and there is no other chapter/source work left to do.
    """
    if not isinstance(p, dict) or not requires_results(p):
        return None
    if confirmed(p) and not placeholder_sections(p):
        return None
    if _other_work_remains(p) or _already_asked(p):
        return None
    return FILLER_QUESTION if confirmed(p) else NO_DATA_QUESTION
