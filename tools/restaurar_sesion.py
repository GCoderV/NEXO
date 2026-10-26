"""Restore historical workspace layout only on explicit --aplicar; never installs."""
import argparse,hashlib,shutil
from pathlib import Path
from verificar_respaldo import ROOT,verify

def digest(p):return hashlib.sha256(p.read_bytes()).digest()
def main():
    a=argparse.ArgumentParser();a.add_argument('--destino',type=Path,default=Path('/home/user'));a.add_argument('--aplicar',action='store_true');args=a.parse_args()
    verify();target=args.destino.expanduser().resolve();pairs=[]
    for component in ('nexo-pc','nexo-tesis','rea-arena','rea-setup','.agents/skills/reverse-engineer-anything'):
        for src in (ROOT/component).rglob('*'):
            if src.is_file() and '__pycache__' not in src.parts:pairs.append((src,target/src.relative_to(ROOT)))
    for src in (ROOT/'releases').glob('*.zip'):pairs.append((src,target/src.name))
    conflicts=[];pending=[]
    for src,dst in pairs:
        if not dst.resolve().is_relative_to(target):raise SystemExit('Destino fuera de la raíz elegida.')
        if dst.exists():
            if not dst.is_file() or digest(src)!=digest(dst):conflicts.append(str(dst))
        else:pending.append((src,dst))
    print('Destino:',target,'| Nuevos archivos:',len(pending),'| Conflictos:',len(conflicts))
    if conflicts:raise SystemExit('No se sobrescribirá. Usa una raíz vacía o revisa: '+', '.join(conflicts[:8]))
    if not args.aplicar:print('Solo plan. Usa --aplicar para copiar; no se instalarán dependencias.');return
    for src,dst in pending:dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    print('Copia terminada. Lee CONTINUAR-EN-ARENA.md. No se conectó a Microsoft/GitHub ni se instaló software.')
if __name__=='__main__':main()
