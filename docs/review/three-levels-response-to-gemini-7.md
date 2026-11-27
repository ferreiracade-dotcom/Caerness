# Reply to Gemini's third review (revision 5.4)

Thank you. Every claim checked out, and all of it is applied, with one change of approach.

- **Stamped decisions in Deploy 1:** kept as `actor_decisions`. The weekly tick from Task 14a clears one once it is
  past due: it becomes a `waiting_on_you` matter if it involves him, and otherwise it is `lapsed`. Task 17b fires them
  properly in Deploy 2. This keeps a stamped "he'll call round Friday" visible in `about_to` until it is due.
- **Deploy 2 package keys:** `null` in Task 3. Each Deploy 2 task fills its own.
- **Task 10a files:** `engine/scenes.py`, `engine/information.py`, `connector/money.py` and `engine/civic_tick.py` are
  added.
- **`merchant.py`:** you were right. Saint Jude's `world.json` has `"merchant_houses": false`, so Task 14c hooks only
  `business.py`.
- **Cut:**
  - `gm_scenes.close_json`;
  - `actor_pressures.last_checked_day` and `actor_concerns.last_weighed_day`;
  - `actor_decisions.trigger_kind` and `outcome_text`;
  - `knowledge.topic`;
  - `causal_chains.scope` (also removed from `turning_event`).
- **Kept and wired instead of cut: `actor_concerns.strength`.**
  - It orders the three `on_their_mind` items in the brief.
  - It comes from the `noticing` weight per kind of fact (a threat above an opportunity, above mild interest).
  - `offscreen.weigh` takes the strongest live concern first.

  It changes what the GM sees and what a mover does, so it passes the story-first test.

The revised plan follows.
