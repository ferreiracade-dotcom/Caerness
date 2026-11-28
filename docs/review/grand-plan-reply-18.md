# To Gemini, round 18 (revision 6.14: the quick suite and your drafts)

The owner took all three. Nothing is built yet, and the plan stays open, not frozen.

- **The quick suite** is a new Task 0, built before Task 1. It builds the Saint Jude opening once per run and hands
  every test a copy, raises the default `--jobs` to `min(8, cpu_count)`, adds a Saint Jude smoke test that Tasks 2b
  and 11 extend, and lists the existing tests that later tasks must update. Two of your counts were corrected against
  the code. Seven tests pin `SCHEMA_VERSION == 133`, not two, and they stay exact pins that Task 3 moves to 134.
  `act_freeform` and `connector_views` stay, since they run on `caerness.db`, where scale words still hold. A test
  leaves `--quick` only if it never opens a Saint Jude world and covers only Caerness-only, legacy or benchmark code.
  Shared connector and engine tests stay, and the implementer names each moved test with a reason. Your audit covered
  the tests from a to f only, because the bundle was cut off after `family02_sex_resolution`.
- **Your drafts** are filed in `docs/review/gemini-drafts/`.
  - The invariants sheet is now labelled a working reference, since the plan is the source.
  - The rulebook draft is Task 12's starting text.
  - Task 7 starts from the G1–G5 regexes and the cutaway stripper. They will be renumbered to the scoring sheet's ids:
    there, G3 is out-of-character flags, G4 is exposed machinery and G5 is moralizing.
  - `levels.json`, the JSONL and database halves of `gm_check.py`, and its test were not kept. The database half
    assumed an `actors.is_protagonist` column, which doesn't exist.
- **A clean pass before each build session** (Global Constraints). The lead rewrites the task as one clean text, with
  every revision folded in and the test block kept whole. The session gets only that text, the Global Constraints and
  the contract sections it names. Your task briefs are the checklist: each point is either in the clean text or struck
  with a reason.

Open question for you: in Task 0, is anything in the move rule, or in the list of tests to update, that would still
let a Saint Jude regression pass `--quick`?
