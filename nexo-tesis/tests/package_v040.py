import hashlib,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parent.parent
with zipfile.ZipFile('/home/user/nexo-tesis-v0.3.1-windows.zip') as z:
    paths=[n.split('/',1)[1] for n in z.namelist() if not n.endswith('/') and not n.endswith('/SHA256SUMS.txt')]
paths+=['materials.py','material_worker.py','material_word.ps1','native_material.py','material_dialog.py','guide_rules.py','prompt_policy.py','context_policy.py','conversation_state.py','copilot_metadata.py']
paths += [str(p.relative_to(root)) for p in (root/'pypdf').rglob('*.py')]+['pypdf/LICENSE']
paths=sorted(set(paths));assert all((root/p).is_file() for p in paths)
assert not any(p.startswith(('tests/','reports/')) or '__pycache__' in p for p in paths)
assert [p for p in paths if p.lower().endswith('.md')]==['README.md']
(root/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256((root/p).read_bytes()).hexdigest()+'  '+p+'\n' for p in paths))
paths.append('SHA256SUMS.txt');dest=Path('/home/user/nexo-tesis-v0.4.0-windows.zip')
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in paths:z.write(root/p,'Nexo-Tesis-0.4.0/'+p)
with zipfile.ZipFile(dest) as z:
    assert z.testzip() is None
    for p in paths:assert z.read('Nexo-Tesis-0.4.0/'+p)==(root/p).read_bytes()
result={'file':str(dest),'files':len(paths),'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'crc_checked':True,'source_equality_checked':True,'runtime_only':True}
(root/'reports/package-v040.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
