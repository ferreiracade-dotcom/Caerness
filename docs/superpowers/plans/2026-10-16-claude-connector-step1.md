# Claude Connector, Step 1: First Playable Slice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner opens a normal chat in the Claude desktop app on Windows, says "resume", and plays a real scene in which every fact and every consequential outcome comes from the Caerness engine.

**Architecture:** A new top-level `connector/` package runs as a local MCP server over stdio, launched by the Claude desktop app. It is thin: it opens a campaign database (a copy of the opening world), shapes compact read results from existing engine functions, and routes changes through the engine's existing player-action pipeline (`engine.turns.resolve_turn_state`) and time-skip runner (`engine.timeskip`). Every mutating call is idempotent by a caller-supplied `call_id`.

**Tech Stack:** Python 3.13 at `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"`, SQLite, the official MCP Python SDK (`mcp` package, `FastMCP`), existing `engine/`.

**Spec:** `docs/superpowers/specs/2026-10-16-claude-connector-design.md` (read §2, §4–§7, §9, §11 step 1, Appendix A). Requirements background: `D:\Theology\Caerness_Agreed_Narrative_Design_Baseline_2026-10-16.md`.

**Branch:** `feat/claude-connector` (already created from `master`; the spec is committed there).

## Global Constraints

- Build on `master`'s engine. Do not copy files from the Codex `feat/*` branches in this step.
- Never write to the packaged `data/caerness.db`. Campaigns are copies. Tests use scratch databases (`CAERNESS_DB_PATH` / temp dirs).
- No raw SQL tool, no Python-exec tool, no tool that edits arbitrary world data.
- Tool parameters are general (who/what/where/how long). No activity-specific tools.
- Mutating tools (`act`, `advance`, `note`) require a `call_id`; repeating a call returns the stored result and changes nothing.
- Token targets (spec §9): all tool definitions together ≤ 1.5k tokens (≈ 6,000 characters of JSON); `resume` ≤ 3k tokens (≈ 12,000 chars); `scene` ≤ 1k (≈ 4,000 chars); `lookup` ≤ 500 typical (≈ 2,000 chars); `act`/`advance` results ≤ 600 (≈ 2,400 chars). Enforced by tests as character limits.
- JSON returned to Claude: UTF-8, `ensure_ascii=False`, no `None`-valued keys, no internal packet dumps.
- Tests follow the repo convention: `tests/<name>_test.py`, a `run()` function, `if __name__ == "__main__": run()`, plain `assert`s, a final `print(...passed...)`. They are picked up by `tools/run_suite.py`. Run one with `CAERNESS_DB_PATH=<scratch>.db PYTHONPATH=. "$PY" tests/<name>_test.py`.
- Owner rule: commit after each task on this branch; push only when the owner asks.

## Review Focus

1. **Anything printed to stdout breaks the MCP stdio protocol.** Engine code may `print`. Every tool call must run with stdout redirected to stderr. Test in Task 7.
2. **Slow tools.** A 90-day advance takes ~35 s on this PC. `advance` caps one call at 30 days and says how many remain; the test in Task 5 checks the cap.
3. **Two chats at once** can start two server processes on the same campaign file. Connections set `PRAGMA busy_timeout=30000`; mutating calls run inside one transaction. Test in Task 2.
4. **Non-ASCII names** (the opening world has them; console output showed `�`). Results must round-trip UTF-8. Test in Task 3.
5. **Retry with the same `call_id` but different arguments** must be refused, not answered with the old result. Test in Task 2.

---

### Task 1: Campaign files and package skeleton

**Files:**
- Create: `connector/__init__.py` (empty), `connector/campaign.py`, `connector/requirements.txt`, `connector/setup_campaign.py`
- Test: `tests/connector_campaign_test.py`

**Interfaces:**
- Produces:
  - `campaign_dir() -> pathlib.Path`: `%CAERNESS_CAMPAIGN_DIR%` if set, else `%LOCALAPPDATA%\Caerness\campaigns`. Created if missing.
  - `open_campaign(name: str) -> pathlib.Path`: path `<campaign_dir>/<name>.db`. If absent, copy `data/caerness.db` there. Set `os.environ["CAERNESS_DB_PATH"]` to it, call `engine.db.init_db()` (idempotent schema), then `connector.store.ensure_connector_schema` (Task 2). Returns the path. Name must match `^[A-Za-z0-9_-]{1,40}$`, else `ValueError`.
  - `connect_campaign() -> sqlite3.Connection`: `engine.db.connect()` plus `PRAGMA busy_timeout=30000`.
  - CLI `python connector/setup_campaign.py --campaign NAME [--actor "Full Name"]`: opens/creates the campaign; with `--actor`, sets that existing person as protagonist via `engine.player.set_player(conn, actor_id, campaign_name=NAME)` and commits. Prints the path and protagonist to stderr. (Step 1 only: the new-character flow is step 2.)

- [ ] **Step 1: Install the SDK and pin it.** Run `"$PY" -m pip install mcp`, then write the installed version into `connector/requirements.txt` as `mcp==<version>`.
- [ ] **Step 2: Write the failing test** `tests/connector_campaign_test.py`:
  - sets `CAERNESS_CAMPAIGN_DIR` to a fresh temp dir; records SHA-256 of `data/caerness.db`;
  - `p = open_campaign("t1")` → `p.exists()`, `p.parent == campaign_dir()`, `os.environ["CAERNESS_DB_PATH"] == str(p)`;
  - calling `open_campaign("t1")` again does not re-copy (mtime unchanged);
  - `open_campaign("bad name!")` raises `ValueError`;
  - packaged DB hash unchanged at the end.
- [ ] **Step 3: Run it, expect failure** (module missing).
- [ ] **Step 4: Implement `connector/campaign.py` and `connector/setup_campaign.py`** per Interfaces. Copy with `shutil.copy2`; never open the packaged file for writing.
- [ ] **Step 5: Run the test, expect pass.**
- [ ] **Step 6: Commit** `feat(connector): campaign copies and setup CLI`.

### Task 2: Connector store: idempotent calls and GM notes

**Files:**
- Create: `connector/store.py`, `connector/schema.sql`
- Test: `tests/connector_store_test.py`

**Interfaces:**
- Produces (`connector/store.py`):
  - `ensure_connector_schema(conn) -> None`: executes `connector/schema.sql` (all `CREATE TABLE IF NOT EXISTS`).
  - `run_once(conn, call_id: str, tool: str, request: dict, fn: Callable[[], dict]) -> dict`: if a row exists for `call_id` with the same `tool` and same canonical request JSON, return its stored result with `"replayed": True` added. If it exists with a different tool or request, raise `ValueError("call_id reused with different arguments")`. Otherwise run `fn()` and store the result in the same transaction (`BEGIN IMMEDIATE` … commit; rollback on exception, and nothing is stored when `fn` raises).
  - `recent_operations(conn, limit: int = 3) -> list[dict]`: newest stored mutating calls as `{"call_id", "tool", "summary", "day"}`; `summary` is the result's `summary` field.
  - `add_note(conn, subject_kind: str, subject_id: int | None, text: str, call_id: str) -> dict`: `subject_kind` in `{"actor","location","general"}`; subject must exist for actor/location; `text` stripped, 1–500 chars. Returns `{"note_id", "subject_kind", "subject_id", "summary"}`.
  - `notes_for(conn, subject_kind: str, subject_id: int, limit: int = 5) -> list[str]`.
- Tables (`connector/schema.sql`):
  - `connector_calls(call_id TEXT PRIMARY KEY, tool TEXT NOT NULL, request_json TEXT NOT NULL, result_json TEXT NOT NULL, world_day INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`
  - `gm_notes(id INTEGER PRIMARY KEY AUTOINCREMENT, subject_kind TEXT NOT NULL CHECK (subject_kind IN ('actor','location','general')), subject_id INTEGER, text TEXT NOT NULL, provenance TEXT NOT NULL DEFAULT 'gm_improvised', world_day INTEGER NOT NULL, call_id TEXT NOT NULL)` with an index on `(subject_kind, subject_id)`.
  - `connector_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)`

- [ ] **Step 1: Write the failing test** on a scratch DB built with `reset_db(); init_db(); seed_demo()` (as `tests/action_test.py` does), then `ensure_connector_schema`:
  - `run_once` with a counter-incrementing `fn`: two calls with the same id/args → counter == 1, second result has `replayed` True;
  - same id, different request → `ValueError`;
  - `fn` raising → no row stored, and a retry with the same id runs `fn`;
  - `add_note` on a seeded actor, then `notes_for` returns the text; a missing actor id → `ValueError`; 501-char text → `ValueError`;
  - **concurrency:** a second connection holding `BEGIN IMMEDIATE` for 1 s on another thread does not make `run_once` fail (busy timeout waits).
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(connector): idempotent call store and GM notes`.

### Task 3: `scene` and `lookup` (read-only)

**Files:**
- Create: `connector/views.py`
- Test: `tests/connector_views_test.py`

**Interfaces:**
- Consumes: `engine.player.build_scene_packet(conn, request_text="")`, `engine.player.get_player`, `store.notes_for`, `store.recent_operations`.
- Produces:
  - `compact_scene(conn) -> dict` with keys: `day`, `location` (`id`, `name`, one-line description), `protagonist` (`id`, `name`, age if known, occupation/role line), `present` (list of `{"id","name","who"}` where `who` is the one-line description the packet already has; at most 12), `pending` (pending player interactions: `{"interaction_id","kind","from","about"}`), `news` (known events and rumours, at most 5 each, one line; rumours prefixed "rumour:"), `competence` (compact `professional_context`: the protagonist's relevant domains and what they would notice, at most 6 lines), `condition` (one line from `health_context`), `notes` (GM notes for the location and present actors, `{"about","text"}`, at most 6), `recent_operations` (`store.recent_operations`). Must **not** contain `narrator_rules`, `embodiment`, `canon`, raw `player` record or `scene_packet_id`.
  - `lookup(conn, query: str) -> dict`: `query` is a name or a numeric id. Finds an actor (`actors.name`), else a location, else returns `{"found": False, "candidates": [up to 5 close names of either kind]}` (case-insensitive `LIKE '%q%'`). When found: `{"found": True, "kind", "id", "name", "basics"}` plus `"known"`: up to 8 of the protagonist's `knowledge.belief_text` lines whose text mentions the name, each `{"text","confidence","learned_day"}`; `"relationship"`: the protagonist↔actor relationship as stored by `engine/relationships.py` (whatever that module's pair accessor returns, reduced to its numeric/label fields), omitted if none; `"notes"`: `notes_for`. Never includes `truth_event_id` or anything the protagonist doesn't know.

- [ ] **Step 1: Write the failing test** on a scratch copy of the packaged opening world (copy `data/caerness.db` to a temp path, set `CAERNESS_DB_PATH`, `init_db()`, `ensure_connector_schema`), protagonist set with `set_player` to the first `actors` row with `actor_type='character'` and a non-null `current_location_id`:
  - `s = compact_scene(conn)`: required keys present; `"narrator_rules" not in s`; `"competence" in s`; `len(json.dumps(s, ensure_ascii=False)) <= 4000`;
  - `lookup(conn, <a present actor's name>)["found"] is True` and its JSON ≤ 2000 chars;
  - `lookup(conn, "zzzz-nobody")["found"] is False`;
  - **UTF-8:** pick any actor whose name has a non-ASCII character (if the world has one) and assert `lookup` returns that exact name;
  - after `add_note` on a present actor, the note appears in `compact_scene(conn)["notes"]`.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** `compact_scene` by selecting and trimming fields from `build_scene_packet`'s output (keys listed in spec §9 measurement: `location`, `present_actors`, `pending_player_interactions`, `known_events`, `known_rumours`, `professional_context`, `health_context`); `lookup` with direct queries on `actors`, `locations`, `knowledge`.
- [ ] **Step 4: Run, expect pass.** If `compact_scene` exceeds 4,000 chars, trim list lengths, not the limit.
- [ ] **Step 5: Commit** `feat(connector): compact scene and lookup views`.

### Task 4: `act` through the engine's player-action pipeline

**Files:**
- Create: `connector/acting.py`
- Test: `tests/connector_act_test.py`

**Interfaces:**
- Consumes: `engine.turns.resolve_turn_state(conn, raw_input, action_provider=...)`, `engine.actions.PlayerActionProposal`, `engine.actions.shortest_route(conn, start_id, end_id) -> (days, ids, names) | None`, `store.run_once`.
- Produces:
  - `ACT_TYPES = ("observe", "speak", "investigate", "respond", "travel")`
  - `class StructuredActionProvider` implementing `propose(conn, raw_text) -> PlayerActionProposal` from fields given at construction (no text parsing). For `travel` it fills duration and route from `shortest_route`; if no route, `needs_interpretation=True` with note "No known route to that place." For `respond`, `response_choice` must be one of `accept`, `reject`, `counter`.
  - `act(conn, call_id: str, action_type: str, intent: str, *, target_actor_id: int | None = None, target_location_id: int | None = None, interaction_id: int | None = None, response_choice: str | None = None, duration_days: int = 0) -> dict`, wrapped in `run_once`. Unknown `action_type` → result `{"status": "refused", "summary": "Unsupported action type; use one of …"}` with no world change (not an exception). Returns `{"status", "action_type", "summary", "day_started", "day_ended", "elapsed_days", "operation_id": call_id, "turn_id"}` (drop the engine's narration envelope and packets). `intent` (the player's words, ≤ 500 chars) is the `raw_input` stored on the turn.

- [ ] **Step 1: Write the failing test** on the demo world (`reset_db(); init_db(); index_canon(DEFAULT_CANON); seed_demo()`, protagonist set as in `tests/action_test.py`):
  - `speak` to a present actor → `status == "applied"`, `elapsed_days == 0`;
  - `travel` to a connected location → `status == "applied"`, protagonist's `current_location_id` is the destination, `world_state.current_day` advanced by `elapsed_days`;
  - repeating the same `travel` call_id → result `replayed` True and day unchanged since the first call;
  - `action_type="seize_castle"` → `status == "refused"`, day and `player_actions` row count unchanged;
  - `speak` with a nonexistent `target_actor_id` → status not `applied`, day unchanged;
  - every result's JSON ≤ 2400 chars.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** per Interfaces. Validate ids exist before building the proposal.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(connector): act routes structured intents through the engine`.

### Task 5: `advance` through the time-skip runner

**Files:**
- Create: `connector/timeflow.py`
- Test: `tests/connector_advance_test.py`

**Interfaces:**
- Consumes: `engine.timeskip.prepare_time_skip(conn, actor_id, days, interruption_policy="meaningful") -> run_id`, `engine.timeskip.resolve_time_skip(conn, run_id) -> dict`, `store.run_once`.
- Produces:
  - `MAX_ADVANCE_DAYS = 30`
  - `advance(conn, call_id: str, days: int, purpose: str) -> dict`, wrapped in `run_once`. `days` < 1 → `ValueError`. Requests over 30 run 30 and report `"remaining_days": days - 30`. Returns `{"summary", "day_started", "day_ended", "elapsed_days", "interrupted": bool, "interruption": one line or omitted, "noticed": up to 8 one-line items the protagonist learned during the window (their `knowledge` rows with `learned_day` in range), "remaining_days" (omitted if 0), "operation_id"}`.

- [ ] **Step 1: Write the failing test** on the demo world:
  - `advance(…, 5, "rest")` → `day_ended - day_started == elapsed_days`, `1 <= elapsed_days <= 5`;
  - same call_id again → `replayed`, day unchanged;
  - `advance(…, 45, …)` → `elapsed_days <= 30` and `remaining_days == 15` when not interrupted;
  - `advance(…, 0, …)` raises `ValueError`;
  - result JSON ≤ 2400 chars.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** per Interfaces; take the interruption line from the resolved run's interruption record.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(connector): advance time with interruptions and a 30-day cap`.

### Task 6: `resume` and the GM rulebook

**Files:**
- Create: `connector/rulebook.md`, `connector/session.py`
- Test: `tests/connector_resume_test.py`

**Interfaces:**
- Consumes: `views.compact_scene`, `store` meta table.
- Produces:
  - `connector/rulebook.md`: the text of spec **Appendix A** copied verbatim (headings and bullets), preceded by one line: "You are the game master for Caerness. These rules are binding for this chat."
  - `load_rulebook() -> str` (reads the file as UTF-8).
  - `resume(conn) -> dict`: `{"rulebook": load_rulebook(), "campaign": <name from player_state>, "protagonist": compact_scene()["protagonist"], "scene": compact_scene(conn), "how_to_play": <the five-line protocol below>}`. If no protagonist is set: `{"needs_setup": True, "how": "Run: python connector/setup_campaign.py --campaign NAME --actor \"Full Name\""}`. Records `last_resume_at` in `connector_meta`.
  - `how_to_play` text (exact):
    ```
    1. Check facts with scene or lookup; never rely on memory for names, numbers, places or who knows what.
    2. Consequential intentions go through act first; narrate only what it returns.
    3. Passing time goes through advance; the player directs significant skips.
    4. Record lasting improvised details with note.
    5. Every act, advance and note needs a fresh call_id; reuse it only to retry the same call.
    ```

- [ ] **Step 1: Write the failing test:** rulebook contains "Close third person, past tense" and "Don't switch to italic reported speech" and "narrate"/"after `act`"; `resume` on a world with a protagonist has all keys and JSON ≤ 12,000 chars; `resume` with no player row returns `needs_setup`.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(connector): resume with GM rulebook`.

### Task 7: MCP server and desktop registration

**Files:**
- Create: `connector/server.py`, `connector/run_server.py`, `connector/README.md`
- Test: `tests/connector_server_test.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `connector/server.py`: `mcp = FastMCP("caerness", instructions="Caerness game connector. At the start of a Caerness chat call resume and follow the rulebook it returns.")` with exactly six tools: `resume()`, `scene()`, `lookup(query: str)`, `act(call_id: str, action_type: str, intent: str, target_actor_id: int | None = None, target_location_id: int | None = None, interaction_id: int | None = None, response_choice: str | None = None)`, `advance(call_id: str, days: int, purpose: str)`, `note(call_id: str, subject_kind: str, subject_id: int | None, text: str)`. Docstrings one or two short sentences each. Each tool opens `connect_campaign()`, runs the view/operation with `contextlib.redirect_stdout(sys.stderr)`, closes, and returns the dict. Exceptions become `{"error": "<message>"}`, never a traceback.
  - `main()` reads `CAERNESS_CAMPAIGN` (default `main`), calls `open_campaign`, then `mcp.run()` (stdio).
  - `connector/run_server.py`: inserts the repo root into `sys.path`, forces UTF-8 on stdio (`sys.stdout.reconfigure(encoding="utf-8")`, same for stdin/stderr), calls `server.main()`.
  - `connector/README.md`: setup in five steps: install requirements; `setup_campaign.py --campaign main --actor "<name>"`; add to `%APPDATA%\Claude\claude_desktop_config.json`:
    ```json
    {"mcpServers": {"caerness": {
      "command": "C:\\Users\\NozzE\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
      "args": ["D:\\Code\\Caerness\\connector\\run_server.py"],
      "env": {"CAERNESS_CAMPAIGN": "main"}}}}
    ```
    restart the app; in a new chat type `resume`.

- [ ] **Step 1: Write the failing test:**
  - list the registered tools (via the FastMCP tool manager / `await mcp.list_tools()`); exactly the six names; `len(json.dumps([t.model_dump() for t in tools])) <= 6000`;
  - call each tool function in-process against a demo campaign in a temp `CAERNESS_CAMPAIGN_DIR`; every return is a dict without `"error"` (for `act` use `observe`);
  - **stdout guard:** monkeypatch an engine function used by `scene` to `print("noise")`; capture real stdout during the tool call; assert nothing was written to stdout;
  - a tool given a bad id returns `{"error": ...}` rather than raising.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect pass.** Then run the full suite: `"$PY" tools/run_suite.py --out runs/suite` and `git restore game/campaign_01/model_requests/`; expect no regressions from before this branch.
- [ ] **Step 5: Commit** `feat(connector): MCP server with six tools and desktop setup notes`.

### Task 8: Owner play check (manual acceptance)

Not code. The implementer prepares; the owner plays.

- [ ] **Step 1:** Run `setup_campaign.py --campaign main --actor "<person chosen with the owner>"`, add the config entry (back up the existing `claude_desktop_config.json` first and merge, never overwrite other servers), and ask the owner to restart the Claude desktop app.
- [ ] **Step 2:** The owner, in a new normal chat: types `resume`; plays a short scene; asks a parenthetical question their character would know; speaks to someone present; travels somewhere; waits a few days.
- [ ] **Step 3: Checks** (the implementer reads the campaign DB afterwards):
  - each consequential outcome in the chat matches a `connector_calls` row and the engine state (location, day);
  - no outcome was narrated that has no matching call (if one was, record it: this is the "skipped tool" risk, spec §13);
  - the owner opens a **second new chat**, types `resume`, and the scene, day and place match where the first chat ended;
  - the owner judges the voice against Appendix A (direct speech, third person past, no italics for speech).
- [ ] **Step 4:** Write findings (what worked, tool-call misses, token impressions, owner's judgement) to `docs/superpowers/plans/2026-10-16-claude-connector-step1-playcheck.md` and commit. These feed the step-2 plan.
