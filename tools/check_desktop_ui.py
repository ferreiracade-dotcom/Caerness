"""Browser usability check. No model replies: screenshots use labelled Bible excerpts.

Run against a fresh copy served by narrative_play.py on port 8774. Requires Playwright.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from playwright.async_api import async_playwright

async def main():
 out=ROOT/'docs/demos/desktop-narrative';out.mkdir(parents=True,exist_ok=True)
 errors=[];results=[]
 # Reset only this disposable UI copy's setup camera, so each run exercises first launch.
 os.environ['CAERNESS_DB_PATH']='/tmp/caerness-desktop-ui.db'
 from engine.db import connect
 with connect() as c:
  c.execute('DELETE FROM player_state')
  c.execute('UPDATE campaign_setup_state SET player_setup_complete=0 WHERE id=1')
  c.commit()
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':1440,'height':900})
  await page.emulate_media(reduced_motion='reduce')
  page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://127.0.0.1:8774');await page.wait_for_function('state && ledger')
  if not await page.evaluate('!!state.player'):
   assert await page.locator('#onboarding').is_visible()
   await page.get_by_text('Or inhabit an existing character',exact=True).click()
   await page.locator('#characterSearch').fill('Robert Baird')
   await page.get_by_role('button',name='Inhabit this character').click()
   await page.wait_for_function("state && state.player && state.player.name==='Robert Baird'")
  # Source-only reading fixtures; no AI or outcome is simulated.
  os.environ['CAERNESS_DB_PATH']='/tmp/caerness-desktop-ui.db'
  from engine.db import connect
  from engine.ai_planning import session,message
  from engine.canon import extract_docx_blocks
  paragraphs=[text for _,text in extract_docx_blocks(ROOT/'canon/world_bible_current.docx')]
  excerpts=[next(t for t in paragraphs if prefix in t) for prefix in ('Formality in Caerness is not decoration','The single most common error in reading Caerness','The Underheaven Empire possesses')]
  with connect() as c:
   old=session(c);message(c,old['id'],'player','Reading layout preview — World Bible reference, not live gameplay.')
   message(c,old['id'],'assistant','INTERFACE PREVIEW — Authored World Bible excerpts below; no model-generated scene or gameplay outcome.\n\n'+'\n\n'.join(excerpts))
   for i in range(6):
    s=session(c);message(c,s['id'],'player',f'Interface-only history fixture {i}; no model response.')
   c.commit();oldid=old['id']
  await page.evaluate(f"planningSession={oldid};newConversation=false;refresh()")
  assert (await page.locator('#transcript').inner_text()).count('Authored World Bible')==1
  await page.reload();await page.wait_for_function('state && state.player')
  await page.evaluate(f"resumeSession({oldid})")
  assert 'Formality in Caerness' in await page.locator('#transcript').inner_text()
  # Formatting doesn't execute HTML or invent a speaker.
  assert await page.evaluate('prose(\'<img src=x onerror="window.untrusted=true">\').includes("&lt;img")')
  assert '<blockquote' in await page.evaluate('prose(\'“A formatting test only.”\')')
  # Keyboard routes and multiline input are actual client behavior.
  await page.keyboard.press('Control+k');assert await page.locator('#input').evaluate('(e)=>e===document.activeElement')
  await page.locator('#input').fill('A multiline intention');await page.keyboard.press('Shift+Enter');await page.keyboard.type('with its conditions retained.');assert '\n' in await page.locator('#input').input_value()
  # Pressing Enter sends unchanged text to the real (unavailable) runtime; no canned AI response.
  await page.keyboard.press('Enter');await page.wait_for_function("!busy && !document.getElementById('referral').classList.contains('hidden')")
  assert 'not connected' in await page.locator('#referralTitle').inner_text()
  await page.locator('#closeReferral').click()
  await page.evaluate(f'resumeSession({oldid})')
  await page.keyboard.press('Alt+2');assert await page.locator('#world').is_visible()
  assert await page.locator('#scene').is_visible()
  scroll=await page.locator('#storyScroll').evaluate('(e)=>e.scrollTop')
  await page.get_by_role('button',name='Commitments',exact=False).click()
  assert await page.locator('#storyScroll').evaluate('(e)=>e.scrollTop')==scroll
  await page.keyboard.press('Escape');assert not await page.locator('#notebook').is_visible()
  await page.locator('#settingsButton').click();assert await page.locator('#settingsDialog').is_visible()
  await page.locator('#readingSize').select_option('large');await page.locator('#closeSettings').click();assert not await page.locator('#modelSetup').is_visible()
  await page.locator('#settingsButton').click();await page.locator('#readingSize').select_option('standard');await page.locator('#closeSettings').click()
  for width,height,label in ((1440,900,'desktop-1440'),(1920,1080,'desktop-1920'),(390,844,'phone-390')):
   await page.set_viewport_size({'width':width,'height':height})
   await page.evaluate("openPanel('scene');document.getElementById('storyScroll').scrollTop=0")
   await page.wait_for_timeout(250)
   assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),label
   box=await page.locator('#input').bounding_box();assert box['y']>=0 and box['y']+box['height']<=height,label
   await page.screenshot(path=str(out/f'{label}-story.png'))
   await page.get_by_role('button',name='World',exact=False).click()
   assert await page.locator('#world').is_visible()
   await page.screenshot(path=str(out/f'{label}-notebook.png'))
   await page.locator('#closeNotebook').click()
   await page.locator('#settingsButton').click();assert await page.locator('#modelSetup').is_visible();await page.keyboard.press('Escape')
   results.append({'viewport':[width,height],'horizontal_overflow':False,'input_visible':True,'notebook_and_settings_accessible':True})
  # Fixture-only decision presentation must expose omissions and disable commitment.
  html=await page.evaluate("reviewCard({id:1,session_id:1,digest:'fixture',summary:'Interface-only decision test',review_scope:['Ask for an existing responsibility.'],original_instruction:'Include all conditions.',unresolved:['A gift remains unsupported.'],scope_verification:{complete:false,omissions:['Missing gift']},source_handling:[]})")
  assert 'Missing gift' in html and 'data-approve-plan' not in html
  assert not errors,errors
  (out/'browser-checks.json').write_text(json.dumps({'viewports':results,'first_time_existing_character_selection':True,'older_than_five_conversations_resumable':True,'keyboard_enter_shift_enter_ctrl_k_alt_tabs_escape':True,'real_unavailable_model_message_saved':True,'safe_prose_formatting':True,'incomplete_decision_cannot_approve':True,'javascript_errors':errors,'screenshot_content':'Labelled authored World Bible reference fixture; not a live-model transcript or gameplay demonstration.'},indent=2)+'\n')
  await browser.close()
 print('Desktop/mobile client, keyboard, setup, history, unavailable-model feedback, decision disclosure and safe formatting PASS; no model replies fabricated.')
asyncio.run(main())
