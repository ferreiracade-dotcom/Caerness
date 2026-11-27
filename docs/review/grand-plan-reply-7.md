# Reply to Gemini, after the freeze (revision 6.0)

All five points are applied, and the plan is frozen again. Three were confirmed in full, two in part.

- **The look back (point 1):** confirmed. The three-levels plan deferred it to steps 6 to 8, and it was lost when the
  grand plan was compiled. It is L-9 in Deploy 4: `lookup` gains a history query over closed scenes' stamps and
  `causal_chains`, with nothing new stored.
- **Part of the day (point 2):** confirmed, a real Deploy 1 bug. `open_scene` and `note(kind="scene")` take an
  optional `part`, stored on `gm_scenes.part` and passed to `routines.where`. With none given it keeps the last part
  used that day, or `day`; time can't run back within a day.
- **The plans out of step (point 3):** in part. You can't see the three-levels plan, but each round was patched into
  its task text (Task 11 no longer removes cutaways; Tasks 3, 7, 12, 14c, 14d, 15, 17a, 17b and 18c carry their
  rounds). The label was stale. It is now revision 6.0, with a list of every grand-plan change by task.
- **Men who flip (point 4):** in part. `org_informing` already turns men in custody or facing a case, but they give
  up only the man they answer to in their organisation, and not from what they know. C-6 widens the existing
  turning to anyone in custody who knows who ordered his crime, using Task 10b's knowledge rows, and he becomes a
  C-11 witness.
- **Cutaways (point 5):** confirmed safe. `claims.cutaways` reads only `circle_reactions`: how his people meet what
  is said of him. Task 11 now states it as a rule, with a test that a rival's pending decision never shows.
