import copy,json,tempfile,threading,unittest
from pathlib import Path
from project_store import ProjectStore,set_fact,SECTIONS
from agent import Agent,context
from autonomy import plan,order,protected,fingerprint,AutonomousRunner,route_scope
from test_core import FakeAPI,reply

def draft(k,text):return {'section':k,'text':text,'sources':[]}
class AutonomyTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=ProjectStore(self.tmp.name);self.p=self.store.create('Tema del proyecto');self.stop=threading.Event()
    def tearDown(self):self.tmp.cleanup()
    def saved_draft(self,k,text='Texto anterior.',status='borrador'):
        self.p['drafts'][k]={'text':text,'status':status,'sources':[],'producer':{'provider':'simulated'}}
    def task(self,p=None):
        p=p or self.p;tasks,_=plan(p);return order(p,tasks[0])
    def run_batch(self,apis,limit=2,**kwargs):
        apis=list(apis);scope=route_scope(apis[0]);r=AutonomousRunner(self.store,lambda:apis.pop(0),self.stop,**kwargs)
        return r.run(self.p['id'],limit,authorized_scope=scope)
    def test_missing_sections_prioritized_with_explicit_target(self):
        self.saved_draft('delimitacion');tasks,_=plan(self.p)
        self.assertEqual(tasks[0]['section'],'problematica');self.assertEqual(tasks[-1]['section'],'delimitacion')
    def test_protected_manual_approved_inserted_not_overwritten(self):
        for k,status in [('delimitacion','aprobado_usuario'),('problematica','insertado_pendiente_revision_word')]:self.saved_draft(k,status=status)
        self.saved_draft('pregunta');self.p['drafts']['pregunta']['edited_by_user']=True
        self.saved_draft('objetivos');self.p['drafts']['objetivos'].pop('producer')
        tasks,_=plan(self.p);self.assertTrue(all(t['section'] not in ('delimitacion','problematica','pregunta','objetivos') for t in tasks))
    def test_previous_protected_status_survives_fact_invalidation(self):
        self.saved_draft('delimitacion',status='aprobado_usuario');set_fact(self.p,'nivel','grado')
        self.assertTrue(protected(self.p['drafts']['delimitacion']))
    def test_empirical_sections_not_scheduled_without_confirmed_data(self):
        tasks,notice=plan(self.p);self.assertFalse({'resultados','discusion','conclusiones'} & {t['section'] for t in tasks});self.assertIn('confirmados',notice)
        set_fact(self.p,'datos','Corpus aportado');self.p['data_ready']=True
        tasks,_=plan(self.p);self.assertIn('resultados',[t['section'] for t in tasks])
    def test_documentary_work_does_not_force_instruments_or_action_plan(self):
        set_fact(self.p,'tipo_trabajo','revisión documental');set_fact(self.p,'metodologia','análisis de documentos')
        tasks,_=plan(self.p);self.assertFalse({'instrumentos','plan_accion'} & {t['section'] for t in tasks})
    def test_full_previous_text_in_review_context(self):
        self.saved_draft('delimitacion','Texto largo. '*700);t=order(self.p,{'section':'delimitacion','mode':'revisar','label':'Delimitación'})
        data=json.loads(context(self.p,'Revisa',origin='autonomo',work_order=t));self.assertEqual(data['work_order']['previous_text'],self.p['drafts']['delimitacion']['text'])
    def test_completed_draft_not_rewritten_on_every_session(self):
        api=FakeAPI([reply(drafts=[draft('delimitacion','Nuevo contenido útil.')])]);r=self.run_batch([api],1)
        self.assertNotIn('delimitacion',[t['section'] for t in plan(r)[0]])
        set_fact(r,'alcance','Nuevo alcance');self.assertIn('delimitacion',[t['section'] for t in plan(r)[0]])
    def test_only_promises_get_one_correction_not_an_infinite_loop(self):
        api=FakeAPI([reply('Puedo continuar.'),reply('Podemos avanzar.')]);r=self.run_batch([api],1)
        self.assertEqual(len(api.requests),2);self.assertEqual(r['drafts'],{});self.assertEqual(r['autonomy']['status'],'sin_avance');self.assertNotIn('pending',r)
    def test_correction_can_deliver_real_progress(self):
        api=FakeAPI([reply('Puedo continuar.'),reply(drafts=[draft('delimitacion','Desarrollo nuevo.')])]);r=self.run_batch([api],1)
        self.assertEqual(r['autonomy']['completed'],['delimitacion']);self.assertEqual(len(api.requests),2)
    def test_two_tasks_run_without_user_continua_messages(self):
        a=FakeAPI([reply(drafts=[draft('delimitacion','Delimitación nueva.')])]);b=FakeAPI([reply(drafts=[draft('problematica','Problema concreto.')])]);progress=[]
        r=self.run_batch([a,b],2,on_progress=lambda p:progress.append(copy.deepcopy(p)))
        self.assertEqual(r['autonomy']['completed'],['delimitacion','problematica']);self.assertEqual(len(progress),2);self.assertFalse([m for m in r['messages'] if m['role']=='user']);self.assertEqual(r['usage']['calls'],2)
    def test_stop_between_tasks_keeps_completed_work(self):
        a=FakeAPI([reply(drafts=[draft('delimitacion','Nuevo texto.')])]);b=FakeAPI([])
        r=self.run_batch([a,b],2,on_progress=lambda p:self.stop.set())
        self.assertEqual(r['autonomy']['status'],'detenido');self.assertEqual(len(b.requests),0);self.assertIn('delimitacion',r['drafts'])
    def test_no_synthetic_decisions_from_autonomous_instruction(self):
        a=FakeAPI([reply(facts=[{'key':'metodologia','value':'Experimental','evidence':'crear'}],drafts=[draft('delimitacion','Propuesta provisional.')])]);r=self.run_batch([a],1)
        self.assertNotIn('metodologia',r['facts']);self.assertFalse(r['data_ready'])
    def test_identical_draft_is_not_progress_or_a_new_version(self):
        for k in SECTIONS:self.saved_draft(k)
        self.store.save(self.p);a=FakeAPI([reply(drafts=[draft('delimitacion','Texto anterior.')])]*2);r=self.run_batch([a],1)
        self.assertEqual(r['autonomy']['status'],'sin_avance');self.assertNotIn('versions',r['drafts']['delimitacion'])
    def test_large_truncation_not_silently_saved(self):
        for k in SECTIONS:self.saved_draft(k,'Contenido largo. '*100)
        self.store.save(self.p);a=FakeAPI([reply(drafts=[draft('delimitacion','Resumen breve.')])]*2);r=self.run_batch([a],1)
        self.assertEqual(r['drafts']['delimitacion']['text'],self.p['drafts']['delimitacion']['text'])
    def test_model_cannot_change_other_section_from_task(self):
        self.saved_draft('objetivos','No tocar.',status='aprobado_usuario');self.store.save(self.p)
        a=FakeAPI([reply(drafts=[draft('delimitacion','Texto nuevo.'),draft('objetivos','Cambio indebido.')])]);r=self.run_batch([a],1)
        self.assertEqual(r['drafts']['objetivos']['text'],'No tocar.')
    def test_pending_error_stops_and_resume_does_not_duplicate_task(self):
        a=FakeAPI([RuntimeError('fallo')]);r=self.run_batch([a],1);self.assertEqual(r['autonomy']['status'],'pendiente')
        mid=r['pending']['mid'];self.assertEqual(r['pending']['revision'],r['revision'])
        api=FakeAPI([reply(drafts=[draft('delimitacion','Recuperado.')])]);r=Agent(self.store,api).turn(r['id'],resume=True)
        self.assertEqual(sum(m['id']==mid for m in r['messages']),1);self.assertIn('delimitacion',r['drafts'])
    def test_new_batch_never_replaces_pending_request(self):
        a=FakeAPI([RuntimeError('fallo')]);r=self.run_batch([a],1)
        with self.assertRaisesRegex(ValueError,'pendiente'):self.run_batch([FakeAPI([])],1)
    def test_recipient_scope_change_stops_before_send(self):
        a=FakeAPI([reply(drafts=[draft('delimitacion','Nuevo.')])]);b=FakeAPI([]);b.model='different'
        r=self.run_batch([a,b],2);self.assertEqual(r['autonomy']['status'],'requiere_autorizacion');self.assertFalse(b.requests)
    def test_revision_check_before_any_model_call(self):
        a=FakeAPI([]);runner=AutonomousRunner(self.store,lambda:a,self.stop)
        with self.assertRaisesRegex(ValueError,'cambió'):runner.run(self.p['id'],1,authorized_scope=route_scope(a),expected_revision=999)
        self.assertFalse(a.requests)
    def test_time_budget_prevents_next_task(self):
        a=FakeAPI([]);times=iter([0,601]);r=self.run_batch([a],1,clock=lambda:next(times))
        self.assertEqual(r['autonomy']['status'],'limite_tiempo');self.assertFalse(a.requests)
    def test_search_two_phases_and_first_progress_is_retained(self):
        api=FakeAPI([reply(drafts=[draft('delimitacion','Texto nuevo.')],search={'query':'reading education','reason':'Bibliografía'}),reply('La fuente aún requiere revisión.')]);runner=AutonomousRunner(self.store,lambda:api,self.stop,approve_search=lambda *a:True,searcher=lambda q:[])
        r=runner.run(self.p['id'],1,True,route_scope(api));self.assertEqual(len(api.requests),2);self.assertEqual(r['autonomy']['completed'],['delimitacion'])
    def test_no_word_actions_available_to_scheduler(self):
        import autonomy
        source=Path(autonomy.__file__).read_text();self.assertNotIn('word_bridge',source);self.assertNotIn('subprocess',source)

class WordTOCRegressionTests(unittest.TestCase):
    def test_unsupported_property_removed_but_creation_parameter_retained(self):
        s=Path('word_layout.ps1').read_text();self.assertNotIn('$toc.UseOutlineLevels=',s);self.assertIn('TablesOfContents.Add($at,$true,1,3,$false,$m,$true,$true,$m,$true,$true,$true)',s)
        self.assertIn('$toc.HeadingStyles.Add($name,$level)',s);self.assertIn('Set-NexoTOCStyles $toc',s)
    def test_toc_property_assignments_match_documented_object(self):
        import re
        allowed={'UseHeadingStyles','UpperHeadingLevel','LowerHeadingLevel','IncludePageNumbers','RightAlignPageNumbers','UseHyperlinks','TabLeader'}
        s=Path('word_layout.ps1').read_text();self.assertLessEqual(set(re.findall(r'\$toc\.(\w+)\s*=',s)),allowed)
