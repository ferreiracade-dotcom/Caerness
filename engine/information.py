from __future__ import annotations

import hashlib
import math
import sqlite3
from dataclasses import dataclass


VISIBILITIES = {"public", "limited", "private", "secret"}


@dataclass(frozen=True)
class EventPolicy:
    visibility: str
    secrecy: float
    rumorability: float
    reliability: float


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def default_event_policy(event_type: str, severity: int) -> EventPolicy:
    """Conservative defaults. Callers can override per event.

    Publicity is intentionally separate from importance: a severe investigation can remain private,
    while a modest public duel can be highly rumourable.
    """
    et = (event_type or "").lower()
    sev = max(1, min(5, int(severity)))

    if "investigation" in et:
        return EventPolicy("private", 0.85, 0.08 if sev < 4 else 0.18, 0.82)
    if "inter_actor_conflict" in et or ":attack" in et:
        return EventPolicy("public", 0.12, 0.88, 0.84)
    if et.startswith("interaction:threat") or et.startswith("interaction:demand"):
        return EventPolicy("limited", 0.58, 0.42, 0.78)
    if et.startswith("interaction:alliance") or et.startswith("interaction:contract"):
        return EventPolicy("limited", 0.46, 0.48, 0.9)
    if et.startswith("actor_decision"):
        return EventPolicy("private", 0.72, 0.12, 0.88)
    if et.startswith("background:"):
        if sev >= 4:
            return EventPolicy("public", 0.18, 0.78, 0.78)
        return EventPolicy("limited", 0.48, 0.46, 0.72)
    if et.startswith("clock:"):
        return EventPolicy("limited", 0.5, 0.38, 0.8)
    return EventPolicy("limited", 0.5, 0.4, 0.8)


def infer_event_location(conn: sqlite3.Connection, event_id: int) -> int | None:
    row = conn.execute("SELECT location_id,source_actor_id FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        raise ValueError(f"unknown event_id {event_id}")
    if row["location_id"] is not None:
        return int(row["location_id"])

    # A direct target's current location is normally the best proxy for where an event landed.
    target = conn.execute(
        """SELECT a.current_location_id FROM event_targets et
           JOIN actors a ON a.id=et.actor_id
           WHERE et.event_id=? AND a.current_location_id IS NOT NULL
           ORDER BY et.actor_id LIMIT 1""",
        (event_id,),
    ).fetchone()
    if target and target[0] is not None:
        loc = int(target[0])
        conn.execute("UPDATE events SET location_id=? WHERE id=? AND location_id IS NULL", (loc, event_id))
        return loc

    if row["source_actor_id"] is not None:
        source = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (row["source_actor_id"],)).fetchone()
        if source and source[0] is not None:
            loc = int(source[0])
            conn.execute("UPDATE events SET location_id=? WHERE id=? AND location_id IS NULL", (loc, event_id))
            return loc
    return None


# Shown for rumour provenance (not stored per hearer: it was 5 MB of one repeated sentence by year 3).
RUMOUR_PROVENANCE_NOTE = "Heard as rumour; belief is not equivalent to verified world truth."


def _information_link(
    conn: sqlite3.Connection,
    day: int,
    source_kind: str,
    source_id: int,
    target_kind: str,
    target_id: int,
    relation: str,
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO information_links(day,source_kind,source_id,target_kind,target_id,relation)
           VALUES (?,?,?,?,?,?)""",
        (day, source_kind, source_id, target_kind, target_id, relation),
    )


def _upsert_knowledge(
    conn: sqlite3.Connection,
    actor_id: int,
    fact_key: str,
    belief_text: str,
    confidence: float,
    learned_day: int,
    *,
    truth_event_id: int | None = None,
    source_kind: str = "admin",
    source_id: int | None = None,
    channel_id: int | None = None,
    location_id: int | None = None,
    notes: str | None = None,
) -> int:
    confidence = _clamp(confidence)
    old = conn.execute(
        "SELECT id,confidence FROM knowledge WHERE knower_actor_id=? AND fact_key=?",
        (actor_id, fact_key),
    ).fetchone()
    if old:
        # New evidence can strengthen but should not silently lower an existing stronger belief.
        merged_confidence = max(float(old["confidence"]), confidence)
        conn.execute(
            """UPDATE knowledge SET belief_text=?,confidence=?,truth_event_id=COALESCE(?,truth_event_id),learned_day=?
               WHERE id=?""",
            (belief_text, merged_confidence, truth_event_id, learned_day, old["id"]),
        )
        knowledge_id = int(old["id"])
    else:
        cur = conn.execute(
            """INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,truth_event_id,learned_day)
               VALUES (?,?,?,?,?,?)""",
            (actor_id, fact_key, belief_text, confidence, truth_event_id, learned_day),
        )
        knowledge_id = int(cur.lastrowid)

    conn.execute(
        """INSERT INTO knowledge_provenance(knowledge_id,source_kind,source_id,channel_id,location_id,acquired_day,notes)
           VALUES (?,?,?,?,?,?,?)""",
        (knowledge_id, source_kind, source_id, channel_id, location_id, learned_day, notes),
    )
    # PERF-01: no rumour->knowledge "learned_as" link; knowledge_provenance above already records the
    # source, and nothing read the link (it was a quarter of all rows written per rumour heard).

    # BELIEF-01 compatibility bridge: legacy knowledge remains readable, but new actor
    # reasoning should consume provenance-bearing claims/evidence/beliefs.
    try:
        from .belief import mirror_legacy_knowledge
        mirror_legacy_knowledge(
            conn, knowledge_id=knowledge_id, actor_id=actor_id, fact_key=fact_key,
            belief_text=belief_text, confidence=confidence, learned_day=learned_day,
            truth_event_id=truth_event_id, source_kind=source_kind, source_id=source_id,
            location_id=location_id, notes=notes,
        )
    except sqlite3.OperationalError as exc:
        # Compatibility for deliberately old schemas opened before migration only.
        if "no such table" not in str(exc).lower():
            raise
    return knowledge_id


def register_event_information(
    conn: sqlite3.Connection,
    event_id: int,
    *,
    day: int | None = None,
    visibility: str | None = None,
    secrecy: float | None = None,
    rumorability: float | None = None,
    reliability: float | None = None,
) -> EventPolicy:
    event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        raise ValueError(f"unknown event_id {event_id}")
    existing = conn.execute("SELECT * FROM event_information WHERE event_id=?", (event_id,)).fetchone()
    policy = default_event_policy(str(event["event_type"]), int(event["severity"]))
    if existing:
        return EventPolicy(
            str(existing["visibility"]),
            float(existing["secrecy"]),
            float(existing["rumorability"]),
            float(existing["reliability"]),
        )

    vis = visibility or policy.visibility
    if vis not in VISIBILITIES:
        raise ValueError(f"unsupported event visibility: {vis}")
    policy = EventPolicy(
        vis,
        _clamp(policy.secrecy if secrecy is None else secrecy),
        _clamp(policy.rumorability if rumorability is None else rumorability),
        _clamp(policy.reliability if reliability is None else reliability),
    )
    registered_day = int(event["day"] if day is None else day)
    conn.execute(
        """INSERT INTO event_information(event_id,visibility,secrecy,rumorability,reliability,registered_day)
           VALUES (?,?,?,?,?,?)""",
        (event_id, policy.visibility, policy.secrecy, policy.rumorability, policy.reliability, registered_day),
    )
    loc = infer_event_location(conn, event_id)

    participant_ids: list[tuple[int, str]] = []
    if event["source_actor_id"] is not None:
        participant_ids.append((int(event["source_actor_id"]), "source"))
    participant_ids.extend(
        (int(r["actor_id"]), "target")
        for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (event_id,)).fetchall()
    )
    seen: set[int] = set()
    for actor_id, witness_type in participant_ids:
        if actor_id in seen:
            continue
        seen.add(actor_id)
        conf = max(0.86, policy.reliability)
        conn.execute(
            """INSERT OR REPLACE INTO event_witnesses(event_id,actor_id,witness_type,confidence,learned_day)
               VALUES (?,?,?,?,?)""",
            (event_id, actor_id, witness_type, conf, registered_day),
        )
        kid = _upsert_knowledge(
            conn,
            actor_id,
            f"event:{event_id}",
            str(event["summary"]),
            conf,
            registered_day,
            truth_event_id=event_id,
            source_kind="event",
            source_id=event_id,
            location_id=loc,
            notes=f"Direct {witness_type} knowledge.",
        )
        _information_link(conn, registered_day, "event", event_id, "knowledge", kid, "directly_known")
    return policy


def ensure_event_information(conn: sqlite3.Connection, through_day: int) -> int:
    rows = conn.execute(
        """SELECT e.id FROM events e
           LEFT JOIN event_information ei ON ei.event_id=e.id
           WHERE e.day<=? AND ei.event_id IS NULL
           ORDER BY e.day,e.id""",
        (through_day,),
    ).fetchall()
    for row in rows:
        register_event_information(conn, int(row["id"]))
    return len(rows)


def _rumour_text(event: sqlite3.Row, visibility: str) -> str:
    if visibility == "public":
        return f"Reports are circulating that {event['summary']}"
    # Limited events should not turn the exact private state into omniscient tavern gossip.
    return f"Word is circulating about {str(event['title']).lower()}; the details are inconsistent."


def _best_channel_between(conn: sqlite3.Connection, a: int, b: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT ic.*,MIN(ca.strength,cb.strength) effective_strength
           FROM information_channels ic
           JOIN channel_locations ca ON ca.channel_id=ic.id AND ca.location_id=?
           JOIN channel_locations cb ON cb.channel_id=ic.id AND cb.location_id=?
           ORDER BY ic.speed_multiplier ASC, effective_strength DESC, ic.fidelity DESC
           LIMIT 1""",
        (a, b),
    ).fetchone()


def _neighbors(conn: sqlite3.Connection, location_id: int, day: int) -> list[tuple[dict, int]]:
    """Return information-propagation neighbors from the authoritative route layer when crystallized.

    v0.4's ``location_links`` predate v0.22's physical travel model. They remain a compatibility/
    latent-geography fallback for old saves and abstract information maps, but once a location has
    crystallized ``travel_routes`` those routes own reachability and travel time. This prevents
    information from leaking through a road/pass that the ecology system currently says is closed.
    """
    physical = conn.execute(
        """SELECT * FROM travel_routes WHERE from_location_id=? OR to_location_id=? ORDER BY id""",
        (location_id, location_id),
    ).fetchall()
    if physical:
        from .ecology import _route_eval
        out: list[tuple[dict, int]] = []
        for row in physical:
            ev = _route_eval(conn, row, int(location_id), int(day))
            if not bool(ev["usable"]):
                continue
            other = int(ev["target"])
            # Information traffic is an operational proxy, not a second route truth. Capacity and
            # reliability only shape how readily ordinary word travels over a usable route.
            traffic = _clamp(0.25 + 0.45 * (float(row["capacity"]) / 100.0) + 0.30 * (float(row["reliability"]) / 100.0))
            out.append(({"travel_days": max(1.0, float(ev["days"])), "traffic": traffic, "route_id": int(row["id"])}, other))
        return out

    rows = conn.execute(
        """SELECT * FROM location_links WHERE active=1 AND (location_a_id=? OR location_b_id=?)""",
        (location_id, location_id),
    ).fetchall()
    out: list[tuple[dict, int]] = []
    for row in rows:
        other = int(row["location_b_id"] if int(row["location_a_id"]) == location_id else row["location_a_id"])
        out.append(({"travel_days": float(row["travel_days"]), "traffic": float(row["traffic"]), "legacy_link_id": int(row["id"])}, other))
    return out


def _schedule_from_location(
    conn: sqlite3.Connection,
    rumour_id: int,
    location_id: int,
    day: int,
    prevalence: float,
    fidelity: float,
    hop_count: int,
) -> None:
    for route, other in _neighbors(conn, location_id, day):
        existing = conn.execute(
            "SELECT 1 FROM rumour_locations WHERE rumour_id=? AND location_id=?",
            (rumour_id, other),
        ).fetchone()
        pending = conn.execute(
            "SELECT id FROM rumour_transmissions WHERE rumour_id=? AND to_location_id=?",
            (rumour_id, other),
        ).fetchone()
        if existing or pending:
            continue

        channel = _best_channel_between(conn, location_id, other)
        speed = float(channel["speed_multiplier"]) if channel else 1.0
        channel_fidelity = float(channel["fidelity"]) if channel else 0.78
        channel_strength = float(channel["effective_strength"]) if channel else 0.55
        traffic = float(route["traffic"])
        travel_days = max(1, int(math.ceil(float(route["travel_days"]) * speed)))
        next_prevalence = _clamp(prevalence * (0.48 + 0.52 * traffic) * (0.7 + 0.3 * channel_strength))
        next_fidelity = _clamp(fidelity * channel_fidelity * (0.985 ** max(0, hop_count)))
        if next_prevalence < 0.055:
            continue
        cur = conn.execute(
            """INSERT INTO rumour_transmissions(
                   rumour_id,from_location_id,to_location_id,channel_id,due_day,fidelity,prevalence,hop_count,status
               ) VALUES (?,?,?,?,?,?,?,?,'pending')""",
            (
                rumour_id,
                location_id,
                other,
                int(channel["id"]) if channel else None,
                day + travel_days,
                next_fidelity,
                next_prevalence,
                hop_count + 1,
            ),
        )
        # PERF-01: no write-only rumour->transmission "spread_via" link.


def seed_rumours_from_events(conn: sqlite3.Connection, through_day: int) -> int:
    rows = conn.execute(
        """SELECT e.*,ei.visibility,ei.secrecy,ei.rumorability,ei.reliability
           FROM events e JOIN event_information ei ON ei.event_id=e.id
           WHERE e.day<=? AND ei.visibility IN ('public','limited') AND ei.rumorability>=0.20
             AND NOT EXISTS (SELECT 1 FROM rumours r WHERE r.truth_event_id=e.id)
           ORDER BY e.day,e.id""",
        (through_day,),
    ).fetchall()
    made = 0
    for event in rows:
        loc = infer_event_location(conn, int(event["id"]))
        if loc is None:
            continue
        distortion = _clamp(0.08 + 0.45 * (1.0 - float(event["reliability"])) + 0.15 * float(event["secrecy"]))
        reach = _clamp(0.12 + 0.12 * int(event["severity"]) + 0.3 * float(event["rumorability"]))
        cur = conn.execute(
            """INSERT INTO rumours(created_day,origin_location_id,text,truth_event_id,distortion,reach,status)
               VALUES (?,?,?,?,?,?,'circulating')""",
            (int(event["day"]), loc, _rumour_text(event, str(event["visibility"])), int(event["id"]), distortion, reach),
        )
        rumour_id = int(cur.lastrowid)
        fidelity = _clamp(float(event["reliability"]) * (1.0 - distortion * 0.35))
        prevalence = _clamp(0.28 + reach * 0.55)
        conn.execute(
            """INSERT INTO rumour_locations(rumour_id,location_id,first_arrived_day,last_updated_day,prevalence,fidelity,hop_count)
               VALUES (?,?,?,?,?,?,0)""",
            (rumour_id, loc, int(event["day"]), int(event["day"]), prevalence, fidelity),
        )
        _information_link(conn, int(event["day"]), "event", int(event["id"]), "rumour", rumour_id, "became_rumour")
        _schedule_from_location(conn, rumour_id, loc, int(event["day"]), prevalence, fidelity, 0)
        made += 1
    return made


def _stable_fraction(*parts: object) -> float:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def expose_actor_to_rumour(
    conn: sqlite3.Connection,
    rumour_id: int,
    actor_id: int,
    day: int,
    location_id: int,
    *,
    channel_id: int | None = None,
    force: bool = False,
    prefetched: tuple[sqlite3.Row | None, sqlite3.Row | None, set[int]] | None = None,
) -> int | None:
    # PERF-01: a caller exposing many people to one rumour at one place passes the rumour, its local
    # spread and the set of people already exposed, instead of re-reading them for every person.
    if prefetched is not None:
        local, rumour, exposed = prefetched
        if actor_id in exposed:
            return None
    else:
        exposed = None
        if conn.execute(
            "SELECT 1 FROM rumour_exposures WHERE rumour_id=? AND actor_id=?",
            (rumour_id, actor_id),
        ).fetchone():
            return None
        local = conn.execute(
            "SELECT * FROM rumour_locations WHERE rumour_id=? AND location_id=?",
            (rumour_id, location_id),
        ).fetchone()
        rumour = conn.execute("SELECT * FROM rumours WHERE id=?", (rumour_id,)).fetchone()
    if not local or not rumour:
        return None

    prevalence = float(local["prevalence"])
    access_bonus = 0.0
    if channel_id is not None:
        membership = conn.execute(
            "SELECT access_level FROM channel_memberships WHERE channel_id=? AND actor_id=?",
            (channel_id, actor_id),
        ).fetchone()
        if membership:
            access_bonus = 0.28 * float(membership["access_level"])
    chance = _clamp(prevalence + access_bonus)
    if not force and _stable_fraction(rumour_id, actor_id, day, location_id) > chance:
        return None

    confidence = _clamp(float(local["fidelity"]) * (1.0 - float(rumour["distortion"]) * 0.45))
    conn.execute(
        """INSERT INTO rumour_exposures(rumour_id,actor_id,heard_day,confidence,source_location_id,channel_id)
           VALUES (?,?,?,?,?,?)""",
        (rumour_id, actor_id, day, confidence, location_id, channel_id),
    )
    if exposed is not None:
        exposed.add(actor_id)
    kid = _upsert_knowledge(
        conn,
        actor_id,
        f"rumour:{rumour_id}",
        str(rumour["text"]),
        confidence,
        day,
        truth_event_id=int(rumour["truth_event_id"]) if rumour["truth_event_id"] is not None else None,
        source_kind="rumour",
        source_id=rumour_id,
        channel_id=channel_id,
        location_id=location_id,
        notes=None,  # PERF-01: the standard rumour note is implied by source_kind; see RUMOUR_PROVENANCE_NOTE
    )
    return kid


def _expose_present_actors(
    conn: sqlite3.Connection, rumour_id: int, location_id: int, day: int,
    *, presence_snapshot: dict[int, float] | None = None,
) -> None:
    # PRESBACK-01: settlement assignment is not exact co-presence.  The location/day
    # probability snapshot may be reused by several rumours; only the deterministic
    # purpose-specific draw differs per rumour.
    from .presence import actors_plausibly_present
    present_ids = set(actors_plausibly_present(
        conn, location_id, day=day, purpose=f"rumour:{rumour_id}",
        probability_snapshot=presence_snapshot,
    ))
    prefetched = (
        conn.execute("SELECT * FROM rumour_locations WHERE rumour_id=? AND location_id=?", (rumour_id, location_id)).fetchone(),
        conn.execute("SELECT * FROM rumours WHERE id=?", (rumour_id,)).fetchone(),
        {int(r[0]) for r in conn.execute("SELECT actor_id FROM rumour_exposures WHERE rumour_id=?", (rumour_id,))},
    )
    for actor_id in sorted(present_ids):
        expose_actor_to_rumour(conn, rumour_id, actor_id, day, location_id, prefetched=prefetched)

    # Network members can receive information more readily in a place covered by their network.
    channels = conn.execute(
        "SELECT channel_id FROM channel_locations WHERE location_id=?",
        (location_id,),
    ).fetchall()
    for crow in channels:
        cid = int(crow["channel_id"])
        members = conn.execute(
            """SELECT cm.actor_id FROM channel_memberships cm
               JOIN actors a ON a.id=cm.actor_id
               WHERE cm.channel_id=? AND a.status='active'""",
            (cid,),
        ).fetchall()
        for member in members:
            actor_id = int(member["actor_id"])
            if actor_id in present_ids:
                expose_actor_to_rumour(conn, rumour_id, actor_id, day, location_id, channel_id=cid, prefetched=prefetched)


def process_due_transmissions(conn: sqlite3.Connection, through_day: int) -> int:
    delivered = 0
    # Neighborly-style reverse presence is reusable across all rumours arriving at the
    # same location on the same day. Keep the cache local to this transaction/process call
    # so no stale presence survives world-state mutation or restart.
    presence_cache: dict[tuple[int, int], dict[int, float]] = {}
    while True:
        rows = conn.execute(
            """SELECT * FROM rumour_transmissions
               WHERE status='pending' AND due_day<=?
               ORDER BY due_day,id""",
            (through_day,),
        ).fetchall()
        if not rows:
            break
        for row in rows:
            rid = int(row["rumour_id"])
            loc = int(row["to_location_id"])
            due = int(row["due_day"])
            conn.execute(
                """INSERT INTO rumour_locations(
                       rumour_id,location_id,first_arrived_day,last_updated_day,prevalence,fidelity,hop_count
                   ) VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(rumour_id,location_id) DO UPDATE SET
                     last_updated_day=MAX(last_updated_day,excluded.last_updated_day),
                     prevalence=MAX(prevalence,excluded.prevalence),
                     fidelity=MAX(fidelity,excluded.fidelity),
                     hop_count=MIN(hop_count,excluded.hop_count)""",
                (rid, loc, due, due, float(row["prevalence"]), float(row["fidelity"]), int(row["hop_count"])),
            )
            conn.execute("UPDATE rumour_transmissions SET status='delivered' WHERE id=?", (row["id"],))
            # PERF-01: no write-only transmission->location "arrived_at" link; rumour_locations records arrival.
            cache_key = (loc, due)
            if cache_key not in presence_cache:
                from .presence import presence_probability_snapshot
                presence_cache[cache_key] = presence_probability_snapshot(conn, loc, day=due)
            _expose_present_actors(conn, rid, loc, due, presence_snapshot=presence_cache[cache_key])
            _schedule_from_location(
                conn,
                rid,
                loc,
                due,
                float(row["prevalence"]),
                float(row["fidelity"]),
                int(row["hop_count"]),
            )
            delivered += 1
    return delivered


def learn_public_events_at_location(
    conn: sqlite3.Connection,
    actor_id: int,
    location_id: int,
    day: int,
    *,
    lookback_days: int = 21,
) -> int:
    rows = conn.execute(
        """SELECT e.*,ei.reliability FROM events e
           JOIN event_information ei ON ei.event_id=e.id
           WHERE e.location_id=? AND ei.visibility='public' AND e.day BETWEEN ? AND ?
           ORDER BY e.day,e.id""",
        (location_id, max(0, day - lookback_days), day),
    ).fetchall()
    learned = 0
    for event in rows:
        exists = conn.execute(
            "SELECT 1 FROM knowledge WHERE knower_actor_id=? AND fact_key=?",
            (actor_id, f"event:{event['id']}"),
        ).fetchone()
        if exists:
            continue
        _upsert_knowledge(
            conn,
            actor_id,
            f"event:{event['id']}",
            str(event["summary"]),
            max(0.7, float(event["reliability"])),
            day,
            truth_event_id=int(event["id"]),
            source_kind="event",
            source_id=int(event["id"]),
            location_id=location_id,
            notes="Learned from public local awareness.",
        )
        learned += 1
    return learned


def hear_local_rumours(
    conn: sqlite3.Connection,
    actor_id: int,
    location_id: int,
    day: int,
    *,
    limit: int = 8,
    force_top: int = 2,
) -> int:
    rows = conn.execute(
        """SELECT rl.*,r.reach,r.distortion FROM rumour_locations rl
           JOIN rumours r ON r.id=rl.rumour_id
           WHERE rl.location_id=? AND r.status='circulating'
           ORDER BY (rl.prevalence*r.reach) DESC,rl.first_arrived_day DESC
           LIMIT ?""",
        (location_id, max(1, limit)),
    ).fetchall()
    heard = 0
    for idx, row in enumerate(rows):
        kid = expose_actor_to_rumour(
            conn,
            int(row["rumour_id"]),
            actor_id,
            day,
            location_id,
            force=idx < force_top and float(row["prevalence"]) >= 0.18,
        )
        if kid is not None:
            heard += 1
    return heard


def process_information(conn: sqlite3.Connection, through_day: int) -> dict[str, int]:
    registered = ensure_event_information(conn, through_day)
    seeded = seed_rumours_from_events(conn, through_day)
    delivered = process_due_transmissions(conn, through_day)
    return {"registered_events": registered, "seeded_rumours": seeded, "delivered_transmissions": delivered}


def next_information_due_day(conn: sqlite3.Connection, after_day: int, through_day: int) -> int | None:
    """Return the next *causal* information checkpoint.

    Information has two independent wake-up sources:
    1. an already-scheduled rumour transmission;
    2. a newly-created event that has not yet been registered into the information layer.

    The second source is load-bearing for chunk-invariant simulation.  Previously new
    events were often discovered only by ``advance_connection``'s arbitrary terminal
    catch-up pass, so advancing 90 days once differed from 30+30+30.  An event created
    at the current checkpoint is exposed to this owner by the same-checkpoint registry
    refresh (after_day=day-1).  Legacy overdue/unregistered events are deterministically
    scheduled for the next simulation day rather than for an API-call boundary.
    """
    vals: list[int] = []
    row = conn.execute(
        """SELECT MIN(due_day) FROM rumour_transmissions
           WHERE status='pending' AND due_day>? AND due_day<=?""",
        (after_day, through_day),
    ).fetchone()
    if row and row[0] is not None:
        vals.append(int(row[0]))

    # Legacy/imported events may not yet have an event_information row.
    row = conn.execute(
        """SELECT MIN(e.day)
           FROM events e LEFT JOIN event_information ei ON ei.event_id=e.id
           WHERE ei.event_id IS NULL AND e.day<=?""",
        (through_day,),
    ).fetchone()
    if row and row[0] is not None:
        event_day = int(row[0])
        due = event_day if event_day > after_day else after_day + 1
        if due <= through_day:
            vals.append(due)

    # Normal log_event() registers event_information immediately, but rumour seeding is
    # intentionally downstream.  That downstream work must advertise a due day instead
    # of relying on a caller-boundary catch-up.
    row = conn.execute(
        """SELECT MIN(e.day)
           FROM events e JOIN event_information ei ON ei.event_id=e.id
           WHERE e.day<=?
             AND ei.visibility IN ('public','limited') AND ei.rumorability>=0.20
             AND NOT EXISTS (SELECT 1 FROM rumours r WHERE r.truth_event_id=e.id)
             AND (
                 e.location_id IS NOT NULL
                 OR EXISTS (SELECT 1 FROM actors sa WHERE sa.id=e.source_actor_id AND sa.current_location_id IS NOT NULL)
                 OR EXISTS (
                     SELECT 1 FROM event_targets et JOIN actors ta ON ta.id=et.actor_id
                     WHERE et.event_id=e.id AND ta.current_location_id IS NOT NULL
                 )
             )""",
        (through_day,),
    ).fetchone()
    if row and row[0] is not None:
        event_day = int(row[0])
        due = event_day if event_day > after_day else after_day + 1
        if due <= through_day:
            vals.append(due)

    return min(vals) if vals else None


def recent_rumours(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT r.*,l.name origin_name,e.title truth_title
           FROM rumours r
           LEFT JOIN locations l ON l.id=r.origin_location_id
           LEFT JOIN events e ON e.id=r.truth_event_id
           ORDER BY r.created_day DESC,r.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def actor_knowledge(conn: sqlite3.Connection, actor_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """SELECT k.*,e.title truth_title,e.event_type
           FROM knowledge k LEFT JOIN events e ON e.id=k.truth_event_id
           WHERE k.knower_actor_id=? ORDER BY k.learned_day DESC,k.id DESC LIMIT ?""",
        (actor_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]
