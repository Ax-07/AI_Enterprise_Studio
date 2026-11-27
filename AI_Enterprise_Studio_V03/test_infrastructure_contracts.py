"""R03 integration contracts: temporary database, synthetic responses, no paid API."""
from contextlib import ExitStack
from email.message import Message
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import serveur as s
import preview_campus
from infrastructure import database, diagnostics, providers


class InfrastructureImportTests(unittest.TestCase):
    def test_imports_are_inert_and_do_not_load_business_modules(self):
        root=Path(__file__).resolve().parent
        script=r"""
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
from infrastructure import configuration, database, providers, security, diagnostics
assert not ({'serveur','moteur','autopilot','planner','periodic','campus_tools','campus_live'} & set(sys.modules))
"""
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,'-I','-B','-c',script,str(root)],
                                  cwd=directory,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(list(Path(directory).iterdir()),[])


class InfrastructureFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.path=self.root/'fixture.sqlite3'
        self.stack.enter_context(patch.object(s,'DB',self.path))
        self.stack.enter_context(patch.dict(os.environ,{'OPENAI_API_KEY':'','BRAVE_API_KEY':''}))
        self.transport=self.stack.enter_context(patch.object(providers.urllib.request,'urlopen',
                                    side_effect=AssertionError('unexpected external transport')))
        s.init()
        self.stack.enter_context(patch.object(s,'ROOT',self.root))
        self.write_config(2)
        with s.db() as c:
            self.mid=c.execute("INSERT INTO missions(title,mode,state) VALUES('fixture','cloud','en cours')").lastrowid

    def write_config(self,budget):
        (self.root/'config.json').write_text(json.dumps({
            'openai_budget_usd':budget,'openai_api_key':'fixture-key'}),encoding='utf-8')

    def ledger(self):
        with database.read_snapshot(self.path) as c:
            return [dict(row) for row in c.execute(
                'SELECT * FROM ledger WHERE mission=? ORDER BY id',(self.mid,))]

    def call(self):
        return s.call_model(self.mid,'ATLAS','fixture prompt',s.config(),maxout=128)

    def test_zero_budget_refuses_before_transport_or_reservation(self):
        self.write_config(0)
        with self.assertRaisesRegex(RuntimeError,'Budget logiciel insuffisant'):
            self.call()
        self.transport.assert_not_called()
        self.assertEqual(self.ledger(),[])

    def test_reservation_precedes_transport_and_measured_cost_matches_diagnostic(self):
        value={'rapport':'fixture','requetes':[],'demandes':[]}
        result={'status':'completed','usage':{'input_tokens':100,'output_tokens':20,
                    'output_tokens_details':{'reasoning_tokens':3}},
                'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        def reply(request,timeout):
            rows=self.ledger()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['state'],'réservé')
            self.assertGreater(rows[0]['reserved'],0)
            self.assertIsNone(rows[0]['actual'])
            self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
            self.assertEqual(request.get_header('Authorization'),'Bearer fixture-key')
            self.assertEqual(timeout,120)
            body=json.loads(request.data)
            self.assertEqual(body['model'],s.DEFAULT['ATLAS'])
            self.assertEqual(body['max_output_tokens'],128)
            self.assertFalse(body['store'])
            response=MagicMock()
            response.__enter__.return_value.read.return_value=json.dumps(result).encode()
            return response
        self.transport.side_effect=reply
        self.assertEqual(self.call(),value)
        self.transport.assert_called_once()
        row=self.ledger()[0]
        self.assertEqual((row['state'],row['actual'],row['reasoning_tokens']),('mesuré',400,3))
        with database.read_snapshot(self.path) as c:
            self.assertEqual(s.used(c),400)
            report=diagnostics.mission(c,self.mid)
            self.assertEqual(report['calls'],1)
            self.assertEqual(report['estimated_usd'],.0004)
            self.assertNotIn('fixture-key',json.dumps(report))

    def test_transport_failure_preserves_reservation_without_raw_error(self):
        self.transport.side_effect=TimeoutError('private-fixture')
        with self.assertRaisesRegex(RuntimeError,'réservation conservée') as error:
            self.call()
        self.assertNotIn('private-fixture',str(error.exception))
        row=self.ledger()[0]
        self.assertEqual(row['state'],'à rapprocher')
        self.assertIsNone(row['actual'])
        self.assertGreater(row['reserved'],0)
        self.assertEqual(row['diagnostic'],'TimeoutError')
        with database.read_snapshot(self.path) as c:
            self.assertEqual(s.used(c),row['reserved'])
            self.assertEqual(diagnostics.mission(c,self.mid)['estimated_usd'],row['reserved']/1e6)

    def test_invalid_model_output_is_measured_but_not_accepted(self):
        result={'status':'completed','usage':{'input_tokens':100,'output_tokens':20},
                'output':[{'type':'message','content':[{'type':'output_text',
                    'text':'{"private-fixture": }'}]}]}
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps(result).encode()
        self.transport.side_effect=None
        self.transport.return_value=response
        with self.assertRaisesRegex(s.InvalidModelOutput,'JSON non décodable') as error:
            self.call()
        self.assertNotIn('private-fixture',str(error.exception))
        row=self.ledger()[0]
        self.assertEqual((row['state'],row['actual']),('mesuré',400))
        self.assertIn('JSON non décodable',row['diagnostic'])
        self.assertNotIn('private-fixture',row['diagnostic'])


class InfrastructureHTTPTests(unittest.TestCase):
    def handler(self,cls,path,values):
        handler=object.__new__(cls)
        handler.path=path
        handler.headers=Message()
        for name,value in values.items():
            handler.headers[name]=value
        handler.send=MagicMock()
        handler.rfile=MagicMock()
        handler.rfile.read.side_effect=AssertionError('body read before authorization')
        return handler

    def test_rejected_commands_do_not_read_body_or_configuration(self):
        base={'Host':f'localhost:{s.PORT}','Origin':f'http://localhost:{s.PORT}',
              'Content-Type':'application/json','Content-Length':'2'}
        cases=[
            ('/campus/command',{'X-Campus-Command':s.CAMPUS_READ_SESSION}),
            ('/campus/owner-command',{'X-Campus-Owner':s.CAMPUS_COMMAND_SESSION}),
            ('/campus/command?x=1',{'X-Campus-Command':s.CAMPUS_COMMAND_SESSION}),
            ('/api/resume',{'X-Session':s.SESSION,'Origin':'https://example.invalid'}),
        ]
        with patch.object(s,'config',side_effect=AssertionError('configuration before authorization')) as config:
            for path,extra in cases:
                with self.subTest(path=path):
                    handler=self.handler(s.Handler,path,base|extra)
                    handler._post()
                    self.assertEqual(handler.send.call_args.args[1],403)
                    handler.rfile.read.assert_not_called()
            config.assert_not_called()

    def test_preview_rejects_even_valid_owner_session(self):
        handler=self.handler(preview_campus.PreviewHandler,'/campus/owner-command',{
            'Host':f'localhost:{s.PORT}','Origin':f'http://localhost:{s.PORT}',
            'X-Campus-Owner':s.CAMPUS_OWNER_SESSION,'Content-Type':'application/json'})
        handler.do_POST()
        handler.send.assert_called_once_with({'error':'Aperçu en lecture seule : commandes interdites'},403)
        handler.rfile.read.assert_not_called()


if __name__=='__main__':
    unittest.main()
