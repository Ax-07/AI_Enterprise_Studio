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
    from test_campus_live import fixture
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'test.db';fixture(path)
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
                expect(page.locator('#campus-map [data-building]')).to_have_count(7)
                page.locator('#campus-map [data-building="CORE"]').focus()
                page.keyboard.press('Enter')
                expect(page.locator('#lift-view [data-floor]')).to_have_count(5)
                page.locator('#lift-view [data-floor="CORE"]').click()
                expect(page.locator('#room-view [data-station]')).to_have_count(5)
                expect(page.locator('#room-view img')).to_be_visible()
                expect(page.locator('#agents')).to_contain_text('MNEMOS')
                expect(page.locator('#agents')).to_contain_text('PROMETHEUS')
                expect(page.locator('#missions')).to_contain_text('SIMULATION enregistrée')
                expect(page.locator('#artifacts')).to_contain_text('SIMULATION enregistrée')
                page.locator('#room-view [data-station="CORE:station:2"]').click()
                expect(page.locator('#station-content')).to_contain_text('MNEMOS')
                page.locator('#lift-back').click()
                page.locator('#buildings button[data-id="HERMES"]').click()
                expect(page.locator('#lift-view [data-floor]')).to_have_count(8)
                page.locator('#lift-view [data-floor="VIDEO183"]').click()
                expect(page.locator('#room-view [data-station]')).to_have_count(5)
                page.locator('#room-view [data-station="VIDEO183:station:1"]').click()
                expect(page.locator('#station-content')).to_contain_text('non raccordée')
                page.route('**/campus/live-data',lambda r:r.fulfill(status=503,body='{}',content_type='application/json'))
                page.locator('#refresh').click()
                expect(page.locator('#status')).to_contain_text('Données indisponibles')
                expect(page.locator('#metrics .metric')).to_have_count(0)
                expect(page.locator('#station-content')).to_contain_text('Données indisponibles')
                assert not errors and not writes and not external,(errors,writes,external)
                browser.close()
        finally:srv.shutdown();srv.server_close();thread.join()
    print('Campus D03 read-only smoke passed')

if __name__=='__main__':
    smoke()
    smoke_live()

