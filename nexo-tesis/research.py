"""Fase 3: bounded, provenance-carrying academic discovery.

The agent mode must "hacer todas las investigaciones del lugar". This module
does the searching deterministically (not by asking the model to promise it):
it derives query facets from the project's OWN topic/facts, queries several
public metadata APIs within a shared budget, deduplicates, records which
provider saw each item, and returns candidates ready for commit_slice(M2).

No network in this sandbox: every provider failure is contained and reported.
Nothing here downloads full text. Verified metadata is NOT proof that a paper
supports a particular claim — that stays a human judgement.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request

from diagnostics import as_text
from project_store import now

MAX_QUERIES = 6
MAX_RESULTS_PER_PROVIDER = 5
TIMEOUT = 12
MAX_BYTES = 800000

STOP = set('and or the a an of in on for to with de del la los las el un una y o en '
           'para con por desde hasta sobre estudio analisis investigacion trabajo tesis '
           'proyecto efecto impacto desarrollo aplicacion estrategia'.split())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirección bibliográfica bloqueada.')


def _get(url, accept='application/json'):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'NexoTesis/0.4 (academic-assistant; contacto local)',
        'Accept': accept})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=TIMEOUT) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Respuesta demasiado grande.')
    return json.loads(raw.decode('utf-8', 'replace'))


def clean(value):
    return html.unescape(re.sub('<[^>]+>', ' ', str(value or ''))).strip()


def facets(p, limit=MAX_QUERIES):
    """Derive query facets from the project's own words; never invent terms."""
    topic = as_text(p.get('topic', ''), 'topic', 1500)
    words = [w for w in re.findall(r'[\wáéíóúüñ]{4,}', topic.lower())
             if w not in STOP]
    facts = p.get('facts', {}) if isinstance(p.get('facts'), dict) else {}
    for key in ('objetivo_usuario', 'poblacion', 'contexto', 'metodologia'):
        value = facts.get(key, {})
        if isinstance(value, dict):
            words += [w for w in re.findall(r'[\wáéíóúüñ]{4,}', str(value.get('value', '')).lower())
                      if w not in STOP]
    seen, ordered = set(), []
    for word in words:
        if word not in seen:
            seen.add(word)
            ordered.append(word)
    if not ordered:
        return [topic[:120]] if topic else []
    core = ordered[:6]
    out = [' '.join(core)]
    if len(core) >= 4:
        out.append(' '.join(core[:3]))
        out.append(' '.join(core[3:6]))
    if len(core) >= 6:
        out.append(' '.join(core[::2]))
        out.append(' '.join(core[1::2]))
    for question in p.get('questions', [])[:2]:
        if isinstance(question, dict) and question.get('text'):
            text = as_text(question['text'], 'question', 300)
            extra = [w for w in re.findall(r'[\wáéíóúüñ]{4,}', text.lower()) if w not in STOP]
            if extra:
                out.append(' '.join((core[:3] + extra[:3])))
    result = []
    for query in out:
        query = query.strip()[:180]
        if len(query) >= 4 and query not in result:
            result.append(query)
        if len(result) >= limit:
            break
    return result


def _crossref(query):
    url = 'https://api.crossref.org/works?' + urllib.parse.urlencode(
        {'query.bibliographic': query, 'rows': MAX_RESULTS_PER_PROVIDER})
    message = _get(url)['message']
    out = []
    for item in message.get('items', [])[:MAX_RESULTS_PER_PROVIDER]:
        doi = str(item.get('DOI', ''))
        if not doi or item.get('type') == 'peer-review':
            continue
        parts = item.get('issued', {}).get('date-parts', [[]])
        year = str(parts[0][0]) if parts and parts[0] and parts[0][0] else 's. f.'
        authors = '; '.join(' '.join(str(a.get(k, '')) for k in ('given', 'family')).strip()
                            for a in item.get('author', [])[:8]
                            if a.get('given') or a.get('family'))
        out.append({'title': clean((item.get('title') or ['Sin título'])[0])[:300],
                    'authors': authors[:400], 'year': year, 'doi': doi,
                    'url': 'https://doi.org/' + doi,
                    'excerpt': clean(item.get('abstract', ''))[:2000],
                    'status': 'metadatos Crossref' + (' + resumen' if item.get('abstract') else ''),
                    'origin': 'Crossref', 'query': query})
    return out


def _openalex(query):
    url = 'https://api.openalex.org/works?' + urllib.parse.urlencode(
        {'search': query, 'per-page': MAX_RESULTS_PER_PROVIDER})
    message = _get(url)
    out = []
    for item in message.get('results', [])[:MAX_RESULTS_PER_PROVIDER]:
        doi = str(item.get('doi') or '').replace('https://doi.org/', '')
        out.append({'title': clean(item.get('title') or item.get('display_name') or 'Sin título')[:300],
                    'authors': '; '.join(a.get('author', {}).get('display_name', '')
                                         for a in item.get('authorships', [])[:8]),
                    'year': str(item.get('publication_year') or 's. f.'),
                    'doi': doi, 'url': item.get('primary_location', {}).get('landing_page_url', '')
                    or ('https://doi.org/' + doi if doi else ''),
                    'excerpt': '', 'status': 'metadatos OpenAlex',
                    'origin': 'OpenAlex', 'query': query})
    return out


def _semantic_scholar(query):
    url = 'https://api.semanticscholar.org/graph/v1/paper/search?' + urllib.parse.urlencode(
        {'query': query, 'limit': MAX_RESULTS_PER_PROVIDER,
         'fields': 'title,authors,year,externalIds,abstract,url'})
    message = _get(url)
    out = []
    for item in message.get('data', [])[:MAX_RESULTS_PER_PROVIDER]:
        ids = item.get('externalIds') or {}
        doi = str(ids.get('DOI') or '')
        out.append({'title': clean(item.get('title') or 'Sin título')[:300],
                    'authors': '; '.join(a.get('name', '') for a in item.get('authors', [])[:8]),
                    'year': str(item.get('year') or 's. f.'), 'doi': doi,
                    'url': item.get('url') or ('https://doi.org/' + doi if doi else ''),
                    'excerpt': clean(item.get('abstract') or '')[:2000],
                    'status': 'metadatos Semantic Scholar',
                    'origin': 'Semantic Scholar', 'query': query})
    return out


def _arxiv(query):
    url = 'http://export.arxiv.org/api/query?' + urllib.parse.urlencode(
        {'search_query': 'all:' + query, 'start': 0, 'max_results': 3})
    request = urllib.request.Request(url, headers={'User-Agent': 'NexoTesis/0.4'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=TIMEOUT) as response:
        raw = response.read(MAX_BYTES).decode('utf-8', 'replace')
    out = []
    for entry in re.findall(r'<entry>(.*?)</entry>', raw, re.S)[:3]:
        def tag(name):
            match = re.search(r'<' + name + r'[^>]*>(.*?)</' + name + r'>', entry, re.S)
            return clean(match.group(1)) if match else ''
        paper_id = tag('id').rsplit('/', 1)[-1]
        out.append({'title': tag('title')[:300],
                    'authors': ', '.join(re.findall(r'<name>(.*?)</name>', entry, re.S)[:8]),
                    'year': tag('published')[:4] or 's. f.', 'doi': '',
                    'url': tag('id'), 'excerpt': tag('summary')[:2000],
                    'status': 'metadatos arXiv', 'origin': 'arXiv', 'query': query})
        if not out[-1]['doi']:
            out[-1]['doi'] = 'arXiv:' + paper_id
    return out


PROVIDERS = (('Crossref', _crossref), ('OpenAlex', _openalex),
             ('Semantic Scholar', _semantic_scholar), ('arXiv', _arxiv))


def _norm_title(title):
    return re.sub(r'[^a-z0-9]+', ' ', str(title).lower()).strip()[:160]


def dedupe(items):
    """Merge providers per paper; keep provenance. Two providers = verified."""
    merged = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        doi = str(item.get('doi') or '').lower().strip()
        key = 'doi:' + doi if doi else 'title:' + _norm_title(item.get('title'))
        origin = item.get('origin', 'desconocido')
        if key in merged:
            record = merged[key]
            if origin not in record['verified_by']:
                record['verified_by'].append(origin)
            for field in ('authors', 'year', 'url', 'excerpt', 'doi'):
                if not record.get(field) and item.get(field):
                    record[field] = item[field]
            if item.get('excerpt') and len(item['excerpt']) > len(record.get('excerpt', '')):
                record['excerpt'] = item['excerpt']
        else:
            record = dict(item)
            record['verified_by'] = [origin]
            merged[key] = record
    for record in merged.values():
        providers = sorted(set(record['verified_by']))
        record['verified_by'] = providers
        record['verification'] = ('DOI/metadatos coincidentes en ' + ' + '.join(providers)
                                  if len(providers) >= 2 else
                                  'un solo proveedor; procedencia sin confirmar')
        record['supports'] = 'Pendiente de comprobar pertinencia y alcance'
        record['locator'] = 'Resumen depositado por el proveedor' if record.get('excerpt') else ''
        record['retrieved'] = now()
        base = 'metadatos ' + '/'.join(providers)
        record['status'] = base + (' + resumen' if record.get('excerpt') else '') + \
            ('; verificado en 2+ bases' if len(providers) >= 2 else '; verificación pendiente')
    return list(merged.values())


def discover(p, queries=None, max_queries=MAX_QUERIES, providers=None,
             on_event=None, allow_network=True, deadline_s=45):
    """Search every facet in every provider, bounded. Contained failures.

    Returns {'items','attempted','errors','queries','providers','verified'}.
    `allow_network=False` is used by offline self-checks.
    """
    queries = [as_text(q, 'query', 180) for q in (queries or facets(p, max_queries))]
    queries = [q for q in queries if len(q) >= 4][:max_queries]
    chosen = providers or PROVIDERS
    items, errors = [], []
    attempted = 0
    started = time.monotonic()
    for query in queries:
        if time.monotonic() - started >= deadline_s:
            errors.append('Presupuesto de investigación agotado; se devolvió lo encontrado.')
            break
        for name, function in chosen:
            if time.monotonic() - started >= deadline_s:
                break
            attempted += 1
            if on_event:
                on_event('Buscando en ' + name + ': ' + query[:60])
            if not allow_network:
                errors.append(name + ': sin red (autochequeo)')
                continue
            try:
                found = function(query)
                if isinstance(found, list):
                    items.extend(found)
            except Exception as exc:
                errors.append(name + ': ' + type(exc).__name__ + ' ' + str(exc)[:100])
    merged = dedupe(items)
    return {'items': merged, 'attempted': attempted, 'errors': errors,
            'queries': queries, 'providers': [n for n, _ in chosen],
            'verified': sum(1 for x in merged if len(x['verified_by']) >= 2),
            'note': ('Solo metadatos/resúmenes. La coincidencia entre bases NO demuestra '
                     'que el artículo respalde una afirmación concreta.')}


def research_for(p, approve=None, on_event=None, allow_network=True,
                 max_queries=MAX_QUERIES, deadline_s=45, queries=None):
    """Full in-place investigation + commit through the single write path.

    Returns a receipt. `approve(queries)` is the human authorization boundary:
    the user sees the exact queries BEFORE any network request.
    """
    from project_state import commit_slice
    queries = queries if queries is not None else facets(p, max_queries)
    queries = [as_text(q, 'query', 180) for q in queries][:max_queries]
    if not queries:
        return {'ok': False, 'reason': 'No hay tema del que derivar consultas.', 'added': []}
    if approve is not None and approve(queries) is not True:
        return {'ok': False, 'reason': 'Investigación no autorizada.', 'added': [],
                'queries': queries}
    outcome = discover(p, queries, max_queries, on_event=on_event,
                       allow_network=allow_network, deadline_s=deadline_s)
    if not outcome['items']:
        return {'ok': False, 'reason': 'Ninguna base devolvió metadatos.',
                'added': [], 'errors': outcome['errors'][:6], 'queries': queries,
                'attempted': outcome['attempted']}
    before = len(p.get('sources', []))
    receipt = commit_slice(p, 'M2', {'sources': outcome['items'][:60]},
                           'Investigación automática verificable', actor='investigador')
    added = len(p.get('sources', [])) - before
    return {'ok': True, 'added': added, 'attempted': outcome['attempted'],
            'verified': outcome['verified'], 'errors': outcome['errors'][:6],
            'queries': queries, 'providers': outcome['providers'],
            'commit': receipt, 'note': outcome['note']}
