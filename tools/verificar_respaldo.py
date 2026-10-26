"""Read-only integrity check; no network, imports of app code, or installations."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def verify():
    failures=[];count=0
    for line in (ROOT/'SHA256SUMS.txt').read_text('utf-8').splitlines():
        expected,name=line.split('  ',1);path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT):raise SystemExit('Ruta fuera del respaldo.')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:failures.append(name)
        count+=1
    if failures:raise SystemExit('No coincide: '+', '.join(failures))
    print(f'Integridad comprobada: {count} archivos. No acredita funcionamiento de Word/Copilot.')
    return count
if __name__=='__main__':verify()
