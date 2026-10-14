"""Responsive provider-settings check. Explicit UI fixture, no model inference."""
import asyncio
import json
import os
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))

async def main():
    output=ROOT/'runs/cloud-ui';output.mkdir(parents=True,exist_ok=True)
    os.environ['CAERNESS_DB_PATH']=str(output/'ui-fixture.db')
    from planning_demo import fixture
    from engine.ai_planning import session,message
    from engine.local_model import set_runtime_config
    from engine.ai_providers import PROVIDERS
    from engine.mobile_server import CaernessHandler
    c,ids=fixture();s=session(c)
    message(c,s['id'],'player','[INTERFACE FIXTURE] I pause in the courtyard.')
    message(c,s['id'],'assistant','[INTERFACE FIXTURE — no model inference] This is a layout preview of the same persistent story while AI providers change.')
    set_runtime_config(c,device_profile='desktop_free_cloud_groq',local_backend='openai_compatible',local_endpoint=PROVIDERS['groq']['endpoint'],local_model='openai/gpt-oss-120b');c.commit();c.close()
    server=ThreadingHTTPServer(('127.0.0.1',0),CaernessHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[];sizes=[]
    from playwright.async_api import async_playwright
    try:
      async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        for width,height in [(1440,900),(1920,1080),(390,844)]:
            await page.set_viewport_size({'width':width,'height':height})
            await page.goto(f'http://127.0.0.1:{server.server_port}')
            await page.wait_for_function('state && state.player')
            await page.locator('#settingsButton').click()
            assert 'groq' in await page.locator('#activeProvider').inner_text()
            assert 'Choose AI.cmd' in await page.locator('#settingsDialog').inner_text()
            assert await page.locator('input[type=password]').count()==0
            assert await page.evaluate('document.body.scrollWidth <= innerWidth+1')
            await page.screenshot(path=str(output/f'provider-settings-{width}x{height}.png'))
            await page.locator('#modelSetup').locator('xpath=..').locator('summary').click()
            assert await page.locator('#modelSetup').evaluate('(form)=>form.checkValidity()')
            sizes.append({'width':width,'height':height,'no_horizontal_overflow':True,'valid_response_budget_form':True})
        assert not errors,errors
        await browser.close()
    finally:server.shutdown();server.server_close();thread.join(2)
    (output/'browser-check.json').write_text(json.dumps({'evidence_type':'UI fixture, NOT actual model responses','sizes':sizes,'errors':errors,'no_browser_key_input':True},indent=2))
    print('Provider settings desktop/phone layout and credential-free browser PASS (UI fixture only)')

if __name__=='__main__':asyncio.run(main())
