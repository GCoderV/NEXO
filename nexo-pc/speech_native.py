"""Windows installed voices via PyWinRT; plain text only, no network service.
Separate process so Stop can terminate synthesis/playback reliably.
"""
import asyncio
import json
import os
import sys

async def native(mode,payload):
    if os.name!='nt':raise RuntimeError('Las voces nativas requieren Windows.')
    try:
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer
        from winrt.windows.media.playback import MediaPlayer, MediaPlayerAudioCategory
        # These projections are needed for streams and vector views at runtime.
        import winrt.windows.foundation
        import winrt.windows.foundation.collections
        import winrt.windows.storage.streams
    except ImportError:raise RuntimeError('Faltan los componentes de voz. Cierra Nexo y ejecuta instalar-VOZ.cmd.') from None
    voices=list(SpeechSynthesizer.all_voices)
    if mode=='voices':return {'ok':True,'voices':[{'id':v.id,'name':v.display_name,'language':v.language} for v in voices]}
    text=payload.get('text','');language=payload.get('language','es-MX');voice_id=payload.get('voice_id','');rate=payload.get('rate',1.0)
    if not isinstance(text,str) or not text.strip() or len(text)>12000:raise ValueError('Texto de lectura inválido; máximo 12 000 caracteres.')
    if type(rate) not in (float,int) or not .5<=rate<=2:raise ValueError('Velocidad de voz inválida.')
    matches=[v for v in voices if (v.id==voice_id if voice_id else v.language.lower()==language.lower())]
    if not matches:
        raise RuntimeError('No se encontró la voz elegida ('+str(language)+'). Instala una voz de español (México) en Windows o elige otra voz instalada en Ajustes → Voz. No se cambiará de idioma automáticamente.')
    synth=SpeechSynthesizer();synth.voice=matches[0];synth.options.speaking_rate=float(rate)
    player=None;stream=None;tokens=[]
    try:
        stream=await asyncio.wait_for(synth.synthesize_text_to_stream_async(text),timeout=90)
        player=MediaPlayer();player.audio_category=MediaPlayerAudioCategory.SPEECH
        ended=asyncio.Event();loop=asyncio.get_running_loop();errors=[]
        def finish(sender,args):loop.call_soon_threadsafe(ended.set)
        def fail(sender,args):
            errors.append(str(args.error_message));loop.call_soon_threadsafe(ended.set)
        tokens=[player.add_media_ended(finish),player.add_media_failed(fail)]
        player.set_stream_source(stream);player.play();await ended.wait()
        if errors:raise RuntimeError('No se pudo reproducir: '+'; '.join(errors))
        return {'ok':True,'language':matches[0].language,'voice':matches[0].display_name}
    finally:
        if player:
            player.pause()
            if tokens:player.remove_media_ended(tokens[0]);player.remove_media_failed(tokens[1])
            player.close()
        if stream:stream.close()
        synth.close()

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stdin,'reconfigure'):sys.stdin.reconfigure(encoding='utf-8')
    try:
        if len(sys.argv)!=2 or sys.argv[1] not in ('voices','speak'):raise ValueError('Modo de voz inválido.')
        payload=json.loads(sys.stdin.read(100000)) if sys.argv[1]=='speak' else {}
        result=asyncio.run(native(sys.argv[1],payload))
    except Exception as e:result={'ok':False,'error':str(e)}
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result.get('ok') else 1

if __name__=='__main__':raise SystemExit(main())
