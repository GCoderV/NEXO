"""Nexo's own runtime: observable prepare/review/execute/result phases.
No Cline runtime or SDK is imported. See TRAZABILIDAD.md for study boundaries.
"""
import copy
import json
from pathlib import Path
from adapters import Cancelled, DECLARATIONS, validate_call
from permissions import Authorization
from conversation import switch_session, build_context

READ_ONLY={'read_file','list_files'}

def response_parts(provider, pending):
    if provider=='Ollama':
        return [{'role':'tool','tool_name':item['name'],'content':json.dumps(item['result'],ensure_ascii=False)} for item in pending]
    if provider=='Gemini':
        parts=[]
        for item in pending:
            response={'name':item['name'],'response':item['result']}
            if item.get('id'):response['id']=item['id']
            parts.append({'functionResponse':response})
            if item.get('image'):parts.append({'inlineData':{'mimeType':'image/jpeg','data':item['image']}})
        return [{'role':'user','parts':parts}]
    return [{'role':'tool','tool_call_id':item['id'],'name':item['name'],'content':json.dumps(item['result'],ensure_ascii=False)} for item in pending]

def recover_pending(session):
    """Never replay a tool after a crash. Close unfinished provider protocol messages."""
    if not session.get('pending'):return False
    for item in session['pending']:
        if item.get('result') is None:
            item['result']={'interrupted':True,'previous_state':item.get('state'),
                            'message':'Acción interrumpida; sus efectos pueden ser desconocidos. No se volvió a ejecutar. Inspecciona el estado antes de proponer repetirla.'}
        item.pop('image',None)
    session['messages'].extend(response_parts(session['provider'],session['pending']))
    session['pending']=[];session['status']='interrupted'
    return True

class Runtime:
    def __init__(self,api,tools,store,review,emit,stop):
        self.api,self.tools,self.store,self.review,self.emit,self.stop=api,tools,store,review,emit,stop
    def check(self):
        if self.stop.is_set():raise Cancelled('Detenido por el usuario.')
    def say(self,session,who,text):
        text=str(text).replace(self.api.key,'[CLAVE OMITIDA]') if getattr(self.api,'key',None) else str(text)
        session['display'].append({'who':who,'text':text});self.emit(who,text)
    def save(self,session):self.store.save(session)
    def run(self,prompt,session,mode,enabled,approval="step",max_calls=8,max_actions=16,broad=False,context_limit=60000,economy=True):
        if mode not in ('PLAN','ACT'):raise ValueError('Modo inválido.')
        if not prompt.strip() or len(prompt)>6000:raise ValueError('La tarea debe tener entre 1 y 6000 caracteres.')
        if Path(session['workspace']).resolve()!=self.tools.root:raise ValueError('La carpeta no coincide con la sesión. Crea otra sesión para otra carpeta.')
        if self.store.root.is_relative_to(self.tools.root) or Path(__file__).resolve().parent.is_relative_to(self.tools.root):
            raise ValueError('Usa una carpeta dedicada que no contenga los datos ni el código de Nexo.')
        if recover_pending(session):self.say(session,'Recuperación','Se cerraron llamadas pendientes sin repetirlas. Verifica sus efectos antes de continuar.')
        for value,low,high in [(max_calls,1,64),(max_actions,1,256),(context_limit,10000,500000)]:
            if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:raise ValueError('Límites inválidos.')
        if switch_session(session,self.api.provider,self.api.model,getattr(self.api,'endpoint','')):
            self.say(session,'Modelo',f'Continúas en este mismo chat con {self.api.provider} · {self.api.model}. Historial conservado; no se repiten acciones ni se transfieren permisos anteriores.')
        allowed=set(enabled)-{'submit_plan'}
        if mode=='ACT' and approval=='plan':allowed.add('submit_plan')
        if mode=='PLAN':allowed &= READ_ONLY
        authorization=Authorization(mode,approval,allowed,self.tools.root,self.review,broad,max_calls,max_actions)
        declarations=[d for d in DECLARATIONS if d['name'] in allowed]
        current=f'Modo elegido por el usuario: {mode}. Política: {approval}. Límites: {max_calls} solicitudes, {max_actions} acciones. Carpeta: {self.tools.root}. Herramientas: {sorted(allowed)}.\n{prompt}'
        session['messages'].append({'role':'user','parts':[{'text':current}]} if self.api.provider=='Gemini' else {'role':'user','content':current})
        session['status']='running';self.say(session,'Tú · '+mode,prompt);self.save(session)
        action_count=0
        try:
            for iteration in range(max_calls):
                self.check()
                outbound,stats=build_context(session,context_limit,economy)
                session['context_stats']=stats
                if stats['compacted'] and not session.get('context_notice_shown'):
                    self.say(session,'Ahorro','Se envían extractos locales y los pasos recientes; el historial completo sigue guardado. No se usa otra llamada al modelo para resumir. Puede faltar detalle antiguo: puedes consultarlo en el chat o ampliar el contexto en Ajustes.')
                    session['context_notice_shown']=True
                session['api_calls']+=1;self.save(session)
                message,text,calls=self.api.request(outbound,declarations)
                usage=getattr(self.api,'last_usage',{})
                if usage:
                    totals=session.setdefault('usage_totals',{'input_tokens':0,'output_tokens':0,'reported_requests':0})
                    for name in ('input_tokens','output_tokens'):totals[name]+=usage.get(name,0)
                    totals['reported_requests']+=1
                    session['last_usage']={'provider':self.api.provider,'model':self.api.model,**usage}
                self.check();session['messages'].append(message)
                if text:self.say(session,'Nexo',text)
                if not calls:
                    if not text:self.say(session,'Aviso','El proveedor devolvió una respuesta vacía. La tarea no se da por completada automáticamente.')
                    session['status']='idle';self.save(session);return
                session['pending']=[{**copy.deepcopy(c),'state':'proposed','result':None} for c in calls]
                self.save(session)
                prepared=[]
                # Preparation (including review) precedes execution, following the observed contract.
                for item in session['pending']:
                    self.check();action_count+=1;preview=None
                    try:
                        validate_call(item['name'],item['args'])
                        if action_count>max_actions:raise ValueError(f'Límite de {max_actions} acciones por tarea alcanzado.')
                        if item['name'] not in allowed:raise ValueError('Herramienta bloqueada por el modo o por tus permisos.')
                        if item['name']=='write_file':preview=self.store.preview(self.tools.root,**item['args'])
                        details={'mode':mode,'workspace':str(self.tools.root),'tool':item['name'],'arguments':item['args']}
                        if preview:details['diff']=preview['diff'];details['expected_hash']=preview['expected_hash']
                        self.store.audit(session['id'],'review-requested',tool=item['name'])
                        # Reviewer receives an isolated copy; cannot silently change the proposed command.
                        answer=authorization.authorize(item['name'],details)
                        self.check()
                        if answer is not True:
                            item['state']='denied';item['result']={'denied':True,'message':'Acción rechazada. No se ejecutó; no intentes eludir el rechazo con otra herramienta.'}
                        else:
                            item['state']='approved'
                            self.store.audit(session['id'],'authorized',tool=item['name'],policy=approval,broad=broad)
                    except Cancelled:raise
                    except Exception as e:
                        item['state']='blocked';item['result']={'error':str(e),'executed':False}
                    prepared.append((item,preview));self.save(session)
                for item,preview in prepared:
                    self.check();name=item['name']
                    if item['state']=='approved':
                        item['state']='executing';self.save(session)
                        self.store.audit(session['id'],'tool-started',tool=name)
                        try:
                            if name=='submit_plan':result={'approved':True,'message':'Plan autorizado para esta tarea. Ejecuta y verifica sin pedir de nuevo los pasos cubiertos; respeta permisos y límites.'}
                            elif name=='write_file':result=self.store.write(self.tools.root,**item['args'],session=session['id'],expected_hash=preview['expected_hash'])
                            else:result=self.tools.execute(name,item['args'])
                            image=result.pop('image_base64',None)
                            item['result']=result
                            # Pixels only exist in current in-memory conversation, not the pending journal.
                            if image:item['image']=image
                        except Cancelled:raise
                        except Exception as e:
                            if type(e).__name__=='FailSafeException':self.stop.set();raise Cancelled('Parada de emergencia del ratón.')
                            item['result']={'error':str(e),'message':'La operación falló; puede haber tenido efectos parciales. Verifica antes de reintentar.'}
                        item['state']='done';self.save(session)
                    self.store.audit(session['id'],'tool-result',tool=name,state=item['state'],error='error' in item['result'])
                    result_text=json.dumps(item['result'],ensure_ascii=False)
                    self.say(session,'Herramienta · '+name,result_text[:16000]+('\n[Vista truncada]' if len(result_text)>16000 else ''))
                session['messages'].extend(response_parts(self.api.provider,session['pending']))
                session['pending']=[];self.save(session)
                if authorization.denied:
                    session['status']='denied';self.say(session,'Permisos','Plan rechazado. No se ejecutará ni se volverá a solicitar en esta tarea.');return
                if action_count>=max_actions:break
            session['status']='limit';self.say(session,'Límite',f'Se alcanzó el presupuesto de esta tarea ({max_calls} solicitudes / {max_actions} acciones). Revisa lo hecho. Puedes continuar con una nueva autorización; no se da por completada.')
        except Cancelled:
            recover_pending(session);session['status']='interrupted';self.say(session,'Detenido','No se ejecutarán más acciones en este turno. Las acciones previas no se deshacen.')
        except Exception as e:
            recover_pending(session);session['status']='error';self.say(session,'Error',str(e))
        finally:
            # Strip pending image bytes before serialization (messages also use disk_copy).
            for item in session.get('pending',[]):item.pop('image',None)
            self.save(session)
