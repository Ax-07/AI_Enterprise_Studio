import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import serveur as s
import moteur as m

class References(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p=patch.object(s,'DB',Path(self.tmp.name)/'db')
        p.start();self.addCleanup(p.stop)
        s.init()
        self.cfg=s.config()
        with s.db() as c:
            self.old=m.create(s,c,'Source','cloud')
            self.aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?, 'kit.csv',1,'NEXUS','a,b\n1,2\n','test')",(self.old,)).lastrowid
            self.other=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?, 'kit.csv',2,'NEXUS','a,b\n3,4\n','test')",(self.old,)).lastrowid
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(self.old,))
            self.new=m.create(s,c,'Amélioration','cloud',self.aid)
    def act(self,agent,action,target='',text=''):
        with s.db() as c:
            tid=m.add_task(c,self.new,agent,'test')
            t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
        return m.execute(s,t,dict(action=action,target=target,text=text,detail=''),self.cfg,'cloud')
    def test_exact_reference_and_permissions(self):
        self.assertEqual(self.act('NEXUS','read_file','ref:'+str(self.aid))['contenu'],'a,b\n1,2\n')
        self.assertTrue(self.act('SENTINEL','check_file','ref:'+str(self.aid))['valide'])
        self.assertEqual(self.act('ATLAS','list_files')[0]['target'],'ref:'+str(self.aid))
        for agent,target in [('NEXUS','ref:'+str(self.other)),('ORION','ref:'+str(self.aid)),('NEXUS','kit.csv')]:
            with self.assertRaises(ValueError):self.act(agent,'read_file',target)
    def test_new_file_preserves_source(self):
        self.act('NEXUS','write_file','kit.csv','a,b\n9,8\n')
        self.assertEqual(self.act('NEXUS','read_file','kit.csv')['contenu'],'a,b\n9,8\n')
        self.assertEqual(self.act('NEXUS','read_file','ref:'+str(self.aid))['contenu'],'a,b\n1,2\n')
        with self.assertRaises(ValueError):self.act('NEXUS','write_file','ref:'+str(self.aid),'bad')
    def test_invalid_refs(self):
        for mode,aid in [('demo',self.aid),('cloud',True),('cloud',99999999)]:
            with self.assertRaises(ValueError):
                with s.db() as c:m.create(s,c,'Refus',mode,aid)
    def test_context(self):
        with s.db() as c:
            t=dict(c.execute('SELECT * FROM tasks WHERE mission=?',(self.new,)).fetchone())
            mission=dict(c.execute('SELECT * FROM missions WHERE id=?',(self.new,)).fetchone())
        context=m.context(s,t,mission,self.cfg)
        self.assertIn('ref:'+str(self.aid),context)
        self.assertIn('lecture_seule',context)
        self.assertNotIn('a,b\\n1,2',context)
