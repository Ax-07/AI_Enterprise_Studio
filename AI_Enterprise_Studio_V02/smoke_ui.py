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
    with tempfile.TemporaryDirectory() as tmp, patch.object(s,'DB',Path(tmp)/'test.sqlite3'), patch.object(s,'config',return_value={**s.config(),'key':'fake-test-key','brave':'','budget':2000000}), patch.object(s,'request',side_effect=AssertionError('Appel fournisseur interdit')) as network, patch.object(m,'fetch_page',side_effect=AssertionError('Réseau interdit')):
        s.init()
        with s.db() as c:
            mid=m.create(s,c,'Étude Shopify', 'cloud')
            c.execute("UPDATE missions SET state='terminée' WHERE id=?",(mid,))
            aid=c.execute("INSERT INTO artifacts(mission,name,version,agent,content,description) VALUES(?, 'kit.csv',1,'NEXUS','a,b\n1,2\n','test')",(mid,)).lastrowid
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
                expect(page.locator('#connection-text')).to_have_text('Serveur V0.2.2')
                expect(page.locator('#quick-products')).to_have_text('1')
                for section in ('decisions','missions','work','opps','files','goals','agents','finance','memory','tools','home'):
                    page.locator(f'[data-page="{section}"]').click()
                    expect(page.locator('#page-'+section)).to_be_visible()
                page.locator('[data-quick="create"]').click()
                expect(page.locator('#mission')).to_have_value(__import__('re').compile('NEXUS'))
                expect(page.locator('#attached-file')).to_be_hidden()
                page.locator('[data-page="files"]').click()
                page.locator('#file-list').get_by_role('button',name='Aperçu texte').click()
                expect(page.locator('#file-content')).to_have_text('a,b\n1,2',use_inner_text=True)
                with page.expect_download() as dl:
                    page.locator('#file-list').get_by_role('button',name='Télécharger').click()
                assert dl.value.suggested_filename=='kit.csv'
                assert Path(dl.value.path()).read_text()=='a,b\n1,2\n'
                page.locator('#file-list').get_by_role('button',name='Améliorer').click()
                expect(page.locator('#attached-label')).to_contain_text('kit.csv')
                expect(page.locator('#mission')).to_have_value(__import__('re').compile('ref:'+str(aid)))
                page.locator('#detach-file').click()
                expect(page.locator('#attached-file')).to_be_hidden()
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
                expect(page.locator('#mission-state')).to_have_text('terminée',timeout=15000)
                # Verify real server completion rather than a stale state.
                page.wait_for_function("document.querySelector('#select').value !== '"+str(mid)+"'")
                with s.db() as c:
                    assert c.execute("SELECT state FROM missions WHERE mode='demo'").fetchone()[0]=='terminée'
                    assert s.used(c)==500
                page.locator('[data-page="files"]').click()
                page.locator('#file-filter').select_option(str(mid))
                page.locator('#file-list').get_by_role('button',name='Améliorer').click()
                expect(page.locator('#attached-file')).to_be_visible()
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

if __name__=='__main__':
    smoke()
