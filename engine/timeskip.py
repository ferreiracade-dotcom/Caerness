from __future__ import annotations

import json
import sqlite3
from typing import Any

from .competence import process_competence
from .simulation import advance_connection, current_day


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


def _policy_threshold(policy: str) -> int:
    return {"all": 3, "meaningful": 4, "critical_only": 5}[policy]


def prepare_time_skip(
    conn: sqlite3.Connection,
    actor_id: int,
    days: int,
    *,
    focus: list[dict[str, Any]] | None = None,
    delegation: dict[str, Any] | None = None,
    interruption_policy: str = "meaningful",
    max_chunk_days: int = 30,
) -> int:
    if days < 1:
        raise ValueError("days must be >= 1")
    if interruption_policy not in {"all", "meaningful", "critical_only"}:
        raise ValueError("invalid interruption_policy")
    actor = conn.execute("SELECT id FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not actor:
        raise ValueError(f"No actor #{actor_id}")
    start = current_day(conn)
    focus_items = list(focus or [])
    weights = [max(0.01, min(1.0, float(x.get("weight", 1.0)))) for x in focus_items]
    total = sum(weights)
    if total > 1.000001:
        raise ValueError("time-skip focus weights may not sum to more than 1.0")
    cur = conn.execute(
        """INSERT INTO time_skip_runs(
               actor_id,start_day,requested_end_day,planned_days,status,focus_json,delegation_json,
               interruption_policy,max_chunk_days
           ) VALUES (?,?,?,?, 'prepared',?,?,?,?)""",
        (actor_id, start, start + days, days, _json(focus_items), _json(delegation or {}), interruption_policy,
         max(1, min(365, int(max_chunk_days)))),
    )
    run_id = int(cur.lastrowid)
    for idx, item in enumerate(focus_items):
        key = str(item.get("key") or item.get("domain") or f"focus_{idx+1}")
        desc = str(item.get("description") or key)
        domain = item.get("domain")
        career_id = item.get("career_id")
        weight = max(0.01, min(1.0, float(item.get("weight", 1.0))))
        conn.execute(
            """INSERT INTO time_skip_focus_progress(run_id,focus_key,description,domain_key,career_id,weight)
               VALUES (?,?,?,?,?,?)""",
            (run_id, key, desc, domain, career_id, weight),
        )
    return run_id


def _delegated(run: sqlite3.Row, kind: str, source_id: int | None, interaction_type: str | None = None) -> bool:
    data = _load(run["delegation_json"], {})
    if kind == "obligation" and source_id is not None:
        return int(source_id) in {int(x) for x in data.get("delegated_obligation_ids", [])}
    if kind == "interaction" and interaction_type:
        return interaction_type in set(data.get("delegated_interaction_types", []))
    return False


def _earliest_existing_due(conn: sqlite3.Connection, run: sqlite3.Row, from_day: int, to_day: int) -> int | None:
    actor_id = int(run["actor_id"])
    threshold = _policy_threshold(str(run["interruption_policy"]))
    rows = conn.execute(
        """SELECT o.id,o.due_day,o.importance,ci.auto_policy
           FROM obligations o LEFT JOIN character_intentions ci ON ci.id=o.intention_id
           WHERE o.actor_id=? AND o.status='active' AND o.due_day>? AND o.due_day<=? AND o.importance>=?
           ORDER BY o.due_day,o.id""",
        (actor_id, from_day, to_day, threshold),
    ).fetchall()
    for row in rows:
        if row["auto_policy"] == "routine":
            continue
        if not _delegated(run, "obligation", int(row["id"])):
            return int(row["due_day"])
    return None


def _find_interruptions(
    conn: sqlite3.Connection,
    run: sqlite3.Row,
    *,
    start_day: int,
    end_day: int,
    event_floor: int,
    interaction_floor: int,
) -> list[dict[str, Any]]:
    actor_id = int(run["actor_id"])
    threshold = _policy_threshold(str(run["interruption_policy"]))
    actor = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    location_id = actor[0] if actor else None
    found: list[dict[str, Any]] = []

    events = conn.execute(
        """SELECT e.*,
                  EXISTS(SELECT 1 FROM event_targets et WHERE et.event_id=e.id AND et.actor_id=?) direct_target
           FROM events e
           WHERE e.id>? AND e.day>? AND e.day<=? AND e.severity>=?
           ORDER BY e.day,e.id""",
        (actor_id, event_floor, start_day, end_day, threshold),
    ).fetchall()
    for e in events:
        relevant = int(e["direct_target"]) == 1 or e["source_actor_id"] == actor_id or (
            location_id is not None and e["location_id"] == location_id and int(e["severity"]) >= threshold
        )
        if relevant:
            found.append({
                "day": int(e["day"]), "source_kind": "event", "source_id": int(e["id"]),
                "severity": int(e["severity"]), "reason": f"{e['title']}: {e['summary']}",
                "metadata": {"event_type": e["event_type"]},
            })

    interactions = conn.execute(
        """SELECT * FROM interactions
           WHERE id>? AND recipient_actor_id=? AND created_day>? AND created_day<=? AND status='pending' AND stakes>=?
           ORDER BY created_day,id""",
        (interaction_floor, actor_id, start_day, end_day, threshold),
    ).fetchall()
    for i in interactions:
        if _delegated(run, "interaction", int(i["id"]), str(i["interaction_type"])):
            continue
        found.append({
            "day": int(i["created_day"]), "source_kind": "interaction", "source_id": int(i["id"]),
            "severity": int(i["stakes"]),
            "reason": f"A consequential {i['interaction_type']} now requires your attention.",
            "metadata": {"interaction_type": i["interaction_type"], "proposer_actor_id": i["proposer_actor_id"]},
        })

    obligations = conn.execute(
        """SELECT o.*,ci.auto_policy FROM obligations o
           LEFT JOIN character_intentions ci ON ci.id=o.intention_id
           WHERE o.actor_id=? AND o.status='active' AND o.due_day>? AND o.due_day<=? AND o.importance>=?
           ORDER BY o.due_day,o.id""",
        (actor_id, start_day, end_day, threshold),
    ).fetchall()
    for o in obligations:
        if o["auto_policy"] == "routine" or _delegated(run, "obligation", int(o["id"])):
            continue
        found.append({
            "day": int(o["due_day"]), "source_kind": "obligation", "source_id": int(o["id"]),
            "severity": int(o["importance"]), "reason": f"An important obligation is due: {o['description']}",
            "metadata": {},
        })
    found.sort(key=lambda x: (x["day"], -x["severity"], x["source_kind"], x["source_id"] or 0))
    return found


def _present_actor_ids(conn: sqlite3.Connection, actor_id: int) -> tuple[int | None, set[int]]:
    row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    loc = int(row[0]) if row and row[0] is not None else None
    if loc is None:
        return None, set()
    ids = {int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE current_location_id=?", (loc,)).fetchall()}
    return loc, ids


def _accumulate_focus(conn: sqlite3.Connection, run_id: int, elapsed_days: int) -> None:
    if elapsed_days <= 0:
        return
    rows = conn.execute("SELECT * FROM time_skip_focus_progress WHERE run_id=?", (run_id,)).fetchall()
    for row in rows:
        gain = float(elapsed_days) * float(row["weight"])
        conn.execute(
            "UPDATE time_skip_focus_progress SET accumulated_days=accumulated_days+? WHERE id=?",
            (gain, int(row["id"])),
        )
        # Accumulate exposure without granting automatic score increases. Later career/training
        # resolvers may convert this evidence into advancement using their own rules.
        if row["domain_key"]:
            comp = conn.execute(
                """SELECT ac.id,ac.experience_json FROM actor_competence ac
                   JOIN competence_domains d ON d.id=ac.domain_id
                   WHERE ac.actor_id=(SELECT actor_id FROM time_skip_runs WHERE id=?) AND d.domain_key=?
                   ORDER BY ac.score DESC LIMIT 1""",
                (run_id, row["domain_key"]),
            ).fetchone()
            if comp:
                exp = _load(comp["experience_json"], {})
                exp["time_skip_focus_days"] = round(float(exp.get("time_skip_focus_days", 0.0)) + gain, 3)
                exp["last_time_skip_run_id"] = run_id
                conn.execute("UPDATE actor_competence SET experience_json=?,updated_day=? WHERE id=?",
                             (_json(exp), current_day(conn), int(comp["id"])))
        if row["career_id"]:
            career = conn.execute("SELECT experience_json FROM actor_careers WHERE id=?", (row["career_id"],)).fetchone()
            if career:
                exp = _load(career["experience_json"], {})
                exp["time_skip_focus_days"] = round(float(exp.get("time_skip_focus_days", 0.0)) + gain, 3)
                exp["last_time_skip_run_id"] = run_id
                conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (_json(exp), int(row["career_id"])))


def _record_interrupt(conn: sqlite3.Connection, run_id: int, item: dict[str, Any]) -> int:
    cur = conn.execute(
        """INSERT INTO time_skip_interruptions(run_id,day,source_kind,source_id,reason,severity,requires_player,metadata_json)
           VALUES (?,?,?,?,?,?,1,?)""",
        (run_id, item["day"], item["source_kind"], item.get("source_id"), item["reason"], item["severity"],
         _json(item.get("metadata", {}))),
    )
    return int(cur.lastrowid)


def _finalize(conn: sqlite3.Connection, run: sqlite3.Row, status: str, *, interruption: dict[str, Any] | None = None) -> dict[str, Any]:
    end = current_day(conn)
    focuses = [dict(r) for r in conn.execute(
        "SELECT focus_key,description,domain_key,career_id,weight,accumulated_days FROM time_skip_focus_progress WHERE run_id=? ORDER BY id",
        (int(run["id"]),),
    ).fetchall()]
    summary = {
        "elapsed_days": end - int(run["start_day"]),
        "planned_days": int(run["planned_days"]),
        "focus": focuses,
        "interruption": interruption,
        "player_summary": (
            f"{end - int(run['start_day'])} in-world day(s) passed before the time skip was interrupted."
            if status == "interrupted" else
            f"The planned {int(run['planned_days'])}-day time skip completed."
        ),
    }
    conn.execute(
        """UPDATE time_skip_runs SET status=?,actual_end_day=?,summary_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (status, end, _json(summary), int(run["id"])),
    )
    if end > int(run["start_day"]):
        conn.execute(
            """INSERT INTO historical_anchors(
                   entity_kind,entity_id,anchor_type,start_day,end_day,summary,detail_json,
                   source_kind,source_id,certainty,canon_scope,immutable,created_day
               ) VALUES ('actor',?,'time_skip_period',?,?,?,?, 'player_action',NULL,1.0,'campaign',1,?)""",
            (int(run["actor_id"]), int(run["start_day"]), end,
             summary["player_summary"], _json({"time_skip_run_id": int(run["id"]), "focus": focuses}), end),
        )
    return time_skip_run(conn, int(run["id"])) or summary


def resolve_time_skip(conn: sqlite3.Connection, run_id: int) -> dict[str, Any]:
    run = conn.execute("SELECT * FROM time_skip_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"No time skip #{run_id}")
    if run["status"] not in {"prepared", "running"}:
        return time_skip_run(conn, run_id) or {}
    if current_day(conn) != int(run["start_day"]) and run["status"] == "prepared":
        raise ValueError("A prepared time skip must begin on the day it was created.")
    conn.execute("UPDATE time_skip_runs SET status='running',updated_at=CURRENT_TIMESTAMP WHERE id=?", (run_id,))
    target = int(run["requested_end_day"])

    while current_day(conn) < target:
        now = current_day(conn)
        remaining = target - now
        chunk = min(int(run["max_chunk_days"]), remaining)
        due = _earliest_existing_due(conn, run, now, now + chunk)
        if due is not None:
            chunk = min(chunk, due - now)
        if chunk < 1:
            chunk = 1

        event_floor = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0])
        interaction_floor = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM interactions").fetchone()[0])
        conn.execute("SAVEPOINT timeskip_preview")
        advance_connection(conn, chunk)
        preview_end = current_day(conn)
        hits = _find_interruptions(
            conn, run, start_day=now, end_day=preview_end,
            event_floor=event_floor, interaction_floor=interaction_floor,
        )
        if hits:
            first_day = int(hits[0]["day"])
            conn.execute("ROLLBACK TO timeskip_preview")
            conn.execute("RELEASE timeskip_preview")
            advance_connection(conn, max(1, first_day - now))
            elapsed = current_day(conn) - now
            _accumulate_focus(conn, run_id, elapsed)
            loc, present = _present_actor_ids(conn, int(run["actor_id"]))
            competence = process_competence(conn, int(run["actor_id"]), current_location_id=loc, present_actor_ids=present)
            need_player = [o for o in competence if o.outcome == "needs_player"]
            if need_player:
                hit = {
                    "day": current_day(conn), "source_kind": "competence", "source_id": need_player[0].intention_id,
                    "severity": 4, "reason": f"A previously established intention now requires a fresh decision: {need_player[0].summary}",
                    "metadata": {},
                }
            else:
                # Recompute after authoritative replay so source ids are guaranteed to refer to committed rows.
                committed_hits = _find_interruptions(
                    conn, run, start_day=now, end_day=current_day(conn),
                    event_floor=event_floor, interaction_floor=interaction_floor,
                )
                hit = committed_hits[0] if committed_hits else hits[0]
            _record_interrupt(conn, run_id, hit)
            return _finalize(conn, run, "interrupted", interruption=hit)

        conn.execute("RELEASE timeskip_preview")
        elapsed = preview_end - now
        _accumulate_focus(conn, run_id, elapsed)
        loc, present = _present_actor_ids(conn, int(run["actor_id"]))
        competence = process_competence(conn, int(run["actor_id"]), current_location_id=loc, present_actor_ids=present)
        need_player = [o for o in competence if o.outcome == "needs_player"]
        if need_player:
            hit = {
                "day": current_day(conn), "source_kind": "competence", "source_id": need_player[0].intention_id,
                "severity": 4, "reason": f"A previously established intention now requires a fresh decision: {need_player[0].summary}",
                "metadata": {},
            }
            _record_interrupt(conn, run_id, hit)
            return _finalize(conn, run, "interrupted", interruption=hit)

    return _finalize(conn, run, "completed")


def time_skip_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM time_skip_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["focus"] = _load(out.pop("focus_json"), [])
    out["delegation"] = _load(out.pop("delegation_json"), {})
    out["summary"] = _load(out.pop("summary_json"), {})
    out["focus_progress"] = [dict(r) for r in conn.execute(
        "SELECT * FROM time_skip_focus_progress WHERE run_id=? ORDER BY id", (run_id,)
    ).fetchall()]
    interruptions = []
    for r in conn.execute("SELECT * FROM time_skip_interruptions WHERE run_id=? ORDER BY day,id", (run_id,)).fetchall():
        d = dict(r)
        d["metadata"] = _load(d.pop("metadata_json"), {})
        interruptions.append(d)
    out["interruptions"] = interruptions
    return out
