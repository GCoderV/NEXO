"""Explicit installer for the optional, pinned Spanish Vosk data model."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.request
import zipfile
import uuid
from voice_assets import MODEL_NAME, MODEL_URL, MODEL_SHA256, DEFAULT_MODEL, valid_model, bundled_archive


def validate_archive(archive):
    infos=archive.infolist()
    if len(infos)>1000 or sum(i.file_size for i in infos)>200_000_000:raise ValueError('Modelo demasiado grande.')
    for item in infos:
        name=PurePosixPath(item.filename)
        if (name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0]!=MODEL_NAME
            or '\\' in item.filename or ':' in item.filename or stat.S_ISLNK(item.external_attr>>16)):
            raise ValueError('Ruta insegura dentro del modelo.')
    if MODEL_NAME+'/am/final.mdl' not in archive.namelist():raise ValueError('El ZIP no contiene el modelo esperado.')


def install(destination=DEFAULT_MODEL,archive_path=None,repair=False):
    destination=Path(destination)
    if valid_model(destination) and not repair:return 'El modelo ya existe; no se modificó.'
    if archive_path is None and bundled_archive().is_file():archive_path=bundled_archive()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.nexo-voz-',dir=destination.parent) as temp:
        temp=Path(temp);archive=temp/'model.zip'
        if archive_path:shutil.copyfile(archive_path,archive)
        else:
            request=urllib.request.Request(MODEL_URL,headers={'User-Agent':'NexoPC/0.4'})
            with urllib.request.urlopen(request,timeout=120) as response,archive.open('wb') as output:
                total=0
                while block:=response.read(1024*1024):
                    total+=len(block)
                    if total>60_000_000:raise RuntimeError('La descarga superó el tamaño previsto.')
                    output.write(block)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=MODEL_SHA256:
            raise RuntimeError('El SHA-256 del modelo no coincide. No se instaló; no desactives esta comprobación.')
        extracted=temp/'extracted';extracted.mkdir()
        with zipfile.ZipFile(archive) as z:
            validate_archive(z);z.extractall(extracted)
        if not valid_model(extracted/MODEL_NAME):raise ValueError('El modelo extraído está incompleto.')
        backup=None
        if destination.exists():
            backup=destination.with_name(destination.name+'-respaldo-'+uuid.uuid4().hex[:8])
            destination.rename(backup)
        try:os.replace(extracted/MODEL_NAME,destination)
        except OSError:
            if backup and not destination.exists():backup.rename(destination)
            raise
    return 'Modelo local instalado. Puedes abrir Nexo y activar Mic.'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--yes',action='store_true');args=parser.parse_args()
    if not args.yes:
        print('Preparará el modelo incluido; solo si falta lo descargará (40 MB de alphacephei.com). No modifica permisos de Windows.')
        if input('¿Continuar? [s/N] ').strip().lower() not in ('s','si','sí'):raise SystemExit(0)
    try:print(install())
    except Exception as e:print('No se instaló:',e);raise SystemExit(1)
