# Narrative play: integration ready, live gameplay not yet demonstrated

The phone interface now opens in narrative play. Conversations remain in the save,
earlier exchanges can be retrieved, NPC context is refreshed, and ordinary dialogue
does not automatically change relationships or pass days. A clear short journey or
rest can execute through verified engine operations without a second click. Major
commitments still show a readable scope in the scene before proceeding.

**The actual model service was unavailable.** The twenty-turn HTTP/browser tests use
explicitly labelled stubs. They prove persistence and the interface, not believable
characters or literary quality. The real inference attempt and A–D gate status are
recorded in [live-evaluation.json](live-evaluation.json). No actual model transcript
exists from this environment; one has not been replaced with invented prose.

## Connect and play

From this branch's checkout, with the existing Python/numpy setup:

```sh
python tools/narrative_play.py --configure
```

The launcher asks for the endpoint and available model name, then requests the API
key with a hidden prompt. The key stays in the running process; it is not saved or
sent to the browser. Use a provider account/API key with access to the selected model.
An ordinary ChatGPT subscription does not itself supply API credentials. The suggested
OpenAI chat-completions endpoint/model is a configuration example, not a tested account.
Other compatible HTTPS services and unauthenticated loopback servers use the same
adapter. API cost and model access belong to that configured service.

Open **http://127.0.0.1:8765** on the device running Caerness. Create your character in
Ledger if needed. Say what you want to do or simply talk. Scene contains saved
conversation selection and a New conversation button. You contains endpoint/model
settings and a connection check. That check establishes reachability, not model quality.
The default save is `game/narrative-session.db`, copied from the opening once and
reused on future launches. Closing the game never advances story time.

Managed installations can instead provide `CAERNESS_MODEL_ENDPOINT`,
`CAERNESS_MODEL_NAME` and `CAERNESS_MODEL_API_KEY` (or `OPENAI_API_KEY`) in the runtime
environment. Never paste a key into gameplay, a public PR or a URL. The existing
manual ChatGPT/Claude export/import route remains available as a slower alternative.

## Run the live acceptance gate

With the model connected through those environment settings:

```sh
python tools/evaluate_narrative.py --out runs/my-live-evaluation --approve-reviewed
```

This uses a fresh copy and existing established people. It sends plain player
inputs and records the model's actual choices, tools, prose, allowed/refused effects,
state and reload. `--approve-reviewed` is an explicit test-player approval of complete
displayed scopes; unresolved scopes are never automatically approved. Specify
`--player`/`--npc` to select a different existing co-located pair. Use a fresh output
folder for each attempt. The resulting transcript needs qualitative review and
state verification; the recorder does not declare prose enjoyable.

## Evidence and limitations

- [Architecture, authority policy, contextual retrieval and precise gaps](../../plans/2026-10-12-narrative-runtime.md)
- [Phone conversation after reload](conversation-reload.png) — explicitly scripted transport responses.
- [Phone model configuration](model-setup.png)
- [Integration, regression, latency and benchmark evidence](verification.json)

No real-model performance, rich prose, eighteen-year autobiographical continuity,
full spy networks or operating schools are claimed. Unknown history stays unknown;
new enduring facts and promises need supported world operations. The initial automatic
policy covers only short time/travel, not routine spending or appointments. These
limits and the blocked live-model gate are part of the delivery, not hidden success claims.
