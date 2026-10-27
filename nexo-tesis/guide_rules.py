"""Conservative, evidenced rule proposals; user selects before any Word application."""
from diagnostics import as_key, as_text
import copy,hashlib,re,unicodedata
DEFAULT={'page_size':'Carta','font':'Times New Roman','body_size':12,'heading_size':12,'subheading_size':12,'spacing':2.0,'margin_cm':2.54,'alignment':'izquierda'}
LABELS={'include_section':'Apartado requerido (confirmar contexto)','page_size':'Papel','font':'Fuente','body_size':'Tamaño cuerpo','heading_size':'Tamaño títulos','subheading_size':'Tamaño subtítulos','spacing':'Interlineado','margin_cm':'Márgenes (cm)','alignment':'Alineación cuerpo','heading_case':'Mayúsculas/minúsculas (revisión manual)'}
def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')
def proposals(segments):
    result=[]
    def add(key,value,text,locator,start,end):
        e=text[max(0,start-50):min(len(text),end+70)]
        boundaries=list(re.finditer(r'[;\n]|,(?!\d)|(?<!\d),|[.!?](?:\s|$)',text))
        left=max([b.end() for b in boundaries if b.end()<=start]+[0]);right=min([b.start() for b in boundaries if b.start()>=end]+[len(text)])
        near=norm(text[left:right])
        strength='ejemplo' if re.search(r'\b(ejemplo|ilustrativo)\b',near) else 'recomendación' if re.search(r'\b(recomienda|sugiere|preferible)\b',near) else 'obligatorio según texto' if re.search(r'\b(debe|deben|obligatorio|obligatoria|exige|requiere)\b',near) else 'por confirmar'
        scope='subtítulos' if 'subtitulo' in near else 'títulos' if re.search(r'\btitulos?\b',near) else 'referencias' if 'referencias' in near else 'general / por confirmar'
        if key=='margin_cm' and re.search(r'\b(izquierdo|derecho|superior|inferior)\b',near):scope='márgenes diferenciados'
        if key=='body_size' and scope in ('títulos','subtítulos'):key='heading_size' if scope=='títulos' else 'subheading_size'
        item={'key':key,'value':value,'evidence':e,'locator':locator,'strength':strength,'scope':scope}
        if not any(x['key']==key and x['value']==value and x['locator']==locator for x in result):result.append(item)
    for part in segments:
        raw=part['text'];n=norm(raw);loc=part['locator']
        for m in re.finditer(r'(?:papel|pagina|hoja|formato)[^\n.;]{0,15}\b(a4|carta|letter)\b',n):add('page_size','A4' if m[1]=='a4' else 'Carta',raw,loc,*m.span())
        for m in re.finditer(r'\b(cronograma|presupuesto|anexos)\b',n):add('include_section',m[1],raw,loc,*m.span())
        for m in re.finditer(r'\b(times new roman|arial|calibri)\b(?:\s*[,;]?\s*(?:tamano\s*)?(1[0-4]))?',n):
            add('font',{'times new roman':'Times New Roman','arial':'Arial','calibri':'Calibri'}[m[1]],raw,loc,*m.span())
            if m[2]:add('body_size',int(m[2]),raw,loc,*m.span())
        for m in re.finditer(r'interlineado\s*(?:de|:|=)?\s*(1[.,]5|1[.,]0|2[.,]0|doble|sencillo|simple|1|2)\b',n):add('spacing',{'doble':2.0,'sencillo':1.0,'simple':1.0}.get(m[1],float(m[1].replace(',','.')) if m[1][0].isdigit() else 2),raw,loc,*m.span())
        for key,pat in [('heading_size',r'\btitulos?\b[^\n\d]{0,28}(1[0-8])\b'),('subheading_size',r'\bsubtitulos?\b[^\n\d]{0,28}(1[0-8])\b'),('margin_cm',r'\bmargenes\b[^\n\d]{0,15}([1-4](?:[.,]\d{1,2})?)\s*cm')]:
            for m in re.finditer(pat,n):add(key,float(m[1].replace(',','.')),raw,loc,*m.span())
        for m in re.finditer(r'\b(subtitulos?|titulos?)\b[^\n.;,]{0,50}?\b(mayusculas?|minusculas?)\b',n):add('heading_case',m[1]+': '+m[2]+'; revisión manual en Word',raw,loc,*m.span())
        for m in re.finditer(r'(?:texto|cuerpo)\s+(?:alineado\s+a\s+la\s+)?(izquierda|justificado)\b',n):add('alignment',m[1],raw,loc,*m.span())
    return result[:80]
def approve(p,record,candidates,indices):
    chosen=[candidates[i] for i in sorted(set(indices))]
    if not chosen:raise ValueError('Selecciona las reglas que revisaste; no se aplica una guía automáticamente.')
    values={}
    for r in chosen:
        if not isinstance(r,dict):continue
        key=as_key(r.get('key'),'rule.key')
        if not key:continue
        if r.get('strength')=='ejemplo':raise ValueError('Una muestra o ejemplo no se aplica como requisito. Deja esa regla sin seleccionar o registra la decisión explícita en Memoria → guia.')
        scope=as_text(r.get('scope','general / por confirmar'),'rule.scope',200)
        if key in ('font','body_size','spacing','margin_cm','alignment','page_size') and scope!='general / por confirmar':raise ValueError('Regla de ámbito específico ('+scope+'). No se convertirá en formato global; revísala manualmente.')
        if key in ('include_section','heading_case'):continue
        if key in values and values[key]!=r.get('value'):raise ValueError('Hay valores contradictorios para '+LABELS.get(key,key)+'. Elige cuál corresponde.')
        values[key]=r.get('value')
    effective={**DEFAULT,**{k:v for k,v in values.items() if k in DEFAULT}}
    validate(effective)
    p['format_profile']={'name':'Guía revisada: '+record['name'],'source_id':record['id'],'sha256':record['sha256'],'rules':chosen,'effective':effective,'manual_checks':[r.get('value') for r in chosen if isinstance(r,dict) and as_key(r.get('key'),'rule.key')=='heading_case']}
    return p['format_profile']
def validate(v):
    if v.get('page_size','Carta') not in ('Carta','A4'):raise ValueError('Tamaño de papel no admitido.')
    if v.get('font') not in ('Times New Roman','Arial','Calibri') or v.get('alignment') not in ('izquierda','justificado'):raise ValueError('Perfil de formato no admitido.')
    for k in ('body_size','heading_size','subheading_size'):
        if type(v.get(k)) not in (int,float) or not 10<=v[k]<=18:raise ValueError('Tamaño inválido.')
    if v.get('spacing') not in (1,1.5,2) or type(v.get('margin_cm')) not in (int,float) or not 1<=v['margin_cm']<=4:raise ValueError('Espaciado o márgenes inválidos.')
    return v

def effective(p,root=None):
    profile=p.get('format_profile')
    if not profile:return {'name':'APA 7 base','effective':copy.deepcopy(DEFAULT),'manual_checks':[]}
    if profile['source_id']=='memoria-guia':valid=hashlib.sha256(p['facts'].get('guia',{}).get('value','').encode()).hexdigest()==profile['sha256']
    else:valid=any(m['id']==profile['source_id'] and m['sha256']==profile['sha256'] and m.get('active') for m in p.get('materials',[]))
    if valid and root is not None and profile['source_id']!='memoria-guia':
        from materials import content
        content(root,p,next(m for m in p['materials'] if m['id']==profile['source_id']))
    if not valid:raise ValueError('La guía cambió o fue retirada. Revisa de nuevo sus reglas antes de aplicar formato.')
    profile=copy.deepcopy(profile);profile['effective']={**DEFAULT,**profile['effective']}
    validate(profile['effective']);return profile
