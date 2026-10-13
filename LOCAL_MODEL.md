# Local Model Gateway

**Current play setup (13 October 2026):** free local inference is the default.
Double-click `Play Caerness.cmd` for hardware detection, explicit download consent,
Ollama setup and a real inference check. `Play with LM Studio.cmd` supports its local
server. See [Windows instructions](WINDOWS_PLAY.md), [runtime/model assessment](docs/local-ai.md)
and [genuine test evidence](docs/local-ai-evidence.md). No account/API key is required.
Models are hardware-sized candidates, not an untested literary ranking.

Caerness v0.7 treats a local model as a replaceable reasoning/narration component.

## Supported backends

### OpenAI-compatible

Windows free-local launcher default (legacy unconfigured saves retain port 8080):

```text
http://127.0.0.1:11434/v1/chat/completions
```

This is the recommended interface because it keeps Caerness independent of any one local runtime.

LM Studio uses `http://127.0.0.1:1234/v1/chat/completions`. Both use the same gateway.
Free-local planning/narrative replies have mode-specific JSON schemas; engine checks
still establish authority, completeness and feasibility. The model cannot authorize
itself. Over-budget context/output is refused rather than silently truncating terms.
The free-local desktop profile executes locally without mandatory paid-model referral.
The advanced native adapter below remains supported, but the launcher does not need it.

### Ollama-native

Optional:

```text
http://127.0.0.1:11434/api/chat
```

Set it with:

```bash
python run.py runtime-config --backend ollama_native --endpoint http://127.0.0.1:11434/api/chat --model MODEL_NAME
```

Caerness itself does not require an Ollama account or cloud service; this adapter simply understands the native local endpoint when available.

## Model authority boundary

Local models have the same restrictions as ChatGPT/Claude:

```text
model proposes/interprets/narrates
engine validates
SQLite records authoritative reality
```

A narration generation cannot create an event simply by mentioning it.

## Scene router

```bash
python run.py model-route REQUEST_ID
```

The router's recommendation is advisory. To override it:

```bash
python run.py model-run-local REQUEST_ID --force --apply
```

## Multi-scene local narration

When a resolved turn contains several fictional beats (for example departure -> journey -> arrival), the local runtime may generate each beat separately and concatenate them into one player-facing passage.

This exists for two reasons:

1. long output can be expensive on a phone;
2. a model-generation boundary is not a legitimate reason to demand player input.

The player sees one continuous section and receives control only at the actual agency handoff.
