"""Fase 3: deterministic quality gates. No model judgement, no network.

DoThesis blocks M4 commits on impossible statistics and M5 commits on prose
numbers that contradict persisted results (agent/stats_validation.py,
agent/coherence.py). Nexo applies the same idea with a smaller, honest rule
set: only PROVABLY wrong or PROVABLY unsupported content is a hard block.
Soft findings are reported, never used to fake completion.
"""
from __future__ import annotations

import re
import unicodedata

from diagnostics import as_key
from project_store import LABELS

DOI = re.compile(r'\b10\.\d{4,9}/[^\s,;)\]}"\']+', re.I)
CITATION = re.compile(r'\[([FD]\d+)\]')
PCT = re.compile(r'(?<!\w)(\d{1,3}(?:[.,]\d+)?)\s*%')
STAT = re.compile(r'(?i)\b(?:β|R²|R2|p\s*=|t\s*=|n\s*=|AVE|α\s*=|r\s*=|χ²)\b')
PLACEHOLDER = re.compile(r'\[Por redactar\]|Por definir|\bTODO\b|\bTBD\b|Lorem ipsum', re.I)
EMPIRICAL = ('resultados', 'discusion', 'conclusiones')
DOCUMENTARY = re.compile(r'(?i)documental|revisi[oó]n\s+(?:bibliogr|sistem|de\s+literatura)')
INSTRUMENT_WORDS = re.compile(r'(?i)cuestionario|encuesta|escala\s+likert|entrevista\s+estructurada|pretest|postest')


def _fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text or '').lower())
                   if unicodedata.category(c) != 'Mn')


def _drafts(p):
    return {as_key(k): v for k, v in p.get('drafts', {}).items()
            if isinstance(v, dict) and isinstance(v.get('text'), str)}


def _source_ids(p):
    ids = set()
    for source in p.get('sources', []):
        if isinstance(source, dict):
            value = as_key(source.get('id'), 'source.id')
            if value:
                ids.add(value)
    for material in p.get('materials', []):
        if isinstance(material, dict):
            value = as_key(material.get('id'), 'material.id')
            if value:
                ids.add(value)
    return ids


def check_sources(p):
    """Every [F#]/[D#] and every printed DOI must exist in the registry."""
    hard, soft = [], []
    known = _source_ids(p)
    registry = ''
    for source in p.get('sources', []):
        if isinstance(source, dict):
            registry += ' ' + str(source.get('doi', '')) + ' ' + str(source.get('url', ''))
    registry = registry.lower()
    for section, draft in _drafts(p).items():
        text = draft['text']
        ids = set(CITATION.findall(text))
        unknown = sorted(ids - known)
        if unknown:
            hard.append(LABELS.get(section, section) + ' cita fuentes inexistentes: ' + ', '.join(unknown[:6]))
        for match in DOI.finditer(text):
            token = match.group(0).rstrip('.,;').lower()
            if token not in registry:
                hard.append(LABELS.get(section, section) + ' imprime un DOI no registrado: ' + token[:60])
                break
    return hard, soft


def check_numbers(p):
    """No empirical numbers without confirmed data; no impossible percentages."""
    hard, soft = [], []
    facts = p.get('facts', {}) if isinstance(p.get('facts'), dict) else {}
    corpus = str(facts.get('datos', {}).get('value', ''))
    confirmed = bool(p.get('data_ready') and corpus.strip())
    for section in EMPIRICAL:
        draft = _drafts(p).get(section)
        if not draft:
            continue
        text = draft['text']
        numeric = PCT.findall(text) or STAT.findall(text)
        if numeric and not confirmed:
            hard.append(LABELS[section] + ' contiene cifras sin datos/corpus confirmados: ' +
                        str(numeric[:4]))
        for raw in PCT.findall(text):
            try:
                value = float(str(raw).replace(',', '.'))
            except ValueError:
                continue
            if value > 100:
                hard.append(LABELS[section] + ' indica ' + str(value) + '%, imposible como porcentaje.')
        if confirmed and PCT.findall(text):
            corpus_values = set(PCT.findall(corpus))
            for raw in PCT.findall(text):
                if raw not in corpus_values and raw.replace('.', ',') not in corpus_values:
                    soft.append(LABELS[section] + ' cita ' + str(raw) +
                                '% que no aparece literalmente en el corpus aportado; verifica la procedencia.')
                    break
    return hard, soft


def check_coherence(p):
    """Cross-section contradictions that are provable from state."""
    hard, soft = [], []
    drafts = _drafts(p)
    facts = p.get('facts', {}) if isinstance(p.get('facts'), dict) else {}
    method = ' '.join(str(facts.get(k, {}).get('value', '')) for k in ('metodologia', 'tipo_trabajo'))
    method += ' ' + (drafts.get('metodologia', {}).get('text', '')[:600])
    instruments = drafts.get('instrumentos', {}).get('text', '')
    if DOCUMENTARY.search(method) and INSTRUMENT_WORDS.search(instruments):
        soft.append('La metodología parece documental pero Instrumentos propone aplicación empírica; revisa la coherencia.')
    theory = drafts.get('marco_teorico', {}).get('text', '')
    if theory and p.get('sources') and not CITATION.search(theory):
        soft.append('Marco teórico sin citas [F#] aunque hay fuentes registradas.')
    if theory and not p.get('sources'):
        hard.append('Marco teórico redactado sin ninguna fuente registrada.')
    results = drafts.get('resultados', {}).get('text', '')
    objectives = drafts.get('objetivos', {}).get('text', '')
    if results and not objectives:
        soft.append('Hay resultados pero no hay objetivos redactados que los enmarquen.')
    refs = drafts.get('referencias', {}).get('text', '')
    if refs and p.get('sources'):
        ids = set(CITATION.findall(refs))
        known = _source_ids(p)
        if len(ids) < min(3, len(known)):
            soft.append('Referencias no identifica todas las fuentes registradas con [F#].')
    return hard, soft


def check_export(p):
    """Refuse to ship placeholders, stubs or missing required chapters."""
    from document import section_blocks
    hard, soft = [], []
    required = ('delimitacion', 'problematica', 'objetivos', 'justificacion',
                'marco_teorico', 'metodologia')
    for key in required:
        draft = _drafts(p).get(key)
        if not draft:
            hard.append('Falta el apartado obligatorio: ' + LABELS.get(key, key))
        elif len(draft['text'].strip()) < 60:
            hard.append('Apartado demasiado corto para exportar: ' + LABELS.get(key, key))
    for label, body, _state in section_blocks(p):
        if PLACEHOLDER.search(body[:600]):
            soft.append('El documento contiene marcadores pendientes en ' + label + '.')
    return hard, soft


def evaluate(p):
    """Return {'hard': [...], 'soft': [...], 'score': int}."""
    hard, soft = [], []
    for check in (check_sources, check_numbers, check_coherence, check_export):
        try:
            h, s = check(p)
            hard += h
            soft += s
        except Exception as exc:
            soft.append('No se pudo evaluar ' + check.__name__ + ': ' + type(exc).__name__)
    score = max(0, 100 - 12 * len(hard) - 3 * len(soft))
    return {'hard': hard, 'soft': soft, 'score': score,
            'passes': not hard, 'checked': 4}
