"""Local, deterministic document placement and APA layout planning; no model calls.
All positions originate in the inspected native Word document. No silent replacement.
"""
import hashlib,json,re,unicodedata
from project_store import SECTIONS,LABELS
ALIASES={ 'cronograma':['cronograma','cronograma de actividades'],'presupuesto':['presupuesto'],'anexos':['anexos'],
 'delimitacion':['delimitación','delimitación del tema','delimitación de la investigación'],
 'problematica':['problemática','planteamiento del problema','situación problemática','problema de investigación'],
 'pregunta':['pregunta de investigación','preguntas de investigación','formulación del problema'],
 'objetivos':['objetivos','objetivos de la investigación'],
 'justificacion':['justificación','justificación de la investigación'],
 'marco_teorico':['marco teórico','marco conceptual','marco teórico y conceptual'],
 'metodologia':['metodología','diseño metodológico','marco metodológico'],
 'instrumentos':['instrumentos','instrumentos de recolección de datos'],
 'plan_accion':['plan de acción'], 'analisis_previsto':['análisis previsto','plan de análisis'],
 'resultados':['resultados','presentación de resultados','análisis de resultados'],
 'discusion':['discusión','discusión de resultados'], 'conclusiones':['conclusiones'],
 'referencias':['referencias','referencias bibliográficas','bibliografía']}
def normalized(s):
    s=''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')
    s=re.sub(r'^\s*(?:capitulo\s+[ivxlcdm\d]+\s*[:.\-–]?\s*|(?:\d+(?:\.\d+)*|[ivxlcdm]+)[.)\s:\-–]+)','',s)
    return re.sub(r'\s+',' ',s).strip(' \r\n\t:.-–')
LOOKUP={normalized(x):k for k,v in ALIASES.items() for x in v}
INTRO={'introduccion','resumen','abstract','introducción'}
def key_for(text):return LOOKUP.get(normalized(text))
def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def validate_state(s,path):
    if not isinstance(s,dict) or s.get('path','').casefold()!=path.casefold():raise ValueError('La estructura pertenece a otro documento.')
    for k in ('end','hwnd'):
        if type(s.get(k)) is not int or s[k]<0:raise ValueError('Posiciones de Word inválidas.')
    for k in ('hash','structure_hash'):
        if not isinstance(s.get(k),str) or not re.fullmatch('[a-f0-9]{64}',s[k]):raise ValueError('Huella de documento inválida.')
    ps=s.get('paragraphs')
    if not isinstance(ps,list) or len(ps)>4000:raise ValueError('Estructura de documento demasiado grande.')
    previous=-1
    for p in ps:
        if not isinstance(p,dict) or any(type(p.get(k)) is not int for k in ('start','end','level')) or not 0<=p['start']<p['end']<=s['end'] or p['start']<previous or not isinstance(p.get('text'),str) or len(p['text'])>240:raise ValueError('Párrafo de Word inválido.')
        previous=p['end']
    if not isinstance(s.get('tocs',[]),list) or len(s.get('tocs',[]))>10:raise ValueError('Lista de índices inválida.')
    for r in s.get('tocs',[]):
        if not isinstance(r,dict) or any(type(r.get(k)) is not int for k in ('start','end')) or not 0<=r['start']<=r['end']<=s['end']:raise ValueError('Índice fuera del documento.')
    if not isinstance(s.get('markers',[]),list) or any(not isinstance(x,str) for x in s.get('markers',[])):raise ValueError('Marcadores inválidos.')
    return s

def in_toc(p,s):return any(p['start']<t['end'] and p['end']>t['start'] for t in s.get('tocs',[]))
def headings(s):
    out=[]
    for p in s['paragraphs']:
        if p.get('table') or p.get('special') or in_toc(p,s):continue
        k=None if p.get('truncated') else key_for(p['text']);n='' if p.get('truncated') else normalized(p['text'])
        label_kind='abstract' if n in ('resumen','abstract') else 'appendix' if re.fullmatch(r'(?:apendice|anexo)(?:s| [a-z0-9]+)?',n) else ''
        if k or 1<=p['level']<=9 or n in INTRO or label_kind:
            out.append({**p,'key':k,'label_kind':label_kind,'level':p['level'] if 1<=p['level']<=9 else 1})
    return out

def paragraphs(text,section,drop_main=True,base_level=1):
    if not isinstance(text,str) or not text.strip() or len(text.encode('utf-16-le'))//2>10000:raise ValueError('Cada apartado admite entre 1 y 10000 caracteres.')
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',text):raise ValueError('El texto contiene caracteres de control no admitidos; revisa el borrador.')
    if '|' in text and re.search(r'^\s*\|?.*\|.*\n\s*\|?\s*:?-{3}',text,re.M):raise ValueError('Una tabla Markdown necesita revisión; no se convertirá a párrafos automáticamente.')
    chunks=[];pending=[];root_depth=None
    def push():
        if pending:
            chunks.append({'text':' '.join(pending),'kind':'reference' if section=='referencias' else 'body'});pending.clear()
    for line in text.replace('\r\n','\n').replace('\r','\n').split('\n'):
        line=line.strip()
        if not line:push();continue
        h=re.match(r'^(#{1,5})\s+(.+)$',line)
        if h:
            push();label=h[2].strip().strip('*').strip()
            if drop_main and not chunks and key_for(label)==section:root_depth=len(h[1]);continue # existing/new main heading is separate
            level=len(h[1])-root_depth+1 if root_depth else len(h[1])+base_level
            if not 1<=level<=3:raise ValueError('El borrador usa encabezados que requieren revisión específica (niveles superiores a 3 o jerarquía inconsistente).')
            chunks.append({'text':label,'kind':'heading','level':level});continue
        if re.fullmatch(r'\*\*[^*]+\*\*',line) and len(line)<180:
            push();label=line.strip('*').strip()
            if drop_main and not chunks and key_for(label)==section:continue
            pending.append(line);continue
        if line.startswith('> '):
            push();chunks.append({'text':line[2:],'kind':'quote'});continue
        if re.match(r'^(?:[-•]|\d+[.)])\s+',line):
            push();chunks.append({'text':line,'kind':'list'});continue
        if section=='referencias':push();chunks.append({'text':line,'kind':'reference'})
        else:pending.append(line)
    push()
    if not chunks:raise ValueError('El apartado no contiene texto para insertar.')
    for block in chunks:
        # Only explicit paired markdown emphasis is converted, never evaluate embedded code.
        raw=block['text'];plain='';runs=[];cursor=0
        for m in re.finditer(r'\*\*([^*\n]+)\*\*|(?<!\*)\*([^*\n]+)\*(?!\*)',raw):
            plain+=raw[cursor:m.start()];value=m[1] if m[1] is not None else m[2]
            runs.append({'start':len(plain.encode('utf-16-le'))//2,'length':len(value.encode('utf-16-le'))//2,'bold':m[1] is not None,'italic':m[1] is None});plain+=value;cursor=m.end()
        block['text']=plain+raw[cursor:];block['runs']=runs
    return chunks

def build_plan(state,project,selected=(),format_all=True,index=True):
    validate_state(state,state['path']);hs=headings(state);warnings=[];operations=[];promotions=[]
    if type(format_all) is not bool or type(index) is not bool:raise ValueError('Opciones de formato inválidas.')
    if len(selected)>len(SECTIONS) or len(set(selected))!=len(selected):raise ValueError('Selección de apartados inválida.')
    if state.get('revisions',0):warnings.append('Hay revisiones previas: se conservan; no se aceptarán automáticamente.')
    for h in hs:
        if not 1<=next(p['level'] for p in state['paragraphs'] if p['start']==h['start'])<=9:
            promotions.append({'start':h['start'],'end':h['end'],'level':h['level'],'key':h['key'],'text':h['text']})
    for key in sorted(selected,key=lambda k:SECTIONS.index(k) if k in SECTIONS else 999):
        if key not in SECTIONS or key not in project['drafts']:raise ValueError('Apartado no disponible.')
        d=project['drafts'][key]
        if d['status']=='necesita_revision':raise ValueError(LABELS[key]+': guarda una revisión antes de insertarlo.')
        if key in ('resultados','discusion','conclusiones') and not project.get('data_ready'):raise ValueError('Confirma primero los datos reales de '+LABELS[key]+'.')
        marker='NexoS'+digest(project['id']+'\n'+key+'\n'+d['text'])[:32]
        if marker in state.get('markers',[]):warnings.append(LABELS[key]+': este mismo texto ya tiene un marcador de inserción; no se repetirá.');continue
        matches=[h for h in hs if h['key']==key]
        if len(matches)>1:raise ValueError(LABELS[key]+': hay varias ubicaciones posibles ('+', '.join(str(h['start']) for h in matches)+'). No se eligió a ciegas. Revisa los títulos duplicados o utiliza la inserción manual.')
        new=False
        if matches:
            h=matches[0];next_h=next((x for x in hs if x['start']>=h['end'] and x['level']<=h['level']),None)
            position=next_h['start'] if next_h else state['end']-1
            target='Al final de «'+h['text'].strip()+'», antes de «'+next_h['text'].strip()+'»' if next_h else 'Al final de «'+h['text'].strip()+'»'
        else:
            following=next((h for h in hs if (h['key'] and SECTIONS.index(h['key'])>SECTIONS.index(key)) or h.get('label_kind')=='appendix'),None)
            if not hs and not state.get('empty'):raise ValueError('No hay títulos reconocibles para ubicar '+LABELS[key]+'. Marca los títulos con estilos de Word o usa la inserción manual; no se alteró el documento.')
            position=following['start'] if following else state['end']-1;new=True
            target='Crear «'+LABELS[key]+'» '+('antes de «'+following['text'].strip()+'»' if following else 'al final del documento')
        blocks=paragraphs(d['text'],key)
        if new:blocks.insert(0,{'kind':'heading','level':1,'text':LABELS[key],'runs':[]})
        operations.append({'section':key,'position':position,'target':target,'blocks':blocks,'marker':marker,'order':SECTIONS.index(key),'source_hash':digest(d['text'])})
        if re.search(r'\[F\d+\]|FUENTE PENDIENTE|Por completar',d['text'],re.I):warnings.append(LABELS[key]+': contiene referencias/IDs pendientes; el formato no las convierte en citas APA verificadas.')
    if sum(len(b['text'].encode('utf-16-le'))//2 for op in operations for b in op['blocks'])>60000:raise ValueError('El lote supera 60000 caracteres. Selecciona menos apartados.')
    toc={'mode':'none'}
    if index:
        if not any(h['level']<=3 for h in hs) and not any(b['kind']=='heading' and b['level']<=3 for o in operations for b in o['blocks']):raise ValueError('No hay encabezados de niveles 1–3 para un índice utilizable. No se creará un campo vacío.')
        if len(state.get('tocs',[]))>1:raise ValueError('Hay varios índices automáticos. No se actualizará uno al azar; resuelve cuál corresponde en Word.')
        if state.get('tocs'):toc={'mode':'update','position':state['tocs'][0]['start']}
        else:
            body=next((h for h in hs if h['key'] or normalized(h['text'])=='introduccion'),None)
            if body is None:
                if state.get('empty') and operations:pos=0
                else:raise ValueError('No se identificó el inicio del cuerpo para colocar el índice. Añade un título principal reconocible; no se insertará delante de una portada por suposición.')
            else:pos=body['start']
            toc={'mode':'create','position':pos}
    body_start=next((h['start'] for h in hs if h['key'] or normalized(h['text'])=='introduccion'),state['end']-1)
    boundary=next((h for h in hs if h['start']==body_start),None)
    if boundary and (format_all or toc['mode']=='create') and sum(1 for h in hs if (h['key']==boundary['key'] if boundary['key'] else normalized(h['text'])==normalized(boundary['text'])))>1:raise ValueError('El título que delimita el comienzo del cuerpo aparece varias veces. Revisa la estructura o un posible índice manual; no se eligió una ubicación a ciegas.')
    if state.get('empty'):body_start=0
    if format_all:
        if not state.get('empty') and not any(h['key'] or normalized(h['text'])=='introduccion' for h in hs):raise ValueError('No se identificó el comienzo del cuerpo para distinguirlo de la portada. Marca un título principal reconocible antes de normalizar todo el documento.')
        warnings.extend(['En la portada se conservan alineación y sangrías; se normalizan fuente e interlineado. Revisa sus datos y requisitos institucionales.', 'Tablas, ecuaciones, notas, citas complejas y niveles de encabezado 4–9 requieren revisión específica. No se certifican citas ni referencias completas.'])
        if state.get('page_number_present') or state.get('header_text_present'):warnings.append('Hay numeración o contenido en encabezados/pies: se preservará; no se duplicará ni moverá silenciosamente. Revisa que la numeración esté arriba a la derecha.')
    if not operations and not format_all and toc['mode']=='none':raise ValueError('No hay cambios nuevos seleccionados.')
    if any(h['start']<body_start and h.get('label_kind')!='abstract' for h in hs):warnings.append('Hay encabezados antes del cuerpo: revisa que la portada no use niveles de esquema si no debe aparecer en el índice.')
    from guide_rules import effective
    profile=effective(project)
    if not project.get('format_profile') and (project.get('facts',{}).get('guia') or any(m.get('role')=='guia' and m.get('active') for m in project.get('materials',[]))):warnings.append('Hay una guía registrada sin perfil aprobado: revisa sus reglas en Archivos; esta vista previa usa la base APA.')
    warnings.extend('Revisión manual según guía: '+str(x) for x in profile.get('manual_checks',[]))
    return {'format_profile':profile,'schema':1,'path':state['path'],'snapshot':{k:state[k] for k in ('path','hwnd','hash','structure_hash','end')},'project_id':project['id'],'project_revision':project['revision'],'format_all':format_all,'body_start':body_start,'operations':operations,'promotions':promotions,'headings':[{'start':h['start'],'end':h['end'],'level':h['level'],'key':h['key'],'label_kind':h.get('label_kind',''),'text':h['text']} for h in hs], 'toc':toc,'warnings':list(dict.fromkeys(warnings))}

def preview(plan):
    lines=['VISTA PREVIA — '+plan['path'],'No se guardará el archivo ni se sustituirá contenido académico ni se aceptarán revisiones. Word puede regenerar las entradas del índice. No edites Word mientras se aplica.']
    if plan['format_all']:
        from guide_rules import DEFAULT
        profile=plan.get('format_profile',{'name':'APA 7 base','effective':DEFAULT});v=profile['effective']
        lines+=['','FORMATO: '+profile['name'],f"{v['font']} {v['body_size']}; interlineado {v['spacing']}; títulos {v['heading_size']}, subtítulos {v['subheading_size']}; alineación {v['alignment']}; márgenes {v['margin_cm']} cm; papel {v.get('page_size','Carta')}. Base: márgenes de 2,54 cm cuando no hay otra regla aprobada; sangrías APA. No se convierte automáticamente el uso de mayúsculas/minúsculas.", 'Se conserva el contenido de portada, tablas y cabeceras; la paginación puede cambiar. Numeración superior derecha solo si no hay numeración/contenido previo en cabeceras o pies.']
        if profile.get('rules'):lines+=['Reglas aprobadas:']+[str(r['key'])+' = '+str(r['value'])+' · '+r['locator']+' · '+r['evidence'] for r in profile['rules']]
    if plan['promotions']:lines+=['','Títulos de texto que se convertirán en encabezados para formato/índice: '+', '.join(LABELS.get(h['key'],h['text']) for h in plan['promotions'])]
    if plan['toc']['mode']!='none':lines+=['','ÍNDICE: '+('actualizar el campo existente' if plan['toc']['mode']=='update' else 'crear índice automático antes del cuerpo, posición '+str(plan['toc']['position']))+'. Niveles 1–3; páginas calculadas por Word. Si el índice previo tenía entradas personalizadas, se conservan y requieren revisión.']
    if plan['headings']:lines+=['','ENCABEZADOS DETECTADOS (nivel · posición):']+['• '+h['text']+' — '+str(h['level'])+' · '+str(h['start']) for h in plan['headings']]
    for op in plan['operations']:
        lines+=['','INSERTAR '+LABELS[op['section']].upper(),op['target']+' · posición '+str(op['position']),'Texto nuevo (no sustituye el apartado previo):','\n\n'.join(b['text'] for b in op['blocks'])]
    if plan['warnings']:lines+=['','REVISAR:']+['• '+w for w in plan['warnings']]
    return '\n'.join(lines)
