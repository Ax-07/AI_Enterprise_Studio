import unittest
from unittest.mock import patch
import serveur as s,autopilot as a,improvement as i,portfolio as p
from test_improvement import ImprovementTests,CANDIDATE

class OwnerConsoleTests(unittest.TestCase):
    setUp=ImprovementTests.setUp
    start=ImprovementTests.start
    act=ImprovementTests.act
    reply=ImprovementTests.reply
    product=ImprovementTests.product
    prepared=ImprovementTests.prepared
    produce=ImprovementTests.produce

    def test_completed_cycle_allows_new_campaign_without_mutation(self):
        pid,aid=self.prepared()
        cid=self.start(project=pid,improvement=i.CSV_PROFILE,max_missions=1)
        self.produce(cid,CANDIDATE)
        with s.db() as c:
            self.assertTrue(a.readiness(c,self.cfg)['ready'])
            self.assertEqual(a.status(c)['state'],'terminé')
            self.assertEqual(i.cycle(c,cid)['state'],'retained')
            new=p.latest(c,pid)['id']
        other=self.start(project=pid,budget='0.50',max_missions=3)
        with s.db() as c:
            self.assertNotEqual(cid,other)
            self.assertEqual(a._campaign(c,cid)['state'],'terminé')
            self.assertEqual(a._campaign(c,other)['source'],new)
            self.assertEqual(i.cycle(c,cid)['candidate'],new)
            self.assertEqual(p.latest(c,pid)['id'],new)

    def test_readiness_distinguishes_lock_and_active_campaign(self):
        with s.db() as c:
            self.assertTrue(a.readiness(c,self.cfg)['ready'])
            self.assertIn('Moteur local occupé',a.readiness(c,self.cfg,True)['blockers'][0])
            self.assertFalse(a.readiness(c,{**self.cfg,'key':''})['ready'])
            self.assertFalse(a.readiness(c,{**self.cfg,'budget':9999})['ready'])
        cid=self.start()
        with s.db() as c:
            r=a.readiness(c,self.cfg)
            self.assertEqual(r['active_campaign'],cid)
            self.assertFalse(r['ready'])
            a.stop(c,cid)
            self.assertTrue(a.readiness(c,self.cfg)['ready'])
