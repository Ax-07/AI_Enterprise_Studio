import json,hashlib
from unittest.mock import patch
from test_autopilot import AutopilotTests
import serveur as s, moteur as m, autopilot as a, protocol_recovery as p

class ProtocolRecovery(AutopilotTests):
    def setup_blocked(self):
        with s.db() as c:
            original=m.create(s,c,'Prototype','cloud')
            data='a,b\n1,2\n'
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'kit.csv',1,'NEXUS',?,'test')",(original,data)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(original,))
        cid=self.start()
        with s.db() as c:
            mid=m.create(s,c,'Audit complémentaire','cloud',aid)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'functional',?)",(cid,mid,aid))
            root=c.execute('SELECT id FROM tasks WHERE mission=?',(mid,)).fetchone()[0]
            tid=m.add_task(c,mid,'SENTINEL','Audit','Tests',root)
            c.execute('UPDATE tasks SET turns=8 WHERE id=?',(tid,))
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
            m.log(c,t,'read_file',m.action_args(self.act('read_file','ref:'+str(aid))),{'fichier':aid,'contenu':data},True)
            proof={'kind':'csv','sha256':hashlib.sha256(data.encode()).hexdigest(),'status':'invalid','checks':[],'error':'1 à 4 cas HTML requis'}
            vid=c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL','{}',?)",(aid,mid,json.dumps(proof))).lastrowid
            m.log(c,t,'test_file',{},dict(proof,verification_id=vid),True)
            for i in range(6):m.log(c,t,'memory',{}, {'résultats':[]},True)
            c.execute("UPDATE missions SET state='bloquée',error=? WHERE id=?",('Action identique répétée trois fois; tâche #'+str(tid)+' ; outil read_file ; cible ref:'+str(aid),mid))
            c.execute("UPDATE campaigns SET state='bloqué' WHERE id=?",(cid,))
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,'test',1000,500,'mesuré')",(mid,))
        return cid,mid,tid,aid
    def test_recover_exact_block_and_pin(self):
        cid,mid,tid,aid=self.setup_blocked()
        with s.db() as c:
            self.assertTrue(a.status(c,self.cfg)['recoverable'])
            a.resume(c,cid,self.cfg)
            self.assertEqual(a.costs(c,cid),500)
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
            mission=dict(c.execute('SELECT * FROM missions WHERE id=?',(mid,)).fetchone())
            self.assertEqual(t['turns'],8)
            self.assertTrue(p.corrective(c,t))
        prompt=m.context(s,t,mission,self.cfg)
        self.assertIn('FILE_PIN',prompt);self.assertIn('a,b',prompt)
        self.assertIn('1 à 4 cas HTML requis',prompt)
        self.assertIn('12 étapes',prompt)
        spec=json.dumps({'checks':[{'op':'row_count','expected':1}]})
        actions=[self.act('test_file','ref:'+str(aid),spec),self.act('finish',text='Un contrôle réussi; périmètre limité.'),self.act('finish',text='Conclusion limitée.')]
        def fake(*args,**kwargs):
            if args[1]=='SENTINEL' and len(actions)==3:
                self.assertEqual(set(kwargs['schema']['properties']['action']['enum']),{'test_file','finish'})
                self.assertFalse(kwargs['validator'](self.act('read_file','ref:'+str(aid))))
            return actions.pop(0)
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'call_model',side_effect=fake):
            m.run(s,mid)
        with s.db() as c:
            self.assertEqual(c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0],'terminée')
            self.assertEqual(c.execute('SELECT turns FROM tasks WHERE id=?',(tid,)).fetchone()[0],10)
            self.assertEqual(a._proof(c,aid,mid),'passed')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM verification_results').fetchone()[0],2)
    def test_recovery_refused_without_turns_or_matching_block(self):
        cid,mid,tid,aid=self.setup_blocked()
        with s.db() as c:
            c.execute('UPDATE tasks SET turns=9 WHERE id=?',(tid,))
            self.assertFalse(a.status(c,self.cfg)['recoverable'])
            with self.assertRaises(ValueError):a.resume(c,cid,self.cfg)
            c.execute('UPDATE tasks SET turns=8 WHERE id=?',(tid,))
            c.execute("UPDATE missions SET error='Budget insuffisant' WHERE id=?",(mid,))
            self.assertFalse(a.status(c,self.cfg)['recoverable'])
