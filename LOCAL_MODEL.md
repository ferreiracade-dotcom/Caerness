# Local Model Gateway

Caerness v0.7 treats a local model as a replaceable reasoning/narration component.

## Supported backends

### OpenAI-compatible

Default:

```text
http://127.0.0.1:8080/v1/chat/completions
```

This is the recommended interface because it keeps Caerness independent of any one local runtime.

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
