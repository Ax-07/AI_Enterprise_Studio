"""Trusted test harness, only executed inside the restricted test container."""
import json, sys
from playwright.sync_api import sync_playwright, expect

def main():
    raw=sys.stdin.buffer.read(160001)
    if len(raw)>160000: raise ValueError('Input too large')
    request=json.loads(raw)
    results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--disable-dev-shm-usage'])
        for case in request['cases']:
            context=browser.new_context(service_workers='block',accept_downloads=False)
            context.route('**/*',lambda route:route.abort())
            page=context.new_page()
            page.set_default_timeout(1600)
            step_index=0
            try:
                page.set_content(request['html'],wait_until='domcontentloaded',timeout=5000)
                for step_index,step in enumerate(case['steps'],1):
                    loc=page.locator('css='+step['selector'])
                    op=step['op'];v=step.get('value')
                    if op=='fill': loc.fill(v)
                    elif op=='select': loc.select_option(v)
                    elif op=='click': loc.click()
                    elif op=='upload': loc.set_input_files({'name':'synthetic.csv','mimeType':'text/csv','buffer':v.encode('utf-8')})
                    elif op=='contains': expect(loc).to_contain_text(v,timeout=1600)
                    elif op=='text_equals': expect(loc).to_have_text(v,timeout=1600)
                    elif op=='value_equals': expect(loc).to_have_value(v,timeout=1600)
                    elif op=='visible': expect(loc).to_be_visible(timeout=1600)
                    else: raise ValueError('Unknown test action')
                results.append({'name':case['name'],'passed':True,'steps':step_index})
            except Exception as e:
                # Do not expose page console, raw HTML or arbitrary exception content.
                results.append({'name':case['name'],'passed':False,'step':step_index,'error':type(e).__name__})
            finally: context.close()
        browser.close()
    print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':main()
