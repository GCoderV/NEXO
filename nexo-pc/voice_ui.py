"""Chat voice UX. All Tk access stays on the UI thread."""
import math
import os
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from voice_assets import find_model, ensure_model
from voice import DEFAULT_MODEL, VoiceFlow, Recorder, Speaker, native_voices, open_windows_dictation, command_of, process_has_foreground

class VoiceUIMixin:
    def setup_voice_ui(self,composer):
        p=self.settings.data['preferences']
        self.voice_preparing=False;self.voice_prepare_token=0;self.voice_prepare_activate=False
        self.voice_flow=VoiceFlow();self.voice_ready=False;self.voice_capturing=False;self.voice_speaking=False;self.voice_resume_at=0
        self.voice_auto=tk.BooleanVar(value=p.get('voice_auto_send',True));self.voice_delay=tk.DoubleVar(value=p.get('voice_delay',3.0))
        self.voice_read=tk.BooleanVar(value=p.get('voice_auto_read',True));self.voice_model=tk.StringVar(value=p.get('voice_model',str(DEFAULT_MODEL)))
        self.voice_language=tk.StringVar(value=p.get('voice_language','es-MX'));self.voice_id=tk.StringVar(value=p.get('voice_id',''))
        self.voice_rate=tk.DoubleVar(value=p.get('voice_rate',1.0));self.voice_choices={};self.voice_selected=tk.StringVar(value='Automática · '+self.voice_language.get())
        self.voice_settings_status=tk.StringVar(value='Micrófono apagado al iniciar. Audio local; el texto enviado usa el proveedor elegido.')
        self.voice_status=tk.StringVar(value='Voz apagada · clic derecho para copiar/pegar')
        self.recorder=Recorder(lambda token,event:self.events.put(('voice_input',token,event)))
        self.speaker=Speaker(lambda token,event:self.events.put(('voice_output',token,event)))
        self.voice_tts_failed=False;self.voice_last_answer='';self.voice_paused=True;self.native_notice=False;self.native_dictation=False
        row=ttk.Frame(composer);row.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(5,0))
        self.mic_button=ttk.Button(row,text='🎙 Mic',width=5,command=self.toggle_microphone);self.mic_button.pack(side='left')
        self.read_button=ttk.Button(row,text='🔊 Leer',width=6,command=self.toggle_read);self.read_button.pack(side='left',padx=4)
        self.paste_button=ttk.Button(row,text='Pegar',width=6,command=lambda:self.paste_text(self.input));self.paste_button.pack(side='left')
        self.native_button=ttk.Button(row,text='Dictado Windows',width=15,command=self.native_dictation_click);self.native_button.pack(side='right')
        self.voice_status_label=ttk.Label(composer,textvariable=self.voice_status,style='Muted.TLabel',wraplength=700)
        self.voice_status_label.grid(row=3,column=0,columnspan=2,sticky='w',pady=(4,0))
        self.input.bind('<KeyPress>',lambda e:self.voice_flow.cancel_pending(),add='+')
    def voice_preferences(self):
        delay=self.voice_delay.get();rate=self.voice_rate.get()
        if not 2<=delay<=10:raise ValueError('Pausa de dictado: entre 2 y 10 segundos.')
        if not .5<=rate<=2:raise ValueError('Velocidad de lectura: entre 0.5 y 2.')
        return {'voice_auto_send':self.voice_auto.get(),'voice_delay':delay,'voice_auto_read':self.voice_read.get(),
                'voice_model':self.voice_model.get(),'voice_language':self.voice_language.get(),'voice_id':self.voice_id.get(),'voice_rate':rate}
    def voice_foreground(self):
        try:
            focused=self.root.focus_get()
            return process_has_foreground() and self.root.state()!='iconic' and focused is not None and focused.winfo_toplevel() is self.root and not self.root.grab_current()
        except tk.TclError:return False
    def voice_allowed(self):
        return self.voice_flow.active and self.voice_ready and not self.busy and not self.pending and not self.voice_speaking and time.monotonic()>=self.voice_resume_at and self.voice_foreground()
    def toggle_microphone(self):
        if self.voice_preparing:
            self.voice_prepare_activate=False;self.voice_status.set('Preparando archivos locales; el micrófono seguirá apagado.');return
        if self.voice_flow.active:self.microphone_off();return
        if self.native_dictation:
            if not messagebox.askyesno('Cerrar primero el dictado de Windows','Cierra el panel Win+H y apaga su micrófono antes de activar el modo local. Nexo no puede verificar el estado de ese micrófono.\n\n¿Ya lo cerraste?',parent=self.root):return
            self.native_dictation=False;self.native_button.configure(text='Dictado Windows')
        model=find_model(self.voice_model.get())
        if model is None:
            self.prepare_voice_model(activate=True);return
        self.voice_model.set(str(model))
        try:self.settings.save_preferences({'voice_model':str(model)})
        except OSError:pass
        try:self.voice_preferences()
        except (ValueError,tk.TclError) as e:messagebox.showerror('Voz',str(e));return
        action=('Después de cada pausa, enviará automáticamente el texto al proveedor del chat. Esto puede iniciar acciones según el modo y permisos actuales.' if self.voice_auto.get() else 'El dictado quedará en el cuadro; di «Nexo enviar» o pulsa Enviar para mandarlo.')
        if self.input.get('1.0','end-1c').strip():action+=' Ya hay un borrador: el dictado se añadirá a ese texto.'
        if not messagebox.askyesno('Activar conversación por voz','Se usará el micrófono predeterminado mientras esta ventana esté activa. El audio se procesa localmente y no se guarda.\n\n'+action+'\n\nSe pausa mientras Nexo trabaja, lee, pide permisos o pierde el foco. No acepta aprobaciones de seguridad por voz. Pulsa el micrófono para apagarlo. ¿Activar?',parent=self.root):return
        self.voice_flow.enable();self.voice_ready=False;self.voice_capturing=False;self.voice_paused=True;self.voice_tts_failed=False
        self.mic_button.configure(text='■ Mic');self.voice_status.set('Preparando reconocimiento local…');self.input.focus_set()
        try:self.recorder.start(self.voice_model.get())
        except Exception as e:self.microphone_off();self.emit_ui('Voz',str(e))
    def prepare_voice_model(self,activate=False,repair=False):
        if self.voice_preparing:return
        # Stop workers before changing model files. Data is prepared offline from
        # the bundled, hash-pinned ZIP; no automatic pip or permission changes.
        self.microphone_off();self.voice_preparing=True;self.voice_prepare_activate=activate
        self.voice_prepare_token+=1;token=self.voice_prepare_token;preferred=self.voice_model.get()
        self.voice_status.set('Preparando modelo incluido… sin descargar ni abrir el micrófono')
        self.voice_settings_status.set('Preparando modelo español automáticamente…')
        def run():
            try:self.events.put(('voice_prepared',token,str(ensure_model(preferred,repair=repair)),None))
            except Exception as e:self.events.put(('voice_prepared',token,None,str(e)))
        threading.Thread(target=run,daemon=True).start()
    def voice_prepared_event(self,token,path,error):
        if token!=self.voice_prepare_token:return
        activate=self.voice_prepare_activate;self.voice_preparing=False;self.voice_prepare_activate=False
        if error:
            self.voice_status.set('No se pudo preparar el modelo');self.voice_settings_status.set(error);self.emit_ui('Voz',error);return
        self.voice_model.set(path)
        try:self.settings.save_preferences({'voice_model':path})
        except OSError:pass
        self.voice_status.set('Modelo listo · pulsa Mic para conversar');self.voice_settings_status.set('Modelo español listo; carpeta detectada automáticamente.')
        # Still asks for microphone/autosend consent; never starts while hidden,
        # busy or in a settings dialog. An earlier click can cancel activation.
        if activate and not self.busy and self.voice_foreground():self.toggle_microphone()
    def microphone_off(self):
        self.voice_prepare_activate=False
        self.voice_flow.disable();self.voice_ready=False;self.voice_capturing=False;self.recorder.stop();self.stop_read()
        self.mic_button.configure(text='🎙 Mic');self.voice_status.set('Win+H: cierra su micrófono desde Windows' if self.native_dictation else 'Voz apagada · el borrador no se envió')
    def voice_tick(self):
        allowed=self.voice_allowed()
        if not allowed and not self.voice_paused:self.voice_flow.cancel_pending()
        self.voice_paused=not allowed;self.recorder.pause(not allowed)
        if not allowed:self.voice_capturing=False
        if not self.voice_flow.active:return
        if self.voice_speaking:self.voice_status.set('Leyendo · micrófono en pausa')
        elif not self.voice_ready:self.voice_status.set('Preparando reconocimiento local…')
        elif not allowed:self.voice_status.set('En pausa · espera o vuelve al chat')
        elif self.voice_flow.review_required:self.voice_status.set('Baja confianza · revisa el texto y pulsa Enviar')
        elif self.voice_flow.deadline is not None:
            remaining=max(0,math.ceil(self.voice_flow.deadline-time.monotonic()))
            self.voice_status.set(f'Enviaré en {remaining} s · «Nexo cancelar» o apaga Mic')
        elif not self.voice_capturing:self.voice_status.set('Activando micrófono…')
        else:self.voice_status.set('Escuchando · «Nexo apagar micrófono» para salir')
        if self.voice_flow.take_due(allowed):self.start()
    def voice_event(self,token,event):
        if token!=self.recorder.token or not self.voice_flow.active:return
        kind=event.get('type')
        if kind=='error':
            self.microphone_off();self.emit_ui('Voz',event.get('text','No se pudo usar el micrófono.'));return
        if kind=='ready':self.voice_ready=True;return
        if kind=='paused':self.voice_capturing=False;return
        if kind=='listening':
            if event.get('epoch')==self.recorder.epoch:self.voice_capturing=True
            return
        if kind not in ('partial','final') or not self.voice_allowed() or event.get('epoch')!=self.recorder.epoch:return
        if kind=='partial':self.voice_flow.partial(self.voice_delay.get());return
        self.voice_capturing=True
        text=event.get('text','').strip()
        if not text:return
        confidence=event.get('confidence',0)
        if type(confidence) not in (int,float):confidence=0
        command=command_of(text) if confidence>=.65 else None
        if command=='off':self.microphone_off();return
        if command=='cancel':
            self.voice_flow.cancel_pending();self.voice_status.set('Envío cancelado · borrador conservado');return
        if command=='clear':self.input.delete('1.0','end');self.voice_flow.sent();return
        if command=='send':
            if not self.voice_flow.review_required:self.voice_flow.cancel_pending();self.start()
            return
        existing=self.input.get('1.0','end-1c')
        self.input.insert('end',(' ' if existing and not existing[-1].isspace() else '')+text);self.input.see('end')
        if len(self.input.get('1.0','end-1c'))>6000:
            self.microphone_off();self.emit_ui('Voz','El dictado superó 6000 caracteres. Se conservó el borrador y se apagó el micrófono; reduce o divide el texto antes de enviarlo.');return
        self.voice_flow.final(self.voice_auto.get(),self.voice_delay.get(),confidence)
    def before_voice_send(self):
        self.voice_flow.sent();self.voice_last_answer='';self.stop_read();self.recorder.pause(True)
    def read_response(self,text):
        if self.native_dictation:
            messagebox.showinfo('Dictado Windows activo','Cierra y apaga el panel Win+H antes de reproducir voz, para que no transcriba a Nexo. Después pulsa de nuevo Dictado Windows para marcarlo como cerrado.',parent=self.root);return
        self.voice_flow.cancel_pending();self.recorder.pause(True);self.voice_resume_at=time.monotonic()+.7
        try:
            self.voice_preferences();self.voice_speaking=True;self.read_button.configure(text='■ Voz')
            token=self.speaker.speak(text,self.voice_language.get(),self.voice_id.get(),self.voice_rate.get())
            if token is None:self.stop_read()
            else:self.voice_status.set('Leyendo · micrófono en pausa')
        except Exception as e:self.stop_read();self.emit_ui('Voz',str(e))
    def toggle_read(self):
        if self.voice_speaking:self.stop_read();return
        text=self.selected_text(self.log) or next((r['text'] for r in reversed(self.chat_messages) if r['who']=='Nexo'),'')
        if text:self.read_response(text)
        else:self.voice_status.set('Todavía no hay una respuesta para leer')
    def stop_read(self):
        self.speaker.stop();self.voice_speaking=False;self.voice_resume_at=time.monotonic()+.7
        self.read_button.configure(text='🔊 Leer')
        if not self.voice_flow.active:self.voice_status.set('Lectura detenida · micrófono local apagado')
    def voice_output_event(self,token,event):
        if token!=self.speaker.token:return
        self.voice_speaking=False;self.read_button.configure(text='🔊 Leer');self.voice_resume_at=time.monotonic()+.7
        if not event.get('ok'):
            self.voice_tts_failed=True;self.emit_ui('Voz',event.get('error','No se pudo leer la respuesta.')+' La lectura automática queda pausada hasta volver a activar Mic o detectar voces.')
        elif not self.voice_flow.active:self.voice_status.set('Lectura terminada · micrófono local apagado')
    def after_voice_task(self):
        if self.voice_foreground() and self.voice_flow.active and self.voice_read.get() and not self.voice_tts_failed and self.session and self.session['status']=='idle' and self.voice_last_answer:self.read_response(self.voice_last_answer)
    def native_dictation_click(self):
        if self.native_dictation:
            if messagebox.askyesno('Dictado Windows','Nexo no puede detener ni consultar el micrófono de Win+H. Ciérralo desde su panel.\n\n¿Ya lo apagaste y cerraste?',parent=self.root):
                self.native_dictation=False;self.native_button.configure(text='Dictado Windows');self.voice_status.set('Dictado Windows marcado como cerrado')
            return
        if not messagebox.askyesno('Dictado nativo de Windows','Abrirá Win+H con el cursor en el mensaje. Usa el idioma de dictado de Windows (puedes mantener español de México).\n\nWindows controla esa escucha y puede procesarla en línea según su configuración. Este acceso no envía mensajes automáticamente. Cierra su panel para apagar su micrófono; Nexo no lo controla. ¿Abrir?',parent=self.root):return
        self.microphone_off();self.input.focus_force()
        def launch():
            if self.root.focus_get() is not self.input:return
            try:
                open_windows_dictation();self.native_dictation=True;self.native_button.configure(text='Win+H abierto')
                self.voice_status.set('Win+H: Windows controla el micrófono y su cierre')
            except Exception as e:messagebox.showerror('Dictado Windows',str(e),parent=self.root)
        self.root.after(180,launch)
    def voice_settings(self,tabs):
        page=self.scroll_page(tabs,'Voz')
        ttk.Label(page,text='Conversación continua local',font=('Segoe UI',11,'bold')).grid(row=0,column=0,sticky='w')
        ttk.Label(page,text='No es el motor Win+H. Usa Vosk en español; la precisión del acento mexicano y vocabulario técnico debe comprobarse en tu equipo.',wraplength=380,style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=8)
        ttk.Checkbutton(page,text='Enviar después de una pausa',variable=self.voice_auto,command=self.voice_flow.cancel_pending).grid(row=2,column=0,sticky='w')
        ttk.Label(page,text='Espera tras la última frase (2–10 segundos)').grid(row=3,column=0,sticky='w',pady=(8,2))
        ttk.Spinbox(page,from_=2,to=10,increment=.5,textvariable=self.voice_delay,width=10).grid(row=4,column=0,sticky='w')
        ttk.Label(page,text='Modelo español: detección y preparación automáticas. No requiere elegir carpetas.',wraplength=380).grid(row=5,column=0,sticky='w',pady=(8,2))
        ttk.Label(page,textvariable=self.voice_model,wraplength=380,style='Muted.TLabel').grid(row=6,column=0,sticky='w')
        ttk.Button(page,text='Comprobar / reparar modelo incluido',command=lambda:self.prepare_voice_model(repair=True)).grid(row=7,column=0,sticky='w',pady=5)
        ttk.Separator(page).grid(row=8,column=0,sticky='ew',pady=10)
        ttk.Label(page,text='Lectura con voces de Windows',font=('Segoe UI',11,'bold')).grid(row=9,column=0,sticky='w')
        ttk.Checkbutton(page,text='Leer respuestas mientras el modo Mic esté activo',variable=self.voice_read).grid(row=10,column=0,sticky='w',pady=6)
        self.voice_picker=ttk.Combobox(page,textvariable=self.voice_selected,state='readonly',values=['Automática · '+self.voice_language.get()]);self.voice_picker.grid(row=11,column=0,sticky='ew')
        def selected(event=None):
            voice=self.voice_choices.get(self.voice_selected.get())
            if voice:self.voice_id.set(voice['id']);self.voice_language.set(voice['language']);self.voice_tts_failed=False
        self.voice_picker.bind('<<ComboboxSelected>>',selected)
        ttk.Button(page,text='Detectar voces instaladas',command=self.detect_voices).grid(row=12,column=0,sticky='w',pady=5)
        ttk.Label(page,text='Velocidad de lectura (0.5–2)').grid(row=13,column=0,sticky='w')
        ttk.Spinbox(page,from_=.5,to=2,increment=.1,textvariable=self.voice_rate,width=10).grid(row=14,column=0,sticky='w',pady=4)
        def settings():
            if os.name=='nt':os.startfile('ms-settings:speech')
            else:messagebox.showinfo('Windows','Disponible en Windows.',parent=self.config_window)
        ttk.Button(page,text='Abrir ajustes de voz de Windows',command=settings).grid(row=15,column=0,sticky='w',pady=5)
        ttk.Label(page,textvariable=self.voice_settings_status,wraplength=380,style='Muted.TLabel').grid(row=16,column=0,sticky='w',pady=8)
        ttk.Label(page,text='Comandos: «Nexo enviar», «Nexo cancelar», «Nexo borrar» y «Nexo apagar micrófono». Las aprobaciones de seguridad no se aceptan por voz. La escucha se pausa durante tareas, lectura, diálogos y al perder el foco. Para interrumpir una respuesta hablada, pulsa ■ Voz.',wraplength=380,style='Muted.TLabel').grid(row=17,column=0,sticky='w',pady=8)
    def detect_voices(self):
        self.voice_settings_status.set('Consultando voces de Windows…')
        def run():
            try:self.events.put(('voices_list',native_voices(),None))
            except Exception as e:self.events.put(('voices_list',[],str(e)))
        threading.Thread(target=run,daemon=True).start()
    def voices_list_event(self,voices,error):
        if error:self.voice_settings_status.set(error);return
        self.voice_choices={v['language']+' · '+v['name']:v for v in voices}
        if hasattr(self,'voice_picker') and self.voice_picker.winfo_exists():self.voice_picker.configure(values=list(self.voice_choices))
        preferred=next((label for label,v in self.voice_choices.items() if v['id']==self.voice_id.get()),None)
        if not preferred:preferred=next((label for label,v in self.voice_choices.items() if v['language'].lower()=='es-mx'),None)
        if preferred:
            voice=self.voice_choices[preferred];self.voice_selected.set(preferred);self.voice_id.set(voice['id']);self.voice_language.set(voice['language'])
        self.voice_tts_failed=False
        self.voice_settings_status.set(f'{len(voices)} voces encontradas.'+(' Preferencia: español de México.' if any(v['language'].lower()=='es-mx' for v in voices) else ' No se encontró es-MX: instala esa voz o elige otra explícitamente.'))
    def shutdown_voice(self):
        self.voice_prepare_token+=1;self.voice_prepare_activate=False
        self.voice_flow.disable();self.recorder.stop();self.speaker.stop()
