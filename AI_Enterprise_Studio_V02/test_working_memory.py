import hashlib,json,unittest
from unittest.mock import patch
import test_autopilot
import serveur as s,moteur as m,autopilot as a,working_memory as w

class WorkingMemoryTests(unittest.TestCase):
    setUp=test_autopilot.AutopilotTests.setUp
    start=test_autopilot.AutopilotTests.start
    act=test_autopilot.AutopilotTests.act
    reply=test_autopilot.AutopilotTests.reply
    def blocked(self):
        data='<p>Fichier synthétique pour étude commerciale</p>'
        with s.db() as c:
            orig=m.create(s,c,'Prototype','cloud')
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'kit.html',1,'NEXUS',?,'interne')",(orig,data)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(orig,))
        cid=self.start()
        with s.db() as c:
            audit=m.create(s,c,'Audit','cloud',aid)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'functional',?)",(cid,audit,aid))
            spec={'cases':[{'name':'Exemple','steps':[{'op':'visible','selector':'p'}]}]}
            result={'kind':'html','status':'passed','sha256':hashlib.sha256(data.encode()).hexdigest(),'checks':[{'name':'Exemple','passed':True}]}
            c.execute("INSERT INTO verification_results(artifact,mission,agent,spec,result) VALUES(?,?,'SENTINEL',?,?)",(aid,audit,json.dumps(spec),json.dumps(result)))
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(audit,))
            mid=m.create(s,c,'Marché','cloud',aid)
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind,artifact) VALUES(?,?,'market',?)",(cid,mid,aid))
            root=c.execute('SELECT id FROM tasks WHERE mission=?',(mid,)).fetchone()[0]
            tid=m.add_task(c,mid,'HERMES','Étudier demande et alternatives','Aucune source externe inventée',root)
            c.execute('UPDATE tasks SET turns=1 WHERE id=?',(root,))
            c.execute('UPDATE tasks SET turns=9 WHERE id=?',(tid,))
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
            v=self.act('read_file','ref:'+str(aid))
            for i in range(2):m.log(c,t,'read_file',m.action_args(v),{'fichier':aid,'contenu':data},True)
            for i in range(6):
                v=self.act('memory',text='Marché recherche '+str(i))
                m.log(c,t,'memory',m.action_args(v),{'résultats':[{'type':'reports','id':4,'mission':audit,'mode':'cloud','extrait':'Test technique; aucune demande prouvée'}]},True)
            c.execute("UPDATE missions SET state='bloquée',error=? WHERE id=?",('Action identique répétée trois fois; tâche #'+str(tid)+' ; outil read_file ; cible ref:'+str(aid),mid))
            c.execute("UPDATE campaigns SET state='bloqué' WHERE id=?",(cid,))
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state) VALUES(?,'test',12000,11000,'mesuré')",(mid,))
        return cid,mid,tid,aid,data
    def test_recovery_real_worker_mocked_provider(self):
        cid,mid,tid,aid,data=self.blocked()
        with s.db() as c:
            self.assertEqual(a.status(c,self.cfg)['recovery_kind'],'memory')
            a.resume(c,cid,self.cfg)
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
            self.assertEqual(t['turns'],9);self.assertEqual(a.costs(c,cid),11000)
            work=w.snapshot(c,t)
            self.assertEqual(work['memory_count'],6);self.assertEqual(len(work['hits']),1)
            self.assertEqual(work['files'][0]['contenu'],data)
            allowed=w.policy(c,t,self.cfg,m.PERMS['HERMES'],work)
            self.assertTrue({'memory','read_file','read'}.isdisjoint(allowed))
        actions=[self.act('finish',text='Étude partielle : aucun accès Internet; demande inconnue.'),
                 self.act('delegate','MIDAS','Calcul hypothétique','Données manquantes'),
                 self.act('finish',text='Marge hypothétique, données manquantes.'),
                 self.act('finish',text='Conclusion : aucune demande vérifiée.'),
                 self.act('delegate','ORION','Explorer','Mémoire uniquement'),
                 self.act('opportunity','Piste nouvelle','Hypothèse','Vérifier'),
                 self.act('finish',text='Hypothèse non validée'),
                 self.act('finish',text='Étude interne')]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            if len(actions)==8:
                self.assertIn(data,body['input'])
                self.assertIn('Brave non disponible',body['input'])
                self.assertIn('Test technique; aucune demande prouvée',body['input'])
                self.assertEqual(body['text']['format']['schema']['properties']['action']['enum'],['finish'])
            act=actions.pop(0)
            return self.reply(act)
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake) as req:
            a.worker(s,cid)
            self.assertEqual(req.call_count,8)
        self.assertEqual(actions,[])
        with s.db() as c:
            state=a.status(c,self.cfg)
            self.assertEqual(state['state'],'terminé')
            self.assertEqual([x['kind'] for x in state['missions']],['functional','market','opportunity'])
            self.assertEqual(state['searches'],0)
            self.assertGreater(state['spent'],11000)
            self.assertEqual(c.execute('SELECT turns FROM tasks WHERE id=?',(tid,)).fetchone()[0],10)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM reports WHERE mission=? AND agent='HERMES'",(mid,)).fetchone()[0],1)
    def test_wrong_target_changed_file_exhausted(self):
        cid,mid,tid,aid,data=self.blocked()
        with s.db() as c:
            c.execute('UPDATE tasks SET turns=10 WHERE id=?',(tid,))
            self.assertIsNone(w.recovery_task(c,mid,self.cfg))
            c.execute('UPDATE tasks SET turns=9 WHERE id=?',(tid,))
            c.execute("UPDATE missions SET error=? WHERE id=?",('Action identique répétée trois fois; tâche #'+str(tid)+' ; outil read_file ; cible ref:999',mid))
            self.assertIsNone(w.recovery_task(c,mid,self.cfg))
            c.execute("UPDATE missions SET error=? WHERE id=?",('Action identique répétée trois fois; tâche #'+str(tid)+' ; outil read_file ; cible ref:'+str(aid),mid))
            c.execute("UPDATE artifacts SET content='modifié' WHERE id=?",(aid,))
            self.assertIsNone(w.recovery_task(c,mid,self.cfg))
    def test_new_file_version_remains_readable(self):
        with s.db() as c:
            mid=m.create(s,c,'Production','cloud')
            tid=m.add_task(c,mid,'NEXUS','Créer')
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'kit.csv',1,'NEXUS','a,b','test')",(mid,)).lastrowid
            v=self.act('read_file','kit.csv')
            m.log(c,t,'read_file',m.action_args(v),{'fichier':aid,'contenu':'a,b'},True)
            work=w.snapshot(c,t)
            self.assertTrue(w.redundant(c,t,v,work,m.resolve_artifact))
            self.assertNotIn('read_file',w.policy(c,t,self.cfg,m.PERMS['NEXUS'],work))
            c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?,'kit.csv',2,'NEXUS','a,b\n1,2','test')",(mid,))
            self.assertFalse(w.redundant(c,t,v,work,m.resolve_artifact))
            self.assertIn('read_file',w.policy(c,t,self.cfg,m.PERMS['NEXUS'],work))
    def test_memory_cap_and_task_isolation(self):
        with s.db() as c:
            mid=m.create(s,c,'Étude','cloud')
            tid=m.add_task(c,mid,'ORION','Recherche');other=m.add_task(c,mid,'MIDAS','Finance')
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
            ot=dict(c.execute('SELECT * FROM tasks WHERE id=?',(other,)).fetchone())
            for i in range(3):m.log(c,t,'memory',m.action_args(self.act('memory',text=str(i))),{'résultats':[]},True)
            self.assertNotIn('memory',w.policy(c,t,self.cfg,m.PERMS['ORION'],w.snapshot(c,t)))
            self.assertIn('memory',w.policy(c,ot,self.cfg,m.PERMS['MIDAS'],w.snapshot(c,ot)))
            self.assertNotIn('search',w.policy(c,t,{**self.cfg,'brave':''},m.PERMS['ORION'],w.snapshot(c,t)))
            self.assertNotIn('read',w.policy(c,t,self.cfg,m.PERMS['ORION'],w.snapshot(c,t)))
