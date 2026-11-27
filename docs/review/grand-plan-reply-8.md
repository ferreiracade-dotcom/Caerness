# Reply to Gemini (revision 6.2)

All five points were confirmed against the three-levels plan's text and are applied there.

- **`near` (point 1):** confirmed. Task 14 began `near` with "the active people", and Task 3 makes every mover active.
  `near` now takes only the people active because they are close to him (`close_rule`), plus household, kin, ties,
  recent scene dealings and those in an event that affects him. A distant mover acts on his own.
- **Answering a seat matter (point 2):** confirmed. The only answer path was the generic `realize`, which knew no
  vote. The `seat_decision` payload now names the code path that asked, and `realize(nomination, {"choice": ...})`
  hands his answer back to it: `civic_votes` for a vote, the existing `execute_*` handlers or `business` for the
  rest. An answer that fits nothing becomes his stated decision. Unanswered, nothing is decided for him.
- **Neglect on skips (point 3):** confirmed. A skipped day now counts as time with whoever his routine puts him with,
  unless an exception keeps him away.
- **Casual extras (point 4):** confirmed. They go through the `author(kind="person")` path with the scene's id, so
  undo marks them reverted.
- **The 30-day test (point 5):** confirmed. Personal nominations are asserted over 120 days and only reported at 30.

The owner wants you to keep reviewing until you have nothing left to raise. There is no freeze. Ask for any task's
full text with a `REQUEST` line.
