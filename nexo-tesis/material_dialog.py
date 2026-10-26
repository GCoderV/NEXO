"""Local library UI; explicit sharing and explicit rule approval are separate actions."""
import hashlib,json,tkinter as tk
from tkinter import ttk,messagebox,filedialog
from tkinter.scrolledtext import ScrolledText
import materials,guide_rules
from project_store import message
from conversation_state import flag_rebind

class MaterialDialog:
    def __init__(self,app):
        self.app=app;self.win=tk.Toplevel(app.root);w=self.win;w.title('Archivos del proyecto · lectura y permisos');w.geometry('920x650');w.minsize(720,540);w.transient(app.root);w.grab_set();w.columnconfigure(0,weight=1);w.rowconfigure(2,weight=1);w.rowconfigure(4,weight=2)
        row=ttk.Frame(w,padding=10);row.grid(row=0,column=0,sticky='ew')
        self.role=tk.StringVar(value='guia');ttk.Label(row,text='Función del archivo:').pack(side='left');ttk.Combobox(row,textvariable=self.role,values=materials.ROLES,state='readonly',width=14).pack(side='left',padx=6)
        ttk.Button(row,text='Adjuntar archivo…',command=lambda:self.guard(self.add)).pack(side='left');ttk.Button(row,text='Revisar guía de Memoria',command=lambda:self.guard(self.memory_guide)).pack(side='left',padx=6)
        ttk.Label(w,text='Recepción local ≠ subida a Copilot. Solo se comparten extractos al autorizar sus destinatarios. PDF escaneado e imágenes: OCR pendiente.',wraplength=680).grid(row=1,column=0,sticky='w',padx=10)
        self.tree=ttk.Treeview(w,columns=('role','state','version','share'),show='tree headings',height=6);self.tree.heading('#0',text='Archivo');self.tree.column('#0',width=270)
        for k,t,width in [('role','Función',85),('state','Extracción',150),('version','Versión',55),('share','Permiso',120)]:self.tree.heading(k,text=t);self.tree.column(k,width=width)
        self.tree.grid(row=2,column=0,sticky='nsew',padx=10,pady=6);self.tree.bind('<<TreeviewSelect>>',lambda e:self.show())
        row=ttk.Frame(w);row.grid(row=3,column=0,sticky='w',padx=10)
        for text,fn in [('Autorizar extractos',self.share),('Revocar',self.revoke),('Revisar requisitos',self.rules),('Retirar versión',self.retire)]:ttk.Button(row,text=text,command=lambda f=fn:self.guard(f)).pack(side='left',padx=3)
        self.text=ScrolledText(w,wrap='word',height=12);self.text.grid(row=4,column=0,sticky='nsew',padx=10,pady=8);app.text_menu(self.text)
        foot=ttk.Frame(w);foot.grid(row=5,column=0,pady=8)
        ttk.Button(foot,text='Restaurar perfil APA base',command=lambda:self.guard(self.clear_profile)).pack(side='left',padx=8)
        ttk.Button(foot,text='Cerrar',command=self.close).pack(side='left');w.protocol('WM_DELETE_WINDOW',self.close);self.refresh()
    def clear_profile(self):
        if messagebox.askyesno('Restaurar base APA','Se dejarán de aplicar las reglas seleccionadas de la guía en próximas operaciones. No cambia Word ahora ni elimina archivos. ¿Restaurar perfil APA base?',parent=self.win):
            self.app.project.pop('format_profile',None);self.app.store.save(self.app.project,'guide-profile-cleared')
    def guard(self,fn):
        if self.app.busy:return
        try:fn()
        except Exception as e:messagebox.showerror('Archivos',str(e),parent=self.win)
    def close(self):
        if self.app.busy:self.app.status.set('Espera a que termine la lectura del archivo; no se enviará automáticamente.');return
        self.win.destroy()
    def selected(self):
        ids=self.tree.selection()
        if not ids:raise ValueError('Selecciona un archivo.')
        return next(m for m in self.app.project.get('materials',[]) if m['id']==ids[0])
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for m in self.app.project.get('materials',[]):self.tree.insert('','end',iid=m['id'],text=m['ref']+' · '+m['name']+(' (retirado)' if not m.get('active') else ''),values=(m['role'],m['status'],m['version'],'extractos permitidos' if m.get('shared_routes') else 'solo local'))
    def show(self):
        try:
            m=self.selected();data=materials.content(self.app.store.root,self.app.project,m)
            text=f"{m['name']} · {m['ref']} · versión {m['version']}\nEstado: {m['status']} · unidades con texto: {m['read_units']}/{m['units']}\nOriginal conservado; NO subido a Copilot.\n\n"+'\n'.join(data['warnings'])+'\n\n'+'\n\n'.join('['+s['locator']+']\n'+s['text'] for s in data['segments'])
            self.app.put(self.text,text,True)
        except (ValueError,OSError):pass
    def add(self):
        path=filedialog.askopenfilename(parent=self.win,title='Adjuntar material al proyecto',filetypes=[('Documentos e imágenes','*.pdf *.docx *.txt *.md *.xlsx *.csv *.tsv *.pptx *.png *.jpg *.jpeg'),('Todos','*.*')])
        if not path:return
        if not messagebox.askyesno('Lectura local','Se copiará el archivo a la biblioteca local y se intentará extraer su texto. DOCX requiere Word nativo, abre la copia solo para lectura, deshabilita macros y no guarda. No se subirá a Microsoft ni a otro modelo. ¿Autorizar?',parent=self.win):return
        import copy
        from native_material import read_docx
        p=copy.deepcopy(self.app.project);role=self.role.get()
        def done(result):
            record,data=result;materials.attach(p,record);message(p,'system','Archivo '+record['ref']+' recibido localmente: '+record['status']+'. No subido a Copilot.');self.app.store.save(p,'material-imported');self.app.project=p;self.app.render();self.refresh();self.tree.selection_set(record['id']);self.show();self.app.status.set('Archivo recibido. Revisa extracción y permisos en Archivos.')
        self.app.run_job(lambda:materials.import_file(self.app.store.root,p,path,role,read_docx),done)
    def share(self):
        m=self.selected()
        if not m.get('characters'):raise ValueError('No hay texto extraído para compartir.')
        api=self.app.api_factory()
        if not self.app.authorize(api):return
        # authorize may save/deep-copy project dictionaries; reacquire selection.
        m=self.selected();grants=materials.scopes(api)
        if not messagebox.askyesno('Autorizar extractos','Los extractos seleccionados de '+m['name']+' podrán enviarse a TODAS las rutas actualmente autorizadas para esta ejecución, incluida su rotación. También autoriza el contexto de borradores y respuestas derivados. Una versión retirada no aporta extractos nuevos, solo procedencia ya guardada. No es una subida del archivo original. Si contiene datos identificables, anonimízalos primero. Las rutas nuevas requerirán autorizar este archivo de nuevo. ¿Permitir?',parent=self.win):return
        m['shared_routes']=grants;self.app.store.save(self.app.project,'material-sharing-approved');self.refresh();self.app.status.set('Permiso de extractos guardado; todavía no se hizo una llamada al modelo.')
    def rebind_notice(self,reason):
        flag_rebind(self.app.project,reason)
        message(self.app.project,'system',reason+' Nexo no abrirá otro chat en silencio: abre «Hilo Copilot» para decidir si necesitas un hilo limpio por privacidad.')
    def revoke(self):
        m=self.selected();m['shared_routes']=[]
        self.rebind_notice('Se revocaron los extractos de '+m['name']+'. Lo enviado permanece en el chat de Microsoft.')
        self.app.store.save(self.app.project,'material-sharing-revoked');self.refresh();self.app.status.set('Revocado para solicitudes futuras. No borra información enviada previamente ni conversaciones de Microsoft. Decide el hilo en «Hilo Copilot».')
    def retire(self):
        m=self.selected()
        if not messagebox.askyesno('Retirar versión','Se excluirá de futuras selecciones y perfiles. Su original queda local para conservar procedencia. No borra contenido ya enviado ni otras versiones. ¿Continuar?',parent=self.win):return
        m['active']=False;m['shared_routes']=[]
        self.rebind_notice('Se retiró '+m['name']+'. Lo enviado permanece en el chat de Microsoft; retirar no borra esa memoria.')
        self.app.store.save(self.app.project,'material-retired');self.refresh()
    def rules(self):
        m=self.selected()
        if m['role']!='guia' or not m.get('active'):raise ValueError('Selecciona una guía activa.')
        data=materials.content(self.app.store.root,self.app.project,m);self.open_rules(m,data['segments'])
    def memory_guide(self):
        text=self.app.project['facts'].get('guia',{}).get('value','')
        if not text:raise ValueError('No hay requisitos en Memoria → guía.')
        self.open_rules({'id':'memoria-guia','name':'guía aportada en Memoria','sha256':hashlib.sha256(text.encode()).hexdigest()},[{'locator':'Memoria → guía','text':text}])
    def open_rules(self,m,segments):
        candidates=guide_rules.proposals(segments)
        if not candidates:raise ValueError('No se detectaron candidatas de formato. El texto sigue disponible para revisión; no se inventó un perfil.')
        w=tk.Toplevel(self.win);w.title('Requisitos detectados · seleccionar y aprobar');w.geometry('820x540');w.minsize(680,450);w.transient(self.win);w.grab_set();w.columnconfigure(0,weight=1);w.rowconfigure(1,weight=1)
        ttk.Label(w,text='Selecciona SOLO las reglas aplicables (Ctrl/clic). Verifica ejemplos, excepciones y versión de la guía.\nDetección parcial: selecciona requisitos, no ejemplos. Campos no seleccionados: base APA. Mayúsculas: revisión manual.',wraplength=650).grid(row=0,column=0,padx=12,pady=10)
        tree=ttk.Treeview(w,columns=('value','source'),show='tree headings',selectmode='extended');tree.heading('#0',text='Regla');tree.heading('value',text='Valor');tree.heading('source',text='Ubicación');tree.grid(row=1,column=0,sticky='nsew',padx=12)
        for i,r in enumerate(candidates):tree.insert('','end',iid=str(i),text=guide_rules.LABELS[r['key']],values=(r['value'],r['locator']))
        evidence=ScrolledText(w,height=5,wrap='word');evidence.grid(row=2,column=0,sticky='ew',padx=12,pady=8)
        def show(e=None):self.app.put(evidence,'\n\n'.join(candidates[int(i)].get('strength','por confirmar')+' · ámbito: '+candidates[int(i)].get('scope','por confirmar')+'\n'+candidates[int(i)]['evidence'] for i in tree.selection()),True)
        tree.bind('<<TreeviewSelect>>',show)
        def accept():
            try:
                guide_rules.approve(self.app.project,m,candidates,[int(i) for i in tree.selection()]);self.app.store.save(self.app.project,'guide-rules-approved');w.destroy();self.win.grab_set();self.app.status.set('Reglas aprobadas para el plan y la vista previa de Word; todavía no se cambió el documento.')
            except Exception as e:messagebox.showerror('Requisitos',str(e),parent=w)
        ttk.Button(w,text='Aprobar reglas seleccionadas',command=accept).grid(row=3,column=0,pady=10)
