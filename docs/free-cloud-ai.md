# Optional free cloud AI: architecture and evidence

Research date: **14 October 2026**. `feat/free-cloud-ai` is based on PR #7 `feat/free-local-ai` at `10587dcec2f198353893f1d6dba10511094d9d62`, preserving its dependencies and recovery corrections. No simulation expansion, canonical changes or merges.

## Current official provider assessment

| Provider | Compatibility and candidate | Limits and billing | Privacy |
| --- | --- | --- | --- |
| GroqCloud | GPT-OSS 120B, 131,072 context; documented schema/JSON modes and low reasoning. First reasoning/tool candidate, literary quality untested. Published throughput is not measured Caerness latency. | Current limits page lists 30 RPM, 1,000 RPD, 8K TPM, 200K TPD for this model; account limits are authoritative. The page also discusses Developer-plan limits: a table alone does not establish account entitlement. Paid pricing is nonzero. Authenticated availability check plus dated free-model review, expiring 13 November. | Organization data controls include optional Zero Data Retention, available to all customers. Do not assume it is enabled or that every feature retains nothing. |
| Gemini | Live free stable Flash/Flash-Lite models intersect official pricing and native model metadata; current first candidate `gemini-3.8-flash`. Existing OpenAI-compatible chat endpoint, schema mode, metadata context/output limits, low reasoning. | South Africa is in official regions. RPM/TPM/RPD vary by project/model/tier; check AI Studio. A paid project can incur charges for models also available free. No extra grounding/search/cache tools enabled. | Pricing states free content is used to improve products; unpaid-service terms discuss human review. Paid-service protections must not be claimed for free projects. |
| OpenRouter | Dynamic exact `:free` IDs with zero supplied prices, known prompt/completion prices, >=8K context, >=1K output, response-format support. Schema where advertised, JSON mode otherwise. No fixed best-model claim. | Current unpaid limits: 20 RPM, 50 RPD; buying >=$10 credits raises daily limits, which this setup does not recommend. Zero-price routing ceiling, endpoint fallback disabled, one explicit model. | OpenRouter and inference provider both process context; provider policies/settings differ. Restricting data collection may reduce free-model availability. No blanket no-training promise. |

Sources consulted:

- Groq: [models](https://console.groq.com/docs/models), [GPT-OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b), [structured responses](https://console.groq.com/docs/structured-outputs), [rate limits](https://console.groq.com/docs/rate-limits), [data controls](https://console.groq.com/docs/your-data).
- Google: [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai), [pricing](https://ai.google.dev/gemini-api/docs/pricing), [regions](https://ai.google.dev/gemini-api/docs/available-regions), [limits](https://ai.google.dev/gemini-api/docs/rate-limits), [terms](https://ai.google.dev/gemini-api/terms).
- OpenRouter: [live catalog](https://openrouter.ai/api/v1/models), [free variants](https://openrouter.ai/docs/guides/routing/model-variants/free), [limits](https://openrouter.ai/docs/api_reference/limits), [routing](https://openrouter.ai/docs/guides/routing/provider-selection), [provider privacy](https://openrouter.ai/docs/guides/privacy/provider-logging), [data collection](https://openrouter.ai/docs/guides/privacy/data-collection).

Gemini pages and OpenRouter catalog were fetched directly. Groq/OpenRouter documentation excerpts were obtained through Firecrawl after direct HTTP was refused. No provider keys were configured/present in relevant environment variables; account entitlement, live inference and actual privacy settings remain unverified.

The full official privacy pages were also read through Firecrawl: Groq normally does not retain inference inputs/outputs, but reliability/abuse logs may last up to 30 days (or longer if legally required); usage metadata is always retained, and ZDR opts out of those content logs. OpenRouter's own prompt logging/product-use are opt-in/off by default; request metadata is retained, with anonymous categorization described in its policy. Its inference providers have separate retention/training rules and separate free-model training settings. These differences do not establish the owner's current account settings or override Google's direct unpaid-API terms.

## Same game, bounded adapters

`engine/ai_providers.py` adds catalogs/policy/payload options to the existing gateway. It introduces no separate narrative engine or unrestricted database tool. The trusted launcher holds provider-bound keys in memory and remembers only provider/model preferences. Exact official HTTPS endpoints and no redirects prevent key forwarding. Loopback requests suppress bearer authentication even outside the free-local profile. Hidden key entry refuses an echoing fallback.

Cloud schemas deliberately use **best-effort `strict:false`**: Caerness's general capability argument objects are outside some providers' closed-object strict subsets. JSON mode is used where only that mode is advertised. **Strict application contract and all source coverage, authoring consistency, NPC consent, scope and domain validation remain unchanged.** No format rejection automatically strips the contract or applies arbitrary JSON. HTTP 400/422 produce explicit compatibility diagnostics; incomplete/invalid responses remain unapplied. Actual provider acceptance of the dynamic schema still requires live keys.

Scene/memory compression and one-call ordinary discussion remain intact. Genuine investigations, independent authoring and scope review can require further calls. Provider/context budgets are checked without silent truncation. Compatible creative histories and significant identities remain permitted through existing graded persistence; independent NPC development and knowledge boundaries are preserved. Cloud model capability grants no extra mutation privilege.

Diagnostics record provider/model, token counts, latency and only supplied numerical rate headers. Groq remaining-request headers refer to **daily requests** and remaining-token headers to **tokens/minute**, not a universal balance. Missing balances remain unknown. No automatic retry/sleep/provider change replays world actions or increases costs unexpectedly.

## Acceptance status

| Case | Required actual-model evidence | Current status |
| --- | --- | --- |
| Observation | Grounded, evocative prose, usually one call. | Three-provider one-call HTTP mock; live **BLOCKED**. |
| NPC conversation | Distinct personality/knowledge and natural pacing. | Existing integration regressions; live **BLOCKED**. |
| Investigation | Saved scoped tool call and actual engine feedback, not invented inspection. | Person-read + failed continuation/reload/retry mock; live **BLOCKED**. |
| Unfamiliar instruction | All conditions preserved using shared capabilities. | Existing general planning regressions; live **BLOCKED**. |
| Creative world development | Compatible biography/significant identities persisted; recollection versus truth distinct. | Existing authoring/contradiction regressions; live **BLOCKED**. |
| Complex undertaking | Resource/authority/consent checks, truthful partial completion. | Native day commit survives failed cloud narration/retry; live **BLOCKED**. |
| Interruption | Retry latest unfinished request, no duplicate completed action. | Timeout/quota/invalid-response/committed-day mock; live **BLOCKED**. |
| Longer dialogue | Twenty turns, changing topics, earlier recall and save/reload coherence. | Existing scripted persistence tests; actual voice/recall **BLOCKED**. |

New HTTP mocks exercise provider adapters, verification, paid model rejection, errors 200/401/402/404/422/429/503, timeout, output cutoff, save/reload, safe diagnostics, private key input, stale local environment, consent, billing attestation and local switching. Mock counts **111 input / 22 output tokens per completion are synthetic**, not measured performance. Short inference probes and valid JSON are not literary acceptance.

The existing real-model recorder sends natural-language test messages, never prepared model responses/plans. It records complete responses, inspected context, engine outcomes, wall/model timing and token/call totals, leaving qualitative acceptance pending. Use it plus manual invention/interruption cases. OpenRouter's limited daily quota may stop a twenty-turn evaluation with tool/review rounds.

No cloud speed, tokens/sec, quality improvement or successful live session is claimed. Next gate: owner privately enters a free key in the launch window and plays unprepared turns. Current CPU-local measurements remain poor; this feature makes faster cloud access practical without claiming the game is already enjoyable.

Final automated results: **136/136 complete regression tests**, six focused checks plus launcher/redirect hardening checks, responsive browser tests at all three resolutions, and Python/JavaScript syntax checks pass. See [committed evidence](evidence/free-cloud/README.md), including screenshots. Canonical database and World Bible hashes are unchanged.
