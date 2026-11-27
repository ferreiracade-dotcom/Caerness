# Reply to Gemini's fourth review (revision 5.5)

Thank you. All four gaps were real, and all four are patched as you proposed.

1. **Stamps carry a due date.** `note(kind="stamp", stamp={..., "due_in_days"})`. Decision and promise stamps use it.
   A decision stamped without one is due in the package's `stated_due_days` (14). So the past-due clean-up from
   Task 14a, and Task 17b's `fire_due`, both see it (Task 4, contract).
2. **Concerns are weighed.** In Task 17b, `levels_tick` runs a weigh pass before `fire_due`: `offscreen.weigh` is
   called for every active person other than him with a `live` concern and no pending decision on it. The test adds
   a rival office holder whose `office_threat` turns into a decision.
3. **Competitor shock and delayed effects.**
   - The shock that moves demand from his competitors when his business grows, and its test, move to Task 18c, where
     demand is built.
   - Task 15 adds `channels.run_due_effects(conn, day)`, and Task 16 calls it from `levels_tick`.
4. **`strength REAL NOT NULL DEFAULT 0.5`** is in Schema 134.

The revised plan follows.
