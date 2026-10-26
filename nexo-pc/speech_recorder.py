"""Isolated local microphone worker. Starts PAUSED; never stores audio on disk."""
import argparse
import json
from pathlib import Path
import queue
import sys
import threading


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);args=parser.parse_args()
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    lock=threading.Lock();state={'pause':True,'epoch':0,'stop':False}
    output_lock=threading.Lock()
    def emit(kind,**data):
        with output_lock:print(json.dumps({'type':kind,**data},ensure_ascii=False),flush=True)
    def commands():
        for line in sys.stdin:
            try:request=json.loads(line)
            except ValueError:continue
            if isinstance(request,dict) and isinstance(request.get('pause'),bool) and type(request.get('epoch')) is int:
                with lock:state.update(pause=request['pause'],epoch=request['epoch'])
        with lock:state['stop']=True
    def snapshot():
        with lock:return dict(state)
    threading.Thread(target=commands,daemon=True).start()
    stage='modelo'
    try:
        if not (Path(args.model)/'am'/'final.mdl').is_file():raise RuntimeError('No se encontró el modelo local de español. Pulsa Comprobar / reparar modelo incluido en Ajustes → Voz.')
        stage='componentes'
        try:
            import sounddevice as sd
            import vosk
        except ImportError:raise RuntimeError('Faltan los componentes opcionales. Cierra Nexo y ejecuta instalar-VOZ.cmd.') from None
        stage='modelo'
        vosk.SetLogLevel(-1);model=vosk.Model(args.model)
        emit('ready')
        idle=threading.Event()
        while not snapshot()['stop']:
            if snapshot()['pause']:idle.wait(.08);continue
            stage='microfono'
            info=sd.query_devices(None,'input');rate=int(info['default_samplerate'])
            recognizer=vosk.KaldiRecognizer(model,rate);recognizer.SetWords(True)
            audio=queue.Queue(maxsize=40);overrun=threading.Event();epoch=snapshot()['epoch'];last_partial=''
            def capture(indata,frames,time_info,status):
                current=snapshot()
                if current['pause'] or current['epoch']!=epoch:return
                if status:overrun.set();return
                try:audio.put_nowait(bytes(indata))
                except queue.Full:overrun.set()
            with sd.RawInputStream(samplerate=rate,blocksize=max(1,rate//8),device=None,dtype='int16',channels=1,callback=capture):
                emit('listening',epoch=epoch)
                while True:
                    current=snapshot()
                    if current['stop'] or current['pause'] or current['epoch']!=epoch:break
                    if overrun.is_set():raise RuntimeError('Se perdió audio del micrófono. La escucha se detuvo para no enviar una transcripción incompleta. Revisa el dispositivo o la carga del equipo.')
                    try:data=audio.get(timeout=.1)
                    except queue.Empty:continue
                    if recognizer.AcceptWaveform(data):
                        result=json.loads(recognizer.Result());text=result.get('text','').strip();words=result.get('result',[])
                        confidence=sum(float(w.get('conf',0)) for w in words)/len(words) if words else 0
                        current=snapshot()
                        if text and not current['pause'] and current['epoch']==epoch:emit('final',text=text,confidence=confidence,epoch=epoch)
                        last_partial=''
                    else:
                        partial=json.loads(recognizer.PartialResult()).get('partial','')
                        if partial:
                            emit('partial',epoch=epoch);last_partial=partial
            # Closing the stream releases the microphone; stale audio is discarded.
            emit('paused')
    except Exception as e:
        hint={'modelo':' Pulsa Comprobar / reparar modelo incluido en Ajustes → Voz.','componentes':' Cierra Nexo y ejecuta instalar-VOZ.cmd; esta etapa no usa el micrófono.','microfono':' Revisa el dispositivo predeterminado y el permiso de micrófono para aplicaciones de escritorio en Windows.'}
        emit('error',text=str(e)+hint[stage])
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
