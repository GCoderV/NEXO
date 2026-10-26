"""SQLite project-scoped checkpoints with optimistic concurrency.
No reads from Nexo PC or from other projects when building model context.
"""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import uuid

MAX_PROJECT=3_000_000
FACT_KEYS=('nivel','institucion','programa','tipo_trabajo','metodologia','contexto','poblacion','datos','guia','alcance','objetivo_usuario')
SECTIONS=('delimitacion','problematica','pregunta','objetivos','justificacion','marco_teorico','metodologia','instrumentos','plan_accion','analisis_previsto','cronograma','presupuesto','resultados','discusion','conclusiones','referencias','anexos')
LABELS={'cronograma':'Cronograma','presupuesto':'Presupuesto','anexos':'Anexos','delimitacion':'Delimitación','problematica':'Problemática','pregunta':'Pregunta de investigación','objetivos':'Objetivos','justificacion':'Justificación','marco_teorico':'Marco teórico','metodologia':'Metodología','instrumentos':'Instrumentos','plan_accion':'Plan de acción','analisis_previsto':'Análisis previsto','resultados':'Resultados','discusion':'Discusión','conclusiones':'Conclusiones','referencias':'Referencias'}
class Conflict(RuntimeError):pass

def is_greeting(text):
    import unicodedata
    s=''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')
    return s.strip(' ¡!¿?.') in ('hola','buenas','buenos dias','buenas tardes','buenas noches','hello','hi','saludos')

def now():return datetime.now(timezone.utc).isoformat()
def safe_id(id):
    if not isinstance(id,str) or not re.fullmatch('[a-f0-9]{32}',id):raise ValueError('Identificador de proyecto inválido.')
    return id

def message(p,role,text):
    p['messages'].append({'id':uuid.uuid4().hex,'role':role,'text':text,'time':now()})
    return p['messages'][-1]['id']

def invalidate(p,reason):
    for d in p['drafts'].values():
        if d['status']!='necesita_revision':d['previous_status']=d['status']
        d['status']='necesita_revision';d['warning']=reason

def set_fact(p,key,value,evidence='',source='usuario',message_id=None):
    if key not in FACT_KEYS or not isinstance(value,str) or not value.strip() or len(value)>12000:raise ValueError('Dato no admitido.')
    previous=p['facts'].get(key)
    if previous is None or previous['value']!=value:
        if previous:p['decisions'].append({'key':key,'previous':previous,'time':now()})
        if key!='guia':invalidate(p,'Se incorporó o cambió '+key+'; revisar dependencias antes de utilizar este apartado.')
        if key in ('datos','contexto','poblacion','metodologia'):p['data_ready']=False
    p['facts'][key]={'value':value,'evidence':evidence,'source':source,'message_id':message_id,'status':'aportado, no verificado externamente','time':now()}
    for q in p['questions']:
        if q['key']==key and q['status']=='abierta':q['status']='respondida';q['answered_at']=now()

def validate(p):
    if not isinstance(p,dict) or p.get('schema')!=1:raise ValueError('Proyecto incompatible.')
    safe_id(p.get('id'))
    if not isinstance(p.get('topic'),str) or not 1<=len(p['topic'])<=1500:raise ValueError('Tema de 1 a 1500 caracteres requerido.')
    for k in ('facts','drafts'):
        if not isinstance(p.get(k),dict):raise ValueError('Proyecto inválido: '+k)
    for k in ('messages','questions','sources','decisions'):
        if not isinstance(p.get(k),list):raise ValueError('Proyecto inválido: '+k)
    if len(json.dumps(p,ensure_ascii=False).encode())>MAX_PROJECT:raise ValueError('Proyecto supera 3 MB; exporta una copia y archiva material antes de continuar. No se truncó.')
    return p

class ProjectStore:
    def __init__(self,root=None):
        self.root=Path(root or Path.home()/'.nexo-tesis').resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'projects.sqlite3'
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,topic TEXT NOT NULL,updated TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS checkpoints(project_id TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(project_id,revision));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,project_id TEXT NOT NULL,time TEXT NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL);''')
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=5);c.execute('PRAGMA busy_timeout=5000')
        try:
            with c:yield c
        finally:c.close()
    def create(self,topic):
        p={'schema':1,'id':uuid.uuid4().hex,'topic':topic.strip(),'created':now(),'updated':now(),'revision':0,'facts':{},'drafts':{},'messages':[],'questions':[],'sources':[],'decisions':[],'profile':None,'data_ready':False,'word_path':None,'run':{'status':'listo'},'usage':{'calls':0,'input_tokens':0,'output_tokens':0}}
        validate(p)
        message(p,'assistant','Proyecto creado a partir de tu tema. Trabajaremos por etapas: delimitar → plantear problema y objetivos → reunir fuentes → justificar metodología → desarrollar apartados → revisar. No he supuesto universidad, población ni método.\n\nPuedes pegar un texto con TODOS los datos disponibles, sin separarlos por campos. El agente extraerá lo explícito en una sola respuesta, lo distribuirá en Memoria y agrupará únicamente las preguntas iniciales que falten. Si todavía no tienes esos datos, pulsa «Continuar» para ver las preguntas juntas.')
        with self.connect() as c:c.execute('INSERT INTO projects VALUES(?,?,?,?,?)',(p['id'],p['topic'],p['updated'],0,json.dumps(p,ensure_ascii=False)))
        return p
    def load(self,id):
        with self.connect() as c:r=c.execute('SELECT payload FROM projects WHERE id=?',(safe_id(id),)).fetchone()
        if not r:raise ValueError('Proyecto no encontrado.')
        p=validate(json.loads(r[0]))
        if is_greeting(p['topic']):p['topic_pending']=True
        return p
    def list(self):
        with self.connect() as c:return [{'id':r[0],'topic':r[1],'updated':r[2]} for r in c.execute('SELECT id,topic,updated FROM projects ORDER BY updated DESC')]
    def save(self,p,event='checkpoint',detail=''):
        validate(p);nextp=copy.deepcopy(p);nextp['revision']+=1;nextp['updated']=now();validate(nextp)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT revision,payload FROM projects WHERE id=?',(p['id'],)).fetchone()
            if not old or old[0]!=p['revision']:raise Conflict('El proyecto cambió en otra operación. No se sobrescribió; vuelve a abrirlo.')
            c.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)',(p['id'],old[0],old[1]))
            c.execute('DELETE FROM checkpoints WHERE project_id=? AND revision NOT IN (SELECT revision FROM checkpoints WHERE project_id=? ORDER BY revision DESC LIMIT 6)',(p['id'],p['id']))
            c.execute('UPDATE projects SET topic=?,updated=?,revision=?,payload=? WHERE id=?',(nextp['topic'],nextp['updated'],nextp['revision'],json.dumps(nextp,ensure_ascii=False),p['id']))
            c.execute('INSERT INTO events(project_id,time,kind,detail) VALUES(?,?,?,?)',(p['id'],now(),event,detail[:2000]))
        p.update(nextp)
    def recover(self,p):
        if p['run'].get('status') in ('modelo','busqueda','en_curso'):
            p['run']={'status':'interrumpido','notice':'No se repitió la llamada anterior. Revisa lo último guardado y continúa explícitamente.'}
            if p.get('pending'):
                p['pending']['uncertain']=bool(p['pending'].get('inflight'));p['pending']['inflight']=False;p['pending']['revision']=p['revision']+1
            message(p,'system',p['run']['notice']);self.save(p,'recovery')
        return p
    def change_topic(self,p,topic):
        if not topic.strip():raise ValueError('Tema vacío.')
        p['decisions'].append({'key':'topic','previous':p['topic'],'time':now()})
        for key in list(p['facts']):
            if p['facts'][key]['source']=='extraído del tema; revisar interpretación':
                p['decisions'].append({'key':key,'previous':p['facts'].pop(key),'time':now()})
                for q in p['questions']:
                    if q['key']==key:q['status']='revisar_tras_cambio_tema'
        p['topic']=topic.strip();p['topic_pending']=False;p['data_ready']=False;invalidate(p,'Cambió el tema; revisar todos los apartados.');self.save(p,'topic-changed')
    def approve_draft(self,p,section):
        d=p['drafts'][section]
        if d['status']=='necesita_revision':raise ValueError('Apartado desactualizado: revísalo y guarda una versión antes de aprobarlo.')
        d['status']='aprobado_usuario';d['approved_at']=now();self.save(p,'draft-approved',section)
    def update_draft(self,p,section,text):
        if section not in SECTIONS or not text.strip() or len(text)>20000:raise ValueError('Apartado inválido o demasiado largo.')
        old=p['drafts'].get(section)
        revisions=(old.get('versions',[])+[{'text':old['text'],'time':now(),'status':old['status']}])[-5:] if old else []
        p['drafts'][section]={'text':text,'status':'borrador','sources':[],'edited_by_user':True,'material_ids':(old or {}).get('material_ids',[]),'warning':'Edición manual: revisar afirmaciones y referencias.','versions':revisions,'time':now()};self.save(p,'draft-edited',section)

def export_markdown(p):
    lines=['# '+p['topic'],'','Borrador de trabajo. No es una tesis validada ni un DOCX.','', '## Decisiones y datos aportados']
    for k,v in p['facts'].items():lines += [f"- **{k}**: {v['value']} ({v['status']})."]
    for k in SECTIONS:
        if k in p['drafts']:
            d=p['drafts'][k];lines += ['', '## '+LABELS[k],f"Estado: {d['status']}. {d.get('warning','')}",d['text']]
    lines += ['', '## Fuentes registradas — no bibliografía APA certificada']
    for s in p['sources']:lines += [f"### [{s['id']}] {s['title']}",f"{s.get('authors','')} · {s.get('year','')} · {s['status']}",s.get('url',''),f"Localizador: {s.get('locator','')}",f"Material consultado: {s.get('excerpt','')}"]
    lines += ['', '## Preguntas y pendientes']
    lines += [f"- [{q['status']}] {q['text']}" for q in p['questions']]
    lines += ['', '## Conversación completa del proyecto']
    for m in p['messages']:lines += ['### '+m['role']+' · '+m['time'],m['text']]
    return '\n\n'.join(lines)+'\n'
