# Creative campaign authorship — owner clarification implemented

The [latest owner clarification on PR #7](https://github.com/ferreiracade-dotcom/Caerness/pull/7#pullrequestreview-5501018499)
supersedes the earlier blanket prohibition. The World Bible is a foundation, not
an exhaustive roster, biography or history. Compatible invention is permitted,
including genuinely important new people and institutions. Missing records are
not proof something never happened. Campaign additions do not rewrite setting canon.

## What actually works now

- **Natural expression:** gestures, tone, incidental atmosphere and ordinary anecdotes
  can appear directly in conversation. No acceptance roll, player confirmation or
  database record for every sentence is required. Existing transcripts preserve dialogue.
- **Attributed memories and rumours:** `discuss` can optionally carry small continuity
  details alongside prose. The engine stores the speaker, observer, date and uncertain
  status. Petra can remember an undocumented winter morning without proving an event
  already exists. The remembered account remains available across reloads and new
  conversations; it is not silently promoted to objective history.
- **Previously undescribed objective history:** `author` proposes a bounded batch of
  biography, ordinary work, acquaintances, local customs/history or circumstances.
  The engine freezes constraints; a separate model call checks consistency and causal
  plausibility. Engine validation then commits stable historical anchors and observer-
  scoped details. Same-key objective facts cannot silently be rewritten. Different-key
  prose contradictions additionally depend on semantic review.
- **Entirely new significant identities:** independent people and institutions can be
  introduced without an opening name or pre-existing latent entry. The adapter creates
  a tracking latent descriptor when necessary and reuses the existing resolution/
  materialization and institution-candidate mechanisms. People receive ordinary life,
  health, presence, embodiment, cultivation and simulation profiles. Institutions get
  native profiles, NPC leadership and memberships. Both receive native independent
  goals and TRACKED resolution; they can continue through existing world processes.
- **Work/acquaintance integration:** reviewed work facts can establish ordinary membership
  in an actual institution. Reviewed acquaintances create neutral directional relationship
  records with limited familiarity, not guaranteed loyalty or consent. New schools/guilds
  can have durable identity and leadership before their operational capacity is developed.

The interface remains a conversation. These are internal model protocols, not commands
such as “spawn a school” that the player must learn. The same mechanism handles
biographical disclosure and new institutions; no request-specific parser was added.

## How it fits the existing architecture

POST_V07 §§18.5, 19–20 and 34–35 already describe progressive depth, historical
anchors, compressed connective tissue and life beyond the initial seed. The original
`crystallization.py` route validates latent **new-person** proposals; it does not
supply a conversation-level mechanism for existing named people or arbitrary new
institutional identities. Its older requirement for persisted connection bases remains
appropriate for that route, not a universal ban on compatible new material.

The focused adapter is `engine/narrative_authoring.py`. It reuses continuity cores,
historical anchors, latent materialization, institution candidates, memberships,
relationships, goals and resolution profiles. Small new runtime tables retain
proposal/review/digest/provenance and epistemically labelled detail observations.
They are created on campaign saves, without changing the opening or World Bible.

For objective additions:

`proposal → frozen world constraints + relevant canon → independent consistency review → engine recheck → transactional native commit → narrator feedback`

The private verification envelope includes saved identities, life dates, kinship,
careers, anchors and relevant state. It is not placed in player-facing character
context. Rejected feedback does not disclose private constraint details. Changes
while review is pending invalidate the snapshot. A failed institutional formation
rolls back the entire batch, including its new people. Narration receives successful
identity IDs/details only after commit. Runtime results separately report campaign
additions, including when a later model call fails.

Knowledge remains scoped: objective additions and subjective accounts have distinct
labels; only observers receive those details. A `person` lookup includes known authored
continuity, and `authoring_details` supports scoped search/paging across conversations.
New public identity backgrounds persist; private independent goals are not exposed by
that lookup. As-of/observed dates matter after time skips; an old employment account
is not a guarantee that someone never changes work.

## What this does not shortcut

The mechanism cannot directly set money, possessions, troops, cultivation Stage,
player command, family identity, NPC consent, agreements, victory or completed work.
Those continue through existing domain validation. An affiliation text containing
“head master” does not grant command; only validated leadership of a new independent
institution is installed, with an NPC head rather than the player. Institutions gain
no fabricated treasury, property or fighting force. Native merchant-house formation
requirements are retained rather than bypassed with a generic history claim.

Anti-convenience is contextual: independent circumstances and consistency are checked,
but an important new person/opportunity is not rejected merely because it matters or
could eventually help. Player requests still require real means, consent and time.
Authorship review is automatic engine review, not another player approval ceremony.
Major player commitments retain the existing scope review.

## Deliberate first-implementation limits

- New persistent identities are initially introduced at the current established location.
  Distant, previously undescribed people can still occur in attributed recollections;
  remote identity crystallization needs an appropriate disclosure/location interface.
- Newly materialized people use ordinary baseline native profiles. Extraordinary mastery,
  extensive assets, troops, full kinship/family changes, formal political sovereignty,
  new physical locations and elaborate institutional operations need their respective
  domain integrations. Their concepts are **permitted**, not universally banned;
  this adapter cannot yet establish all those mechanical structures.
- Descriptive work/biography is not an instant functioning enterprise or training service.
  Property, equipment, finances, competence and delivery still need validated means.
- Semantic compatibility with free-text canon/history relies partly on the configured
  model's independent review and retrieved context. It is not a formal proof that all
  possible prose contradictions are detected. Deterministic guards prevent direct typed
  state overwrites, and stable facts cannot be silently replaced.
- Ordinary prose is not automatically extracted into objective truth. The narrator must
  promote consequential material before relying on it for outcomes. A model that fails
  to use this protocol remains an acceptance issue, not permission to prohibit creativity.

## Tests and playtest readiness

`tests/narrative_authoring_test.py` exercises the actual runtime with clearly stubbed
model replies: permissible recollection without extra review, disposable expression,
new significant instructor/school/work, independent native goals/profiles, observer
scope, reload and time passage, existing-family contradictions, same-key overwrite,
pre-birth history, stale review, disguised resources/player authority and atomic
rollback of a failed native institution. Existing narrative/planning/crystallization
regressions are retained. Test records are in `docs/evidence/narrative-authoring/`.

The **policy and initial persistence path are ready for a controlled owner-side Windows
local-AI playtest**. They are not proof the game is enjoyable or that a model will
use every tool correctly. The new authorship protocol has not undergone a genuine
larger-model twenty-turn evaluation here; the automated model replies are stubs.
Windows/GPU launch and Qwen3.5 9B versus Gemma 4 12B comparison remain owner-side gates.

The earlier winter and school passages must be re-evaluated under this policy: a winter
recollection is permissible, and school duties can be a valid claim or a reviewed
occupation. Mere undocumented invention is not a failure. Earlier timing, repetitive/
awkward prose and reluctance to inspect remain relevant observations. Raw prior
transcripts are preserved, and the old evidence report now carries this correction.

Download the updated PR #7 branch and follow `WINDOWS_PLAY.md`. Try a recollection,
ask about previously undescribed work, meet a new person/institution and return after
time passes. Check that significant details recur consistently and that the game
neither forces administrative approvals nor invents instant player success. No coding
or paid-model account is needed for that playtest.
