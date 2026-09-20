# Using Caerness Engine with Claude

Caerness v0.6 can use an ordinary Claude conversation as its model layer through bounded Markdown packets. No Anthropic API key is required.

## Best workflow

Configure Claude as the manual action/narration model while leaving autonomous background simulation on rules:

```bash
python run.py model-config --action manual_claude --decision rules --narrator manual_claude
```

Then use:

```bash
python run.py bridge-play "YOUR ACTION" --provider claude
```

Upload or paste the generated request file into Claude. The packet asks Claude for one structured JSON response. Save that answer and feed it back with `model-import` followed by `model-apply`.

For a major NPC decision:

```bash
python run.py model-decide "ACTOR NAME" --provider claude
```

As with ChatGPT, it is best to keep **player/narrator packets** and **world-mind packets** in separate conversations if you want to remain spoiler-blind. A world-mind request intentionally contains private actor state; a narration request intentionally does not.

Routine background simulation remains rules-driven, so Claude does not need to be contacted whenever a dormant organization or distant region advances.
