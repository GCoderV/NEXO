"""Assembled thesis document: one ordered structure and one write path.

Design borrowed from chat-first thesis agents (a single project-scoped state with
a validated mutation function), but implemented with the standard library only.
The document is a VIEW over the project's drafts: hiding a section never deletes
its text. Exports are Markdown, a self-contained HTML page (openable in Word)
and a minimal OOXML .docx. No Word COM, no network, no third-party packages.
"""
import html
import re
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from limits import MAX_DRAFT_CHARS
from project_store import LABELS, SECTIONS, now

MAX_EXTRA_SECTIONS = 24
PLACEHOLDER = '**[Por redactar]** Este apartado aún no tiene contenido verificado.'

# Sections that are optional templates: they may legitimately stay empty.
OPTIONAL = ('cronograma', 'presupuesto', 'anexos')
EMPIRICAL = ('resultados', 'discusion', 'conclusiones')


def slug(text, limit=48):
    base = ''.join(c for c in unicodedata.normalize('NFD', str(text or '').lower())
                   if unicodedata.category(c) != 'Mn')
    base = re.sub(r'[^a-z0-9]+', '-', base).strip('-')
    return (base[:limit].strip('-') or 'documento')


def extras(p):
    result = []
    for item in p.get('doc_extra', []):
        if isinstance(item, dict) and re.fullmatch(r'x-[a-z0-9-]{1,40}', str(item.get('key', ''))):
            result.append({'key': item['key'], 'label': str(item.get('label', ''))[:80] or item['key'],
                           'after': item.get('after', 'anexos')})
    return result


def hidden(p):
    return {k for k in p.get('doc_hidden', []) if isinstance(k, str)}


def label(p, key):
    if key in LABELS:
        return LABELS[key]
    for item in extras(p):
        if item['key'] == key:
            return item['label']
    return ''


def order(p):
    """Canonical sections first, then user-added ones right after their anchor."""
    keys = list(SECTIONS)
    for item in extras(p):
        anchor = item['after']
        position = keys.index(anchor) + 1 if anchor in keys else len(keys)
        # Preserve insertion order of extra sections sharing the same anchor.
        while position < len(keys) and keys[position].startswith('x-') and keys[position - 1] == anchor:
            position += 1
        keys.insert(position, item['key'])
    return keys


def outline_key_visible(p,key):
    return next((e['visible'] for e in outline(p) if e['key']==key),False)


def outline(p):
    off = hidden(p)
    entries = []
    for key in order(p):
        draft = p['drafts'].get(key)
        entries.append({
            'key': key,
            'label': label(p, key),
            'visible': key not in off,
            'custom': key.startswith('x-'),
            'has_draft': bool(draft),
            'chars': len(draft['text']) if draft else 0,
            'status': draft.get('status', 'sin_borrador') if draft else 'sin_borrador',
            'protected': bool(draft and (draft.get('edited_by_user') or draft.get('status') in
                                        ('aprobado_usuario', 'insertado_pendiente_revision_word'))),
            'sources': sorted(set(re.findall(r'\[[FD]\d+\]', draft['text']))) if draft else [],
        })
    return entries


def gaps(p):
    """Honest, actionable list of what is still missing. Never invents content."""
    out = []
    entries = {e['key']: e for e in outline(p)}
    missing = [e['label'] for e in outline(p) if e['visible'] and not e['has_draft'] and e['key'] not in OPTIONAL and not (e['key']=='referencias' and p.get('sources'))]
    if missing:
        out.append('Apartados sin borrador: ' + ', '.join(missing) + '.')
    revision = [e['label'] for e in outline(p) if e['visible'] and e['status'] == 'necesita_revision']
    if revision:
        out.append('Apartados desactualizados: ' + ', '.join(revision) + '.')
    optional = [e['label'] for e in outline(p) if e['key'] in OPTIONAL and e['visible'] and not e['has_draft']]
    if optional:
        out.append('Plantillas opcionales sin generar: ' + ', '.join(optional) + '.')
    if not p.get('sources'):
        out.append('No hay fuentes registradas: Referencias y Antecedentes no tienen respaldo verificable.')
    if not (p.get('data_ready') and p['facts'].get('datos')):
        out.append('No hay datos/corpus confirmados: no deben redactarse resultados empíricos.')
    uncited = [e['label'] for e in outline(p) if e['visible'] and e['key'] == 'marco_teorico'
               and e['has_draft'] and not e['sources']]
    if uncited:
        out.append('Marco teórico sin citas [F#]: añade fuentes verificables antes de usarlo.')
    if not out:
        out.append('No se detectan huecos estructurales. Revisa igualmente cada afirmación y cada cita.')
    return out


def references(p):
    lines = []
    for s in p.get('sources', []):
        year = s.get('year') or 's. f.'
        if str(year).lower() in ('none', 'null', ''):
            year = 's. f.'
        authors = s.get('authors') or 'Autoría por completar'
        title = s.get('title') or 'Título por completar'
        url = s.get('url') or ''
        lines.append('[{}] {} ({}). {}. {} — {}'.format(
            s.get('id', 'F?'), authors, year, title, url, s.get('status', 'procedencia no verificada')))
    return '\n\n'.join(lines) if lines else 'Sin fuentes registradas. No se inventaron referencias.'


def section_blocks(p):
    """(label, text, state) for every visible section of the assembled document."""
    off = hidden(p)
    blocks = []
    for e in outline(p):
        if not e['visible']:
            continue
        draft = p['drafts'].get(e['key'])
        if e['key'] == 'referencias':
            body = references(p)
            state = 'generado desde el registro de fuentes' if p.get('sources') else 'sin fuentes'
        elif draft:
            body = draft['text']
            state = draft.get('status', 'borrador')
        else:
            body = PLACEHOLDER
            state = 'pendiente'
        blocks.append((e['label'], body, state))
    return blocks


def compile_markdown(p):
    lines = ['# ' + (p.get('topic') or 'Tesis sin título'), '',
             '> Documento de trabajo generado por Nexo Tesis. No es una tesis validada: '
             'revisa cada afirmación, cita y dato antes de entregarlo.', '',
             'Generado: ' + now(), '', '## Estado del documento', '']
    lines += ['- ' + g for g in gaps(p)]
    lines += ['', '## Apartados incluidos', '']
    for label, _body, state in section_blocks(p):
        lines.append('- {} — {}'.format(label, state))
    lines += ['', '---', '']
    for label, body, state in section_blocks(p):
        lines += ['## ' + label, '', '*(Estado: ' + state + ')*', '', body, '']
    return '\n'.join(lines) + '\n'


def compile_html(p):
    def para(text):
        chunks = str(text).split('\n')
        return ''.join('<p>' + html.escape(c) + '</p>' if c.strip() else '<p>&nbsp;</p>' for c in chunks)
    parts = ['<!doctype html><html lang="es"><head><meta charset="utf-8">',
             '<title>' + html.escape(p.get('topic') or 'Tesis') + '</title>',
             '<style>body{font-family:Calibri,Arial,sans-serif;max-width:46em;margin:3em auto;'
             'line-height:1.55;color:#20242a}h1{font-size:1.9em}h2{border-bottom:1px solid #ccd;'
             'margin-top:2.2em;padding-bottom:.25em}.estado{color:#666;font-size:.9em}'
             'blockquote{background:#f5f7fa;padding:1em;border-left:4px solid #4b7b8a}</style>',
             '</head><body><h1>' + html.escape(p.get('topic') or 'Tesis sin título') + '</h1>',
             '<blockquote>Documento de trabajo generado por Nexo Tesis. No es una tesis validada; '
             'revisa cada afirmación, cita y dato antes de entregarlo.</blockquote>',
             '<h2>Estado del documento</h2><ul>']
    parts += ['<li>' + html.escape(g) + '</li>' for g in gaps(p)]
    parts += ['</ul><hr>']
    for label, body, state in section_blocks(p):
        parts += ['<h2>' + html.escape(label) + '</h2>',
                  '<p class="estado">Estado: ' + html.escape(state) + '</p>', para(body)]
    parts += ['</body></html>']
    return '\n'.join(parts)


def _docx_paragraph(text, style=None):
    props = '<w:pPr><w:pStyle w:val="{}"/></w:pPr>'.format(style) if style else ''
    runs = []
    for line in str(text).split('\n'):
        runs.append('<w:r><w:t xml:space="preserve">' + xml_escape(line) + '</w:t></w:r><w:r><w:br/></w:r>')
    return '<w:p>' + props + ''.join(runs) + '</w:p>'


def compile_docx(p):
    """Minimal WordprocessingML package. Standard OOXML, no Word automation."""
    body = [_docx_paragraph(p.get('topic') or 'Tesis sin título', 'Title'),
            _docx_paragraph('Documento de trabajo generado por Nexo Tesis. No es una tesis validada.'),
            _docx_paragraph('Estado del documento', 'Heading1')]
    body += [_docx_paragraph('• ' + g) for g in gaps(p)]
    for label, text, state in section_blocks(p):
        body.append(_docx_paragraph(label, 'Heading1'))
        body.append(_docx_paragraph('Estado: ' + state))
        body.append(_docx_paragraph(text))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body>' + ''.join(body) +
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418"/></w:sectPr>'
                '</w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
              '<w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
              '<w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/>'
              '<w:rPr><w:sz w:val="22"/></w:rPr></w:style></w:styles>')
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                     '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '</Relationships>')
    out = BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', document)
        z.writestr('word/styles.xml', styles)
        z.writestr('word/_rels/document.xml.rels', doc_rels)
    return out.getvalue()


def export(p, directory, basename=None):
    """Write the three offline formats into `directory` (created if needed)."""
    base = slug(basename or p.get('topic') or 'tesis')
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        base + '.md': compile_markdown(p).encode('utf-8'),
        base + '.html': compile_html(p).encode('utf-8'),
        base + '.docx': compile_docx(p),
    }
    for name, data in files.items():
        (folder / name).write_bytes(data)
    return {'directory': str(folder), 'files': sorted(files),
            'bytes': sum(len(v) for v in files.values()),
            'sections': len(section_blocks(p)), 'gaps': gaps(p),
            'hidden': sorted(hidden(p)), 'extra': [e['label'] for e in extras(p)]}


# --- The single validated write path -----------------------------------------

def fit(text):
    """Trim at a paragraph boundary with a VISIBLE notice, never a silent cut."""
    body = str(text or '')
    if len(body) <= MAX_DRAFT_CHARS:
        return body
    cut = body[:MAX_DRAFT_CHARS - 160]
    boundary = max(cut.rfind('\n\n'), cut.rfind('. '))
    if boundary > MAX_DRAFT_CHARS // 2:
        cut = cut[:boundary + 1]
    return cut.rstrip() + '\n\n> [Nexo] El texto se recortó por límite de ' + str(MAX_DRAFT_CHARS) + ' caracteres; faltan partes por entregar.'


def _known_ids(p):
    return {s['id'] for s in p.get('sources', [])} | {m['id'] for m in p.get('materials', [])}


def write_section(p, key, text, sources=(), producer='agente-loop'):
    """Validate and store one section. This is the ONLY mutation entry point."""
    if key not in order(p):
        raise ValueError('Apartado no existe en la estructura del documento.')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('El texto del apartado está vacío.')
    old = p['drafts'].get(key)
    if old and (old.get('edited_by_user') or old.get('status') in
                ('aprobado_usuario', 'insertado_pendiente_revision_word')):
        raise ValueError('El apartado está protegido: edítalo tú en Apartados antes de que el agente lo cambie.')
    if key in EMPIRICAL and not (p.get('data_ready') and p['facts'].get('datos')):
        raise ValueError('Faltan datos/corpus confirmados; no se redactarán resultados empíricos.')
    used = set(sources) | set(re.findall(r'\[([FD]\d+)\]', text))
    known = _known_ids(p)
    if not used <= known:
        raise ValueError('El texto cita fuentes inexistentes: ' + ', '.join(sorted(used - known)))
    body = references(p) if key == 'referencias' else fit(text)
    versions = (old.get('versions', []) + [{'text': old['text'], 'status': old['status'], 'time': now()}])[-5:] if old else []
    p['drafts'][key] = {'text': body, 'sources': sorted(used), 'status': 'borrador',
                        'warning': 'Propuesta del agente: revisar evidencia, coherencia y citas antes de aprobar.',
                        'time': now(), 'versions': versions, 'material_ids': (old or {}).get('material_ids', []),
                        'producer': {'provider': producer}}
    from autonomy import fingerprint
    p['drafts'][key]['auto_reviewed_for'] = fingerprint(p, body)
    return {'section': key, 'label': label(p, key), 'chars': len(body), 'sources': sorted(used)}


def patch_section(p, key, anchor, new_text, mode='insert_after'):
    """Surgical edit: change exactly one anchored fragment, keep the rest intact."""
    if key not in order(p):
        raise ValueError('Apartado no existe.')
    draft = p['drafts'].get(key)
    if not draft:
        raise ValueError('No hay borrador en ese apartado; usa escribir_apartado.')
    if draft.get('edited_by_user') or draft.get('status') in ('aprobado_usuario', 'insertado_pendiente_revision_word'):
        raise ValueError('El apartado está protegido.')
    if not isinstance(anchor, str) or not anchor.strip():
        raise ValueError('Indica el fragmento exacto a localizar.')
    if draft['text'].count(anchor) != 1:
        raise ValueError('El fragmento indicado no aparece exactamente una vez; no se editó nada.')
    if mode == 'insert_after':
        body = draft['text'].replace(anchor, anchor + str(new_text), 1)
    elif mode == 'remove':
        body = draft['text'].replace(anchor, '', 1)
    elif mode == 'replace':
        if not isinstance(new_text, str) or not new_text.strip():
            raise ValueError('Falta el texto de reemplazo.')
        body = draft['text'].replace(anchor, str(new_text), 1)
    else:
        raise ValueError('Modo de edición no admitido.')
    return write_section(p, key, body, draft.get('sources', []))


def add_extra(p, title, after='anexos'):
    key = 'x-' + slug(title, 36)
    items = [i for i in p.get('doc_extra', []) if isinstance(i, dict)]
    if not isinstance(title, str) or not 2 <= len(title.strip()) <= 80:
        raise ValueError('Título de apartado inválido.')
    if len(items) >= MAX_EXTRA_SECTIONS:
        raise ValueError('Límite de apartados adicionales alcanzado.')
    if key in order(p):
        raise ValueError('Ya existe un apartado con ese nombre.')
    if after not in order(p):
        after = 'anexos'
    items.append({'key': key, 'label': title.strip(), 'after': after})
    p['doc_extra'] = items
    return {'key': key, 'label': title.strip(), 'after': after}


def set_visible(p, key, visible=True):
    if key not in order(p):
        raise ValueError('Apartado no existe.')
    keys = set(hidden(p))
    if visible:
        keys.discard(key)
    else:
        keys.add(key)
    p['doc_hidden'] = sorted(keys)
    return {'key': key, 'label': label(p, key), 'visible': bool(visible),
            'note': 'El borrador se conservó; solo se ocultó en el documento.' if not visible else ''}


def compact_state(p):
    """Small JSON summary used as the loop's acceptance check after each pass."""
    entries = outline(p)
    return {'sections': len(entries),
            'with_draft': sum(1 for e in entries if e['has_draft'] and e['visible']),
            'missing': [e['key'] for e in entries if e['visible'] and not e['has_draft']],
            'needs_revision': [e['key'] for e in entries if e['visible'] and e['status'] == 'necesita_revision'],
            'hidden': sorted(hidden(p)), 'sources': len(p.get('sources', [])),
            'gaps': gaps(p)}
