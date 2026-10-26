"""Nexo PC 0.6: local academic pilot, native Word comments and explicit permissions."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import webbrowser
from adapters import API, PROVIDERS, Tools, ollama_models
from runtime import Runtime, recover_pending
from storage import Store
from settings import Settings
from clipboard_ui import ClipboardMixin
from voice_ui import VoiceUIMixin

def state_text(value):
    return {'idle':'listo','running':'en curso','limit':'límite alcanzado','error':'error','denied':'plan rechazado','interrupted':'detenido'}.get(value,value)

class Application(ClipboardMixin,VoiceUIMixin):
    def __init__(self,root,store=None,settings=None):
        self.root=root;self.store=store or Store();self.settings=settings or Settings(self.store.root)
        self.events=queue.Queue();self.stop=threading.Event();self.busy=False
        self.tools=None;self.session=None;self.pending=None;self.controls=[];self.config_window=None;self.session_window=None
        self.memory_keys={};self.last_models={};self.config_widgets={};self.autonomy_before=False;self.tool_events=[];self.chat_messages=[];self.message_action_widgets=[]
        p=self.settings.data['preferences']
        root.title('Nexo PC · 0.6.0 · Tesis piloto');root.geometry('880x700');root.minsize(480,400);root.configure(bg='#f5f6fa')
        self.configure_style()
        self.provider=tk.StringVar(value=p['provider'] if p['provider'] in PROVIDERS else 'Groq')
        self.model=tk.StringVar(value=p['model']);self.endpoint=tk.StringVar(value=p['endpoint']);self.key=tk.StringVar()
        self.workspace=tk.StringVar(value=p['workspace']);self.mode=tk.StringVar(value='PLAN')
        self.approval=tk.StringVar(value=p['approval'] if p['approval'] in ('plan','step') else 'plan')
        self.autonomous=tk.BooleanVar(value=False);self.broad=tk.BooleanVar(value=False)
        self.remember=tk.BooleanVar(value=p['remember']);self.consent=tk.BooleanVar(value=False)
        self.max_calls=tk.IntVar(value=p['max_calls']);self.max_actions=tk.IntVar(value=p['max_actions'])
        self.economy=tk.BooleanVar(value=p.get('economy',True));self.timeout=tk.IntVar(value=p['timeout']);self.context_limit=tk.IntVar(value=p['context_limit']);self.font_size=tk.IntVar(value=p['font_size'])
        self.flags={k:tk.BooleanVar(value=p.get('flags',{}).get(k,k=='files')) for k in ('files','shell','browser','desktop')}
        self.active_profile=(self.provider.get(),self.model.get(),self.endpoint.get())
        self.restore_key()
        root.columnconfigure(0,weight=1);root.rowconfigure(1,weight=1)
        header=ttk.Frame(root,padding=(18,12));header.grid(row=0,column=0,sticky='ew');header.columnconfigure(0,weight=1)
        brand=ttk.Frame(header);brand.grid(row=0,column=0,sticky='w')
        ttk.Label(brand,text='nexo',style='Brand.TLabel').pack(side='left')
        self.tagline=ttk.Label(brand,text='  /  tu espacio de trabajo',style='Muted.TLabel');self.tagline.pack(side='left')
        actions=ttk.Frame(header);actions.grid(row=0,column=1,sticky='e')
        self.button(actions,'Tesis',self.show_academic).pack(side='left',padx=3)
        self.button(actions,'Historial',self.show_sessions).pack(side='left',padx=3)
        self.button(actions,'Ajustes',self.show_settings).pack(side='left')
        modes=ttk.Frame(header);modes.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(10,0))
        for label,value in [('Planificar','PLAN'),('Actuar','ACT')]:
            w=ttk.Radiobutton(modes,text=label,value=value,variable=self.mode,command=self.update_mode)
            w.pack(side='left',padx=(0,12));self.controls.append((w,'normal'))
        # Autonomy remains operable while busy ONLY to revoke a running task.
        self.auto_toggle=ttk.Checkbutton(modes,text='Autónomo',variable=self.autonomous,command=self.autonomy_changed)
        self.auto_toggle.pack(side='right')
        self.profile_label=ttk.Label(header,text='',style='Muted.TLabel');self.profile_label.grid(row=2,column=0,columnspan=2,sticky='w',pady=(8,0))
        self.mode_note=ttk.Label(header,text='',style='Muted.TLabel',wraplength=720)
        self.mode_note.grid(row=3,column=0,columnspan=2,sticky='w',pady=(3,0))
        chat=ttk.Frame(root,padding=(18,0));chat.grid(row=1,column=0,sticky='nsew');chat.rowconfigure(1,weight=1);chat.columnconfigure(0,weight=1)
        self.session_label=ttk.Label(chat,text='Nueva conversación',style='Muted.TLabel');self.session_label.grid(row=0,column=0,sticky='w',pady=(0,6))
        self.log=ScrolledText(chat,wrap='word',height=3,state='disabled',font=('Segoe UI',self.font_size.get()),
                             bg='#ffffff',fg='#25304b',relief='flat',padx=16,pady=14,borderwidth=0)
        self.log.grid(row=1,column=0,sticky='nsew')
        self.log.tag_configure('title',foreground='#5865d8',font=('Segoe UI',self.font_size.get(),'bold'),spacing1=8,spacing3=4)
        self.log.tag_configure('tool',foreground='#66738c',font=('Consolas',max(9,self.font_size.get()-1)))
        composer=ttk.Frame(root,padding=(18,10,18,0));composer.grid(row=2,column=0,sticky='ew');composer.columnconfigure(0,weight=1)
        self.input=tk.Text(composer,height=3,wrap='word',font=('Segoe UI',self.font_size.get()),bg='white',fg='#25304b',
                           relief='flat',padx=12,pady=10,undo=True,highlightthickness=1,highlightbackground='#dfe3ee',highlightcolor='#6875e5')
        self.input.grid(row=0,column=0,sticky='nsew',padx=(0,10))
        self.input.bind('<Return>',self.on_enter);self.input.bind('<Shift-Return>',self.on_newline);self.input.bind('<KP_Enter>',self.on_enter)
        compose_buttons=ttk.Frame(composer);compose_buttons.grid(row=0,column=1,sticky='ns')
        self.send=self.button(compose_buttons,'Enviar  ↗',self.start,style='Accent.TButton');self.send.pack(fill='x')
        self.stop_button=ttk.Button(compose_buttons,text='Detener',command=self.cancel);self.stop_button.pack(fill='x',pady=(6,0))
        ttk.Label(composer,text='Enter envía · Shift+Enter crea otra línea',style='Muted.TLabel').grid(row=1,column=0,columnspan=2,sticky='w',pady=(5,0))
        self.setup_voice_ui(composer)
        self.attach_text_menu(self.input);self.attach_text_menu(self.log)
        footer=ttk.Frame(root,padding=(18,6,18,10));footer.grid(row=3,column=0,sticky='ew');footer.columnconfigure(0,weight=1)
        self.status=tk.StringVar(value='Listo')
        self.status_label=ttk.Label(footer,textvariable=self.status,style='Muted.TLabel',wraplength=600)
        self.status_label.grid(row=0,column=0,sticky='w')
        self.button(footer,'Detalles',self.show_details).grid(row=0,column=1,padx=(3,5))
        self.button(footer,'Nueva',self.new_session).grid(row=0,column=2)
        # A hidden list is also kept for programmatic session selection; the visible history lives in a dialog.
        self.sessions_list=tk.Listbox(root,exportselection=False)
        self.refresh_sessions();self.update_mode();self.update_profile_label()
        root.report_callback_exception=self.callback_error
        self.emit_ui('Hola, soy Nexo','¿En qué trabajamos hoy?\n\nPlanifica para explorar sin modificar archivos. En Actuar, aprueba un plan una sola vez o activa Autónomo para las herramientas autorizadas.\n\nConfigura tus modelos y sus claves en Ajustes. Tus conversaciones anteriores siguen disponibles en Historial.')
        if self.settings.warning:self.emit_ui('Preferencias',self.settings.warning)
        root.bind('<Configure>',self.on_resize);root.protocol('WM_DELETE_WINDOW',self.close);root.after(80,self.poll)
    def show_academic(self):
        if self.busy:return
        if getattr(self,'academic_window',None) is not None:
            self.academic_window.window.lift();return
        if self.native_dictation:
            if not messagebox.askyesno('Cerrar dictado de Windows','Antes de trabajar en Word, cierra Win+H y apaga su micrófono. Nexo no puede verificarlo. ¿Ya lo cerraste?',parent=self.root):return
            self.native_dictation=False;self.native_button.configure(text='Dictado Windows')
        self.stop_read();self.voice_flow.cancel_pending()
        from academic_ui import AcademicWindow
        try:self.academic_window=AcademicWindow(self)
        except Exception as e:messagebox.showerror('Nexo Académico',str(e),parent=self.root)
    def callback_error(self,kind,error,traceback):
        text=str(error)
        for secret in list(self.memory_keys.values())+[self.key.get()]:
            if secret:text=text.replace(secret,'[CLAVE OMITIDA]')
        self.emit_ui('Error de interfaz',text)
        messagebox.showerror('Nexo encontró un error',text+'\n\nLa tarea no se considera completada. Puedes revisar Detalles.',parent=self.root)
    def configure_style(self):
        s=ttk.Style();s.theme_use('clam')
        s.configure('.',font=('Segoe UI',10));s.configure('TFrame',background='#f5f6fa');s.configure('Chat.TFrame',background='white')
        s.configure('TLabel',background='#f5f6fa',foreground='#25304b')
        s.configure('Muted.TLabel',foreground='#68738b',font=('Segoe UI',9))
        s.configure('Brand.TLabel',foreground='#5865d8',font=('Segoe UI',25,'bold'))
        s.configure('TButton',padding=(10,7),background='#e9ecf5',borderwidth=0,foreground='#35405a')
        s.map('TButton',background=[('active','#dce2f4')])
        s.configure('Accent.TButton',background='#5865d8',foreground='white',padding=(14,10))
        s.map('Accent.TButton',background=[('active','#4552c7'),('disabled','#c4c9e9')],foreground=[('disabled','#f7f8fc')])
        s.configure('TCheckbutton',background='#f5f6fa');s.configure('TRadiobutton',background='#f5f6fa')
        s.configure('TNotebook',background='#f5f6fa',borderwidth=0);s.configure('TNotebook.Tab',padding=(12,8))
    def button(self,parent,text,command,**kwargs):
        w=ttk.Button(parent,text=text,command=command,**kwargs);self.controls.append((w,'normal'));return w
    def on_resize(self,event):
        if event.widget is self.root:
            self.status_label.configure(wraplength=max(120,event.width-300))
            self.mode_note.configure(wraplength=max(350,event.width-45))
            self.voice_status_label.configure(wraplength=max(350,event.width-45))
            if event.height<450:self.profile_label.grid_remove()
            else:self.profile_label.grid()
            if event.width<650:self.tagline.pack_forget()
            elif not self.tagline.winfo_manager():self.tagline.pack(side='left')
            if event.height<500:
                self.mode_note.grid_remove();self.session_label.grid_remove();self.input.configure(height=2)
            else:
                self.mode_note.grid();self.session_label.grid();self.input.configure(height=3)
    def on_enter(self,event=None):
        if event is not None and event.state & 1:return self.on_newline(event)
        self.start();return 'break'
    def on_newline(self,event=None):
        self.voice_flow.cancel_pending()
        self.input.insert('insert','\n');return 'break'
    def set_busy(self,value):
        self.busy=value
        self.controls=[(w,state) for w,state in self.controls if w.winfo_exists()]
        for w,state in self.controls:w.configure(state='disabled' if value else state)
        self.sessions_list.configure(state='disabled' if value else 'normal')
        self.send.configure(text='En curso…' if value else 'Enviar  ↗')
    def update_profile_label(self):
        self.profile_label.configure(text=f'{self.provider.get()}  ·  {self.model.get()[:48]}')
    def update_mode(self):
        if self.mode.get()=='PLAN':
            self.autonomous.set(False)
            text='Solo lectura. No modifica archivos ni ejecuta comandos.'
        elif self.autonomous.get():text='Autónomo · ejecuta dentro de tus permisos y límites. Detener revoca esta tarea.'
        elif self.approval.get()=='step':text='Supervisado · revisarás cada acción antes de ejecutarla.'
        else:text='Por plan · una aprobación por tarea; sin repetir pasos ya autorizados.'
        self.mode_note.configure(text=text)
    def autonomy_changed(self):
        if self.busy:
            self.autonomous.set(False);self.cancel();self.update_mode();return
        if self.autonomous.get():
            if not messagebox.askyesno('Activar autonomía','Nexo podrá leer y modificar archivos de la carpeta elegida sin revisar cada paso. Se mantienen checkpoints, límites y Detener.\n\nLas herramientas amplias siguen requiriendo revisión salvo autorización adicional en Ajustes. No se reactivará automáticamente al abrir Nexo.\n\n¿Activar?',parent=self.root):self.autonomous.set(False)
            else:self.mode.set('ACT')
        self.update_mode()
    def broad_changed(self):
        if self.broad.get() and not messagebox.askyesno('Permisos amplios durante esta ejecución','Si habilitas estas herramientas, la aprobación del plan o el modo autónomo también cubrirá PowerShell, escritorio y clics/rellenos del navegador.\n\nPueden afectar archivos fuera de la carpeta, enviar datos, borrar contenido o actuar con tus permisos de usuario. Los checkpoints NO revierten esos efectos. No existe un filtro perfecto de acciones peligrosas.\n\nSe desactiva al reiniciar. ¿Autorizar este alcance?',parent=self.config_window):self.broad.set(False)
    def restore_key(self):
        profile=(self.provider.get(),self.model.get(),self.endpoint.get())
        try:self.key.set(self.memory_keys[profile] if self.memory_keys.get(profile) else self.settings.key(*profile))
        except Exception as e:self.key.set('');self.settings.warning='No se pudo recuperar una clave protegida: '+str(e)
        self.active_profile=profile
    def stash_key(self):
        self.memory_keys[self.active_profile]=self.key.get()
    def provider_changed(self,event=None):
        self.stash_key();self.last_models[self.active_profile[0]]=self.active_profile[1]
        provider=self.provider.get();models=self.settings.models(provider)
        self.model.set(self.last_models.get(provider,models[0] if models else PROVIDERS[provider]));self.restore_key()
        self.refresh_model_widgets();self.update_profile_label()
    def model_changed(self,event=None):
        profile=(self.provider.get(),self.model.get().strip(),self.endpoint.get())
        if profile!=self.active_profile:self.stash_key();self.restore_key()
        self.update_profile_label()
    def refresh_model_widgets(self):
        w=self.config_widgets.get('model')
        if w and w.winfo_exists():w.configure(values=sorted(set(self.settings.models(self.provider.get())+[PROVIDERS[self.provider.get()]])))
        is_local=self.provider.get()=='Ollama'
        for key in ('key','remember'):
            w=self.config_widgets.get(key)
            if w and w.winfo_exists():w.configure(state='disabled' if is_local else 'normal')
        w=self.config_widgets.get('endpoint')
        if w and w.winfo_exists():w.configure(state='normal' if is_local else 'disabled')
    def preference_values(self):
        values={'provider':self.provider.get(),'model':self.model.get().strip(),'endpoint':self.endpoint.get().strip(),
                'workspace':self.workspace.get().strip(),'approval':self.approval.get(),'remember':self.remember.get(),
                'max_calls':self.max_calls.get(),'max_actions':self.max_actions.get(),'timeout':self.timeout.get(),
                'economy':self.economy.get(),'context_limit':self.context_limit.get(),'font_size':self.font_size.get(),'flags':{k:v.get() for k,v in self.flags.items()}}
        for k,lo,hi in [('max_calls',1,64),('max_actions',1,256),('timeout',10,600),('context_limit',10000,500000),('font_size',9,16)]:
            if not lo<=values[k]<=hi:raise ValueError(f'{k}: usa un valor entre {lo} y {hi}.')
        values.update(self.voice_preferences())
        return values
    def save_preferences(self,notify=False):
        try:
            values=self.preference_values()
            self.settings.save_profile(values['provider'],values['model'],self.key.get(),values['endpoint'],self.remember.get())
            self.settings.save_preferences(values);self.active_profile=(values['provider'],values['model'],values['endpoint']);self.stash_key()
            self.log.configure(font=('Segoe UI',values['font_size']));self.input.configure(font=('Segoe UI',values['font_size']))
            self.log.tag_configure('title',font=('Segoe UI',values['font_size'],'bold'))
            self.update_profile_label();self.update_mode();self.refresh_model_widgets()
            if notify:messagebox.showinfo('Guardado','Perfil y preferencias guardados. Las claves recordadas se protegen con Windows DPAPI.',parent=self.config_window or self.root)
            return True
        except Exception as e:messagebox.showerror('No se pudo guardar',str(e),parent=self.config_window or self.root);return False
    def forget_key(self):
        self.settings.forget(self.provider.get(),self.model.get(),self.endpoint.get());self.memory_keys.pop(self.active_profile,None);self.key.set('')
        messagebox.showinfo('Clave eliminada','Se eliminó la clave guardada de este perfil. No revoca la clave en el proveedor.',parent=self.config_window)
    def choose_folder(self):
        if self.busy:return
        path=filedialog.askdirectory(parent=self.config_window or self.root)
        if path:self.workspace.set(path)
    def open_keys(self):
        url={'Groq':'https://console.groq.com/keys','Gemini':'https://aistudio.google.com/apikey','Ollama':'https://ollama.com/download'}[self.provider.get()]
        webbrowser.open(url)
    def detect_models(self):
        endpoint=self.endpoint.get();self.settings_status.set('Consultando Ollama…')
        def task():
            try:self.events.put(('models',endpoint,ollama_models(endpoint),None))
            except Exception as e:self.events.put(('models',endpoint,[],str(e)))
        threading.Thread(target=task,daemon=True).start()
    def scroll_page(self,notebook,title):
        outer=ttk.Frame(notebook);notebook.add(outer,text=title)
        canvas=tk.Canvas(outer,bg='#f5f6fa',highlightthickness=0);scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        frame=ttk.Frame(canvas,padding=14);window=canvas.create_window(0,0,anchor='nw',window=frame)
        frame.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width));frame.columnconfigure(0,weight=1)
        return frame
    def show_settings(self):
        if self.busy:return
        if self.config_window and self.config_window.winfo_exists():self.config_window.lift();return
        win=tk.Toplevel(self.root);self.config_window=win;win.title('Ajustes · Nexo');win.geometry('680x650');win.minsize(450,400);win.transient(self.root)
        win.rowconfigure(0,weight=1);win.columnconfigure(0,weight=1)
        tabs=ttk.Notebook(win);tabs.grid(row=0,column=0,sticky='nsew',padx=10,pady=10)
        connection=self.scroll_page(tabs,'Modelos');permissions=self.scroll_page(tabs,'Permisos');limits=self.scroll_page(tabs,'Avanzado')
        self.config_widgets={};r=0
        for label,var,key in [('Proveedor',self.provider,'provider'),('Modelo / perfil guardado',self.model,'model'),('Clave API de este perfil',self.key,'key'),('Dirección local de Ollama',self.endpoint,'endpoint')]:
            ttk.Label(connection,text=label).grid(row=r,column=0,sticky='w',pady=(6,3));r+=1
            if key=='provider':
                w=ttk.Combobox(connection,textvariable=var,values=list(PROVIDERS),state='readonly');w.bind('<<ComboboxSelected>>',self.provider_changed)
            elif key=='model':
                w=ttk.Combobox(connection,textvariable=var);w.bind('<<ComboboxSelected>>',self.model_changed);w.bind('<FocusOut>',self.model_changed)
            else:w=ttk.Entry(connection,textvariable=var,show='•' if key=='key' else '')
            if key=='endpoint':w.bind('<FocusOut>',self.model_changed)
            w.grid(row=r,column=0,sticky='ew');self.config_widgets[key]=w;self.controls.append((w,'readonly' if key=='provider' else 'normal'));r+=1
        remember=ttk.Checkbutton(connection,text='Recordar clave para este modelo (Windows DPAPI)',variable=self.remember)
        remember.grid(row=r,column=0,sticky='w',pady=10);self.config_widgets['remember']=remember;r+=1
        buttons=ttk.Frame(connection);buttons.grid(row=r,column=0,sticky='w');r+=1
        ttk.Button(buttons,text='Detectar Ollama',command=self.detect_models).pack(side='left',padx=(0,5))
        ttk.Button(buttons,text='Obtener clave / instalar',command=self.open_keys).pack(side='left')
        ttk.Button(connection,text='Olvidar clave de este perfil',command=self.forget_key).grid(row=r,column=0,sticky='w',pady=8);r+=1
        self.settings_status=tk.StringVar(value='Ollama: usa un modelo descargado con soporte de herramientas. No se descarga ni instala nada automáticamente.')
        ttk.Label(connection,textvariable=self.settings_status,wraplength=390,style='Muted.TLabel').grid(row=r,column=0,sticky='w')
        ttk.Label(permissions,text='Carpeta de trabajo',font=('Segoe UI',11,'bold')).grid(row=0,column=0,sticky='w')
        row=ttk.Frame(permissions);row.grid(row=1,column=0,sticky='ew',pady=8);row.columnconfigure(0,weight=1)
        ttk.Entry(row,textvariable=self.workspace).grid(row=0,column=0,sticky='ew');ttk.Button(row,text='Elegir',command=self.choose_folder).grid(row=0,column=1,padx=5)
        ttk.Label(permissions,text='Cuando Autónomo está desactivado:').grid(row=2,column=0,sticky='w',pady=(8,4))
        ttk.Radiobutton(permissions,text='Aprobar un plan por tarea (recomendado)',variable=self.approval,value='plan',command=self.update_mode).grid(row=3,column=0,sticky='w')
        ttk.Radiobutton(permissions,text='Revisar cada acción',variable=self.approval,value='step',command=self.update_mode).grid(row=4,column=0,sticky='w')
        ttk.Label(permissions,text='Herramientas disponibles',font=('Segoe UI',11,'bold')).grid(row=5,column=0,sticky='w',pady=(16,5))
        for i,(key,label) in enumerate([('files','Archivos de la carpeta'),('shell','PowerShell — acceso amplio al PC'),('browser','Navegador separado (requiere Extras)'),('desktop','Escritorio — experimental, requiere Extras')]):
            ttk.Checkbutton(permissions,text=label,variable=self.flags[key]).grid(row=6+i,column=0,sticky='w',pady=3)
        ttk.Separator(permissions).grid(row=10,column=0,sticky='ew',pady=12)
        ttk.Checkbutton(permissions,text='Autorizar herramientas amplias por tarea',variable=self.broad,command=self.broad_changed).grid(row=11,column=0,sticky='w')
        ttk.Label(permissions,text='Solo durante esta apertura de Nexo. Incluye PowerShell, escritorio y clics/rellenos. Pueden actuar fuera de la carpeta y enviar datos. No hay deshacer general.',wraplength=390,style='Muted.TLabel').grid(row=12,column=0,sticky='w',pady=8)
        for i,(label,var,lo,hi) in enumerate([('Solicitudes al modelo por tarea',self.max_calls,1,64),('Acciones por tarea',self.max_actions,1,256),('Espera de API, en segundos',self.timeout,10,600),('Límite duro de contexto, caracteres aprox.',self.context_limit,10000,500000),('Tamaño de texto',self.font_size,9,16)]):
            ttk.Label(limits,text=label).grid(row=i*2,column=0,sticky='w',pady=(8,2));ttk.Spinbox(limits,textvariable=var,from_=lo,to=hi,width=12).grid(row=i*2+1,column=0,sticky='w')
        ttk.Label(limits,text='Más solicitudes pueden consumir más cuota y dinero. No hay cambio automático de proveedor ni reintentos ocultos. Detener bloquea nuevas acciones; una respuesta API en curso puede tardar hasta el tiempo configurado.\n\nEl historial se guarda localmente sin cifrar. Las claves recordadas sí se protegen con DPAPI; otro proceso de tu misma cuenta puede descifrarlas. Con Ollama, comprueba que el modelo sea realmente local: una dirección local no garantiza por sí sola inferencia local.',wraplength=390,style='Muted.TLabel').grid(row=10,column=0,sticky='w',pady=16)
        ttk.Checkbutton(limits,text='Ahorrar tokens con contexto compacto (recomendado)',variable=self.economy).grid(row=11,column=0,sticky='w')
        ttk.Label(limits,text='Objetivo: 12 000 caracteres de historial por solicitud, más instrucciones y herramientas. Conserva el chat completo y no gasta llamadas en resumir. Los pasos grandes pueden superar ese objetivo hasta el límite configurado.',wraplength=390,style='Muted.TLabel').grid(row=12,column=0,sticky='w',pady=8)
        self.voice_settings(tabs)
        row=ttk.Frame(win,padding=10);row.grid(row=1,column=0,sticky='ew')
        ttk.Button(row,text='Checkpoints',command=self.checkpoints).pack(side='left')
        ttk.Button(row,text='Guardar perfil y ajustes',command=lambda:self.save_preferences(True),style='Accent.TButton').pack(side='right')
        def close():self.model_changed();self.config_window=None;win.grab_release();win.destroy();self.update_profile_label();self.update_mode()
        win.protocol('WM_DELETE_WINDOW',close);win.grab_set();self.refresh_model_widgets();self.attach_menus_tree(win)
    def emit_ui(self,who,text):
        source_text=text;start=self.log.index('end-1c')
        if who=='Nexo':self.voice_last_answer=text
        if who.startswith('Herramienta'):
            self.tool_events.append((who,text))
            try:
                result=json.loads(text)
                if result.get('written'):text='Archivo guardado: '+result['written']+'\nCheckpoint creado; puedes restaurarlo desde Ajustes.'
                elif result.get('approved'):text='Plan aprobado. Continúo dentro de los permisos acordados.'
                elif result.get('error'):text='No se completó: '+str(result['error'])[:500]
                elif result.get('denied'):text='Acción rechazada. No se ejecutó.'
                elif 'entries' in result:text=f"{len(result['entries'])} entradas encontradas. Detalles disponibles abajo."
                elif 'text' in result:text='Contenido leído. '+str(result['text'])[:180]+('…' if len(str(result['text']))>180 else '')
                else:text=text[:250]+('…  Ver Detalles.' if len(text)>250 else '')
            except (ValueError,TypeError):text=text[:500]
        self.log.configure(state='normal');self.log.insert('end',who.upper()+'\n','title')
        self.log.insert('end',text+'\n\n','tool' if who.startswith('Herramienta') else ());
        if who=='Nexo':self.response_actions(source_text)
        self.chat_messages.append({'who':who,'text':source_text,'start':start,'end':self.log.index('end-1c')})
        self.log.see('end');self.log.configure(state='disabled')
    def show_details(self):
        win=tk.Toplevel(self.root);win.title('Detalles de herramientas');win.geometry('700x500');win.minsize(400,250)
        area=ScrolledText(win,wrap='word',font=('Consolas',10));area.pack(fill='both',expand=True,padx=12,pady=12)
        area.insert('1.0','\n\n'.join(who+'\n'+text for who,text in self.tool_events) or 'Todavía no hay herramientas ejecutadas en esta conversación.');area.configure(state='disabled');self.attach_text_menu(area)
    def clear_ui(self):
        self.tool_events.clear();self.chat_messages.clear()
        for widget in self.message_action_widgets:
            if widget.winfo_exists():widget.destroy()
        self.message_action_widgets.clear();self.log.configure(state='normal');self.log.delete('1.0','end');self.log.configure(state='disabled')
    def refresh_sessions(self):
        self.session_rows=self.store.sessions();self.sessions_list.delete(0,'end')
        for row in self.session_rows:self.sessions_list.insert('end',row['title'][:55] or row['id'][:8])
    def show_sessions(self):
        if self.busy:return
        if self.session_window and self.session_window.winfo_exists():self.session_window.lift();return
        win=tk.Toplevel(self.root);self.session_window=win;win.title('Conversaciones');win.geometry('560x430');win.minsize(360,260);win.transient(self.root)
        ttk.Label(win,text='Continúa donde lo dejaste',font=('Segoe UI',16,'bold')).pack(anchor='w',padx=16,pady=14)
        self.sessions_list.destroy();self.sessions_list=tk.Listbox(win,relief='flat',bg='white',font=('Segoe UI',11),exportselection=False)
        self.sessions_list.pack(fill='both',expand=True,padx=16,pady=8);self.refresh_sessions()
        def close():
            self.sessions_list.destroy();self.sessions_list=tk.Listbox(self.root,exportselection=False);self.refresh_sessions();self.session_window=None;win.destroy()
        def load():self.load_session();close()
        row=ttk.Frame(win,padding=12);row.pack(fill='x');ttk.Button(row,text='Abrir',command=load,style='Accent.TButton').pack(side='right')
        ttk.Button(row,text='Nueva',command=lambda:(self.new_session(),close())).pack(side='left')
        self.sessions_list.bind('<Double-Button-1>',lambda e:load());win.protocol('WM_DELETE_WINDOW',close)
    def new_session(self):
        if self.busy:return
        self.microphone_off();self.session=None;self.clear_ui();self.session_label.configure(text='Nueva conversación');self.emit_ui('Nueva conversación','Elige una tarea. El historial anterior sigue guardado.')
    def load_session(self):
        if self.busy or not self.sessions_list.curselection():return
        try:
            self.microphone_off();self.stash_key();r=self.store.load(self.session_rows[self.sessions_list.curselection()[0]]['id'])
            self.session=r;self.provider.set(r['provider']);self.model.set(r['model']);self.workspace.set(r['workspace'])
            if r.get('endpoint'):self.endpoint.set(r['endpoint'])
            self.restore_key();self.clear_ui()
            for entry in r['display']:self.emit_ui(entry['who'],entry['text'])
            self.session_label.configure(text=f"{r['title'][:45]} · {state_text(r['status'])}");self.update_profile_label()
            self.emit_ui('Reanudación','Historial recuperado y perfil cargado. No se ejecuta nada al abrir. Las autorizaciones anteriores no se reactivan.')
        except Exception as e:messagebox.showerror('Sesión',str(e))
    def start(self):
        if self.busy:return
        prompt=self.input.get('1.0','end-1c').strip()
        if not prompt:return
        self.before_voice_send()
        if len(prompt)>6000:messagebox.showerror('Tarea muy larga','Máximo 6000 caracteres. El texto sigue en el cuadro.');return
        try:
            values=self.preference_values()
            api=API(self.provider.get(),self.key.get(),self.model.get().strip(),endpoint=self.endpoint.get(),timeout=self.timeout.get())
            path=self.workspace.get().strip()
            if not path:raise ValueError('Elige una carpeta en Ajustes > Permisos.')
            resolved=Path(path).resolve()
            if self.store.root.is_relative_to(resolved) or Path(__file__).resolve().parent.is_relative_to(resolved):raise ValueError('Usa una carpeta dedicada que no contenga los datos ni el código de Nexo.')
            if self.session and Path(self.session['workspace']).resolve()!=resolved:
                raise ValueError('Cambiaste la carpeta de trabajo. Pulsa Nueva para ese destino; cambiar de modelo no requiere otro chat.')
        except Exception as e:messagebox.showerror('Revisa los ajustes',str(e));return
        if not self.consent.get():
            text=('El contexto de esta conversación (incluido historial anterior) y los resultados se enviarán al proveedor seleccionado.' if api.provider!='Ollama' else 'Las instrucciones y resultados se enviarán al servidor Ollama local. Usa un modelo descargado y desactiva funciones cloud en Ollama si necesitas privacidad estricta.')
            if not messagebox.askyesno('Datos de esta sesión',text+'\n\nEl historial se guarda en este PC sin cifrar, sin guardar la clave dentro de la conversación. ¿Continuar?',parent=self.root):return
            self.consent.set(True);self.consent_provider=api.provider
        elif getattr(self,'consent_provider',api.provider)!=api.provider:
            self.consent.set(False);return self.start()
        if not self.save_preferences():return
        enabled=[]
        if self.flags['files'].get():enabled+=['list_files','read_file','write_file']
        if self.flags['shell'].get():enabled+=['powershell']
        if self.flags['browser'].get():enabled+=['browser']
        if self.flags['desktop'].get():enabled+=['desktop']
        options={'approval':'auto' if self.autonomous.get() else self.approval.get(),'max_calls':values['max_calls'],
                 'max_actions':values['max_actions'],'context_limit':values['context_limit'],'economy':values['economy'],'broad':self.broad.get()}
        self.stop.clear();self.set_busy(True);self.status.set('Trabajando…');self.input.delete('1.0','end')
        # Capture all Tk values on the UI thread; workers never read Tk variables.
        threading.Thread(target=self.worker,args=(api,enabled,path,prompt,self.mode.get(),self.session,options),daemon=True).start()
    def worker(self,api,enabled,path,prompt,mode,session,options):
        try:
            if session is None:
                session=self.store.new_session(api.provider,api.model,path,prompt)
                if api.provider=='Ollama':session['endpoint']=api.endpoint
            self.store.secrets={v for v in self.memory_keys.values() if v}
            if api.key:self.store.secrets.add(api.key)
            self.events.put(('session',session));self.tools=Tools(path,self.stop,api.provider,self.store.root)
            engine=Runtime(api,self.tools,self.store,self.approve,lambda who,text:self.events.put(('message',who,text)),self.stop)
            engine.run(prompt,session,mode,enabled,**options)
        except Exception as e:
            text=str(e)
            if api.key:text=text.replace(api.key,'[CLAVE OMITIDA]')
            self.events.put(('message','Error',text))
        finally:
            if self.tools:self.tools.close()
            self.tools=None;self.events.put(('done',session))
    def approve(self,name,details):
        event=threading.Event();answer={'yes':False};self.events.put(('approval',name,details,event,answer))
        while not event.wait(.1):
            if self.stop.is_set():return False
        return answer['yes'] is True and not self.stop.is_set()
    def approval_dialog(self,name,details,event,answer):
        if self.stop.is_set():event.set();return
        plan=name=='execution_plan';dialog=tk.Toplevel(self.root);dialog.title('Aprobar plan' if plan else 'Revisar acción · '+name)
        dialog.geometry('740x570');dialog.minsize(440,340);dialog.transient(self.root)
        dialog.rowconfigure(2,weight=1);dialog.columnconfigure(0,weight=1)
        ttk.Label(dialog,text='Un plan. Una autorización.' if plan else 'Esta acción necesita tu revisión',font=('Segoe UI',17,'bold')).grid(row=0,column=0,sticky='w',padx=16,pady=(16,6))
        note=('Los pasos cubiertos no volverán a pedir permiso durante esta tarea. Revisa el alcance, no solo el objetivo.' if plan else 'Revisa todos los argumentos. La autorización se limita a esta acción.')
        ttk.Label(dialog,text=note,wraplength=400).grid(row=1,column=0,sticky='w',padx=16)
        tabs=ttk.Notebook(dialog);tabs.grid(row=2,column=0,sticky='nsew',padx=16,pady=12)
        contents=[]
        if plan:contents.append(('Plan',details['plan']['summary']+'\n\n'+details['plan']['steps']+'\n\nCARPETA\n'+details['workspace']+'\n\nALCANCE\n'+details['scope']+'\n\n'+details['warning']+'\n\n'+details['note']))
        contents.append(('Alcance completo' if plan else 'Argumentos completos',json.dumps({k:v for k,v in details.items() if k!='diff'},ensure_ascii=False,indent=2)))
        if 'diff' in details:contents.append(('Diferencias',details['diff'] or '(Sin diferencias de texto)'))
        for label,content in contents:
            area=ScrolledText(tabs,wrap='word',font=('Consolas',10));area.insert('1.0',content);area.configure(state='disabled');tabs.add(area,text=label)
        if 'diff' in details:tabs.select(len(contents)-1)
        self.pending=(dialog,event,answer)
        def resolve(yes):answer['yes']=yes;event.set();self.pending=None;dialog.destroy()
        row=ttk.Frame(dialog,padding=12);row.grid(row=3,column=0,sticky='ew')
        ttk.Button(row,text='Rechazar',command=lambda:resolve(False)).pack(side='left')
        ttk.Button(row,text='Aprobar plan y ejecutar' if plan else 'Aprobar esta acción',command=lambda:resolve(True),style='Accent.TButton').pack(side='right')
        dialog.protocol('WM_DELETE_WINDOW',lambda:resolve(False));dialog.lift();self.attach_menus_tree(dialog)

    def checkpoints(self):
        if self.busy:return
        workspace=self.workspace.get();records=self.store.checkpoints(workspace)
        dialog=tk.Toplevel(self.root);dialog.title('Checkpoints · solo archivos de write_file');dialog.geometry('850x440')
        ttk.Label(dialog,text='Restaura de más reciente a más antiguo. No se sobreescriben cambios posteriores.',wraplength=800).pack(padx=16,pady=14)
        listing=tk.Listbox(dialog,font=('Consolas',10));listing.pack(fill='both',expand=True,padx=16,pady=8)
        for r in records:listing.insert('end',f"{r['time'][:19]}  {r['state']:9}  {r['path']}")
        def restore():
            if self.busy or not listing.curselection():return
            record=records[listing.curselection()[0]]
            if not messagebox.askyesno('Confirmar restauración',f"Restaurar el estado anterior de:\n{record['path']}\n\nSi el archivo se creó en esa edición, se eliminará. No se revierte el historial de conversación ni otros efectos.",parent=dialog):return
            try:
                result=self.store.restore(record['id'],workspace);note='Restauración solicitada por el usuario: '+json.dumps(result,ensure_ascii=False)+'. Inspecciona el estado actual antes de editar.'
                if self.session and Path(self.session['workspace']).resolve()==Path(workspace).resolve():
                    recover_pending(self.session)
                    self.session['display'].append({'who':'Restauración','text':note})
                    self.session['messages'].append({'role':'user','parts':[{'text':note}]} if self.session['provider']=='Gemini' else {'role':'user','content':note})
                    self.store.save(self.session)
                self.emit_ui('Restauración',note);dialog.destroy()
            except Exception as e:messagebox.showerror('No se restauró',str(e),parent=dialog)
        ttk.Button(dialog,text='Restaurar seleccionado',command=restore).pack(pady=12)
    def cancel(self):
        self.microphone_off()
        self.stop.set();self.status.set('Deteniendo · esperando operación en curso')
        if self.pending:
            dialog,event,answer=self.pending;answer['yes']=False;event.set();self.pending=None;dialog.destroy()
    def poll(self):
        try:
            while True:
                item=self.events.get_nowait()
                if item[0]=='voice_input':self.voice_event(item[1],item[2])
                elif item[0]=='voice_prepared':self.voice_prepared_event(*item[1:])
                elif item[0]=='voice_output':self.voice_output_event(item[1],item[2])
                elif item[0]=='voices_list':self.voices_list_event(item[1],item[2])
                elif item[0]=='message':self.emit_ui(item[1],item[2])
                elif item[0]=='approval':self.approval_dialog(*item[1:])
                elif item[0]=='session':self.session=item[1];self.session_label.configure(text=self.session['title'][:55])
                elif item[0]=='models':
                    if self.config_window and self.config_window.winfo_exists() and self.endpoint.get()==item[1]:
                        self.settings_status.set(item[3] or f'{len(item[2])} modelos encontrados. Elige uno en Modelo; algunos no admiten herramientas.')
                        if not item[3] and self.provider.get()=='Ollama':self.config_widgets['model'].configure(values=item[2])
                elif item[0]=='done':
                    self.session=item[1];self.set_busy(False);self.refresh_sessions();self.status.set('Finalizado · '+(state_text(self.session['status']) if self.session else 'revisa el resultado'))
                    if self.session:self.session_label.configure(text=f"{self.session['title'][:35]} · {state_text(self.session['status'])} · {self.session['api_calls']} solicitudes")
                    if self.session and self.session.get('usage_totals'):
                        u=self.session['usage_totals'];self.status.set(self.status.get()+f" · {u['input_tokens']+u['output_tokens']} tokens reportados (chat)")
                    self.after_voice_task()
        except queue.Empty:pass
        self.voice_tick()
        self.root.after(80,self.poll)
    def close(self):
        panel=getattr(self,'academic_window',None)
        if panel is not None:
            if panel.busy:
                messagebox.showinfo('Word en curso','Espera a que termine la operación de Word antes de cerrar Nexo.',parent=self.root);return
            panel.guard(panel.close)
            if getattr(self,'academic_window',None) is not None:return
        if self.busy:
            if messagebox.askyesno('Tarea en curso','¿Detener la tarea? Espera a que termine la operación en curso y vuelve a cerrar.'):self.cancel()
            return
        if self.native_dictation and not messagebox.askyesno('Dictado de Windows','El micrófono de Win+H se controla desde Windows. Ciérralo allí; cerrar Nexo no lo apaga. ¿Salir de Nexo?',parent=self.root):return
        # Save geometry-independent preferences; keys are saved explicitly or when sending.
        try:self.settings.save_preferences(self.preference_values())
        except (ValueError,tk.TclError,OSError):pass
        self.shutdown_voice();self.key.set('');self.memory_keys.clear();self.root.destroy()

if __name__=='__main__':
    mutex=None
    if os.name=='nt':
        import ctypes
        kernel=ctypes.windll.kernel32;kernel.CreateMutexW.restype=ctypes.c_void_p
        mutex=kernel.CreateMutexW(None,False,'Local\\NexoPC_0_2_single_instance')
        if kernel.GetLastError()==183:
            ctypes.windll.user32.MessageBoxW(None,'Nexo PC ya está abierto. Cierra la versión anterior antes de abrir esta.','Nexo PC',0);raise SystemExit(0)
    root=tk.Tk();Application(root);root.mainloop()
