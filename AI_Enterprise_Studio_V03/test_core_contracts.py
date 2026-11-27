"""R04 transverse contracts on the real application schema and fake transport."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import connectors
import moteur as m
import serveur as s
from infrastructure import providers


class CoreImportTests(unittest.TestCase):
    def test_nine_modules_import_without_io_or_business_dependencies(self):
        root = Path(__file__).resolve().parent
        script = r"""
import os, sys
def guard(event, args):
    if event == 'open':
        flags = args[2]
        if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError('write on import')
    if event in ('sqlite3.connect', 'socket.connect', 'socket.getaddrinfo',
                 'subprocess.Popen', 'os.mkdir', 'os.remove', 'os.rename'):
        raise AssertionError('side effect on import: '+event)
sys.addaudithook(guard)
sys.path.insert(0,sys.argv[1])
from core import (agents, permissions, tool_catalog, execution, internal_execution,
                  collaboration, orchestration, turn_execution, model_turn)
assert not ({'serveur','moteur','autopilot','planner','periodic','commercial',
             'connectors','working_memory','campus_tools','campus_live'} & set(sys.modules))
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable,'-I','-B','-c',script,str(root)],
                                    cwd=directory,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(list(Path(directory).iterdir()),[])


class CoreMissionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(s,'DB',self.root/'fixture.sqlite3'))
        self.stack.enter_context(patch.dict(os.environ,{'OPENAI_API_KEY':'','BRAVE_API_KEY':''}))
        self.transport = self.stack.enter_context(patch.object(
            providers.urllib.request,'urlopen',
            side_effect=AssertionError('unexpected transport')))
        self.search = self.stack.enter_context(patch.object(
            s,'search',side_effect=AssertionError('unexpected search')))
        self.fetch = self.stack.enter_context(patch.object(
            m,'fetch_page',side_effect=AssertionError('unexpected read')))
        self.invoke = self.stack.enter_context(patch.object(
            connectors,'invoke',side_effect=AssertionError('unexpected connector')))
        s.init()
        self.stack.enter_context(patch.object(s,'ROOT',self.root))
        self.write_config(2)

    def write_config(self,budget):
        (self.root/'config.json').write_text(json.dumps({
            'openai_budget_usd':budget,'openai_api_key':'fixture-key'}),
            encoding='utf-8')

    def mission(self,mode='cloud',turns=0):
        with s.db() as c:
            if mode=='demo':
                return m.create(s,c,'fixture demo','demo')
            mid=c.execute("INSERT INTO missions(title,mode,state,engine) VALUES('fixture','cloud','en cours','dynamic')").lastrowid
            tid=m.add_task(c,mid,'ORION','fixture research')
            c.execute('UPDATE tasks SET turns=? WHERE id=?',(turns,tid))
            return mid

    def rows(self,table,mid):
        # Fixed fixture table names only.
        self.assertIn(table,('tasks','events','reports','ledger','artifacts','opportunities','rewards','searches'))
        with s.db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM '+table+' WHERE mission=? ORDER BY id',(mid,))]

    def status(self,mid):
        with s.db() as c:
            return tuple(c.execute('SELECT state,error FROM missions WHERE id=?',(mid,)).fetchone())

    def assert_no_other_transport(self):
        self.search.assert_not_called()
        self.fetch.assert_not_called()
        self.invoke.assert_not_called()

    def feed(self,mid,*outputs):
        remaining=iter(outputs)
        self.payloads=[]
        def reply(request,timeout):
            self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
            self.assertEqual(timeout,120)
            payload=json.loads(request.data)
            self.payloads.append(payload)
            self.assertFalse(payload['store'])
            row=self.rows('ledger',mid)[-1]
            self.assertEqual(row['state'],'réservé')
            self.assertGreater(row['reserved'],0)
            self.assertIsNone(row['actual'])
            raw=next(remaining)
            response=MagicMock()
            result={'status':'completed','usage':{'input_tokens':100,'output_tokens':20},
                    'output':[{'type':'message','content':[{'type':'output_text','text':raw}]}]}
            response.__enter__.return_value.read.return_value=json.dumps(result).encode()
            return response
        self.transport.side_effect=reply

    @staticmethod
    def action(action='finish',text='fixture report'):
        return json.dumps({'action':action,'target':'','text':text,'detail':''})

    def test_full_demo_delegation_production_audit_and_reports(self):
        mid=self.mission('demo')
        m.run(s,mid)
        self.assertEqual(self.status(mid),('terminée',''))
        self.assertEqual([r['agent'] for r in self.rows('tasks',mid)],
                         ['ATLAS','ORION','NEXUS','MIDAS','SENTINEL'])
        self.assertTrue(all(r['state']=='terminée' for r in self.rows('tasks',mid)))
        events=self.rows('events',mid)
        self.assertEqual([r['action'] for r in events],
                         ['delegate','opportunity','finish','delegate','write_file','finish',
                          'delegate','calculate','finish','delegate','check_file','finish','finish'])
        self.assertTrue(all(r['ok']==1 for r in events))
        self.assertEqual(len(self.rows('reports',mid)),5)
        self.assertEqual(self.rows('artifacts',mid)[0]['name'],'exemple.csv')
        self.assertEqual(self.rows('opportunities',mid)[0]['status'],'hypothèse')
        self.assertEqual(self.rows('rewards',mid),[])
        self.assertEqual(self.rows('ledger',mid),[])
        self.assertEqual(self.rows('searches',mid),[])
        self.transport.assert_not_called()
        self.assert_no_other_transport()

    def test_cloud_invalid_json_then_finish_counts_two_calls_one_action(self):
        mid=self.mission()
        self.feed(mid,'{"private-fixture": }',self.action())
        m.run(s,mid)
        self.assertEqual(self.status(mid),('terminée',''))
        self.assertEqual(self.transport.call_count,2)
        self.assertEqual([r['action'] for r in self.rows('events',mid)],['finish'])
        self.assertEqual(self.rows('tasks',mid)[0]['turns'],1)
        self.assertEqual(len(self.rows('reports',mid)),1)
        ledger=self.rows('ledger',mid)
        self.assertEqual(len(ledger),2)
        self.assertTrue(all(r['state']=='mesuré' and r['actual']>0 for r in ledger))
        self.assertIn('JSON non décodable',ledger[0]['diagnostic'])
        self.assertNotIn('private-fixture',ledger[0]['diagnostic'])
        self.assertEqual([p['max_output_tokens'] for p in self.payloads],[4096,8192])
        self.assertEqual(self.payloads[0]['text'],self.payloads[1]['text'])
        self.assertIn('Tentative de correction unique',self.payloads[1]['input'])
        self.assert_no_other_transport()

    def test_cloud_second_invalid_response_blocks_without_action(self):
        mid=self.mission()
        self.feed(mid,'{}','{}')
        m.run(s,mid)
        state,error=self.status(mid)
        self.assertEqual(state,'bloquée')
        self.assertIn('Correction unique épuisée',error)
        self.assertEqual(self.transport.call_count,2)
        self.assertEqual(len(self.rows('ledger',mid)),2)
        self.assertTrue(all(r['state']=='mesuré' for r in self.rows('ledger',mid)))
        self.assertEqual(self.rows('events',mid),[])
        self.assertEqual(self.rows('reports',mid),[])
        self.assertEqual(self.rows('tasks',mid)[0]['turns'],0)
        self.assert_no_other_transport()

    def test_cloud_budget_zero_refuses_before_transport(self):
        mid=self.mission()
        self.write_config(0)
        m.run(s,mid)
        state,error=self.status(mid)
        self.assertEqual(state,'bloquée')
        self.assertIn('Budget logiciel insuffisant',error)
        self.transport.assert_not_called()
        self.assertEqual(self.rows('ledger',mid),[])
        self.assertEqual(self.rows('events',mid),[])
        self.assertEqual(self.rows('tasks',mid)[0]['turns'],0)
        self.assert_no_other_transport()

    def test_cloud_final_turn_cannot_execute_calculate_even_after_retry(self):
        mid=self.mission(turns=s.config()['turn_limit']-1)
        self.feed(mid,self.action('calculate','1+1'),self.action())
        m.run(s,mid)
        self.assertEqual(self.status(mid),('terminée',''))
        self.assertEqual(self.transport.call_count,2)
        self.assertEqual([p['max_output_tokens'] for p in self.payloads],[2048,4096])
        for payload in self.payloads:
            self.assertEqual(payload['text']['format']['schema']['properties']['action']['enum'],['finish'])
        self.assertEqual([r['action'] for r in self.rows('events',mid)],['finish'])
        self.assertEqual(len(self.rows('reports',mid)),1)
        self.assert_no_other_transport()


if __name__=='__main__':
    unittest.main()
