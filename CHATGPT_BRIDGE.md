# Using Caerness Engine with ChatGPT

Caerness v0.6 can use an ordinary ChatGPT conversation as its model layer through bounded Markdown packets. No OpenAI API key is required.

## Best workflow

Configure ChatGPT as the manual action/narration model while leaving autonomous background simulation on rules:

```bash
python run.py model-config --action manual_chatgpt --decision rules --narrator manual_chatgpt
```

Then use:

```bash
python run.py bridge-play "YOUR ACTION" --provider chatgpt
```

Upload or paste the generated request file into ChatGPT. Ask ChatGPT to follow the packet exactly. Save its JSON answer and import/apply it with `model-import` and `model-apply`.

The packet already contains the relevant player-safe canon/state. Do **not** upload the whole SQLite database to the narrator chat. The separation is intentional.

For a major off-screen actor decision, use `model-decide ACTOR --provider chatgpt`. Those packets contain that actor's private decision context and should be kept separate from a player-facing narration chat if you want to avoid spoilers.

A good practical setup is therefore two ChatGPT conversations:

- **Caerness — Player/Narrator:** narration and player-action packets only.
- **Caerness — World Mind:** major NPC-decision packets. Avoid reading this chat if you are playing spoiler-blind.

The rules engine continues to move all routine background actors whether either chat is open or not.
