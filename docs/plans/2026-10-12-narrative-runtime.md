# Narrative runtime and the remaining live-model gate

This branch extends PR #4 (including `80c3e0f`) and preserves PR #3's corrections.
It follows AGENTS, DESIGN's authority/knowledge/turn rules, POST_V07's narrative,
continuity and delegation sections, PR #1's audit and owner clarification, and the
World Bible's cultural formality and distinction between imperial authority and
martial standing. No canon, opening, fortune probabilities or background simulation
policy was changed. Unreal is deferred.

## The experience gap addressed

PR #4's default play stopped every plan for digest review, passed a large scene and
full capability schemas on every exchange, and retained only the last 24 records
in the prompt. It supported discussion but not persistent retrieved interlocutor
context. The existing model adapter had no authentication for a hosted endpoint;
the local quality router could send a capable configured remote model back to a
manual packet. Execution narration was usually an offline template or a separately
queued request rather than the next scene in the same conversation.

Narrative play is now the default phone mode. A model can speak naturally, inspect
actual present people, resume a conversation, retrieve earlier source exchanges,
compose the same general plans, and narrate confirmed consequences in that same
conversation. Temporary dialogue is saved as **unverified speech**, not world truth.
No conversation acceptance roll, relationship delta or clock advance follows from
a discussion response. Plan review mode and existing/offline play remain available.

## Model connection

The existing OpenAI-compatible chat-completions adapter is reused, rather than
introducing provider-specific execution paths. `CAERNESS_MODEL_ENDPOINT` and
`CAERNESS_MODEL_NAME` override nonsecret save settings. `CAERNESS_MODEL_API_KEY` or
`OPENAI_API_KEY` supplies the bearer credential in memory. Keys are never placed in
SQLite, browser settings, exported packets, logs or committed files. Remote requests
require HTTPS, reject credentials/query strings embedded in URLs, preserve inherited
proxy/CA behavior, refuse redirects, and return sanitized service errors. HTTP on
loopback remains supported for local servers and test doubles. A recognized remote
endpoint bypasses **local hardware** referral gating, not world validation.

Every actual response still enters the persisted request/import/validation boundary.
Model call latency and token usage are stored separately from simulation timings.
The launcher creates/reuses a separate campaign save and refuses the canonical path.
A hidden-key configuration prompt and the phone's endpoint/model settings provide
simple setup. Health checks are connectivity evidence, never reasoning acceptance.

## Conversation and knowledge

Existing `ai_sessions` retain the exact transcript and ownership. Optional additive
`narrative_participants` remembers people actually inspected in that session. Their
fresh dossiers are attached on later turns; an absent former interlocutor is marked
unavailable, never made to answer remotely. NPC tools expose present identity,
expressive profile, coarse response cues, shared known events and shared institutional
affiliations. They do not expose secret goals, inventories, medical diagnoses,
private event history or an invented eighteen-year biography. Unknown is not none.

The prompt contains early anchors and 32 recent records. Search/page tools retrieve
older exact excerpts on demand; this avoids lossy model summaries becoming history.
The transcript retains source days, roles and indices. Tool dumps are omitted from
routine repeated memory; stored interlocutors and fresh world context supply relevant
facts. Recent events, rumours, culture, environment, nearby established routes,
player embodiment and two canon chunks replace an unrestricted database dump.
People discovery can find an actually present person outside the first scene list.
Full capability argument schemas are discoverable on demand. Ordinary turns receive
names/descriptions, not a repeated technical schema catalogue.

This is bounded retrieval, **not perfect semantic memory**. Older details can still
be missed if the model does not retrieve them. A speaker's recollection, rumour or
previous assistant statement does not prove a permanent fact. New private disclosures,
biographical anchors and contracts require appropriate domain adapters; prose cannot
create them. Mutual history retrieval is deliberately narrower than unrestricted
NPC self-knowledge.

## Conversational authorization

The planner still cannot call arbitrary Python or SQL, authorize its own graph, or
report world success without engine feedback. Each proposed narrative plan receives
a separate persisted scope-verification request. It receives the original instruction,
source-handling excerpts, conversation and **engine-authored effects**, rather than
trusting the planner's summary. The verifier must identify current directive spans,
match all conditions, and disclose omissions or altered terms.

The engine's initial automatic policy is deliberately small: complete, independently
verified directives containing only established adjacent travel or time advancement,
with no more than seven cumulative world days. It creates the same digest-pinned
approval and records the original source/evidence and policy. There is no language
keyword recognizer. All budgets, role/service offers, proposal answers, durable
obligations, long skips and unknown capabilities require review. This is a first
risk policy, not a universal measure of gameplay stakes; routine funded delegation
still needs one readable scope review. Significant review appears in Scene as well
as Matters, so it does not require managing a technical plan dashboard.

A fully source-covered plan can still be semantically incomplete. The negative test
marks the entire horse-gift-plus-wait request as `context`, so the original syntactic
checker accepts it. The independent verifier reports the omitted horse; the engine
blocks automatic **and direct** approval until revision. Non-executed source spans
and semantic omissions are prominent in the phone review. Verifier disagreement,
uncertain intent and incomplete scope never execute. The second call reduces risk;
it does **not mathematically prove semantic completeness** and is itself subject to
model error. Live adversarial testing and policy calibration remain acceptance work.

Approved operations retain PR #4's transactional commits, consent/refusal, resources,
immutable committed prefixes and native progress. Their real results are returned to
the same narrator before further prose. If that model call fails, the confirmed
outcomes and pending narration remain saved. Review/import/force-local continuations
use the same bounded protocol. A legitimate accepted work engagement can be
commissioned after its commander leaves, using exactly its accepted quote and a
worker actually at the suitable site. New contact and different work are not invented.

## Evaluation and current outcome

The managed runtime reports no secrets, runtime model variables or outbound identities.
The configured `local-model` endpoint at `127.0.0.1:8080` fails both connectivity and
an actual inference attempt. No hosted provider account or runtime credential was
available. **Actual gameplay A–D and literary quality remain BLOCKED.** Codex's own
reasoning, fake HTTP outputs and browser screenshots do not cross that gate.

`tools/evaluate_narrative.py` selects actual co-located people with an established
relationship from an opening copy. Its player inputs are plain language, never
pretranslated plans; the runtime model must choose all tools/operations. It records
20 conversation exchanges and the unfamiliar instruction/time-return/ordinary-play
inputs, every model request/reply, inspection, engine outcome, pre/post state and
separate latency, then checks reload. Optional test-player review explicitly records
what scope was approved. The available attempt selected Robert Baird and Petra Fenn
with their existing history; no response was fabricated. The evidence marks all four
gates blocked. The harness records evidence for qualitative review, not automatic
"enjoyable game" pass/fail. Meaningful ongoing-work acceptance additionally needs a
feasible commitment in that save; a refusal or an unavailable adapter is not evidence
of ongoing success.

Reproducible HTTP tests cover 20 scripted exchanges, present character retrieval,
old-memory search, reload, no social/time effects, explicit/hypothetical distinctions,
fully-covered-but-incomplete interpretation, direct-approval bypass prevention,
major commitment review, native travel and post-state narration. Authority tests
cover remote selection, secret exclusion, HTTPS, safe errors, no redirects and
accepted delegation without commander presence. Existing regression tests protect
the original simulation. See the demonstration folder for exact run evidence.

Four long-running native projects have paired benchmark copies with and without
active AI tracking, from day 0 and a simulated three-year save, for 90/365 days.
Their daily prerequisite/plan checks are profiled separately. All four remain active,
so this is not an empty-world or already-completed-plan benchmark. These are explicit
performance fixtures, not model intelligence. Measurements include profiler overhead,
one cloud machine and run-to-run noise; they are not OnePlus 12 results. A noisy older
90-day pair was repeated separately after the full suite. The repeated older 90-day
pairs measured 12.329/12.806s and 13.596/12.888s (without/with tracking), while
planning itself took 0.065–0.066s. Sampled native actor state, event history and
project progress fingerprints were identical across both pairs. This gives no
evidence of a significant planning regression warranting a scheduler rewrite;
full world simulation remains the main time-skip cost. No costly background language-model process was introduced.

## Acceptance still needed

Connect a capable runtime model and complete A–D with fresh player inputs, then
review full transcripts for character coherence, appropriately situated knowledge,
repetition, pacing, unsupported claims, semantic omissions and administrative friction.
Correct specific failures with reusable retrieval/protocol changes. Human literary
review remains essential. In particular, the richer instructions here have not been
shown to produce good prose on any actual model.

Existing engine gaps remain: legal institutional formation, acquisition/leases,
remote contact, recruitment, payments/gifts/recurring finance, negotiated new quotes,
private information disclosure, robust biography/relationship anchors, actual report
substance, educational programs, paused-work recovery and deeper independent NPC
narrative initiative. Travel currently exposes adjacent established routes; rest
advances native time rather than granting invented supplies or guaranteed recovery.
Mild investigation can inspect accessible facts, not manufacture clues or events.
The engine still has whole-day time and SQLite's existing single-writer behavior;
long model requests may delay concurrent administrative writes. Streaming and voice
are not implemented. Context retrieval and authorization need real-model calibration.

This delivers a reviewable connected-model narrative **integration**. It does not
claim that Caerness now achieves the owner's original freedom or narrative richness.
