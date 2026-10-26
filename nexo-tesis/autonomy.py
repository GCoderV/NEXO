"""Local bounded scheduler: academic drafts only, never Word or implicit recipients."""
import hashlib,json,re,time,uuid,unicodedata
from project_store import SECTIONS,LABELS,message,now

def clean(text):return re.sub(r'\s+',' ',text).strip()
def fingerprint(p,text):
    inputs={'topic':p['topic'],'facts':{k:v['value'] for k,v in p['facts'].items() if k!='guia'},'sources':p['sources'],'materials':[(m['sha256'],m.get('active'),m.get('shared_routes',[])) for m in p.get('materials',[]) if m['role']!='guia'],'data_ready':p.get('data_ready'), 'text':clean(text)}
    return hashlib.sha256(json.dumps(inputs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def protected(d):
    return not d.get('producer') or d.get('status') in ('aprobado_usuario','insertado_pendiente_revision_word') or d.get('previous_status') in ('aprobado_usuario','insertado_pendiente_revision_word') or d.get('edited_by_user') or d.get('warning','').startswith('Edición manual:')
def plan(p):
    if p.get('topic_pending'):return [],'Primero aporta un tema explícito; no se inventará.'
    typ=' '.join(p['facts'].get(k,{}).get('value','') for k in ('tipo_trabajo','metodologia'))
    typ=''.join(c for c in unicodedata.normalize('NFD',typ.lower()) if unicodedata.category(c)!='Mn')
    documentary=any(x in typ for x in ('documental','revision bibliografica','revision sistematica','revision de literatura'))
    proposal=any(x in typ for x in ('anteproyecto','protocolo','propuesta de investigacion'))
    action='accion' in typ or 'intervencion' in typ
    eligible=[];blocked=[]
    required=set()
    if p.get('format_profile'):
        from guide_rules import effective
        required={r['value'] for r in effective(p).get('rules',[]) if r['key']=='include_section'}
    for k in SECTIONS:
        if k in ('cronograma','presupuesto','anexos') and k not in required:continue
        if proposal and k in ('resultados','discusion','conclusiones'):continue
        if k in ('resultados','discusion','conclusiones') and not (p.get('data_ready') and p['facts'].get('datos')):
            blocked.append(LABELS[k]+': necesita datos/corpus aportados y confirmados en Memoria');continue
        if k=='referencias' and not p['sources']:continue
        if k=='plan_accion' and not action:continue
        if k=='instrumentos' and (documentary or not p['facts'].get('metodologia')):continue
        d=p['drafts'].get(k)
        if d and protected(d):continue
        mode='crear' if not d else 'revisar'
        if d and d.get('status')!='necesita_revision' and d.get('auto_reviewed_for')==fingerprint(p,d['text']):continue
        eligible.append({'section':k,'mode':mode,'label':LABELS[k]})
    # Missing/outdated first, then one review per input fingerprint, never endless polishing.
    eligible.sort(key=lambda t:(0 if t['section'] not in p['drafts'] or p['drafts'][t['section']]['status']=='necesita_revision' else 1,SECTIONS.index(t['section'])))
    notice='Se pueden producir borradores provisionales; lo no aportado debe quedar pendiente.' if eligible else 'No quedan tareas automáticas elegibles. Los borradores protegidos se conservan y los ya revisados no se reescriben sin nuevos datos.'
    if any(m.get('active') and not m.get('shared_routes') for m in p.get('materials',[])):notice+='\nHay archivos solo locales; no se usarán sus extractos sin permiso en Archivos.'
    if blocked:notice+='\nPendientes: '+'; '.join(blocked)+'.'
    return eligible,notice

def order(p,task):
    k=task['section'];d=p['drafts'].get(k)
    if k not in SECTIONS or (d and protected(d)):raise ValueError('El apartado está protegido o no es válido.')
    return {**task,'previous_text':d['text'] if d else '', 'instruction':'Entrega texto concreto y coherente con los datos del proyecto; conserva lo válido. Señala lo provisional y la evidencia pendiente.'}

def route_scope(api):
    if not hasattr(api,'routes'):return {(api.provider,api.model,getattr(api,'endpoint',''))}
    accounts=api.config.data['accounts']
    return {(r['provider'],r['model'],r['endpoint'],r['account_id'],accounts.get(r['account_id'],{}).get('generation','')) for r in api.routes}

def save_session(store,p,status,reason):
    p['autonomy'].update(status=status,reason=reason,updated=now())
    op=p.get('pending')
    if op and op.get('revision')==p['revision']:op['revision']=p['revision']+1
    store.save(p,'autonomy-'+status)

class AutonomousRunner:
    def __init__(self,store,api_factory,stop,emit=None,approve_search=None,searcher=None,clock=time.monotonic,on_progress=None):
        self.store=store;self.api_factory=api_factory;self.stop=stop;self.emit=emit or (lambda s:None);self.approve_search=approve_search;self.searcher=searcher;self.clock=clock;self.on_progress=on_progress or (lambda p:None)
    def run(self,project_id,limit=6,research=False,authorized_scope=None,expected_revision=None,expected_tasks=None):
        from agent import Agent
        if type(limit) is not int or not 1<=limit<=12:raise ValueError('Elige entre 1 y 12 apartados por sesión.')
        p=self.store.load(project_id)
        if p.get('pending'):raise ValueError('Hay una petición pendiente: usa Reanudar antes de iniciar otro conjunto.')
        if expected_revision is not None and expected_revision!=p['revision']:raise ValueError('El proyecto cambió desde la aprobación: revisa el plan de nuevo.')
        tasks,notice=plan(p);tasks=tasks[:limit]
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
