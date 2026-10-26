"""Academic panel: local first. The model receives nothing until the user sends.
Word mutations are host-approved comments only, not general shell tools.
"""
import copy
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from academic import (ProjectStore, ACTION_FIELDS, ACTION_LABELS, SOURCE_STATES,
                      audit, chat_context, render_report, new_source, percentage)
from word_bridge import WordBridge

FIELD_LABELS={
 'title':'Título','institution':'Universidad','level':'Nivel','area':'Área','method':'Metodología','period':'Período',
 'diagnosis':'Informe diagnóstico','oral_tasks':'Tareas orales realizadas','observations':'Observaciones y aclaraciones',
 'question':'Pregunta propuesta','general_objective':'Objetivo general propuesto','objectives':'Objetivos específicos — uno por línea',
 'hypothesis':'Hipótesis de acción propuesta'}

class AcademicWindow:
    def __init__(self,app,store=None,bridge=None):
        self.app=app;self.store=store or ProjectStore(app.store.root/'academic')
        self.data=self.store.load();self.saved_data=copy.deepcopy(self.data);self.busy=False;self.events=queue.Queue();self.controls=[];self.documents=[]
        self.bridge=bridge or WordBridge(app.store.root/'academic'/'word-audit.jsonl')
        self.window=tk.Toplevel(app.root);w=self.window
        w.title('Nexo · Tesis | piloto UCE');w.geometry('900x730');w.minsize(720,530);w.transient(app.root)
        w.columnconfigure(0,weight=1);w.rowconfigure(1,weight=1)
        top=ttk.Frame(w,padding=(14,12));top.grid(row=0,column=0,sticky='ew');top.columnconfigure(0,weight=1)
        ttk.Label(top,text='Tesis / investigación-acción',font=('Segoe UI',17,'bold')).grid(row=0,column=0,sticky='w')
        ttk.Label(top,text='Local · sin consumo de API al editar o comprobar · Word nativo pendiente de validación',wraplength=680).grid(row=1,column=0,columnspan=2,sticky='w',pady=(4,0))
        self.button(top,'Guardar expediente',self.save).grid(row=0,column=1,padx=(10,0))
        self.tabs=ttk.Notebook(w);self.tabs.grid(row=1,column=0,sticky='nsew',padx=14)
        self.build_project();self.build_evidence();self.build_plan();self.build_sources();self.build_review();self.build_word()
        footer=ttk.Frame(w,padding=12);footer.grid(row=2,column=0,sticky='ew');footer.columnconfigure(0,weight=1)
        self.status=tk.StringVar(value='Borrador precargado. Guarda para conservarlo en este PC.')
        self.status_label=ttk.Label(footer,textvariable=self.status,wraplength=390);self.status_label.grid(row=0,column=0,sticky='w')
        self.button(footer,'Exportar informe .md',self.export).grid(row=0,column=1)
        self.button(footer,'Cerrar',self.close).grid(row=0,column=2,padx=(6,0))
        w.protocol('WM_DELETE_WINDOW',lambda:self.guard(self.close));w.bind('<Configure>',self.resize);w.grab_set();self.timer=w.after(80,self.poll)
    def resize(self,event):
        if event.widget is self.window:self.status_label.configure(wraplength=max(230,event.width-350))
    def button(self,parent,text,command):
        b=ttk.Button(parent,text=text,command=lambda:self.guard(command));self.controls.append(b);return b
    def guard(self,fn):
        if self.busy:return
        try:return fn()
        except Exception as e:messagebox.showerror('Nexo Académico',str(e),parent=self.window)
    def tab(self,title):
        f=ttk.Frame(self.tabs,padding=10);self.tabs.add(f,text=title);return f
    def text(self,parent,height=6):
        t=ScrolledText(parent,wrap='word',height=height,font=('Segoe UI',10),undo=True)
        self.app.attach_text_menu(t);return t
    @staticmethod
    def put(t,value):t.delete('1.0','end');t.insert('1.0',value)
    def build_project(self):
        f=self.tab('Expediente');f.columnconfigure(0,weight=1);f.rowconfigure(3,weight=1)
        row=ttk.Frame(f);row.grid(row=0,column=0,sticky='ew',pady=(0,8))
        ttk.Label(row,text='Participantes del diagnóstico:').pack(side='left')
        self.participants=tk.StringVar(value=str(self.data['participants']));ttk.Entry(row,textvariable=self.participants,width=6).pack(side='left',padx=6)
        self.modality=tk.StringVar(value=self.data['modality']);ttk.Combobox(row,textvariable=self.modality,values=('pendiente','escrita','oral','escrita y oral'),state='readonly',width=17).pack(side='left')
        self.field='title';self.field_choice=tk.StringVar(value=FIELD_LABELS[self.field])
        c=ttk.Combobox(f,textvariable=self.field_choice,values=list(FIELD_LABELS.values()),state='readonly');c.grid(row=1,column=0,sticky='ew')
        c.bind('<<ComboboxSelected>>',lambda e:self.guard(self.change_field))
        ttk.Label(f,text='Los objetivos y la hipótesis son propuestas. No equivalen a aprobación del asesor.',wraplength=650).grid(row=2,column=0,sticky='w',pady=8)
        self.editor=self.text(f,12);self.editor.grid(row=3,column=0,sticky='nsew');self.put(self.editor,self.data[self.field])
        self.button(f,'Preparar diagnóstico en el chat',lambda:self.handoff('diagnosis')).grid(row=4,column=0,sticky='w',pady=(8,0))
    def commit_field(self):
        value=self.editor.get('1.0','end-1c')
        self.data[self.field]=[x.strip() for x in value.splitlines() if x.strip()] if self.field=='objectives' else value
    def change_field(self):
        self.commit_field();self.field=next(k for k,v in FIELD_LABELS.items() if v==self.field_choice.get())
        val=self.data[self.field];self.put(self.editor,'\n'.join(val) if isinstance(val,list) else val)
    def build_evidence(self):
        f=self.tab('Evidencias');f.columnconfigure(0,weight=1);f.rowconfigure(1,weight=1)
        ttk.Label(f,text='Observación, autopercepción y frecuencias permanecen separadas. No registra nombres de estudiantes.',wraplength=680).grid(row=0,column=0,sticky='w',pady=(0,8))
        self.evidence_tree=ttk.Treeview(f,columns=('kind','claim','count'),show='headings',height=7)
        for k,label,width in [('kind','Tipo',140),('claim','Hallazgo informado',360),('count','Frecuencia',150)]:
            self.evidence_tree.heading(k,text=label);self.evidence_tree.column(k,width=width,minwidth=80)
        self.evidence_tree.grid(row=1,column=0,sticky='nsew')
        self.evidence_tree.bind('<<TreeviewSelect>>',lambda e:self.show_evidence())
        self.evidence_detail=self.text(f,5);self.evidence_detail.grid(row=2,column=0,sticky='ew',pady=8);self.evidence_detail.config(state='disabled')
        self.button(f,'Editar evidencia / frecuencia real',self.edit_evidence).grid(row=3,column=0,sticky='w')
        self.refresh_evidence()
    def refresh_evidence(self):
        self.evidence_tree.delete(*self.evidence_tree.get_children())
        for e in self.data['evidence']:self.evidence_tree.insert('', 'end',iid=e['id'],values=(e['kind'],e['claim'],percentage(e)))
    def show_evidence(self):
        selected=self.evidence_tree.selection()
        if not selected:return
        e=next(e for e in self.data['evidence'] if e['id']==selected[0]);self.evidence_detail.config(state='normal')
        self.put(self.evidence_detail,e['detail']);self.evidence_detail.config(state='disabled')
    def edit_evidence(self):
        selected=self.evidence_tree.selection()
        if not selected:raise ValueError('Selecciona una evidencia.')
        item=next(e for e in self.data['evidence'] if e['id']==selected[0]);d=tk.Toplevel(self.window);d.title('Evidencia aportada');d.geometry('600x460');d.transient(self.window);d.grab_set()
        d.columnconfigure(1,weight=1);d.rowconfigure(2,weight=1)
        kind=tk.StringVar(value=item['kind']);claim=tk.StringVar(value=item['claim']);count=tk.StringVar(value='' if item['count'] is None else str(item['count']));den=tk.StringVar(value='' if item['denominator'] is None else str(item['denominator']))
        ttk.Label(d,text='Tipo').grid(row=0,column=0,padx=10,pady=8);ttk.Combobox(d,textvariable=kind,values=('autopercepción','observación docente','respuesta a prueba','documento aportado'),state='readonly').grid(row=0,column=1,sticky='ew',padx=10)
        ttk.Label(d,text='Hallazgo').grid(row=1,column=0,padx=10);ttk.Entry(d,textvariable=claim).grid(row=1,column=1,sticky='ew',padx=10)
        detail=self.text(d);detail.grid(row=2,column=0,columnspan=2,sticky='nsew',padx=10,pady=10);self.put(detail,item['detail'])
        r=ttk.Frame(d);r.grid(row=3,column=0,columnspan=2,pady=8)
        ttk.Label(r,text='Cantidad (vacío si no existe):').pack(side='left');ttk.Entry(r,textvariable=count,width=6).pack(side='left');ttk.Label(r,text=' de ').pack(side='left');ttk.Entry(r,textvariable=den,width=6).pack(side='left')
        def close():d.grab_release();d.destroy();self.window.grab_set()
        def apply():
            try:
                from academic import validate_project
                e={**item,'kind':kind.get(),'claim':claim.get(),'detail':detail.get('1.0','end-1c'), 'count':int(count.get()) if count.get().strip() else None,'denominator':int(den.get()) if den.get().strip() else None}
                test=copy.deepcopy(self.data);test['participants']=int(self.participants.get());test['evidence']=[e if v['id']==e['id'] else v for v in test['evidence']];validate_project(test)
                item.update(e);self.refresh_evidence();close()
            except Exception as err:messagebox.showerror('Revisar evidencia',str(err),parent=d)
        ttk.Button(d,text='Conservar en el borrador',command=apply).grid(row=4,column=0,columnspan=2,pady=8);d.protocol('WM_DELETE_WINDOW',close)
    def build_plan(self):
        f=self.tab('Plan de acción');f.columnconfigure(0,weight=1);f.rowconfigure(3,weight=1)
        self.action_index=0;self.action_field='activity'
        self.action_choice=tk.StringVar(value='Actividad 1');c=ttk.Combobox(f,textvariable=self.action_choice,values=[f'Actividad {i+1}' for i in range(len(self.data['actions']))],state='readonly');c.grid(row=0,column=0,sticky='ew');c.bind('<<ComboboxSelected>>',lambda e:self.guard(self.change_action))
        self.action_field_choice=tk.StringVar(value=ACTION_LABELS[2]);c=ttk.Combobox(f,textvariable=self.action_field_choice,values=ACTION_LABELS,state='readonly');c.grid(row=1,column=0,sticky='ew',pady=8);c.bind('<<ComboboxSelected>>',lambda e:self.guard(self.change_action))
        ttk.Label(f,text='Propuestas no ejecutadas. La duración queda pendiente: no se inventa un cronograma.',wraplength=680).grid(row=2,column=0,sticky='w',pady=(0,8))
        self.action_editor=self.text(f);self.action_editor.grid(row=3,column=0,sticky='nsew');self.put(self.action_editor,self.data['actions'][0]['activity'] if self.data['actions'] else '')
        self.action_links=tk.StringVar();ttk.Label(f,textvariable=self.action_links).grid(row=4,column=0,sticky='w',pady=6);self.show_action_links()
        self.button(f,'Preparar plan en el chat',lambda:self.handoff('plan')).grid(row=5,column=0,sticky='w')
    def commit_action(self):
        if self.data['actions']:self.data['actions'][self.action_index][self.action_field]=self.action_editor.get('1.0','end-1c')
    def change_action(self):
        self.commit_action()
        self.action_index=int(self.action_choice.get().split()[-1])-1
        self.action_field=ACTION_FIELDS[ACTION_LABELS.index(self.action_field_choice.get())]
        self.put(self.action_editor,self.data['actions'][self.action_index][self.action_field]);self.show_action_links()
    def show_action_links(self):
        self.action_links.set('Evidencias: '+', '.join(self.data['actions'][self.action_index]['evidence_ids']) if self.data['actions'] else 'Sin actividades.')
    def build_sources(self):
        f=self.tab('Fuentes');f.columnconfigure(0,weight=1);f.rowconfigure(3,weight=1)
        bar=ttk.Frame(f);bar.grid(row=0,column=0,sticky='ew');bar.columnconfigure(0,weight=1)
        self.source_index=None;self.source_field='title';self.source_choice=tk.StringVar()
        self.source_combo=ttk.Combobox(bar,textvariable=self.source_choice,state='readonly');self.source_combo.grid(row=0,column=0,sticky='ew');self.source_combo.bind('<<ComboboxSelected>>',lambda e:self.guard(self.change_source))
        self.button(bar,'Añadir fuente',self.add_source).grid(row=0,column=1,padx=(8,0))
        self.source_labels={'title':'Título','authors':'Autoría','year':'Año','url':'DOI / URL o referencia local','excerpt':'Fragmento consultado','locator':'Página / apartado','supports':'Afirmación que respalda'}
        self.source_field_choice=tk.StringVar(value='Título');c=ttk.Combobox(f,textvariable=self.source_field_choice,values=list(self.source_labels.values()),state='readonly');c.grid(row=1,column=0,sticky='ew',pady=8);c.bind('<<ComboboxSelected>>',lambda e:self.guard(self.change_source))
        self.source_state=tk.StringVar(value='pendiente');ttk.Combobox(f,textvariable=self.source_state,values=SOURCE_STATES,state='readonly').grid(row=2,column=0,sticky='ew',pady=(0,8))
        self.source_editor=self.text(f);self.source_editor.grid(row=3,column=0,sticky='nsew')
        ttk.Label(f,text='El estado lo declara quien registra la fuente. Nexo no verifica automáticamente que exista o respalde la afirmación. No genera bibliografía APA en esta versión.',wraplength=680).grid(row=4,column=0,sticky='w',pady=8)
        self.refresh_sources()
    def refresh_sources(self):
        values=[s['id'] for s in self.data['sources']];self.source_combo.configure(values=values)
        if self.source_index is None and values:self.source_index=0
        self.source_editor.configure(state='normal' if self.source_index is not None else 'disabled')
        if self.source_index is not None:
            s=self.data['sources'][self.source_index];self.source_choice.set(s['id']);self.source_state.set(s['state']);self.put(self.source_editor,s[self.source_field])
    def commit_source(self):
        if self.source_index is not None:
            s=self.data['sources'][self.source_index];s[self.source_field]=self.source_editor.get('1.0','end-1c');s['state']=self.source_state.get()
    def change_source(self):
        self.commit_source()
        if not self.data['sources']:return
        self.source_index=next(i for i,s in enumerate(self.data['sources']) if s['id']==self.source_choice.get())
        self.source_field=next(k for k,v in self.source_labels.items() if v==self.source_field_choice.get());self.refresh_sources()
    def add_source(self):
        self.commit_source();self.data['sources'].append(new_source());self.source_index=len(self.data['sources'])-1;self.refresh_sources()
    def build_review(self):
        f=self.tab('Guía y revisión');f.columnconfigure(0,weight=1);f.rowconfigure(1,weight=1)
        self.button(f,'Comprobar expediente',self.review).grid(row=0,column=0,sticky='w',pady=(0,8))
        self.review_text=self.text(f);self.review_text.grid(row=1,column=0,sticky='nsew');self.review_text.config(state='disabled')
    def review(self):
        self.gather();profile=json.loads((Path(__file__).parent/'academic_profile.json').read_text(encoding='utf-8'))
        lines=[profile['name'],profile['status'],profile['source'],profile['scope'],'']
        for c in profile['chapters']:lines += [c['title']+' (p. '+c['page']+')']+['  • '+s for s in c['sections']]+['']
        lines += ['FORMATO APORTADO']+profile['format']+['','POR ACLARAR']+profile['pending']+['','COMPROBACIONES LOCALES — no certifican calidad ni cumplimiento']
        lines += [f"[{i['level']}] {i['text']}" for i in audit(self.data)]
        self.review_text.config(state='normal');self.put(self.review_text,'\n'.join(lines));self.review_text.config(state='disabled');self.status.set('Comprobación local terminada. No se llamó a una API.')
    def build_word(self):
        f=self.tab('Word');f.columnconfigure(0,weight=1);f.rowconfigure(3,weight=1);f.rowconfigure(5,weight=1)
        ttk.Label(f,text='Piloto Windows: solo lectura de selección y comentarios aprobados. Abre una COPIA local .docx en Word. Guarda tú desde Word; AutoSave puede guardar automáticamente si está activo.',wraplength=680).grid(row=0,column=0,sticky='w')
        row=ttk.Frame(f);row.grid(row=1,column=0,sticky='ew',pady=8);row.columnconfigure(0,weight=1)
        self.document_choice=tk.StringVar();self.document_combo=ttk.Combobox(row,textvariable=self.document_choice,state='readonly');self.document_combo.grid(row=0,column=0,sticky='ew');self.document_combo.bind('<<ComboboxSelected>>',lambda e:self.invalidate_word())
        self.button(row,'Buscar abiertos',self.list_word).grid(row=0,column=1,padx=4);self.button(row,'Confirmar y leer',self.read_word).grid(row=0,column=2)
        ttk.Label(f,text='Selección leída — no se envía al modelo:').grid(row=2,column=0,sticky='w')
        self.word_text=self.text(f,5);self.word_text.grid(row=3,column=0,sticky='nsew');self.word_text.config(state='disabled')
        ttk.Label(f,text='Comentario propuesto (edítalo; no sustituirá el texto):').grid(row=4,column=0,sticky='w',pady=(8,2))
        self.comment_text=self.text(f,5);self.comment_text.grid(row=5,column=0,sticky='nsew')
        self.button(f,'Revisar y añadir comentario',self.comment_word).grid(row=6,column=0,sticky='w',pady=(8,0))
    def invalidate_word(self):
        self.bridge.snapshot=None;self.bridge.path=None
        self.word_text.config(state='normal');self.put(self.word_text,'');self.word_text.config(state='disabled')
    def list_word(self):
        self.invalidate_word()
        def done(docs):
            self.documents=docs;self.document_combo.configure(values=[d['path'] for d in docs]);self.document_choice.set(docs[0]['path'] if docs else '')
            self.status.set(f'{len(docs)} documentos DOCX guardados encontrados. No se ha leído su contenido.')
        self.run_job(self.bridge.documents,done)
    def read_word(self):
        path=self.document_choice.get()
        if not path or not any(d['path']==path for d in self.documents):raise ValueError('Busca y selecciona un documento abierto.')
        if not messagebox.askyesno('Autorizar lectura local',f'Documento:\n{path}\n\nSelecciona texto en ese documento de Word y déjalo activo. ¿Autorizas leer SOLO esa selección? No se envía a una API.',parent=self.window):return
        self.bridge.bind(path)
        def done(s):
            self.word_text.config(state='normal');self.put(self.word_text,s['text']);self.word_text.config(state='disabled');self.status.set('Selección leída. Escribe y revisa el comentario; no cambies el documento ni la selección durante la operación.')
        self.run_job(self.bridge.read,done)
    def comment_word(self):
        if not self.bridge.snapshot:raise ValueError('Primero lee una selección del documento confirmado.')
        comment=self.comment_text.get('1.0','end-1c')
        if not comment.strip() or len(comment)>6000:raise ValueError('Escribe un comentario de 1 a 6000 caracteres.')
        # Freeze the exact comment before the approval dialog / worker.
        if not messagebox.askyesno('Aprobar comentario',f'Documento: {self.bridge.path}\n\nSe añadirá el comentario que acabas de revisar a la selección mostrada. No se reemplazará texto ni se aceptarán revisiones.\n\nNo edites Word durante esta operación. Si falla, inspecciona Word antes de repetir. ¿Aprobar?',parent=self.window):return
        def done(result):
            self.status.set('Comentario confirmado por Word. Puedes eliminarlo desde Revisar. Nexo no guardó ni cerró el documento; revisa AutoSave.')
        self.run_job(lambda:self.bridge.comment(comment,approved=True),done)
    def run_job(self,work,done):
        self.busy=True;self.status.set('Esperando a Word… No edites el documento durante la operación.')
        for b in self.controls:b.state(['disabled'])
        self.document_combo.configure(state='disabled')
        def worker():
            try:self.events.put((done,work(),None))
            except Exception as e:self.events.put((done,None,str(e)))
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:
            while True:
                done,result,error=self.events.get_nowait();self.busy=False
                for b in self.controls:b.state(['!disabled'])
                self.document_combo.configure(state='readonly')
                if error:
                    self.status.set('Operación no confirmada. Revisa Word antes de repetir.');messagebox.showerror('Conexión Word',error,parent=self.window)
                else:done(result)
        except queue.Empty:pass
        self.timer=self.window.after(80,self.poll)
    def gather(self):
        from academic import validate_project
        self.commit_field();self.commit_action();self.commit_source()
        try:self.data['participants']=int(self.participants.get())
        except ValueError:raise ValueError('Participantes debe ser un número entero.')
        self.data['modality']=self.modality.get();validate_project(self.data)
        return self.data
    def save(self):
        self.store.save(self.gather());self.saved_data=copy.deepcopy(self.data);self.status.set('Expediente guardado localmente. Copia anterior conservada; sin envío al modelo.')
    def export(self):
        report=render_report(self.gather())
        path=filedialog.asksaveasfilename(parent=self.window,title='Exportar informe de trabajo (no Word)',defaultextension='.md',filetypes=[('Markdown','*.md')],initialfile='Nexo-expediente-tesis.md')
        if not path:return
        if Path(path).suffix.lower()!='.md':raise ValueError('Este informe se exporta como .md, no como un documento de Word.')
        ProjectStore.atomic(Path(path),report.encode('utf-8'));self.status.set('Informe Markdown exportado. No es un archivo Word ni una tesis terminada.')
    def handoff(self,section):
        if self.app.busy:raise ValueError('Espera a que termine la tarea del chat.')
        text=chat_context(self.gather(),section)
        if self.app.input.get('1.0','end-1c').strip():raise ValueError('El chat tiene un borrador. Consérvalo o vacíalo antes; no se sobrescribió.')
        if not messagebox.askyesno('Preparar contexto para el chat','Se copiará este apartado al cuadro de mensaje. Podrás revisarlo antes de Enviar; al enviarlo lo recibirá el proveedor seleccionado. No se incluye la selección de Word.\n\nEl chat se dejará en Planificar y sin herramientas. ¿Continuar?',parent=self.window):return
        self.store.save(self.data)
        self.app.mode.set('PLAN');self.app.autonomous.set(False);self.app.broad.set(False)
        for k in ('files','shell','browser','desktop'):self.app.flags[k].set(False)
        self.app.update_mode();self.app.input.insert('1.0',text)
        self.destroy()
    def destroy(self):
        self.window.after_cancel(self.timer);self.window.grab_release();self.window.destroy();self.app.academic_window=None
    def close(self):
        if self.busy:raise ValueError('Espera a que termine la operación de Word (máximo aproximado: 35 s).')
        self.gather()
        changed=self.data!=self.saved_data
        if changed:
            answer=messagebox.askyesnocancel('Guardar expediente','¿Guardar los cambios locales antes de cerrar?',parent=self.window)
            if answer is None:return
            if answer:self.store.save(self.data)
        self.destroy()
