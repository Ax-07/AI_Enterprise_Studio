"""Chromium + serveur réel, base temporaire, réseau fournisseur interdit."""
import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect
import serveur as s
import moteur as m

def smoke():
    with tempfile.TemporaryDirectory() as tmp, patch.object(s,'DB',Path(tmp)/'test.sqlite3'), patch.object(s,'config',return_value={**s.config(),'key':'fake-test-key','brave':'','budget':2000000,'html_sandbox_enabled':False}), patch.object(s,'request',side_effect=AssertionError('Appel fournisseur interdit')) as network, patch.object(m,'fetch_page',side_effect=AssertionError('Réseau interdit')):
        s.init()
        with s.db() as c:
            mid=m.create(s,c,'Étude Shopify', 'cloud')
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?, 'kit.csv',1,'NEXUS','a,b\n1,2\n','test')",(mid,)).lastrowid
            html_aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?, 'prototype_shopify_correction_v2_fr_en.html',1,'NEXUS','<p>fixture</p>','test')",(mid,)).lastrowid
            c.execute("INSERT INTO reports(mission,step,agent,report,sources) VALUES(?,0,'NEXUS',?,'[]')",(mid,json.dumps({'rapport':'Rapprochement Shopify'})))
            c.execute("INSERT INTO ledger(mission,model,reserved,actual,state,agent) VALUES(?,'test',1000,500,'mesuré','NEXUS')",(mid,))
        server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        port=server.server_address[1]
        base=f'http://127.0.0.1:{port}'
        try:
            with patch.object(s,'PORT',port), sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page(accept_downloads=True,viewport={'width':1440,'height':900})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                page.goto(base)
                expect(page.locator('#connection-text')).to_have_text('Serveur V0.4.5.1')
                expect(page.locator('#quick-products')).to_have_text('2')
                expect(page.locator('#pilotage-plan')).to_contain_text('Activer ou examiner le bac à sable')
                page.locator('#pilotage-next').click()
                expect(page.locator('#page-files')).to_be_visible()
                page.locator('#nav-expert > summary').click() if not page.locator('#nav-expert').evaluate('(e)=>e.open') else None
                for section in ('decisions','missions','work','opps','files','goals','agents','finance','memory','tools','home'):
                    page.locator(f'[data-page="{section}"]').click()
                    expect(page.locator('#page-'+section)).to_be_visible()
                page.locator('#home-details > summary').click()
                page.locator('[data-quick="create"]').click()
                expect(page.locator('#mission')).to_have_value(__import__('re').compile('NEXUS'))
                expect(page.locator('#attached-file')).to_be_hidden()
                page.locator('[data-page="files"]').click()
                page.locator('#file-list .file-card').filter(has_text='kit.csv').get_by_role('button',name='Aperçu texte').click()
                expect(page.locator('#file-content')).to_have_text('a,b\n1,2',use_inner_text=True)
                with page.expect_download() as dl:
                    page.locator('#file-list .file-card').filter(has_text='kit.csv').get_by_role('button',name='Télécharger').click()
                assert dl.value.suggested_filename=='kit.csv'
                assert Path(dl.value.path()).read_text()=='a,b\n1,2\n'
                page.locator('#file-list .file-card').filter(has_text='kit.csv').get_by_role('button',name='Améliorer').click()
                expect(page.locator('#attached-label')).to_contain_text('kit.csv')
                expect(page.locator('#mission')).to_have_value(__import__('re').compile('ref:'+str(aid)))
                page.locator('#detach-file').click()
                expect(page.locator('#attached-file')).to_be_hidden()
                page.locator('[data-page="files"]').click()
                page.once('dialog',lambda d:d.accept())
                page.get_by_role('button',name='Test rapide Shopify').click()
                proof=page.locator('#file-list .file-card').filter(has_text='prototype_shopify_correction_v2_fr_en.html')
                expect(proof.locator('summary')).to_contain_text('Indisponible')
                proof.locator('summary').click()
                with page.expect_download() as dl:
                    proof.get_by_role('button',name='Exporter la preuve et le scénario').click()
                evidence=json.loads(Path(dl.value.path()).read_text())
                assert evidence['artifact']==html_aid and evidence['result']['status']=='unavailable'
                page.locator('[data-page="memory"]').click()
                page.locator('#memory-query').fill('Shopify')
                page.locator('#memory-search').click()
                expect(page.locator('#memory-count')).to_contain_text('1 rapport')
                page.locator('[data-page="finance"]').click()
                expect(page.locator('#cost-summary')).to_contain_text('NEXUS')
                with page.expect_download() as dl:
                    page.locator('#export-costs').click()
                assert '0.000500' in Path(dl.value.path()).read_text(encoding='utf-8-sig')
                page.locator('[data-page="missions"]').click()
                page.locator('#demo').click()
                # Wait for the new mission, then its completion. Use locator assertions
                # rather than evaluating JavaScript strings (the app blocks unsafe-eval).
                expect(page.locator('#select')).not_to_have_value(str(mid),timeout=15000)
                expect(page.locator('#mission-state')).to_have_text('terminée',timeout=15000)
                with s.db() as c:
                    assert c.execute("SELECT state FROM missions WHERE mode='demo'").fetchone()[0]=='terminée'
                    assert s.used(c)==500
                page.locator('[data-page="files"]').click()
                page.locator('#file-filter').select_option(str(mid))
                page.locator('#file-list .file-card').filter(has_text='kit.csv').get_by_role('button',name='Améliorer').click()
                expect(page.locator('#attached-file')).to_be_visible()
                page.locator('[data-page="missions"]').click()
                with page.expect_download() as dl:
                    page.locator('#mission-diagnostic').click()
                assert 'estimated_usd' in json.loads(Path(dl.value.path()).read_text())
                # Cloud start checks only the request and persistent reference.
                # Stub the worker: no model calls, no external side effects.
                with patch.object(s,'run',return_value=None):
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/start' and r.request.method=='POST') as response:
                        page.locator('#cloud').click()
                    assert response.value.ok, response.value.text()
                    created=response.value.json()['id']
                    with s.db() as c:
                        assert c.execute('SELECT artifact FROM mission_artifact_refs WHERE mission=?',(created,)).fetchone()[0]==aid
                assert not errors,errors
                network.assert_not_called()
                browser.close()
        finally:
            server.shutdown();server.server_close();thread.join()
    print('Chromium smoke: navigation, missions, fichiers, mémoire, coûts, simulation et référence Cloud OK')

def smoke_recovery():
    # Same persisted evidence chain as the actual case, with a synthetic artifact.
    from test_audit_recovery import AuditRecovery
    fixture=AuditRecovery('test_recover_provenance_and_no_cost')
    fixture.setUp()
    try:
        with patch.object(s,'config',return_value=fixture.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(s,'run',side_effect=AssertionError('No worker on closure')) as worker:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    page=browser.new_page()
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base)
                    expect(page.locator('#pilotage-plan')).to_contain_text('Clôturer l’audit sur preuve')
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/close_audit' and r.request.method=='POST') as response:
                        page.locator('#pilotage-next').click()
                    assert response.value.ok,response.value.text()
                    assert response.value.json()['paid_call'] is False
                    expect(page.locator('#mission-state')).to_have_text('prête')
                    expect(page.locator('#reports')).to_contain_text('SYNTHÈSE TECHNIQUE DU MOTEUR')
                    expect(page.locator('#close-audit')).to_be_hidden()
                    expect(page.locator('#resume')).to_be_enabled()
                    with s.db() as c:
                        assert s.used(c)==500
                        assert c.execute('SELECT turns FROM tasks WHERE id=?',(fixture.tid,)).fetchone()[0]==10
                    assert not errors,errors
                    network.assert_not_called();worker.assert_not_called()
                    browser.close()
            finally:
                server.shutdown();server.server_close();thread.join()
    finally: fixture.doCleanups()
    print('Chromium audit recovery: closure confirmed, provenance visible, no provider call or worker')

def smoke_autopilot():
    from test_autopilot import AutopilotTests
    import autopilot as a
    fixture=AutopilotTests('test_validation_and_one_active')
    fixture.setUp()
    try:
        with patch.object(s,'config',return_value=fixture.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(a,'worker',return_value=None) as worker:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page()
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base)
                    expect(page.locator('#auto-start')).to_be_enabled()
                    expect(page.locator('#auto-budget')).to_have_value('1.00')
                    expect(page.locator('#auto-count')).to_have_value('3')
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/autopilot/start') as res:page.locator('#auto-start').click()
                    assert res.value.ok,res.value.text()
                    expect(page.locator('#auto-state')).to_have_text('actif')
                    expect(page.locator('#auto-stop')).to_be_visible()
                    expect(page.locator('#cloud')).to_be_disabled()
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/autopilot/stop') as res:page.locator('#auto-stop').click()
                    assert res.value.ok,res.value.text()
                    expect(page.locator('#auto-state')).to_have_text('arrêté')
                    expect(page.locator('#auto-resume')).to_be_visible()
                    with s.db() as c:assert s.used(c)==0
                    network.assert_not_called();worker.assert_called_once()
                    assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:fixture.doCleanups()
    print('Chromium Autopilote: autorisation, verrouillage manuel, arrêt et reprise visible; aucun fournisseur')

def smoke_working_memory():
    from test_working_memory import WorkingMemoryTests
    import autopilot as a
    fixture=WorkingMemoryTests('test_recovery_real_worker_mocked_provider')
    fixture.setUp()
    try:
        cid,mid,tid,aid,data=fixture.blocked()
        with patch.object(s,'config',return_value=fixture.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(a,'worker',return_value=None) as worker:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page()
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base)
                    expect(page.locator('#auto-resume')).to_have_text('Reprendre avec mémoire de travail')
                    expect(page.locator('#auto-start')).to_be_hidden()
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/autopilot/resume') as res:page.locator('#auto-resume').click()
                    assert res.value.ok,res.value.text()
                    expect(page.locator('#auto-state')).to_have_text('actif')
                    with s.db() as c:
                        assert a.costs(c,cid)==11000
                        assert c.execute('SELECT turns FROM tasks WHERE id=?',(tid,)).fetchone()[0]==9
                    network.assert_not_called();worker.assert_called_once()
                    assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:fixture.doCleanups()
    print('Chromium mémoire de travail: reprise ciblée, campagne et compteurs conservés')

def smoke_portfolio():
    from test_portfolio import PortfolioTests
    import autopilot as a
    fixture=PortfolioTests('test_migration_costs_lineage_and_no_duplicate')
    fixture.setUp()
    try:
        *_,old,new=fixture.historical()
        with patch.object(s,'config',return_value=fixture.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(a,'worker',return_value=None) as worker:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page()
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base);page.locator('[data-page="portfolio"]').click()
                    expect(page.locator('#portfolio-list')).to_contain_text('Audit de catalogues')
                    expect(page.locator('#portfolio-list')).to_contain_text('original.csv')
                    card=page.locator('#portfolio-list article').filter(has_text='Audit de catalogues')
                    card.get_by_role('button',name='Préparer une validation commerciale').click()
                    expect(page.locator('#auto-project')).to_have_value(str(new))
                    expect(page.locator('#auto-count')).to_have_value('1')
                    expect(page.locator('#auto-production')).not_to_be_checked()
                    expect(page.locator('#auto-connector-cap')).to_have_value('0')
                    expect(page.locator('#auto-start')).to_be_enabled()
                    expect(page.locator('#auto-mode')).to_have_value('commercial')
                    page.locator('#auto-project').select_option('explore')
                    expect(page.locator('#auto-mode')).to_have_value('commercial')
                    expect(page.locator('#auto-start')).to_be_disabled()
                    page.locator('#auto-project').select_option(str(old))
                    expect(page.locator('#auto-mode-summary')).to_contain_text('fichier #')
                    page.locator('#auto-project').select_option(str(new))
                    expect(page.locator('#auto-mode')).to_have_value('commercial')
                    expect(page.locator('#auto-start')).to_be_enabled()
                    dialogs=[]
                    def accept(d):
                        dialogs.append(d.message);d.accept()
                    page.once('dialog',accept)
                    with page.expect_response(lambda r:r.url==base+'/api/autopilot/start') as res:page.locator('#auto-start').click()
                    assert res.value.ok,res.value.text()
                    assert 'Préparation commerciale interne' in dialogs[0]
                    expect(page.locator('#auto-state')).to_have_text('actif')
                    expect(page.locator('#auto-info')).to_contain_text('Préparation commerciale')
                    with s.db() as c:
                        import portfolio as p
                        assert p.scope(c,res.value.json()['campaign'])['project']==new
                        assert p.scope(c,res.value.json()['campaign'])['scope']=='commercial'
                        assert a._campaign(c,res.value.json()['campaign'])['source'] is None
                    network.assert_not_called();worker.assert_called_once()
                    assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:fixture.doCleanups()
    print('Chromium portefeuille: historique, sélection d’une activité, campagne ciblée sans fournisseur')

def smoke_laboratory():
    from test_laboratory import LabIntegration,observations
    import verification as v
    fixture=LabIntegration('test_exact_hash_and_not_json')
    fixture.setUp()
    try:
        pid,aid,other=fixture.product()
        with patch.object(s,'config',return_value={**fixture.cfg,'html_sandbox_enabled':True}),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(v,'browser_results',return_value=observations()) as browser_run:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page()
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base);page.locator('#nav-expert > summary').click();page.locator('[data-page="laboratory"]').click()
                    expect(page.locator('#lab-artifact')).to_have_value(str(aid))
                    expect(page.locator('#lab-size')).to_have_value('300')
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/laboratory/run') as res:page.locator('#lab-run').click()
                    assert res.value.ok,res.value.text()
                    expect(page.locator('#lab-results')).to_contain_text('42 / FP 0 / FN 0')
                    expect(page.locator('#lab-results')).to_contain_text('100 %')
                    with page.expect_download() as dl:page.get_by_role('button',name='Exporter la preuve et les données').click()
                    assert dl.value.suggested_filename.startswith('laboratoire_')
                    network.assert_not_called();browser_run.assert_called_once()
                    assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:fixture.doCleanups()
    print('Chromium laboratoire: sélection du moteur, résultat et export, sans fournisseur')

def smoke_improvement():
    from test_improvement import ImprovementTests
    import autopilot as a,improvement as i
    fixture=ImprovementTests('test_auto_retain_and_restore')
    fixture.setUp()
    try:
        pid,aid=fixture.prepared()
        with patch.object(s,'config',return_value=fixture.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(a,'worker',return_value=None) as worker:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page()
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base);page.locator('[data-page="portfolio"]').click()
                    page.get_by_role('button',name='Préparer une amélioration').click()
                    expect(page.locator('#auto-project')).to_have_value(str(pid))
                    expect(page.locator('#auto-improvement')).to_have_value(i.CSV_PROFILE)
                    expect(page.locator('#auto-count')).to_have_value('1')
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/autopilot/start') as res:page.locator('#auto-start').click()
                    assert res.value.ok,res.value.text()
                    expect(page.locator('#auto-state')).to_have_text('actif')
                    with s.db() as c:
                        cy=i.cycle(c,res.value.json()['campaign'])
                        assert cy['baseline']==aid and cy['state']=='pending'
                    network.assert_not_called();worker.assert_called_once()
                    assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:fixture.doCleanups()
    print('Chromium amélioration: sélection du profil, une mission, référence protégée')

def smoke_owner_console():
    from test_owner_console import OwnerConsoleTests,CANDIDATE
    import autopilot as a,improvement as i
    fixture=OwnerConsoleTests('test_completed_cycle_allows_new_campaign_without_mutation')
    fixture.setUp()
    try:
        pid,aid=fixture.prepared()
        cid=fixture.start(project=pid,improvement=i.CSV_PROFILE,max_missions=1)
        fixture.produce(cid,CANDIDATE)
        with patch.object(s,'config',return_value=fixture.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.object(a,'worker',return_value=None) as worker:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':800})
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base)
                    expect(page.locator('#auto-state')).to_have_text('terminé')
                    expect(page.locator('#auto-state-label')).to_contain_text('nouvelle campagne possible')
                    expect(page.locator('#auto-settings')).to_be_visible()
                    expect(page.locator('#nav-expert')).not_to_have_attribute('open','')
                    with page.expect_download() as dl:page.locator('#auto-diagnostic').click()
                    diag=json.loads(Path(dl.value.path()).read_text())
                    assert diag['readiness']['ready'] and diag['campaign']['improvement']['state']=='retained'
                    expect(page.locator('#auto-audit-export')).to_be_visible()
                    with page.expect_download() as dl:page.locator('#auto-audit-export').click()
                    assert dl.value.suggested_filename==f'dossier_campagne_{cid}.json'
                    dossier=json.loads(Path(dl.value.path()).read_text())
                    assert dossier['schema']=='aes-campaign-audit-v1' and dossier['campaign_id']==cid
                    assert dossier['diagnostic_campagne']['campaign']==diag['campaign']
                    assert {'capabilities','runs'}<=dossier['connecteurs'].keys()
                    assert {'sources','comparisons','ranking'}<=dossier['intelligence_economique'].keys()
                    assert [m['mission']['id'] for m in dossier['missions']]==[m['id'] for m in diag['campaign']['missions']]
                    assert all({'reports','tasks','events','collective_evidence'}<=m.keys() for m in dossier['missions'])
                    assert 'collective_audit' in dossier and 'previous_laboratory' in dossier
                    assert s.SESSION not in json.dumps(dossier)
                    assert page.request.get(base+'/api/campaign_audit?id='+str(cid)).status==404
                    assert page.request.get(base+'/api/campaign_audit?id=0',headers={'X-Session':s.SESSION}).status==400
                    page.locator('[data-page="portfolio"]').click()
                    page.get_by_role('button',name='Préparer une amélioration').click()
                    expect(page.locator('#auto-count')).to_have_value('1')
                    page.locator('[data-page="portfolio"]').click()
                    page.get_by_role('button',name='Préparer la campagne',exact=True).click()
                    expect(page.locator('#auto-improvement')).to_have_value('')
                    expect(page.locator('#auto-count')).to_have_value('3')
                    expect(page.locator('#auto-budget')).to_have_value('0.50')
                    expect(page.locator('#auto-start')).to_be_enabled()
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/autopilot/start') as res:page.locator('#auto-start').click()
                    assert res.value.ok,res.value.text()
                    expect(page.locator('#auto-state')).to_have_text('actif')
                    expect(page.locator('#auto-readiness')).to_contain_text('en cours')
                    expect(page.locator('#auto-settings')).to_be_hidden()
                    expect(page.locator('#auto-audit-export')).to_be_hidden()
                    assert page.request.get(base+'/api/campaign_audit?id='+str(res.value.json()['campaign']),headers={'X-Session':s.SESSION}).status==400
                    with s.db() as c:
                        cid2=res.value.json()['campaign']
                        assert i.cycle(c,cid2) is None and a._campaign(c,cid2)['max_missions']==3
                        assert a._campaign(c,cid)['state']=='terminé'
                    network.assert_not_called();worker.assert_called_once()
                    assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:fixture.doCleanups()
    print('Chromium console propriétaire: campagne retenue clôturée, diagnostic exporté, paramètres réinitialisés, nouvelle campagne')

def smoke_connectors():
    import connectors as x,autopilot as a
    from test_connectors import ConnectorTests
    fixture=ConnectorTests('test_default_deny_no_secret_and_migration')
    fixture.setUp()
    try:
        with patch.object(s,'config',return_value=fixture.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network,patch.dict(x.ADAPTERS,{x.PUBLIC:lambda name:{'repository':name,'stars':12}}),patch.object(a,'worker',return_value=None) as worker:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page(accept_downloads=True)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base);page.locator('#nav-expert > summary').click();page.locator('[data-page="tools"]').click()
                    expect(page.locator('#connector-list')).to_contain_text('Préparé — indisponible')
                    card=page.locator('#connector-list article').filter(has_text='GitHub')
                    expect(card.get_by_role('button',name='Tester la connexion publique')).to_be_disabled()
                    card.locator('summary').click()
                    card.get_by_label('Activer ce connecteur').check()
                    card.get_by_label('ORION',exact=True).check()
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/connectors/policy') as res:
                        card.get_by_role('button',name='Enregistrer les autorisations').click()
                    assert res.value.ok,res.value.text()
                    expect(card.get_by_role('button',name='Tester la connexion publique')).to_be_enabled()
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/connectors/test') as res:
                        card.get_by_role('button',name='Tester la connexion publique').click()
                    assert res.value.json()['status']=='received'
                    expect(page.locator('#connector-runs')).to_contain_text('received')
                    with page.expect_download() as dl:page.locator('#connector-export').click()
                    j=json.loads(Path(dl.value.path()).read_text());assert j['total']['calls']==1
                    page.locator('[data-page="home"]').click()
                    page.locator('#auto-project').select_option('explore')
                    page.locator('#auto-advanced > summary').click()
                    page.locator('#auto-connector-cap').fill('2')
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/autopilot/start') as res:page.locator('#auto-start').click()
                    assert res.value.ok,res.value.text()
                    expect(page.locator('#auto-info')).to_contain_text('Connecteurs : 0/2')
                    network.assert_not_called();worker.assert_called_once()
                    assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:fixture.doCleanups()
    print('Chromium connecteurs: activation, permissions, test public simulé, export et autorisation de campagne')

def smoke_n8n():
    import os,n8n_bridge as n
    from test_n8n import N8nTests,TOKEN
    fixture=N8nTests('test_contracts_reject_arbitrary_payloads')
    fixture.setUp()
    try:
        with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}),patch.object(s,'config',return_value=fixture.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')),patch.object(n,'call',side_effect=fixture.result) as call:
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page(accept_downloads=True)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base);page.locator('#nav-expert > summary').click();page.locator('[data-page="tools"]').click()
                    card=page.locator('#connector-list article').filter(has_text='Statistiques numériques')
                    with page.expect_download() as dl:card.get_by_role('button',name='Télécharger le workflow JSON').click()
                    w=json.loads(Path(dl.value.path()).read_text());assert w['nodes'][0]['parameters']['authentication']=='headerAuth'
                    card.locator('summary').click()
                    card.get_by_label('Activer ce connecteur').check();card.get_by_label('MIDAS',exact=True).check()
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/connectors/policy') as res:card.get_by_role('button',name='Enregistrer les autorisations').click()
                    assert res.value.ok,res.value.text()
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/connectors/test') as res:card.get_by_role('button',name='Tester le workflow local').click()
                    assert res.value.json()['status']=='received'
                    expect(card).to_contain_text('n8n #123')
                    expect(card).to_contain_text('"sum": 14')
                    with page.expect_download() as dl:page.locator('#connector-export').click()
                    raw=Path(dl.value.path()).read_text();assert TOKEN not in raw
                    assert json.loads(raw)['runs'][0]['execution_id']=='123'
                    call.assert_called_once();assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:fixture.doCleanups()
    print('Chromium n8n: template download, scoped authorization, verified result and secret-free export (mock transport)')

def smoke_intelligence():
    import os,n8n_bridge as n,intelligence as i,connectors as x,autopilot as a
    from test_intelligence import IntelligenceTests,TOKEN,fixture as wb_fixture
    case=IntelligenceTests('test_request_and_parse');case.setUp()
    try:
        with patch.dict(os.environ,{'AES_N8N_TOKEN':TOKEN}),patch.object(s,'config',return_value=case.cfg),patch.object(s,'request',side_effect=AssertionError('Provider forbidden')),patch.dict(x.ADAPTERS,{i.CAP:lambda value:wb_fixture(value)}),patch.object(a,'worker',return_value=None) as worker:
            case.policy(i.CAP);case.policy(n.COMPARE)
            x.invoke(s,i.CAP,'{"countries":["FRA","GBR"],"year":2023}')
            server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                with patch.object(s,'PORT',port),sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page(accept_downloads=True)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page.goto(base);page.locator('[data-page="opps"]').click()
                    expect(page.locator('#intel-sources')).to_contain_text('FRA, GBR')
                    with page.expect_download() as dl:page.locator('#intel-export').click()
                    j=json.loads(Path(dl.value.path()).read_text());assert j['sources'][0]['integrity'] and 'raw_json' in j['sources'][0]
                    page.locator('[data-page="home"]').click();page.locator('#auto-intelligence').click()
                    expect(page.locator('#auto-project')).to_have_value('explore')
                    expect(page.locator('#auto-count')).to_have_value('1')
                    expect(page.locator('#auto-budget')).to_have_value('0.50')
                    expect(page.locator('#auto-connector-cap')).to_have_value('3')
                    expect(page.locator('#auto-start')).to_be_enabled()
                    page.once('dialog',lambda d:d.accept())
                    with page.expect_response(lambda r:r.url==base+'/api/autopilot/start') as res:page.locator('#auto-start').click()
                    assert res.value.ok,res.value.text()
                    with s.db() as c:
                        cy=res.value.json()['campaign'];assert set(x.campaign_status(c,cy)['capabilities'])=={i.CAP,n.COMPARE}
                    worker.assert_called_once();assert not errors,errors
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
    finally:case.doCleanups()
    print('Chromium intelligence: evidence export, dedicated preset and frozen capability selection')

if __name__=='__main__':
    smoke()
    smoke_recovery()
    smoke_autopilot()
    smoke_working_memory()
    smoke_portfolio()
    smoke_laboratory()
    smoke_improvement()
    smoke_owner_console()
    smoke_connectors()
    smoke_n8n()
    smoke_intelligence()
