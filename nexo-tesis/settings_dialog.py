"""Compact provider accounts, installed models and explicit rotation routes."""
import json,queue,threading,uuid
import tkinter as tk
from tkinter import ttk,messagebox
from providers import PROVIDERS,list_models
from config import edit
class SettingsDialog:
    def __init__(self,app):
        self.app=app;self.config=app.config;self.working=False;self.cancel=threading.Event();self.widgets=[];self.progress=queue.Queue();self.async_timer=None
        w=self.win=tk.Toplevel(app.root);w.title('Modelos y cuentas · Nexo Tesis');w.geometry('840x650');w.minsize(720,590);w.transient(app.root);w.grab_set();w.protocol('WM_DELETE_WINDOW',self.close)
        w.columnconfigure(0,weight=1);w.rowconfigure(1,weight=1)
        ttk.Label(w,text='Tus cuentas, reutilizables entre modelos',font=('Segoe UI',15,'bold')).grid(row=0,column=0,sticky='w',padx=18,pady=(14,10))
        self.tabs=ttk.Notebook(w);self.tabs.grid(row=1,column=0,sticky='nsew',padx=16)
        self.routes_tab=ttk.Frame(self.tabs,padding=12);self.accounts_tab=ttk.Frame(self.tabs,padding=12);self.policy_tab=ttk.Frame(self.tabs,padding=12)
        for frame,title in ((self.routes_tab,'Modelos y rutas'),(self.accounts_tab,'Cuentas'),(self.policy_tab,'Rotación y privacidad')):self.tabs.add(frame,text=title)
        self.note=tk.StringVar(value='Ningún catálogo ni cuenta se consulta al abrir esta ventana.')
        ttk.Label(w,textvariable=self.note,wraplength=760,style='Muted.TLabel').grid(row=2,column=0,sticky='ew',padx=18,pady=8)
        footer=ttk.Frame(w);footer.grid(row=3,column=0,sticky='ew',padx=16,pady=(0,10))
        ttk.Button(footer,text='Cerrar',command=self.close).pack(side='right')
        self.cancel_button=ttk.Button(footer,text='Cancelar conexión',command=self.cancel.set);self.cancel_button.pack(side='left');self.cancel_button.state(['disabled'])
        for aid in list(self.config.data['accounts']):
            try:self.config.ensure_account_route(aid)
            except Exception:pass
        self.build_routes();self.build_accounts();self.build_policy();self.refresh()
        rid=self.config.data['current'].get('route_id')
        if rid and self.route_tree.exists(rid):self.route_tree.selection_set(rid);self.load_route()
        elif not self.config.data['accounts']:self.tabs.select(self.accounts_tab)
    def button(self,parent,text,fn,**kw):
        def run():
            if self.working:return
            try:fn()
            except Exception as e:messagebox.showerror('Modelos y cuentas',self.config.redact(e),parent=self.win)
        b=ttk.Button(parent,text=text,command=run,**kw);self.widgets.append(b);return b
    def entry(self,parent,var,show=None):
        e=ttk.Entry(parent,textvariable=var,show=show or '');self.widgets.append(e);return e
    def combo(self,parent,var,values=(),readonly=False):
        e=ttk.Combobox(parent,textvariable=var,values=values,state='readonly' if readonly else 'normal');e._readonly=readonly;self.widgets.append(e);return e
    def build_routes(self):
        f=self.routes_tab;f.columnconfigure(1,weight=1);f.rowconfigure(5,weight=1)
        c=self.config.data['current'];self.provider=tk.StringVar(value=c['provider']);self.model=tk.StringVar(value=c['model']);self.endpoint=tk.StringVar(value=c.get('endpoint') or 'http://127.0.0.1:11434');self.account_choice=tk.StringVar();self.auto=tk.BooleanVar(value=False)
        for row,label in ((0,'Proveedor'),(1,'Cuenta'),(2,'Modelo / ID'),(3,'Ollama local')):ttk.Label(f,text=label).grid(row=row,column=0,sticky='w',pady=4,padx=(0,12))
        pc=self.combo(f,self.provider,list(PROVIDERS),True);pc.grid(row=0,column=1,sticky='ew');pc.bind('<<ComboboxSelected>>',lambda e:self.change_provider())
        self.account_combo=self.combo(f,self.account_choice,readonly=True);self.account_combo.grid(row=1,column=1,sticky='ew')
        self.model_combo=self.combo(f,self.model,self.model_options());self.model_combo.grid(row=2,column=1,sticky='ew')
        self.entry(f,self.endpoint).grid(row=3,column=1,sticky='ew')
        self.button(f,'Actualizar lista',self.refresh_models).grid(row=2,column=2,padx=(8,0))
        self.button(f,'Sugerido',lambda:self.model.set(PROVIDERS[self.provider.get()])).grid(row=0,column=2,padx=(8,0))
        cb=ttk.Checkbutton(f,text='Incluir esta ruta en la rotación automática (excepto Ollama)',variable=self.auto);cb.grid(row=4,column=0,columnspan=3,sticky='w',pady=8);self.widgets.append(cb)
        self.route_tree=ttk.Treeview(f,columns=('provider','account','model','auto'),show='headings',height=5,selectmode='browse')
        for col,title,width in (('provider','Proveedor',95),('account','Cuenta',120),('model','Modelo',270),('auto','Rotación',65)):
            self.route_tree.heading(col,text=title);self.route_tree.column(col,width=width,minwidth=50)
        self.route_tree.grid(row=5,column=0,columnspan=3,sticky='nsew');self.route_tree.bind('<ButtonRelease-1>',lambda e:self.load_route())
        for key in ('Up','Down','Home','End','Return'):self.route_tree.bind('<KeyRelease-'+key+'>',lambda e:self.load_route())
        row=ttk.Frame(f);row.grid(row=6,column=0,columnspan=3,sticky='ew',pady=(8,0))
        for text,fn in [('Guardar ruta',self.save_route),('Guardar y usar',self.use_route),('Quitar',self.remove_route),('Activar/desactivar',self.toggle_route),('↑',lambda:self.move(-1)),('↓',lambda:self.move(1))]:self.button(row,text,fn,style='Accent.TButton' if text=='Guardar y usar' else 'TButton').pack(side='left',padx=(0,5))
        ttk.Label(f,text='Una cuenta puede usarse en varias rutas. Guardar un modelo nuevo conserva los anteriores. Los modelos de catálogo no participan hasta que los guardes con cuenta.',wraplength=710,style='Muted.TLabel').grid(row=7,column=0,columnspan=3,sticky='w',pady=(8,0))
    def build_accounts(self):
        f=self.accounts_tab;f.columnconfigure(1,weight=1);f.rowconfigure(7,weight=1)
        self.ap=tk.StringVar(value='Groq');self.alias=tk.StringVar();self.secret=tk.StringVar();self.remember=tk.BooleanVar(value=False);self.account_id=None;self.account_enabled=tk.BooleanVar(value=True);self.copilot_mode=tk.StringVar(value='Escritorio M365')
        self.combo(f,self.copilot_mode,['Escritorio M365','Acceso con Edge'],True).grid(row=0,column=2,padx=(6,0))
        ttk.Label(f,text='Proveedor').grid(row=0,column=0,sticky='w');account_provider=self.combo(f,self.ap,[p for p in PROVIDERS if p!='Ollama'],True);account_provider.grid(row=0,column=1,sticky='ew')
        account_provider.bind('<<ComboboxSelected>>',lambda e:self.new_account())
        ttk.Label(f,text='Nombre de cuenta').grid(row=1,column=0,sticky='w',pady=5);self.entry(f,self.alias).grid(row=1,column=1,sticky='ew')
        cb=ttk.Checkbutton(f,text='Cuenta habilitada',variable=self.account_enabled);cb.grid(row=2,column=2);self.widgets.append(cb)
        self.api_label=ttk.Label(f,text='API key');self.api_label.grid(row=2,column=0,sticky='w')
        self.api_entry=self.entry(f,self.secret,show='●');self.api_entry.grid(row=2,column=1,sticky='ew')
        self.remember_cb=ttk.Checkbutton(f,text='Recordar con cifrado de Windows (DPAPI); desmarcado = solo sesión',variable=self.remember);self.remember_cb.grid(row=3,column=0,columnspan=2,sticky='w',pady=8);self.widgets.append(self.remember_cb)
        row=ttk.Frame(f);row.grid(row=4,column=0,columnspan=2,sticky='ew')
        for text,fn in [('Nueva cuenta',self.new_account),('Guardar cuenta',self.save_account),('Eliminar cuenta',self.remove_account),('Conectar escritorio M365',self.connect_copilot)]:
            b=self.button(row,text,fn,style='Accent.TButton' if text=='Guardar y usar' else 'TButton');b.pack(side='left',padx=(0,5))
            if text=='Guardar cuenta':self.save_account_button=b
        self.probe=tk.StringVar(value='')
        ttk.Label(f,textvariable=self.probe,wraplength=710,style='Muted.TLabel').grid(row=5,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Button(f,text='Copiar mensaje de conexión',command=self.copy_probe).grid(row=6,column=0,columnspan=2,sticky='w')
        self.account_tree=ttk.Treeview(f,columns=('provider','alias','storage','state'),show='headings',height=4,selectmode='browse')
        for col,title,width in [('provider','Proveedor',110),('alias','Cuenta',200),('storage','Credencial',130),('state','Estado',180)]:self.account_tree.heading(col,text=title);self.account_tree.column(col,width=width,minwidth=60)
        self.account_tree.grid(row=7,column=0,columnspan=2,sticky='nsew',pady=(10,0));self.account_tree.bind('<<TreeviewSelect>>',lambda e:self.load_account())
        ttk.Label(f,text='No se guardan claves en proyectos ni en registros. No se crean cuentas, activan pagos ni se recargan saldos. Microsoft y otros proveedores pueden aplicar sus propias condiciones y permisos.',wraplength=710,style='Muted.TLabel').grid(row=8,column=0,columnspan=2,sticky='w',pady=8)
        self.sync_account_provider()
    def sync_account_provider(self):
        """Copilot365 is a session connector, not an API key: never ask for one.

        The visible form must match the selected provider so choosing Copilot365
        cannot look like a demand for a key, token or URL from the user.
        """
        copilot=self.ap.get()=='Copilot365'
        if copilot:
            self.api_label.grid_remove();self.api_entry.grid_remove();self.secret.set('')
            self.remember_cb.configure(text='Recordar la conexión con cifrado de Windows (DPAPI); desmarcado = solo sesión')
            self.save_account_button.configure(text='Conectar / guardar M365')
            self.probe.set('Copilot365 NO usa API key: pulsa «Conectar escritorio M365» para vincular TU sesión de Microsoft 365. La cuenta se guarda sola. No pegues claves, tokens ni URLs.')
        else:
            self.api_label.grid(row=2,column=0,sticky='w');self.api_entry.grid(row=2,column=1,sticky='ew');self.api_entry.state(['!disabled'])
            self.remember_cb.configure(text='Recordar con cifrado de Windows (DPAPI); desmarcado = solo sesión')
            self.save_account_button.configure(text='Guardar cuenta')
            self.probe.set('Escribe la API key de tu proveedor. Copilot365 no la necesita: elige ese proveedor y pulsa «Conectar escritorio M365».')
    def build_policy(self):
        f=self.policy_tab;f.columnconfigure(0,weight=1)
        self.automatic=tk.BooleanVar(value=self.config.data.get('automatic',True));self.limit=tk.IntVar(value=self.config.data.get('attempt_limit',6));self.seconds=tk.IntVar(value=self.config.data.get('cycle_seconds',180))
        cb=ttk.Checkbutton(f,text='Rotación automática entre rutas configuradas y marcadas',variable=self.automatic);cb.grid(row=0,column=0,sticky='w');self.widgets.append(cb)
        ttk.Label(f,text='Orden: cuenta actual → otras cuentas del mismo modelo → otros modelos del proveedor → otros proveedores autorizados. Dentro de cada grupo se respeta el orden de las rutas. Ollama solo se elige manualmente y nunca salta a la nube.\n\nUna ruta sin conexión (Copilot365) o sin clave (API), con cuenta eliminada/desactivada, o con cifrado que no se puede abrir recibe cero llamadas. Las claves de solo sesión también sirven.\n\nLa rotación puede consumir cuota o saldo de todas las rutas que marques. Verifica sus precios: un ID no garantiza acceso gratuito. Nexo no activa planes, compras ni recargas. La autorización de destinatarios es por proyecto.\n\nErrores ambiguos después de enviar o de formato académico se detienen para que decidas. No se promete facturación exactamente una vez. Las cuotas pueden estar compartidas entre modelos o cuentas.',wraplength=710,justify='left').grid(row=1,column=0,sticky='w',pady=16)
        row=ttk.Frame(f);row.grid(row=2,column=0,sticky='w')
        ttk.Label(row,text='Intentos por ciclo (1–30)').pack(side='left');e=ttk.Spinbox(row,from_=1,to=30,textvariable=self.limit,width=5);e.pack(side='left',padx=10);self.widgets.append(e)
        ttk.Label(row,text='Presupuesto en segundos (10–600)').pack(side='left');e=ttk.Spinbox(row,from_=10,to=600,textvariable=self.seconds,width=6);e.pack(side='left',padx=10);self.widgets.append(e)
        self.button(f,'Guardar política',self.save_policy).grid(row=3,column=0,sticky='w',pady=14)
        ttk.Label(f,text='Copilot365: integración no oficial experimental. Solo se anuncia “auto”; el nombre real del modelo, licencia, cuota y funcionamiento con tu versión de escritorio no están certificados. No hay automatización del chat por DOM ni lectura general de cachés de credenciales.',wraplength=710,style='Muted.TLabel').grid(row=4,column=0,sticky='w',pady=8)
    def refresh(self):
        selected=self.route_tree.selection();self.route_tree.delete(*self.route_tree.get_children())
        for r in self.config.data['routes']:
            a=self.config.data['accounts'].get(r['account_id'],{});self.route_tree.insert('', 'end',iid=r['id'],values=(r['provider'],a.get('alias','Local' if r['provider']=='Ollama' else 'Sin cuenta'),r['model']+(' [desactivada]' if not r.get('enabled') else ''),'Sí' if r.get('auto') and r.get('enabled') else 'No'))
        if selected and self.route_tree.exists(selected[0]):self.route_tree.selection_set(selected[0])
        self.account_tree.delete(*self.account_tree.get_children())
        for aid,a in self.config.data['accounts'].items():
            try:usable=bool(self.config.secret(aid))
            except Exception:usable=False
            state='Acceso rechazado' if self.config.data['health'].get(aid)=='auth' else ('Respuesta recibida' if self.config.data['health'].get(aid)=='ok' and usable else 'Lista; no verificada' if usable and a.get('enabled') else 'Sin credencial utilizable')
            self.account_tree.insert('','end',iid=aid,values=(a['provider'],a['alias'],'DPAPI' if a.get('secret') else 'Solo sesión',state))
        self.refresh_accounts();self.app.update_provider()
    def model_options(self):
        provider=self.provider.get()
        return list(dict.fromkeys([PROVIDERS[provider]]+[m['id'] for m in self.config.data.get('catalog',{}).get(provider,[])]+[r['model'] for r in self.config.data['routes'] if r['provider']==provider]))
    def focus_account(self,aid):
        a=self.config.data['accounts'][aid];rid=self.config.ensure_account_route(aid)
        self.refresh();self.provider.set(a['provider']);self.refresh_accounts()
        if rid:
            self.route_tree.selection_set(rid);self.route_tree.focus(rid);self.route_tree.see(rid);self.load_route()
        else:self.model.set(PROVIDERS[a['provider']])
        self.model_combo.configure(values=self.model_options());self.tabs.select(self.routes_tab)
        self.account_choice.set(next((label for label,account in self.account_map.items() if account==aid),''))
    def refresh_accounts(self):
        self.account_map={a['alias']+' · '+aid[:6]:aid for aid,a in self.config.data['accounts'].items() if a['provider']==self.provider.get() and a.get('enabled')}
        old=self.account_choice.get();self.account_combo.configure(values=list(self.account_map));self.account_choice.set(old if old in self.account_map else next(iter(self.account_map),''))
    def change_provider(self):
        self.model.set(PROVIDERS[self.provider.get()]);self.model_combo.configure(values=self.model_options());self.refresh_accounts()
        if self.provider.get()=='Ollama':self.auto.set(False)
    def selected_route(self):
        sel=self.route_tree.selection()
        if not sel:raise ValueError('Selecciona una ruta guardada.')
        return next(r for r in self.config.data['routes'] if r['id']==sel[0])
    def load_route(self):
        if self.working:return
        try:r=self.selected_route()
        except ValueError:return
        self.provider.set(r['provider']);self.model.set(r['model']);self.endpoint.set(r.get('endpoint') or 'http://127.0.0.1:11434');self.auto.set(bool(r.get('auto')));self.refresh_accounts()
        self.account_choice.set(next((name for name,aid in self.account_map.items() if aid==r['account_id']),''));self.model_combo.configure(values=self.model_options())
    def copilot_account_ready(self,aid):
        """A Copilot account is usable only while its observed connection is readable."""
        if not aid:return False
        try:return bool((self.config.secret(aid) or '').strip())
        except Exception:return False
    def offer_copilot_connection(self):
        """Do not ask for an API key: send the user to the one-time M365 connection."""
        text=('Copilot365 no usa API key ni credenciales que tengas que escribir.\n\n'
              'Nexo se conecta a TU sesión de Microsoft 365 Copilot: hay que pulsar '
              '«Conectar escritorio M365» una vez y enviar la frase de prueba en un chat nuevo.\n\n'
              '¿Abrir ahora esa conexión?')
        if not messagebox.askyesno('Copilot365 · sin API key',text,parent=self.win):
            self.note.set('Copilot365 necesita una conexión a tu sesión de M365. En Cuentas pulsa «Conectar escritorio M365»; no hay API key que introducir.');return None
        self.tabs.select(self.accounts_tab);self.new_account();self.ap.set('Copilot365');self.sync_account_provider()
        if not self.alias.get().strip():self.alias.set('Microsoft 365')
        self.connect_copilot();return None
    def save_route(self):
        provider=self.provider.get();aid=self.account_map.get(self.account_choice.get(),'');model=self.model.get().strip();ep=self.endpoint.get().strip()
        if provider=='Copilot365' and not self.copilot_account_ready(aid):return self.offer_copilot_connection()
        old=next((r for r in self.config.data['routes'] if r['provider']==provider and r['model']==model.removeprefix('models/') and r['account_id']==aid and (provider!='Ollama' or r['endpoint']==ep)),None)
        rid=self.config.route(provider,model,aid,ep,self.auto.get(),old['id'] if old else None)
        self.refresh();self.route_tree.selection_set(rid);self.load_route();self.note.set('Ruta guardada. Guardar y usar la selecciona para conversar.');return rid
    def use_route(self):
        rid=self.save_route()
        if not rid:return
        self.config.select(rid);self.app.update_provider();self.note.set('En uso: '+self.provider.get()+' / '+self.account_choice.get()+' / '+self.model.get()+'. Puedes cerrar esta ventana y conversar en el mismo proyecto.')
    def remove_route(self):
        r=self.selected_route()
        if not messagebox.askyesno('Quitar ruta','¿Quitar esta ruta? La cuenta y la conversación se conservan.',parent=self.win):return
        with edit(self.config):self.config.data['routes'].remove(r);self.config.flush()
        self.refresh()
    def toggle_route(self):
        r=self.selected_route()
        with edit(self.config):r['enabled']=not r.get('enabled',True);self.config.flush()
        self.refresh()
    def move(self,delta):
        r=self.selected_route();items=self.config.data['routes'];i=items.index(r);j=max(0,min(len(items)-1,i+delta))
        with edit(self.config):items.insert(j,items.pop(i));self.config.flush()
        self.refresh()
    def load_account(self):
        if self.working:return
        sel=self.account_tree.selection()
        if not sel:return
        self.account_id=sel[0];a=self.config.data['accounts'][self.account_id];self.ap.set(a['provider']);self.alias.set(a['alias']);self.remember.set(bool(a.get('secret')));self.secret.set('');self.account_enabled.set(a.get('enabled',True))
        self.sync_account_provider()
        self.note.set('Conexión de Copilot365 conservada. Si caducó, pulsa «Conectar escritorio M365» para renovarla; no hay API key.' if a['provider']=='Copilot365' else 'Deja la clave vacía para conservarla. Guardar también rehabilita una cuenta con acceso rechazado.')
    def new_account(self):
        self.account_id=None;self.alias.set('');self.secret.set('');self.remember.set(False);self.account_enabled.set(True);self.account_tree.selection_remove(*self.account_tree.selection())
        self.sync_account_provider()
    def save_account(self):
        if self.ap.get()=='Copilot365':
            # No key to paste. Reuse a readable connection or (re)start the M365 flow.
            key=''
            if self.account_id:
                try:key=self.config.secret(self.account_id) or ''
                except Exception:key=''
            if not key.strip():self.connect_copilot();return
            self.account_id=self.config.account('Copilot365',self.alias.get(),key.strip(),self.remember.get(),self.account_id,self.account_enabled.get())
            self.secret.set('');self.focus_account(self.account_id)
            self.note.set('Cuenta Copilot actualizada. No se introdujo ninguna API key. Pulsa Guardar y usar para conversar.');return
        key=self.secret.get().strip() or (self.config.secret(self.account_id) if self.account_id else '')
        self.account_id=self.config.account(self.ap.get(),self.alias.get(),key,self.remember.get(),self.account_id,self.account_enabled.get());self.secret.set('');self.focus_account(self.account_id);self.note.set('Cuenta disponible con modelo sugerido (no verificado). Elige otro modelo si corresponde y pulsa Guardar y usar. No se activó la rotación ni se hizo una consulta.')
    def remove_account(self):
        if not self.account_id:raise ValueError('Selecciona una cuenta.')
        if messagebox.askyesno('Eliminar cuenta','¿Eliminar esta credencial? Las rutas vinculadas quedarán sin cuenta y no recibirán llamadas.',parent=self.win):self.config.remove_account(self.account_id);self.new_account();self.refresh()
    def save_policy(self):
        n=self.limit.get();t=self.seconds.get()
        if not 1<=n<=30 or not 10<=t<=600:raise ValueError('Revisa los límites indicados.')
        with edit(self.config):self.config.data.update(automatic=self.automatic.get(),attempt_limit=n,cycle_seconds=t);self.config.flush()
        self.note.set('Política guardada; solo se usan rutas configuradas y autorizadas.')
    def async_job(self,fn,done):
        self.working=True;self.cancel.clear();self.cancel_button.state(['!disabled'])
        for w in self.widgets:w.state(['disabled'])
        q=queue.Queue()
        def run():
            try:q.put((fn(),None))
            except Exception as e:q.put((None,e))
        threading.Thread(target=run,daemon=True).start()
        def poll():
            if not self.win.winfo_exists():return
            try:
                while True:self.note.set(self.progress.get_nowait())
            except queue.Empty:pass
            try:value,error=q.get_nowait()
            except queue.Empty:self.async_timer=self.win.after(100,poll);return
            self.working=False;self.cancel_button.state(['disabled'])
            for w in self.widgets:
                w.state(['!disabled'])
                if isinstance(w,ttk.Combobox):w.configure(state='readonly' if getattr(w,'_readonly',False) else 'normal')
            if self.ap.get()=='Copilot365':self.api_entry.state(['disabled'])  # keep the key field closed for Copilot
            if error:self.note.set(self.config.redact(error));return
            try:done(value)
            except Exception as e:self.note.set(self.config.redact(e))
        self.async_timer=self.win.after(100,poll)
    def refresh_models(self):
        provider=self.provider.get();aid=self.account_map.get(self.account_choice.get(),'');key=self.config.secret(aid) if aid else '';ep=self.endpoint.get()
        self.note.set('Consultando modelos disponibles; no se está generando texto…')
        def done(models):
            self.model_combo.configure(values=[m['id'] for m in models]);self.note.set(f'{len(models)} modelos publicados por {provider}. Selecciona uno o escribe su ID y guarda la ruta. Publicación no garantiza acceso ni gratuidad.')
            with edit(self.config):self.config.data.setdefault('catalog',{})[provider]=models;self.config.flush()
        self.async_job(lambda:list_models(provider,key,ep),done)
    def copy_probe(self):
        if not hasattr(self,'probe_text'):self.note.set('Inicia Conectar escritorio M365 para crear una frase de prueba.');return
        self.win.clipboard_clear();self.win.clipboard_append(self.probe_text)
    def connect_copilot(self):
        if self.ap.get()!='Copilot365':raise ValueError('Selecciona Copilot365 como proveedor de la cuenta.')
        from copilot_socket import launch_desktop,launch_auth_window,capture_connection
        import process_guard
        process_guard.start_tracking()
        mode=self.copilot_mode.get()
        intro=('Cierra primero Microsoft 365 Copilot.' if mode=='Escritorio M365' else 'Se abrirá Microsoft Edge en un perfil separado de Nexo. Sus cookies de inicio de sesión pueden persistir; cierra sesión allí si no deseas conservarlas.')
        if not messagebox.askyesno('Conexión experimental a tu sesión',intro+' Nexo intentará abrirlo con diagnóstico SOLO local y observará su conexión sin recargar la ventana ni borrar sus datos. Inicia sesión tú mismo; no compartas tu contraseña ni tokens.\n\nDespués copia la frase de prueba y envíala manualmente en un chat nuevo, sin archivos adjuntos. No se automatiza escribir o leer el chat. Se capturará únicamente la conexión que transporte esa frase.\n\nAl caducar la sesión, Nexo podrá observar una renovación si Microsoft la produce en esa ventana y mantiene la misma cuenta. Si no ocurre, pedirá reconectar; no recargará la ventana. Cierra Copilot al terminar para cerrar su puerto de diagnóstico. ¿Autorizar?',parent=self.win):return
        self.probe_text='Responde solo OK. NEXO CONEXION '+uuid.uuid4().hex[:12];self.probe.set(self.probe_text);self.copy_probe()
        self.note.set('Frase copiada. Espera a que cargue Copilot normalmente, abre un chat NUEVO y envíala allí manualmente. Límite: 3 minutos.')
        aid=self.account_id;alias=self.alias.get() or 'Microsoft 365';remember=self.remember.get();probe=self.probe_text;enabled=self.account_enabled.get()
        def work():
            try:
                return capture_connection(launch_desktop() if mode=='Escritorio M365' else launch_auth_window(self.app.store.root),probe=probe,stop=self.cancel,on_ready=lambda:self.progress.put('Observación preparada SIN recarga. Abre un chat NUEVO en Copilot y envía la frase copiada.'))
            finally:
                # A failed/cancelled capture must not leave a blank WebView2 window.
                process_guard.close_all()
        def done(secret):
            self.account_id=self.config.account('Copilot365',alias,secret,remember,aid,enabled);self.focus_account(self.account_id)
            self.note.set('Conexión observada y guardada SIN API key. Esto aún no confirma inferencia independiente. Copilot ya aparece en la lista. Pulsa Guardar y usar, cierra esta ventana y prueba una solicitud en Nexo.')
        self.async_job(work,done)
    def close(self):
        self.cancel.set();self.secret.set('');self.app.update_provider()
        try:
            import process_guard
            process_guard.close_all()
        except Exception:
            pass
        if self.async_timer:self.win.after_cancel(self.async_timer)
        self.win.destroy()
