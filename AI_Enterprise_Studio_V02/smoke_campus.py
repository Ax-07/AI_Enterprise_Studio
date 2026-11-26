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
            expect(page.locator('.demo')).to_contain_text('D01')
            expect(page.locator('#buildings [data-id]')).to_have_count(7)
            expect(page.locator('#hdDecor image')).to_have_count(1)
            campus=page.locator('#buildings [data-id="HERMES"]').first
            campus.focus()
            campus.press('Enter')
            expect(page.locator('#elevator181')).to_be_visible()
            expect(page.locator('#elevator181 [data-floor181]')).to_have_count(8)
            page.locator('#roster [data-agent="NEXUS"]').click()
            expect(page.locator('#elevator181 [data-floor181]')).to_have_count(5)
            page.locator('#elevator181 [data-floor181="LAB"]').click()
            expect(page.locator('#roomScene')).to_be_visible()
            expect(page.locator('#roomScene svg')).to_have_count(1)
            page.locator('#backCampus').click()
            expect(page.locator('#campusSvg')).to_be_visible()
            page.wait_for_timeout(500)
            assert not errors,errors
            assert not unexpected,unexpected
            assert any(status==200 and '/campus/assets/' in url for status,url in responses),responses
            assert all(status<400 for status,url in responses),responses
            browser.close()
    finally:srv.shutdown();srv.server_close();thread.join()
    print('Campus D01 smoke passed')

if __name__=='__main__':smoke()
