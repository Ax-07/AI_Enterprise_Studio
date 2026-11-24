import json, unittest, tempfile
from pathlib import Path
from unittest.mock import patch
import serveur as s, moteur as m

class JsonRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.p=patch.object(s,'DB',Path(self.tmp.name)/'db'); self.p.start(); s.init()
        self.cfg={**s.config(),'key':'test','budget':2000000,'mission_budget':1000000}
        with s.db() as c:
            self.mid=m.create(s,c,'Test reprise NEXUS','cloud')
            root=c.execute('SELECT id FROM tasks WHERE mission=?',(self.mid,)).fetchone()[0]
            self.orion=m.add_task(c,self.mid,'ORION','Recherche','',root)
            self.nexus=m.add_task(c,self.mid,'NEXUS','Produit','',root)
            c.execute("UPDATE tasks SET state='terminée',result='Recherche conservée' WHERE id=?",(self.orion,))
            c.execute('INSERT INTO reports(mission,step,agent,report,sources) VALUES(?,?,?,?,?)',(self.mid,self.orion,'ORION',json.dumps({'rapport':'Recherche conservée'}),'[]'))
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state,agent) VALUES(?, 'gpt-6-luna',1000,700,'mesuré','ORION')",(self.mid,))
    def tearDown(self): self.p.stop(); self.tmp.cleanup()
    def raw(self,text):
        return {'status':'completed','usage':{'input_tokens':1200,'output_tokens':500,'output_tokens_details':{'reasoning_tokens':100}},'output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}
    def action(self,a,target='',text='',detail=''):
        return self.raw(json.dumps(dict(action=a,target=target,text=text,detail=detail)))
    def run_mock(self, responses, cfg=None):
        with patch.object(s,'config',return_value=cfg or self.cfg),patch.object(s,'request',side_effect=responses) as req:
            s.run(self.mid); return req.call_args_list
    def test_json_recovery_keeps_orion_and_charges(self):
        calls=self.run_mock([self.raw('{"action":'),self.action('write_file','kit.csv','a,b\n1,2\n'),self.action('finish',text='Produit interne'),self.action('finish',text='Conclusion')])
        self.assertEqual([x.args[2]['max_output_tokens'] for x in calls],[8192,16384,8192,4096]); self.assertIn('Tentative de correction unique',calls[1].args[2]['input'])
        with s.db() as c:
            self.assertEqual(c.execute('SELECT state FROM missions').fetchone()[0],'terminée')
            self.assertEqual(c.execute('SELECT actual FROM ledger WHERE id=1').fetchone()[0],700)
            self.assertIn('JSON non décodable',c.execute('SELECT diagnostic FROM ledger WHERE id=2').fetchone()[0])
            self.assertEqual(c.execute('SELECT count(*) FROM reports WHERE agent=\'ORION\'').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM artifacts').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT turns FROM tasks WHERE id=?',(self.nexus,)).fetchone()[0],2)
            self.assertEqual(c.execute('SELECT count(*) FROM ledger').fetchone()[0],5)
    def test_only_one_retry_then_resume(self):
        calls=self.run_mock([self.raw(''),self.raw('{"action":"finish"}')]); self.assertEqual(len(calls),2)
        with s.db() as c:
            self.assertIn('Correction unique épuisée',c.execute('SELECT error FROM missions').fetchone()[0]);self.assertEqual(c.execute('SELECT count(*) FROM artifacts').fetchone()[0],0)
            self.assertIn('vide',c.execute('SELECT diagnostic FROM ledger WHERE id=2').fetchone()[0]); self.assertIn('schéma',c.execute('SELECT diagnostic FROM ledger WHERE id=3').fetchone()[0]); c.execute("UPDATE missions SET state='en cours',error='' WHERE id=?",(self.mid,))
        calls=self.run_mock([self.action('write_file','kit.csv','a,b\n1,2\n'),self.action('finish',text='Produit'),self.action('finish',text='Conclusion')]);self.assertEqual(len(calls),3)
        with s.db() as c:self.assertEqual(c.execute('SELECT state FROM missions').fetchone()[0],'terminée');self.assertEqual(c.execute('SELECT count(*) FROM reports WHERE agent=\'ORION\'').fetchone()[0],1)
    def test_refusal_not_retried(self):
        response=self.raw('');response['output'][0]['content']=[{'type':'refusal','refusal':'no'}]
        self.assertEqual(len(self.run_mock([response])),1)
        with s.db() as c:self.assertIn('refusal',c.execute('SELECT error FROM missions').fetchone()[0])
    def test_retry_respects_budget(self):
        self.assertEqual(len(self.run_mock([self.raw('{')],{**self.cfg,'mission_budget':65000})),1)
        with s.db() as c:self.assertIn('Budget',c.execute('SELECT error FROM missions').fetchone()[0]);self.assertEqual(c.execute('SELECT count(*) FROM ledger').fetchone()[0],2)
    def test_token_limit_then_invalid_no_third_call(self):
        response=self.raw('');response['status']='incomplete';response['incomplete_details']={'reason':'max_output_tokens'}
        self.assertEqual(len(self.run_mock([response,self.raw('')])),2)
        with s.db() as c:self.assertIn('Correction unique épuisée',c.execute('SELECT error FROM missions').fetchone()[0])
