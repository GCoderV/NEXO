"""Mouse editing for Tk text/entry widgets. Paste never submits a task."""
import tkinter as tk
from tkinter import ttk

class ClipboardMixin:
    def clipboard_write(self,text):
        if not text:return False
        self.root.clipboard_clear();self.root.clipboard_append(text);self.root.update_idletasks()
        return True
    def selected_text(self,widget):
        try:
            if isinstance(widget,tk.Text):return widget.get('sel.first','sel.last')
            return widget.get()[int(widget.index('sel.first')):int(widget.index('sel.last'))]
        except tk.TclError:return ''
    def copy_selection(self,widget):return self.clipboard_write(self.selected_text(widget))
    def select_all(self,widget):
        if isinstance(widget,tk.Text):widget.tag_add('sel','1.0','end-1c')
        else:widget.selection_range(0,'end')
    def editable(self,widget):
        try:return str(widget.cget('state'))=='normal'
        except tk.TclError:return False
    def delete_selection(self,widget):
        try:
            if isinstance(widget,tk.Text):widget.delete('sel.first','sel.last')
            else:widget.delete('sel.first','sel.last')
        except tk.TclError:pass
    def paste_text(self,widget):
        if not self.editable(widget):return False
        try:text=self.root.clipboard_get()
        except tk.TclError:return False
        self.delete_selection(widget);widget.insert('insert',text);widget.focus_set()
        if widget is getattr(self,'input',None) and hasattr(self,'voice_flow'):self.voice_flow.cancel_pending()
        return True
    def cut_selection(self,widget):
        if self.editable(widget) and self.copy_selection(widget):self.delete_selection(widget)
    def message_at(self,index):
        for record in getattr(self,'chat_messages',[]):
            if self.log.compare(index,'>=',record['start']) and self.log.compare(index,'<',record['end']):return record
        return None
    def attach_text_menu(self,widget):
        if getattr(widget,'_nexo_menu_attached',False):return
        widget._nexo_menu_attached=True
        if isinstance(widget,tk.Text):widget.configure(exportselection=False)
        def popup(event):
            previous=getattr(self,'last_text_menu',None)
            if previous is not None and previous.winfo_exists():previous.destroy()
            menu=tk.Menu(widget,tearoff=False)
            selected=self.selected_text(widget)
            menu.add_command(label='Copiar selección',command=lambda:self.copy_selection(widget),state='normal' if selected else 'disabled')
            if widget is getattr(self,'log',None):
                record=self.message_at(widget.index(f'@{event.x},{event.y}'))
                if record:
                    menu.add_command(label='Copiar este mensaje',command=lambda:self.clipboard_write(record['text']))
                    if record['who']=='Nexo':menu.add_command(label='Leer este mensaje',command=lambda:self.read_response(record['text']))
            if self.editable(widget):
                menu.add_command(label='Cortar',command=lambda:self.cut_selection(widget),state='normal' if selected else 'disabled')
                menu.add_command(label='Pegar',command=lambda:self.paste_text(widget))
            menu.add_separator();menu.add_command(label='Seleccionar todo',command=lambda:self.select_all(widget))
            self.last_text_menu=menu  # Also used by the real-Tk regression tests.
            try:menu.tk_popup(event.x_root,event.y_root)
            finally:menu.grab_release()
            return 'break'
        widget.bind('<Button-3>',popup)
        widget.bind('<Shift-F10>',lambda e:popup(type('MenuEvent',(),{'x':0,'y':0,'x_root':widget.winfo_rootx()+12,'y_root':widget.winfo_rooty()+12})()))
    def attach_menus_tree(self,parent):
        for child in parent.winfo_children():
            if isinstance(child,(tk.Text,tk.Entry,ttk.Entry,ttk.Combobox)):self.attach_text_menu(child)
            self.attach_menus_tree(child)
    def response_actions(self,text):
        row=ttk.Frame(self.log,style='Chat.TFrame')
        ttk.Button(row,text='Copiar',command=lambda:self.clipboard_write(text)).pack(side='left')
        ttk.Button(row,text='Leer',command=lambda:self.read_response(text)).pack(side='left',padx=5)
        self.log.window_create('end',window=row);self.log.insert('end','\n\n')
        self.message_action_widgets.append(row)
