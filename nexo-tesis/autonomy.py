"""Local bounded scheduler: academic drafts only, never Word or implicit recipients."""
from diagnostics import as_key, as_text
import hashlib,json,re,time,uuid,unicodedata
from project_store import SECTIONS,LABELS,message,now

def clean(text):return re.sub(r'\s+',' ',text).strip()
def fingerprint(p,text):
    inputs={'topic':p['topic'],'facts':{k:v['value'] for k,v in p['facts'].items() if k!='guia'},'sources':p['sources'],'materials':[(m['sha256'],m.get('active'),m.get('shared_routes',[])) for m in p.get('materials',[]) if m['role']!='guia'],'data_ready':p.get('data_ready'), 'text':clean(text)}
    return hashlib.sha256(json.dumps(inputs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def protected(d):
    return not d.get('producer') or d.get('status') in ('aprobado_usuario','insertado_pendiente_revision_word') or d.get('previous_status') in ('aprobado_usuario','insertado_pendiente_revision_word') or d.get('edited_by_user') or d.get('warning','').startswith('Edición manual:')
PROVISIONAL=('cronograma','presupuesto','anexos')
PROVISIONAL_INSTRUCTION={
 'cronograma':'Entrega una ESTRUCTURA de cronograma con las fases del estudio y columnas de periodo, responsable y evidencia. Marca como «Por definir» toda fecha, duración, horario y número de ciclos que no conste en facts. No inventes fechas ni plazos.',
 'presupuesto':'Entrega una ESTRUCTURA de presupuesto con categorías de recursos y columnas de cantidad, costo y fuente. Marca como «Por definir» todo importe que no conste en facts. No inventes precios, montos, proveedores ni financiación.',
 'anexos':'Entrega un ÍNDICE de anexos previstos (instrumentos, consentimientos, guías, evidencias) indicando cuáles existen y cuáles están pendientes. No inventes documentos, fechas ni resultados que no consten en el proyecto.',
}
SECTION_INSTRUCTION={
 # "Antecedentes" is not a separate section in this data model; it belongs here.
 'marco_teorico':'Incluye un apartado «Antecedentes» con los estudios previos que figuren en FUENTES, citados como [F#]. Si no hay fuentes suficientes, escribe «Antecedentes pendientes de búsqueda bibliográfica» y propón términos concretos; nunca inventes autores, años, títulos ni DOI. Conserva lo válido de previous_text.',
 'referencias':'Entrega una propuesta de lista de referencias SOLO con las fuentes presentes en FUENTES, en formato APA 7 y con [F#]. Nexo reconstruira la lista definitiva desde el registro de fuentes para impedir citas inventadas. No anadas obras que no esten en FUENTES.',
 'instrumentos':'Describe los instrumentos como PROPUESTA derivada de la metodología. No afirmes que ya están validados, aplicados ni pilotados salvo que conste en facts. Marca «Por definir» lo que requiera datos del usuario.',
}
DEFAULT_INSTRUCTION='Entrega texto concreto y coherente con los datos del proyecto; conserva lo válido. Señala lo provisional y la evidencia pendiente.'

def plan(p,include_optional=False):
    if p.get('topic_pending'):return [],'Primero aporta un tema explícito; no se inventará.'
    typ=' '.join(p['facts'].get(k,{}).get('value','') for k in ('tipo_trabajo','metodologia'))
    typ=''.join(c for c in unicodedata.normalize('NFD',typ.lower()) if unicodedata.category(c)!='Mn')
    documentary=any(x in typ for x in ('documental','revision bibliografica','revision sistematica','revision de literatura'))
    proposal=any(x in typ for x in ('anteproyecto','protocolo','propuesta de investigacion'))
    action='accion' in typ or 'intervencion' in typ
    eligible=[];blocked=[];required=set()
    if p.get('format_profile'):
        from guide_rules import effective
        required={r['value'] for r in effective(p).get('rules',[]) if r['key']=='include_section'}
    # A methodology DRAFT is enough to schedule instruments: previously only a
    # metodologia FACT unblocked it, which left the project in a dead end.
    has_method=bool(p['facts'].get('metodologia') or p['drafts'].get('metodologia'))
    sources=p.get('sources',[])
    protected_count=0
    for k in SECTIONS:
        if k in PROVISIONAL and k not in required and not include_optional:continue
        if proposal and k in ('resultados','discusion','conclusiones'):continue
        if k in ('resultados','discusion','conclusiones') and not (p.get('data_ready') and p['facts'].get('datos')):
            blocked.append(LABELS[k]+': necesita datos/corpus aportados y confirmados en Memoria');continue
        if k=='referencias' and not sources:continue
        if k=='plan_accion' and not action:continue
        if k=='instrumentos' and (documentary or not has_method):continue
        d=p['drafts'].get(k)
        if d and protected(d):protected_count+=1;continue
        mode='crear' if not d else 'revisar'
        if d and d.get('status')!='necesita_revision' and d.get('auto_reviewed_for')==fingerprint(p,d['text']):continue
        eligible.append({'section':k,'mode':mode,'label':LABELS[k]})
    # Missing/outdated first, then one review per input fingerprint, never endless polishing.
    eligible.sort(key=lambda t:(0 if t['section'] not in p['drafts'] or p['drafts'][t['section']]['status']=='necesita_revision' else 1,SECTIONS.index(t['section'])))
    lines=[]
    if eligible:lines.append('Se pueden producir borradores provisionales; lo no aportado debe quedar pendiente.')
    else:lines.append('No quedan tareas automáticas elegibles con los datos actuales. Esto NO significa que el trabajo esté terminado:')
    if sources:
        lines.append('• Fuentes registradas: '+str(len(sources))+'. Ya se puede generar Referencias y revisar apartados citando [F#].')
    else:
        lines.append('• FALTAN FUENTES: pulsa «Buscar fuentes» e indica términos, activa «Permitir búsqueda» y escribe «busca fuentes sobre …», o añade fuentes a mano en la pestaña Fuentes. Sin fuentes no se generan Referencias ni Antecedentes verificables.')
    if not (p.get('data_ready') and p['facts'].get('datos')):
        lines.append('• Resultados/Discusión/Conclusiones bloqueados: se requieren datos o corpus aportados y confirmados en Memoria. No se inventarán resultados empíricos.')
    if not has_method and not documentary:
        lines.append('• Instrumentos bloqueado: falta la metodología (dato en Memoria o borrador de Metodología).')
    if protected_count:
        lines.append('• '+str(protected_count)+' apartado(s) protegido(s) (aprobado, editado por ti o insertado en Word): no se reescriben automáticamente; revísalos manualmente.')
    if not include_optional and not (required & set(PROVISIONAL)):
        missing=[LABELS[k] for k in PROVISIONAL if k not in p['drafts']]
        if missing:lines.append('• Apartados opcionales pendientes: '+', '.join(missing)+'. Activa «Incluir apartados opcionales» para crear plantillas con campos «Por definir», sin inventar fechas ni importes.')
    if blocked:lines.append('• Pendientes: '+'; '.join(blocked)+'.')
    if any(m.get('active') and not m.get('shared_routes') for m in p.get('materials',[])):
        lines.append('• Hay archivos solo locales; no se usarán sus extractos sin permiso en Archivos.')
    return eligible,'\n'.join(lines)

def order(p,task):
    k=task['section'];d=p['drafts'].get(k)
    if k not in SECTIONS or (d and protected(d)):raise ValueError('El apartado está protegido o no es válido.')
    instruction=PROVISIONAL_INSTRUCTION.get(k) or SECTION_INSTRUCTION.get(k) or DEFAULT_INSTRUCTION
    return {**task,'previous_text':d['text'] if d else '', 'instruction':instruction,
            'provisional':bool(k in PROVISIONAL and not d)}

def route_scope(api):
    if not hasattr(api,'routes'):return {(api.provider,api.model,getattr(api,'endpoint',''))}
    accounts=api.config.data.get('accounts',{}) if isinstance(api.config.data,dict) else {}
    if not isinstance(accounts,dict):accounts={}
    out=set()
    for r in api.routes:
        if not isinstance(r,dict):continue
        aid=as_key(r.get('account_id'),'route.account_id')
        record=accounts.get(aid,{})
        generation=as_text(record.get('generation',''),'generation') if isinstance(record,dict) else ''
        out.add(tuple(as_text(r.get(k,''),'route.'+k) for k in ('provider','model','endpoint'))+(aid,generation))
    return out

def save_session(store,p,status,reason):
    p['autonomy'].update(status=status,reason=reason,updated=now())
    op=p.get('pending')
    if op and op.get('revision')==p['revision']:op['revision']=p['revision']+1
    store.save(p,'autonomy-'+status)

class AutonomousRunner:
    def __init__(self,store,api_factory,stop,emit=None,approve_search=None,searcher=None,clock=time.monotonic,on_progress=None):
        self.store=store;self.api_factory=api_factory;self.stop=stop;self.emit=emit or (lambda s:None);self.approve_search=approve_search;self.searcher=searcher;self.clock=clock;self.on_progress=on_progress or (lambda p:None)
    def run(self,project_id,limit=6,research=False,authorized_scope=None,expected_revision=None,expected_tasks=None,include_optional=False):
        from agent import Agent
        if type(limit) is not int or not 1<=limit<=12:raise ValueError('Elige entre 1 y 12 apartados por sesión.')
        p=self.store.load(project_id)
        if p.get('pending'):raise ValueError('Hay una petición pendiente: usa Reanudar antes de iniciar otro conjunto.')
        if expected_revision is not None and expected_revision!=p['revision']:raise ValueError('El proyecto cambió desde la aprobación: revisa el plan de nuevo.')
        tasks,notice=plan(p,include_optional);tasks=tasks[:limit]
        if expected_tasks is not None and tasks!=expected_tasks:raise ValueError('Cambió el plan: revisa el conjunto antes de iniciar.')
        if not tasks:raise ValueError(notice)
        p['autonomy']={'id':uuid.uuid4().hex,'status':'en_curso','limit':limit,'tasks':tasks,'completed':[],'started':now(),'reason':''}
        save_session(self.store,p,'en_curso','Conjunto autorizado; no incluye modificaciones de Word.')
        started=self.clock();reason='Límite del conjunto alcanzado.';status='completado'
        for i,task in enumerate(tasks):
            if self.stop.is_set():status='detenido';reason='Detenido por el usuario; lo guardado permanece.';break
            if self.clock()-started>=600:status='limite_tiempo';reason='Diez minutos alcanzados; no se inicia otro apartado.';break
            try:api=self.api_factory()
            except Exception:
                status='error';reason='No se pudo preparar una ruta configurada. Revisa Modelos y cuentas; no se inició otro apartado.';break
            if authorized_scope is None or not route_scope(api)<=authorized_scope:
                status='requiere_autorizacion';reason='Cambió el destinatario o su configuración: se requiere autorización, sin envío.';break
            self.emit(f'Trabajo autónomo {i+1}/{len(tasks)} · {task["mode"]} {task["label"]}')
            work=order(p,task)
            worker=Agent(self.store,api,self.approve_search,self.searcher,self.stop,self.emit)
            p=worker.turn(project_id,'Tarea automática autorizada: '+task['mode']+' '+task['label']+'.',research,origin='autonomo',task=work)
            if p.get('pending'):
                status='pendiente';reason='Se detuvo por error, cancelación o respuesta incierta. Reanudar retoma solo la petición pendiente; no reinicia el conjunto.';break
            if not p.get('last_step',{}).get('progress'):
                status='sin_avance';reason=p.get('last_step',{}).get('reason','El modelo no entregó un cambio nuevo. No se seguirá gastando en el mismo paso.');break
            p['autonomy']['completed'].append(task['section'])
            save_session(self.store,p,'en_curso','Guardado '+task['label']+'.');self.on_progress(p)
        if self.stop.is_set() and status=='completado':status='detenido';reason='Detenido; los apartados confirmados ya están guardados.'
        message(p,'system',f'Sesión autónoma: {len(p["autonomy"]["completed"])}/{len(tasks)} apartados con cambios guardados. '+reason+' Word no se modificó.')
        save_session(self.store,p,status,reason);return p
