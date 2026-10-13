# Local AI evidence and acceptance status

**The integration has produced genuine local replies. The narrative RPG is not
accepted, and no model is claimed to be the best Caerness narrator.**

Research/implementation date: 13 October 2026. Base PR #6 latest corrections,
`a9ec492ca26716fb2da6deeefffffb9176fba368`. The owner explicitly approved only the
smaller diagnostic model download on this host. No paid inference service was used.

## Actual runtime and model

Ollama **0.40.3**, official Linux AMD64 release; Qwen3.5 **4B Q4_K_M**, explicit
`qwen3.5:4b-q4_K_M` tag, with a Caerness 8192-context alias. The runtime reports
4.2B parameters, GGUF/llama.cpp. Official manifest layers total **3,324,173,934 bytes**;
all blobs were SHA-256 verified. Weights/runtime/database files are excluded from
this PR. [Approved manifest](evidence/local-ai/approved-model-manifest.json).

Host: Linux, no GPU, **8 GiB cgroup RAM**, two CPU-equivalents (three logical CPUs
reported). This is not a Windows/GPU test or a comparison of Qwen 9B and Gemma 12B.
Ollama's direct registry download could not traverse the environment's restricted
network path; the approved official blobs were downloaded through the session proxy.
The initial temporary filesystem also filled; task files were moved to the larger
workspace drive. Neither workaround is added to the Windows product.

The first **actual OpenAI-compatible structured diagnostic** passed: 15.119 seconds,
51 input tokens, 19 output tokens. The response was `{"ready":true,"reply":"Hello!"}`.
Its 1.257 output tokens per wall second includes loading/prefill and is **not**
generation rate. The runtime measured 3.75 generation tokens/second for that request.
[Complete probe](evidence/local-ai/openai-probe.json),
[timing-only runtime log](evidence/local-ai/runtime-timings.txt).

The loaded model reported 3,355,422,227 bytes, zero GPU allocation, context 8192.
A separate Linux process observation recorded runner RSS 4,326,580 KiB and peak
4,429,312 KiB. These are observations, not guaranteed memory requirements; shared
pages, other applications, backend versions and longer context matter.

## Genuine player-input evaluations

All player text went directly to the real model through Caerness. No model replies
or structured plans were prepared by the agent. Player-input test lists are ordinary
language evaluation stimuli, not gameplay recognisers. Each JSON transcript includes
player words, actual model packet/reply, engine result, before/after state and latency.
Model narration being stored as unverified dialogue does **not** make its claims true.

| Evaluation | Actual result | Acceptance |
|---|---|---|
| Initial ordinary observation | Three real JSON replies included unused mode fields; each was rejected. A fourth request exceeded conservative context budget. 849.8 seconds total; no time/resource/plan changes | Failed; prompted mode-specific schema fix |
| Schema-backed ordinary life | Four replies accepted structurally, then rest attempt failed when inference runner was killed under memory contention | BLOCKED; prose/grounding issues also found |
| Unfamiliar road-experience exchange | One real response, 287.617 seconds including queueing; discussion instead of requested inspection. No tools or world operations; no funds/positions invented | Technically recorded, qualitatively inadequate |
| NPC conversation before automatic context | Two real replies, 305.218 and 371.478 seconds including queueing. Invented an early shared memory without inspecting the person | INCOMPLETE and qualitatively failed; not twenty-turn acceptance |
| Final scoped-context check under contention | Real request included Petra's available relationship/history context; inference returned HTTP 500 after the runner was killed | BLOCKED; retained, not hidden |
| Final standalone NPC retest | Two real turns with scoped person context; 160.944 and 189.865 seconds, no new OOM kill. Invented school duties and an ungrounded early memory | INCOMPLETE and qualitatively failed; 4B not recommended for campaigns |

Artifacts:

- [Initial failure transcript](evidence/local-ai/failed-initial-transcript.json), [status](evidence/local-ai/failed-initial-evaluation.json), [reload](evidence/local-ai/failed-initial-reload-state.json).
- [Ordinary-life transcript](evidence/local-ai/ordinary-schema-transcript.json), [status](evidence/local-ai/ordinary-schema-evaluation.json), [reload](evidence/local-ai/ordinary-schema-reload-state.json).
- [Unfamiliar instruction transcript](evidence/local-ai/unfamiliar-before-context-fix-transcript.json), [status](evidence/local-ai/unfamiliar-before-context-fix-evaluation.json), [reload](evidence/local-ai/unfamiliar-before-context-fix-reload-state.json).
- [Two-turn NPC transcript](evidence/local-ai/npc-before-auto-context-transcript.json), [status](evidence/local-ai/npc-before-auto-context-evaluation.json), [reload](evidence/local-ai/npc-before-auto-context-reload-state.json).
- [Contention failure transcript](evidence/local-ai/final-context-under-memory-contention-transcript.json), [status](evidence/local-ai/final-context-under-memory-contention-evaluation.json), [reload](evidence/local-ai/final-context-under-memory-contention-reload-state.json).
- [Final standalone transcript](evidence/local-ai/standalone-final-transcript.json), [status](evidence/local-ai/standalone-final-evaluation.json), [reload](evidence/local-ai/standalone-final-reload-state.json).
- [Completed launcher inference/performance check](evidence/local-ai/final-launcher-inference.json): no download, no API key, saved local model reused through the actual launcher on Linux.

Representative failures are important evidence. Asked to greet someone nearby, the
model answered about "institutions waiting in the background" and asked for another
approval to look for a person. The bounded scene list had inadvertently prioritised
low-ID institutions over people. That retrieval defect is fixed: actual present
characters follow explicitly named subjects before other institution entries.

Asked about early acquaintance, Petra's generated reply invented a quiet memory in
"Thistlewood halls before the end fell" and a hearth scene. No shared known history
supported this. Named, present interlocutors now automatically receive the existing
knowledge-safe person context, retaining it across turns; no biography is created.
Missing expressive profiles/history stay explicitly empty. This fix improves the
input, but does not prove that the small model will stop inventing memories.

Asked to find who could prepare road advice and establish permissible terms, the
model asked the player to supply candidates/authorize an inspection already requested.
It did not silently spend resources, but it also did not accomplish the requested
investigation. General guidance now tells it to use authorized read tools without
repeated permission. A larger-model retest is still required; no special road handler
was added. The schema constrains fields/tool names, not intelligence or honesty.

Ordinary prose was generic and sometimes incoherent ("settlements line the settlement's
perimeter"), with unsupported walls/smoke and repeated heaviness/silence. Road options
were narrated imprecisely. The two-turn NPC voice was warm but formulaic, not demonstrated
individual character depth. These are **quality failures**, not a successful RPG demo.

## Memory contention and performance

The agent overlapped a memory-heavy regression run with inference on this 8 GiB
host. The runner was killed; cgroup counters confirm one OOM kill, with HTTP 500
responses to the queued requests. [Counters](evidence/local-ai/memory-events-under-contention.txt).
This experiment is retained and cannot establish that a standalone model necessarily
exhausts RAM. Successful turns already show that CPU response speed is poor here.
The final standalone check completed without another OOM kill. Its two turns still
failed factual-grounding review: supplied context identified Petra as a spouse,
with empty public affiliations/shared history, yet the model invented a school and
students and later a winter meeting. Correct context does not cure this model's
instruction-following weakness. The 4B download is offered only as a diagnostic
fallback, explicitly marked as having failed story-grounding tests.

The completed launcher was then exercised with `--local --probe` and an existing
isolated save, finding Ollama through PATH and reusing the saved model without a
selection/download prompt. Actual OpenAI-schema inference passed in 5.0 seconds;
a separate native timing diagnostic measured **7.8 generation tokens/second**.
The report includes native duration/count fields and runtime RSS/peak observations.
This validates the Python setup path on Linux, not the Windows command shell,
installer, dxdiag or GPU path. No further inference failure was disguised as a pass.

Schema-backed first observation: 3164 input/119 output tokens, 141.955 seconds model
latency and 142.037 seconds whole turn. Runtime generation was 5.87 tokens/second.
Initial pretty-printed observation packet: 4606 input/83 output tokens, 286.220 seconds.
These runs had different contention and formatting/grammar, so this is **not** a
controlled claim of doubled inference performance. Later replies include queue time.
[timing-only log](evidence/local-ai/runtime-timings.txt) distinguishes prefill/generation.

Simulation is measured independently on fresh opening copies: **1 day 0.357 s,
7 days 0.374 s, 90 days 10.725 s**, peak simulation RSS 35–38 MiB.
[Benchmark](evidence/local-ai/simulation-benchmark.json). Inference was also running;
these are this host's observations, not a cross-machine speed guarantee. No simulation
or daily-planning background process was added by this task.

## Repeatable tests and remaining gates

The final full isolated suite passed **132/132**; six focused final checks passed
including consent rejection, hardware sizing/unknown memory, dedicated VRAM parsing,
cloud aliases (including changes after setup), inherited-key suppression, structured
schema scope, incomplete-output/context refusal, private-state exclusion, NPC retrieval
and model-change/save continuity. Existing twenty-turn HTTP tests still use explicitly
scripted responses and are **not model intelligence evidence**.
[Focused test record](evidence/local-ai/focused-tests.jsonl),
[final full-suite record](evidence/local-ai/full-regression.jsonl). Canonical opening and World Bible hashes remain
unchanged; all regression/gameplay work used copies.

**BLOCKED acceptance gates:** native Windows installation/GPU first launch; actual
Qwen3.5 9B versus Gemma 4 12B literary/technical comparison; larger hardware-permitted
models; twenty-turn coherent grounded conversation; unfamiliar instruction with
successful investigation/composable execution; substantial time passage and returning;
credible institutional presence. The diagnostic model is not accepted for these.

The simplest owner-side next step is to follow [WINDOWS_PLAY.md](../WINDOWS_PLAY.md),
let the launcher inspect the PC, consent to a hardware-sized local candidate, then
use **Test Local AI.cmd**. Compare another model with **Change Local Model.cmd**;
your campaign is preserved. No external credential, subscription or programming
is required. Actual transcripts and independent world outcomes must be reviewed
before declaring the game enjoyable or selecting the best narrator.
