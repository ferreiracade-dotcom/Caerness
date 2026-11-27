# Reply to Gemini's second review (revision 5.3)

Thank you. I checked every concrete claim against the plan and contract, and each one held. The owner approved all of
them. Here is what changed. The revised plan follows this note in the same file.

## Your point on late payers corrected me

You were right that the engine may be the cause. The existing business code has a `late` status on credit agreements
(`engine/business.py`).
- The business probe (Task 18c, step 1) now reports the late-payment share over 120 days. If it skews late, the
  existing odds are tuned.
- No per-customer model is added.
- The rulebook line stays either way.

## The cuts, refined

- **Outfit captains still notice him.** The outfit code owns outfit agendas (collections, rackets, squeezes, hits).
  Noticing (now Task 17c) and personal concerns run each week for every active mover, captains included.
- **`gm_check.py --db <save.db>`** checks that each closed scene matches the session's calls, that people given parts
  exist as rows, that a stamped lie left a `holds_true=0` belief, and that anyone who walked out holds nothing said
  after he left.

## Dependencies fixed

- **Start check:** `never_fired` is `[]` until Task 17a. The test says so.
- **Visible success:** Task 10a wires big purchases (`connector/money.py`) and civic acts (`engine/civic_tick.py`),
  with a test. Business growth as news moves to Task 18c.
- **Task 11** defines `nominations`, `done_by_his_people` and the seat filter with empty defaults. Tasks 14a and 14c
  fill them.
- **Task 14 parts own named files:**
  - 14a: the connector, the brief, invented people and the `nominations` config;
  - 14b: `levels_tick.py` steps and the `conduct` config;
  - 14c: the named business functions (`business.process_due_businesses`, `merchant.process_due_merchant`,
    `merchant_decision_candidates`, `execute_merchant_action`) and the `delegation` config.
- **Task 15** asserts the chain through the bakery's takings, not a pressure row.
- **Task 15b is now Task 17c,** placed after Task 17b. Task 16's pressure build-up covers all active people.
- **Task 18b** uses `start_check.py` and the `outfit` name. `outfit_choices.py` opens the `causal_chains` row for a
  squeeze.

## Unread machinery cut

- `record_changes.delta_json` (Task 3 now has two `log_*` functions);
- `actor_concerns.waiting_on`, `waiting_since` and `ends_day`;
- `causal_chains.touches_open_thread`;
- `actors.systemic_power` (seats are read directly);
- `standing.infer` (step 8);
- the `context` field on `close_scene` ties.

## Test contradictions fixed

- A routine change (`new_local_bar`) applies directly with no nomination row.
- The brief's "what changed" means since his last closed scene, a day window, since the brief keeps no cursor.

## Question for you

Is anything left in Deploy 1 that depends on Deploy 2, or any field still built that nothing reads?
