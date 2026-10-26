"""Execution of production PS insertion/preflight with a text-range double, not Office."""
import json,subprocess,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent));sys.path.insert(0,str(Path(__file__).resolve().parent))
from word_layout import build_plan
from test_v030 import state
ROOT=Path(__file__).resolve().parent.parent
PW='/home/user/.cache/pwsh-7.4.6/pwsh'
checks=[]
def execute(texts,drafts,expected,stale=False):
    st=state(*texts);p={'id':'test','revision':1,'data_ready':True,'drafts':{k:{'text':v,'status':'borrador'} for k,v in drafts.items()}}
    plan=build_plan(st,p,list(drafts),format_all=False,index=False);raw='\r'.join(texts)+'\r'
    if stale:plan['snapshot']['hash']='0'*64
    request={'action':'layout','approved':True,'operation':uuid.uuid4().hex,'plan':plan}
    payload=json.dumps({'text':raw,'state':st,'request':request},ensure_ascii=False).encode()
    out=subprocess.run([PW,'-NoProfile','-NonInteractive','-File',str(ROOT/'tests/native/layout_mock.ps1'),'-Helper',str(ROOT/'word_layout.ps1')],input=payload,capture_output=True,timeout=30)
    if out.stderr:print(out.stderr.decode())
    result=json.loads(out.stdout.decode('utf-8-sig'))
    assert result['text']==expected,(result,expected)
    assert result['tracking'] is False and result['formatting'] is False,result
    if stale:assert 'cambio desde' in result['error'];checks.append('stale text fingerprint rejects before mutation')
    else:
        assert 'error' not in result,result;assert result['result']['text_verified'] is True
        assert len(result['markers'])==len(drafts);checks.append('PS insertion: '+repr(expected))
        assert all(r['outline'] in (1,2,3,10) for r in result['ranges'])
execute(['Objetivos','Original'],{'objetivos':'Nuevo'},'Objetivos\rOriginal\rNuevo\r')
execute(['Objetivos','Original',''],{'objetivos':'Nuevo'},'Objetivos\rOriginal\rNuevo\r')
execute([''],{'objetivos':'Objetivo nuevo','metodologia':'Método nuevo'},'Objetivos\rObjetivo nuevo\rMetodología\rMétodo nuevo\r')
execute(['Objetivos','Original'],{'objetivos':'Ampliación','metodologia':'Método','referencias':'Apellido. *Título*.'},'Objetivos\rOriginal\rAmpliación\rMetodología\rMétodo\rReferencias\rApellido. Título.\r')
execute(['Objetivos','Original','Metodología','Método'],{'objetivos':'😀 **Lectura**'},'Objetivos\rOriginal\r😀 Lectura\rMetodología\rMétodo\r')
execute(['Objetivos','Original'],{'objetivos':'Nuevo'},'Objetivos\rOriginal\r',True)
snapshots=[]
for _ in range(2):
    out=subprocess.run([PW,'-NoProfile','-NonInteractive','-File',str(ROOT/'tests/native/state_mock.ps1'),'-Root',str(ROOT)],capture_output=True,timeout=30)
    assert out.returncode==0,out.stderr;snapshots.append(json.loads(out.stdout.decode('utf-8-sig')))
from word_layout import validate_state
validate_state(snapshots[0],snapshots[0]['path']);assert len(snapshots[0]['paragraphs'])==2
checks.append('production native snapshot function returns valid bounded JSON with a paragraph DOUBLE')
assert snapshots[0]['structure_hash']==snapshots[1]['structure_hash']
checks.append('ordered snapshot structure hash stable across two real PowerShell processes')
Path('reports/native-layout-v030.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'word_com':False,'note':'production PS insertion and preflight executed with a custom range/text DOUBLE, not Microsoft Word'},indent=2))
print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
