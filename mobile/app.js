let state = null;
let referral = null;
let worldTab = 'people';
let busy = false;
let historyIndex = [];
let currentPanel = 'scene';
let ledger = null;
let planningSession = Number(localStorage.getItem("caernessSession")) || null;
let newConversation = false;
let cameraActor = null;
let revisingPlan = null;

const $ = (id) => document.getElementById(id);
$('newIdea').addEventListener('click', () => { if (busy) return; revisingPlan=null; planningSession=null; newConversation=true; localStorage.removeItem('caernessSession'); renderState(); openPanel('scene'); $('input').focus(); });
function esc(v='') { return String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function api(path, options={}) {
  const res = await fetch(path, {headers:{'Content-Type':'application/json'}, ...options});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function prose(text='') {
  // Formatting only: quoted speech differs visually, without inferring a speaker or facts.
  return String(text).split(/\n\s*\n/).filter(Boolean).map(part=> {
    const safe=esc(part);
    const spoken=safe.replace(/(“[^“”\n]+”|&quot;[^\n]*?&quot;)/g,'<span class="spoken">$1</span>');
    return /^[“"]/.test(part.trim()) ? `<blockquote class="dialogue">${spoken}</blockquote>` : `<p>${spoken}</p>`;
  }).join('');
}
function reviewCard(x) {
  const omissions=[...(x.unresolved||[]),...(x.scope_verification?.omissions||[])];
  const permit=!omissions.length && x.scope_verification?.complete!==false;
  return `<article class="decision-card"><span class="eyebrow">A MEANINGFUL DECISION</span><h3>Before you commit</h3><p>${esc(x.summary)}</p>${x.review_scope.map(t=>`<p>${esc(t)}</p>`).join('')}${omissions.map(t=>`<p class="missing">Still unresolved: ${esc(t)}</p>`).join('')}<details><summary>Your original intention and unexecuted terms</summary><p>${esc(x.original_instruction)}</p>${(x.source_handling||[]).filter(h=>h.handling!=='planned').map(h=>`<p>Not executed: ${esc(h.text)}</p>`).join('')}</details>${permit?`<button data-approve-plan="${x.id}" data-digest="${esc(x.digest)}">Proceed with these terms</button>`:''}<button class="secondary" data-revise-plan="${x.id}" data-session="${x.session_id}">Keep discussing</button></article>`;
}
function renderState() {
  if (!state) return;
  const p=state.player;
  $('worldline').textContent=p?`${p.location||'Unknown'} · Day ${state.world.day} · ${p.name}`:'A new life awaits';
  $('chapterTitle').textContent=p?.location||'Your life in Caerness';
  if (cameraActor && cameraActor!==p?.actor_id) { planningSession=null;newConversation=true; }
  cameraActor=p?.actor_id;
  const conversations=state.conversations||[];
  if (planningSession && !conversations.some(x=>x.id===planningSession)) planningSession=null;
  if (!planningSession && !newConversation && conversations.length) planningSession=conversations[0].id;
  const index=historyIndex.length?historyIndex:conversations.map(x=>({id:x.id,title:x.messages.find(m=>m.role==='player')?.text,created_day:x.messages[0]?.day}));
  $('conversationPicker').innerHTML='<option value="">New conversation</option>'+index.map(x=>`<option value="${x.id}">${esc(String(x.title||'Conversation').slice(0,65))}</option>`).join('');
  $('conversationPicker').value=planningSession||'';
  $('historyBody').innerHTML=index.map(x=>`<div class="card"><div class="meta">Day ${esc(x.created_day)}</div><div>${esc(String(x.title||'Conversation').slice(0,140))}</div><button data-resume-session="${x.id}">Resume conversation</button></div>`).join('')||'<p class="muted">Your conversations will remain here as your life unfolds.</p>';
  const active=conversations.find(x=>x.id===planningSession);
  const turns=state.turns||[];
  if (active) {
    $('transcript').innerHTML=active.messages.filter(x=>['player','assistant'].includes(x.role)).map(x=>`<article class="turn"><div class="daytag">Day ${esc(x.day)}</div>${x.role==='player'?`<div class="player-line"><span class="speaker-label">${esc(p?.name||'You')}</span>${esc(typeof x.text==='string'?x.text:'')}</div>`:`<div class="narration">${prose(typeof x.text==='string'?x.text:x.text.proposed_scope||'')}</div>`}</article>`).join('');
  } else {
    $('transcript').innerHTML=newConversation?'':turns.map(t=>`<article class="turn"><div class="daytag">Day ${esc(t.day_started)}${t.day_ended!==t.day_started?`–${esc(t.day_ended)}`:''}</div><div class="player-line"><span class="speaker-label">${esc(p?.name||'You')}</span>${esc(t.raw_input)}</div><div class="narration">${prose(t.narration_text||'')}</div></article>`).join('');
  }
  const review=(state.plans||[]).find(x=>x.session_id===planningSession && x.status==='draft');
  if (review) $('transcript').innerHTML+=reviewCard(review);
  $('emptyScene').classList.toggle('hidden',!!$('transcript').innerHTML||!p);
  $('attention').innerHTML=(state.attention||[]).slice(0,4).map(c=>`<div class="attention-card ${esc(c.cue_type)}">${esc(c.text)}</div>`).join('');
  const m=state.matters||{};
  $('mattersBody').innerHTML=[
    ...(state.plans||[]).map(x=>x.status==='draft'?reviewCard(x):`<div class="card"><div class="card-title">${esc(x.summary)}</div><div class="meta">${esc(x.status.replaceAll('_',' '))}</div>${Object.values(x.steps).filter(s=>s.result.summary).map(s=>`<p>${esc(s.result.summary)}${s.result.progress==null?'':` (${Math.round(s.result.progress)}%)`}</p>`).join('')}<button data-revise-plan="${x.id}" data-session="${x.session_id}">Discuss this undertaking</button></div>`),
    ...(state.scope_reviews||[]).map(x=>`<div class="card"><p>${esc(x.detail.original_instruction)}</p><p>${esc(x.summary)}</p><button data-confirm-appointment="${x.action_id}">Confirm this offer only</button></div>`),
    ...(m.appointments||[]).map(x=>card(x.title,`${x.holder_name} · ${x.institution_name}`,`Held since day ${x.started_day}`)),
    ...(m.obligations||[]).map(o=>card(o.description,o.due_day==null?'No fixed date':`Due day ${o.due_day}`,o.notes)),
    ...(m.intentions||[]).map(i=>card(i.description,i.status,i.possession_name||''))
  ].join('')||'<p class="muted">No outstanding promises. A quiet day is yours to spend.</p>';
  renderWorld();
  $('youBody').innerHTML=p?card(p.name,p.location||'','Your circumstances and the people you know give shape to your life.'):'<p class="muted">Choose or create a character to begin.</p>';
  const r=state.runtime||{};
  if (!$('modelEndpoint').value) $('modelEndpoint').value=r.model_endpoint||'';
  if (!$('modelName').value) $('modelName').value=r.local_model||'';
  if (!$('modelContext').value) $('modelContext').value=r.local_heavy_context_tokens||8192;
  if (!$('modelOutput').value) $('modelOutput').value=r.local_max_output_tokens||1200;
  $('runtimeBody').innerHTML=`<div class="meta">${esc(r.local_backend||'')} · ${esc(r.local_model||'')}<br>Story time advances through play only.</div>`;
}
function card(title, meta='', body='') {
  return `<div class="card"><div class="card-title">${esc(title)}</div>${meta?`<div class="meta">${esc(meta)}</div>`:''}${body?`<div>${esc(body)}</div>`:''}</div>`;
}
document.addEventListener('click', async e => {
  if (busy) return;
  const resume=e.target.closest('[data-resume-session]');
  if (resume) { await resumeSession(Number(resume.dataset.resumeSession)); return; }
  const revise = e.target.closest('[data-revise-plan]');
  if (revise) {
    planningSession = Number(revise.dataset.session); revisingPlan = Number(revise.dataset.revisePlan);
    await refresh(); openPanel('scene'); $('input').focus(); return;
  }
  const approve = e.target.closest('[data-approve-plan]');
  if (approve) {
    setBusy(true);
    try {
      const data = await api('/api/plan-approve', {method:'POST', body:JSON.stringify({plan_id:Number(approve.dataset.approvePlan),digest:approve.dataset.digest,narrative:$('playMode').value==='narrative'})});
      $('playStatus').textContent=data.summary||'Decision saved.';
      if(data.status==='external_recommended')showReferral(data);
      await refresh(); scrollLatest();
    } catch (error) { alert(error.message); }
    finally {setBusy(false);}
    return;
  }
  const button = e.target.closest('[data-confirm-appointment]');
  if (!button) return;
  try {
    await api('/api/appointment-confirm', {method:'POST', body:JSON.stringify({action_id:Number(button.dataset.confirmAppointment)})});
    await refresh();
  } catch (error) { alert(error.message); }
});
function renderWorld() {
  if (!state) return;
  let html = '';
  if (worldTab === 'people') {
    html = (state.people || []).map(p => `<div class="card"><div class="card-title">${esc(p.name)}</div><div class="meta">${esc(p.type || '')}</div>${(p.shared_history||[]).length ? `<ul class="history">${p.shared_history.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>` : '<div class="meta">No significant shared history recorded yet.</div>'}</div>`).join('');
  } else if (worldTab === 'places') {
    html = (state.places || []).map(p => card(p.name, `${p.kind || ''}${p.last_information_day != null ? ` • last information day ${p.last_information_day}`:''}`, p.political_owner || '')).join('');
  } else {
    html = (state.claims || []).map(c => card(c.belief_text, `${c.certainty} • learned day ${c.learned_day}`, `${c.source_label}${c.source_location_name ? ` at ${c.source_location_name}`:''}`)).join('');
  }
  $('worldBody').innerHTML = html || '<p class="muted">Nothing known here yet.</p>';
}
function kv(rows=[]) { return `<div class="kv">${rows.map(([k,v])=>`<span>${esc(k)}</span><span>${esc(v ?? '—')}</span>`).join('')}</div>`; }
function renderLedger() {
  if (!ledger) return;
  const setup = ledger.setup || {}; const ss = setup.setup || {}; const counts = setup.counts || {};
  if (!ss.bootstrap_complete && !(setup.available_locations && counts.named_characters)) {
    $('setupBody').innerHTML = `<div class="card"><div class="card-title">Set up Caerness</div><div class="meta">Load the versioned World-Bible-derived starting world. Open geography/calendar questions remain unseeded.</div><div class="setup-actions"><button id="bootstrapCampaign">Bootstrap Caerness</button></div></div>`;
    setTimeout(()=>{ const b=$('bootstrapCampaign'); if(b) b.onclick=bootstrapCampaign; },0);
  } else if (!state?.player) {
    $('setupBody').innerHTML = `<div class="setup-card"><span class="eyebrow">BEGIN A LIFE</span><h2>Create your character</h2><div class="meta">Choose where your life begins. Your circumstances will persist as the world changes.</div><div class="setup-actions"><input id="playerName" placeholder="Character name"><input id="playerStart" value="Cairnholt" placeholder="Start location"><input id="playerAge" type="number" min="0" max="200" placeholder="Age (optional)"><button id="createPlayer">Begin your story</button></div><details><summary>Or inhabit an existing character</summary><p>Choose someone already living in this campaign. Their established circumstances remain intact.</p><input id="characterSearch" placeholder="Search by name" aria-label="Find an existing character"><div id="characterChoices"></div></details></div>`;
    setTimeout(()=>{ const b=$('createPlayer'); if(b) b.onclick=createPlayer; },0);
  } else { $('setupBody').innerHTML=''; }
  $('onboarding').innerHTML=$('setupBody').innerHTML; $('setupBody').innerHTML='';
  const admin = ledger.admin || {};
  let html = card('Campaign integrity', `Engine ${admin.engine_version || ''} • schema ${admin.schema_version || ''}`, `${admin.contradiction_count || 0} detected save contradiction(s)`);
  html += card('Seeded world', `${counts.named_characters || 0} named characters • ${counts.institutions || 0} institutions • ${counts.locations || 0} places`, `${Math.round(counts.aggregate_population || 0).toLocaleString()} aggregate Hearth population`);
  const p = ledger.player;
  if (p) {
    const hp=p.health?.profile || {};
    html += `<div class="card"><div class="card-title">${esc(p.name)}</div>${kv([['Location',p.location],['Aging phase',hp.aging_phase],['Functional capacity',hp.functional_capacity],['Recovery',hp.recovery_capacity],['Pain burden',hp.pain_burden]])}</div>`;
    if (p.household) html += card(p.household.name, `Household • ${p.household.role || ''}`, `Cohesion ${Math.round(p.household.cohesion)} • liquidity ${Math.round(p.household.liquidity)}`);
    if ((p.derived_motives||[]).length) html += `<div class="card"><div class="card-title">Current pressures & continuities</div><ul class="history">${p.derived_motives.map(x=>`<li>${esc(x.description)} <span class="meta">(${esc(x.domain)})</span></li>`).join('')}</ul></div>`;
    const cond=(p.health?.conditions||[]).filter(x=>['active','recovering','chronic'].includes(x.status));
    if(cond.length) html += `<div class="card"><div class="card-title">Health</div><ul class="history">${cond.map(x=>`<li>${esc(x.label)} — ${esc(x.status)}</li>`).join('')}</ul></div>`;
    const enr=(p.education?.enrollments||[]).filter(x=>['active','paused'].includes(x.status));
    if(enr.length) html += `<div class="card"><div class="card-title">Training & education</div><ul class="history">${enr.map(x=>`<li>${esc(x.name)} — ${esc(x.status)}${x.teacher_name?` with ${esc(x.teacher_name)}`:''}</li>`).join('')}</ul></div>`;
    const aff=(p.religion?.affiliations||[]).filter(x=>x.status==='active');
    if(aff.length) html += `<div class="card"><div class="card-title">Religious life</div><ul class="history">${aff.map(x=>`<li>${esc(x.tradition)} — ${esc(x.affiliation_kind)}</li>`).join('')}</ul></div>`;
    if(p.travel) html += card('Travel', `${p.travel.status} • ${p.travel.destination_name || 'destination'}`, `Next review day ${p.travel.next_review_day}`);
  }
  $('ledgerBody').innerHTML=html;
  $('characterDetails').innerHTML=p?[
    p.household?card(p.household.name,'Household',p.household.role||''):'',
    ...(p.derived_motives||[]).map(x=>card(x.description,x.domain)),
    ...(p.health?.conditions||[]).filter(x=>['active','recovering','chronic'].includes(x.status)).map(x=>card(x.label,x.status)),
    ...(p.education?.enrollments||[]).filter(x=>['active','paused'].includes(x.status)).map(x=>card(x.name,x.status,x.teacher_name?`With ${x.teacher_name}`:'')),
    ...(p.religion?.affiliations||[]).filter(x=>x.status==='active').map(x=>card(x.tradition,x.affiliation_kind))
  ].join(''):'';
}
async function bootstrapCampaign(){
  if(!confirm('Bootstrap the production Caerness starting world?')) return;
  try { await api('/api/campaign/bootstrap',{method:'POST',body:'{}'}); await refresh(); } catch(e){ alert(e.message); }
}
async function createPlayer(){
  const name=$('playerName')?.value.trim(); if(!name){alert('Enter a character name.');return;}
  const start=$('playerStart')?.value.trim()||'Cairnholt'; const age=$('playerAge')?.value;
  try { await api('/api/campaign/player',{method:'POST',body:JSON.stringify({name,start_location:start,age:age||null})}); await refresh(); } catch(e){ alert(e.message); }
}
async function refresh() {
  [state,ledger,historyIndex]=await Promise.all([api('/api/state'),api('/api/ledger'),api('/api/conversations')]);
  if (planningSession && !newConversation && !state.conversations.some(x=>x.id===planningSession)) {
    try { state.conversations.push(await api(`/api/conversation/${planningSession}`)); } catch (_) { planningSession=null; }
  }
  renderState();renderLedger();
  $('input').disabled=!state.player||busy; $('send').disabled=!state.player||busy;
  $('input').placeholder=state.player?'Say something, do something, or simply stay a while…':'Choose or create your character to begin';
}
function setBusy(v) {
  busy=v;document.body.classList.toggle('busy',v);$('interrupt').classList.toggle('hidden',!v);
  $('input').disabled=v||!state?.player;$('send').disabled=v||!state?.player;
  if(v) $('playStatus').textContent='Your narrator is responding…';
  else if($('playStatus').textContent==='Your narrator is responding…') $('playStatus').textContent='';
}
function scrollLatest() { requestAnimationFrame(()=>{ $('storyScroll').scrollTop=$('storyScroll').scrollHeight; }); }
function openPanel(name) {
  currentPanel=name;
  document.body.classList.toggle('reference-closed',name==='scene');
  document.querySelectorAll('.bottomnav button').forEach(b=>{b.classList.toggle('active',b.dataset.panel===name);b.setAttribute('aria-pressed',b.dataset.panel===name);});
  document.querySelectorAll('#notebook .panel').forEach(p=>p.classList.toggle('active',p.id===name));
}
async function resumeSession(id) {
  if(busy)return;
  planningSession=id||null;newConversation=!planningSession;revisingPlan=null;
  localStorage.setItem('caernessSession',planningSession||'');
  await refresh();openPanel('scene');scrollLatest();$('input').focus();
}
function showReferral(data) {
  referral = data;
  const a = data.assessment || {};
  $('referralTitle').textContent=data.failure ? ({timeout:'The response timed out',unavailable:'Your model is unavailable',context_limit:'The conversation exceeds model context',invalid_response:'The model response was invalid',incomplete_response:'The model response was incomplete',out_of_memory:'The model ran out of memory',continuation_failed:'The continuation was interrupted',interrupted:'Conversation paused',repeated_read:'The model repeated a completed read'}[data.failure.code]||'Response interrupted') : 'A model response is needed';
  if(data.failure) $('diagnosticStatus').textContent=`Request #${data.failure.request_id} · ${data.failure.phase} · ${data.failure.code}`;
  $('referralMessage').textContent=data.reason||'Your message is saved. The configured model could not complete this response.';
  $('referralScores').innerHTML = [
    ['Reasoning', a.reasoning_score], ['Narrative', a.narrative_score], ['Local load', a.hardware_score], ['Context', a.context_tokens_estimate ? `${a.context_tokens_estimate} tok` : '—']
  ].map(([k,v])=>`<div class="score">${esc(k)}<strong>${esc(v ?? '—')}</strong></div>`).join('');
  $('referralReasons').innerHTML = (a.reasons || []).map(r=>`<li>${esc(r)}</li>`).join('');
  $('referral').classList.remove('hidden');
}
async function submit(text, forceLocal=false) {
  if (busy) return;
  setBusy(true);
  try {
    const narrative = $('playMode').value === 'narrative';
    const planning = narrative || $('playMode').value === 'planner';
    const data = await api(narrative ? '/api/narrative-play' : planning ? '/api/plan-play' : '/api/play', {method:'POST', body:JSON.stringify({text, mode:$('playMode').value, force_local:forceLocal, session_id:planningSession, plan_id:revisingPlan})});
    if (data.session_id) { planningSession = data.session_id; newConversation=false; localStorage.setItem("caernessSession",planningSession); }
    if (data.input_not_recorded) $('input').value=text;
    if (data.status === 'external_recommended') showReferral(data);
    await refresh(); scrollLatest();
  } catch (e) {
    $('input').value=text;
    $('playStatus').textContent=e.message;
  } finally { setBusy(false); }
}

$('composer').addEventListener('submit', async e => {
  e.preventDefault();
  const text = $('input').value.trim();
  if (!text) return;
  $('input').value = '';
  await submit(text);
});
$('input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!busy&&$('input').value.trim())$('composer').requestSubmit();}});
$('interrupt').addEventListener('click', async () => { try { await api('/api/interrupt',{method:'POST',body:'{}'});$('playStatus').textContent='Pause requested. The current model call may need to finish; confirmed actions are saved.'; } catch(e) {} });
$('closeReferral').addEventListener('click', ()=> $('referral').classList.add('hidden'));
$('runLocalAnyway').addEventListener('click', async ()=> {
  if (!referral) return;
  $('referral').classList.add('hidden');
  setBusy(true);
  try {
    const data = await api(referral.failure ? '/api/narrative-retry' : `/api/model/${referral.request_id}/local`, {method:'POST', body:JSON.stringify({request_id:referral.request_id,force:true, apply:true})});
    if (data.status === 'external_recommended') showReferral(data);
    await refresh();
  } catch(e) { alert(e.message); }
  finally { setBusy(false); }
});
async function copyPacket(which) {
  if (!referral || !referral[which]) return;
  await navigator.clipboard.writeText(referral[which].packet || '');
  alert(`${which === 'chatgpt' ? 'ChatGPT' : 'Claude'} packet copied.`);
}
$('copyChatGPT').addEventListener('click', ()=>copyPacket('chatgpt'));
$('copyClaude').addEventListener('click', ()=>copyPacket('claude'));

$('importExternal').addEventListener('click', async ()=> {
  if (!referral) return;
  try {
    const response = await navigator.clipboard.readText();
    if (!response.trim()) { alert('Clipboard is empty.'); return; }
    $('referral').classList.add('hidden');
    setBusy(true);
    const data = await api(`/api/model/${referral.request_id}/import`, {method:'POST', body:JSON.stringify({response, apply:true, auto_continue:true})});
    if (data.followup && data.followup.status === 'external_recommended') showReferral(data.followup);
    await refresh();
  } catch(e) { alert(e.message); }
  finally { setBusy(false); }
});

document.querySelectorAll('.bottomnav button').forEach(b=>b.addEventListener('click',()=>openPanel(b.dataset.panel)));
document.querySelectorAll('.subtabs button').forEach(b => b.addEventListener('click', ()=> {
  worldTab=b.dataset.worldtab;
  document.querySelectorAll('.subtabs button').forEach(x=>x.classList.toggle('active',x===b));
  renderWorld();
}));

refresh().catch(e => $('worldline').textContent=e.message);

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});

$('conversationPicker').addEventListener('change',e=>resumeSession(Number(e.target.value)));
$('modelSetup').addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/runtime',{method:'POST',body:JSON.stringify({local_backend:'openai_compatible',local_endpoint:$('modelEndpoint').value,local_model:$('modelName').value,local_heavy_context_tokens:Number($('modelContext').value),local_max_context_tokens:Math.min(6000,Number($('modelContext').value)),local_max_output_tokens:Number($('modelOutput').value)})});$('modelStatus').textContent='Model settings saved. Credentials remain in the server environment.';await refresh();}catch(e){$('modelStatus').textContent=e.message;}});
$('testModel').addEventListener('click',async()=>{try{const h=await api('/api/local-health');$('modelStatus').textContent=h.ok?'Endpoint available. Start a conversation to test this model.':h.error||h.status;}catch(e){$('modelStatus').textContent=e.message;}});

$('copyDiagnostics').addEventListener('click',async()=>{try{$('diagnosticStatus').textContent='Collecting non-secret hardware and request diagnostics…';const report=await api('/api/diagnostics?hardware=1');const text=JSON.stringify(report,null,2);$('diagnosticStatus').textContent=text;await navigator.clipboard.writeText(text);$('playStatus').textContent='Diagnostics copied. No dialogue, credentials or world facts included.';}catch(e){$('playStatus').textContent=e.message;}});
$('retryNarrative').addEventListener('click',async()=>{if(busy)return;setBusy(true);try{const report=await api('/api/diagnostics'+(planningSession?'?session_id='+Number(planningSession):''));const pending=report.requests.find(r=>r.retryable);if(!pending)throw new Error('There is no unfinished response to retry.');const data=await api('/api/narrative-retry',{method:'POST',body:JSON.stringify({request_id:pending.request_id})});if(data.session_id){planningSession=data.session_id;localStorage.setItem('caernessSession',planningSession);}if(data.status==='external_recommended')showReferral(data);else{$('referral').classList.add('hidden');$('diagnosticStatus').textContent='Unfinished response completed. Earlier actions were not replayed.';}await refresh();scrollLatest();}catch(e){$('playStatus').textContent=e.message;}finally{setBusy(false);}});

openPanel('scene');
$('closeNotebook').addEventListener('click',()=>{openPanel('scene');$('input').focus();});
$('focusInput').addEventListener('click',()=>{openPanel('scene');$('input').focus();});
$('latest').addEventListener('click',scrollLatest);
$('settingsButton').addEventListener('click',()=>$('settingsDialog').showModal());
$('closeSettings').addEventListener('click',()=>$('settingsDialog').close());
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openPanel('scene');$('input').focus();}
  if(e.key==='Escape'){ $('referral').classList.add('hidden');openPanel('scene'); }
  if(e.altKey&&['1','2','3','4','5'].includes(e.key)){e.preventDefault();openPanel(['scene','world','matters','history','you'][Number(e.key)-1]);}
});
$('readingSize').value=localStorage.getItem('caernessReadingSize')||'standard';
function applyReadingSize(){document.documentElement.style.setProperty('--reading-size',$('readingSize').value==='large'?'23px':'');localStorage.setItem('caernessReadingSize',$('readingSize').value);}
$('readingSize').addEventListener('change',applyReadingSize);applyReadingSize();
let characterTimer;
document.addEventListener('input',e=>{if(e.target.id==='characterSearch'){clearTimeout(characterTimer);characterTimer=setTimeout(async()=>{try{const rows=await api('/api/campaign/characters?query='+encodeURIComponent(e.target.value));$('characterChoices').innerHTML=rows.map(x=>`<div class="card"><b>${esc(x.name)}</b><div class="meta">${esc(x.location||'Unknown place')} · ${esc(x.role||'')}</div><button data-select-character="${x.id}">Inhabit this character</button></div>`).join('');}catch(error){$('characterChoices').textContent=error.message;}},250);}});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-select-character]');if(b){try{await api('/api/campaign/select',{method:'POST',body:JSON.stringify({actor_id:Number(b.dataset.selectCharacter)})});planningSession=null;newConversation=true;await refresh();$('input').focus();}catch(error){alert(error.message);}}});
