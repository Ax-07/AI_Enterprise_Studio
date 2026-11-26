import os
import secrets
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import acquisition_runtime as rt
import acquisition_sync as sync
import public_channel as ch

class AcquisitionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'channel.sqlite3'
        self.reset=patch.multiple(rt,_managed=False,_process=None,_key=None,_attempts=0,_state='not_started')
        self.reset.start()
        self.addCleanup(self.reset.stop)
        self.addCleanup(rt.stop)

    def test_real_child_start_stop_and_restart_revokes_previous_grant(self):
        self.assertTrue(rt.start(self.path))
        key=rt.runtime_key()
        self.assertEqual(len(key),32)
        self.assertEqual(sync.key(),key)
        self.assertTrue(rt.status()['ready'])
        t=int(time.time());page=secrets.token_hex(16)
        m={'id':page,'mode':'test','snapshot':'b'*64,'offer':5,'title':'Test',
           'description':'Fictif','limitations':'Pas de vente','price_cents':4900,'starts':t,'expires':t+600}
        sync.request_admin('publish',{'payload':m,'signature':ch.sign(key,'publication-v1',m)},key)
        old=rt._process
        old.terminate();old.wait(timeout=5)
        self.assertFalse(rt.status()['ready'])
        calls=[]
        rt.maintain(self.path,lambda:calls.append('stop_grants'))
        self.assertEqual(calls,['stop_grants'])
        self.assertTrue(rt.status()['ready'])
        new=sync.key()
        self.assertNotEqual(key,new)
        nonce=secrets.token_hex(16)
        proof=sync.request_admin('status',{'page':page,'nonce':nonce},new)
        ch.check(new,'status-v1',proof['payload'],proof['signature'])
        self.assertTrue(proof['payload']['publication_revoked'])
        self.assertFalse(proof['payload']['publication_open'])
        proc=rt._process
        rt.stop()
        self.assertIsNotNone(proc.poll())
        self.assertFalse(sync.configured())
        with self.assertRaises(ValueError):sync.key()

    def test_collision_does_not_mutate_database_and_retry_bounded(self):
        with socket.socket() as blocker:
            blocker.bind(('127.0.0.1',rt.PORT))
            blocker.listen()
            self.assertFalse(rt.start(self.path))
            self.assertFalse(self.path.exists())
            for _ in range(4):rt.maintain(self.path,lambda:None)
            self.assertEqual(rt.status()['attempts'],rt.MAX_STARTS)
            self.assertEqual(rt.status()['state'],'retry_limit')
            self.assertFalse(sync.configured())

    def test_secret_environment_allowlist_and_separate_database(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-secret','BRAVE_API_KEY':'test-secret',
                                    'AES_N8N_TOKEN':'test-secret','PYTHONPATH':'test-secret',
                                    'AES_CHANNEL_TEST_KEY_HEX':'a'*64,'LOCALAPPDATA':self.tmp.name}):
            env=rt.child_environment()
            for name in ('OPENAI_API_KEY','BRAVE_API_KEY','AES_N8N_TOKEN','PYTHONPATH','AES_CHANNEL_TEST_KEY_HEX'):
                self.assertNotIn(name,env)
            one=rt.database_path(Path(self.tmp.name)/'one'/'enterprise.sqlite3')
            two=rt.database_path(Path(self.tmp.name)/'two'/'enterprise.sqlite3')
            self.assertNotEqual(one,two)
            self.assertNotIn('one',one.parts)
            with patch.object(rt,'_managed',True):
                self.assertFalse(sync.configured())
                with self.assertRaises(ValueError):sync.key()
