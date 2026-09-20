let state = null;
let referral = null;
let worldTab = 'people';
let controller = null;
let ledger = null;

const $ = (id) => document.getElementById(id);
function esc(v='') { return String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function api(path, options={}) {
  const res = await fetch(path, {headers:{'Content-Type':'application/json'}, ...options});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function renderState() {
  if (!state) return;
  const p = state.player;
  $('worldline').textContent = p ? `Day ${state.world.day} • ${p.location || 'Unknown'} • ${p.name}` : `Day ${state.world.day} • No player configured`;
  const turns = state.turns || [];
  $('emptyScene').classList.toggle('hidden', turns.length > 0);
  $('transcript').innerHTML = turns.map(t => `
    <article class="turn">
      <div class="daytag">Day ${t.day_started}${t.day_ended !== t.day_started ? `–${t.day_ended}`:''}</div>
      <div class="player-line">${esc(t.raw_input)}</div>
      <div class="narration">${esc(t.narration_text || '')}</div>
    </article>`).join('');

  $('attention').innerHTML = (state.attention || []).slice(0,5).map(c => `
    <div class="attention-card ${esc(c.cue_type)}">${esc(c.text)}</div>`).join('');

  const m = state.matters || {intentions:[], obligations:[]};
  $('mattersBody').innerHTML = [
    ...(m.obligations || []).map(o => card(o.description, o.due_day == null ? 'No fixed date' : `Due day ${o.due_day}`, o.notes)),
    ...(m.intentions || []).map(i => card(i.description, `${i.status}${i.target_actor_name ? ` • ${i.target_actor_name}`:''}${i.target_location_name ? ` • ${i.target_location_name}`:''}`, i.possession_name || ''))
  ].join('') || '<p class="muted">Nothing currently needs carrying in your head.</p>';

  renderWorld();
  $('youBody').innerHTML = p ? card(p.name, p.location || '', 'The interface shows what this character knows or is carrying forward, not hidden world truth.') : '<p class="muted">No player configured.</p>';
  const r = state.runtime || {};
  $('runtimeBody').innerHTML = `<div class="meta">${esc(r.device_profile || '')}<br>${esc(r.local_backend || '')} • ${esc(r.local_model || '')}<br>Story time only: ${r.story_time_only ? 'yes' : 'no'}<br>Referral: ${esc(r.referral_sensitivity || '')}</div>`;
}
function card(title, meta='', body='') {
  return `<div class="card"><div class="card-title">${esc(title)}</div>${meta?`<div class="meta">${esc(meta)}</div>`:''}${body?`<div>${esc(body)}</div>`:''}</div>`;
}
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
  if (!ss.bootstrap_complete) {
    $('setupBody').innerHTML = `<div class="card"><div class="card-title">Set up Caerness</div><div class="meta">Load the versioned World-Bible-derived starting world. Open geography/calendar questions remain unseeded.</div><div class="setup-actions"><button id="bootstrapCampaign">Bootstrap Caerness</button></div></div>`;
    setTimeout(()=>{ const b=$('bootstrapCampaign'); if(b) b.onclick=bootstrapCampaign; },0);
  } else if (!ss.player_setup_complete) {
    $('setupBody').innerHTML = `<div class="card"><div class="card-title">Create your character</div><div class="meta">The world is seeded. Player identity is never invented by the bootstrap.</div><div class="setup-actions"><input id="playerName" placeholder="Character name"><input id="playerStart" value="Cairnholt" placeholder="Start location"><input id="playerAge" type="number" min="0" max="200" placeholder="Age (optional)"><button id="createPlayer">Create player character</button></div></div>`;
    setTimeout(()=>{ const b=$('createPlayer'); if(b) b.onclick=createPlayer; },0);
  } else { $('setupBody').innerHTML=''; }
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
  [state,ledger] = await Promise.all([api('/api/state'),api('/api/ledger')]);
  renderState(); renderLedger();
  const hasPlayer=!!state.player; $('input').disabled=!hasPlayer; $('send').disabled=!hasPlayer;
  $('input').placeholder=hasPlayer?'What do you do?':'Set up your campaign in Ledger first';
}
function setBusy(v) {
  document.body.classList.toggle('busy', v);
  $('interrupt').classList.toggle('hidden', !v);
  $('input').disabled = v;
}
function showReferral(data) {
  referral = data;
  const a = data.assessment || {};
  $('referralTitle').textContent = a.recommendation === 'external_strongly_recommended' ? 'A stronger model is strongly recommended here.' : 'ChatGPT or Claude would likely improve this section.';
  $('referralScores').innerHTML = [
    ['Reasoning', a.reasoning_score], ['Narrative', a.narrative_score], ['Phone load', a.hardware_score], ['Context', a.context_tokens_estimate ? `${a.context_tokens_estimate} tok` : '—']
  ].map(([k,v])=>`<div class="score">${esc(k)}<strong>${esc(v ?? '—')}</strong></div>`).join('');
  $('referralReasons').innerHTML = (a.reasons || []).map(r=>`<li>${esc(r)}</li>`).join('');
  $('referral').classList.remove('hidden');
}
async function submit(text, forceLocal=false) {
  setBusy(true);
  try {
    const data = await api('/api/play', {method:'POST', body:JSON.stringify({text, mode:'auto', force_local:forceLocal})});
    if (data.status === 'external_recommended') showReferral(data);
    await refresh();
  } catch (e) {
    alert(e.message);
  } finally { setBusy(false); }
}

$('composer').addEventListener('submit', async e => {
  e.preventDefault();
  const text = $('input').value.trim();
  if (!text) return;
  $('input').value = '';
  await submit(text);
});
$('input').addEventListener('input', e => { e.target.style.height='44px'; e.target.style.height=Math.min(144,e.target.scrollHeight)+'px'; });
$('interrupt').addEventListener('click', async () => { try { await api('/api/interrupt',{method:'POST',body:'{}'}); } catch(e) {} });
$('closeReferral').addEventListener('click', ()=> $('referral').classList.add('hidden'));
$('runLocalAnyway').addEventListener('click', async ()=> {
  if (!referral) return;
  $('referral').classList.add('hidden');
  setBusy(true);
  try {
    const data = await api(`/api/model/${referral.request_id}/local`, {method:'POST', body:JSON.stringify({force:true, apply:true})});
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

document.querySelectorAll('.bottomnav button').forEach(b => b.addEventListener('click', ()=> {
  document.querySelectorAll('.bottomnav button').forEach(x=>x.classList.toggle('active',x===b));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id===b.dataset.panel));
}));
document.querySelectorAll('.subtabs button').forEach(b => b.addEventListener('click', ()=> {
  worldTab=b.dataset.worldtab;
  document.querySelectorAll('.subtabs button').forEach(x=>x.classList.toggle('active',x===b));
  renderWorld();
}));

refresh().catch(e => $('worldline').textContent=e.message);

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
