# Gemini's drafts

Filed 2026-11-28 (build plan revision 6.14). Nothing here is live or imported, and none of it is the source: the build
plan (`docs/superpowers/plans/2026-11-26-three-levels-build.md`) and its contract
(`docs/superpowers/specs/2026-11-26-three-levels-contract.md`) are. Where a draft and the plan differ, the plan wins.

| File | What it is | Used by |
|---|---|---|
| `invariants.md` | Gemini's one-page summary of Deploys 1 and 2 through revision 6.13, relabelled from "Final" to a working reference | the lead, as a quick reminder |
| `task-briefs.md` | Gemini's zero-history briefs for the most-patched tasks | the lead's clean pass before each build session (Global Constraints) |
| `rulebook_core_draft.md` | a tight draft of `connector/rulebook_core.md` | Task 12, as its starting text |
| `gm_check_prose_patterns.py` | the G1–G5 regexes and `_strip_cutaway_blocks` from Gemini's `gm_check.py` | Task 7, as its starting patterns (renumbered to the scoring sheet's ids) |

Not kept:
- `levels.json`: the values come from the plan's tasks, each set where the task that uses it is built.
- The JSONL-ledger and `--db` halves of the draft `gm_check.py`: they assumed columns that don't exist (for example
  `actors.is_protagonist`); Task 7 builds those checks against the contract.
- The draft `gm_check_test.py`: it tested the dropped halves.
