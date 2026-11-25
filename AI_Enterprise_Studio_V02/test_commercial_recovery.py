import json,unittest
from unittest.mock import patch
import serveur as s,moteur as m,autopilot as a,portfolio as p,commercial as co,research
import test_commercial as tc
from test_autopilot import AutopilotTests
from test_portfolio import PortfolioTests

class CommercialRecoveryTests(unittest.TestCase):
    setUp=AutopilotTests.setUp
    start=AutopilotTests.start
    act=AutopilotTests.act
    reply=AutopilotTests.reply
    historical=PortfolioTests.historical
    prepare=tc.CommercialTests.prepare

    def fixture(self):
        *_,old,new=self.historical()
        cid=self.prepare(new,search_cap=3)
        with s.db() as c:
            mid=m.create(s,c,'Préparation commerciale','cloud')
            c.execute("INSERT INTO campaign_missions(campaign,mission,kind) VALUES(?,?,'commercial')",(cid,mid))
            p.attach(c,mid,new,'campagne ciblée')
            atlas=c.execute("SELECT id FROM tasks WHERE mission=? AND agent='ATLAS'",(mid,)).fetchone()[0]
            oid=m.add_task(c,mid,'ORION','Étudier',parent=atlas)
            hid=m.add_task(c,mid,'HERMES','Préparer une offre',parent=atlas)
            c.execute("UPDATE tasks SET state='terminée',turns=8 WHERE id=?",(oid,))
            c.execute("UPDATE tasks SET turns=2 WHERE id=?",(atlas,))
            for n in range(3):
                c.execute("INSERT INTO searches(mission,query,status,result) VALUES(?,?,'reçue','[]')",(mid,'Recherche '+str(n)))
            ids=[]
            for n,txt in enumerate(('Eurostat Prices dashboard \n Loading... \n'+'Menu et navigation. '*30,'European Statistical Monitor - Eurostat')):
                url='https://example.com/'+str(n)
                page=c.execute("INSERT INTO fetched(mission,url,state,content) VALUES(?,?,'reçue',?)",(mid,url,json.dumps({'url':url,'texte':txt,'date':'2026-11-25'}))).lastrowid
                quote=txt.split('\n')[0].strip()
                sig=co.execute(c,{'mission':mid,'agent':'ORION'},'commercial_signal',str(page),json.dumps({'kind':'alternative','quote':quote,'interpretation':'Alternative documentaire, pas demande.'}),'')
                ids.append(sig['signal'])
        return cid,mid,hid,new,ids

    def block(self,cid,mid,hid,ids):
        plan={**tc.PLAN,'signal_ids':ids}
        actions=[self.act('commercial_offer',text=json.dumps({**plan,'risks':'x'*n})) for n in (801,802,803)]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            self.assertIn('800 caractères chacune',body['input'])
            if len(actions)==1:
                self.assertIn('CORRECTION COMMERCIALE CIBLÉE',body['input'])
                self.assertEqual(set(body['text']['format']['schema']['properties']['action']['enum']),{'commercial_offer','finish'})
            return self.reply(actions.pop(0))
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake),patch.object(m,'fetch_page',side_effect=AssertionError('No page fetch')):
            a.worker(s,cid)
        self.assertEqual(actions,[])
        with s.db() as c:
            state=a.status(c,self.cfg)
            self.assertEqual(state['state'],'bloqué',state)
            self.assertEqual(state['recovery_kind'],'commercial')
            self.assertEqual(c.execute('SELECT turns FROM tasks WHERE id=?',(hid,)).fetchone()[0],3)
            errors=list(c.execute("SELECT id,result FROM events WHERE task=? AND ok=0 ORDER BY id",(hid,)))
            self.assertEqual(len(errors),3)
            self.assertIn('803 caractères reçus',errors[-1]['result'])
            return errors[-1]['id']

    def test_resume_legacy_loss_and_complete_without_research(self):
        cid,mid,hid,pid,ids=self.fixture()
        last=self.block(cid,mid,hid,ids)
        with s.db() as c:
            # Reproduce the old transaction rollback in a disposable test database only.
            c.execute('DELETE FROM events WHERE id=?',(last,))
            for row in c.execute('SELECT id FROM events WHERE task=?',(hid,)).fetchall():
                c.execute('UPDATE events SET result=? WHERE id=?',(json.dumps({'erreur':'Texte invalide : risks'}),row['id']))
            before=a.status(c,self.cfg)
            self.assertEqual(before['recovery_kind'],'commercial')
            self.assertEqual(before['searches'],3)
            self.assertEqual(len(co.context(c,mid)['signals']),2)
            self.assertEqual({x['quality'] for x in co.context(c,mid)['signals']},{'short_excerpt','possible_dynamic_shell'})
            a.resume(c,cid,self.cfg)
            self.assertEqual(a.costs(c,cid),before['spent'])
            self.assertEqual(a.searches(c,cid),3)
            self.assertEqual(c.execute('SELECT turns FROM tasks WHERE id=?',(hid,)).fetchone()[0],3)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM commercial_recoveries WHERE task=?',(hid,)).fetchone()[0],1)
        actions=[self.act('commercial_offer',text=json.dumps({**tc.PLAN,'signal_ids':ids})),self.act('finish',text='Offre interne'),
            self.act('delegate','MIDAS','Évaluer','Hypothèses'),self.act('commercial_economics','1',json.dumps(tc.ECO)),self.act('finish',text='Évaluation'),
            self.act('delegate','SENTINEL','Auditer','Limites'),self.act('commercial_review','1',json.dumps({'verdict':'study_further','gaps':'Sources insuffisantes, aucune demande prouvée.'})),
            self.act('finish',text='Revue interne'),self.act('finish',text='Aucun lancement')]
        def fake(url,headers,body=None):
            self.assertIn('api.openai.com',url)
            if len(actions)==9:
                self.assertIn('CORRECTION COMMERCIALE CIBLÉE',body['input'])
                self.assertIn('Texte invalide : risks',body['input'])
                self.assertEqual(set(body['text']['format']['schema']['properties']['action']['enum']),{'commercial_offer','finish'})
            return self.reply(actions.pop(0))
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',side_effect=fake),patch.object(m,'fetch_page',side_effect=AssertionError('No repeat research')):
            a.worker(s,cid)
        self.assertEqual(actions,[])
        with s.db() as c:
            status=a.status(c,self.cfg)
            self.assertEqual(status['state'],'terminé',status)
            self.assertEqual(status['searches'],3)
            self.assertEqual(len(status['missions']),1)
            self.assertEqual(status['missions'][0]['id'],mid)
            self.assertGreater(status['spent'],before['spent'])
            self.assertEqual(len(status['commercial_recoveries']),1)
            dossier=s.campaign_audit(c,self.cfg,cid)
            commercial=dossier['commercial'][0]
            self.assertEqual({x['id'] for x in commercial['signals']},set(ids))
            self.assertEqual(commercial['offer']['state'],'preparation_incomplete')
            self.assertIn('indices_documentaires_insuffisants',commercial['offer']['gaps'])
            self.assertFalse(commercial['offer']['external_authorized'])
            self.assertEqual(commercial['offer']['sales'],0)
            self.assertIsNotNone(commercial['offer']['economics'])
            self.assertIsNotNone(commercial['offer']['review'])

    def test_new_failure_journal_and_recovery_once(self):
        cid,mid,hid,pid,ids=self.fixture()
        self.block(cid,mid,hid,ids)
        with s.db() as c:
            self.assertIsNone(co.recovery_task(c,mid,{**self.cfg,'turn_limit':4}))
            self.assertIsNone(co.recovery_task(c,mid,{**self.cfg,'call_limit':3}))
            a.resume(c,cid,self.cfg)
        bad=self.act('commercial_offer',text=json.dumps({**tc.PLAN,'risks':['risque']}))
        with patch.object(s,'config',return_value=self.cfg),patch.object(s,'request',return_value=self.reply(bad)) as req:
            a.worker(s,cid)
            req.assert_called_once()
        with s.db() as c:
            state=a.status(c,self.cfg)
            self.assertEqual(state['state'],'bloqué')
            self.assertFalse(state['recoverable'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM events WHERE task=? AND ok=0',(hid,)).fetchone()[0],4)
            err=c.execute('SELECT result FROM events WHERE task=? ORDER BY id DESC LIMIT 1',(hid,)).fetchone()[0]
            self.assertIn('type reçu list',err)
            with self.assertRaises(ValueError):a.resume(c,cid,self.cfg)

    def test_quality_labels_and_contract(self):
        self.assertEqual(research.excerpt_quality('Titre seul'),'short_excerpt')
        self.assertEqual(research.excerpt_quality('Loading... '+'menu '*100),'possible_dynamic_shell')
        self.assertEqual(research.excerpt_quality('Document public. '*100),'text_available')
        with self.assertRaisesRegex(ValueError,'801 caractères reçus'):co._text({'risks':'x'*801},'risks',5,800)
        with self.assertRaisesRegex(ValueError,'type reçu list'):co._text({'risks':[]},'risks',5,800)
