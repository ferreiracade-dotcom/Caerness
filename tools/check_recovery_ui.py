"""Check diagnostics UI on port 8775 with an explicit timeout fixture (no inference).

The disposable campaign is prepared separately; never run against an owner save.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    output=Path('runs/windows-recovery-ui');output.mkdir(parents=True,exist_ok=True)
    errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        context=await browser.new_context(permissions=['clipboard-read','clipboard-write'],viewport={'width':1440,'height':900})
        page=await context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto('http://127.0.0.1:8775');await page.wait_for_function('state && state.player')
        report=await page.evaluate("api('/api/diagnostics')")
        failure=report['requests'][0]['failure']
        assert failure['code']=='timeout'
        await page.evaluate("data=>showReferral(data)",{'request_id':report['requests'][0]['request_id'],'failure':{'request_id':report['requests'][0]['request_id'],'code':'timeout','phase':failure['phase']},'reason':'INTERFACE TEST ONLY: the response timed out. This screenshot uses a staged failure, not real inference.'})
        assert 'timed out' in await page.locator('#referralTitle').inner_text()
        await page.screenshot(path=str(output/'timeout-desktop.png'))
        await page.locator('#closeReferral').click()
        await page.locator('#settingsButton').click()
        await page.locator('summary').filter(has_text='Advanced options').click()
        await page.locator('#copyDiagnostics').click()
        await page.wait_for_function("document.getElementById('playStatus').textContent.includes('Diagnostics copied')")
        clipboard=await page.evaluate('navigator.clipboard.readText()')
        assert 'PRIVATE_UI_SENTINEL' not in clipboard and 'narrative_play_v1' in clipboard
        assert 'timeout' in clipboard and 'hardware' in clipboard
        assert await page.locator('#modelSetup').evaluate('(form)=>form.checkValidity()')
        await page.screenshot(path=str(output/'diagnostics-desktop.png'))
        await page.set_viewport_size({'width':390,'height':844})
        await page.locator('#copyDiagnostics').scroll_into_view_if_needed()
        assert await page.evaluate('document.body.scrollWidth <= innerWidth+1')
        await page.screenshot(path=str(output/'diagnostics-phone.png'))
        assert not errors,errors
        await browser.close()
    (output/'browser-check.json').write_text(json.dumps({'fixture':'Explicit timeout UI fixture, no model inference','desktop':'1440x900','phone':'390x844','clipboard_redaction':True,'settings_form_valid':True,'phone_no_horizontal_overflow':True,'browser_errors':errors},indent=2))
    print('Diagnostics titles, clipboard privacy, default form validity, desktop/mobile layout PASS (staged UI fixture, no inference)')

if __name__=='__main__':asyncio.run(main())
