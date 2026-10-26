"""Preview and one-shot approval of native Word layout/placement operations."""
import copy
import tkinter as tk
from tkinter import ttk,messagebox
from tkinter.scrolledtext import ScrolledText
from project_store import SECTIONS,LABELS
from word_layout import preview,digest

class WordLayoutDialog:
    def __init__(self,app,state):
        self.app=app;self.state=state;self.plan=None;self.project=copy.deepcopy(app.project)
        w=self.win=tk.Toplevel(app.root);w.title('Organizar Word · ubicaciones, APA 7 e índice');w.geometry('900x690');w.minsize(720,560);w.transient(app.root);w.grab_set();w.columnconfigure(0,weight=1);w.rowconfigure(3,weight=1)
        ttk.Label(w,text=state['name'],font=('Segoe UI',13,'bold')).grid(row=0,column=0,sticky='w',padx=14,pady=(12,6))
        choices=ttk.Frame(w,padding=(14,0));choices.grid(row=1,column=0,sticky='ew');choices.columnconfigure(1,weight=1)
        self.format_all=tk.BooleanVar(value=True);self.index=tk.BooleanVar(value=True)
        ttk.Checkbutton(choices,text='Aplicar al documento completo el perfil aprobado (o APA 7 base)',variable=self.format_all).grid(row=0,column=0,columnspan=2,sticky='w')
        ttk.Checkbutton(choices,text='Crear o actualizar índice automático (niveles 1–3)',variable=self.index).grid(row=1,column=0,columnspan=2,sticky='w')
        ttk.Label(choices,text='Apartados para insertar (opcionales):\nCtrl/clic permite elegir varios.\nNo se sustituyen textos previos.',style='Muted.TLabel').grid(row=2,column=0,sticky='nw',padx=(0,12),pady=8)
        self.keys=[k for k in SECTIONS if k in self.project['drafts'] and self.project['drafts'][k]['status'] not in ('necesita_revision','insertado_pendiente_revision_word')]
        self.list=tk.Listbox(choices,height=4,selectmode='extended',exportselection=False);self.list.grid(row=2,column=1,sticky='ew',pady=8)
        for k in self.keys:self.list.insert('end',LABELS[k]+' · '+self.project['drafts'][k]['status'])
        origin=app.word_origin
        if origin and origin[0] in self.keys and app.word_proposal.get('1.0','end-1c')==self.project['drafts'][origin[0]]['text']:self.list.selection_set(self.keys.index(origin[0]))
        row=ttk.Frame(w,padding=(14,0));row.grid(row=2,column=0,sticky='ew')
        ttk.Button(row,text='Preparar vista previa',command=self.prepare).pack(side='left')
        ttk.Label(row,text='Usa los borradores guardados de Apartados; no envía el documento a un modelo.',style='Muted.TLabel',wraplength=500).pack(side='left',padx=10)
        self.text=ScrolledText(w,wrap='word',font=('Segoe UI',10),height=12);self.text.grid(row=3,column=0,sticky='nsew',padx=14,pady=10);app.text_menu(self.text);self.text.configure(state='disabled')
        self.note=tk.StringVar(value='Analizado localmente. Prepara la vista previa y revisa las ubicaciones antes de aprobar.')
        ttk.Label(w,textvariable=self.note,wraplength=680,style='Muted.TLabel').grid(row=4,column=0,sticky='w',padx=14)
        bottom=ttk.Frame(w,padding=14);bottom.grid(row=5,column=0,sticky='ew')
        self.apply_button=ttk.Button(bottom,text='Aprobar y aplicar conjunto',command=self.apply,style='Accent.TButton',state='disabled');self.apply_button.pack(side='left')
        self.index_button=ttk.Button(bottom,text='Solo actualizar índice',command=self.index_only,state='normal' if len(state.get('tocs',[]))==1 else 'disabled');self.index_button.pack(side='left',padx=6)
        ttk.Button(bottom,text='Cerrar sin aplicar',command=w.destroy).pack(side='right')
        self.format_all.trace_add('write',lambda *a:self.invalidate());self.index.trace_add('write',lambda *a:self.invalidate());self.list.bind('<<ListboxSelect>>',lambda e:self.invalidate())
    def index_only(self):
        if len(self.state.get('tocs',[]))!=1:
            self.note.set('Esta opción requiere un único índice automático existente.');return
        self.format_all.set(False);self.index.set(True);self.list.selection_clear(0,'end');self.prepare()
    def invalidate(self):
        self.plan=None;self.apply_button.state(['disabled']);self.note.set('Cambió la selección: prepara otra vista previa. Todavía no se modificó Word.')
    def prepare(self):
        try:
            __import__('guide_rules').effective(self.project,self.app.store.root)
            self.plan=self.app.bridge.prepare_layout(self.project,[self.keys[i] for i in self.list.curselection()],self.format_all.get(),self.index.get())
            self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0',preview(self.plan));self.text.configure(state='disabled');self.apply_button.state(['!disabled']);self.note.set('Revisa todo el conjunto. La conformidad bibliográfica APA y los elementos especiales requieren revisión.')
        except Exception as e:
            self.plan=None;self.apply_button.state(['disabled']);self.note.set(str(e))
    def apply(self):
        if not self.plan:return
        try:
            app=self.app;p=app.store.load(self.project['id'])
            if not app.project or app.project['id']!=p['id'] or p['revision']!=self.plan['project_revision']:raise ValueError('El proyecto cambió. Cierra esta ventana y analiza de nuevo.')
            __import__('guide_rules').effective(p,app.store.root)
            for op in self.plan['operations']:
                if digest(p['drafts'][op['section']]['text'])!=op['source_hash']:raise ValueError('Un borrador cambió. Prepara el plan otra vez.')
            if not messagebox.askyesno('Aplicar el conjunto revisado','Documento:\n'+self.plan['path']+'\n\nSe aplicará SOLO el conjunto visible. Las inserciones no reemplazan texto previo. No se aceptan revisiones ni se guarda el archivo desde Nexo; AutoSave de Word podría guardarlo. Formato/índice pueden no quedar enteramente representados por las revisiones: usa una COPIA.\n\nNo edites Word durante la operación. Si hay un error, puede quedar un efecto parcial; no se repetirá automáticamente. ¿Aprobar?',parent=self.win):return
            plan=copy.deepcopy(self.plan);id=p['id'];self.plan=None;self.win.destroy()
            def done(result):
                if not app.project or app.project['id']!=id:return
                for section in result.get('inserted',[]):
                    if section in app.project['drafts']:app.project['drafts'][section]['status']='insertado_pendiente_revision_word'
                app.project['word_path']=plan['path'];app.store.save(app.project,'word-layout-confirmed');app.load_draft()
                app.put(app.word_selection,'Estructura aplicada. Analiza otra vez para preparar más cambios.',True)
                app.status.set('Word confirmó el conjunto. Revisa formato, índice y revisiones en la COPIA; guarda desde Word cuando corresponda.')
            app.run_job(lambda:app.bridge.apply_layout(plan,True),done)
        except Exception as e:messagebox.showerror('Organizar Word',str(e),parent=self.win if self.win.winfo_exists() else self.app.root)
