"""PERF-01 memory fading: people forget low-importance rumours nobody repeats; the world does not.

A person's memory of a rumour fades when the underlying event was minor (severity 1-3), did not touch them
(they were not its source or target, nor kin or household of one who was), they are not the player, and they
have not heard anything about that event for the retention time (severity 1 ~1 year, 2 ~1.5 years, 3 ~3 years,
varied +/-30% per person).  Wars, the deaths of the great and a new Sixth (severity 4-5) are never forgotten.

Fading removes only that person's knowledge, rumour exposure (so they can hear it again), evidence access,
belief and belief revisions.  Shared rumour evidence is removed once nobody holds it.  Claims, rumours,
events, public narratives and records are never removed: the world keeps its history.

The rule depends only on the day, so the 30-day cadence is chunk-invariant.
"""
from __future__ import annotations

import hashlib
import sqlite3

MEMORY_GRID_DAYS = 30
RETENTION_DAYS = {1: 365, 2: 540, 3: 1095}
MIN_RETENTION_DAYS = int(min(RETENTION_DAYS.values()) * 0.7)
# News goes stale: a rumour that has reached nowhere new for this long stops circulating (great events longer).
NEWS_STALE_DAYS = {1: 180, 2: 180, 3: 365, 4: 730, 5: 730}
DELIVERED_TRANSMISSION_KEEP_DAYS = 90


def _stable_fraction(*parts: object) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def retention_days(actor_id: int, event_key: str, severity: int) -> float:
    return RETENTION_DAYS[max(1, min(3, int(severity)))] * (0.7 + 0.6 * _stable_fraction("memory", actor_id, event_key))


def next_memory_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    day = (int(after_day) // MEMORY_GRID_DAYS + 1) * MEMORY_GRID_DAYS
    return day if day <= int(end_day) else None


def _personal_pairs(conn: sqlite3.Connection, event_ids: set[int]) -> set[tuple[int, int]]:
    """(actor, event) pairs where the event touched the actor: source/target, their kin, their household."""
    if not event_ids:
        return set()
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _memory_events(event_id INTEGER PRIMARY KEY)")
    conn.execute("DELETE FROM _memory_events")
    conn.executemany("INSERT INTO _memory_events(event_id) VALUES (?)", [(e,) for e in sorted(event_ids)])
    involved: dict[int, set[int]] = {}
    for eid, aid in conn.execute(
        """SELECT e.id,e.source_actor_id FROM events e JOIN _memory_events m ON m.event_id=e.id WHERE e.source_actor_id IS NOT NULL
           UNION SELECT t.event_id,t.actor_id FROM event_targets t JOIN _memory_events m ON m.event_id=t.event_id"""
    ):
        involved.setdefault(int(eid), set()).add(int(aid))
    people = {a for s in involved.values() for a in s}
    close: dict[int, set[int]] = {a: {a} for a in people}
    if people:
        marks = ",".join("?" * len(people))
        for a, b in conn.execute(
            f"SELECT actor_a_id,actor_b_id FROM kinship_links WHERE actor_a_id IN ({marks}) OR actor_b_id IN ({marks})",
            (*people, *people),
        ):
            if int(a) in close: close[int(a)].add(int(b))
            if int(b) in close: close[int(b)].add(int(a))
        for a1, a2 in conn.execute(
            f"""SELECT m1.actor_id,m2.actor_id FROM household_members m1 JOIN household_members m2 ON m2.household_id=m1.household_id
                WHERE m1.actor_id IN ({marks}) AND m1.status='active' AND m2.status='active'""",
            tuple(people),
        ):
            close[int(a1)].add(int(a2))
    return {(member, eid) for eid, actors in involved.items() for a in actors for member in close.get(a, {a})}


def _forget_all(conn: sqlite3.Connection, forget: list[tuple[int, int, str, int]]) -> tuple[int, int]:
    """Set-based removal of (knowledge_id, actor, fact_key, rumour_id) memories; returns (faded, evidence collected)."""
    claims_by_key: dict[str, list[int]] = {}
    for cid, key in conn.execute("SELECT id,claim_key FROM information_claims WHERE claim_key LIKE 'rumour:%'"):
        claims_by_key.setdefault(str(key).split("#", 1)[0], []).append(int(cid))
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _memory_forget(knowledge_id INTEGER, actor_id INTEGER, rumour_id INTEGER)")
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _memory_forget_claims(actor_id INTEGER, claim_id INTEGER, PRIMARY KEY(actor_id,claim_id))")
    conn.execute("DELETE FROM _memory_forget"); conn.execute("DELETE FROM _memory_forget_claims")
    conn.executemany("INSERT INTO _memory_forget VALUES (?,?,?)", [(k, a, r) for k, a, _, r in forget])
    conn.executemany("INSERT OR IGNORE INTO _memory_forget_claims VALUES (?,?)",
                     [(a, cid) for _, a, key, _ in forget for cid in claims_by_key.get(key, ())])
    conn.execute("""DELETE FROM actor_evidence_access WHERE (actor_id,evidence_id) IN
                    (SELECT f.actor_id,ce.id FROM _memory_forget_claims f JOIN claim_evidence ce ON ce.claim_id=f.claim_id)""")
    conn.execute("DELETE FROM actor_beliefs WHERE (actor_id,claim_id) IN (SELECT actor_id,claim_id FROM _memory_forget_claims)")
    conn.execute("DELETE FROM belief_revisions WHERE (actor_id,claim_id) IN (SELECT actor_id,claim_id FROM _memory_forget_claims)")
    conn.execute("DELETE FROM knowledge_provenance WHERE knowledge_id IN (SELECT knowledge_id FROM _memory_forget)")
    conn.execute("DELETE FROM knowledge WHERE id IN (SELECT knowledge_id FROM _memory_forget)")
    conn.execute("DELETE FROM rumour_exposures WHERE (rumour_id,actor_id) IN (SELECT rumour_id,actor_id FROM _memory_forget)")
    collected = conn.execute(
        """DELETE FROM claim_evidence WHERE claim_id IN (SELECT DISTINCT claim_id FROM _memory_forget_claims)
           AND evidence_kind='rumour' AND NOT EXISTS (SELECT 1 FROM actor_evidence_access a WHERE a.evidence_id=claim_evidence.id)"""
    ).rowcount
    return len(forget), int(collected)


def fade_stale_news(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Rumours that stopped moving stop circulating; their per-place spread rows and transmissions go.
    The rumour row and its event stay (history); memories of it follow memory fading."""
    stale = []
    for rid, sev, last in conn.execute(
        """SELECT r.id,COALESCE(e.severity,1),MAX(r.created_day,COALESCE(MAX(rl.last_updated_day),r.created_day))
           FROM rumours r LEFT JOIN events e ON e.id=r.truth_event_id
           LEFT JOIN rumour_locations rl ON rl.rumour_id=r.id
           WHERE r.status='circulating' GROUP BY r.id"""
    ):
        if int(last) + NEWS_STALE_DAYS[max(1, min(5, int(sev)))] <= day:
            stale.append((int(rid),))
    if stale:
        conn.executemany("UPDATE rumours SET status='faded' WHERE id=?", stale)
        conn.executemany("DELETE FROM rumour_locations WHERE rumour_id=?", stale)
        conn.executemany("DELETE FROM rumour_transmissions WHERE rumour_id=?", stale)
    pruned = conn.execute("DELETE FROM rumour_transmissions WHERE status='delivered' AND due_day<?",
                          (day - DELIVERED_TRANSMISSION_KEEP_DAYS,)).rowcount
    return {"news_faded": len(stale), "transmissions_pruned": int(pruned)}


AUDIT_KEEP_DAYS = 365


def prune_audit_logs(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Diagnostic trails keep about a year; history (events, decisions, breakthroughs, relationships) is kept.
    Every reader of these trails looks at the same day or an entity's latest row, which is always kept."""
    cutoff = int(day) - AUDIT_KEEP_DAYS
    n = 0
    n += conn.execute("DELETE FROM decision_evaluations WHERE day<?", (cutoff,)).rowcount  # candidate audits cascade
    n += conn.execute("DELETE FROM mortality_audit WHERE day<?", (cutoff,)).rowcount
    n += conn.execute("DELETE FROM regional_growth_snapshots WHERE day<?", (cutoff,)).rowcount
    n += conn.execute("DELETE FROM cultivation_history WHERE history_kind='practice_review' AND day<?", (cutoff,)).rowcount
    n += conn.execute(
        """DELETE FROM resolution_reviews WHERE day<? AND id NOT IN
           (SELECT MAX(id) FROM resolution_reviews GROUP BY entity_kind,entity_id)""", (cutoff,)).rowcount
    return {"audit_rows_pruned": int(n)}


def process_due_memory(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    day = int(day)
    news = fade_stale_news(conn, day)
    result = forget_minor_rumours(conn, day)
    audit = prune_audit_logs(conn, day)
    return {**news, **result, **audit}


def forget_minor_rumours(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    day = int(day)
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    player_id = int(player[0]) if player and player[0] is not None else -1
    rows = conn.execute(
        """SELECT k.id,k.knower_actor_id,k.fact_key,k.learned_day,r.id,r.truth_event_id,COALESCE(e.severity,1)
           FROM knowledge k
           JOIN rumours r ON r.id=CAST(substr(k.fact_key,8) AS INTEGER)
           LEFT JOIN events e ON e.id=r.truth_event_id
           WHERE k.fact_key LIKE 'rumour:%' AND k.knower_actor_id<>? AND COALESCE(e.severity,1)<=3
             AND k.learned_day<=?
           ORDER BY k.id""",
        (player_id, day - MIN_RETENTION_DAYS),
    ).fetchall()
    if not rows:
        return {"memories_faded": 0, "evidence_collected": 0}
    event_ids = {int(r[5]) for r in rows if r[5] is not None}
    personal = _personal_pairs(conn, event_ids)
    # Hearing anything about the same event refreshes the memory of it.
    last_touch: dict[tuple[int, str], int] = {}
    for kid, actor, fact_key, learned, rid, eid, sev in rows:
        key = (int(actor), f"e{eid}" if eid is not None else f"r{rid}")
        last_touch[key] = max(last_touch.get(key, 0), int(learned))
    if event_ids:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _memory_events(event_id INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM _memory_events")
        conn.executemany("INSERT INTO _memory_events(event_id) VALUES (?)", [(e,) for e in sorted(event_ids)])
        for actor, eid, latest in conn.execute(
            """SELECT k.knower_actor_id,r.truth_event_id,MAX(k.learned_day) FROM knowledge k
               JOIN rumours r ON r.id=CAST(substr(k.fact_key,8) AS INTEGER)
               JOIN _memory_events m ON m.event_id=r.truth_event_id
               WHERE k.fact_key LIKE 'rumour:%' GROUP BY 1,2"""
        ):
            key = (int(actor), f"e{eid}")
            last_touch[key] = max(last_touch.get(key, 0), int(latest))
    forget: list[tuple[int, int, str, int]] = []
    for kid, actor, fact_key, learned, rid, eid, sev in rows:
        actor = int(actor)
        if eid is not None and (actor, int(eid)) in personal:
            continue
        event_key = f"e{eid}" if eid is not None else f"r{rid}"
        if last_touch[(actor, event_key)] + retention_days(actor, event_key, int(sev)) > day:
            continue
        forget.append((int(kid), actor, str(fact_key), int(rid)))
    if not forget:
        return {"memories_faded": 0, "evidence_collected": 0}
    faded, collected = _forget_all(conn, forget)
    return {"memories_faded": faded, "evidence_collected": int(collected)}
