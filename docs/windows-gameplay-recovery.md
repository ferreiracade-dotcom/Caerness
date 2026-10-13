# Windows gameplay recovery — PR #7

## What was established

The [owner's Windows review](https://github.com/ferreiracade-dotcom/Caerness/pull/7#pullrequestreview-5505105042)
proves that request #2 parsed and applied successfully, then generated pending
request #3. Its HTTP 200 / 4,703 input tokens / 33 output tokens / 124.1 seconds
must **not** be diagnosed as a malformed first response. The original owner save
was not supplied. Its exact #3 failure therefore remains unknown.

Disposable campaigns and genuine Ollama inference reproduced the same failure
**class**: a successful, applied 33-token read followed by a pending continuation
that failed the context guard before the next inference. Further real reads exposed
a legacy `context` result of approximately 8,838 estimated tokens, mostly a large
roster, repeated player details and repeated narrator rules. No malformed first
response was needed to reproduce this.

Other independently reproducible defects were:

- `read_tools += ...` mutated the module-level catalogue. Every round/turn added
  duplicate tools, enlarging subsequent packets and response schemas.
- Rules appeared twice; scene/person read results could duplicate supplied context.
- The guard estimated escaped JSON transport rather than actual message content.
  Structured local grammar is not model input text. The estimate remains conservative;
  it is not an exact tokenizer, and important content is never silently trimmed.
- Parsed unfinished responses were sent through inference again on retry.
- Progress was left in an outer HTTP transaction during later slow calls.
- The UI replaced distinct failures with “Your narrator is not connected”.

The initial/intermediate experiments are preserved alongside later results, rather
than presented as successful final gameplay.

## Focused implementation

The Python/SQLite simulation, World Bible and general planner remain intact.
No request-specific actions, broad simulation expansion or extra daily processes
were introduced.

Narrative packets now use an independent tool list, send rules once, retain stable
prefixes for caching, share identical snapshots and discover detailed authoring
fields when needed. The scene is already supplied, so requesting it again is not
advertised as another model round. Commanded institution reads retain actual
members, resources, roles and sites. Ordinary `context` reads reuse scoped perception
rather than dumping the legacy roster. Large public results are saved in full and
explicitly paged via `read_result`, with field paths, offsets, provenance and dates.
Private consistency-review constraints are excluded from that interface.

Ordinary dialogue uses early anchors plus 16 recent source messages, with explicit
selection/omission counts. Entire conversations stay saved and searchable/pageable;
the model must retrieve older relevant passages when needed. Original intentions,
unresolved conditions, ongoing plans and authored continuity remain separately
supplied. This avoids repeatedly sending long transcript tails, without quietly
dropping conditions or turning a generated summary into campaign truth. Long-dialogue
literary continuity under this smaller explicit window remains a live-model gate.

Completed reads remain discoverable in the current turn. Completed zero-argument
reads are not advertised again; an identical repeated read stops with an accurate
model-behaviour error rather than another multi-minute loop. Legitimately different
queries and new reads after world changes remain possible. Requests, NPC autonomy,
authoring freedom, exact source conditions and validated commitments are preserved.

Each unfinished request is committed before slow inference. Applying a response and
creating its continuation are transactional; completed prefixes are committed before
the next call. Retry accepts only the owner's latest unfinished request in that
conversation. A saved `responded` request is applied without another model call;
an `applied` request cannot replay. Explicit pause is honoured at safe boundaries.
An in-flight call is not instantly cancelled. A new message cannot overwrite a
pending turn; the input stays available while the player retries or opens a new
conversation. Manual model handoff remains opt-in and separate from diagnostics.

Plain-English errors distinguish unavailable service, timeout, incomplete/invalid
response, context limit, reported memory exhaustion, continuation errors and repeated
reads. Diagnostics show request/phase/round, error category/type, HTTP status where
available, successful usage, failure latency and returned incomplete-output usage.
Unknown usage stays unknown. **Copy Diagnostics** additionally collects non-secret
RAM/GPU/driver and loaded-model GPU allocation. It excludes prompts, dialogue, world
facts, credentials, endpoints and personal paths. No SQLite/Python instructions are
needed to share it.

## Genuine inference: successful transport is not gameplay acceptance

Official Ollama 0.40.3, existing owner-approved Qwen3.5 4B Q4_K_M weights, 8 GiB
CPU-only Linux host, three CPU cores, thinking disabled, 8K context, no paid service.
The official registry manifest/weight hashes matched the installed model. These
measurements are **not** Windows/CUDA benchmarks or a comparison with 9B/Gemma.
Some short focused checks overlapped exploratory inference; there was no overlapping
full regression/model workload. Treat timings as observed runs, not controlled
cross-machine speedup claims. A brief existing-design setting anchor was added after
the recordings; literary quality under that final wording remains unaccepted.

| Actual player turn | Calls | Input/output tokens | Whole turn | Outcome |
|---|---:|---:|---:|---|
| Quiet conversation with Petra | 1 | 2,902 / 72 | 139.55 s | Parsed/persisted dialogue; generic prose |
| Early-acquaintance recollection | 1 | 2,992 / 187 | 91.06 s | Permissible subjective memory; no objective authorship demonstrated |
| Ordinary surroundings | 1 | 3,209 / 127 | 146.34 s | Answered, but remained in NPC voice |
| Greeting a nearby person | 1 | 3,362 / 72 | 65.36 s | Repeated an earlier reply verbatim: quality failure |
| Roads: successful scene read then failed continuation | 1 completed | 3,459 / 33 | 59.32 s | Next request blocked before inference; not malformed first output |
| Later two-paragraph observation | 1 | 2,888 / 189 | 155.99 s | Coherent returned prose; CPU latency unacceptable |
| Intermediate published-services investigation | 7 | See transcript | 395.17 s | Repeated reads/round bound; led to the new repeated-read guard |
| Final published-services request | 1 | 2,903 / 355 | 178.41 s | **Failed investigation:** answered without required native read |
| Final ordinary biographical recollection | 1 | 3,044 / 287 | 171.63 s | Returned creative recollection; consequential promotion still unproven |

The last two calls separately measured **115.14/121.97 seconds of prefill** and
**63.07/49.41 seconds of generation**, at **5.61/5.79 output tokens/second**.
Cached prefill helped some turns, but the hybrid runtime also forced full reprocessing
on others. Peak observed llama-server RSS was about **5.99 GiB**; this is not a
guaranteed VRAM requirement. Ordinary engine/orchestration overhead was small compared
with model latency. Native time/resource changes did not occur in these discussions.

Previously undescribed memories are not categorical hallucinations. The failures are
slow response, repetition, uncertain genre fit and claims of inspecting records
without actually using the required discovery tools. There is no real-model proof
here of reliable objective authorship, complex operations or twenty-turn quality.

Complete representative player/model replies and every recorded request's response,
phase, advertised tools and usage are in
[genuine-transcripts.json](evidence/windows-recovery/genuine-transcripts.json).
[Ollama timing pairs](evidence/windows-recovery/ollama-timings.json) contain numerical
prefill/generation fields without raw environment/prompt logs. Ollama task IDs are
not Caerness request IDs. Full prompt usage differs from evaluated prefill when cached.

## Repeatable tests and recovery evidence

Full isolated regression suite: **134/134 passed**. Final targeted suite: **8/8
passed**, including transport, authoring, planning, authority, browser API and native
regressions. [Regression records](evidence/windows-recovery/regression.jsonl) and
[focused records](evidence/windows-recovery/focused.jsonl).

| Required recovery case | Repeatable evidence | Model-call counts / tokens |
|---|---|---|
| Simple observation / NPC chat | Runtime/HTTP integration | One each; captured prompt estimates in test log; synthetic usage 100/20 |
| Legitimate read continuation | Scoped person read followed by dialogue | Two; synthetic usage 100/20 per successful stub call |
| Timeout then retry | First read applied; second call fails; close/reopen and retry exact pending ID | Two attempts initially, one retry; timeout usage unknown |
| Invalid response | Malformed response retained as retryable failure; distinct error | One failed + one successful retry; stub usage only |
| Interrupted with outcomes | Native one-day action, timeout during consequences, reload, retry | Three initial calls/attempts + one narration retry; day advances exactly once |
| Explicit pause after inference | Parsed response saved as `responded` | One initial call; **zero** extra calls to resume |
| Creative biography | Existing authoring tests: recollection, new significant person/school, contradiction/refusal/reload/time | Explicit queued stubs; no literary-quality claim |

These rows are **mocked interpreter/transport tests**, not actual model intelligence.
Their captured estimates and synthetic usage are labelled in
[mocked-recovery-test.txt](evidence/windows-recovery/mocked-recovery-test.txt).
Tests also cover exact paged retrieval without loss, private reviewer exclusion,
context refusal before inference, repeated reads, memory-error redaction and transport
timeouts. The canonical opening and World Bible SHA-256 remain unchanged.

A genuine inference process was also interrupted with SIGINT. Its applied read
prefix survived and the next request remained pending after reopening; retries of
already-applied IDs were rejected. A subsequent real retry completed another read,
then encountered the oversized legacy-context path. That was **not** a successful
complete narrative recovery; it helped identify the need for scoped/paged results.
[Interruption snapshot](evidence/windows-recovery/actual-interruption.json).

Desktop 1440×900 and phone 390×844 browser checks passed: correct timeout title,
working clipboard redaction, valid settings defaults, no horizontal phone overflow,
no browser errors. Screenshots use an **explicit staged timeout UI fixture**, not
fabricated inference: [desktop error](evidence/windows-recovery/timeout-desktop.png),
[desktop diagnostics](evidence/windows-recovery/diagnostics-desktop.png),
[phone diagnostics](evidence/windows-recovery/diagnostics-phone.png).

## Owner's next step and remaining acceptance gate

Follow [campaign-preserving Windows update/retry instructions](../WINDOWS_PLAY.md).
Use the installed 4B for the recovery check; do not redownload 9B or simply increase
timeouts. Copy Diagnostics after a short observation, conversation and investigation.
Verify supported CUDA/driver offload, or compare LM Studio's CUDA GGUF loading, before
accepting CPU fallback. The launcher defaults away from Vulkan when starting a new
NVIDIA Windows server, while respecting explicit user settings and existing servers.

Current [Ollama GPU documentation](https://docs.ollama.com/gpu) lists GTX 1050 Ti
support, and requires driver 570+ for its compute capability range. This is documented
compatibility, **not** a successful CUDA test on the owner's card. Four gigabytes
of VRAM must not be assumed sufficient for efficient 9B. Smaller local models are
a quality trade-off; another existing GPU-equipped computer avoids ongoing fees.
There is no mandatory API or subscription.

**Software recovery is reviewable; enjoyable local gameplay is not accepted.** The
observed CPU configuration is too slow, and this 4B narrator did not reliably perform
investigations. CUDA/LM Studio may improve speed, but competent free-form planning,
continuity and prose must also pass genuine owner-side tests. No simulation expansion
or larger-model performance claim substitutes for that gate. Nothing was merged.
