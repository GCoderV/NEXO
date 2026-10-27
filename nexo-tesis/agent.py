"""Bounded academic workflow. The model proposes; the host validates state changes.
Research permission and Word approval are separate, never controlled by model text.
"""
import copy
import json
import re
import threading
import uuid
import unicodedata
from project_store import FACT_KEYS, SECTIONS, LABELS, now, message, set_fact
import bibliography
import context_policy
import conversation_state

from prompt_policy import instructions, incremental_instructions
SYSTEM=instructions()

class Stopped(RuntimeError):pass

def _json_objects(text):
    """Complete {...} candidates, left to right, ignoring braces inside strings.

    Chat-oriented models (notably Copilot365) often wrap the requested JSON in
    prose or in a ```json fence. This only locates an object that was actually
    received: it never invents content and never triggers another model call.
    """
    found=[];start=None;depth=0;quoted=False;escape=False
    for i,ch in enumerate(text):
        if start is None:
            if ch=='{':start=i;depth=1;quoted=False;escape=False
        elif quoted:
            if escape:escape=False
            elif ch=='\\':escape=True
            elif ch=='"':quoted=False
        elif ch=='"':quoted=True
        elif ch=='{':depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:found.append(text[start:i+1]);start=None
    return found

def _without_trailing_commas(text):
    """Remove commas before } or ] only outside JSON strings."""
    out=[];i=0;quoted=False;escape=False
    while i<len(text):
        ch=text[i]
        if quoted:
            out.append(ch)
            if escape:escape=False
            elif ch=='\\':escape=True
            elif ch=='"':quoted=False
            i+=1;continue
        if ch=='"':quoted=True;out.append(ch);i+=1;continue
        if ch==',':
            j=i+1
            while j<len(text) and text[j].isspace():j+=1
            if j<len(text) and text[j] in '}]':i+=1;continue
        out.append(ch);i+=1
    return ''.join(out)

def parse_json(text):
    """Parse one JSON object, also when fenced or surrounded by brief prose."""
    known={'reply','text','drafts','questions','question','search','topic','facts'}
    try:
        value=json.loads(text.strip())
        if isinstance(value,dict):return value
    except (ValueError,TypeError):pass
    for candidate in _json_objects(text)[:128]:  # bounded work on a 45k-char reply
        for attempt in (candidate,_without_trailing_commas(candidate)):
            try:value=json.loads(attempt)
            except (ValueError,TypeError):continue
            if isinstance(value,dict) and set(value)&known:return value
    raise ValueError('No se encontró un objeto JSON completo en la respuesta.')

FORMAT_REASONS={
 'Respuesta del modelo vacía o demasiado larga.':'la respuesta llegó vacía o demasiado larga',
 'No se encontró un objeto JSON completo en la respuesta.':'no se encontró un JSON completo (es posible que el modelo haya respondido en texto libre)',
 'Respuesta de tarea incompatible.':'la respuesta de tarea incluía campos no permitidos',
 'Respuesta estructurada no compatible.':'faltan campos obligatorios o hay campos desconocidos',
 'Falta explicación utilizable.':'falta el campo reply',
 'Propuesta de dato inválida.':'un dato propuesto no es válido',
 'Propuesta de apartado inválida.':'el borrador propuesto no cumple el contrato',
 'Bloque de preguntas inválido.':'el bloque de preguntas no es válido',
 'Pregunta inválida.':'una pregunta no es válida',
 'Tema propuesto inválido.':'el tema propuesto no es válido',
 'Búsqueda inválida.':'la búsqueda propuesta no es válida',
}
def format_reason(error):
    """Fixed, privacy-safe reason: never echoes model output, tokens or URLs."""
    if isinstance(error,(TypeError,KeyError)):return 'la estructura JSON de la respuesta no es compatible'
    return FORMAT_REASONS.get(str(error),'la respuesta no tiene el formato JSON académico esperado')

def unpack(text,task=None):
    if not isinstance(text,str) or len(text)>45000:raise ValueError('Respuesta del modelo vacía o demasiado larga.')
    result=parse_json(text)
    if task and isinstance(result,dict) and ('text' in result or 'drafts' in result):
        # facts/topic are discarded here (an automatic task is never a user statement);
        # accepting their presence avoids a false format error from chatty models.
        allowed={'text','sources','reply','questions','question','search','drafts','facts','topic'}
        if set(result)-allowed:raise ValueError('Respuesta de tarea incompatible.')
        incoming=result.get('drafts',[]);drafts=[]
        if isinstance(incoming,list):
            for d in incoming[:2]:
                if not isinstance(d,dict):continue
                d=dict(d);d.setdefault('section',task['section'])
                if not isinstance(d.get('sources'),list):d['sources']=[]
                drafts.append(d)
        if isinstance(result.get('text'),str):
            sources=result.get('sources',[])
            drafts.append({'section':task['section'],'text':result['text'],'sources':sources if isinstance(sources,list) else []})
        reply=result.get('reply')
        if not isinstance(reply,str) or not 1<=len(reply)<=10000:reply='Borrador preparado.'
        result={'reply':reply,'drafts':drafts[:2],'questions':result.get('questions',[]),'question':result.get('question'),'search':result.get('search')}
    if not isinstance(result,dict) or set(result)-{'reply','facts','drafts','question','questions','search','topic'}:raise ValueError('Respuesta estructurada no compatible.')
    if not isinstance(result.get('reply'),str) or not 1<=len(result['reply'])<=10000:raise ValueError('Falta explicación utilizable.')
    for name,maximum in [('facts',12),('drafts',2)]:
        if not isinstance(result.get(name,[]),list) or len(result.get(name,[]))>maximum:raise ValueError('Demasiadas propuestas en '+name)
    for f in result.get('facts',[]):
        if not isinstance(f,dict) or f.get('key') not in FACT_KEYS or any(not isinstance(f.get(k),str) or not f[k].strip() for k in ('value','evidence')) or len(f['value'])>12000 or len(f['evidence'])>6000:raise ValueError('Propuesta de dato inválida.')
    for d in result.get('drafts',[]):
        if not isinstance(d,dict) or d.get('section') not in SECTIONS or not isinstance(d.get('text'),str) or not 1<=len(d['text'])<=10000 or not isinstance(d.get('sources'),list) or any(not isinstance(x,str) for x in d['sources']):raise ValueError('Propuesta de apartado inválida.')
    questions=result.get('questions',[])
    if not isinstance(questions,list) or len(questions)>len(FACT_KEYS):raise ValueError('Bloque de preguntas inválido.')
    if result.get('question') is not None:questions=questions+[result['question']]
    for q in questions:
        if not isinstance(q,dict) or q.get('key') not in FACT_KEYS or not isinstance(q.get('text'),str) or not 1<=len(q['text'])<=1000 or type(q.get('clarify',False)) is not bool:raise ValueError('Pregunta inválida.')
    title=result.get('topic')
    if title is not None and (not isinstance(title,dict) or not isinstance(title.get('text'),str) or not 1<=len(title['text'])<=1500 or not isinstance(title.get('evidence'),str) or not 1<=len(title['evidence'])<=6000):raise ValueError('Tema propuesto inválido.')
    s=result.get('search')
    if s is not None and (not isinstance(s,dict) or not isinstance(s.get('query'),str) or not 2<=len(s['query'])<=250 or not isinstance(s.get('reason'),str) or len(s['reason'])>1000):raise ValueError('Búsqueda inválida.')
    return result

def context(p,user_text,research_enabled=False,search_notice='',origin='usuario',work_order=None,material=(),allowed_material_ids=None):
    from context_policy import build_context
    return build_context(p,user_text,research_enabled,search_notice,origin,work_order,material,allowed_material_ids)

def apply_proposal(p,r,user_text,message_id,origin='usuario',material_ids=()):
    warnings=[]
    title=r.get('topic')
    if title and p.get('topic_pending') and origin=='usuario':
        if title['evidence'] in user_text and title['text'] in title['evidence']:
            p['topic']=title['text'];p['topic_pending']=False
        else:warnings.append('No se cambió el tema: falta una cita literal del texto aportado.')
    for f in r.get('facts',[]):
        if origin!='usuario':
            warnings.append('No se incorporaron decisiones desde contenido documental o un paso automático; requieren información del usuario.');continue
        from_message=f['evidence'] in user_text
        if not from_message and f['evidence'] not in p['topic']:
            warnings.append('No se guardó '+f['key']+': no contiene evidencia literal del mensaje ni del tema.');continue
        set_fact(p,f['key'],f['value'],f['evidence'],'extraído del mensaje; revisar interpretación' if from_message else 'extraído del tema; revisar interpretación',message_id if from_message else None)
        if material_ids:p['facts'][f['key']]['material_ids']=sorted(material_ids)
    ids={s['id'] for s in p['sources']}|set(material_ids)
    for d in r.get('drafts',[]):
        section=d['section']
        if not set(p['drafts'].get(section,{}).get('material_ids',[]))<=set(material_ids):
            warnings.append('No se sustituyó '+LABELS[section]+': el texto previo depende de archivos que esta petición no recibió con permiso.');continue
        used=set(d['sources'])|set(re.findall(r'\[([FD]\d+)\]',d['text']))
        if not used<=ids:
            warnings.append('No se guardó '+LABELS[section]+': cita identificadores de fuentes inexistentes.');continue
        if section in ('resultados','discusion','conclusiones') and (not p.get('data_ready') or 'datos' not in p['facts']):
            warnings.append('No se guardó '+LABELS[section]+': faltan datos/corpus aportados y su confirmación en Memoria. Se puede preparar el análisis previsto.');continue
        text=d['text']
        if section=='referencias':
            text='\n\n'.join(f"[{s['id']}] {s.get('authors','')} ({(s.get('year') if str(s.get('year','')).lower() not in ('none','null','') else 's.f.')}). {s['title']}. {s.get('url','')} — {s['status']}" for s in p['sources']) or 'Sin fuentes registradas.'
        old=p['drafts'].get(section);versions=(old.get('versions',[])+[{'text':old['text'],'status':old['status'],'time':now()}])[-5:] if old else []
        p['drafts'][section]={'text':text,'sources':sorted(used),'status':'borrador','warning':'Propuesta del modelo: revisar evidencia, coherencia y citas antes de aprobar.','time':now(),'versions':versions,'material_ids':sorted(material_ids)}
    proposed=list(r.get('questions',[]))
    if r.get('question'):proposed.append(r['question']) # legacy replies still accepted
    accepted=[];seen=set()
    for q in proposed:
        if q['key'] in seen:continue
        seen.add(q['key'])
        duplicate=any(x['key']==q['key'] and x['status'] in ('respondida','aplazada') for x in p['questions']) or q['key'] in p['facts'] or (q['key']=='guia' and any(m.get('role')=='guia' and m.get('active') for m in p.get('materials',[])))
        if duplicate and not q.get('clarify'):
            warnings.append('Se omitió una pregunta sobre información ya respondida o aplazada.');continue
        if any(x['key']==q['key'] and x['status']=='abierta' and (not q.get('clarify') or x['text']==q['text']) for x in p['questions']):
            warnings.append('La pregunta ya está pendiente; no se duplicó.');continue
        p['questions'].append({'id':uuid.uuid4().hex,'key':q['key'],'text':q['text'],'status':'abierta','clarify':q.get('clarify',False),'time':now(),'material_ids':sorted(material_ids)});accepted.append(q)
    answer=r['reply']
    if len(accepted)==1:answer+='\n\n'+accepted[0]['text']
    elif accepted:answer+='\n\nSolo falta precisar lo siguiente; puedes responder todo en un único texto:\n'+'\n'.join(str(i)+'. '+q['text'] for i,q in enumerate(accepted,1))
    if warnings:answer+='\n\nComprobaciones de Nexo:\n'+'\n'.join('• '+w for w in warnings)
    message(p,'assistant',answer)
    if material_ids:p['messages'][-1]['material_ids']=sorted(material_ids)
    return warnings

class Agent:
    def __init__(self,store,api,approve_search=None,searcher=None,stop=None,emit=None):
        self.store=store;self.api=api;self.approve_search=approve_search;self.searcher=searcher or bibliography.search;self.stop=stop or threading.Event();self.emit=emit or (lambda text:None)
    def check(self):
        if self.stop.is_set():raise Stopped('Detenido. No se iniciarán más solicitudes; lo ya guardado permanece.')
    def turn(self,project_id,user_text='',allow_research=False,origin='usuario',resume=False,refresh_context=False,task=None):
        p=self.store.load(project_id);self.store.recover(p)
        decision=conversation_state.pending(p,self.api)
        if decision:raise conversation_state.ContinuityPending(decision['message'])
        secret=getattr(self.api,'key','')
        redact=getattr(self.api,'redact',lambda text:str(text).replace(secret,'[CLAVE OMITIDA]') if secret else str(text))
        if resume:
            op=p.get('pending')
            if not op:raise ValueError('No hay una petición pendiente en este proyecto.')
            op['force_full']=True  # a reanudación nunca asume recuerdo remoto
            if op.get('revision')!=p['revision']:
                if not refresh_context:raise ValueError('El proyecto cambió; confirma el contexto actualizado antes de reanudar.')
                # Conservar los identificadores: el contexto cambió, el chat no.
                op.pop('search_approved',None);op.pop('query',None)
                if op.get('task'):
                    from autonomy import order
                    op['task']=order(p,op['task']);op.pop('task_progress',None)
                op.update(stage='model',iteration=1 if op.get('searched') else 0,notice='El usuario autorizó continuar con el contexto actual; conservar las fases guardadas. No repetir búsquedas completadas.')
            user_text=op['text'];origin=op['origin'];allow_research=op['research']
        else:
            if not isinstance(user_text,str) or not 1<=len(user_text.strip())<=12000:raise ValueError('Mensaje de 1 a 12000 caracteres requerido.')
            if origin not in ('usuario','seleccion_word','autonomo'):raise ValueError('Procedencia de mensaje inválida.')
            user_text=redact(user_text)
            if p.get('pending'):message(p,'system','La petición pendiente anterior fue sustituida por una nueva solicitud explícita; su mensaje permanece en el historial.')
            mid=message(p,'system' if origin=='autonomo' else 'user',user_text);p['messages'][-1]['origin']=origin
            op={'id':uuid.uuid4().hex,'text':user_text,'origin':origin,'mid':mid,'stage':'model','iteration':0,'searched':False,'notice':'','research':allow_research,'remote':{},'inflight':False,'uncertain':False}
            if task:
                from autonomy import order
                op['task']=order(p,task)
            from conversation_state import load
            op['remote']=load(p,self.api)
            p['pending']=op
        def checkpoint(event):
            if 'pending' in p:p['pending']=op
            op['revision']=p['revision']+1;self.store.save(p,event)
            if 'pending' in p:p['pending']=op
        if getattr(self.api,'neutral',False):
            self.api.stop=self.stop;self.api.emit=self.emit;self.api.remote=op.setdefault('remote',{});self.api.project_id=project_id
        # Sembrar el interruptor A/B también en el PRIMER turno, cuando todavía no
        # existe ningún hilo guardado del que conversation_state.load pueda leerlo.
        affinity=bool(p.get('copilot_affinity',True))
        for aid in conversation_state.keys(self.api):
            op['remote'].setdefault(aid,{}).setdefault('affinity',affinity)
        p['run']={'status':'en_curso','started':now()};checkpoint('turn-resumed' if resume else 'turn-started')
        try:
            while True:
                self.check()
                if op['stage']=='search':
                    query=op['query']
                    if not op.get('search_approved'):
                        if not allow_research or self.approve_search is None or self.approve_search(query['query'],query['reason']) is not True:
                            message(p,'system','Búsqueda no autorizada. No se enviaron datos a Crossref.');break
                        op['search_approved']=True;checkpoint('search-approved')
                    self.check();p['run']['status']='busqueda';op['inflight']=True;checkpoint('search-intent');self.emit('Consultando metadatos bibliográficos…')
                    try:
                        items=self.searcher(query['query']);added=bibliography.add_sources(p,items)
                        op['notice']='Búsqueda completada. IDs nuevos: '+', '.join(added)+'. Solo material indicado en el estado de cada fuente; no lectura completa.'
                    except Exception as e:op['notice']='La búsqueda falló; no hay nuevos resultados: '+redact(e)[:400]
                    message(p,'system',op['notice']);op.update(searched=True,stage='model',iteration=1,inflight=False);checkpoint('search-result')
                    self.check();continue
                p['run']['status']='modelo';op['inflight']=True;op['uncertain']=False;checkpoint('model-intent');self.emit('Desarrollando '+LABELS[op['task']['section']]+'…' if op.get('task') else 'Preparando el siguiente paso…')
                from materials import select,scopes
                material=select(self.store.root,p,user_text+' '+p['topic']+' '+op.get('task',{}).get('label',''),scopes(self.api))
                allowed={m['ref'] for m in p.get('materials',[]) if scopes(self.api) and set(scopes(self.api))<=set(m.get('shared_routes',[]))}
                # Siempre se construye el contexto completo: aplica permisos y límites
                # incluso cuando solo se enviarán los cambios a un hilo verificado.
                full=context(p,user_text,allow_research and not op['searched'],op['notice'],origin,op.get('task'),material,allowed)
                text=full
                if not op.get('force_full') and conversation_state.can_increment(p,self.api):
                    delta=context_policy.incremental(full,p.get('copilot_ledger'))
                    if delta:text=delta
                incremental=text is not full
                self.api.instructions=incremental_instructions(op.get('task')) if incremental else instructions(op.get('task'))
                received_ids={m['id'] for m in material}|set(json.loads(full).get('inherited_material_ids',[]))
                p['last_context']={'characters':len(text),'full_characters':len(full),'mode':'incremental' if incremental else 'completo','instructions_characters':len(self.api.instructions),'material_fragments':len(material),'material_ids':sorted({m['id'] for m in material})}
                payload=[{'role':'user','parts':[{'text':text}]}] if self.api.provider=='Gemini' and not getattr(self.api,'neutral',False) else [{'role':'user','content':text}]
                response_message,raw,calls=self.api.request(payload,[])
                if conversation_state.keys(self.api):context_policy.record_ledger(p,full,incremental)
                if isinstance(response_message,dict) and isinstance(response_message.get('metadata'),dict):p['provider_references']=response_message['metadata'].get('citations',[])[:30]
                from conversation_state import save
                save(p,self.api,op['remote'])
                p['usage']['calls']+=1
                for k in ('input_tokens','output_tokens'):p['usage'][k]+=getattr(self.api,'last_usage',{}).get(k,0)
                if hasattr(self.api,'trace'):p['last_transport']={'attempts':self.api.attempts,'route':self.api.route_identity,'trace':self.api.trace[-30:]}
                self.check()
                if calls:raise ValueError('El modelo intentó herramientas no disponibles. No se ejecutaron.')
                raw=redact(raw)
                try:r=unpack(raw,op.get('task'))
                except (ValueError,TypeError,KeyError) as e:
                    op['inflight']=False;p['run']={'status':'error_formato'}
                    message(p,'system','La respuesta no cumple el formato académico ('+format_reason(e)+'). No se aplicó. Puedes elegir otro modelo y pulsar Reanudar.')
                    checkpoint('format-pending');return p
                # Apply only a complete validated response while this operation is active.
                before_drafts=dict(p['drafts'])
                target=op.get('task',{}).get('section')
                if target:
                    from autonomy import clean,protected,fingerprint
                    old=p['drafts'].get(target)
                    selected=[]
                    for d in r.get('drafts',[]):
                        if d['section']!=target or (old and protected(old)):continue
                        if old and (clean(d['text'])==clean(old['text']) or (len(old['text'])>800 and len(d['text'])<len(old['text'])*.65)):continue
                        selected.append(d)
                    r['drafts']=selected[:1]
                apply_proposal(p,r,user_text,op['mid'],origin,received_ids);op['inflight']=False
                producer={'provider':self.api.provider,'model':getattr(self.api,'model','no reportado'),'route':getattr(self.api,'route_identity',''),'operation_id':op['id']}
                for draft in r.get('drafts',[]):
                    if draft['section'] in p['drafts'] and p['drafts'][draft['section']] is not before_drafts.get(draft['section']):p['drafts'][draft['section']]['producer']=producer
                if p['messages'] and p['messages'][-1]['role']=='assistant':p['messages'][-1]['producer']=producer
                if target:
                    new=p['drafts'].get(target);old=before_drafts.get(target)
                    progress=bool(new and (not old or clean(new['text'])!=clean(old['text'])))
                    if progress:new['auto_reviewed_for']=fingerprint(p,new['text']);op['task_progress']=True
                    progress=bool(op.get('task_progress'))
                    p['last_step']={'operation':op['id'],'section':target,'progress':progress,'reason':'Texto nuevo guardado en Apartados.' if progress else 'Sin avance verificable: el modelo no entregó un borrador nuevo utilizable para '+LABELS[target]+'. No se cambió ese apartado; revisa preguntas, datos y avisos.'}
                    message(p,'system',('Guardado en Apartados: '+LABELS[target]+'. No se modificó Word.') if progress else p['last_step']['reason'])
                query=r.get('search')
                if query and not op['searched'] and op['iteration']==0 and allow_research:
                    op.update(stage='search',query=query);checkpoint('proposal-staged');self.check();continue
                if target and not progress and not query and op['iteration']==0:
                    op.update(iteration=1,notice='El paso anterior no produjo un cambio verificable. Esta es la única corrección permitida: entrega en drafts el apartado work_order.section, con texto completo y útil; no repitas promesas. Si no es posible, explica qué información concreta lo bloquea.')
                    checkpoint('no-progress-correction');self.check();continue
                if query:
                    message(p,'system','Búsqueda propuesta pendiente: activa Permitir búsqueda para otra solicitud.' if not allow_research else 'Se alcanzó el límite de una búsqueda y dos fases de modelo por turno.')
                break
            p.pop('pending',None)
            p['run']={'status':'sin_avance' if op.get('task') and not p.get('last_step',{}).get('progress') else 'esperando_respuesta' if any(q['status']=='abierta' for q in p['questions']) else 'listo'}
        except Stopped as e:
            p['run']={'status':'detenido'};op['uncertain']=bool(op.get('inflight'));op['inflight']=False;message(p,'system',str(e)+' La petición puede reanudarse.')
        except Exception as e:
            p['run']={'status':'error'};op['uncertain']=getattr(e,'kind','')=='uncertain' or bool(op.get('inflight') and not hasattr(e,'kind'));op['inflight']=False
            message(p,'system','Paso pendiente: '+redact(e)[:1500]+' Puedes configurar otra ruta y pulsar Reanudar; no hace falta escribir de nuevo.')
        # Persistir SIEMPRE el estado del hilo. Un error sin confirmación conserva
        # los identificadores y marca la decisión pendiente; nunca los descarta.
        from conversation_state import save
        # Each account slot carries its own confirmation flag: a failed attempt on
        # one route must not mark a later successful route as uncertain.
        save(p,self.api,op['remote'],uncertain=bool(op.get('uncertain')))
        if hasattr(self.api,'trace'):
            p['last_transport']={'attempts':self.api.attempts,'route':self.api.route_identity,'trace':self.api.trace[-30:]}
        checkpoint('turn-finished');return p
