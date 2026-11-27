"""Exact commercial documentary retrieval on local SQLite fixtures."""
import json
import sqlite3
import unittest
from unittest.mock import patch

import commercial as co
import intelligence as intel
from departments import commercial_evidence as ce


class CommercialEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.row_factory=sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE missions(id INTEGER PRIMARY KEY,mode TEXT,state TEXT);
            CREATE TABLE fetched(id INTEGER PRIMARY KEY,mission INTEGER,url TEXT,state TEXT,
                                 content TEXT,created TEXT DEFAULT '2026-11-25');
            CREATE TABLE commercial_signals(id INTEGER PRIMARY KEY,project INTEGER,mission INTEGER,
                page INTEGER,kind TEXT,quote TEXT,interpretation TEXT,proof TEXT,
                created TEXT DEFAULT '2026-11-25');
        """)
        self.c.executemany('INSERT INTO missions VALUES(?,?,?)',
                          [(1,'cloud','terminée'),(2,'cloud','en cours'),
                           (3,'cloud','terminée'),(4,'demo','terminée'),(5,'cloud','bloquée')])

    def add(self,mid=1,pid=10,quote='Les erreurs coûtent du temps.',body=None,kind='buyer_problem'):
        url='https://fixture.example/document'
        text=body if body is not None else quote+' '+('Extrait documentaire synthétique uniquement. '*5)
        page=self.c.execute("INSERT INTO fetched(mission,url,state,content) VALUES(?,?,'reçue',?)",
            (mid,url,json.dumps({'url':url,'texte':text,'date':'2026-11-25'}))).lastrowid
        proof=intel.page_reference(self.c,mid,page)
        sid=self.c.execute('INSERT INTO commercial_signals(project,mission,page,kind,quote,interpretation,proof) VALUES(?,?,?,?,?,?,?)',
            (pid,mid,page,kind,quote,'Interprétation non certifiée.',intel.canonical(proof))).lastrowid
        return sid,page,proof

    def test_exact_proof_and_read_only(self):
        sid,page,proof=self.add()
        before=self.c.total_changes
        self.c.execute('PRAGMA query_only=ON')
        row,ref=co._signal(self.c,10,sid,None)
        self.assertEqual(ref,proof)
        self.assertEqual(co._proof(self.c,row),proof)
        self.assertEqual(co.signals(self.c,10),[{'id':sid,'mission':1,'kind':'buyer_problem',
            'quote':row['quote'],'interpretation':row['interpretation'],'created':row['created'],
            'proof':proof,'quality':'text_available'}])
        self.assertEqual(self.c.total_changes,before)

    def test_project_and_cloud_scope(self):
        valid,_,_=self.add()
        other,_,_=self.add(pid=20)
        simulated,_,_=self.add(mid=4)
        blocked,_,_=self.add(mid=5)
        self.assertEqual([x['id'] for x in co.signals(self.c,10)],[valid])
        self.assertEqual([x['id'] for x in co.signals(self.c,20)],[other])
        for sid in (other,simulated,blocked,999):
            with self.subTest(sid=sid),self.assertRaisesRegex(ValueError,'Signal de cette activité requis'):
                co._signal(self.c,10,sid,None)

    def test_mission_context_and_historical_cutoff(self):
        old,_,_=self.add(mid=1)
        current,_,_=self.add(mid=2)
        future,_,_=self.add(mid=3)
        self.assertEqual([x['id'] for x in co.signals(self.c,10)],[future,old])
        self.assertEqual([x['id'] for x in co.signals(self.c,10,2)],[current,old])
        self.assertEqual(co._signal(self.c,10,current,2)[0]['id'],current)
        with self.assertRaises(ValueError):co._signal(self.c,10,current,None)
        # Historical direct lookup deliberately differs from the bounded listing.
        self.assertEqual(co._signal(self.c,10,future,2)[0]['id'],future)

    def test_quote_and_excerpt_fingerprint_must_both_match(self):
        sid,page,proof=self.add()
        original=self.c.execute('SELECT content FROM fetched WHERE id=?',(page,)).fetchone()[0]
        data=json.loads(original);data['texte']+=' Texte ajouté.'
        self.c.execute('UPDATE fetched SET content=? WHERE id=?',(json.dumps(data),page))
        self.assertEqual(co.signals(self.c,10),[])
        with self.assertRaisesRegex(ValueError,'Citation ou empreinte modifiée'):
            co._signal(self.c,10,sid,None)
        self.c.execute('UPDATE fetched SET content=? WHERE id=?',(original,page))
        self.c.execute("UPDATE commercial_signals SET quote='Citation absente' WHERE id=?",(sid,))
        self.assertEqual(co.signals(self.c,10),[])
        with self.assertRaisesRegex(ValueError,'Citation ou empreinte modifiée'):
            co._signal(self.c,10,sid,None)

    def test_page_mission_state_and_url_binding(self):
        sid,page,proof=self.add()
        for sql,args in (
            ("UPDATE fetched SET mission=2 WHERE id=?",(page,)),
            ("UPDATE fetched SET mission=1,state='erreur' WHERE id=?",(page,)),
            ("UPDATE fetched SET state='reçue',url='https://other.example/' WHERE id=?",(page,))):
            self.c.execute(sql,args)
            self.assertEqual(co.signals(self.c,10),[])
            with self.assertRaises(ValueError):co._signal(self.c,10,sid,None)

    def test_quality_and_sql_limit_before_invalid_filter(self):
        old,_,_=self.add()
        short,_,_=self.add(quote='Extrait bref.',body='Extrait bref.')
        dynamic,_,_=self.add(quote='Loading...',body='Loading... '+('Texte synthétique. '*10))
        invalid,_,_=self.add()
        self.c.execute("UPDATE commercial_signals SET proof='{}' WHERE id=?",(invalid,))
        self.assertEqual([(x['id'],x['quality']) for x in co.signals(self.c,10)],
                         [(dynamic,'possible_dynamic_shell'),(short,'short_excerpt'),(old,'text_available')])
        self.assertEqual(co.signals(self.c,10,limit=1),[])
        self.assertEqual([x['id'] for x in co.signals(self.c,10,limit=2)],[dynamic])

    def test_legacy_live_callbacks(self):
        sid,page,proof=self.add()
        with patch.object(co,'_proof',return_value=proof) as callback:
            self.assertEqual(co.signals(self.c,10)[0]['proof'],proof)
            self.assertEqual(co._signal(self.c,10,sid,None)[1],proof)
            self.assertEqual(callback.call_count,2)
        with patch.object(ce,'proof',return_value={'fixture':True}) as callback:
            row=self.c.execute('SELECT * FROM commercial_signals WHERE id=?',(sid,)).fetchone()
            self.assertEqual(co._proof(self.c,row),{'fixture':True})
            callback.assert_called_once_with(self.c,row,intel=co.intel)


if __name__=='__main__':
    unittest.main()
