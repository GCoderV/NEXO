import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from word_layout import build_plan,paragraphs,preview,headings,validate_state,digest
from word_bridge import WordBridge,WordError,encoded_native_command,native_script
from project_store import ProjectStore
from test_v02 import session
from test_providers import Response
from test_core import FakeWord
from copilot_socket import capture_connection,RS

def state(*texts,levels=None,tocs=None):
    rows=[];pos=0
    for i,text in enumerate(texts):
        end=pos+len(text.encode('utf-16-le'))//2+1
        rows.append({'start':pos,'end':end,'text':text[:240],'level':levels[i] if levels else 10,'truncated':len(text)>240,'table':False,'special':False,'style':'Normal','list':False});pos=end
    return {'path':r'C:\Copies\thesis.docx','name':'thesis.docx','hwnd':1,'end':pos,'hash':digest('\r'.join(texts)+'\r'),'structure_hash':digest(json.dumps(rows)),'paragraphs':rows,'tocs':tocs or [],'markers':[],'empty':not any(x.strip() for x in texts),'revisions':0,'page_number_present':False,'header_text_present':False}

class LayoutPlanningTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.s=ProjectStore(self.tmp.name);self.p=self.s.create('Topic')
    def tearDown(self):self.tmp.cleanup()
    def draft(self,key,text='Nuevo texto.'):self.p['drafts'][key]={'text':text,'status':'borrador','sources':[]}
    def test_inserts_at_end_of_correct_section_without_deletion(self):
        st=state('Portada','Objetivos','Contenido original','Metodología','Texto del método','Referencias','Ref')
        self.draft('objetivos');plan=build_plan(st,self.p,['objetivos'])
        self.assertEqual(plan['operations'][0]['position'],st['paragraphs'][3]['start']);self.assertNotIn('delete',plan['operations'][0]);self.assertIn('No se',preview(plan))
    def test_heading_number_prefix_is_recognized(self):
        st=state('CAPÍTULO II: MARCO TEÓRICO','texto','3. Metodología','Método')
        self.assertEqual([h['key'] for h in headings(st)],['marco_teorico','metodologia'])
    def test_does_not_use_table_or_toc_entries_as_real_section(self):
        st=state('Objetivos','Metodología','Objetivos','Texto')
        st['paragraphs'][0]['table']=True;st['tocs']=[{'start':st['paragraphs'][1]['start'],'end':st['paragraphs'][1]['end']}]
        self.assertEqual([h['key'] for h in headings(st)],['objetivos'])
    def test_ambiguous_section_is_blocked_not_guessed(self):
        self.draft('objetivos');st=state('Objetivos','Texto','Objetivos','Otro texto')
        with self.assertRaisesRegex(ValueError,'varias ubicaciones'):build_plan(st,self.p,['objetivos'])
    def test_new_section_inserted_before_later_section(self):
        self.draft('justificacion');st=state('Objetivos','Texto','Marco teórico','Texto')
        p=build_plan(st,self.p,['justificacion']);op=p['operations'][0]
        self.assertEqual(op['position'],st['paragraphs'][2]['start']);self.assertEqual(op['blocks'][0]['text'],'Justificación');self.assertEqual(op['blocks'][0]['level'],1)
    def test_missing_references_before_appendix_not_after(self):
        self.draft('referencias','Apellido (2020). Título.');st=state('Conclusiones','Texto','Apéndice A','Material')
        op=build_plan(st,self.p,['referencias'])['operations'][0];self.assertEqual(op['position'],st['paragraphs'][2]['start'])
    def test_body_subheadings_do_not_truncate_parent_section(self):
        self.draft('metodologia');st=state('Metodología','Diseño','Texto','Participantes','Texto','Resultados','Texto',levels=[1,2,10,2,10,1,10])
        self.assertEqual(build_plan(st,self.p,['metodologia'])['operations'][0]['position'],st['paragraphs'][5]['start'])
    def test_plain_unstructured_doc_requires_manual_review(self):
        self.draft('objetivos');st=state('Texto libre sin títulos','Más texto')
        with self.assertRaisesRegex(ValueError,'No hay títulos'):build_plan(st,self.p,['objetivos'],index=False)
    def test_blank_doc_can_receive_new_sections_and_index(self):
        self.draft('objetivos');self.draft('metodologia');plan=build_plan(state(''),self.p,['metodologia','objetivos'])
        self.assertEqual([o['section'] for o in plan['operations']],['objetivos','metodologia']);self.assertEqual(plan['toc']['position'],0)
    def test_empty_index_not_created(self):
        with self.assertRaises(ValueError):build_plan(state(''),self.p,[],index=True)
    def test_existing_index_updated_not_duplicated(self):
        st=state('Índice','Objetivos 1','Objetivos','Texto');st['tocs']=[{'start':st['paragraphs'][1]['start'],'end':st['paragraphs'][1]['end']}]
        self.assertEqual(build_plan(st,self.p,[])['toc']['mode'],'update')
    def test_multiple_indexes_blocked(self):
        st=state('Índice','Objetivos','Texto');st['tocs']=[{'start':0,'end':2},{'start':3,'end':5}]
        with self.assertRaisesRegex(ValueError,'varios índices'):build_plan(st,self.p,[])
    def test_exact_insert_not_replayed_when_marker_exists(self):
        st=state('Objetivos','Texto');self.draft('objetivos');p=build_plan(st,self.p,['objetivos']);st['markers']=[p['operations'][0]['marker']]
        new=build_plan(st,self.p,['objetivos']);self.assertEqual(new['operations'],[]);self.assertTrue(any('no se repetirá' in w for w in new['warnings']))
    def test_stale_drafts_or_missing_empirical_data_blocked(self):
        self.draft('resultados');st=state('Resultados','Texto')
        with self.assertRaisesRegex(ValueError,'datos reales'):build_plan(st,self.p,['resultados'])
        self.p['data_ready']=True;self.p['drafts']['resultados']['status']='necesita_revision'
        with self.assertRaisesRegex(ValueError,'revisión'):build_plan(st,self.p,['resultados'])
    def test_whole_format_explicit_preview_and_existing_numbering_preserved(self):
        st=state('Portada','Objetivos','Texto');st['page_number_present']=True;p=build_plan(st,self.p,[])
        text=preview(p);self.assertIn('Times New Roman 12',text);self.assertIn('2,54',text);self.assertIn('Carta',text);self.assertIn('se preservará',text)
    def test_no_automatic_citation_fabrication(self):
        self.draft('objetivos','La propuesta [F1] necesita apoyo.');p=build_plan(state('Objetivos','Texto'),self.p,['objetivos'])
        self.assertIn('[F1]',p['operations'][0]['blocks'][0]['text']);self.assertTrue(any('citas APA' in w for w in p['warnings']))
    def test_abstract_label_preserved_for_indentation_rules(self):
        hs=headings(state('Resumen','texto','Introducción','texto'))
        self.assertEqual(hs[0]['label_kind'],'abstract')
    def test_scope_is_document_specific(self):
        with self.assertRaises(ValueError):validate_state(state('Objetivos','Texto'),r'C:\other.docx')
    def test_invalid_positions_rejected(self):
        st=state('Objetivos','Texto');st['paragraphs'][1]['start']=-1
        with self.assertRaises(ValueError):validate_state(st,st['path'])

    def test_long_native_heading_still_bounds_previous_section(self):
        self.draft('objetivos');st=state('Objetivos','Texto','Título muy largo '*30,'Texto',levels=[1,10,1,10])
        self.assertEqual(build_plan(st,self.p,['objetivos'])['operations'][0]['position'],st['paragraphs'][2]['start'])
    def test_intro_plain_text_promoted_for_index_only(self):
        p=build_plan(state('Introducción','Texto'),self.p,format_all=False)
        self.assertEqual(p['promotions'][0]['text'],'Introducción');self.assertIn('Introducción',preview(p))
    def test_full_format_refuses_ambiguous_cover_body_boundary(self):
        with self.assertRaisesRegex(ValueError,'comienzo del cuerpo'):build_plan(state('Texto libre','Otro texto'),self.p,index=False)

    def test_manual_toc_duplicates_do_not_become_guessed_body(self):
        with self.assertRaisesRegex(ValueError,'comienzo del cuerpo aparece varias'):build_plan(state('Introducción','Objetivos','Introducción','Texto','Objetivos','Texto'),self.p)

class TextStyleTests(unittest.TestCase):
    def test_word_field_control_characters_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'caracteres de control'):paragraphs('Texto\x13 INCLUDETEXT campo','objetivos')
    def test_markdown_emphasis_and_relative_headings(self):
        blocks=paragraphs('# Objetivos\n\n## Objetivo general\n\nMejorar **lectura** con *evidencia*.','objetivos')
        self.assertEqual(blocks[0]['text'],'Objetivo general');self.assertEqual(blocks[0]['level'],2)
        self.assertEqual(blocks[1]['text'],'Mejorar lectura con evidencia.');self.assertEqual(len(blocks[1]['runs']),2)
    def test_level_four_not_silently_flattened(self):
        with self.assertRaises(ValueError):paragraphs('# Objetivos\n\n#### Profundo\n\nTexto','objetivos')
    def test_bold_sentence_not_silently_promoted_to_heading(self):
        b=paragraphs('**Mejorar la lectura.**','objetivos')[0]
        self.assertEqual(b['kind'],'body');self.assertTrue(b['runs'][0]['bold'])
    def test_manual_heading_not_removed(self):
        b=paragraphs('# Metodología\n\nTexto.','metodologia',drop_main=False,base_level=0);self.assertEqual(b[0]['text'],'Metodología');self.assertEqual(b[0]['level'],1)
    def test_quote_and_reference_styles_not_guessed_from_word_count(self):
        self.assertEqual(paragraphs('Mucho texto. '*80,'objetivos')[0]['kind'],'body')
        self.assertEqual(paragraphs('> Cita explícita.','objetivos')[0]['kind'],'quote')
        self.assertTrue(all(b['kind']=='reference' for b in paragraphs('Una referencia.\nOtra referencia.','referencias')))
    def test_utf16_emphasis_offsets_account_for_emoji(self):
        b=paragraphs('😀 **texto**','objetivos')[0];self.assertEqual(b['runs'][0]['start'],3)
    def test_markdown_tables_rejected_not_flattened(self):
        with self.assertRaises(ValueError):paragraphs('|a|b|\n|---|---|\n|x|y|','resultados')

class LayoutBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=ProjectStore(self.tmp.name);self.project=self.store.create('Tema');self.st=state('Objetivos','Texto');self.calls=[]
        def native(r):
            self.calls.append(r)
            if r['action']=='inspect':return {'ok':True,'structure':copy.deepcopy(self.st)}
            return {'ok':True,'operation':r['operation'],'text_verified':True,'saved':False,'inserted':[]}
        self.b=WordBridge(Path(self.tmp.name)/'journal',native);self.b.bind(self.st['path'])
    def tearDown(self):self.tmp.cleanup()
    def test_inspect_has_no_mutation_request(self):
        self.b.inspect_document();self.assertEqual([r['action'] for r in self.calls],['inspect'])
    def test_requires_approval_and_exact_preview(self):
        self.b.inspect_document();p=self.b.prepare_layout(self.project)
        with self.assertRaises(WordError):self.b.apply_layout(p)
        changed=copy.deepcopy(p);changed['toc']['mode']='none'
        with self.assertRaises(WordError):self.b.apply_layout(changed,True)
        self.assertEqual(len(self.calls),1)
    def test_plan_is_consumed_once(self):
        self.b.inspect_document();p=self.b.prepare_layout(self.project);self.b.apply_layout(p,True)
        with self.assertRaises(WordError):self.b.apply_layout(p,True)
        self.assertEqual([r['action'] for r in self.calls],['inspect','layout'])
    def test_failure_does_not_repeat_effect(self):
        self.b.inspect_document();p=self.b.prepare_layout(self.project)
        def fail(r):self.calls.append(r);raise WordError('partial failure')
        self.b.transport=fail
        with self.assertRaises(WordError):self.b.apply_layout(p,True)
        with self.assertRaises(WordError):self.b.apply_layout(p,True)
        self.assertEqual(len(self.calls),2)
    def test_manual_insert_requests_apa_blocks(self):
        fake=FakeWord();b=WordBridge(Path(self.tmp.name)/'log',fake);b.bind(fake.path);b.read();requests=[];original=b.transport
        b.transport=lambda r:(requests.append(r) or original(r));b.insert('# Título\n\nTexto con **énfasis**.',True)
        self.assertEqual(requests[0]['blocks'][0]['kind'],'heading');self.assertEqual(requests[0]['blocks'][1]['text'],'Texto con énfasis.')
    def test_packaged_adapter_below_windows_command_line_limit(self):
        self.assertLess(len(encoded_native_command()),31000);source=native_script();self.assertIn('[Console]::In.ReadToEnd()',source);self.assertIn('[ordered]@{paragraphs=',source)
    def test_native_contracts_and_no_auto_save_acceptance(self):
        s=native_script();self.assertIn('TablesOfContents.Add($at,$true,1,3',s);self.assertIn('TrackFormatting=$true',s);self.assertIn('structure_hash -cne',s)
        self.assertNotIn('AcceptAll',s);self.assertNotIn('.Save(',s);self.assertIn('doc.Range($pos,$pos)',s)

class CopilotPassiveCaptureTests(unittest.TestCase):
    def test_connection_never_reloads_or_automates_chat(self):
        obj=json.loads(session());frame=obj['frame'];frame['arguments'][0]['message']['text']='PROBE';sent=[]
        events=[{'method':'Network.webSocketCreated','params':{'requestId':'id','url':obj['url']}},{'method':'Network.webSocketFrameSent','params':{'requestId':'id','response':{'payloadData':json.dumps(frame)+RS}}}]
        class WS:
            def send(self,text):sent.append(json.loads(text))
            def recv(self):return json.dumps(events.pop(0))
            def close(self):pass
        class Opener:
            def open(self,*a,**k):return Response([{'type':'page','url':'https://m365.cloud.microsoft/chat','webSocketDebuggerUrl':'ws://127.0.0.1:7777/devtools/page/test'}])
        with patch('copilot_socket.urllib.request.build_opener',return_value=Opener()),patch('copilot_socket.cdp_socket',return_value=WS()):result=capture_connection(7777,'PROBE',timeout=2)
        self.assertEqual([r['method'] for r in sent],['Network.enable']);self.assertEqual(json.loads(result)['frame']['arguments'][0]['message']['text'],'')
    def test_no_credential_cache_or_dom_script_added(self):
        import copilot_socket
        s=Path(copilot_socket.__file__).read_text();self.assertNotIn("'method':'Page.reload'",s);self.assertNotIn('Runtime.evaluate',s);self.assertNotIn('localStorage',s)
