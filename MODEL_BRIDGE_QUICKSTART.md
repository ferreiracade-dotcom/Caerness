# Caerness Engine v0.6 — ChatGPT / Claude Bridge Quickstart

v0.6 is deliberately **API-optional**. You can use a normal ChatGPT or Claude chat as the high-quality model layer without paying for API calls.

The engine remains authoritative. ChatGPT/Claude receive bounded packets and return structured responses. They do not own the database, world clock, hidden state, or canon.

## Recommended no-cost routing

- **Routine world simulation:** rules engine
- **Major NPC decisions:** ChatGPT or Claude only when you choose
- **Player action interpretation:** ChatGPT or Claude when deterministic parsing is insufficient
- **Narration:** ChatGPT or Claude

This prevents hundreds of background actors from requiring manual model calls.

## One-time setup

```bash
python run.py reset
python run.py init
python run.py seed-demo
python run.py model-config --action manual_chatgpt --decision rules --narrator manual_chatgpt
```

To use Claude by default instead:

```bash
python run.py model-config --action manual_claude --decision rules --narrator manual_claude
```

## Start a turn

```bash
python run.py bridge-play "I wait here for two days." --provider chatgpt
```

or

```bash
python run.py bridge-play "I approach the merchant and try to bargain for passage." --provider claude
```

The command writes a Markdown request packet under:

```text
game/campaign_01/model_requests/
```

If the engine already understood the action, it resolves the world first and queues only a **narration** request. If the action was too complex for the deterministic interpreter, it queues an **action interpretation** request and does not mutate world state yet.

## Use the packet in ChatGPT or Claude

1. Open the generated `.md` request packet.
2. Paste its contents into ChatGPT or Claude, or upload the packet file to that chat.
3. The packet asks the model to return one JSON object only.
4. Save that JSON response as something like `response.txt`.
5. Import it:

```bash
python run.py model-import REQUEST_ID response.txt
```

6. Apply it:

```bash
python run.py model-apply REQUEST_ID
```

If this was an action-interpretation request, applying it resolves the actual turn and automatically creates the next narration packet. Repeat the import/apply step for that narration request.

## See pending work

```bash
python run.py model-pending
python run.py model-show REQUEST_ID
```

## Switch the same request between ChatGPT and Claude

A request is provider-neutral internally. You can re-export it without changing the simulation:

```bash
python run.py model-export 12 --provider chatgpt
python run.py model-export 12 --provider claude
```

Only apply one response to the request.

## Ask ChatGPT/Claude to make one major NPC decision

Background actors continue under rules by default. For a particularly important decision:

```bash
python run.py model-decide "[DEMO] House of Seven Ledgers" --provider claude
```

Take the packet to Claude or ChatGPT, import the JSON reply, then apply it. The engine validates that goals, pressures, targets, relationships and interaction types actually exist before the decision can enter world history.

## Why this architecture matters

The manual bridge is not a workaround that turns the chat into the database. It preserves the central architecture:

```text
Caerness state -> bounded model packet -> ChatGPT/Claude proposal
              -> validator -> authoritative state change -> history
```

For narration:

```text
resolved world -> player-safe scene packet -> ChatGPT/Claude prose
```

The narrator never receives the unrestricted database and therefore cannot accidentally reveal every off-screen event.

## No API is required

Nothing in this workflow requires an OpenAI or Anthropic API key. Future local/API adapters can use the same model gateway without changing the simulation architecture.
