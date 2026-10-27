"""Fase 1: single source of truth + the ONLY validated write path.

Adapted from DoThesis's `commit_slice` invariant (AGENTS.md / agent/state.py)
to Nexo's local, single-user project dict. Everything that changes a project —
tools, the agent loop, the UI editor, research and autonomous drafting — must
go through `commit_slice()` or `write_sections()`. Reads are free.

Guarantees:
* `modules` is a derived status map M1..M5, safe to recompute at any time.
* Every write validates ownership, types, bounds and citation ids.
* A snapshot is saved BEFORE applying, so a bad commit can be undone.
* A change to an upstream module flags started downstream modules as
  `needs_review` through a fixed DAG; `done` never silently flaps back.
* `verify()` is the deterministic acceptance check that tells the continuous
  agent loop when the work is actually finished.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from diagnostics import as_key, as_text
from limits import MAX_DRAFT_CHARS
from project_store import FACT_KEYS, LABELS, SECTIONS, invalidate, now

MODULES = ('M1', 'M2', 'M3', 'M4', 'M5')
MODULE_LABELS = {
    'M1': 'Tema y planteamiento',
    'M2': 'Fuentes y marco teórico',
    'M3': 'Diseño metodológico',
    'M4': 'Datos y resultados',
    'M5': 'Escritura y documento',
}
# A change upstream invalidates these downstream modules.
DAG = {'M1': ('M2', 'M3', 'M4', 'M5'), 'M2': ('M3', 'M4', 'M5'),
       'M3': ('M4', 'M5'), 'M4': ('M5',), 'M5': ()}

OWNED_DRAFTS = {
    'M1': ('delimitacion', 'problematica', 'pregunta', 'objetivos', 'justificacion'),
    'M2': ('marco_teorico', 'referencias'),
    'M3': ('metodologia', 'instrumentos', 'plan_accion', 'analisis_previsto'),
    'M4': ('resultados', 'discusion', 'conclusiones'),
    'M5': ('cronograma', 'presupuesto', 'anexos'),
}
OWNED_FACTS = {
    'M1': ('poblacion', 'nivel', 'contexto', 'objetivo_usuario', 'alcance', 'tipo_trabajo'),
    'M2': (),
    'M3': ('metodologia',),
    'M4': ('datos',),
    'M5': (),
}
OPTIONAL = ('cronograma', 'presupuesto', 'anexos')
EMPIRICAL = ('resultados', 'discusion', 'conclusiones')
PLACEHOLDER = re.compile(r'\[Por redactar\]|Por definir|sin borrador', re.I)
MAX_HISTORY = 8


def module_for_section(section):
    for module, owned in OWNED_DRAFTS.items():
        if section in owned:
            return module
    if isinstance(section, str) and section.startswith('x-'):
        return 'M5'
    return 'M5'


def ensure(p):
    """Initialise derived state for legacy 0.4.x projects without losing data."""
    modules = p.get('modules')
    if not isinstance(modules, dict):
        modules = {}
    for module in MODULES:
        record = modules.get(module)
        if not isinstance(record, dict):
            record = {'status': 'locked', 'confirmed_at': None, 'updated': None}
        record.setdefault('status', 'locked')
        record.setdefault('confirmed_at', None)
        modules[module] = record
    p['modules'] = modules
    if not isinstance(p.get('state_history'), list):
        p['state_history'] = []
    return p


def _known_ids(p):
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


def _valid_section(p, section):
    if not isinstance(section, str) or len(section) > 48:
        return False
    if section in SECTIONS:
        return True
    return any(isinstance(x, dict) and x.get('key') == section
               for x in p.get('doc_extra', []))


def _source_shape(item):
    if not isinstance(item, dict):
        return None
    out = {}
    for key in ('title', 'authors', 'year', 'doi', 'url', 'status', 'excerpt',
                'locator', 'supports', 'origin', 'retrieved', 'query',
                'verified_by', 'provenance', 'verification'):
        if key in item:
            value = item[key]
            if key == 'verified_by' and isinstance(value, list):
                out[key] = [as_text(x, 'provider', 60) for x in value[:8]]
            else:
                out[key] = as_text(value, 'source.' + key, 6000)
    out.setdefault('title', 'Sin título')
    out.setdefault('status', 'metadatos sin verificar')
    return out


def _snapshot(p, module, reason, changed):
    """Store only what is needed to undo: pre-change text of changed sections."""
    prior = {}
    for section in changed:
        draft = p.get('drafts', {}).get(section)
        if isinstance(draft, dict):
            prior[section] = {k: draft.get(k) for k in
                              ('text', 'status', 'sources', 'warning', 'versions')}
    p['state_history'].append({
        'time': now(), 'module': module, 'reason': as_text(reason, 'reason', 300),
        'sections': prior,
        'sources': len(p.get('sources', [])),
        'digest': hashlib.sha256(json.dumps(
            {k: p.get('drafts', {}).get(k, {}).get('text', '') for k in sorted(changed)},
            ensure_ascii=False).encode()).hexdigest()[:16],
    })
    p['state_history'] = p['state_history'][-MAX_HISTORY:]


def validate_writes(p, module, writes):
    """Reject illegal ownership, bad types, invented citations and oversize."""
    if not isinstance(writes, dict) or not writes:
        raise ValueError('No hay cambios que confirmar.')
    allowed = {'drafts', 'facts', 'sources', 'topic', 'data_ready', 'doc_extra',
               'doc_hidden', 'remove_sections', 'hide_sections', 'show_sections',
               'questions', 'provider_references'}
    illegal = set(writes) - allowed
    if illegal:
        raise ValueError('Campos no admitidos en commit_slice: ' + ', '.join(sorted(map(str, illegal))))
    if module not in MODULES:
        raise ValueError('Módulo desconocido: ' + str(module)[:40])
    drafts = writes.get('drafts', {})
    if not isinstance(drafts, dict):
        raise ValueError('drafts debe ser un objeto.')
    for section in drafts:
        draft = p.get('drafts', {}).get(as_key(section, 'draft.section'))
        if isinstance(draft, dict) and (draft.get('edited_by_user') or draft.get('status') in
                ('aprobado_usuario', 'insertado_pendiente_revision_word')):
            raise ValueError('El apartado está protegido: ' + str(section)[:40] +
                             '. Edítalo tú en Apartados antes de que el agente lo cambie.')
    known = _known_ids(p)
    for section, body in drafts.items():
        if not _valid_section(p, as_key(section, 'draft.section')):
            raise ValueError('Apartado no reconocido: ' + str(section)[:40])
        if not isinstance(body, str) or not body.strip():
            raise ValueError('Texto vacío en ' + str(section)[:40])
        owner = module_for_section(section)
        if owner != module and module != 'M5':
            raise ValueError(MODULE_LABELS[module] + ' no posee ' + str(section) +
                             '; corresponde a ' + MODULE_LABELS[owner] + '.')
        if len(body) > MAX_DRAFT_CHARS * 2:
            raise ValueError('Borrador demasiado largo: ' + str(section)[:40])
        used = set(re.findall(r'\[([FD]\d+)\]', body))
        if not used <= known:
            raise ValueError('Cita inexistente en ' + str(section)[:40] + ': ' +
                             ', '.join(sorted(used - known)))
        if section in EMPIRICAL and not (p.get('data_ready') and p.get('facts', {}).get('datos')):
            raise ValueError('Faltan datos confirmados para ' + str(section)[:40] +
                             '; no se fabricarán resultados.')
    facts = writes.get('facts', {})
    if not isinstance(facts, dict):
        raise ValueError('facts debe ser un objeto.')
    for key in facts:
        if as_key(key, 'fact.key') not in FACT_KEYS:
            raise ValueError('Dato no admitido: ' + str(key)[:40])
    sources = writes.get('sources', [])
    if not isinstance(sources, list) or len(sources) > 60:
        raise ValueError('Lista de fuentes inválida.')
    for item in sources:
        if _source_shape(item) is None:
            raise ValueError('Fuente inválida: se esperaba un objeto.')
    if 'topic' in writes and not isinstance(writes['topic'], str):
        raise ValueError('Tema inválido.')
    if 'data_ready' in writes and type(writes['data_ready']) is not bool:
        raise ValueError('data_ready debe ser verdadero/falso.')
    return drafts, facts, sources


def _apply(p, module, writes, drafts, facts, sources, actor):
    changed = []
    if 'topic' in writes:
        p['topic'] = as_text(writes['topic'], 'topic', 1500)
    if 'data_ready' in writes:
        p['data_ready'] = bool(writes['data_ready'])
    for key, value in facts.items():
        key = as_key(key, 'fact.key')
        text = as_text(value, 'fact.value', 12000) if isinstance(value, str) else \
            json.dumps(value, ensure_ascii=False, default=str)[:12000]
        p.setdefault('facts', {})[key] = {
            'value': text, 'evidence': 'aportado por ' + as_text(actor, 'actor', 60),
            'source': actor, 'status': 'aportado, no verificado externamente',
            'time': now()}
        invalidate(p, 'Se incorporó el dato ' + key + '; revisar dependencias.')
    if sources:
        from bibliography import _next_source_id
        existing = {str(s.get('doi', '')).lower() for s in p.get('sources', [])
                    if isinstance(s, dict) and s.get('doi')}
        for item in sources:
            shape = _source_shape(item)
            doi = str(shape.get('doi', '')).lower()
            if doi and doi in existing:
                continue
            if len(p.get('sources', [])) >= 150:
                break
            shape['id'] = shape.get('id') or _next_source_id(p)
            p.setdefault('sources', []).append(shape)
            if doi:
                existing.add(doi)
        invalidate(p, 'Se añadieron fuentes; revisar citas y evidencia.')
    for section, body in drafts.items():
        section = as_key(section, 'draft.section')
        old = p.get('drafts', {}).get(section)
        if old and (old.get('edited_by_user') or old.get('status') in
                    ('aprobado_usuario', 'insertado_pendiente_revision_word')):
            continue  # protected drafts are never overwritten by the agent
        from document import fit, references
        text = references(p) if section == 'referencias' else fit(body)
        versions = (old.get('versions', []) + [
            {'text': old['text'], 'status': old.get('status'), 'time': now()}])[-5:] if old else []
        p.setdefault('drafts', {})[section] = {
            'text': text,
            'sources': sorted(set(re.findall(r'\[([FD]\d+)\]', text))),
            'status': 'borrador',
            'warning': 'Propuesta de ' + as_text(actor, 'actor', 60) +
                       ': revisar evidencia, coherencia y citas antes de aprobar.',
            'time': now(), 'versions': versions,
            'material_ids': (old or {}).get('material_ids', []),
            'producer': {'provider': actor}}
        from autonomy import fingerprint
        p['drafts'][section]['auto_reviewed_for'] = fingerprint(p, text)
        changed.append(section)
    for section in writes.get('remove_sections', []) or []:
        section = as_key(section, 'remove.section')
        if section in p.get('drafts', {}):
            p['drafts'].pop(section, None)
            changed.append(section)
    if 'doc_extra' in writes:
        p['doc_extra'] = [x for x in writes['doc_extra'] if isinstance(x, dict)][:24]
    if 'doc_hidden' in writes:
        p['doc_hidden'] = [as_key(x, 'hidden.key') for x in writes['doc_hidden']][:40]
    hidden = set(p.get('doc_hidden', []))
    for key in writes.get('hide_sections', []) or []:
        hidden.add(as_key(key, 'hide.key'))
    for key in writes.get('show_sections', []) or []:
        hidden.discard(as_key(key, 'show.key'))
    p['doc_hidden'] = sorted(hidden)
    if isinstance(writes.get('questions'), list):
        for q in writes['questions'][:4]:
            if isinstance(q, dict) and isinstance(q.get('text'), str):
                p.setdefault('questions', []).append({
                    'id': 'state-' + now(), 'key': as_key(q.get('key'), 'question.key', 'contexto'),
                    'text': as_text(q['text'], 'question.text', 1000),
                    'status': 'abierta', 'clarify': False, 'time': now(), 'material_ids': []})
    if isinstance(writes.get('provider_references'), list):
        p['provider_references'] = writes['provider_references'][:30]
    return changed


def commit_slice(p, module, writes, reason, actor='agente', confirm_done=False):
    """The ONLY write path. Returns a receipt; never raises on protected data."""
    ensure(p)
    drafts, facts, sources = validate_writes(p, module, writes)
    changed = sorted(drafts)
    _snapshot(p, module, reason, changed)
    try:
        applied = _apply(p, module, writes, drafts, facts, sources, actor)
    except Exception:
        undo_last(p)  # never leave a half-applied commit
        raise
    record = p['modules'][module]
    record['updated'] = now()
    if confirm_done:
        if not _has_content(p, module):
            raise ValueError('No se puede marcar ' + MODULE_LABELS[module] +
                             ' como terminado sin contenido propio.')
        record['status'] = 'done'
        record['confirmed_at'] = now()
    elif record.get('status') != 'done':
        record['status'] = 'in_progress'
    for downstream in DAG[module]:
        target = p['modules'][downstream]
        if target.get('status') in ('in_progress', 'done'):
            target['status'] = 'needs_review'
    p['last_commit'] = {'module': module, 'reason': as_text(reason, 'reason', 300),
                        'actor': as_text(actor, 'actor', 60), 'sections': applied,
                        'time': now(), 'sources_added': len(sources)}
    return {'ok': True, 'module': module, 'changed': applied,
            'status': dict((m, p['modules'][m]['status']) for m in MODULES),
            'downstream_flagged': list(DAG[module])}


def write_sections(p, sections, reason='Escritura del agente', actor='agente'):
    """Convenience wrapper: groups sections by owning module automatically."""
    grouped = {}
    for section in sections:
        grouped.setdefault(module_for_section(section), {})[section] = sections[section]
    receipts = []
    for module, drafts in grouped.items():
        receipts.append(commit_slice(p, module, {'drafts': drafts}, reason, actor))
    return receipts


def read_slice(p, module, include_text=False):
    ensure(p)
    if module not in MODULES:
        raise ValueError('Módulo desconocido.')
    drafts = {}
    for section in OWNED_DRAFTS[module]:
        draft = p.get('drafts', {}).get(section)
        if draft:
            drafts[section] = {'chars': len(draft.get('text', '')),
                               'status': draft.get('status'),
                               'text': draft.get('text', '')[:MAX_DRAFT_CHARS] if include_text else None}
    if module == 'M5':
        for draft in p.get('doc_extra', []):
            if isinstance(draft, dict):
                key = as_key(draft.get('key'), 'extra.key')
                value = p.get('drafts', {}).get(key)
                if value:
                    drafts[key] = {'chars': len(value.get('text', '')),
                                   'status': value.get('status'), 'text': None}
    return {'module': module, 'label': MODULE_LABELS[module],
            'status': p['modules'][module]['status'], 'drafts': drafts,
            'facts': {k: p.get('facts', {}).get(k, {}).get('value')
                      for k in OWNED_FACTS[module] if k in p.get('facts', {})},
            'sources': len(p.get('sources', [])) if module == 'M2' else None,
            'data_ready': p.get('data_ready') if module == 'M4' else None}


def _has_content(p, module):
    if module == 'M1':
        return bool(p.get('topic')) and any(p.get('drafts', {}).get(k) for k in OWNED_DRAFTS['M1'][:4])
    if module == 'M2':
        return bool(p.get('sources')) and bool(p.get('drafts', {}).get('marco_teorico'))
    if module == 'M3':
        return bool(p.get('drafts', {}).get('metodologia'))
    if module == 'M4':
        return bool(p.get('facts', {}).get('datos')) or bool(p.get('drafts', {}).get('resultados'))
    skip = set(OPTIONAL)
    if not p.get('facts', {}).get('datos'):
        skip.update(EMPIRICAL)  # an anteproyecto has no empirical results yet
    visible = [s for s in section_order(p) if s not in skip and s != 'referencias']
    needed = max(6, len(visible) - 3)
    return sum(1 for s in visible if p.get('drafts', {}).get(s)) >= needed


def section_order(p):
    """Canonical sections + custom ones, minus hidden; M5's deliverable shape."""
    from document import order, hidden
    off = hidden(p)
    return [k for k in order(p) if k not in off]


def status_map(p):
    """Derive status from REAL content. Done must be earned, not narrated.

    A stored `needs_review` flag (set by the DAG or by invalidate()) keeps a
    module out of `done` until it is written again, so upstream changes cannot
    be silently ignored. This is what the continuous loop verifies.
    """
    ensure(p)
    out = {}
    for module in MODULES:
        record = p['modules'][module]
        review = record.get('status') == 'needs_review' or any(
            p.get('drafts', {}).get(s, {}).get('status') == 'necesita_revision'
            for s in OWNED_DRAFTS[module])
        if not _has_content(p, module):
            out[module] = 'locked'
        elif review:
            out[module] = 'needs_review'
        else:
            out[module] = 'done'
    return out


def next_action(p, include_optional=True):
    """Next module/sub-step with a reason. Feeds the continuous loop's nudge."""
    status = status_map(p)
    for module in MODULES:
        if status[module] != 'done':
            missing = [s for s in OWNED_DRAFTS[module]
                       if not p.get('drafts', {}).get(s)]
            if module == 'M2' and not p.get('sources'):
                return {'module': module, 'reason': 'No hay fuentes verificables: investiga antes de redactar.',
                        'suggested_tool': 'investigar', 'missing': missing}
            if module == 'M4' and not p.get('facts', {}).get('datos'):
                return {'module': module, 'reason': 'Faltan datos/corpus aportados; no se inventarán resultados.',
                        'suggested_tool': 'preguntar_usuario', 'missing': missing}
            return {'module': module, 'reason': 'Faltan apartados de ' + MODULE_LABELS[module] + '.',
                    'suggested_tool': 'escribir_apartado', 'missing': missing}
    if include_optional:
        for section in OPTIONAL:
            if not p.get('drafts', {}).get(section):
                return {'module': 'M5', 'reason': 'Falta la plantilla opcional ' + LABELS.get(section, section) + '.',
                        'suggested_tool': 'escribir_apartado', 'missing': [section]}
    return {'module': None, 'reason': 'Estructura completa.', 'suggested_tool': 'generar_documento', 'missing': []}


def verify(p, include_optional=True):
    """Deterministic acceptance check. `done=True` ends the continuous loop."""
    from gates import evaluate
    status = status_map(p)
    missing, blocked, warnings = [], [], []
    for module in MODULES:
        if status[module] != 'done':
            missing.append(module + ': ' + MODULE_LABELS[module])
    if not p.get('sources'):
        blocked.append('Sin fuentes registradas: el marco teórico y las referencias no tienen respaldo.')
    for section in section_order(p):
        draft = p.get('drafts', {}).get(section)
        if section in OPTIONAL or section in EMPIRICAL:
            continue
        if not draft:
            missing.append('Apartado: ' + LABELS.get(section, section))
        elif PLACEHOLDER.search(draft.get('text', '')[:400]) or len(draft.get('text', '')) < 60:
            missing.append('Apartado incompleto: ' + LABELS.get(section, section))
        elif draft.get('status') == 'necesita_revision':
            warnings.append('Revisar: ' + LABELS.get(section, section))
    gates = evaluate(p)
    blocked += gates['hard']
    warnings += gates['soft']
    if include_optional:
        for section in OPTIONAL:
            if not p.get('drafts', {}).get(section):
                warnings.append('Plantilla opcional pendiente: ' + LABELS.get(section, section))
    done = not missing and not blocked and all(status[m] == 'done' for m in MODULES)
    return {'done': done, 'missing': missing, 'blocked': blocked,
            'warnings': warnings, 'status': status,
            'next': next_action(p, include_optional),
            'score': gates['score'],
            'summary': ('Trabajo terminado.' if done else
                        str(len(missing)) + ' apartados pendientes, ' +
                        str(len(blocked)) + ' bloqueos, ' + str(len(warnings)) + ' avisos.')}


def confirm_module(p, module, actor='usuario'):
    """Explicit user sign-off: marks a module done only if it has content."""
    ensure(p)
    if not _has_content(p, module):
        raise ValueError(MODULE_LABELS[module] + ' todavía no tiene contenido suficiente.')
    p['modules'][module]['status'] = 'done'
    p['modules'][module]['confirmed_at'] = now()
    return status_map(p)


def undo_last(p):
    ensure(p)
    if not p['state_history']:
        return {'ok': False, 'reason': 'No hay commits que deshacer.'}
    entry = p['state_history'].pop()
    restored = []
    for section, draft in entry.get('sections', {}).items():
        if isinstance(draft, dict) and isinstance(draft.get('text'), str):
            p.setdefault('drafts', {})[section] = dict(draft)
            restored.append(section)
    return {'ok': True, 'restored': restored, 'module': entry.get('module')}
