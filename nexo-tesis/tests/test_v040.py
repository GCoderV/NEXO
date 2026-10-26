import copy,hashlib,json,tempfile,threading,unittest,uuid,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from project_store import ProjectStore,set_fact,is_greeting
from materials import extract,import_file,attach,select,scopes,content
from guide_rules import proposals,approve,effective,DEFAULT
from agent import Agent,context,unpack,SYSTEM
from autonomy import plan,fingerprint
from copilot_socket import SignalDecoder,RS
from conversation_state import load,save,pending,resolve,keys
from test_core import FakeAPI,reply

def make_pdf(path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    w=PdfWriter();p=w.add_blank_page(600,800);font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
    text=DecodedStreamObject();text.set_data(b'BT /F1 12 Tf 40 740 Td (Times New Roman 12. Interlineado 1.5. Titulos 14.) Tj ET');p[NameObject('/Contents')]=w._add_object(text)
    with open(path,'wb') as f:w.write(f)

class MaterialTests(unittest.TestCase):
    def setUp(self):self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.s=ProjectStore(self.root);self.p=self.s.create('Lectura crítica');self.api=FakeAPI([])
    def tearDown(self):self.t.cleanup()
    def add(self,name='guide.txt',text='Times New Roman 12\nInterlineado 1.5\nTítulos 14 en mayúscula\nSubtítulos 14\nPapel A4\nCronograma de actividades'):
        f=self.root/name;f.write_text(text,encoding='utf-8');m,d=import_file(self.root,self.p,f,'guia');attach(self.p,m);return m,d
    def test_pdf_real_text_extraction(self):
        f=self.root/'guide.pdf';make_pdf(f);d=extract(f);self.assertEqual(d['read_units'],1);self.assertIn('Interlineado 1.5',d['segments'][0]['text']);self.assertEqual(d['segments'][0]['locator'],'página 1')
    def test_pdf_worker_works_without_installed_packages(self):
        f=self.root/'g.pdf';make_pdf(f);m,d=import_file(self.root,self.p,f,'guia');self.assertEqual(m['status'],'texto_extraido');self.assertTrue(d['segments'])
    def test_image_received_but_never_claimed_read(self):
        f=self.root/'image.png';f.write_bytes(b'fixture');d=extract(f);self.assertEqual(d['status'],'recibido_sin_texto');self.assertFalse(d['segments'])
    def test_docx_requires_native_word_and_accepts_injected_contract(self):
        f=self.root/'guide.docx';f.write_bytes(b'not parsed by Python')
        with self.assertRaises(ValueError):extract(f)
        d=extract(f,lambda p:{'total':1,'segments':[{'locator':'párrafo 1','text':'Guía real'}]});self.assertEqual(d['read_units'],1)
    def test_read_failure_retains_local_original_without_fake_content(self):
        m,d=self.add('bad.pdf','not PDF');self.assertEqual(m['status'],'error_lectura');self.assertFalse(d['segments']);self.assertTrue((self.root/'materials'/self.p['id']/m['id']/'original.pdf').exists())
    def test_no_material_text_leaves_without_grant(self):
        self.add(text='INFORMACION RESERVADA');self.assertEqual(select(self.root,self.p,'guía',scopes(self.api)),[])
    def test_grant_allows_extracts_but_not_new_route(self):
        m,_=self.add();m['shared_routes']=scopes(self.api)
        self.assertTrue(select(self.root,self.p,'guía',scopes(self.api)))
        self.api.model='other';self.assertEqual(select(self.root,self.p,'guía',scopes(self.api)),[])
    def test_rotation_requires_grant_for_every_possible_recipient(self):
        m,_=self.add();m['shared_routes']=scopes(self.api)
        self.assertEqual(select(self.root,self.p,'guía',scopes(self.api)+['new route']),[])
    def test_duplicate_not_copied_again(self):
        m,_=self.add();other,data=import_file(self.root,self.p,self.root/'guide.txt','guia');self.assertEqual(other['id'],m['id']);self.assertIsNone(data)
    def test_new_version_is_local_and_revokes_old_active_selection(self):
        m,_=self.add();m['shared_routes']=scopes(self.api);new,_=self.add(text='Nuevo documento.');self.assertFalse(m['active']);self.assertEqual(new['version'],2);self.assertEqual(new['shared_routes'],[])
    def test_guide_attachment_resolves_availability_question_not_user_facts(self):
        self.p['questions']=[{'key':'guia','status':'abierta'}];self.add();self.assertEqual(self.p['questions'][0]['status'],'respondida');self.assertNotIn('guia',self.p['facts'])
    def test_explicit_file_reference_prioritized(self):
        m,_=self.add(text='Guía genérica.');f=self.root/'data.txt';f.write_text('Datos específicos.',encoding='utf-8');n,_=import_file(self.root,self.p,f,'datos');attach(self.p,n)
        for x in (m,n):x['shared_routes']=scopes(self.api)
        self.assertEqual(select(self.root,self.p,'Usa D2',scopes(self.api))[0]['id'],'D2')
    def test_csv_preserves_row_locations_no_formula_execution(self):
        f=self.root/'data.csv';f.write_text('id,valor\n1,=SUM(A1:A2)',encoding='utf-8');d=extract(f);self.assertEqual(d['segments'][1]['locator'],'fila 2');self.assertIn('=SUM',d['segments'][1]['text'])
    def test_xlsx_reads_cached_cells_only(self):
        f=self.root/'data.xlsx'
        with zipfile.ZipFile(f,'w') as z:z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="2"><c r="B2"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>')
        d=extract(f);self.assertIn('B2=2',d['segments'][0]['text']);self.assertIn('no recalculado',d['segments'][0]['text'])
    def test_pptx_retains_slide_order(self):
        f=self.root/'slides.pptx'
        with zipfile.ZipFile(f,'w') as z:
            for n in (10,2):z.writestr(f'ppt/slides/slide{n}.xml',f'<p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Slide {n}</a:t></p>')
        self.assertIn('Slide 2',extract(f)['segments'][0]['text'])
    def test_xml_entities_are_rejected(self):
        f=self.root/'bad.xlsx'
        with zipfile.ZipFile(f,'w') as z:z.writestr('xl/worksheets/sheet1.xml','<!DOCTYPE x [<!ENTITY y "x">]><x/>')
        with self.assertRaises(ValueError):extract(f)
    def test_character_limit_is_visible(self):
        m,d=self.add(text='x'*110000);self.assertEqual(d['characters'],100000);self.assertEqual(m['status'],'extraccion_parcial')
    def test_rules_are_proposed_with_evidence_not_applied(self):
        m,d=self.add();r=proposals(d['segments']);self.assertNotIn('format_profile',self.p);self.assertIn(1.5,[x['value'] for x in r if x['key']=='spacing']);self.assertTrue(all(x['evidence'] and x['locator'] for x in r))
    def test_approved_profile_and_required_sections(self):
        m,d=self.add();r=proposals(d['segments']);approve(self.p,m,r,range(len(r)));v=effective(self.p)['effective'];self.assertEqual(v['spacing'],1.5);self.assertEqual(v['heading_size'],14);self.assertEqual(v['page_size'],'A4');self.assertIn('cronograma',[t['section'] for t in plan(self.p)[0]])
    def test_conflicting_rule_requires_choice(self):
        m,d=self.add(text='Interlineado 1.5\nInterlineado doble');r=proposals(d['segments'])
        with self.assertRaisesRegex(ValueError,'contradictorios'):approve(self.p,m,r,range(len(r)))
    def test_replaced_guide_invalidates_profile_before_word(self):
        m,d=self.add();r=proposals(d['segments']);approve(self.p,m,r,range(len(r)));self.add(text='Guía diferente')
        with self.assertRaisesRegex(ValueError,'cambió'):effective(self.p)
    def test_material_reference_allowed_only_when_context_contains_it(self):
        m,_=self.add();m['shared_routes']=scopes(self.api);self.s.save(self.p)
        api=FakeAPI([reply(drafts=[{'section':'objetivos','text':'Propuesta basada en la guía [D1].','sources':['D1']}])]);p=Agent(self.s,api).turn(self.p['id'],'Usa la guía D1')
        self.assertIn('objetivos',p['drafts']);sent=json.loads(api.requests[0][0]['content']);self.assertIn('document_extracts',sent)
        self.assertNotIn(str(self.root),json.dumps(sent))
    def test_unshared_file_cannot_be_cited_as_received(self):
        self.add();self.s.save(self.p);api=FakeAPI([reply(drafts=[{'section':'objetivos','text':'Propuesta [D1].','sources':['D1']}])]);p=Agent(self.s,api).turn(self.p['id'],'Continúa');self.assertNotIn('objetivos',p['drafts'])
    def test_file_content_never_becomes_user_decision(self):
        m,_=self.add(text='La población es de 999 estudiantes.');m['shared_routes']=scopes(self.api);self.s.save(self.p)
        api=FakeAPI([reply(facts=[{'key':'poblacion','value':'999','evidence':'999 estudiantes'}])]);p=Agent(self.s,api).turn(self.p['id'],'Lee D1');self.assertNotIn('poblacion',p['facts'])

class RefactorTests(unittest.TestCase):
    def test_prompt_reduced_and_specific_contract(self):
        import zipfile
        from prompt_policy import instructions
        self.assertLess(len(SYSTEM),2200);self.assertLess(len(instructions({'section':'objetivos'})),1800)
    def test_task_contract_accepts_minimal_payload(self):
        r=unpack('{"text":"Un objetivo concreto.","sources":[]}',{'section':'objetivos'});self.assertEqual(r['drafts'][0]['section'],'objetivos')
    def test_answered_questions_not_repeated_in_context(self):
        with tempfile.TemporaryDirectory() as d:
            p=ProjectStore(d).create('Tema');p['questions']=[{'key':'nivel','text':'QUESTION_OLD','status':'respondida','id':'PRIVATE_ID','time':'LONG_DATE'}]
            c=json.loads(context(p,'Sigue'));self.assertEqual(c['questions'],[]);self.assertIn('nivel',c['answered_or_deferred']);self.assertNotIn('PRIVATE_ID',json.dumps(c))
    def test_requested_full_draft_not_sliced(self):
        with tempfile.TemporaryDirectory() as d:
            p=ProjectStore(d).create('Tema');p['drafts']['objetivos']={'text':'abcdefghij'*400,'status':'borrador'}
            c=json.loads(context(p,'Revisa los objetivos'));self.assertEqual(c['recent_drafts']['objetivos']['text'],p['drafts']['objetivos']['text'])
    def test_old_greeting_topic_flagged_without_renaming(self):
        with tempfile.TemporaryDirectory() as d:
            s=ProjectStore(d);p=s.create('hola');loaded=s.load(p['id']);self.assertEqual(loaded['topic'],'hola');self.assertTrue(loaded['topic_pending'])
    def test_format_guide_changes_do_not_invalidate_academic_content(self):
        with tempfile.TemporaryDirectory() as d:
            s=ProjectStore(d);p=s.create('Tema');s.update_draft(p,'objetivos','Objetivos válidos.');before=fingerprint(p,'text');set_fact(p,'guia','Interlineado 1.5')
            self.assertEqual(p['drafts']['objetivos']['status'],'borrador');self.assertEqual(before,fingerprint(p,'text'))
    def test_anteproyecto_does_not_generate_final_results_from_diagnostic(self):
        with tempfile.TemporaryDirectory() as d:
            p=ProjectStore(d).create('Tema');set_fact(p,'tipo_trabajo','anteproyecto');set_fact(p,'datos','Diagnóstico real');p['data_ready']=True
            self.assertFalse({'resultados','discusion','conclusiones'} & {x['section'] for x in plan(p)[0]})

class ThreadAndReferencesTests(unittest.TestCase):
    def api(self,generation='g',identity=None):
        account={'generation':generation}
        if identity:account['identity']=identity
        return SimpleNamespace(routes=[{'provider':'Copilot365','account_id':'account','endpoint':'','model':'auto'}],config=SimpleNamespace(data={'accounts':{'account':account}}))
    def slot(self):return {'conversation':str(uuid.uuid4()),'session':str(uuid.uuid4()),'turns':1,'token':'NEVER_STORE'}
    def test_thread_persistence_is_default_not_opt_in(self):
        p={};save(p,self.api(),{'account':self.slot()});self.assertTrue(load(p,self.api()))
    def test_persistence_has_no_token_and_is_account_scoped(self):
        p={};save(p,self.api(),{'account':self.slot()});first=load(p,self.api())
        self.assertTrue(first);self.assertNotIn('NEVER_STORE',json.dumps(p))
        # Renewing the captured credential (new generation, same oid/tid) keeps the chat.
        self.assertEqual(load(p,self.api('renewed'))['account']['conversation'],first['account']['conversation'])
        # A different Microsoft account never shares the thread.
        self.assertEqual(load(p,self.api('g','b'*64)),{})
        self.assertFalse(load({},self.api()))
    def test_uncertain_response_keeps_ids_and_requires_explicit_decision(self):
        p={};save(p,self.api(),{'account':self.slot()});before=load(p,self.api())['account']['conversation']
        save(p,self.api(),{},True)
        self.assertEqual(load(p,self.api())['account']['conversation'],before)
        self.assertEqual(pending(p,self.api())['kind'],'uncertain')
        self.assertFalse(p.get('copilot_ledger'))
        resolve(p,self.api(),'keep')
        self.assertIsNone(pending(p,self.api()))
    def test_no_rotation_at_40_turns(self):
        p={};slot=self.slot();slot['turns']=40;save(p,self.api(),{'account':slot});self.assertTrue(load(p,self.api()))
        slot['turns']=4000;save(p,self.api(),{'account':slot});self.assertEqual(load(p,self.api())['account']['turns'],4000)
    def test_citations_retained_without_changing_text_or_leaking_query(self):
        d=SignalDecoder();d.consume({'type':1,'arguments':[{'messages':[{'author':'bot','text':'Respuesta','sourceAttributions':[{'displayName':'Fuente','seeMoreUrl':'https://example.org/paper?token=SECRET','referenceId':'1'},{'url':'javascript:alert(1)'}]}]}]});self.assertEqual(d.text(),'Respuesta');self.assertEqual(len(d.citations),1);self.assertNotIn('SECRET',json.dumps(d.citations));self.assertIn('no verificado',d.citations[0]['status'])
    def test_launch_and_capture_functions_unchanged(self):
        import ast,zipfile
        with zipfile.ZipFile('/home/user/nexo-tesis-v0.3.1-windows.zip') as z:old=z.read('Nexo-Tesis-0.3.1/copilot_socket.py').decode()
        new=Path('copilot_socket.py').read_text()
        def funcs(s):return {n.name:ast.get_source_segment(s,n) for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)}
        for name in ('launch_desktop','launch_auth_window','capture_connection','sanitize_frame'):self.assertEqual(funcs(old)[name],funcs(new)[name])

class ProvenanceTests(unittest.TestCase):
    setUp=MaterialTests.setUp
    tearDown=MaterialTests.tearDown
    add=MaterialTests.add
    def test_derived_private_text_is_not_sent_to_ungranted_route(self):
        m,_=self.add(text='PRIVATE_MATERIAL');m['shared_routes']=scopes(self.api);self.s.save(self.p)
        a=FakeAPI([reply(reply='PRIVATE_REPLY',drafts=[{'section':'objetivos','text':'PRIVATE_DRAFT','sources':[]}])]);p=Agent(self.s,a).turn(self.p['id'],'Lee D1');self.assertEqual(p['drafts']['objetivos']['material_ids'],['D1'])
        b=FakeAPI([reply()]);b.model='other';p=Agent(self.s,b).turn(p['id'],'Revisa los objetivos');payload=b.requests[0][0]['content'];self.assertNotIn('PRIVATE_',payload)
    def test_manual_draft_edit_keeps_material_provenance(self):
        self.p['drafts']['objetivos']={'text':'original','status':'borrador','material_ids':['D1']};self.s.update_draft(self.p,'objetivos','Revisión propia');self.assertEqual(self.p['drafts']['objetivos']['material_ids'],['D1'])
    def test_work_order_with_revoked_material_stops_before_call(self):
        from autonomy import order
        self.p['drafts']['objetivos']={'text':'PRIVATE_DRAFT','status':'borrador','producer':{'model':'test'},'material_ids':['D1']};self.s.save(self.p)
        a=FakeAPI([reply()]);p=Agent(self.s,a).turn(self.p['id'],'Revisa el apartado.',origin='autonomo',task=order(self.p,{'section':'objetivos','mode':'revisar','label':'Objetivos'}));self.assertFalse(a.requests);self.assertIn('sin permiso',p['messages'][-1]['text'])
    def test_example_rule_cannot_silently_become_requirement(self):
        m,d=self.add(text='Ejemplo: Arial 12');r=proposals(d['segments']);self.assertTrue(all(x['strength']=='ejemplo' for x in r))
        with self.assertRaisesRegex(ValueError,'ejemplo'):approve(self.p,m,r,range(len(r)))
    def test_specific_reference_scope_not_applied_to_whole_document(self):
        m,d=self.add(text='Referencias: Calibri 11');r=proposals(d['segments'])
        with self.assertRaisesRegex(ValueError,'ámbito'):approve(self.p,m,r,range(len(r)))

class AdditionalBoundaryTests(unittest.TestCase):
    def test_single_line_guide_keeps_body_and_titles_distinct(self):
        r=proposals([{'locator':'Memoria','text':'Times New Roman 12, interlineado 1,5, títulos 14, subtítulos 14'}]);p={'facts':{},'materials':[]};v=approve(p,{'name':'Guía','id':'x','sha256':'x'},r,range(len(r)))['effective'];self.assertEqual(v['body_size'],12);self.assertEqual(v['heading_size'],14);self.assertEqual(v['spacing'],1.5)
    def test_guide_original_change_blocks_format_validation(self):
        with tempfile.TemporaryDirectory() as d:
            s=ProjectStore(d);p=s.create('Tema');f=Path(d)/'g.txt';f.write_text('Interlineado 1.5');m,data=import_file(d,p,f,'guia');attach(p,m);r=proposals(data['segments']);approve(p,m,r,range(len(r)));original=Path(d)/'materials'/p['id']/m['id']/'original.txt';original.write_text('Modificado externamente')
            with self.assertRaisesRegex(ValueError,'cambió'):effective(p,d)
    def test_utf16_entity_declaration_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'bad.xlsx'
            with zipfile.ZipFile(f,'w') as z:z.writestr('xl/worksheets/sheet1.xml','<!DOCTYPE x [<!ENTITY a "b">]><x/>'.encode('utf-16'))
            with self.assertRaises(ValueError):extract(f)
