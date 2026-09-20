from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from .simulation import advance_connection
from .player import process_camera_succession


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def world_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    def count(table: str, where: str = "", args: tuple[Any, ...] = ()) -> int:
        sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else "")
        return int(conn.execute(sql, args).fetchone()[0])

    pop = conn.execute("SELECT COALESCE(SUM(population),0) FROM demographic_cohorts").fetchone()[0]
    pages = int(conn.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    return {
        "day": _day(conn),
        "actors": count("actors"),
        "living_characters": count("actors", "actor_type='character' AND lower(status) NOT IN ('dead','deceased')"),
        "deceased_characters": count("actors", "actor_type='character' AND lower(status) IN ('dead','deceased')"),
        "institutions": count("actors", "actor_type='institution'"),
        "events": count("events"),
        "decisions": count("decisions"),
        "households": count("households"),
        "enterprises": count("civilian_enterprises"),
        "cultural_objects": count("cultural_objects"),
        "education_enrollments": count("education_enrollments"),
        "knowledge_assets": count("knowledge_assets"),
        "religious_institutions": count("religious_institutions"),
        "polities": count("political_polities"),
        "controlled_territories": count("territorial_control"),
        "demographic_population": float(pop or 0),
        "historical_anchors": count("historical_anchors"),
        "crystallization_runs": count("crystallization_runs"),
        "camera_actor_id": int(player[0]) if player and player[0] is not None else None,
        "camera_transfers": count("player_camera_history"),
        "database_bytes_approx": pages * page_size,
    }


def contradiction_scan(conn: sqlite3.Connection, *, deep_integrity: bool = True) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    def add(key: str, detail: str, severity: str = "error") -> None:
        issues.append({"severity": severity, "issue_key": key, "detail": detail})

    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    for row in fk:
        add("foreign_key", f"Foreign-key violation: {tuple(row)}")
    # Full SQLite integrity_check scans the whole file. Keep it in direct/manual audits and at
    # stress-run boundaries, but do not rescan a growing multi-decade DB at every 5-year checkpoint.
    if deep_integrity:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if str(integrity).lower() != "ok":
            add("sqlite_integrity", str(integrity))

    bad_pop = conn.execute("SELECT id,population FROM demographic_cohorts WHERE population<0").fetchall()
    for r in bad_pop:
        add("negative_population", f"Cohort #{r['id']} has population {r['population']}")

    # Household heads must still be active members unless the household is dissolved/historical.
    rows = conn.execute("""SELECT h.id,h.head_actor_id,h.status FROM households h
                           WHERE h.head_actor_id IS NOT NULL AND h.status NOT IN ('dissolved','historical')
                           AND NOT EXISTS(SELECT 1 FROM household_members hm WHERE hm.household_id=h.id
                                          AND hm.actor_id=h.head_actor_id AND hm.status='active')""").fetchall()
    for r in rows:
        add("orphan_household_head", f"Household #{r['id']} head #{r['head_actor_id']} is not an active member")

    rows = conn.execute("""SELECT tc.location_id,tc.controller_polity_id FROM territorial_control tc
                           JOIN political_polities p ON p.id=tc.controller_polity_id
                           WHERE p.status='dissolved'""").fetchall()
    for r in rows:
        add("dissolved_polity_controls_territory", f"Dissolved polity #{r['controller_polity_id']} controls location #{r['location_id']}")

    rows = conn.execute("""SELECT e.id,e.primary_teacher_actor_id FROM education_enrollments e
                           JOIN actors a ON a.id=e.primary_teacher_actor_id
                           WHERE e.status='active' AND lower(a.status) IN ('dead','deceased')""").fetchall()
    for r in rows:
        add("dead_active_teacher", f"Enrollment #{r['id']} still active under dead teacher #{r['primary_teacher_actor_id']}")

    rows = conn.execute("""SELECT t.id,t.provider_actor_id FROM medical_treatments t JOIN actors a ON a.id=t.provider_actor_id
                           WHERE t.status='active' AND lower(a.status) IN ('dead','deceased')""").fetchall()
    for r in rows:
        add("dead_treatment_provider", f"Treatment #{r['id']} still active under dead provider #{r['provider_actor_id']}")

    rows = conn.execute("""SELECT o.id,o.actor_id FROM religious_offices o JOIN actors a ON a.id=o.actor_id
                           WHERE o.status='active' AND lower(a.status) IN ('dead','deceased')""").fetchall()
    for r in rows:
        add("dead_religious_officeholder", f"Religious office #{r['id']} still held by dead actor #{r['actor_id']}")

    future_events = conn.execute("SELECT COUNT(*) FROM events WHERE day>?", (_day(conn),)).fetchone()[0]
    if future_events:
        add("future_event", f"{future_events} events are dated after current story time")
    future_knowledge = conn.execute("SELECT COUNT(*) FROM knowledge WHERE learned_day>?", (_day(conn),)).fetchone()[0]
    if future_knowledge:
        add("future_knowledge", f"{future_knowledge} knowledge records are dated after current story time")

    # If a deceased camera actor has an explicitly designated living successor, the handoff should have resolved.
    camera = conn.execute("""SELECT ps.player_actor_id,a.status FROM player_state ps LEFT JOIN actors a ON a.id=ps.player_actor_id WHERE ps.id=1""").fetchone()
    if camera and camera['player_actor_id'] is not None and str(camera['status'] or '').lower() in ('dead','deceased'):
        available = conn.execute("""SELECT 1 FROM player_camera_successors pcs JOIN actors a ON a.id=pcs.successor_actor_id
                                    WHERE pcs.from_actor_id=? AND pcs.status='designated'
                                      AND lower(a.status) NOT IN ('dead','deceased') LIMIT 1""", (camera['player_actor_id'],)).fetchone()
        if available:
            add("stalled_camera_succession", f"Dead camera actor #{camera['player_actor_id']} still has a valid designated successor")

    # Applied crystallization must point to a real produced actor and preserve a lineage trail.
    rows = conn.execute("SELECT id,crystallized_entity_id FROM crystallization_runs WHERE status='applied'").fetchall()
    for r in rows:
        aid = r['crystallized_entity_id']
        if aid is None or not conn.execute("SELECT 1 FROM actors WHERE id=?", (aid,)).fetchone():
            add("broken_crystallization_target", f"Applied crystallization run #{r['id']} lacks its produced actor")
        if not conn.execute("SELECT 1 FROM crystallization_lineage WHERE run_id=?", (r['id'],)).fetchone():
            add("missing_crystallization_lineage", f"Applied crystallization run #{r['id']} has no lineage records")

    # v0.26 ownership-mirror invariants. Each pair has one authoritative owner and one
    # compatibility/read-model mirror; divergence is a real save-integrity problem.
    rows = conn.execute(
        """SELECT a.id,a.status,lp.life_status FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
           WHERE (lower(a.status) IN ('dead','deceased') AND lp.life_status<>'deceased')
              OR (lower(a.status) NOT IN ('dead','deceased') AND lp.life_status='deceased')"""
    ).fetchall()
    for r in rows:
        add('life_status_mirror', f"Actor #{r['id']} status={r['status']} conflicts with life_status={r['life_status']}")

    rows = conn.execute(
        """SELECT l.id,l.political_owner,a.name authoritative_owner
           FROM territorial_control tc
           JOIN locations l ON l.id=tc.location_id
           JOIN political_polities p ON p.id=tc.controller_polity_id
           JOIN actors a ON a.id=p.institution_actor_id
           WHERE COALESCE(l.political_owner,'')<>COALESCE(a.name,'')"""
    ).fetchall()
    for r in rows:
        add('political_owner_mirror', f"Location #{r['id']} political_owner={r['political_owner']!r} but controller is {r['authoritative_owner']!r}")
    rows = conn.execute(
        """SELECT l.id,l.political_owner FROM locations l
           WHERE l.political_owner IS NOT NULL AND trim(l.political_owner)<>''
             AND NOT EXISTS(SELECT 1 FROM territorial_control tc WHERE tc.location_id=l.id)"""
    ).fetchall()
    for r in rows:
        add('legacy_political_owner_uncrystallized', f"Location #{r['id']} retains legacy/descriptive political_owner={r['political_owner']!r} without crystallized territorial_control", severity='warning')

    row = conn.execute(
        """SELECT ps.player_actor_id,ps.current_location_id mirror_location,a.current_location_id authoritative_location
           FROM player_state ps JOIN actors a ON a.id=ps.player_actor_id WHERE ps.id=1"""
    ).fetchone()
    if row and row['mirror_location'] != row['authoritative_location']:
        add('player_location_mirror', f"Player actor #{row['player_actor_id']} location={row['authoritative_location']} but player_state mirror={row['mirror_location']}")

    # Deceased characters must not remain on the autonomous scheduler or make choices after death.
    rows = conn.execute(
        """SELECT sp.actor_id,a.name FROM simulation_profiles sp JOIN actors a ON a.id=sp.actor_id
           WHERE a.actor_type='character' AND lower(a.status) IN ('dead','deceased')"""
    ).fetchall()
    for r in rows:
        add('deceased_actor_scheduled', f"Deceased character #{r['actor_id']} ({r['name']}) still has a simulation profile")

    rows = conn.execute(
        """SELECT lp.actor_id,lp.last_review_day AS death_day,
                  (SELECT MAX(d.day) FROM decisions d WHERE d.actor_id=lp.actor_id) AS latest_decision
           FROM actor_life_profiles lp
           WHERE lp.life_status='deceased'
             AND EXISTS(SELECT 1 FROM decisions d WHERE d.actor_id=lp.actor_id AND d.day>lp.last_review_day LIMIT 1)"""
    ).fetchall()
    for r in rows:
        add('posthumous_decision', f"Actor #{r['actor_id']} has decision day {r['latest_decision']} after death day {r['death_day']}")

    rows = conn.execute(
        """SELECT hmp.id,hmp.household_id,json_extract(hmp.metadata_json,'$.travel_plan_id') travel_plan_id
           FROM household_migration_plans hmp WHERE hmp.status='in_transit'"""
    ).fetchall()
    for r in rows:
        tid = r['travel_plan_id']
        tr = None if tid is None else conn.execute(
            "SELECT subject_kind,subject_id,status FROM travel_plans WHERE id=?", (tid,)
        ).fetchone()
        if not tr or tr['subject_kind'] != 'household' or int(tr['subject_id']) != int(r['household_id']) or tr['status'] not in ('active','stalled'):
            add('household_migration_travel_mirror', f"Migration plan #{r['id']} is in_transit without a matching active/stalled household travel plan")

    return issues


def start_stress_run(conn: sqlite3.Connection, label: str, scenario_kind: str, years: float) -> int:
    start = _day(conn)
    target = start + int(round(float(years) * 365))
    snap = world_snapshot(conn)
    cur = conn.execute(
        """INSERT INTO stress_runs(label,scenario_kind,start_day,target_day,start_snapshot_json)
           VALUES (?,?,?,?,?)""",
        (label, scenario_kind, start, target, json.dumps(snap, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _record_checkpoint(conn: sqlite3.Connection, run_id: int, label: str, *, deep_integrity: bool = False) -> list[dict[str, str]]:
    snap = world_snapshot(conn)
    issues = contradiction_scan(conn, deep_integrity=deep_integrity)
    conn.execute(
        """INSERT OR REPLACE INTO stress_checkpoints(run_id,day,label,snapshot_json,contradiction_count)
           VALUES (?,?,?,?,?)""",
        (run_id, _day(conn), label, json.dumps(snap, sort_keys=True), len([x for x in issues if x['severity']=='error'])),
    )
    for issue in issues:
        conn.execute(
            "INSERT INTO stress_issues(run_id,day,severity,issue_key,detail) VALUES (?,?,?,?,?)",
            (run_id, _day(conn), issue['severity'], issue['issue_key'], issue['detail']),
        )
    return issues


def run_horizon(conn: sqlite3.Connection, years: float, *, label: str, scenario_kind: str,
                checkpoint_years: float = 5.0, fail_on_contradiction: bool = True) -> dict[str, Any]:
    """Advance a real campaign state through a long horizon and audit it at regular checkpoints."""
    run_id = start_stress_run(conn, label, scenario_kind, years)
    started = time.perf_counter()
    target = int(conn.execute("SELECT target_day FROM stress_runs WHERE id=?", (run_id,)).fetchone()[0])
    checkpoint_days = max(1, int(round(checkpoint_years * 365)))
    all_issues: list[dict[str, str]] = []
    try:
        _record_checkpoint(conn, run_id, "start", deep_integrity=True)
        # Long-run stress testing is intentionally a committed simulation workflow. Persist each
        # checkpoint so SQLite does not retain a century of writes in one transaction/WAL span.
        # This also makes an interrupted stress run inspectable at its last completed checkpoint.
        conn.commit()
        n = 0
        while _day(conn) < target:
            chunk = min(checkpoint_days, target - _day(conn))
            advance_connection(conn, chunk)
            process_camera_succession(conn)
            n += 1
            is_end = _day(conn) >= target
            all_issues.extend(_record_checkpoint(
                conn, run_id, f"checkpoint_{n}" if not is_end else "end", deep_integrity=is_end
            ))
            conn.commit()
        elapsed = time.perf_counter() - started
        errors = [x for x in all_issues if x['severity'] == 'error']
        status = 'failed' if errors and fail_on_contradiction else 'passed'
        summary = {
            "run_id": run_id,
            "label": label,
            "scenario_kind": scenario_kind,
            "years": years,
            "checkpoints": n + 1,
            "contradictions": len(errors),
            "warnings": len([x for x in all_issues if x['severity']=='warning']),
            "duration_seconds": elapsed,
            "snapshot": world_snapshot(conn),
        }
        conn.execute(
            """UPDATE stress_runs SET end_day=?,status=?,finished_at=CURRENT_TIMESTAMP,duration_seconds=?,
               end_snapshot_json=?,summary_json=?,failure_text=? WHERE id=?""",
            (_day(conn), status, elapsed, json.dumps(world_snapshot(conn), sort_keys=True), json.dumps(summary, sort_keys=True),
             None if not errors else json.dumps(errors, sort_keys=True), run_id),
        )
        conn.commit()
        if errors and fail_on_contradiction:
            raise AssertionError(f"Long-run stress test found {len(errors)} contradiction(s): {errors[:3]}")
        return summary
    except Exception as exc:
        elapsed = time.perf_counter() - started
        conn.execute(
            "UPDATE stress_runs SET end_day=?,status='failed',finished_at=CURRENT_TIMESTAMP,duration_seconds=?,failure_text=? WHERE id=?",
            (_day(conn), elapsed, str(exc), run_id),
        )
        raise


def stress_report(conn: sqlite3.Connection, run_id: int | None = None) -> dict[str, Any]:
    if run_id is None:
        row = conn.execute("SELECT id FROM stress_runs ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return {"runs": 0}
        run_id = int(row[0])
    run = conn.execute("SELECT * FROM stress_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise ValueError('Unknown stress run')
    out = dict(run)
    for key in ('start_snapshot_json','end_snapshot_json','summary_json'):
        raw = out.pop(key, None)
        out[key[:-5] if key.endswith('_json') else key] = json.loads(raw or '{}')
    out['checkpoints'] = [dict(r) for r in conn.execute("SELECT * FROM stress_checkpoints WHERE run_id=? ORDER BY day,id", (run_id,)).fetchall()]
    out['issues'] = [dict(r) for r in conn.execute("SELECT * FROM stress_issues WHERE run_id=? ORDER BY day,id", (run_id,)).fetchall()]
    return out
