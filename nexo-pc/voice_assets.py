"""Automatic, bounded discovery of the local Spanish model. No disk-wide scan."""
from pathlib import Path

MODEL_NAME='vosk-model-small-es-0.42'
MODEL_URL='https://alphacephei.com/vosk/models/'+MODEL_NAME+'.zip'
MODEL_SHA256='09b239888f633ef2f0b4e09736e3d9936acfd810bc65d53fad45261762c6511f'
DEFAULT_MODEL=Path.home()/'.nexo-pc'/'speech-models'/MODEL_NAME
REQUIRED_MODEL_FILES=('am/final.mdl','conf/model.conf','conf/mfcc.conf','graph/Gr.fst','graph/HCLr.fst',
 'graph/phones/word_boundary.int','ivector/final.dubm','ivector/final.ie','ivector/final.mat',
 'ivector/global_cmvn.stats','ivector/splice.conf','ivector/online_cmvn.conf')

def valid_model(path):
    try:return all((Path(path)/name).is_file() and (Path(path)/name).stat().st_size>0 for name in REQUIRED_MODEL_FILES)
    except (OSError,ValueError,TypeError):return False

def locations(preferred='',home=None,root=None):
    home=Path(home) if home is not None else Path.home()
    root=Path(root) if root is not None else Path(__file__).resolve().parent
    paths=[]
    if preferred:
        p=Path(preferred).expanduser();paths.append(p)
        if p.name=='am':paths.append(p.parent)
    paths.extend([home/'.nexo-pc'/'speech-models'/MODEL_NAME,root/'models',root/'speech-models',root,
                  home/'Downloads'/MODEL_NAME,home/'Desktop'/MODEL_NAME])
    seen=set()
    for p in paths:
        for candidate in (p,p/MODEL_NAME,p/MODEL_NAME/MODEL_NAME):
            key=str(candidate)
            if key not in seen:seen.add(key);yield candidate

def find_model(preferred='',home=None,root=None):
    return next((p.resolve() for p in locations(preferred,home,root) if valid_model(p)),None)

def bundled_archive(root=None):
    return (Path(root) if root is not None else Path(__file__).resolve().parent)/'models'/(MODEL_NAME+'.zip')

def ensure_model(preferred='',home=None,root=None,allow_download=False,repair=False):
    """Prepare data only. Does not install packages, change permissions or record.
    Automatic UI use is strictly offline. The explicit CLI may allow downloading.
    """
    home=Path(home) if home is not None else Path.home()
    found=find_model(preferred,home,root)
    if found and not repair:return found
    archive=bundled_archive(root)
    if not archive.is_file():
        downloaded=home/'Downloads'/(MODEL_NAME+'.zip')
        if downloaded.is_file():archive=downloaded
    if not archive.is_file() and not allow_download:
        raise RuntimeError('Falta models/'+MODEL_NAME+'.zip. Extrae y copia TODO el paquete 0.5.0, incluida la carpeta models. No tienes que seleccionar una carpeta de voz. No se descargó nada.')
    from prepare_voice import install
    destination=home/'.nexo-pc'/'speech-models'/MODEL_NAME
    install(destination,archive if archive.is_file() else None,repair=repair)
    if not valid_model(destination):raise RuntimeError('No se pudo verificar el modelo preparado; se conservó cualquier copia anterior.')
    return destination.resolve()
