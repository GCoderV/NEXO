import ast,json,sys,tempfile,zipfile
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent.parent),str(Path(__file__).resolve().parent)]
from project_store import ProjectStore,set_fact,SECTIONS,FACT_KEYS,now,message
from agent import context,SYSTEM
from prompt_policy import instructions
with zipfile.ZipFile('/home/user/nexo-tesis-v0.3.1-windows.zip') as z:old_source=z.read('Nexo-Tesis-0.3.1/agent.py').decode()
old={};exec(compile(old_source,'old_release_agent','exec'),old)
with tempfile.TemporaryDirectory() as t:
    p=ProjectStore(t).create('Producción oral en inglés mediante actividades cooperativas')
    for k in FACT_KEYS:set_fact(p,k,{'nivel':'grado','institucion':'Institución de prueba','tipo_trabajo':'anteproyecto','metodologia':'investigación-acción','poblacion':'24 estudiantes','datos':'Diagnóstico aportado; no resultados de intervención','guia':'Times New Roman 12; interlineado 1.5'}.get(k,'Información aportada en una prueba sintética'))
    for i,k in enumerate(FACT_KEYS):p['questions'].append({'id':'question'+str(i),'key':k,'text':'Pregunta anterior sobre '+k,'status':'respondida','time':now()})
    for i in range(15):p['sources'].append({'id':'F'+str(i+1),'title':('Oral production and cooperative learning' if i<4 else 'Unrelated bibliographic topic')+' '+str(i),'authors':'Autor de prueba','year':'2024','status':'solo metadatos y resumen','url':'https://example.org/'+str(i),'excerpt':('Abstract metadata for the synthetic benchmark, not actual research evidence. '*18),'locator':'abstract','doi':'','time':now()})
    for k in ('delimitacion','problematica','pregunta','objetivos','justificacion','marco_teorico','metodologia','instrumentos'):p['drafts'][k]={'text':('Texto de borrador sintético; conserva pendientes, no constituye evidencia. '*24),'status':'borrador','warning':'Revisar','sources':[]}
    for i in range(8):message(p,'assistant','Mensaje sintético de continuidad. '*20)
    task={'section':'metodologia','label':'Metodología','mode':'revisar','previous_text':p['drafts']['metodologia']['text'],'instruction':'Revisa el apartado con contenido concreto.'}
    records=[]
    for label,order in [('dialogue',None),('draft_revision',task)]:
        text='Revisa la metodología y conserva los datos aportados.'
        before=old['context'](p,text,False,'','usuario',order);after=context(p,text,False,'','usuario',order)
        b=len(old['SYSTEM'])+len(before);a=len(instructions(order))+len(after)
        records.append({'case':label,'old_instruction_characters':len(old['SYSTEM']),'new_instruction_characters':len(instructions(order)),'old_context_characters':len(before),'new_context_characters':len(after),'old_total_characters':b,'new_total_characters':a,'reduction_percent':round((1-a/b)*100,2)})
    report={'fixture':'synthetic 11 known facts, 11 answered questions, 15 sources, 8 drafts, 8 messages; no actual user content','comparison':'0.3.1 delivered source vs 0.4.0','measure':'Unicode characters, not tokens or cost; not a quality benchmark','cases':records}
Path('reports/context-v040.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
