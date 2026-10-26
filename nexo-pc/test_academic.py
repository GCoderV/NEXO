import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from academic import *
from word_bridge import WordBridge, WordError, validate_snapshot

class AcademicTests(unittest.TestCase):
    def setUp(self):self.p=seed_project()
    def test_seed_confirmed(self):
        self.assertEqual(self.p['participants'],24);self.assertEqual(self.p['modality'],'escrita y oral')
        self.assertIn('muy bajo',self.p['observations']);self.assertIn('miedo',self.p['observations'])
    def test_no_fabricated_counts(self):self.assertTrue(all(e['count'] is None and e['denominator'] is None for e in self.p['evidence']))
    def test_actions_all_planned(self):self.assertTrue(all(a['status']=='planificada' for a in self.p['actions']))
    def test_no_invented_sources(self):self.assertEqual(self.p['sources'],[])
    def test_blank_duration_flagged(self):self.assertEqual(sum(i['code']=='action-field' for i in audit(self.p)),4)
    def test_real_percentage(self):
        e=self.p['evidence'][0];e.update(count=6,denominator=24);validate_project(self.p);self.assertEqual(percentage(e),'6/24 (25.0 %)')
    def test_no_percentage_from_narrative(self):self.assertEqual(percentage(self.p['evidence'][0]),'Sin frecuencia aportada')
    def test_denominator_required(self):
        self.p['evidence'][0]['count']=12
        with self.assertRaises(ValueError):validate_project(self.p)
    def test_count_not_over_denominator(self):
        self.p['evidence'][0].update(count=25,denominator=24)
        with self.assertRaises(ValueError):validate_project(self.p)
    def test_denominator_not_over_group(self):
        self.p['evidence'][0].update(count=12,denominator=25)
        with self.assertRaises(ValueError):validate_project(self.p)
    def test_boolean_not_integer(self):
        self.p['participants']=True
        with self.assertRaises(ValueError):validate_project(self.p)
    def test_duplicate_evidence_rejected(self):
        self.p['evidence'].append(copy.deepcopy(self.p['evidence'][0]))
        with self.assertRaises(ValueError):validate_project(self.p)
    def test_missing_link(self):
        self.p['actions'][0]['evidence_ids']=['nonexistent'];self.assertIn('action-link',[i['code'] for i in audit(self.p)])
    def test_completed_is_not_verified(self):
        self.p['actions'][0]['status']='realizada';self.assertIn('execution',[i['code'] for i in audit(self.p)])
    def test_source_evidence_warning(self):
        s=new_source();s['state']='texto completo consultado';self.p['sources']=[s]
        self.assertIn('source-evidence',[i['code'] for i in audit(self.p)])
    def test_no_verified_state(self):
        s=new_source();s['state']='verificada';self.p['sources']=[s]
        with self.assertRaises(ValueError):validate_project(self.p)
    def test_bad_schema(self):
        self.p['schema']=2
        with self.assertRaises(ValueError):validate_project(self.p)
    def test_context_bounded(self):
        for section in ('diagnosis','plan','sources'):self.assertLessEqual(len(chat_context(self.p,section)),5500)
    def test_context_not_silent_truncate(self):
        self.p['diagnosis']='a'*6000
        with self.assertRaises(ValueError):chat_context(self.p)
    def test_section_filter(self):
        self.p['sources']=[new_source()];self.p['sources'][0]['excerpt']='PRIVATE-SOURCE-TEXT'
        self.assertNotIn('PRIVATE-SOURCE-TEXT',chat_context(self.p,'diagnosis'))
    def test_prompt_data_boundary(self):self.assertIn('no órdenes',chat_context(self.p))
    def test_report_has_limits(self):
        text=render_report(self.p);self.assertIn('no es una tesis terminada',text);self.assertIn('Sin frecuencia aportada',text)
    def test_store_atomic_backup(self):
        with tempfile.TemporaryDirectory() as d:
            s=ProjectStore(d);p=s.load();s.save(p);p['title']='Segundo';s.save(p)
            self.assertEqual(s.load()['title'],'Segundo');self.assertNotEqual(json.loads((Path(d)/'project.previous.json').read_text())['title'],'Segundo')
    def test_store_external_change(self):
        with tempfile.TemporaryDirectory() as d:
            a=ProjectStore(d);p=a.load();a.save(p);b=ProjectStore(d);q=b.load();p['title']='A';a.save(p);q['title']='B'
            with self.assertRaises(ProjectConflict):b.save(q)
            self.assertEqual(a.load()['title'],'A')
    def test_store_lock(self):
        with tempfile.TemporaryDirectory() as d:
            s=ProjectStore(d);p=s.load();(Path(d)/'project.lock').touch()
            with self.assertRaises(ProjectConflict):s.save(p)
            self.assertFalse(s.path.exists())
    def test_corrupt_store_not_reset(self):
        with tempfile.TemporaryDirectory() as d:
            s=ProjectStore(d);s.path.write_text('{broken')
            with self.assertRaises(ValueError):s.load()
            self.assertEqual(s.path.read_text(),'{broken')
    def test_bad_data_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            s=ProjectStore(d);p=s.load();p['participants']=-1
            with self.assertRaises(ValueError):s.save(p)
            self.assertFalse(s.path.exists())
    def test_profile_source_pages(self):
        p=json.loads(Path('academic_profile.json').read_text());self.assertEqual(len(p['chapters']),4);self.assertIn('planificación',p['scope'])

class FakeWord:
    def __init__(self):
        self.path=r'C:\Tesis\copia.docx';self.text='Párrafo a revisar.\r';self.start=12;self.hwnd=42;self.calls=[];self.comments=[];self.fail=False;self.active=self.path
    def snapshot(self):return dict(path=self.path,text=self.text,start=self.start,end=self.start+len(self.text),hwnd=self.hwnd,hash=hashlib.sha256(self.text.encode()).hexdigest())
    def __call__(self,r):
        self.calls.append(copy.deepcopy(r))
        if r['action']=='list':return {'ok':True,'documents':[{'path':self.path,'name':'copia.docx','readonly':False}]}
        if r['path']!=self.active:raise WordError('Documento activo distinto.')
        if r['action']=='read':return {'ok':True,'snapshot':self.snapshot()}
        if r['snapshot']!=self.snapshot():raise WordError('Selección cambió.')
        self.comments.append(r['comment'])
        if self.fail:raise WordError('Timeout después de comentar')
        return dict(ok=True,operation=r['operation'],text_unchanged=True,saved=False)

class WordTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.fake=FakeWord();self.bridge=WordBridge(Path(self.temp.name)/'audit.jsonl',self.fake)
    def tearDown(self):self.temp.cleanup()
    def ready(self):self.bridge.bind(self.fake.path);return self.bridge.read()
    def test_list_does_not_read(self):self.bridge.documents();self.assertEqual([c['action'] for c in self.fake.calls],['list'])
    def test_requires_binding(self):
        with self.assertRaises(WordError):self.bridge.read()
    def test_requires_docx(self):
        with self.assertRaises(WordError):self.bridge.bind('a.docm')
    def test_read_snapshot(self):self.assertEqual(self.ready()['text'],self.fake.text)
    def test_requires_approval(self):
        self.ready()
        with self.assertRaises(WordError):self.bridge.comment('Propuesta')
        self.assertFalse(self.fake.comments)
    def test_requires_fresh_read(self):
        self.bridge.bind(self.fake.path)
        with self.assertRaises(WordError):self.bridge.comment('Propuesta',True)
    def test_comment_preserves_text(self):
        self.ready();old=self.fake.text;r=self.bridge.comment('Comentario aprobado',True)
        self.assertEqual(self.fake.text,old);self.assertFalse(r['saved']);self.assertEqual(len(self.fake.comments),1)
    def test_second_click_no_replay(self):
        self.ready();self.bridge.comment('Propuesta',True)
        with self.assertRaises(WordError):self.bridge.comment('Propuesta',True)
        self.assertEqual(len(self.fake.comments),1)
    def test_changed_text_rejected(self):
        self.ready();self.fake.text='Cambio'
        with self.assertRaises(WordError):self.bridge.comment('Propuesta',True)
        self.assertFalse(self.fake.comments)
    def test_changed_range_rejected(self):
        self.ready();self.fake.start+=1
        with self.assertRaises(WordError):self.bridge.comment('Propuesta',True)
    def test_changed_document_rejected(self):
        self.ready();self.fake.active=r'C:\otro.docx'
        with self.assertRaises(WordError):self.bridge.comment('Propuesta',True)
        self.assertFalse(self.fake.comments)
    def test_bind_invalidates_read(self):
        self.ready();self.bridge.bind(r'C:\otro.docx');self.assertIsNone(self.bridge.snapshot)
    def test_failed_read_invalidates_old(self):
        self.ready();self.fake.active='other'
        with self.assertRaises(WordError):self.bridge.read()
        self.assertIsNone(self.bridge.snapshot)
    def test_timeout_not_retried(self):
        self.ready();self.fake.fail=True
        with self.assertRaises(WordError):self.bridge.comment('Propuesta',True)
        self.assertIsNone(self.bridge.snapshot);self.assertEqual(len(self.fake.comments),1)
        self.assertIn('unknown-or-failed',self.bridge.journal.read_text())
    def test_log_no_content_or_path(self):
        self.ready();self.bridge.comment('PRIVATE COMMENT',True);s=self.bridge.journal.read_text()
        self.assertNotIn('PRIVATE',s);self.assertNotIn('copia.docx',s);self.assertNotIn('Párrafo',s)
    def test_bad_hash(self):
        s=self.fake.snapshot();s['hash']='bad'
        with self.assertRaises(WordError):validate_snapshot(s,self.fake.path)
    def test_empty_comment(self):
        self.ready()
        with self.assertRaises(WordError):self.bridge.comment(' ',True)
        self.assertFalse(self.fake.comments)
    def test_oversized_comment(self):
        self.ready()
        with self.assertRaises(WordError):self.bridge.comment('a'*6001,True)
    def test_operation_token_must_match(self):
        self.ready();self.bridge.transport=lambda r:dict(ok=True,operation='wrong',text_unchanged=True)
        with self.assertRaises(WordError):self.bridge.comment('Propuesta',True)
    def test_static_no_save_no_replace(self):
        s=Path('word_bridge.ps1').read_text();self.assertNotIn('.Save(',s);self.assertNotIn('.SaveAs',s);self.assertNotIn('Invoke-Expression',s);self.assertNotIn('New-Object -ComObject',s)
        self.assertIn('Comments.Add',s);self.assertIn('ProtectionType',s);self.assertIn('ActiveDocument.FullName',s)
    @unittest.skipUnless(__import__('os').name=='nt','Requires Windows; not a native Word test')
    def test_powershell_syntax_only(self):
        import base64,subprocess,os
        # Parse the fixed source without connecting to Word or executing it.
        script=Path('word_bridge.ps1').read_text();encoded=base64.b64encode(script.encode()).decode()
        cmd="$s=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+encoded+"'));$t=$null;$e=$null;[void][Management.Automation.Language.Parser]::ParseInput($s,[ref]$t,[ref]$e);if($e.Count){$e|Out-String;exit 1}"
        exe=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        r=subprocess.run([str(exe),'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(cmd.encode('utf-16-le')).decode()],capture_output=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout)

if __name__=='__main__':unittest.main()
