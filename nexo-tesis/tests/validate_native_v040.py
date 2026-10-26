import hashlib,json,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from guide_rules import proposals,approve
from test_v030 import state
from word_layout import build_plan,preview
from word_bridge import encoded_native_command
PW='/home/user/.cache/pwsh-7.4.6/pwsh';checks=[]
guide='Arial 11\nInterlineado 1.5\nTítulos 14\nSubtítulos 13\nMárgenes 3 cm\nPapel A4'
p={'id':'test','revision':1,'facts':{'guia':{'value':guide}},'drafts':{'objetivos':{'text':'Texto concreto.','status':'borrador'}}};r=proposals([{'text':guide,'locator':'Memoria'}]);approve(p,{'id':'memoria-guia','sha256':hashlib.sha256(guide.encode()).hexdigest(),'name':'Requisitos'},r,range(len(r)))
st=state('');plan=build_plan(st,p,['objetivos'],format_all=False,index=False)
assert plan['format_profile']['effective']['spacing']==1.5;checks.append('Python plan carries reviewed guide rather than generic APA defaults')
for bad in (False,True):
    payload={'text':'\r','state':st,'request':{'action':'layout','approved':True,'operation':uuid.uuid4().hex,'plan':plan}}
    if bad:plan['format_profile']['effective']['font']='Unsupported'
    proc=subprocess.run([PW,'-NoProfile','-NonInteractive','-File',str(ROOT/'tests/native/layout_mock.ps1'),'-Helper',str(ROOT/'word_layout.ps1')],input=json.dumps(payload,ensure_ascii=False).encode(),capture_output=True,timeout=30)
    result=json.loads(proc.stdout.decode('utf-8-sig'));assert proc.returncode==0,proc.stderr
    if bad:assert 'error' in result and result['text']=='\r';checks.append('Unsupported native profile rejected before text mutation')
    else:
        assert 'error' not in result,result
        headings=[r for r in result['ranges'] if r['outline']==1];bodies=[r for r in result['ranges'] if r['outline']==10]
        assert headings and all(r['font']=='Arial' and r['size']==14 and r['spacing']==1 for r in headings),result
        assert bodies and all(r['font']=='Arial' and r['size']==11 and r['spacing']==1 for r in bodies),result
        checks.append('Production PowerShell applies approved font, body/title sizes and 1.5 spacing to range doubles')
# Page setup uses the real production function with a small PowerShell object double.
script='''param([string]$Helper)
$ErrorActionPreference='Stop'
. $Helper
$pg=[pscustomobject]@{PaperSize=2;TopMargin=0;BottomMargin=0;LeftMargin=0;RightMargin=0;Gutter=0;HeaderDistance=0}
$doc=[pscustomobject]@{Sections=@([pscustomobject]@{PageSetup=$pg;Headers=@();Footers=@()})}
$word=New-Object PSObject
$word | Add-Member ScriptMethod CentimetersToPoints {param($n) $n*28.3464567}
Set-NexoFormat ([pscustomobject]@{effective=[pscustomobject]@{page_size='A4';font='Arial';body_size=11;heading_size=14;subheading_size=13;spacing=1.5;margin_cm=3;alignment='izquierda'}})
Format-NexoDocument $doc ([pscustomobject]@{paragraphs=@();tocs=@();page_number_present=$true}) ([pscustomobject]@{headings=@();body_start=0})
$pg | ConvertTo-Json -Compress
'''
# Keep this development-only fixture outside the runtime package.
f=ROOT/'tests/native/profile_mock.ps1';f.write_text(script)
proc=subprocess.run([PW,'-NoProfile','-NonInteractive','-File',str(f),'-Helper',str(ROOT/'word_layout.ps1')],capture_output=True,timeout=30)
result=json.loads(proc.stdout.decode('utf-8-sig'));assert result['PaperSize']==7 and abs(result['TopMargin']-85.03937)<.001;checks.append('Production page setup selects A4 and approved margins on page-setup double')
# Parse every runtime script, including material reader and trusted encoded loader.
parse="$errors=@(); Get-ChildItem -Path . -Filter *.ps1 | ForEach-Object {$tokens=$null;$e=$null;[void][Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$e);$errors+=@($e)}; if ($errors.Count) {$errors|Format-List;exit 1}; 'Parser OK'"
proc=subprocess.run([PW,'-NoProfile','-NonInteractive','-Command',parse],capture_output=True,timeout=30);assert proc.returncode==0,proc.stdout+proc.stderr;checks.append('All runtime PowerShell scripts parse with PowerShell 7.4.6')
encoded=encoded_native_command();assert len(encoded)<31000
proc=subprocess.run([PW,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],input=b'{"action":"invalid","approved":false}',capture_output=True,timeout=30);assert 'error' in json.loads(proc.stdout.decode('utf-8-sig'));checks.append('Compressed trusted loader executes and refuses unapproved operation without Word')
report={'passed':len(checks),'checks':checks,'encoded_chars':len(encoded),'real_word_com':False,'windows_powershell_5_1':False};Path('reports/native-v040.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
