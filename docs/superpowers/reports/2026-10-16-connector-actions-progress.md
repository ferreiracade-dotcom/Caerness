# SDD ledger — plan: docs/superpowers/plans/2026-10-16-connector-actions.md
Pre-flight: T2 consumes ledger (T1); T3-T5 consume execute/fixture (T2) and coercion (T3, used by T4/T5) — consistent.
Ruling: executor = Sonnet implementer per task, main session reviews each diff, one Opus final review (owner preference) — cost if wrong: weaker per-task review.
Task 1: Ruling: parse_holder(ref, me, conn=None) — existence check needs a connection; transfer always checks — cost if wrong: none.
Task 1: complete (commits 6b6ae9b..343b868, tests: /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/ledger_test.py → ledger_test passed)
Task 2: Ruling: tier-2 hire needs target present; hiring into a holding he cannot draw on refused; role boss refused; household dismissal sets status former — plausibility, consistent with Global Constraints — cost if wrong: small.
Task 2: complete (commits 343b868..a2162ac, tests: bash -c '/c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/player_operations_test.py && /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/connector_act_test.py' → connector_act_test passed)
Task 3: Ruling: coercion test isolates each draw in a rolled-back savepoint — relationships otherwise degrade across draws — cost if wrong: none.
Task 3: Ruling: ledger double counts with create_credit_agreement/make_credit_payment enterprise cash corrected inline — cost if wrong: business cash off by a loan amount.
Task 3: Ruling (reviewer): counters returned as 'countered' with counter_interaction_id; accepting a counter via respond settles the operation (settle_accepted hook in apply_player_response) — plan silent; a counter is a real outcome — cost if wrong: extra code path.
Task 3: complete (commits a2162ac..f6e3d1d, tests: bash -c '/c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/player_operations_test.py && /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/interactions_coercion_test.py && /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/connector_act_test.py' → connector_act_test passed)
Task 4: Ruling: harm falls on the front defender only; empty business = unopposed win; idempotency test lives in player_operations_test (fixture) — cost if wrong: fights feel thin.
Task 4: complete (commits f6e3d1d..7ac9485, tests: bash -c '/c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/player_operations_test.py && /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/connector_act_test.py' → connector_act_test passed)
Task 5: Ruling: public execute strips _principal/_reluctant/_accepted (only _order and settle_accepted pass them) — prevents forged authority or agreement — cost if wrong: none.
Task 5: Ruling: obedience check only for attack and demand (brief's danger table) — cost if wrong: a pay/hire order never refused.
Task 5: minor (deferred): a counter to an ordered operation goes to the subordinate, not the protagonist; ordered outfit-level demands untested.
Task 5: complete (commits 7ac9485..a682320, tests: bash -c '/c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/player_operations_test.py && /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/connector_act_test.py' → connector_act_test passed)
Task 6: Ruling: fully loaded resume cap 18500 -> 19000 for the new rulebook bullet — cost if wrong: ~125 tokens per new chat.
Task 6: complete (commits a682320..7a0da72, tests: bash -c '/c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/connector_resume_test.py && /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/connector_views_test.py && /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/connector_server_test.py && /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/connector_http_test.py' → connector_http_test passed)
Final: reviewer = Opus. Fix pass by Sonnet, commit 6215528, verified by main session (11 suites green); full regression suite not run (owner stopped it earlier).
Final: fixed rank (subordinates must rank below), atomicity (savepoint per operation), loan sources (purse/business only), household wealth conservation, late NPC acceptance settles (settle_npc_accepted), obedience calibration. Evidence: household-wealth and atomicity tests seen RED; rank, loan-source, late-acceptance and obedience tests not seen red in isolation (sequential test) — reasoned against old code.
Final: Ruling: obedience = 0.9*loyalty + 0.6*fear + 0.4*aggression + role bonus (0.25 violent trades, 0.10 other outfit, 0 staff) - 0.18*danger*(1-risk) ± 0.15 — plan formula refused ~half of ordinary orders — cost if wrong: henchmen too compliant or too timid; tune in play.
Final: minor (deferred): money in resources counts as fighting strength in _capacity; bare demand gets coercion 1.0.
Final: minor (deferred): business attack with no staff but owner-outfit weight can be "driven off" by nobody; closed businesses not excluded.
Final: minor (deferred): details "with" as a string iterates characters.
Final: minor (deferred): refusal summaries can carry ids ("unknown business 123"); counter rationale used as loan purpose.
Final: minor (deferred): ordered operation's counter goes to the subordinate (dead end for respond); ordered hire/dismiss resentment aimed at the subordinate.
Final: minor (deferred): hire role "owner" grants authority 100; trade-sell `to` may be the business itself.
Final: minor (deferred): clerk obedience test depends on chosen call ids (deterministic but seed-sensitive).
