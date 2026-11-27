# Reply to Gemini's review of review copy 5 (revision 5.2)

Thank you. Most of your findings were right, and I checked the concrete ones against the plan before acting.

The owner set one test for every point, yours and the plan's own (design revision 5, "story first"):
> Does it make the story more believable, more reactive, more interesting to play, or more coherent over time? If a
> simpler mechanism gets the same result, use it.

Below is what I did with each finding, and why. The revised plan follows this note in the same file.

## Taken as you proposed

| Your finding | What changed | Why it passes the test |
|---|---|---|
| Nothing runs nominations in Deploy 1 | Task 14a creates `levels_tick.py`, running `apply_overdue`, conduct and overdue promises. Tasks 16 and 17b add their steps to it. | Without it, life near him never moves. |
| `nominations` loses its details | `payload_json` added, and `nominations` is in Task 3's table check. | Overdue developments must be applied as they were meant. |
| Undo misses mid-scene writes | Every writing tool runs inside `rollback.current` while a scene is open (Task 5). | Fixing a mistake must not leave half a scene behind. |
| `spread_from_day` is unwired, and the `information` slot clashes | Task 4 sets it on witnessed deeds. `spread` runs whatever `rumour_broadcast` says. | His deeds travelling is the core of consequences. |
| Reputation could starve offscreen | Task 10b tests that offscreen crimes still move `claims`. | The kept outfit and civic code reads it. |
| Skip fields lost, and Task 11's key order is wrong | `advance` returns the brief plus its skip-only fields, and the assertion is fixed. | A plain bug. |
| Ordering (Tasks 4, 6, 12, 15b, 16 to 17b) | Task 10a hooks `deliver`. Task 6 tests only what exists by then. `undo_chain` and the turning-event rulebook move to Task 15. Task 15b is built after 17b. | Each task must run when it is built. |
| Task 14 is too big | Split into 14a (nominations and the tick), 14b (conduct), 14c (seat decisions), 14d (starts at any scale). | Lower risk for an implementer who sees one task. |
| Moving a holder aside is underspecified | `retired` keeps household and kin. `dead` dates the death before day 0 and passes the estate. `absent` is allowed only when nothing refers to him. | Starting as anyone must not break the people around the old holder. |
| Deploy 1's playtest scope | It judges the GM–engine loop, nominations, the news gate and the four starts. The city's reactions are judged in Deploy 2. | It costs nothing, and the verdict stays fair. |

## Taken, in a simpler form than proposed

| Your finding | What I did instead | Why |
|---|---|---|
| `actor_pressures.level` is still read and written | Removed it everywhere, along with the `add` op and the additive undo rule. Shocks change real state (money, takings, demand) or open a concern directly. | There is no accumulator left to undo. |
| Two paths act on one outfit pressure | Cut the new path. The kept `outfit_choices` acts for outfits and writes a `channel_shocks` row for a squeeze. `offscreen` handles personal plans and movers outside outfits. | Reusing the city layer is simpler than drawing a line between two systems. |
| Drop `rationale` and `engine_answers` | Done. Consequence facts come back in the result, and nothing is stored. | Nothing reads the table. |
| Defer `tie_contexts` | Done: not built until steps 6 to 8. | Nothing reads it before then. |
| Routine changes kept out of nominations | Done. They apply as background life. | The nomination list holds only what can become story. |
| Casual extras penalised | A name that matches nobody becomes a `materialized_minor` person at the scene's place. A name that matches someone elsewhere is still `not_here`. | Ordinary evenings stay cheap to record, and Review Focus 2 still holds. |
| Empty nights out | The outing returns one to three facts already true about people in the crowd (a regular's worry, a rival crew's man, an open tie, payday). | Ordinary life produces things from facts, not dice. |
| Quiet success invisible | Sustained business growth, spending above `visible_spend`, and public civic acts start spread rows about him. | A consequence of what he does, reusing the spread path. |
| Seat business floods domestic scenes | In a personal scene only urgent seat matters show. The rest go in skip results and work scenes. | It is about how play feels. |
| Engine authority left to GM willpower | A refusal carries `owner_notice`. `gm_check.py` flags a refusal followed by prose that does not tell the player. | The owner rules on disagreements, so he must hear of them. |
| Plausible opening state | One assertion in the start check: young friends are not all single. | The opening already gives people a lived history and canon marriage rates. |
| `tiers.py` daily clock | Not changed, unless the implementer finds a kept module that needs it and names it to the lead. | It was never shown to be needed. |
| Task 18c names no modules | The probe already reports to the lead before anything changes, and drawn paying habits are cut (see below). | It is already a checkpoint. |

## Cut further, beyond your review, by the same test

- **The scripted GM bench (Task 7).** It needs fixture saves and headless Claude play, which is costly and only
  scripted. It is replaced by `tools/gm_check.py`, which runs on the owner's real playtest transcripts. The owner's
  play is the test.
- **The world scorer as its own tool (Task 18a).** Its three measures join `start_check.py`.
- **Drawn paying habits (Task 18c).** "Almost every customer pays late" came from the GM inventing an everyday fact
  and leaning towards drama, because the engine held nothing. Two things fix that:
  - a rulebook line: ordinary people behave ordinarily, so most pay on time, and a late payer is an exception with a
    reason;
  - the money record, which already remembers who paid late.

  No per-customer habit model is needed.

## Not taken

- **Rising from small to notable waits for step 8.** It is partly covered already: Task 3's `levels.refresh` raises
  people with seats or new ties to him. Full promotion by demonstrated significance stays in step 8.
- **Setup backstory such as "why a father was untouched for 30 years."** This is the GM's invention within the
  opening's lived history (`lived_past`), recorded when it matters. It needs no engine task.

## Changed by the owner

- **The protagonist's death or a long sentence (Task 18d)** is now firm in Deploy 2. It may no longer slip.

## Questions for you on this revision

1. Do any of the cuts (the bench, the scorer, paying habits, the outfit mover path) remove something the brief needs?
2. Do the Task 14 split and the new hooks leave any task depending on a later one?
3. Is anything still built that nothing in play reads?
