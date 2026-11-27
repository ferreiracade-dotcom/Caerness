# Three levels: schema and tool contract (step 2, first artifact)

This fixes the names later tasks build on. It implements `2026-11-26-three-levels-design.md`, revision 3.1. Where a
table already exists and fits, it is extended rather than duplicated. The old `pressures` and `decisions` tables belong
to the old decision loop, whose personal choices Task 2b switches off in Saint Jude (the outfit choices still write `decisions`); they are left alone otherwise; the new ones have distinct names. The
addiction tables `dependency_profiles` and `dependency_exposures` are unrelated, so the design's "dependencies" table
is called `exposure_links`.

## Schema 134 (engine/schema.sql + migration in engine/db.py)

**Who is simulated how**
- `actors.sim_resolution TEXT NOT NULL DEFAULT 'materialized_minor' CHECK IN ('materialized_minor','notable','active')`.
  Separate from `entity_resolution.resolution_level`, which stays as the old cadence system (design section 8 keeps
  `tiers.py`). Set by `engine/levels.py` (rules below).
- `actors.closeness_to_me REAL`, NULL by default, refreshed by `levels.refresh`. Power is read from seats directly
  (revision 5.3).

**Scenes and stamps**
- `gm_scenes(id, opened_day, closed_day NULL, location_id NULL, status CHECK IN ('open','closed','abandoned'),
  opened_call_id, closed_call_id NULL)`. At most one row with `status='open'` (partial unique index).
- `scene_participants(scene_id, actor_id, joined_after_beat INT NULL, left_after_beat INT NULL,
  attention CHECK IN ('involved','attentive','overheard','distracted') DEFAULT 'involved', PRIMARY KEY(scene_id, actor_id))`.
- `scene_stamps(id, scene_id, beat INT, kind CHECK IN ('claim','lie','promise','money','goods','injury','enter','leave',
  'walkout','decision','other'), actor_id NULL, target_actor_id NULL, text, holds_true INT NULL CHECK IN (0,1),
  ref_table NULL, ref_id NULL, due_in_days INT NULL (revision 5.6), call_id, status CHECK IN ('stamped','confirmed','amended','struck') DEFAULT 'stamped')`.
  `beat` counts up from 1 within a scene.

**Causes and rollback keys**
- `causal_chains(id, day, origin_kind CHECK IN ('scene','turning_event','decision','world_process','player_act'),
  origin_id INT, summary)`.
- Add `source_scene_id INT NULL` and `causal_chain_id INT NULL` to: `knowledge`, `relationship_history`, `obligations`,
  and every new table below that can be derived. 
- `record_changes(id, day, source_scene_id NULL, causal_chain_id NULL, table_name, row_id, op CHECK IN ('insert',
  'update'), before_json NULL)`. This is one generic log of every write made while a scene or
  chain is current. It covers:
  - status changes to rows that already existed (an obligation fulfilled, a concern resolved);
  - overwrites of `record_standing`;

  Every new module writes through `rollback.log_insert`, `rollback.log_update`. The log also traces chains.

  Rules:
  - **Discrete values** (`record_standing`, statuses) are logged as `update` with `before_json`. Undo restores the
    old value only if no later `record_changes` row touches the same `(table_name, row_id)`. Otherwise it leaves the
    row and names it in `left`.
  - **Inserts** are deleted on undo.
  - **Outside a context** (no `rollback.current`), the log functions do nothing, so the weekly ticks don't fill it.
  - **Ties** (`relationships`) are never logged here. Undo inverts them from
    `relationship_history` only, so nothing is reverted twice.
  - **Keys:** `rollback.py` keeps an explicit table-to-key map, for tables like `actor_routines` that are keyed on
    `actor_id`. A table missing from the map is refused, never guessed.
- Money is never deleted on undo. `undo_scene` walks `scene_stamps(ref_table, ref_id)` and posts a reversing money
  record for each money stamp, so the ledger stays honest. An authored row (`authored_entities`, connector schema,
  gains `reverted_day NULL`) is marked reverted when nothing after the scene refers to it. Otherwise it stays, and
  it is named in the result.

**Ties by context**
- `tie_contexts` is not built here (revision 5.2; steps 6 to 8).

**Record standing** (design 3 and amendment 3)
- `record_standing(id, subject_kind CHECK IN ('actor','location','business','outfit','household'), subject_id,
  attribute TEXT, standing CHECK IN ('confirmed','inferred'), holds INT NULL CHECK IN (0,1), value_text NULL, day,
  source_scene_id NULL, causal_chain_id NULL, UNIQUE(subject_kind, subject_id, attribute))`.
  No row means unknown. `confirmed` with `holds=0` means "checked, and it is not so".

**Knowledge** (extend `knowledge`)
- `basis CHECK IN ('saw','told','read','heard_rumour','inferred','felt') NULL`, `carrier_actor_id NULL`,
  `path_kind CHECK IN ('self','told','talk','media','mail') NULL` (revision 5.9: how it reached him, generic),
  `channel TEXT NULL` (the package's `news_paths` key for `talk` and `media`, such as `paper`, `television` or
  `parish`; checked against the package, never listed in the engine),
  `holds_true INT NULL` (is the belief actually correct), plus the two rollback keys. Rows without `path_kind` are legacy and
  never reach the news gate.

**Pressure, concern, decision** (amendment 4)
- `actor_pressures(id, actor_id, domain TEXT, since_day, UNIQUE(actor_id, domain))` (revision 5:
  when a condition began to hold, nothing more). `domain` is a package key.
- `actor_concerns(id, actor_id, kind CHECK IN ('owes','owed','wants','resents','fears_for','courts','plans','needs'),
  object_kind NULL CHECK IN ('actor','business','location','outfit','money','work'), object_id NULL,
  origin_kind CHECK IN ('scene','exposure','other_act','chance','buildup','noticed','conduct','opportunity'), origin_text, strength REAL NOT NULL DEFAULT 0.5 (0..1),
  status CHECK IN ('live','waiting','resolved','dropped') DEFAULT 'live', opened_day,
  source_scene_id NULL, causal_chain_id NULL)`.
- `actor_decisions(id, actor_id, concern_id NULL, action TEXT, target_kind NULL, target_id NULL, reason TEXT,
  due_day NULL, status CHECK IN ('pending','fired',
  'dropped','failed','lapsed') DEFAULT 'pending', decided_day, fired_day NULL,
  offer_to_actor_id NULL, told_day NULL, expires_day NULL, on_expiry CHECK IN ('lapse','escalate') NULL,
  source_scene_id NULL, causal_chain_id NULL)`. `action` is a key from the package's generic action set, or the
  reserved `stated` for a decision the GM stamped in a scene (the stamp text is the reason). A decision with
  `offer_to_actor_id` is an offer or demand that waits on that person (design 3, "what waits").
- `offscreen_evaluations(id, day, actor_id, concern_id NULL, why, chosen_action, reason)`: every weighing,
  including those that ended in `do_nothing`, so a world that never does something can be explained.

**News waiting with a carrier** (amendment 6)
- `pending_news(id, carrier_actor_id, recipient_actor_id, knowledge_id, urgent INT 0/1, created_day,
  delivered_scene_id NULL, delivered_day NULL, causal_chain_id NULL)`. The carrier's own knowledge row stays where it
  is. The recipient gets a knowledge row only when the news is delivered, either in a scene with the carrier or by a
  call or visit (urgent items in town). Once delivered, it is never offered again.
  - **A scene delivers at `close_scene`, not when a brief is shown.** The brief is read-only. It lists items where
    `delivered_scene_id` is unset, or equals the open scene's id, so `resume` and repeated briefs show the same
    thing.
  - **The delivered row keeps its chain.** It copies `pending_news.causal_chain_id` and is logged through
    `rollback`, so undoing the chain also removes news that was already delivered.
  - **Carriers can be one step removed.** A carrier is the affected person if he is tied to the recipient. Otherwise
    it is a member of the affected person's household, or close kin of his, who is tied to the recipient (Carla, for
    her father's shop). That carrier learns it from home (`basis` told).

**Channels** (amendment 5)
- No subscription table: `engine/channels.py` derives who is attached to a channel from existing links (employer,
  organisation seat, residence, workplace, routine places).
- `exposure_links(id, actor_id, link_kind CHECK IN ('debt','supplier','protection','customer','competitor'), other_kind, other_id,
  since_day, ended_day NULL, source_scene_id NULL, causal_chain_id NULL)`: only the links with no existing structure.
- `channel_shocks(id, day, channel_kind CHECK IN ('business','location','outfit','sector'), channel_id, shock_kind TEXT,
  magnitude REAL, summary, causal_chain_id NOT NULL)`. `shock_kind` is a package key.
- `scheduled_effects(id, due_day, effect_kind TEXT, payload_json, status CHECK IN ('pending','done','cancelled')
  DEFAULT 'pending', causal_chain_id NOT NULL)`: delayed effects on the due-queue.

**Routines** (amendment 8)
- `actor_routines(actor_id PK, home_location_id NULL, work_location_id NULL, haunts_json DEFAULT '[]',
  schedule_key TEXT)`: `schedule_key` names a package schedule (which part of which day is work, home or haunt).
- `routine_exceptions(id, actor_id, kind CHECK IN ('ill','travel','event','prison','away'), from_day, to_day NULL,
  location_id NULL, source_scene_id NULL, causal_chain_id NULL)`.
- Routines are seeded by `routines.seed` when the opening is built, and for anyone newly notable or active on
  `levels.refresh`. Home comes from the household, work from the employer or the business he owns, and the schedule
  from his position.

**Engine answers**
- Revision 5.2: no table. Consequence facts come back in the tool result as `answers`. A refusal carries
  `owner_notice`.

**Nominations (revision 4)**
- `nominations(id, day, kind, actor_ids_json, cause, causal_chain_id NULL, status CHECK IN
  ('new','planned','realized','declined','applied'), plan_text NULL, by_day NULL, reminded_day NULL,
  decline_reason NULL, realized_scene_id NULL, applied_day NULL, payload_json)` (`payload_json`: revision 5.2).
- Revision 4.1:
  - `knowledge` gains `spread_from_day NULL` (outward spread, Task 10a).
  - Nomination kinds include `neglect`, `wronged`, `broken_promise`, `jealousy` and `lie_found_out` (revision 5).
  - `nominations` gains `weight REAL` and `applied_small INTEGER DEFAULT 0` (the budget).
- Revision 5.1: nomination kind `seat_decision` (a decision of a seat he holds, shown in `waiting_on_you`);
  `create_protagonist`'s account gains `displaced` (`actor_id`, `reason`) for a start in a held seat.

## Package data (worlds/saintjude/levels.json; validated on load, carries `"version": 1`)
`mover_roles` (which seats and offices make someone a mover), `close_rule` (tie thresholds for being close),
`lock_quiet_days` (45), `familiarity_step` and `familiarity_decay` (company in a scene), `tie_steps` (what
`small`, `medium` and `large` mean for each tie dimension), `tie_concern_line` (a tie step that opens a concern),
`acute_shock_line` (a felt shock large enough to open a concern straight away, for notable as well as active people),
`urgent_kinds` (news that a close tie phones or calls round about, in town), `pressures` (domains, the existing values each reads, and its line in weeks), `actions` (the generic action set: key, which concerns it serves, what it needs, habit weight, what it
does when fired), `shocks` (shock kinds: what each changes, such as money, takings or demand, and when it opens a concern), `schedules`,
`news_paths` (everyday channels, now including `television` (revision 5.7), what each carries, and its `kind`,
`media` or `talk` (revision 5.9)), `answers` (the cash share above which money is weighty),
`nominations` (default and longest timeframe in days, reminder lead, weekly budget, weight per kind),
`conduct` (quiet days by closeness, and how long a wrong waits before it surfaces), `news_paths.spread`
(delay per hop, drop-off, chance of a detail changing), `long_sentence_days`, `delegation` (revision 5.1: which decisions of a seat he holds are his), `visible_spend` (revision 5.2), `stated_due_days` (14; revision 5.5), `noticing` (which facts interest which
mover roles), `opportunities` (revision 5.8: the cash line and the struggling line). `mover_roles` includes
political offices and, from revision 5.8, `business_line` (the size of business whose owner is a mover).

## Tool contract (connector/server.py)
- Revision 4: `note(kind="plan", nomination, by_day, text)` sets the GM's timeframe, or with `decline=reason`
  declines; `author` and `close_scene` take `realizes=<nomination id>`. `brief.full` and the skip result list
  `nominations` (new, to remind, overdue, and the small ones applied). `brief.full` has a `you` part. Tool results give facts and numbers in fields, not engine prose.
- **People are a name or an id everywhere** (`close_scene`, stamps, threads). Names are matched against the open
  scene's people first, then the protagonist's known people. An ambiguous name, such as a first name two people share,
  is refused with the candidates. "me" is the protagonist.
- `note(kind="scene", text, present, location=None)`: opens a scene if none is open. `location` is a place name or
  id; without it, it is the protagonist's stored place. A new scene with a location moves him there, through the
  same check as `act travel`. At the open scene's place, the note updates presence. At a different place while a
  scene is open, it is refused with one line: close the current scene first (`close_scene`, or
  `mode="from_stamps"`). Returns `scene_id` and the full brief (connector/brief.py).
- `note(kind="stamp", text, stamp={"kind", "by", "to", "true", "due_in_days"})`: a speech-only beat, using a new `stamp` parameter
  so that `field` and `present` keep their meanings. `true: false` marks a lie or a mistake. Arrivals and departures
  mid-scene are stamps of kind `enter` and `leave`. Returns `{"stamp": {beat, kind, text}}`.
- During an open scene, each `act`, `money` and `note` result carries `changed`: only what that call changed. There
  is no cursor for the GM to track.
- `act`, `money`, `author` stamp themselves while a scene is open, add `stamp` to their result. Results carry `answers: [{kind, text}]` when the engine has a note.
- **New tool** `close_scene(call_id, mode="commit", participants=None, amendments=None, exceptions=None, ties=None,
  threads=None)`. `mode`: `review` returns the ledger and commits nothing; `commit` applies the four fields;
  `from_stamps` commits the ledger as stamped. Shapes:
  - `participants`: `[{"who": "Carla", "joined_after_beat": 3, "left_after_beat": 5, "attention": "overheard"}]`
    (only the exceptions). Anyone in the scene's presence list is otherwise involved for the whole scene. Stamped
    `enter` and `leave` beats already set the times.
  - `amendments`: `[{"beat": 4, "status": "struck"}]` or `[{"beat": 4, "text": "...", "true": false}]`. Beats are
    the numbers the ledger and each stamp result show.
  - `exceptions`: `[{"beat": 2, "missed_by": ["Frank"]}, {"beat": 2, "disbelieved_by": ["Ma"]},
    {"secret": "text", "known_to": ["me", "Frank"]}]`.
  - `ties`: `[{"from": "Ma", "to": "me", "change": {"trust": "-small"}, "cause": "one line"}]`.
    Steps are `small`, `medium` or `large`, with a sign, mapped to numbers by `tie_steps`. The GM never sees or sends
    a raw score.
  - `threads`: `[{"kind": "owed", "by": "Frank", "to": "me", "text": "$40 for the parts", "due_in_days": 4}]` or
    `[{"kind": "meeting", "with": ["Tullio"], "text": "the club, Tuesday", "due_in_days": 5}]`. The kinds are
    `owed`, `meeting` and `promise`.
  - A scene with no stamps and no fields closes cleanly as an ordinary one.
  - **All or nothing:** if any reference fails (an ambiguous or unknown name, a beat that doesn't exist, a
    participant who wasn't there), nothing is committed. The scene stays open, and the result lists each failure
    with its candidates, so the GM fixes the call and sends it again.
  - **Thread shapes:** `owed` and `promise` take `by` and `to`, and become one obligation of `by` toward `to`.
    `meeting` takes `with: [...]` and becomes one obligation row per person listed.
  - **Disbelief:** `disbelieved_by` still gets a knowledge row ("heard X say it"), at confidence 0.1. Knowing that a
    claim was made matters even when it isn't believed.
  - **Secrets:** `secret` defaults to `holds_true=1` and reaches only `known_to`, whoever else was present.
- `advance` refuses while a scene is open, naming `close_scene(mode="from_stamps")`. `resume` returns an open scene
  as it stands and never closes it.
- `author(kind="turning_event", details={channels: [{kind, id or name}], shock, summary, magnitude})`.
- `correct(op="undo_scene", details={"scene": id})` and `correct(op="undo_chain", details={"chain": id})`, on the
  player's explicit yes like every `correct` op.

## Engine module surface
- `engine/levels.py`: `refresh(conn, day) -> dict`, `resolution_of(conn, actor_id) -> str`.
- `engine/scenes.py`: `open_scene`, `open_scene_id`, `stamp`, `ledger`, `close(conn, call_id, mode, **fields) -> dict`.
- `engine/rollback.py`: `current(conn, scene_id=None, chain_id=None)` (context manager setting what new writes are
  keyed to), `log_insert(conn, table, row_id)`, `log_update(conn, table, row_id, before: dict)`,
    `undo_scene(conn, scene_id) -> dict`, `undo_chain(conn, chain_id) -> dict`.
- `engine/routines.py` also has `seed(conn, actor_ids=None) -> int`.
- `engine/news_gate.py` also has `hold(conn, carrier, recipient, knowledge_id, urgent, chain_id) -> int` and
  `deliver(conn, pending_ids, scene_id=None) -> int`.
- `engine/answers.py`: `judge(conn, tool, actor_id, change: dict) -> list[dict]`.
- `engine/standing.py`: `confirm`, `standing_of` (`infer` waits for step 8).
- `engine/news_gate.py`: `reaches(conn, me, start_day, end_day) -> list[dict]`, `held_for(conn, me, carrier) -> list[dict]`.
- `engine/conduct.py`: `weekly(conn, day) -> list[int]`, `lies(conn, day) -> list[int]` (revision 4.1).
- `engine/news_gate.py` also has `spread(conn, day) -> int` (revision 4.1) and
  `publish_media(conn, day, channel, text, *, subject_actor_id=None, chain_id=None) -> int` (revision 5.9: the one
  writer of paper, radio and television items).
- `engine/nominations.py`: `near`, `nominate`, `plan`, `decline`, `realize`, `due`, `apply_overdue` (replaces
  `engine/protection.py`, which is not built).
- `engine/routines.py`: `where(conn, actor_id, day, part) -> int | None`.
- `engine/channels.py`: `attached(conn, channel_kind, channel_id) -> list[tuple[int, str]]`, `publish(conn, shock_id) -> list[dict]`, `run_due_effects(conn, day) -> int` (revision 5.5).
- `engine/pressure.py`: `build(conn, day, actor_ids) -> list[int]` (ids of new concerns).
- `engine/offscreen.py`: `weigh(conn, actor_id, day, why) -> int | None`, `fire_due(conn, day) -> list[int]`.
- `engine/levels_tick.py`: process key `levels`, weekly, registered in `build_default_process_registry` (Task 14a).
