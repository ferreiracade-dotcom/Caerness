# Campaign 01

Reserved for player-facing campaign material: exported journal, character notes, and later campaign-specific presentation files.

The persistent world database lives in `../../data/caerness.db`. The campaign is a **view into the same world state**, not a private copy of the setting that only advances while this character is active.

v0.5 persists player actions and turns in SQLite and can export a player-safe Markdown journal with:

```bash
python run.py export-journal game/campaign_01/journal.md
```

The journal intentionally excludes hidden simulation truth. Off-screen history reaches the player only through direct knowledge, rumours, messages, travel, or later discovery.
