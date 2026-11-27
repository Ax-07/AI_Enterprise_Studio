"""Bounded cycles and scoped visibility; no external execution."""
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

import hermes_acquisition as h
import marketing as mk
import marketing_templates as templates
from departments import marketing_coordination as coord


class MarketingCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.row_factory=sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE projects(id INTEGER PRIMARY KEY,state TEXT);
            CREATE TABLE acquisition_drafts(id INTEGER PRIMARY KEY,offer INTEGER,snapshot_sha256 TEXT,language TEXT);
            CREATE TABLE hermes_preparations(draft INTEGER PRIMARY KEY);
            CREATE TABLE marketing_drafts(draft INTEGER,revision INTEGER);
        """)
        self.c.executemany('INSERT INTO projects VALUES(?,?)',[(i,'active') for i in range(1,7)]+[(7,'paused')])
        self.c.executemany('INSERT INTO hermes_preparations VALUES(?)',[(i,) for i in range(10,16)])

    def test_acquisition_cycle_bound_order_and_active_projects(self):
        commercial=Mock()
        commercial.project_status.side_effect=lambda c,p:{'offer':{'id':p}}
        business=Mock()
        business.gate.return_value=({},True,None)
        business.digest.return_value='snap'
        acquisition=Mock()
        acquisition.prepare.side_effect=lambda c,body,t:body['offer']
        prepare=Mock()
        self.assertEqual(coord.acquisition_cycle(self.c,5,b=business,commercial=commercial,
                         ac=acquisition,prepare=prepare,max_per_cycle=3),[1,2,3])
        self.assertEqual([x.args[1] for x in commercial.project_status.call_args_list],[1,2,3])
        self.assertEqual([x.args[1] for x in prepare.call_args_list],[1,2,3])
        self.assertTrue(all(x.args[1]['confirm'] is True and x.args[1]['language']=='fr'
                            for x in acquisition.prepare.call_args_list))
        business.now.assert_not_called()

    def test_acquisition_skips_existing_revoked_and_ineligible(self):
        self.c.executemany('INSERT INTO acquisition_drafts VALUES(?,?,?,?)',
                           [(10,1,'snap','fr'),(20,2,'snap','fr')])
        commercial=Mock()
        commercial.project_status.side_effect=lambda c,p:{'offer':{'id':p}}
        business=Mock()
        business.offer_row.side_effect=lambda c,p:p
        business.gate.side_effect=lambda c,p:({},p!=3,None)
        business.digest.return_value='snap'
        business.now.return_value=9
        acquisition=Mock()
        acquisition.state.side_effect=lambda c,row:'revoked' if row['id']==20 else 'draft'
        acquisition.prepare.side_effect=lambda c,body,t:body['offer']
        prepare=Mock(side_effect=[ValueError('fixture'),None,None])
        self.assertEqual(coord.acquisition_cycle(self.c,b=business,commercial=commercial,
                         ac=acquisition,prepare=prepare,max_per_cycle=3),[5,6])
        self.assertEqual([x.args[1]['offer'] for x in acquisition.prepare.call_args_list],[4,5,6])
        self.assertTrue(all(x.args[2]==9 for x in prepare.call_args_list))
        business.now.assert_called_once_with()

    def test_content_cycle_bound_revision_and_local_failure(self):
        self.c.execute('INSERT INTO marketing_drafts VALUES(?,?)',(10,templates.REVISION))
        self.c.execute('INSERT INTO marketing_drafts VALUES(?,?)',(11,templates.REVISION+1))
        business=Mock()
        business.now.return_value=12
        prepare=Mock(side_effect=[RuntimeError('fixture'),None,None,None])
        self.assertEqual(coord.content_cycle(self.c,b=business,templates=templates,prepare=prepare),[12,13,14])
        self.assertEqual([x.args[1:] for x in prepare.call_args_list],[(11,12),(12,12),(13,12),(14,12)])
        business.now.assert_called_once_with()

    def scope(self,**changes):
        return {'project':7,'state':'actif','mission_state':'en cours','mode':'cloud',
                'project_state':'active','permissions':json.dumps({'market':True,'tests':True}),**changes}

    def test_context_denial_before_status_for_all_guards(self):
        for fn,agent in ((coord.acquisition_context,'HERMES'),(coord.content_context,'SENTINEL')):
            for scope in (None,self.scope(state='arrêté'),self.scope(mission_state='terminée'),
                          self.scope(mode='simulation'),self.scope(project_state='paused'),
                          self.scope(permissions='{"market":false,"tests":true}')):
                with self.subTest(fn=fn.__name__,scope=scope):
                    commercial=Mock();commercial.scope.return_value=scope
                    status=Mock()
                    self.assertIsNone(fn(self.c,1,agent,commercial=commercial,json=json,status=status))
                    status.assert_not_called()
            commercial=Mock();status=Mock()
            self.assertIsNone(fn(self.c,1,'ATLAS',commercial=commercial,json=json,status=status))
            commercial.scope.assert_not_called();status.assert_not_called()

    def test_acquisition_context_ready_only_and_max_three(self):
        commercial=Mock();commercial.scope.return_value=self.scope()
        status=Mock(return_value={'packets':[{'draft':0,'state':'unavailable'}]+
                                  [{'draft':i,'state':'internal_ready'} for i in range(1,6)],
                                  'external_authorized':False})
        out=coord.acquisition_context(self.c,1,'HERMES',commercial=commercial,json=json,status=status)
        self.assertEqual([x['draft'] for x in out['packets']],[1,2,3])
        self.assertFalse(out['external_authorized'])
        status.assert_called_once_with(self.c,7)

    def test_content_context_separate_test_permission_and_bounded(self):
        commercial=Mock()
        commercial.scope.return_value=self.scope(permissions='{"market":true,"tests":false}')
        status=Mock(return_value={'drafts':[{'draft':i,'state':'unavailable'} for i in range(5)],
                                  'publication_authorized':False,'video_generated':False})
        self.assertIsNone(coord.content_context(self.c,1,'SENTINEL',commercial=commercial,json=json,status=status))
        status.assert_not_called()
        out=coord.content_context(self.c,1,'HERMES',commercial=commercial,json=json,status=status)
        self.assertEqual([x['draft'] for x in out['drafts']],[0,1,2])
        self.assertFalse(out['publication_authorized'])
        status.assert_called_once_with(self.c,7)

    def test_live_legacy_callbacks_for_both_cycles_and_contexts(self):
        with patch.object(coord,'acquisition_cycle',return_value=[1]) as cycle:
            self.assertEqual(h.run_once(self.c,5),[1])
            cycle.assert_called_once_with(self.c,5,b=h.b,commercial=h.commercial,ac=h.ac,
                                          prepare=h.prepare,max_per_cycle=h.MAX_PER_CYCLE)
        with patch.object(coord,'content_cycle',return_value=[2]) as cycle:
            self.assertEqual(mk.run_once(self.c,5),[2])
            cycle.assert_called_once_with(self.c,5,b=mk.b,templates=mk.templates,prepare=mk.prepare)
        for module,name in ((h,'acquisition_context'),(mk,'content_context')):
            with patch.object(coord,name,return_value={'fixture':True}) as context:
                self.assertEqual(module.agent_context(self.c,1,'HERMES'),{'fixture':True})
                context.assert_called_once_with(self.c,1,'HERMES',commercial=module.commercial,
                                                json=module.json,status=module.status)


if __name__=='__main__':
    unittest.main()
