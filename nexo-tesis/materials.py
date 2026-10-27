"""Project-local file library. Originals never auto-uploaded; grants cover extracted text only."""
import csv,hashlib,json,os,re,shutil,subprocess,sys,uuid,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from project_store import safe_id,now
MAX_BYTES=20*1024*1024
MAX_TEXT=100000
ROLES=('guia','borrador','fuente','datos','observaciones')
FORMATS=('.pdf','.docx','.txt','.md','.csv','.tsv','.xlsx','.pptx','.png','.jpg','.jpeg')

def extract(path,native=None):
    path=Path(path);ext=path.suffix.lower();segments=[];total=0;omitted=0;warnings=[]
    if ext not in FORMATS or path.stat().st_size>MAX_BYTES:raise ValueError('Formato no admitido o archivo superior a 20 MB.')
    def add(locator,text):
        nonlocal total,omitted
        text=str(text).replace('\x00','').strip()
        if not text:return False
        room=MAX_TEXT-total
        if room<=0:omitted+=1;return False
        if len(text)>room:omitted+=1;text=text[:room];warnings.append('Extracción truncada por límite de 100000 caracteres.')
        # Split at bounded paragraphs while retaining locator.
        for pos in range(0,len(text),3000):segments.append({'locator':locator+(' · fragmento '+str(pos//3000+1) if len(text)>3000 else ''),'text':text[pos:pos+3000]})
        total+=len(text);return True
    units=0;read=0
    if ext=='.docx':
        if native is None:raise ValueError('La lectura DOCX utiliza Word nativo en Windows, no un conversor alternativo.')
        data=native(str(path));units=data['total'];warnings+=data.get('warnings',[])
        for part in data['segments']:read+=int(add(part['locator'],part['text']))
        omitted+=data.get('omitted',0)
    elif ext=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(str(path),strict=False)
        if reader.is_encrypted:raise ValueError('PDF cifrado: no se intentó eludir su protección.')
        units=len(reader.pages)
        if units>200:raise ValueError('PDF superior a 200 páginas. Divide el documento en partes.')
        for i,page in enumerate(reader.pages):
            if total>=MAX_TEXT:omitted+=units-i;break
            try:read+=int(add('página '+str(i+1),page.extract_text(extraction_mode='plain') or ''))
            except Exception:omitted+=1;warnings.append('No se extrajo la página '+str(i+1)+'.')
        warnings.append('Solo texto; imágenes, gráficos y páginas escaneadas no se interpretan. Si faltan páginas, requieren OCR.')
    elif ext in ('.png','.jpg','.jpeg'):
        units=1;warnings.append('Imagen recibida, sin OCR en esta versión. No se declara leída ni se envía como imagen a Copilot.')
    elif ext in ('.txt','.md','.csv','.tsv'):
        raw=path.read_bytes()
        try:text=raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            if raw.startswith((b'\xff\xfe',b'\xfe\xff')):text=raw.decode('utf-16')
            else:raise ValueError('Guarda el texto como UTF-8 o UTF-16 con BOM; no se adivinó su codificación.')
        if ext in ('.csv','.tsv'):
            rows=csv.reader(text.splitlines(),delimiter='\t' if ext=='.tsv' else ',')
            for i,row in enumerate(rows,1):
                units=i
                if i>5000:omitted+=1;warnings.append('Límite de 5000 filas; el total de filas del archivo no se calculó.');break
                read+=int(add('fila '+str(i),' | '.join(row)))
        else:
            lines=text.splitlines();units=len(lines)
            for i in range(0,len(lines),30):read+=int(add('líneas '+str(i+1)+'–'+str(min(i+30,len(lines))),'\n'.join(lines[i:i+30])))
            read=units if not omitted else min(units,read*30)
    else:
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            if len(infos)>3000 or sum(i.file_size for i in infos)>60*1024*1024 or any(i.file_size>12*1024*1024 for i in infos):raise ValueError('Paquete Office demasiado grande al descomprimir.')
            def xml(name):
                b=z.read(name)
                if b'\x00' in b or b'<!DOCTYPE' in b.upper() or b'<!ENTITY' in b.upper():raise ValueError('XML con declaraciones no admitidas.')
                return ET.fromstring(b)
            ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
            if ext=='.xlsx':
                strings=[]
                if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(x.itertext()) for x in xml('xl/sharedStrings.xml').findall('s:si',ns)]
                sheets=sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n))
                for name in sheets:
                    for row in xml(name).findall('.//s:row',ns):
                        units+=1
                        if units>5000:omitted+=1;warnings.append('Límite de 5000 filas; el total de filas del libro no se calculó.');break
                        cells=[]
                        for c in row.findall('s:c',ns):
                            v=c.find('s:v',ns);value=v.text or '' if v is not None else ''.join(c.find('s:is',ns).itertext()) if c.find('s:is',ns) is not None else ''
                            if c.get('t')=='s':value=strings[int(value)] if value.isdigit() and int(value)<len(strings) else '[cadena no disponible]'
                            if c.find('s:f',ns) is not None:value+=' [resultado guardado de fórmula; no recalculado]'
                            cells.append((c.get('r') or '?')+'='+value)
                        read+=int(add(Path(name).stem+' · fila '+str(row.get('r','?')),' | '.join(cells)))
                warnings.append('Se leen valores guardados por celda; no se ejecutan fórmulas, macros, enlaces ni gráficos. Hojas identificadas por su parte interna sheetN, incluidas ocultas si existen. Revisa el texto antes de compartir.')
            else:
                slides=sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)),key=lambda n:int(re.search(r'(\d+)\.xml',n)[1]))
                units=len(slides)
                for i,n in enumerate(slides[:200],1):read+=int(add('parte '+Path(n).stem+' (orden de presentación no verificado)','\n'.join(t.text or '' for t in xml(n).findall('.//a:t',ns))))
                omitted+=max(0,units-200);warnings.append('Solo texto de partes slideN; su número interno puede no coincidir con el orden mostrado. No imágenes, notas del presentador ni animaciones.')
    status='texto_extraido' if segments and not omitted and read==units else 'extraccion_parcial' if segments else 'recibido_sin_texto'
    return {'status':status,'segments':segments,'units':units,'read_units':read,'omitted':omitted,'characters':total,'warnings':list(dict.fromkeys(warnings))}

def _material_number(value):
    m=re.fullmatch(r'D(\d{1,9})',str(value or ''))
    return int(m.group(1)) if m else 0

def _next_material_ref(p):
    """Monotonic D# refs: reusing a retired ref would make old citations point
    at a different file. Non-numeric legacy refs must not crash an import."""
    items=p.get('materials',[])
    highest=max([_material_number(m.get('ref','')) for m in items if isinstance(m,dict)]+[0])
    stored=p.get('material_seq',0)
    stored=stored if type(stored) is int and 0<=stored<=10**9 else 0
    value=max(stored,highest)+1
    p['material_seq']=value
    return 'D'+str(value)

def import_file(root,p,path,role,native=None):
    safe_id(p['id']);path=Path(path)
    if role not in ROLES or path.suffix.lower() not in FORMATS:raise ValueError('Tipo de material no admitido.')
    if not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('Archivo inexistente o superior a 20 MB.')
    raw=path.read_bytes()
    if len(raw)>MAX_BYTES:raise ValueError('Archivo superior a 20 MB.')
    digest=hashlib.sha256(raw).hexdigest()
    existing=next((m for m in p.get('materials',[]) if m['sha256']==digest and m['role']==role and m.get('active')),None)
    if existing:return existing,None
    if len(p.get('materials',[]))>=30:raise ValueError('Máximo 30 archivos/versiones por proyecto.')
    id=uuid.uuid4().hex;folder=Path(root)/'materials'/p['id']/id;folder.mkdir(parents=True)
    target=folder/('original'+path.suffix.lower());target.write_bytes(raw)
    if os.name=='nt':
        try:
            with open(str(path)+':Zone.Identifier','rb') as f:zone=f.read(16385)
        except FileNotFoundError:zone=None
        if zone is not None:
            if len(zone)>16384:raise ValueError('Marca de seguridad de archivo inesperada; no se eliminó para abrirlo.')
            with open(str(target)+':Zone.Identifier','wb') as f:f.write(zone)
    try:
        if path.suffix.lower()=='.docx':
            with zipfile.ZipFile(target) as z:
                infos=z.infolist()
                if len(infos)>3000 or sum(i.file_size for i in infos)>60*1024*1024 or any(i.file_size>12*1024*1024 for i in infos):raise ValueError('DOCX demasiado grande al descomprimir; no se abrió en Word.')
            data=extract(target,native)
        else:
            r=subprocess.run([sys.executable,'-S',str(Path(__file__).with_name('material_worker.py'))],input=json.dumps({'path':str(target)}).encode(),capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            data=json.loads(r.stdout.decode('utf-8'))
            if 'error' in data:raise ValueError(data['error'])
            if r.stderr.strip():data['warnings'].append('El lector emitió advertencias técnicas; verifica legibilidad y cobertura del texto extraído.')
    except Exception as e:data={'status':'error_lectura','segments':[],'units':0,'read_units':0,'characters':0,'omitted':0,'warnings':['No se leyó el archivo: '+str(e)[:300]]}
    (folder/'extracted.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    record={'id':id,'ref':_next_material_ref(p),'name':path.name[:180],'role':role,'sha256':digest,'suffix':path.suffix.lower(),'bytes':len(raw),'status':data['status'],'characters':data['characters'],'units':data['units'],'read_units':data['read_units'],'warnings':data['warnings'],'shared_routes':[],'active':True,'created':now(),'version':1+sum(m['name']==path.name[:180] for m in p.get('materials',[]))}
    return record,data

def attach(p,record):
    if any(m['id']==record['id'] for m in p.get('materials',[])):return
    for m in p.get('materials',[]):
        if m['name']==record['name'] and m['role']==record['role']:
            m['active']=False
            from conversation_state import flag_rebind
            flag_rebind(p,'Nueva versión de '+record['name']+': el chat remoto ya contiene extractos de la versión anterior; revocar no borra esa memoria.')
    p.setdefault('materials',[]).append(record)
    if record['role']=='guia':
        for q in p['questions']:
            if q['key']=='guia' and q['status']=='abierta':q.update(status='respondida',answered_by=record['ref'],answered_at=now())

def content(root,p,m):
    folder=Path(root)/'materials'/safe_id(p['id'])/safe_id(m['id'])
    if m['suffix'] not in FORMATS:raise ValueError('Formato de biblioteca inválido.')
    original=folder/('original'+m['suffix'])
    if original.stat().st_size>MAX_BYTES or hashlib.sha256(original.read_bytes()).hexdigest()!=m['sha256']:raise ValueError('La copia original cambió fuera de Nexo; importa una versión nueva antes de usarla.')
    path=folder/'extracted.json'
    if path.stat().st_size>2_000_000:raise ValueError('Extracción demasiado grande.')
    return json.loads(path.read_text('utf-8'))

def scopes(api):
    if hasattr(api,'routes'):
        return [json.dumps([r['provider'],r['model'],r['endpoint'],r['account_id'],api.config.data['accounts'].get(r['account_id'],{}).get('generation','')]) for r in api.routes]
    return [json.dumps([api.provider,api.model,getattr(api,'endpoint','')])]

def select(root,p,query,route_scopes,budget=6000):
    words=set(re.findall(r'\w{4,}',query.lower()));ranked=[];explicit=set(re.findall(r'\bD\d+\b',query.upper()))
    for m in p.get('materials',[]):
        if not m.get('active') or not route_scopes or not set(route_scopes)<=set(m.get('shared_routes',[])):continue
        try:data=content(root,p,m)
        except (OSError,ValueError,UnicodeError,KeyError,TypeError):continue
        segments=data.get('segments') if isinstance(data,dict) else None
        if not isinstance(segments,list):continue  # damaged extracted.json must not abort a turn
        for i,seg in enumerate(segments):
            if not isinstance(seg,dict) or not isinstance(seg.get('text'),str) or not isinstance(seg.get('locator'),str):continue
            score=(100 if m.get('ref') in explicit else 0)+len(words & set(re.findall(r'\w{4,}',seg['text'].lower())))+(3 if m.get('role')=='guia' else 0)
            ranked.append((score,-i,m,seg))
    ranked.sort(key=lambda x:(x[0],x[1]),reverse=True);out=[]
    for _,_,m,seg in ranked:
        if len(out)>=6:break
        if len(seg['text'])>budget:continue
        out.append({'id':m.get('ref',''),'name':m.get('name',''),'role':m.get('role',''),'version':m.get('version',1),'locator':seg['locator'],'text':seg['text'],'scope':'extracto local; original no subido a Copilot'});budget-=len(seg['text'])
    return out
