# Desktop narrative play — scope, evidence and remaining gate

This branch starts at the latest PR #5 (`0409086`) and preserves PR #4 and PR #3.
It implements the owner's 13 October direction and PR #5 review: desktop/laptop
narrative play first, mobile compatibility through the same client, capable model
quality over phone-local constraints, and 3D postponed indefinitely until text play
is enjoyable. AGENTS, README, DESIGN and POST_V07 now make that direction explicit.
Historical performance reports/Android tooling remain evidence, not product gates.

The Python/SQLite simulation, World Bible, canonical opening, general capabilities,
NPC consent and narrative gateway are retained. No specialised intention handlers,
population work, general simulation expansion or new model abstraction were added.

## The reading experience

The existing HTML/CSS/JS client now has a restrained ink/forest/brass palette,
comfortable serif prose, bounded line lengths, generous space and a separate input
surface. At desktop width the story and input remain visible while a notebook can
show people, places, knowledge, commitments, history or character information. The
notebook overlays only on smaller screens. Both use the same DOM, APIs and simulation.
The file/module names `mobile/` and `mobile_server.py` remain for compatibility.

Player intentions have their own labelled style. Quoted passages can be styled as
speech; the renderer never infers a speaker or creates a fact. It escapes all model
text before markup, supports paragraph breaks and leaves mixed narrative/dialogue
intact. No new literary-response schema or hard-coded writing/topic handler was
introduced. The model is still responsible for the prose.

Enter sends, Shift+Enter inserts a line, Ctrl+K focuses input, Alt+1–5 opens references,
and Escape returns to the story. Text size is adjustable. Reference switching does
not rebuild the transcript or deliberately scroll it. Saved session rendering avoids
appending the legacy turn journal in front of the same conversation. Older sessions
can be retrieved beyond the five most recently returned by the existing state API;
indexes and fetched transcripts are checked against the current camera owner.
Significant terms and omissions remain in a human-readable inline decision card;
technical operation graphs are not the main play flow. Automatic authorization policy
and engine validation are unchanged from PR #5. Reading settings, endpoint fields,
legacy modes and diagnostics are in a separate settings dialog, not the composer.

Character creation is reachable in the story on first launch. Existing living
characters can be selected using their public name/role/place labels during setup;
this roster is unavailable as in-world knowledge after a character is configured.
The selection uses the existing player-setting function and cannot manufacture a
history. A repeat selection is refused. The packaged opening's legacy bootstrap and
is_canon flags were found unset despite populated people/places; the UI now checks
actual available locations and characters rather than requiring a destructive reseed.
It does not mark or rewrite canon to make the setup screen work.

## Windows and model access

`Play Caerness.cmd` creates/reuses a local Python environment, installs the existing
NumPy dependency if needed and launches the existing narrative tool. The copy-safe
launcher can open the default desktop browser after the local server is listening.
The current model adapter is unchanged. Remote credentials stay in environment or
a hidden terminal prompt; endpoint/model names are nonsecret settings. The browser
receives no API credential, and the database receives no API credential. Managed
credentials can supply CAERNESS_MODEL_ENDPOINT/NAME/API_KEY or OPENAI_API_KEY.
[Windows instructions](../../WINDOWS_PLAY.md) identify the exact external requirement
and explain setup without requiring the owner to write code.

Windows native execution has not been tested on this Linux host. The command file's
paths/flow, Python launcher, isolated save and actual browser/server interaction are
reviewed/validated as applicable; this is not a claim of a Windows-device acceptance.

## Live model gate: blocked

Fresh managed-runtime observations show no secret bindings, model variables or
outbound identities. Environment API credentials and endpoint/model overrides are
absent. The default `local-model` service at 127.0.0.1:8080 is not reachable. An actual
runtime inference was attempted through PR #5's existing evaluation recorder; it
returned no model reply. Ordinary life, 20-turn conversation, unfamiliar consequential
instruction and undertaking/time-return acceptance remain **BLOCKED**.

The missing access is precise: a reachable compatible model service and its enabled
model name, with a valid API credential where required (and account billing/credits).
A locally running capable server can alternatively supply that access. A normal
ChatGPT subscription and Codex's own intelligence do not connect the game. We did not
produce another scripted gameplay demonstration, fabricate a transcript or add
architecture to compensate for missing access.

The screenshots use clearly labelled excerpts from the actual authored World Bible
as **reading-layout fixtures**, not simulated AI dialogue or confirmed gameplay.
The UI harness checks keyboard, character setup, history, safe formatting, incomplete
scope rendering, viewport overflow and a real unavailable-model submission. It does
not supply an AI response. Existing scripted tests are rerun as regression safeguards
only. The new API test verifies setup fields, repeat/invalid selection denial,
old-session access and camera ownership.

## Assessment and performance

The interface removes real friction: desktop space is used for story/reference,
settings are separate, input is keyboard-friendly, existing character setup is
accessible, and older conversations remain reachable. These are interaction outcomes,
not evidence of literary quality. Character nuance, emotion, pacing, rich prose,
semantic understanding and unfamiliar plans still need a capable runtime model and
unscripted/human evaluation. Current bounded NPC context cannot fabricate decades of
biography; private disclosures/biography anchors and other missing general operations
remain PR #5 limitations. Routine budgets/appointments still use one review; this
branch does not loosen world integrity without live-model evidence.

Fresh isolated 1/7/90-day simulation benchmarks are recorded separately from model
latency. Model generation latency is unavailable because no model responded. Browser
and API timings measure interface/retrieval overhead only. PR #5's four-active-plan,
initial/three-year and repeated late-skip benchmark remains relevant because planning
and scheduling were not changed; no new background process or repeated model task
was introduced. Cloud measurements are neither Windows-hardware nor phone benchmarks.

See [desktop evidence and screenshots](../demos/desktop-narrative/README.md) for actual
results and limitations. Nothing is merged automatically. A comfortable reader and
a working configuration path are delivered; an enjoyable AI RPG is **not declared
complete** until the real gameplay gate passes.
