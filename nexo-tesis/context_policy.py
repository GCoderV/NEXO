"""Task-selected context with explicit extraction limits, no full history dump."""
import copy,hashlib,json,re,unicodedata
from datetime import datetime,timezone
from project_store import FACT_KEYS,SECTIONS,LABELS

def normalized(s):return ''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')
def terms(s):return set(re.findall(r'[a-z]{4,}',normalized(s)))-{'para','como','este','esta','continua','proyecto','investigacion','desarrollar','sobre','bibliografica','consulta','propone'}
def build_context(p,user_text,research_enabled=False,search_notice='',origin='usuario',work_order=None,material=(),allowed_material_ids=None):
    allowed=set(allowed_material_ids if allowed_material_ids is not None else (m['id'] for m in material))
    def permitted(record):return set(record.get('material_ids',[]))<=allowed
    if any(not permitted(v) for v in p['facts'].values()):raise ValueError('Hay datos derivados de archivos sin permiso para esta ruta. Autoriza sus extractos en Archivos o revisa esos datos en Memoria antes de enviar.')
    if work_order and not permitted(p['drafts'].get(work_order['section'],{})):raise ValueError('El borrador a revisar deriva de archivos sin permiso para esta ruta. Autoriza sus extractos antes de continuar; no se envió el texto.')
    p=copy.deepcopy(p)
    p['drafts']={k:d for k,d in p['drafts'].items() if permitted(d)}
    p['messages']=[m for m in p['messages'] if permitted(m)]
    p['questions']=[q for q in p['questions'] if permitted(q)]
    query=terms(user_text+' '+p['topic']+' '+' '.join(p['facts'].get(k,{}).get('value','') for k in ('objetivo_usuario','metodologia')))
    explicit=set(re.findall(r'\bF\d+\b',user_text+' '+search_notice));ranked=[]
    for src in p['sources']:
        score=len(query & terms(src['title']+' '+src.get('excerpt','')))
        ranked.append((src['id'] in explicit,score,src))
    ranked.sort(key=lambda t:(t[0],t[1]),reverse=True)
    sources=[]
    for _,_,s in ranked[:4]:
        sources.append({k:s.get(k,'') for k in ('id','title','authors','year','status','url')}|{'excerpt':s.get('excerpt','')[:1800],'excerpt_truncated':len(s.get('excerpt',''))>1800})
    drafts={}
    for k,d in p['drafts'].items():
        if (normalized(LABELS[k]) in normalized(user_text) or k=={'objetivos':'pregunta','pregunta':'problematica','metodologia':'objetivos'}.get((work_order or {}).get('section'))) and k!=(work_order or {}).get('section'):
            drafts[k]={'status':d['status'],'text':d['text'],'scope':'texto completo'}
    data={'topic':p['topic'],'topic_pending':p.get('topic_pending',False),'facts':{k:{'value':v['value']} for k,v in p['facts'].items()},'draft_index':{k:d['status'] for k,d in p['drafts'].items()},'recent_drafts':drafts,'questions':[{'key':q['key'],'text':q['text']} for q in p['questions'] if q['status']=='abierta'][-8:],'answered_or_deferred':sorted({q['key'] for q in p['questions'] if q['status'] in ('respondida','aplazada')}),'sources':sources,'available_source_ids':[s['id'] for s in sources],'data_ready':p.get('data_ready',False),'research_enabled':research_enabled,'current_user_message':user_text,'current_message_origin':origin,'allowed_fact_keys':FACT_KEYS,'allowed_sections':SECTIONS}
    if p.get('materials'):data['file_state']={'guide_attached':any(m['role']=='guia' and m.get('active') for m in p['materials']),'retired_refs':[m['ref'] for m in p['materials'] if not m.get('active')],'notice':'Las referencias retiradas no representan requisitos actuales. Solo has recibido document_extracts, no los archivos originales. No pidas adjuntar otra vez una guía existente; si falta lectura o permiso, explica esa diferencia.'}
    if work_order:data['work_order']=work_order
    if search_notice:data['research_result']=search_notice
    if material:data['document_extracts']=list(material)
    # Small conversational continuity for providers without a durable remote thread.
    data['recent_messages']=[{'role':m['role'],'text':m['text'][:500]} for m in p['messages'][-3:] if m['text']!=user_text and m['role']!='system']
    inherited=set()
    records=list(p['facts'].values())+[d for k,d in p['drafts'].items() if k in drafts or k==(work_order or {}).get('section')]+[q for q in p['questions'] if q['status']=='abierta'][-8:]+p['messages'][-3:]
    for record in records:inherited.update(record.get('material_ids',[]))
    if inherited:data['inherited_material_ids']=sorted(inherited)
    def encoded():
        data['available_source_ids']=[s['id'] for s in data['sources']]
        return json.dumps(data,ensure_ascii=False,separators=(',',':'))
    if len(encoded())>24000:data['recent_messages']=[];data['sources']=sources[:2]
    if len(encoded())>24000:data['recent_drafts']={};data['context_note']='Otros borradores omitidos por límite. El texto completo de la tarea se conserva.'
    if len(encoded())>24000:raise ValueError('El contexto esencial supera 24000 caracteres; divide la tarea o el material. No se recortó el texto a revisar.')
    return encoded()

# --- Incremental context on a VERIFIED thread ---------------------------------
# Only hashes of the last full context are kept locally: enough to compute a delta
# and to rebuild everything if continuity is lost, without duplicating user text.
TRACKED=('topic','topic_pending','facts','draft_index','recent_drafts','questions',
         'answered_or_deferred','sources','available_source_ids','data_ready','allowed_fact_keys',
         'allowed_sections','file_state','work_order','research_result','document_extracts',
         'inherited_material_ids','context_note')

def _fingerprint(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

def snapshot(full_context):
    data=json.loads(full_context)
    return {k:_fingerprint(data[k]) for k in TRACKED if k in data}

def incremental(full_context,ledger):
    """Compact delta for a verified chat. Returns None when a full context is required.

    The FULL context is always built first, so permission checks and size limits still
    run. Only unchanged sections are omitted; the delta is never larger than the full
    context and never exceeds the same 24000-character limit.
    """
    if not isinstance(ledger,dict) or not isinstance(ledger.get('snapshot'),dict):return None
    data=json.loads(full_context);previous=ledger['snapshot']
    changes={k:data[k] for k in TRACKED if k in data and _fingerprint(data[k])!=previous.get(k)}
    removed=[k for k in TRACKED if k in previous and k not in data]
    out={'continuity':'incremental','note':'Mismo chat: solo se envían los cambios desde el último turno.',
         'current_user_message':data.get('current_user_message',''),
         'current_message_origin':data.get('current_message_origin','usuario'),
         'research_enabled':data.get('research_enabled',False),
         'allowed_fact_keys':data.get('allowed_fact_keys',[]),
         'allowed_sections':data.get('allowed_sections',[]),
         'task_section':(data.get('work_order') or {}).get('section'),
         'changes':changes,'removed':removed}
    raw=json.dumps(out,ensure_ascii=False,separators=(',',':'))
    if len(raw)>24000 or len(raw)>=len(full_context):return None
    return raw

def record_ledger(p,full_context,incremental_sent=False):
    """Local recovery summary. No user text, tokens, URLs or headers are stored."""
    data=json.loads(full_context);old=p.get('copilot_ledger') or {}
    p['copilot_ledger']={
        'snapshot':snapshot(full_context),
        'mode':'incremental' if incremental_sent else 'completo',
        'turns':(old.get('turns',0)+1) if isinstance(old,dict) else 1,
        'summary':{'facts':len(data.get('facts',{})),'drafts':len(data.get('draft_index',{})),
                   'sources':len(data.get('sources',[])),'extracts':len(data.get('document_extracts',[]))},
        'updated':datetime.now(timezone.utc).isoformat(timespec='seconds')}
    return p['copilot_ledger']
