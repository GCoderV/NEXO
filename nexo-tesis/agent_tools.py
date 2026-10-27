"""Bounded tool registry for the agent loop. Host-enforced, not model-enforced.

Every mutation goes through `document.write_section` / `patch_section` (one write
path, like a commit_slice). Tool failures are returned as data, never raised into
the loop. The model never gets file-system paths, Word automation, credentials or
the ability to invent a source id: citations are checked against the project.
"""
import json

import bibliography
import document
from limits import MAX_DRAFT_CHARS
from project_store import FACT_KEYS, invalidate, now

MAX_CALLS_PER_PASS = 4
MAX_ARGUMENT_CHARS = 25000
MAX_TOOL_TEXT_CHARS = 40000

# name: (short spec for the prompt, mutates?, needs)
TOOLS = {
    'ver_documento': ({}, False, ''),
    'leer_apartado': ({'section': 'clave del apartado'}, False, ''),
    'listar_fuentes': ({}, False, ''),
    'ver_pendientes': ({'include_optional': 'true/false opcional'}, False, ''),
    'ver_estado': ({}, False, ''),
    'buscar_fuentes': ({'query': 'términos; separados por ;'}, True, 'research'),
    'escribir_apartado': ({'section': 'clave', 'text': 'texto completo', 'sources': '[F#] opcional'}, True, ''),
    'editar_texto': ({'section': 'clave', 'fragmento': 'texto exacto existente',
                      'nuevo': 'texto nuevo (vacío para eliminar)',
                      'modo': 'insertar_despues|reemplazar|eliminar'}, True, ''),
    'anadir_apartado': ({'titulo': 'nombre visible', 'despues_de': 'clave opcional'}, True, ''),
    'quitar_apartado': ({'section': 'clave'}, True, ''),
    'restaurar_apartado': ({'section': 'clave'}, True, ''),
    'generar_documento': ({}, True, 'export'),
    'registrar_dato': ({'clave': 'dato permitido', 'valor': 'texto',
                        'evidencia': 'cita literal del mensaje del usuario'}, True, 'user_fact'),
    'preguntar_usuario': ({'texto': 'pregunta concreta'}, True, 'boundary'),
    'finalizar': ({'motivo': 'por qué se detiene'}, False, 'boundary'),
}

TOOL_GUIDE = (
    'Herramientas (máximo 4 por paso; una acción acotada por paso):\n'
    'ver_documento() · ver_estado() · ver_pendientes() · leer_apartado(section) · listar_fuentes()\n'
    'buscar_fuentes(query) · escribir_apartado(section,text,sources) · '
    'editar_texto(section,fragmento,nuevo,modo) · anadir_apartado(titulo,despues_de) · '
    'quitar_apartado(section) · restaurar_apartado(section) · generar_documento() · '
    'registrar_dato(clave,valor,evidencia) · preguntar_usuario(texto) · finalizar(motivo).\n'
    'Usa las claves que devuelve ver_documento. Nunca escribas Word ni archivos fuera del proyecto.'
)


def catalog():
    return [{'name': name, 'arguments': spec, 'mutates': mutates}
            for name, (spec, mutates, _needs) in TOOLS.items()]


def validate_calls(calls):
    """Reject unknown tools and oversized arguments before anything executes."""
    if not isinstance(calls, list) or len(calls) > MAX_CALLS_PER_PASS:
        raise ValueError('Demasiadas herramientas en un paso.')
    checked = []
    for call in calls:
        if not isinstance(call, dict):
            raise ValueError('Llamada de herramienta inválida.')
        name = call.get('name', call.get('tool', call.get('herramienta')))
        args = call.get('arguments', call.get('args', call.get('parametros', {})))
        if not isinstance(name, str) or name not in TOOLS:
            raise ValueError('Herramienta no disponible: ' + str(name)[:60])
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                raise ValueError('Argumentos de herramienta no son JSON válido.')
        if not isinstance(args, dict):
            raise ValueError('Argumentos de herramienta inválidos.')
        if len(json.dumps(args, ensure_ascii=False)) > MAX_ARGUMENT_CHARS:
            raise ValueError('Argumentos de herramienta demasiado largos.')
        checked.append({'name': name, 'arguments': args})
    return checked


def _text(args, key, required=True, limit=MAX_DRAFT_CHARS):
    value = args.get(key)
    if value is None and not required:
        return ''
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('Argumento ' + key + ' inválido o demasiado largo.')
    return value


def _section(p, args):
    key = _text(args, 'section', limit=60)
    if key not in document.order(p):
        raise ValueError('Apartado desconocido: ' + key[:40])
    return key


def _short(value, limit=900):
    text = str(value)
    return text if len(text) <= limit else text[:limit] + '…'


def execute(p, call, services):
    """Return {'ok','tool','summary','data','changed','stop'}. Never raises out."""
    name = call['name']
    args = call['arguments']
    result = {'ok': False, 'tool': name, 'summary': '', 'data': None,
              'changed': False, 'stop': None}
    needs = TOOLS[name][2]
    try:
        if needs == 'research':
            if not services.get('allow_research') or services.get('approve_search') is None:
                raise ValueError('La búsqueda externa no está autorizada en esta sesión.')
            query = _text(args, 'query', limit=2000)
            queries = bibliography.normalize_queries(query)
            if not queries:
                raise ValueError('No se pudo construir una consulta válida.')
            if services['approve_search']('; '.join(queries), 'Búsqueda solicitada por el agente') is not True:
                raise ValueError('Consulta no autorizada; no se envió nada a Crossref.')
            items, failures = [], []
            searcher = services.get('searcher') or bibliography.search
            for q in queries:
                try:
                    found = searcher(q)
                    if isinstance(found, list):
                        items.extend(found)
                except Exception as exc:
                    failures.append(type(exc).__name__)
            added = bibliography.add_sources(p, items)
            result['data'] = {'queries': queries, 'added': added, 'errors': failures[:3]}
            result['summary'] = ('Fuentes nuevas: ' + ', '.join(added) if added else
                                 'Crossref no devolvió fuentes nuevas (' + '; '.join(failures[:2]) + ').')
            if added:
                invalidate(p, 'Se añadieron fuentes; revisar citas y evidencia.')
                result['changed'] = True

        elif name == 'ver_documento':
            entries = document.outline(p)
            result['data'] = {'entries': [{'key': e['key'], 'label': e['label'],
                                           'state': e['status'], 'chars': e['chars'],
                                           'visible': e['visible'], 'protected': e['protected']}
                                          for e in entries],
                              'state': document.compact_state(p)}
            result['summary'] = 'Estructura: ' + ', '.join(
                e['key'] + ('*' if e['visible'] else '-oculto') for e in entries)

        elif name == 'ver_estado':
            result['data'] = document.compact_state(p)
            result['summary'] = '; '.join(document.gaps(p)[:4])

        elif name == 'ver_pendientes':
            from autonomy import plan
            flag = args.get('include_optional', True)
            flag = True if flag is True or str(flag).lower() in ('true', '1', 'si', 'sí') else False
            tasks, notice = plan(p, flag)
            result['data'] = {'tasks': tasks[:12], 'total': len(tasks), 'notice': notice}
            result['summary'] = str(len(tasks)) + ' tareas pendientes. ' + notice[:400]

        elif name == 'leer_apartado':
            key = _section(p, args)
            draft = p['drafts'].get(key)
            result['data'] = {'section': key, 'text': draft['text'][:12000] if draft else '',
                              'status': draft.get('status', 'sin_borrador') if draft else 'sin_borrador',
                              'truncated': bool(draft and len(draft['text']) > 12000)}
            result['summary'] = (document.label(p, key) + ': ' +
                                 (str(len(draft['text'])) + ' caracteres' if draft else 'sin borrador'))

        elif name == 'listar_fuentes':
            sources = [{'id': s.get('id', ''), 'title': s.get('title', '')[:140],
                        'year': s.get('year', ''), 'status': s.get('status', '')}
                       for s in p.get('sources', [])[:40]]
            result['data'] = {'sources': sources, 'total': len(p.get('sources', []))}
            result['summary'] = str(len(p.get('sources', []))) + ' fuentes registradas'

        elif name == 'escribir_apartado':
            key = _section(p, args)
            text = _text(args, 'text', limit=MAX_TOOL_TEXT_CHARS)
            sources = args.get('sources', [])
            if not isinstance(sources, list):
                sources = []
            sources = [str(x) for x in sources[:30] if isinstance(x, (str, int))]
            made = document.write_section(p, key, text, sources,
                                          producer=services.get('producer', 'agente-loop'))
            result.update(data=made, changed=True,
                          summary='Guardado ' + made['label'] + ' (' + str(made['chars']) + ' caracteres).')

        elif name == 'editar_texto':
            key = _section(p, args)
            fragment = _text(args, 'fragmento', limit=12000)
            mode = {'insertar_despues': 'insert_after', 'reemplazar': 'replace',
                    'eliminar': 'remove'}.get(str(args.get('modo', 'insertar_despues')))
            if not mode:
                raise ValueError('Modo debe ser insertar_despues, reemplazar o eliminar.')
            new = _text(args, 'nuevo', required=(mode != 'remove'), limit=MAX_TOOL_TEXT_CHARS)
            made = document.patch_section(p, key, fragment, new, mode)
            result.update(data=made, changed=True,
                          summary='Edición aplicada en ' + made['label'] + '; el resto del texto se conservó.')

        elif name == 'anadir_apartado':
            title = _text(args, 'titulo', limit=80)
            after = args.get('despues_de') or 'anexos'
            made = document.add_extra(p, title, str(after))
            result.update(data=made, changed=True,
                          summary='Apartado añadido: ' + made['label'] + ' (' + made['key'] + ').')

        elif name in ('quitar_apartado', 'restaurar_apartado'):
            key = _section(p, args)
            made = document.set_visible(p, key, name == 'restaurar_apartado')
            result.update(data=made, changed=True,
                          summary='Apartado ' + ('restaurado: ' if made['visible'] else 'ocultado: ') + made['label'] + '. ' + made['note'])

        elif name == 'generar_documento':
            if not services.get('allow_export'):
                raise ValueError('La exportación no está autorizada en esta sesión.')
            folder = services.get('export_dir')
            if not folder:
                raise ValueError('No se configuró la carpeta de documentos.')
            made = document.export(p, folder)
            result.update(data=made, changed=False,
                          summary='Documento completo generado: ' + ', '.join(made['files']) +
                                  '. Huecos: ' + str(len(made['gaps'])) + '.')

        elif name == 'registrar_dato':
            if needs == 'user_fact' and services.get('origin') != 'usuario':
                raise ValueError('Un paso automático no puede crear datos del usuario.')
            key = _text(args, 'clave', limit=60)
            value = _text(args, 'valor', limit=12000)
            evidence = _text(args, 'evidencia', limit=6000)
            if key not in FACT_KEYS:
                raise ValueError('Dato no admitido: ' + key[:40])
            if evidence not in services.get('user_text', '') and evidence not in p.get('topic', ''):
                raise ValueError('La evidencia no es una cita literal; no se guardó el dato.')
            from project_store import set_fact
            set_fact(p, key, value, evidence, 'aportado por el usuario en el objetivo del agente')
            result.update(data={'key': key}, changed=True, summary='Dato registrado: ' + key)

        elif name == 'preguntar_usuario':
            text = _text(args, 'texto', limit=1000)
            p['questions'].append({'id': 'loop-' + now(), 'key': 'contexto', 'text': text,
                                   'status': 'abierta', 'clarify': False, 'time': now(), 'material_ids': []})
            result.update(data={'question': text}, changed=True, stop='pregunta',
                          summary='Pregunta abierta al usuario: ' + text)

        elif name == 'finalizar':
            reason = _text(args, 'motivo', limit=600)
            result.update(data={'reason': reason}, stop='finalizado',
                          summary='Agente finalizó: ' + reason)
        else:
            raise ValueError('Herramienta no implementada.')
        result['ok'] = True
    except Exception as exc:
        # Contain tool failures: the loop continues with a bounded error result.
        result['ok'] = False
        result['summary'] = 'No se pudo ejecutar ' + name + ': ' + str(exc)[:300]
        result['data'] = {'error': type(exc).__name__}
    return result


def receipt_line(result):
    flag = 'OK' if result['ok'] else 'FALLO'
    return '[' + flag + '] ' + result['tool'] + ': ' + _short(result['summary'], 500)
