# Gemini owner-review follow-up — 14 October 2026

The owner reported two Windows probe failures with successful model discovery, but the old launcher hid their HTTP status. Those original causes remain unknown; neither screenshot establishes invalid JSON or zero quota.

Using the supplied key only through hidden input/process memory, on a disposable opening-world copy, the unchanged actual OpenAI-compatible request produced:

- `gemini-3.8-flash`: structured probe passed, **52.5582 seconds**, 36 prompt / 16 completion tokens.
- `gemini-2.5-flash`: authenticated catalog advertised it, but actual inference returned **HTTP 404 / model_unavailable**, in 0.3133 seconds. No quota or schema failure is inferred from that status.
- A natural scene observation on 3.8 then returned **HTTP 503** in 2.8589 model-request seconds / 2.9277 end-to-end seconds. The pending turn was retained. This is genuine inference-attempt evidence, not a successful scene.
- One explicit safe retry of that same saved request returned **HTTP 503** again, in 0.7001 request seconds / 0.7030 end-to-end seconds. It did not duplicate the player's message or apply world changes. No further provider retries were attempted; the process exited and cleared its key.

The updated launcher saves and prints safe diagnostics even when a probe fails, before browser startup. Reports omit replies, raw errors, keys, endpoints, account/project identifiers, campaign facts and personal paths. The native diagnostics distinguish explicit Google's zero free quota, exhausted daily quota, minute limits, authentication, unavailable model, options rejection and server failure. No automatic fallback or billing advice.

Official sources consulted using Firecrawl:

- https://ai.google.dev/gemini-api/docs/openai — bearer-authenticated endpoint, structured response format, and `reasoning_effort='low'` documented for 3.8; low maps to 1,024 thinking tokens on 2.5. We retain the documented request options instead of guessing which was rejected on Windows. The 512-token probe remains unchanged; incomplete output is reported explicitly.
- https://ai.google.dev/gemini-api/docs/rate-limits — limits belong to the project, vary by model/account and are visible in AI Studio. Listing models does not establish generation access.
- https://ai.google.dev/gemini-api/docs/troubleshooting — direct REST callers must handle service failures; client errors should not receive blind retries.

`focused.jsonl` records three passing mock/regression checks, not additional inference. These probes do **not** demonstrate sustained Gemini gameplay, narrative quality, acceptable latency or a fix to the unknown original Windows failure. No owner campaign was available or modified.

Windows next step: update the branch ZIP, stop the old launcher and copy its entire `game` folder into the new installation. Run `Choose AI.cmd` with a fresh privately entered free-project key. If setup fails, open `game/cloud-inference-check.json` in Notepad and share its contents. Do not switch blindly through models, enable billing or send keys/saves.
