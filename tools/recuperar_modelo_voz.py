"""Optional voice data restoration from pinned official artifact; no package install."""
import argparse,hashlib,os,tempfile,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
NAME='vosk-model-small-es-0.42.zip'
URL='https://alphacephei.com/vosk/models/'+NAME
SHA='09b239888f633ef2f0b4e09736e3d9936acfd810bc65d53fad45261762c6511f'
def main():
    p=argparse.ArgumentParser();p.add_argument('--descargar',action='store_true');a=p.parse_args()
    dst=ROOT/'nexo-pc/models'/NAME
    print('URL oficial:',URL,'\nSHA256 esperado:',SHA,'\nDestino:',dst)
    if dst.exists():
        if hashlib.sha256(dst.read_bytes()).hexdigest()!=SHA:raise SystemExit('Archivo existente distinto: no se reemplaza.')
        print('El modelo ya está íntegro.');return
    if not a.descargar:print('Sin descargas. --descargar autoriza obtener solo estos datos; no instala software.');return
    dst.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=dst.parent,suffix='.partial');h=hashlib.sha256();total=0;start=time.monotonic()
    try:
        with os.fdopen(fd,'wb') as out,urllib.request.urlopen(URL,timeout=30) as response:
            if not response.geturl().startswith('https://alphacephei.com/'):raise ValueError('Redirección no esperada.')
            while True:
                block=response.read(1024*1024)
                if not block:break
                total+=len(block)
                if total>60*1024*1024 or time.monotonic()-start>180:raise ValueError('Descarga excedió límites.')
                h.update(block);out.write(block)
        if h.hexdigest()!=SHA:raise ValueError('El modelo no coincide con la huella fijada; no se usará.')
        os.replace(tmp,dst);print('Modelo verificado. No se extrajo, activó el micrófono ni instaló bibliotecas.')
    finally:
        Path(tmp).unlink(missing_ok=True)
if __name__=='__main__':main()
