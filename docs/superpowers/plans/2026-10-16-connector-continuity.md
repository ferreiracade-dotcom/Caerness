# Connector Continuity (gap 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new chat continues the story: `resume` returns the live thread (recent recaps and open threads), the protagonist's character sheet and the standing rules, and the connector hints when a chat has run long.

**Architecture:** The spec's `campaign` tool is folded into `note` as a `kind` (detail, recap, rule, sheet, error), keeping the tool count at 7 (spec §5 target is 8 or fewer, and `author` is still to come). Four small connector tables hold the records; `resume` reads them; `_call` counts tool calls since the last `resume` and attaches a one-line fresh-chat hint.

**Tech Stack:** Python 3.13, SQLite, mcp SDK 2.3.0 (`MCPServer`), tests as plain `python tests/<name>.py` scripts.

**Spec:** `docs/superpowers/specs/2026-10-16-claude-connector-design.md` (§2 continuity bullet, §5 tool table, §8). Handoff: `docs/superpowers/plans/2026-10-16-connector-handoff.md` (gap 1).

## Global Constraints

- Every mutating call carries a `call_id` and goes through `store.run_once` (same id + same args returns the stored result; same id + different args is refused).
- `connector/rulebook.md` must stay identical to spec Appendix A (enforced by `tests/connector_resume_test.py`); edit both.
- Recaps and notes are guides, never sources of truth (spec §7): nothing here changes engine state.
- Standing rules are saved only after the owner says yes (spec §2); the rulebook says so, the code does not try to enforce it.
- No engine figures in anything the GM is told to show; records here are prose.
- Never write `data/caerness.db`; tests copy it.
- Suggest a fresh chat at ~40 exchanges or after a time skip, never mid-scene (spec §8).

## Review Focus

1. A campaign created before this change (the live `ansel`) opens with the new tables missing: `ensure_connector_schema` must create them and `resume` must return empty continuity, not an error.
2. Recap and thread text of any length: clipped (recap 600 chars, at most 8 threads of 160 chars), so `resume` stays inside its token budget.
3. An unknown `kind` or sheet `field` is refused with the allowed values, not stored.
4. Retrying a recap/rule/sheet note with the same `call_id` stores it once.
5. The hint counter survives server restarts (stored in `connector_meta`) and resets on `resume`.

---

### Task 1: Continuity records through `note`

**Files:**
- Modify: `connector/schema.sql` (append tables)
- Modify: `connector/store.py` (record + read functions)
- Modify: `connector/server.py:109-117` (`note` signature)
- Test: `tests/connector_continuity_test.py` (create)

**Interfaces:**
- Produces (in `connector/store.py`):
  - `NOTE_TYPES = ("detail", "recap", "rule", "sheet", "error")`
  - `SHEET_FIELDS = ("appearance", "voice", "temperament", "ambitions", "habits", "history", "standing")`
  - `record(conn, kind: str, text: str, call_id: str, *, subject_kind: str = "general", subject_id: int | None = None, threads: list[str] | None = None, field: str | None = None) -> dict` — `detail` delegates to existing `add_note`; others insert into their table. Returns `{"saved": kind, ...}` (`"field"` for sheet, `"threads"` count for recap). Does not commit (run inside `run_once`).
  - `continuity(conn) -> dict` → `{"live_thread": {"recent": [str, ...] (last 3 recaps, oldest first), "open_threads": [str, ...] (from the latest recap)}, "character_sheet": {field: text}, "standing_rules": [str, ...] (active, oldest first)}`; empty values omitted, `{}` when nothing is stored.
- Tables: `campaign_recaps(id, world_day, text, threads_json, call_id)`, `standing_rules(id, world_day, text, status DEFAULT 'active', call_id)`, `character_sheet(field PRIMARY KEY, text, world_day, call_id)` (upsert: latest wins), `error_reports(id, world_day, text, status DEFAULT 'open', call_id)`. All `IF NOT EXISTS`.
- Server: `note(call_id: str, text: str, kind: str = "detail", subject_kind: str = "general", subject_id: int | None = None, threads: list[str] | None = None, field: str | None = None) -> dict`, docstring: `"Caerness game: record what should last. kind=detail (a fact about an actor/location/general), recap (after a meaningful moment; threads = open threads), rule (a standing rule the player approved), sheet (protagonist's field), error (an engine or GM mistake)."` The `run_once` request dict includes every argument.

- [ ] **Step 1: Write the failing test** `tests/connector_continuity_test.py`, same scaffolding as `tests/connector_views_test.py` (copy packaged DB to a temp dir, `init_db`, `ensure_connector_schema`, `set_player`). Assertions:

```python
r = store.run_once(conn, "c1", "note", {"k": "recap"}, lambda: store.record(conn, "recap", "Willem rode in at dusk.", "c1", threads=["Rooks probing the Green Table", "x" * 500]))
assert r["saved"] == "recap"
store.run_once(conn, "c1", "note", {"k": "recap"}, lambda: store.record(conn, "recap", "Willem rode in at dusk.", "c1", threads=["Rooks probing the Green Table", "x" * 500]))
assert conn.execute("SELECT COUNT(*) FROM campaign_recaps").fetchone()[0] == 1          # retry stores once
for i in range(4):
    store.record(conn, "recap", f"moment {i} " + "y" * 900, f"r{i}", threads=[f"t{j}" for j in range(12)])
cont = store.continuity(conn)
assert [t[:8] for t in cont["live_thread"]["recent"]] == ["moment 1", "moment 2", "moment 3"]
assert all(len(t) <= 600 for t in cont["live_thread"]["recent"])
assert cont["live_thread"]["open_threads"] == [f"t{j}" for j in range(8)]               # latest recap, max 8
store.record(conn, "sheet", "Heavy-set, grey at the temples.", "s1", field="appearance")
store.record(conn, "sheet", "Heavy-set, close-cropped grey hair.", "s2", field="appearance")
assert store.continuity(conn)["character_sheet"] == {"appearance": "Heavy-set, close-cropped grey hair."}
store.record(conn, "rule", "Never ask me to name subordinates.", "u1")
assert store.continuity(conn)["standing_rules"] == ["Never ask me to name subordinates."]
store.record(conn, "error", "Engine placed Vera in Rivermoor.", "e1")
assert conn.execute("SELECT status FROM error_reports").fetchone()[0] == "open"
assert store.record(conn, "detail", "limps", "d1", subject_kind="actor", subject_id=me)["subject_kind"] == "actor"
for bad in (lambda: store.record(conn, "diary", "x", "b1"), lambda: store.record(conn, "sheet", "x", "b2", field="shoe size")):
    try: bad(); raise AssertionError("accepted")
    except ValueError as e: assert "must be one of" in str(e)
# A campaign from before this change: tables absent until ensure_connector_schema runs, then empty continuity.
for t in ("campaign_recaps", "standing_rules", "character_sheet", "error_reports"): conn.execute(f"DROP TABLE {t}")
store.ensure_connector_schema(conn)
assert store.continuity(conn) == {}
```

- [ ] **Step 2: Run** `python tests/connector_continuity_test.py` — expected FAIL (`AttributeError: ... 'record'`).
- [ ] **Step 3: Implement** the tables, `NOTE_TYPES`, `SHEET_FIELDS`, `record`, `continuity` in `connector/store.py` (clip with the existing `views._clip` rule: recap 600, thread 160, sheet 400, rule 300; refuse with `ValueError(f"kind must be one of {NOTE_TYPES}")` / `f"field must be one of {SHEET_FIELDS}"`), and the new `note` signature in `connector/server.py` calling `store.record` inside `run_once`.
- [ ] **Step 4: Run** `python tests/connector_continuity_test.py`, `python tests/connector_server_test.py`, `python tests/connector_store_test.py` — expected all pass (update `connector_server_test.py` only where it asserts the old `note` parameter list).
- [ ] **Step 5: Commit** `feat(connector): note records recaps, standing rules, character sheet and error reports`.

### Task 2: `resume` restores the story; fresh-chat hint; rulebook

**Files:**
- Modify: `connector/session.py` (`resume`, `HOW_TO_PLAY`)
- Modify: `connector/server.py:29-41` (`_call` counts calls and adds the hint)
- Modify: `connector/store.py` (`bump_calls`)
- Modify: `connector/rulebook.md` and spec Appendix A (Continuity section)
- Test: `tests/connector_resume_test.py`, `tests/connector_server_test.py`

**Interfaces:**
- Consumes: `store.continuity(conn) -> dict` (Task 1).
- Produces: `store.bump_calls(conn, tool: str) -> int` — `resume` sets `connector_meta.calls_since_resume` to 0 and returns 0; any other tool increments and returns the new count (commits). `HINT_AFTER_CALLS = 40`. `_call(fn, tool: str)` adds `result["fresh_chat_hint"] = "A good moment to suggest a fresh chat once this scene ends."` when the result has no `error` and either the count is ≥ 40 and a multiple of 10, or `tool == "advance"` and `result["elapsed_days"] >= 7`.
- `resume` result gains `"story": store.continuity(conn)` (omitted when empty) and, when `character_sheet` is empty, `"sheet_missing": "Draft the protagonist's sheet from scene, lookup and play so far; save each field with note kind=sheet."`

- [ ] **Step 1: Write the failing tests.** In `connector_resume_test.py`: after recording one recap (threads `["Rooks probing"]`), one rule and one sheet field via `store.record` + commit, `r = resume(conn)` has `r["story"]["live_thread"]["open_threads"] == ["Rooks probing"]`, `r["story"]["standing_rules"]`, no `"sheet_missing"`; on a fresh copy `"story" not in r` and `"sheet_missing" in r`; `len(json.dumps(r)) <= 14000` (rulebook included). In `connector_server_test.py`: drive `store.bump_calls` 40 times after a resume and assert the hint appears on the 40th `_call` result and not on the 39th; a `resume` resets the count to 0; an `advance` of 7 days carries the hint.
- [ ] **Step 2: Run** both tests — expected FAIL (`KeyError: 'story'`, no hint).
- [ ] **Step 3: Implement** `bump_calls`, the `_call(fn, tool)` change (every registered tool passes its own name), `resume` additions, and `HOW_TO_PLAY` line 4: `"4. Record what should last with note: details (kind=detail), a recap with open threads after meaningful moments (kind=recap), the protagonist's sheet (kind=sheet), approved standing rules (kind=rule), mistakes (kind=error)."`
- [ ] **Step 4: Rulebook.** Replace the three Continuity bullets in `connector/rulebook.md` and spec Appendix A with:
  - `- `resume` returns the story so far: continue from it mid-scene, without a "previously" unless asked. The live thread and sheet are reminders; the engine decides what happened.`
  - `- After a meaningful moment, save a short recap with `note` kind=recap, listing the threads still open (promises, threats, errands, unanswered questions).`
  - `- Keep the protagonist's sheet current with kind=sheet when play establishes something (appearance, voice, temperament, ambitions, habits, history, standing). If `resume` says the sheet is missing, draft it from what is known and save it.`
  - `- If the player corrects you with a lasting preference, ask whether to save it as a standing rule; save it with kind=rule only after they say yes. Follow saved rules in every chat.`
  - `- When a tool result carries `fresh_chat_hint`, finish the scene, then suggest a fresh chat in one line.`
- [ ] **Step 5: Run** `python tests/connector_resume_test.py`, `python tests/connector_server_test.py`, `python tests/connector_continuity_test.py`, `python tests/connector_http_test.py` — expected all pass.
- [ ] **Step 6: Commit** `feat(connector): resume restores the live thread, sheet and standing rules; fresh-chat hint`.

### Task 3: Deploy and owner check

- [ ] **Step 1:** Full suite: `python tools/run_suite.py --out runs/suite` then `git restore game/campaign_01/model_requests/`; expected no FAIL lines in `runs/suite/progress.jsonl`.
- [ ] **Step 2:** `git push`, then `ssh -i ~/.ssh/caerness_oracle ubuntu@92.4.144.46 'sudo bash /opt/caerness/deploy/update.sh'`; expected the smoke tests pass and `curl -fsS https://caerness.duckdns.org/health` returns ok.
- [ ] **Step 3:** Owner playtest on the phone: new chat, `resume`, play a few exchanges, end the chat, start another; the second chat must open mid-story with the open threads. Ask: "can the GM actually do what a player of this character would ask?"

Out of scope: switching campaigns from chat (one campaign per server; `CAERNESS_CAMPAIGN`), the journal page, error repair (§8b), folding old recaps into a journal.
