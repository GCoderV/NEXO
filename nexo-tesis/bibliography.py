"""Bounded public metadata search, not full-text evidence or universal coverage."""
import html
import json
import re
import urllib.parse
import urllib.request
from project_store import now, invalidate

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Redirección bibliográfica bloqueada.')

def clean(value):return html.unescape(re.sub('<[^>]+>',' ',str(value or ''))).strip()

def search(query,rows=5):
    if not isinstance(query,str) or not 2<=len(query.strip())<=250:raise ValueError('Consulta bibliográfica de 2 a 250 caracteres.')
    if type(rows) is not int or not 1<=rows<=5:raise ValueError('Máximo cinco resultados por consulta.')
    url='https://api.crossref.org/works?'+urllib.parse.urlencode({'query.bibliographic':query,'rows':rows})
    req=urllib.request.Request(url,headers={'User-Agent':'NexoTesis/0.1 (academic-assistant)','Accept':'application/json'})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=20) as response:raw=response.read(1_000_001)
    if len(raw)>1_000_000:raise ValueError('Respuesta bibliográfica demasiado grande.')
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get('message'),dict):raise ValueError('Respuesta de Crossref no reconocida.')
    items=data['message'].get('items',[])
    if not isinstance(items,list):items=[]
    results=[]
    for item in items[:rows]:
        if not isinstance(item,dict):continue
        doi=str(item.get('DOI',''))
        if not doi or len(doi)>250:continue
        authors='; '.join(' '.join(str(a.get(k,'')) for k in ('given','family')).strip() or str(a.get('name','')) for a in item.get('author',[])[:10] if a.get('given') or a.get('family') or a.get('name'))
        parts=item.get('issued',{}).get('date-parts',[[]]);year=str(parts[0][0]) if parts and parts[0] and parts[0][0] else 's. f.'
        if item.get('type')=='peer-review' or clean((item.get('title') or [''])[0]).lower().startswith('review for '):continue
        abstract=clean(item.get('abstract',''))
        results.append({'title':clean((item.get('title') or ['Sin título'])[0])[:2000],'authors':authors[:2000],'year':year,'doi':doi,'url':'https://doi.org/'+urllib.parse.quote(doi,safe='/'),
                        'status':'resumen de metadatos consultado' if abstract else 'solo metadatos consultados','excerpt':abstract[:6000], 'excerpt_truncated':len(abstract)>6000,
                        'locator':'Resumen depositado en Crossref' if abstract else '', 'supports':'Pendiente de comprobar pertinencia y alcance','origin':'Crossref','retrieved':now(),'query':query})
    return results

def _number(value):
    m=re.fullmatch(r'F(\d{1,9})',str(value or ''))
    return int(m.group(1)) if m else 0

def _next_source_id(p):
    """Monotonic F# ids. Old code did max(existing)+1: deleting the last source
    reused its id, silently repointing citations already written in drafts, and
    any non-numeric id crashed the whole search with ValueError."""
    sources=p.get('sources',[])
    highest=max([_number(s.get('id','')) for s in sources if isinstance(s,dict)]+[0])
    stored=p.get('source_seq',0)
    stored=stored if type(stored) is int and 0<=stored<=10**9 else 0
    value=max(stored,highest)+1
    p['source_seq']=value
    return 'F'+str(value)

def add_sources(p,items):
    added=[]
    for item in items:
        if not isinstance(item,dict):continue
        doi=str(item.get('doi','') or '')
        if doi and any(str(s.get('doi','') or '').lower()==doi.lower() for s in p['sources'] if isinstance(s,dict)):continue
        if len(p['sources'])>=150:raise ValueError('Límite de 150 fuentes por proyecto en esta versión.')
        s=dict(item);s['id']=_next_source_id(p)
        p['sources'].append(s);added.append(s['id'])
    return added

def add_fragment(p,title,text,locator,url='',supports=''):
    if not title.strip() or not text.strip() or not locator.strip():raise ValueError('Indica título, fragmento y localizador.')
    if len(text)>12000 or len(title)>2000 or len(locator)>1000 or len(url)>2000 or len(supports)>3000:raise ValueError('Fragmento o metadatos demasiado largos.')
    return add_sources(p,[dict(title=title,authors='Por completar',year='Por completar',url=url,doi='',status='fragmento aportado; procedencia no verificada',excerpt=text,locator=locator,supports=supports,origin='usuario',retrieved=now())])
