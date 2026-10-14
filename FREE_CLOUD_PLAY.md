# Optional free cloud play on Windows

Cloud and local AI use **the same campaign, conversations and authoritative engine**. Groq GPT-OSS 120B has now produced an actual twenty-turn NPC conversation: completed model calls took a median **1.55 seconds**, but rapid turns hit free-token limits and often waited **30–55 seconds** before retry. Investigation continued into actual engine tools, then the daily allowance blocked completion. Complex execution/time-return acceptance remains incomplete. Gemini/OpenRouter have mock integration tests, not live gameplay evidence.

1. Extract the updated project ZIP. Stop the old game first. Copy its **entire `game` folder**, including any `.db-wal`/`.db-shm` files, into the new folder to retain your story. Keep the old folder until your campaign resumes successfully.
2. Double-click **`Play Caerness.cmd`** or **`Choose AI.cmd`**. Python 3.12+ is still required; the launcher installs the existing dependencies if needed.
3. Select **GroqCloud — Free Cloud AI** as the first candidate. Create a free developer key at [GroqCloud](https://console.groq.com/keys). **Keep billing disabled: do not add billing, upgrade or buy credits.**
4. Read the privacy/billing notices. Type `YES` to consent to sending selected game context, then `FREE` to confirm your billing-disabled free account. Paste the key at the **hidden launch-window prompt** and press Enter. Never share it in GitHub comments or chat.
5. Select **`openai/gpt-oss-120b`**, if still available. Caerness verifies the model catalog and runs a short actual JSON inference test. Passing proves connectivity/syntax, **not** complete gameplay acceptance. Groq's strict schema adapter retains general engine arguments and validates decoded responses before any action.
6. The browser opens. Resume your existing story. Choosing AI does not select a different campaign or character.

Keep the launch window open while playing. Keys stay in the Python process, never in the database, browser, logs or diagnostic exports. Closing the window forgets session keys. The next cloud launch asks again unless you deliberately configured that provider's environment key outside Caerness. Only provider/model preferences are saved in `game/ai-choice.json`.

## Alternatives and switching

- **Gemini:** create a free key in [Google AI Studio](https://aistudio.google.com/apikey). Use a **billing-disabled free project**, not a paid project or Vertex AI. Live standard free pricing is checked against available text models. Current first candidate: `gemini-3.8-flash`; other verified free Flash/Flash-Lite choices appear automatically. South Africa is listed as supported. Free-tier content may be used to improve Google products and may receive human review.
- **OpenRouter:** create a key at [OpenRouter](https://openrouter.ai/settings/keys); do not buy credits or enable auto-top-up. Only available `:free` models with zero supplied prices, sufficient context and JSON support are selectable. Free variants change; no fixed best-model claim. Current unpaid allowance is **20 requests/minute and 50/day**; complex turns can consume several calls. No paid model fallback is configured.
- **Ollama / LM Studio:** choose either in the selector, without an API key. Direct **`Play with Ollama.cmd`** and **`Play with LM Studio.cmd`** preserve existing local setup, hardware checks and download consent. See [WINDOWS_PLAY.md](WINDOWS_PLAY.md).
- **Advanced custom endpoint:** separately labelled and **may be paid**. Existing OpenAI-compatible endpoints remain configurable; no free preset silently enters this mode.

To switch, close the launch window, reopen **Choose AI.cmd**, choose another provider/model, and resume the same story. No reinstall or new campaign is needed. Local switching clears cloud session keys; loopback requests never include bearer credentials. Settings shows your active provider and explains switching.

## Free usage and privacy

**Caerness cannot inspect Groq/Gemini billing status. A paid account can be charged for a model also offered free.** `FREE` confirms your account check, not an API guarantee. Keep billing disabled and check your provider console. Groq's dated free-plan review expires **13 November 2026**; the preset then refuses to run until an updated review/package is installed. Gemini/OpenRouter pricing is verified at setup and cached for at most fifteen minutes during play. Unavailable verification never triggers a paid substitute.

Request, token and daily limits change and vary by account; consult the provider console. Diagnostics show only actual token counts and numerical rate headers supplied by the provider. Missing balances stay unknown. No credits, upgrades, billing, automatic provider switches or paid model substitutions are performed. OpenRouter requests include a zero token-price ceiling and disabled endpoint fallback.

Cloud receives necessary scene/character/canon context, conversation excerpts, unresolved intentions and validated feedback, **not the SQLite database**. Dedicated consistency-review calls can receive relevant protected constraints to prevent contradictions. Avoid real personal information. Groq has optional Zero Data Retention controls; OpenRouter also sends context to an inference provider with its own retention/training rules. See [provider policies and assessment](docs/free-cloud-ai.md).

## Failures and real gameplay testing

**If setup fails before the browser opens:** the launch window now prints a safe report with provider, model, phase, error category, HTTP status when known and supplied retry time. It also saves **`game/cloud-inference-check.json`**, on success or failure. Open that file in Notepad and copy its contents for support; it contains no key, raw provider error, dialogue, campaign facts or personal paths. If saving fails, copy the report from the launch window instead. Do not send your campaign database or API key. Model discovery alone does not prove inference access. If Google explicitly reports zero free quota, check the selected project's limits in [AI Studio](https://aistudio.google.com/rate-limit?timeRange=last-28-days); keep billing disabled rather than upgrading.

Use **Settings → Advanced options & diagnostics → Copy Diagnostics**. Reports contain provider/model, request/phase, timing, tokens, numerical rate headers and error category, excluding keys, endpoints, dialogue and campaign facts.

- Rate/token limit: wait before retrying; numerical `retry-after` appears when supplied. Daily limits may require a daily reset. Caerness does not invent reset times or balances.
- Exhausted quota: wait or explicitly choose another free provider/local model.
- Key/account rejected: restart and check the provider-specific key and account access.
- Response options rejected: Copy Diagnostics; no malformed response is accepted. This is a compatibility problem, not a disconnected narrator.
- Internet failure/timeout: correct the connection and **Retry unfinished response**. Do not resend an already executed instruction; confirmed earlier outcomes are retained.

Play with your own unprepared messages: observe ordinary life, sustain twenty NPC turns, request an investigation, try an unfamiliar consequential instruction, introduce compatible biography/institutions, and return after time passes. Judge prose as well as world state. The eight-case checklist is in [docs/free-cloud-ai.md](docs/free-cloud-ai.md).

**`Test Free Cloud AI.cmd`** selects AI then runs the existing real-model recorder on an **isolated opening-world copy**, not your campaign. It stores complete conversation, exact model requests/responses, engine outcomes and token/latency measurements under `runs/local-gameplay-<timestamp>/` (the historical folder name is shared; `evaluation.json` identifies the actual provider). These files contain game-private content; review before sharing. Connection success is never automatically declared gameplay acceptance. Manual invention and interruption/retry tests and qualitative review are still necessary.

Actual Groq transcripts and limitations: [live evidence](docs/evidence/free-cloud/groq-live/conversation.md). Its free limit of 8K tokens/minute and 200K/day makes it a useful first test, but not a proven unrestricted option for long sessions. Consider testing the Gemini free option next if Groq's cadence/quota is restrictive; its literary quality and account limits still need your own evaluation. Never upgrade billing to resolve a quota error.
