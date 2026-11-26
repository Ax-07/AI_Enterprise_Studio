import os
import re
"""Real local HTTP + Chromium: the design is still a detached simulation."""
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect
import serveur as s

def smoke():
    srv=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
    thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    port=srv.server_address[1];base=f'http://127.0.0.1:{port}'
    try:
        with patch.object(s,'PORT',port),patch.object(s,'status',side_effect=AssertionError('No status in D01')),sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1600,'height':1000},reduced_motion='reduce')
            errors=[];unexpected=[];responses=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
            page.on('response',lambda r:responses.append((r.status,r.url)))
            def guard(route):
                if route.request.url.startswith(base+'/campus'):
                    route.continue_()
                elif route.request.url==base+'/favicon.ico':
                    route.fulfill(status=204,body='')
                else:
                    unexpected.append(route.request.url);route.abort()
            page.route('**/*',guard)
            page.goto(base+'/campus/')
            expect(page.locator('.demo')).to_contain_text('D02')
            expect(page.locator('#buildings [data-id]')).to_have_count(7)
            expect(page.locator('#hdDecor image')).to_have_count(1)
            topology=page.evaluate("AESCampusRegistry.snapshot()")
            assert topology['phase']=='D02' and not topology['operational']
            # Static connected layout must stay aligned with the original D02 registry.
            page.add_script_tag(url=base+'/campus/live-layout.js')
            connected=page.evaluate("AESLiveLayout")
            page.add_script_tag(url=base+'/campus/live-teams.js')
            teams=page.evaluate("AESLiveTeams")
            slots=[s for b in teams for s in b['slots']]
            originals=[s for b in topology['buildings'] for s in b['slots']]
            assert [(s['id'],s['kind'],s['name']) for s in slots]==[(s['id'],s['kind'],s['name']) for s in originals]
            assigned=[s['agent'] for s in slots if s['agent']]
            assert len(slots)==56 and len(set(assigned))==8
            page.add_script_tag(url=base+'/campus/live-modules.js')
            modules=page.evaluate("AESLiveModules")
            known={st['id'] for b in connected for f in b['floors'] for st in f['stations']}
            assert set(modules['stations'])<=known
            assert set(modules['native'])<=known
            assert {tool for tools in modules['native'].values() for tool in tools}=={'incidents','quality','infrastructure','economy','business','marketing'}
            assert {p for ps in modules['stations'].values() for p in ps}==set(modules['pages'])
            assert len(modules['pages'])==14
            assert 'VIDEO183:station:1' not in modules['stations']
            expected={f['id']:f for b in topology['buildings'] for f in b['floors']}
            actual={f['id']:f for b in connected for f in b['floors']}
            assert expected.keys()==actual.keys()
            for b in connected:
                original=next(x for x in topology['buildings'] if x['id']==b['id'])
                assert [f['id'] for f in b['floors']]==[f['id'] for f in original['floors']]
                for f in b['floors']:
                    orig=expected[f['id']]
                    assert f['name']==orig['name'],(f['id'],f['name'],orig['name'])
                    assert f['description']==orig['description'],f['id']
                    assert [(x['id'],x['name'],x['destination']) for x in f['stations']]==[(x['id'],x['name'],x['demoDestination']) for x in orig['stations']],f['id']
            assert len(topology['buildings'])==7
            floors=[f for b in topology['buildings'] for f in b['floors']]
            assert len(floors)==len({f['id'] for f in floors})==37
            assert all(f['stations'] and not f['operational'] for f in floors)
            stations=[st for f in floors for st in f['stations']]
            assert len(stations)==len({st['id'] for st in stations})
            assert all(not st['operational'] for st in stations)
            assert sum(len(b['slots']) for b in topology['buildings'])==56
            assert page.evaluate("AESCampusRegistry.service('UNKNOWN') === null")
            assert page.evaluate("AESCampusRegistry.station('OWNER', 999) === null")
            assert page.evaluate("Object.isFrozen(AESCampusRegistry.snapshot().buildings[0].floors)")
            assert page.evaluate("AESCampusRegistry.service('OWNER').buildingId === 'ATLAS'")
            assert page.evaluate("AESCampusRegistry.service('VIDEO183').integration === 'future_or_unmapped'")
            campus=page.locator('#buildings [data-id="HERMES"]').first
            campus.focus()
            campus.press('Enter')
            expect(page.locator('#elevator181')).to_be_visible()
            expect(page.locator('#elevator181 [data-floor181]')).to_have_count(8)
            page.evaluate("goFloor181('LAB')")
            expect(page.locator('#elevator181')).to_be_visible()
            page.locator('#roster [data-agent="NEXUS"]').click()
            expect(page.locator('#elevator181 [data-floor181]')).to_have_count(5)
            page.locator('#elevator181 [data-floor181="LAB"]').click()
            expect(page.locator('#roomScene')).to_be_visible()
            expect(page.locator('#roomScene svg')).to_have_count(1)
            page.locator('#backCampus').click()
            expect(page.locator('#campusSvg')).to_be_visible()
            # Real design controls: add/remove a simulated reserve, preserving OWNER identity.
            page.locator('#build11').click(force=True) if page.locator('#build11').is_visible() else page.evaluate("openModal('Plan', plan221())")
            page.locator('#building221').select_option('ATLAS')
            page.locator('[data-add221]').click()
            assert page.evaluate("AESCampusRegistry.snapshot().buildings.find(b=>b.id==='ATLAS').floors.filter(f=>f.kind==='reserve').length === 1")
            assert page.evaluate("AESCampusRegistry.service('OWNER').level === 9")
            assert page.evaluate("AESCampusRegistry.service('RESERVE221_ATLAS_1') === null")
            page.locator('[data-remove221]').click()
            assert page.evaluate("AESCampusRegistry.service('OWNER').level === 8")
            page.wait_for_timeout(500)
            assert not errors,errors
            assert not unexpected,unexpected
            assert any(status==200 and '/campus/assets/' in url for status,url in responses),responses
            assert all(status<400 for status,url in responses),responses
            browser.close()
    finally:srv.shutdown();srv.server_close();thread.join()
    print('Campus D02 smoke passed')

def smoke_live():
    import tempfile
    from pathlib import Path
    from test_campus_live import fixture, fixture_marketing
    # Optional visual evidence: fixture DB only, capture the scene (not private details).
    target=os.getenv('AES_CAMPUS_SCREENSHOTS')
    def capture(page,name):
        if not target:return
        directory=Path(target);directory.mkdir(parents=True,exist_ok=True)
        page.locator('.scene-panel').screenshot(path=str(directory/(name+'.png')),animations='disabled',timeout=10000)
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'test.db';fixture(path);fixture_marketing(path)
        srv=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        port=srv.server_address[1];base=f'http://127.0.0.1:{port}'
        try:
            with patch.object(s,'PORT',port),patch.object(s,'DB',path),patch.object(s,'config',return_value={'budget':4000000}),sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page()
                errors=[];writes=[];external=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                def guard(route):
                    req=route.request
                    if not req.url.startswith(base+'/'):
                        external.append(req.url);route.abort()
                    elif req.method!='GET':
                        writes.append(req.url);route.abort()
                    else:route.continue_()
                page.route('**/*',guard)
                page.goto(base+'/campus/live/')
                expect(page.locator('#status')).to_contain_text('Connecté')
                expect(page.locator('#buildings button')).to_have_count(7)
                expect(page.locator('#alert-list')).to_contain_text('1 demande(s) en attente')
                expect(page.locator('#campus-decor')).to_have_attribute('href','/campus/assets/campus_1_1.webp')
                capture(page,'01-campus-jour')
                page.locator('#day-toggle').click()
                expect(page.locator('#campus-decor')).to_have_attribute('href','/campus/assets/campus_1_0.webp')
                capture(page,'02-campus-nuit')
                page.locator('#day-toggle').click()
                page.locator('#focus-toggle').click()
                expect(page.locator('#scene-layout')).to_have_class('layout scene-expanded')
                page.locator('#focus-toggle').click()
                page.locator('#motion-toggle').click()
                expect(page.locator('#motion-toggle')).to_have_attribute('aria-pressed','false')
                page.locator('#motion-toggle').click()
                expect(page.locator('#campus-map [data-building]')).to_have_count(7)
                expect(page.locator('#campus-map [data-building="CORE"]')).to_have_attribute('data-activity','running_recorded')
                expect(page.locator('#campus-map [data-building="NEXUS"]')).to_have_attribute('data-activity','quiet')
                expect(page.locator('#live-flows [data-delegation]')).to_have_count(0)
                # New persisted relation is rendered once, not a decorative random robot.
                import sqlite3
                with sqlite3.connect(path) as db:
                    db.execute("INSERT INTO tasks(id,mission,agent,state,created,goal,parent) VALUES(3,1,'ORION','prête','2026-01-01','fixture',1)")
                    db.execute('UPDATE missions SET step=3 WHERE id=1')
                page.locator('#refresh').click()
                expect(page.locator('#campus-map [data-building="ORION"]')).to_have_attribute('data-activity','selected')
                expect(page.locator('#collaborations')).to_contain_text('MNEMOS → ORION')
                expect(page.locator('#live-flows [data-delegation="3"]')).to_have_count(1)
                page.locator('#refresh').click()
                expect(page.locator('#live-flows [data-delegation]')).to_have_count(0)
                page.locator('#campus-map [data-building="CORE"]').focus()
                page.keyboard.press('Enter')
                expect(page.locator('#lift-view [data-floor]')).to_have_count(5)
                expect(page.locator('#lift-view [data-floor="CORE"] .floor-activity')).to_contain_text('2 agent(s) configuré(s)')
                page.locator('#lift-view [data-floor="CORE"]').hover()
                expect(page.locator('#lift-view [data-level-id="CORE"]')).to_have_class(re.compile('focus181'))
                capture(page,'03-ascenseur-core')
                page.locator('#lift-view [data-floor="CORE"]').click()
                expect(page.locator('#room-view [data-station]')).to_have_count(5)
                expect(page.locator('#room-view img')).to_be_visible()
                page.wait_for_function("document.querySelector('#room-view img')?.naturalWidth > 0")
                capture(page,'04-bureau-core')
                expect(page.locator('#team-slots [data-slot]')).to_have_count(8)
                expect(page.locator('#team-slots [data-configured="true"]')).to_have_count(2)
                page.locator('#team-slots [data-slot="CORE:1"]').click()
                expect(page.locator('#team-detail')).to_contain_text('MNEMOS')
                capture(page,'05-equipe-core')
                page.locator('#refresh').click()
                expect(page.locator('#team-slots [data-slot="CORE:1"]')).to_have_attribute('aria-pressed','true')
                expect(page.locator('#agents')).to_contain_text('MNEMOS')
                expect(page.locator('#agents')).to_contain_text('PROMETHEUS')
                expect(page.locator('#missions')).to_contain_text('SIMULATION enregistrée')
                expect(page.locator('#artifacts')).to_contain_text('SIMULATION enregistrée')
                expect(page.locator('#room-view [data-room-station]')).to_have_count(5)
                page.locator('#room-view [data-room-station="CORE:station:2"]').focus()
                page.keyboard.press('Enter')
                expect(page.locator('#room-view [data-station="CORE:station:2"]')).to_have_attribute('aria-pressed','true')
                expect(page.locator('#station-content')).to_contain_text('MNEMOS')
                expect(page.locator('#station-modules [data-module="agents"]')).to_have_attribute('href', '/?page=agents&campusBuilding=CORE&campusFloor=CORE&campusStation=CORE%3Astation%3A2')
                page.locator('#lift-back').click()
                page.locator('#lift-view [data-floor="CORE"]').click()
                page.locator('#room-view [data-station="CORE:station:0"]').click()
                page.locator('[data-native="memory"]').click()
                page.locator('#native-tool input').fill('MNEMOS')
                page.locator('#native-tool button',has_text='Rechercher').click()
                expect(page.locator('#native-tool .native-results')).to_contain_text('MNEMOS')
                page.locator('#native-tool button',has_text='Lire le rapport').click()
                expect(page.locator('#native-tool pre')).to_have_text('Recherche de marché test')
                page.locator('#buildings button[data-id="NEXUS"]').click()
                expect(page.locator('#native-tool')).to_be_hidden()
                page.locator('#lift-view [data-floor="NEXUS"]').click()
                page.locator('#room-view [data-station="NEXUS:station:3"]').click()
                page.locator('[data-native="files"]').click()
                expect(page.locator('#native-tool .native-results')).to_contain_text('Exemple')
                page.locator('#native-tool button',has_text='Consulter / télécharger').click()
                expect(page.locator('#native-tool pre')).to_have_text('secret-test')
                with page.expect_download() as dl:
                    page.locator('#native-tool button',has_text='Télécharger le fichier original').click()
                assert Path(dl.value.path()).read_text()=='secret-test'
                page.locator('#buildings button[data-id="HERMES"]').click()
                expect(page.locator('#lift-view [data-floor]')).to_have_count(8)
                page.locator('#lift-view [data-floor="VIDEO183"]').click()
                expect(page.locator('#room-view [data-station]')).to_have_count(5)
                page.locator('#room-view [data-station="VIDEO183:station:0"]').click()
                expect(page.locator('[data-native="marketing"]')).to_have_count(1)
                page.locator('[data-native="marketing"]').click()
                expect(page.locator('#native-tool [role=status]')).to_contain_text('résultat')
                expect(page.locator('#native-tool')).to_contain_text('aucun média généré')
                page.locator('#room-view [data-station="VIDEO183:station:1"]').click()
                expect(page.locator('#station-content')).to_contain_text('non raccordée')
                expect(page.locator('#station-modules a')).to_have_count(0)
                page.route('**/campus/live-data',lambda r:r.fulfill(status=503,body='{}',content_type='application/json'))
                page.locator('#refresh').click()
                expect(page.locator('#status')).to_contain_text('Données indisponibles')
                expect(page.locator('#metrics .metric')).to_have_count(0)
                expect(page.locator('#campus-map [data-building="CORE"]')).to_have_attribute('data-activity','unknown')
                expect(page.locator('#collaborations')).to_contain_text('Données indisponibles')
                expect(page.locator('#alert-list')).to_contain_text('Données indisponibles')
                expect(page.locator('#station-content')).to_contain_text('Données indisponibles')
                assert not errors and not writes and not external,(errors,writes,external)
                browser.close()
        finally:srv.shutdown();srv.server_close();thread.join()
    print('Campus D03 read-only smoke passed')

def smoke_commands(route='live'):
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d, patch.object(s,'DB',Path(d)/'db.sqlite3'), patch.object(s,'request',side_effect=AssertionError('Provider forbidden')) as network, patch.object(s,'run'):
        s.init()
        srv=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        port=srv.server_address[1];base=f'http://127.0.0.1:{port}'
        try:
            with patch.object(s,'PORT',port),patch.object(s,'config',return_value={**s.config(),'key':'fake-test-key','budget':4000000}),sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page()
                errors=[];posts=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
                page.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') else r.abort())
                page.goto(base+'/campus/'+route+'/?building=ATLAS&floor=ATLAS&station=ATLAS%3Astation%3A1')
                expect(page.locator('#status')).to_contain_text('Connecté')
                if route=='original':
                    expect(page.locator('#design-mode')).to_contain_text('OPÉRATIONNEL')
                    expect(page.locator('[data-commands="missions"]')).to_be_visible()
                    expect(page.locator('meta[name="campus-owner-session"]')).to_have_attribute('content','')
                    page.locator('#tab-functions').click()
                    page.locator('[data-function-tool="missions"]').click()
                    expect(page.locator('#function-detail #station-detail')).to_be_visible()
                page.locator('[data-commands="missions"]').click()
                expect(page.locator('#campus-commands [role=status]')).to_contain_text('États locaux relus')
                expect(page.locator('[data-command="mission_demo"]')).to_be_enabled()
                page.locator('#campus-commands textarea').fill('Simulation navigateur')
                page.once('dialog',lambda d:d.dismiss())
                page.locator('[data-command="mission_demo"]').click()
                assert not posts,posts
                page.once('dialog',lambda d:d.accept())
                page.locator('[data-command="mission_demo"]').click()
                expect(page.locator('#campus-commands [role=status]')).to_contain_text('Commande acceptée')
                page.get_by_role('button',name='Actualiser les états').click()
                expect(page.locator('[data-command="mission_stop"]')).to_have_count(1)
                page.once('dialog',lambda d:d.accept())
                page.locator('[data-command="mission_stop"]').click()
                expect(page.locator('#campus-commands [role=status]')).to_contain_text('Commande acceptée')
                with s.db() as db:
                    m=db.execute("SELECT mode,state FROM missions WHERE title='Simulation navigateur'").fetchone()
                    assert tuple(m)==('demo','arrêtée')
                    assert s.used(db)==0
                assert posts==[base+'/campus/command']*2,posts
                expect(page.locator('[data-command="mission_cloud"]')).to_have_count(0)
                page.goto(base+'/campus/'+route+'/?building=ATLAS&floor=OWNER&station=OWNER%3Astation%3A2')
                expect(page.locator('#status')).to_contain_text('Connecté')
                page.locator('[data-commands="missions"]').click()
                expect(page.locator('[data-command="mission_cloud"]')).to_be_enabled()
                page.locator('#campus-commands textarea').fill('Cloud test navigateur')
                page.once('dialog',lambda d:d.dismiss())
                page.locator('[data-command="mission_cloud"]').click()
                assert len(posts)==2,posts
                page.once('dialog',lambda d:d.accept())
                page.locator('[data-command="mission_cloud"]').click()
                expect(page.locator('#campus-commands [role=status]')).to_contain_text('Commande acceptée')
                with s.db() as db:
                    mid=db.execute("SELECT id FROM missions WHERE title='Cloud test navigateur' AND mode='cloud'").fetchone()[0]
                    db.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
                    rid=db.execute("INSERT INTO requests(mission,body) VALUES(?,'{}')",(mid,)).lastrowid
                page.locator('#room-view [data-station="OWNER:station:4"]').click()
                page.locator('[data-commands="decisions"]').click()
                expect(page.locator('#campus-commands [role=status]')).to_contain_text('États locaux relus')
                page.once('dialog',lambda d:d.accept())
                page.locator('#campus-commands').get_by_role('button',name='Refuser',exact=True).click()
                expect(page.locator('#campus-commands [role=status]')).to_contain_text('Commande acceptée')
                with s.db() as db:
                    assert db.execute('SELECT state FROM requests WHERE id=?',(rid,)).fetchone()[0]=='refusée'
                    assert s.used(db)==0
                assert posts==[base+'/campus/command']*2+[base+'/campus/owner-command']*2,posts
                if route=='original':
                    page.locator('#campus-back').click()
                    page.locator('.top [data-view="campaigns"]').click()
                    expect(page.locator('#top-tool-host #station-modules a').first).to_have_attribute('href','/?page=home')
                    page.locator('#back-top-tool').click()
                    page.locator('#buildings button[data-id="ATLAS"]').click()
                    page.locator('#lift-view [data-floor="ATLAS"]').click()
                    page.locator('#tab-functions').click()
                    page.locator('[data-function-tool="missions"]').click()
                    href=page.locator('#station-modules a[data-module="missions"]').get_attribute('href')
                    assert 'campusView=original' in href
                    page.goto(base+href)
                    expect(page.locator('#campus-return')).to_have_attribute('href',re.compile(r'^/campus/original/'))
                assert not errors,errors
                network.assert_not_called()
                browser.close()
        finally:srv.shutdown();srv.server_close();thread.join()
    print('Campus command smoke passed: '+route)

def smoke_preview():
    import tempfile
    from pathlib import Path
    from preview_campus import PreviewHandler
    with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'):
        s.init()
        before=s.DB.read_bytes()
        srv=s.ThreadingHTTPServer(('127.0.0.1',0),PreviewHandler)
        th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
        port=srv.server_address[1];base=f'http://127.0.0.1:{port}'
        try:
            with patch.object(s,'PORT',port),patch.object(s,'request',side_effect=AssertionError('No provider')) as network,sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page()
                errors=[];posts=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
                page.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') else r.abort())
                page.goto(base+'/campus/live/')
                expect(page.locator('#status')).to_contain_text('Connecté')
                expect(page.locator('#preview-notice')).to_be_visible()
                expect(page.locator('#legacy-entry')).to_be_hidden()
                page.locator('#campus-map [data-building="ATLAS"]').focus()
                page.keyboard.press('Enter')
                page.locator('#lift-view [data-floor="OWNER"]').click()
                page.locator('#room-view [data-station="OWNER:station:2"]').click()
                expect(page.locator('[data-commands]')).to_have_count(0)
                expect(page.locator('[data-module]')).to_have_count(0)
                page.locator('[data-native="owner"]').click()
                expect(page.locator('#native-tool .native-results')).to_contain_text('Solde local estimé')
                expect(page.locator('#native-tool .native-results')).to_contain_text('Points de vigilance')
                page.locator('#native-tool button',has_text='Consulter les décisions réservées').click()
                expect(page.locator('#native-tool h3').first).to_contain_text('Décisions réservées')
                expect(page.locator('#native-tool [role=status]')).to_contain_text('résultat')
                page.locator('#native-tool button',has_text='Retour au tableau de direction').click()
                expect(page.locator('#native-tool .native-results')).to_contain_text('Missions à examiner')
                assert not posts and not errors,(posts,errors)
                network.assert_not_called()
                browser.close()
                assert s.DB.read_bytes()==before
        finally:srv.shutdown();srv.server_close();th.join()
    print('D08.2 read-only preview smoke passed')

def smoke_original():
    import tempfile
    from pathlib import Path
    from preview_campus import PreviewHandler
    with tempfile.TemporaryDirectory() as d,patch.object(s,'DB',Path(d)/'db.sqlite3'):
        s.init()
        before=s.DB.read_bytes()
        srv=s.ThreadingHTTPServer(('127.0.0.1',0),PreviewHandler)
        th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
        port=srv.server_address[1];base=f'http://127.0.0.1:{port}'
        try:
            with patch.object(s,'PORT',port),patch.object(s,'request',side_effect=AssertionError('No provider')) as network,sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1600,'height':1000})
                errors=[];posts=[];requests=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:(requests.append(r.url),posts.append(r.url) if r.method=='POST' else None))
                page.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') else r.abort())
                page.goto(base+'/campus/original/')
                expect(page.locator('#status')).to_contain_text('Connecté')
                expect(page.locator('.main > aside')).to_have_count(2)
                expect(page.locator('#metrics .metric')).to_have_count(5)
                expect(page.locator('#economic-metrics .metric')).to_have_count(5)
                for k in ('revenue','profit','api-today'):
                    expect(page.locator('[data-kpi="'+k+'"] strong')).to_have_text('—')
                expect(page.locator('[data-kpi="workforce"] strong')).to_have_text('8')
                expect(page.locator('[data-kpi="campaigns"] strong')).to_have_text('0 / 0')
                expect(page.locator('[data-kpi="budget"] strong')).not_to_have_text('—')
                expect(page.locator('[data-kpi="commitment"] [role="meter"]')).to_have_count(1)
                expect(page.locator('#buildings .agent')).to_have_count(7)
                expect(page.locator('script[src="/campus/design.js"]')).to_have_count(0)
                assert page.locator('meta[name="campus-command-session"]').get_attribute('content')==''
                target=os.getenv('AES_CAMPUS_SCREENSHOTS')
                def capture(name):
                    if target:
                        directory=Path(target);directory.mkdir(parents=True,exist_ok=True)
                        page.screenshot(path=str(directory/(name+'.png')),animations='disabled',full_page=True)
                capture('F01-campus-original')
                # Exact original 22.6 label geometry, layer separation and day/night source.
                compare=browser.new_page(viewport={'width':1600,'height':1000})
                compare.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') else r.abort())
                compare.goto(base+'/campus/')
                expect(compare.locator('#labels .domain15')).to_have_count(7)
                for building in ['ATLAS','ORION','NEXUS','MIDAS','HERMES','SENTINEL','CORE']:
                    ref=compare.locator('#labels [data-id="'+building+'"] .label-bg')
                    actual=page.locator('#original-signs [data-id="'+building+'"] .label-bg')
                    for attr in ['x','y','width','height','rx']:
                        assert abs(float(ref.get_attribute(attr))-float(actual.get_attribute(attr)))<.001,(building,attr)
                # Paired real browser evidence: same viewport, same original art, no
                # numerical pixel threshold on legitimate differences in business data.
                if 'day' not in (compare.locator('#campusPanel').get_attribute('class') or '').split():
                    compare.locator('#dayBtn').click()
                expect(compare.locator('#hdDecor image')).to_have_attribute('href','/campus/assets/campus_1_1.webp')
                assert page.locator('#original-skyline path').count()==compare.locator('#skyline path').count()
                assert page.locator('#original-skyline rect').count()==compare.locator('#skyline rect').count()
                expect(page.locator('#original-skyline > g')).to_have_attribute('opacity','0.4')
                for prop in ['background-image','filter']:
                    assert compare.locator('#mapWrap').evaluate('(e,p)=>getComputedStyle(e)[p]',prop)==page.locator('#mapWrap').evaluate('(e,p)=>getComputedStyle(e)[p]',prop),prop
                if target:
                    compare.screenshot(path=str(Path(target)/'F05-reference-jour.png'),animations='disabled',full_page=True)
                capture('F05-connecte-jour')
                compare.locator('#dayBtn').click()
                expect(compare.locator('#hdDecor image')).to_have_attribute('href','/campus/assets/campus_1_0.webp')
                if target:
                    compare.screenshot(path=str(Path(target)/'F05-reference-nuit.png'),animations='disabled',full_page=True)
                page.locator('#day-toggle').click()
                expect(page.locator('#original-skyline > g')).to_have_attribute('opacity','0.8')
                capture('F05-connecte-nuit')
                page.locator('#day-toggle').click()
                # Original tower and interior on the same department as the connected one.
                compare.locator('#roster [data-agent="NEXUS"]').click()
                # Original roster may only select when on campus; use the real building control.
                if not compare.locator('#elevator181').is_visible():
                    compare.locator('#buildings [data-id="NEXUS"]').first.focus()
                    compare.keyboard.press('Enter')
                expect(compare.locator('#elevator181')).to_be_visible()
                if target:
                    compare.screenshot(path=str(Path(target)/'F05-reference-ascenseur.png'),animations='disabled',full_page=True)
                compare.locator('#elevator181 [data-floor181="NEXUS"]').click()
                expect(compare.locator('#roomScene svg.office16')).to_be_visible()
                if target:
                    compare.screenshot(path=str(Path(target)/'F05-reference-bureau.png'),animations='disabled',full_page=True)
                compare.close()
                page.locator('#day-toggle').click()
                expect(page.locator('#campus-decor')).to_have_attribute('href','/campus/assets/campus_1_0.webp')
                capture('F02-campus-nuit')
                page.locator('#day-toggle').click()
                expect(page.locator('#campus-decor')).to_have_attribute('href','/campus/assets/campus_1_1.webp')
                sign=page.locator('#original-signs [data-id="NEXUS"]')
                page.locator('#campus-map [data-building="NEXUS"]').focus()
                expect(sign).to_have_class(re.compile('lit181'))
                capture('F02-campus-survol')
                sign.locator('.label-bg').click()
                expect(page.locator('#lift-view .liftHero181')).to_contain_text('ACCÈS VERTICAL / NEXUS')
                page.locator('#lift-view [data-floor="NEXUS"]').hover()
                expect(page.locator('#lift-view [data-level-id="NEXUS"]')).to_have_class(re.compile('focus181'))
                capture('F02-ascenseur')
                capture('F05-connecte-ascenseur')
                page.locator('#campus-back').click()
                page.locator('#focus-toggle').click()
                expect(page.locator('#campusView')).to_have_class(re.compile('immersive'))
                capture('F02-immersion')
                page.locator('#focus-toggle').click()
                for building,floor,count in [('NEXUS','NEXUS',8),('CORE','CORE',7)]:
                    page.locator('#buildings button[data-id="'+building+'"]').click()
                    page.locator('#lift-view [data-floor="'+floor+'"]').click()
                    expect(page.locator('#original-office svg.office16')).to_be_visible()
                    expect(page.locator('#original-office [data-seat16]')).to_have_count(count)
                    if building=='NEXUS':
                        capture('F01-bureau-nexus')
                        capture('F05-connecte-bureau')
                        page.locator('#original-office [data-seat16="director"]').focus()
                        page.keyboard.press('Enter')
                        expect(page.locator('#team-detail')).to_contain_text('NEXUS')
                        page.locator('.office-switch button').click()
                        expect(page.locator('#room-view img')).to_be_visible()
                    else:
                        capture('F01-bureau-core')
                        page.locator('#original-office [data-seat16="1"]').focus()
                        page.keyboard.press('Enter')
                        expect(page.locator('#team-detail')).to_contain_text('MNEMOS')
                    page.locator('#campus-back').click()
                # Every existing floor keeps its five station controls; the ten original
                # vector-only services now expose their actual five interactive objects.
                layout=page.evaluate('window.AESLiveLayout')
                visited=0;vector=0
                for building in layout:
                    for floor in building['floors']:
                        page.locator('#buildings button[data-id="'+building['id']+'"]').click()
                        page.locator('#lift-view [data-floor="'+floor['id']+'"]').click()
                        expect(page.locator('#room-view .station-list button')).to_have_count(5)
                        if not floor['asset']:
                            graphic=page.locator('#room-view .original-vector-room')
                            expect(graphic).to_be_visible()
                            expect(graphic.locator('[data-room-station]')).to_have_count(5)
                            for i in range(5):
                                station_target=graphic.locator('[data-room-station="'+floor['id']+':station:'+str(i)+'"]')
                                station_target.focus()
                                page.keyboard.press('Enter')
                                expect(station_target).to_have_attribute('aria-pressed','true')
                                expect(page.locator('#station-title')).to_have_text(floor['stations'][i]['name'])
                            vector+=1
                            if floor['id'] in ('VIDEO183','ITOPS17','PEOPLE17'):
                                capture('F03-'+floor['id'])
                        visited+=1
                        page.locator('#campus-back').click()
                assert (visited,vector)==(37,10),(visited,vector)
                page.locator('#buildings button[data-id="ATLAS"]').click()
                page.locator('#lift-view [data-floor="ATLAS"]').click()
                expect(page.locator('#room-tabs [role="tab"]:not([hidden])')).to_have_count(4)
                page.locator('#tab-scene').focus()
                page.keyboard.press('ArrowRight')
                expect(page.locator('#tab-functions')).to_have_attribute('aria-selected','true')
                expect(page.locator('#room-functions')).to_be_visible()
                expect(page.locator('#room-view')).to_be_hidden()
                expect(page.locator('#function-cards [data-function-tool="missions"]')).to_have_count(1)
                page.locator('#function-cards [data-function-tool="missions"]').click()
                expect(page.locator('#function-detail #native-tool')).to_be_visible()
                expect(page.locator('#native-tool h3')).to_contain_text('Missions')
                expect(page.locator('#native-tool [role="status"]')).to_contain_text('résultat')
                capture('F04-fonctions-metier')
                page.locator('#tab-team').click()
                expect(page.locator('#team-view')).to_be_visible()
                expect(page.locator('#room-functions')).to_be_hidden()
                capture('F04-equipe')
                page.locator('#tab-settings').click()
                expect(page.locator('#room-options')).to_be_visible()
                page.locator('#room-options summary').click()
                expect(page.locator('#option-stations button')).to_have_count(5)
                capture('F04-options')
                page.locator('#tab-scene').click()
                expect(page.locator('#room-view')).to_be_visible()
                page.locator('#campus-back').click()
                page.locator('#buildings button[data-id="SENTINEL"]').click()
                page.locator('#lift-view [data-floor="INCIDENTS"]').click()
                page.locator('#tab-functions').click()
                page.locator('[data-function-tool="incidents"]').click()
                expect(page.locator('#function-detail #native-tool h3')).to_contain_text('Incidents & reprises')
                expect(page.locator('#native-tool [role=status]')).to_contain_text('résultat')
                expect(page.locator('#native-tool')).to_contain_text('Supervision enregistrée')
                capture('O02-incidents')
                page.locator('#campus-back').click()
                page.locator('#buildings button[data-id="SENTINEL"]').click()
                page.locator('#lift-view [data-floor="SENTINEL"]').click()
                page.locator('#tab-functions').click()
                page.locator('[data-function-tool="quality"]').click()
                expect(page.locator('#function-detail #native-tool h3')).to_contain_text('Preuves qualité')
                expect(page.locator('#native-tool [role=status]')).to_contain_text('résultat')
                expect(page.locator('#native-tool')).to_contain_text('Aucune entrée correspondante')
                capture('O02-qualite')
                page.locator('#campus-back').click()
                page.locator('#buildings button[data-id="CORE"]').click()
                page.locator('#lift-view [data-floor="ITOPS17"]').click()
                page.locator('#tab-functions').click()
                page.locator('[data-function-tool="infrastructure"]').click()
                expect(page.locator('#function-detail #native-tool h3')).to_contain_text('Inventaire technique')
                expect(page.locator('#native-tool [role=status]')).to_contain_text('résultat')
                expect(page.locator('#native-tool')).to_contain_text('Aperçu sans worker')
                expect(page.locator('#native-tool')).to_contain_text('Sauvegarde actuelle non vérifiée')
                capture('O02-infrastructure')
                page.locator('#campus-back').click()
                page.locator('#buildings button[data-id="MIDAS"]').click()
                page.locator('#lift-view [data-floor="ECON"]').click()
                page.locator('#tab-functions').click()
                page.locator('[data-function-tool="economy"]').click()
                expect(page.locator('#function-detail #native-tool h3')).to_contain_text('Pilotage économique')
                expect(page.locator('#native-tool [role=status]')).to_contain_text('résultat')
                expect(page.locator('#native-tool')).to_contain_text('CA vérifié, bénéfice, marge réelle et trésorerie : indisponibles')
                expect(page.locator('#native-tool')).to_contain_text('TEST · exclus du CA réel')
                capture('O02-economie')
                page.locator('#campus-back').click()
                page.locator('.top [data-view="finance"]').click()
                expect(page.locator('#native-tool')).to_be_visible()
                expect(page.locator('#native-tool h3')).to_contain_text('Dépenses API')
                expect(page.locator('#otherView')).to_be_visible()
                expect(page.locator('#campusView')).to_be_hidden()
                expect(page.locator('#top-tool-host #native-tool')).to_be_visible()
                capture('F05-navigation-finances')
                page.locator('#back-top-tool').click()
                expect(page.locator('#campusView')).to_be_visible()
                expect(page.locator('#otherView')).to_be_hidden()
                assert not posts and not errors,(posts,errors)
                assert not any('/campus/design.js' in url for url in requests)
                network.assert_not_called()
                browser.close()
                assert s.DB.read_bytes()==before
        finally:srv.shutdown();srv.server_close();th.join()
    print('F01 original design smoke passed')

if __name__=='__main__':
    smoke()
    smoke_live()
    smoke_commands()
    smoke_commands('original')
    smoke_preview()
    smoke_original()

