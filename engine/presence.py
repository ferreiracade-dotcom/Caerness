from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, asdict
from typing import Any, Iterable



def _current_day(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()
    return int(row[0]) if row else 0


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _stable_fraction(*parts: object) -> float:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


@dataclass(frozen=True)
class PresenceAssessment:
    actor_id: int
    location_id: int
    day: int
    resolution: str
    probability: float
    possible: bool
    basis: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_presence_profile(
    conn: sqlite3.Connection,
    actor_id: int,
    *,
    base_location_id: int | None = None,
    source_kind: str = "campaign",
    confidence: float = 0.7,
    effective_from_day: int | None = None,
    notes: str = "",
) -> int:
    day = _current_day(conn) if effective_from_day is None else int(effective_from_day)
    if base_location_id is None:
        row = conn.execute("SELECT home_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
        base_location_id = int(row[0]) if row and row[0] is not None else None
    conn.execute(
        """INSERT INTO actor_presence_profiles(actor_id,base_location_id,source_kind,confidence,effective_from_day,notes)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(actor_id) DO UPDATE SET
             base_location_id=COALESCE(excluded.base_location_id,actor_presence_profiles.base_location_id),
             source_kind=excluded.source_kind,confidence=excluded.confidence,notes=excluded.notes""",
        (actor_id, base_location_id, source_kind, _clamp(confidence), day, notes),
    )
    return actor_id


def add_presence_habit(
    conn: sqlite3.Connection,
    actor_id: int,
    location_id: int,
    *,
    habit_kind: str = "frequented",
    weight: float = 0.5,
    cadence_days: int = 7,
    time_window: str | None = None,
    basis_kind: str | None = None,
    basis_id: int | None = None,
    source_kind: str = "campaign",
    confidence: float = 0.7,
    effective_from_day: int | None = None,
    effective_to_day: int | None = None,
    notes: str = "",
) -> int:
    ensure_presence_profile(conn, actor_id, source_kind=source_kind)
    day = _current_day(conn) if effective_from_day is None else int(effective_from_day)
    cur = conn.execute(
        """INSERT INTO actor_presence_habits(
               actor_id,location_id,habit_kind,weight,cadence_days,time_window,basis_kind,basis_id,
               source_kind,confidence,effective_from_day,effective_to_day,notes
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(actor_id,location_id,habit_kind,basis_kind,basis_id,effective_from_day)
           DO UPDATE SET weight=excluded.weight,cadence_days=excluded.cadence_days,time_window=excluded.time_window,
             source_kind=excluded.source_kind,confidence=excluded.confidence,effective_to_day=excluded.effective_to_day,notes=excluded.notes""",
        (
            actor_id, location_id, habit_kind, _clamp(weight), max(1, int(cadence_days)), time_window,
            basis_kind, basis_id, source_kind, _clamp(confidence), day, effective_to_day, notes,
        ),
    )
    if cur.lastrowid:
        return int(cur.lastrowid)
    row = conn.execute(
        """SELECT id FROM actor_presence_habits WHERE actor_id=? AND location_id=? AND habit_kind=?
           AND basis_kind IS ? AND basis_id IS ? AND effective_from_day=?""",
        (actor_id, location_id, habit_kind, basis_kind, basis_id, day),
    ).fetchone()
    return int(row[0])


def seed_presence_from_existing_state(conn: sqlite3.Connection, *, effective_day: int | None = None) -> int:
    """Create present-day low-resolution profiles from already-stored facts.

    This deliberately does not manufacture historical movement. Derived habits begin on the
    migration/current day and cite their basis. Explicit travel remains authoritative.
    """
    day = _current_day(conn) if effective_day is None else int(effective_day)
    made = 0

    def has_open_habit(actor_id: int, location_id: int, habit_kind: str, basis_kind: str | None, basis_id: int | None) -> bool:
        return conn.execute(
            """SELECT 1 FROM actor_presence_habits
               WHERE actor_id=? AND location_id=? AND habit_kind=?
                 AND basis_kind IS ? AND basis_id IS ? AND effective_to_day IS NULL
               LIMIT 1""",
            (actor_id, location_id, habit_kind, basis_kind, basis_id),
        ).fetchone() is not None

    actors = conn.execute(
        """SELECT id,home_location_id,current_location_id FROM actors
           WHERE actor_type='character' AND status='active' ORDER BY id"""
    ).fetchall()
    for actor in actors:
        aid = int(actor["id"])
        existed = conn.execute("SELECT 1 FROM actor_presence_profiles WHERE actor_id=?", (aid,)).fetchone()
        ensure_presence_profile(
            conn, aid,
            base_location_id=int(actor["home_location_id"]) if actor["home_location_id"] is not None else None,
            source_kind="migration", confidence=0.65, effective_from_day=day,
            notes="PRES-01 profile derived from existing present-day state; not a historical movement claim.",
        )
        if not existed:
            made += 1
        if actor["home_location_id"] is not None:
            home_id = int(actor["home_location_id"])
            if not has_open_habit(aid, home_id, "home", "actor_home", aid):
                add_presence_habit(
                    conn, aid, home_id, habit_kind="home", weight=0.62,
                    cadence_days=1, basis_kind="actor_home", basis_id=aid, source_kind="migration",
                    confidence=0.9, effective_from_day=day,
                )
        # current_location_id is a broad legacy anchor, not exact co-presence.
        if actor["current_location_id"] is not None and actor["current_location_id"] != actor["home_location_id"]:
            current_id = int(actor["current_location_id"])
            if not has_open_habit(aid, current_id, "legacy_anchor", "legacy_current_location", aid):
                add_presence_habit(
                    conn, aid, current_id, habit_kind="legacy_anchor", weight=0.18,
                    cadence_days=7, basis_kind="legacy_current_location", basis_id=aid, source_kind="migration",
                    confidence=0.45, effective_from_day=day,
                    notes="Legacy current_location imported only as a low-confidence habitual anchor.",
                )

        # Explicit enterprise ties are legitimate present-day work anchors.
        for ent in conn.execute(
            """SELECT e.id,e.location_id FROM civilian_enterprises e
               LEFT JOIN enterprise_partners ep ON ep.enterprise_id=e.id AND ep.actor_id=? AND ep.status='active'
               WHERE e.status IN ('active','strained','insolvent') AND e.location_id IS NOT NULL
                 AND (e.owner_actor_id=? OR ep.actor_id=?)""",
            (aid, aid, aid),
        ).fetchall():
            ent_id = int(ent["id"])
            ent_loc = int(ent["location_id"])
            if not has_open_habit(aid, ent_loc, "work", "enterprise", ent_id):
                add_presence_habit(
                    conn, aid, ent_loc, habit_kind="work", weight=0.74, cadence_days=2,
                    basis_kind="enterprise", basis_id=ent_id, source_kind="derived", confidence=0.85,
                    effective_from_day=day,
                )

        # Institution membership can create a weaker institutional anchor if that institution has a location.
        for inst in conn.execute(
            """SELECT im.institution_actor_id,a.current_location_id FROM institution_memberships im
               JOIN actors a ON a.id=im.institution_actor_id
               WHERE im.member_actor_id=? AND im.status='active' AND a.current_location_id IS NOT NULL""",
            (aid,),
        ).fetchall():
            inst_id = int(inst["institution_actor_id"])
            inst_loc = int(inst["current_location_id"])
            if not has_open_habit(aid, inst_loc, "institution", "institution", inst_id):
                add_presence_habit(
                    conn, aid, inst_loc, habit_kind="institution", weight=0.34, cadence_days=7,
                    basis_kind="institution", basis_id=inst_id, source_kind="derived",
                    confidence=0.65, effective_from_day=day,
                )
    return made


def _active_travel(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT * FROM travel_plans WHERE subject_kind='actor' AND subject_id=?
           AND status IN ('active','stalled') ORDER BY id DESC LIMIT 1""",
        (actor_id,),
    ).fetchone()


def _location_is_large(conn: sqlite3.Connection, location_id: int) -> bool:
    row = conn.execute("SELECT kind FROM locations WHERE id=?", (location_id,)).fetchone()
    if not row:
        return False
    kind = str(row[0] or "").lower()
    return any(token in kind for token in ("city", "capital", "metropolis", "province", "region", "kingdom"))


def assess_presence(
    conn: sqlite3.Connection,
    actor_id: int,
    location_id: int,
    *,
    day: int | None = None,
    exact_present_actor_ids: Iterable[int] | None = None,
    exact_scene_complete: bool = False,
) -> PresenceAssessment:
    day = _current_day(conn) if day is None else int(day)
    exact = None if exact_present_actor_ids is None else {int(x) for x in exact_present_actor_ids}
    if exact is not None and actor_id in exact:
        return PresenceAssessment(actor_id, location_id, day, "exact_scene", 1.0, True, ("exact_scene",))
    if exact is not None and exact_scene_complete:
        return PresenceAssessment(actor_id, location_id, day, "exact_scene", 0.0, False, ("exact_scene_absence",))

    actor = conn.execute(
        "SELECT actor_type,status,home_location_id,current_location_id FROM actors WHERE id=?", (actor_id,)
    ).fetchone()
    if not actor or str(actor["status"]) != "active":
        return PresenceAssessment(actor_id, location_id, day, "aggregate", 0.0, False, ("inactive",))

    travel = _active_travel(conn, actor_id)
    if travel:
        # A current route means the actor is in transit, not standing at the last city endpoint.
        if travel["current_route_id"] is not None and travel["segment_due_day"] is not None and day < int(travel["segment_due_day"]):
            return PresenceAssessment(actor_id, location_id, day, "tracked_travel", 0.0, False, ("in_transit", f"route:{int(travel['current_route_id'])}"))
        here = int(travel["current_location_id"]) == int(location_id)
        return PresenceAssessment(
            actor_id, location_id, day, "tracked_travel", 1.0 if here else 0.0, here,
            (f"travel_plan:{int(travel['id'])}",),
        )

    if str(actor["actor_type"]) == "character" and not conn.execute(
        "SELECT 1 FROM actor_presence_profiles WHERE actor_id=?", (actor_id,)
    ).fetchone():
        # Freshly materialized/crystallized characters can appear after migration.
        # Institutions intentionally do not use character presence profiles; the old
        # unconditional branch repeatedly re-seeded every character whenever an
        # institution was assessed, without ever satisfying the missing-profile test.
        seed_presence_from_existing_state(conn, effective_day=day)

    rows = conn.execute(
        """SELECT * FROM actor_presence_habits WHERE actor_id=? AND location_id=?
           AND effective_from_day<=? AND (effective_to_day IS NULL OR effective_to_day>=?)
           ORDER BY weight DESC,id""",
        (actor_id, location_id, day, day),
    ).fetchall()
    basis: list[str] = []
    # Combine independent weak habits without allowing a broad city anchor to become certainty.
    miss = 1.0
    for row in rows:
        w = _clamp(float(row["weight"]) * (0.55 + 0.45 * float(row["confidence"])))
        if str(row["habit_kind"]) == "legacy_anchor" and _location_is_large(conn, location_id):
            w = min(w, 0.12)
        miss *= (1.0 - w)
        basis.append(f"habit:{int(row['id'])}:{row['habit_kind']}")
    probability = 1.0 - miss

    profile = conn.execute("SELECT * FROM actor_presence_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    if not rows and profile and profile["base_location_id"] is not None and int(profile["base_location_id"]) == int(location_id):
        probability = 0.52 if not _location_is_large(conn, location_id) else 0.22
        basis.append("profile_base")

    # Legacy current_location alone is never exact co-presence at settlement scale.
    if not basis and actor["current_location_id"] is not None and int(actor["current_location_id"]) == int(location_id):
        probability = 0.10 if _location_is_large(conn, location_id) else 0.28
        basis.append("legacy_current_location_fallback")

    return PresenceAssessment(
        actor_id, location_id, day, "habitual" if basis else "aggregate",
        round(_clamp(probability), 4), probability > 0.0, tuple(basis),
    )


def actor_is_present_candidate(
    conn: sqlite3.Connection,
    actor_id: int,
    location_id: int,
    *,
    day: int | None = None,
    purpose: str = "ordinary_contact",
    exact_present_actor_ids: Iterable[int] | None = None,
    exact_scene_complete: bool = False,
) -> bool:
    a = assess_presence(
        conn, actor_id, location_id, day=day, exact_present_actor_ids=exact_present_actor_ids,
        exact_scene_complete=exact_scene_complete,
    )
    if a.probability <= 0:
        return False
    if a.probability >= 1:
        return True
    return _stable_fraction("presence", actor_id, location_id, a.day, purpose) <= a.probability


def presence_probability_snapshot(
    conn: sqlite3.Connection,
    location_id: int,
    *,
    day: int | None = None,
    exact_present_actor_ids: Iterable[int] | None = None,
    exact_scene_complete: bool = False,
) -> dict[int, float]:
    """Return actor -> co-presence probability for one location/day.

    This is the reusable half of PRESBACK-01.  It contains no purpose/rumour-specific
    random draw, so information propagation can compute it once and reuse it for several
    rumours arriving at the same place on the same day.
    """
    day = _current_day(conn) if day is None else int(day)
    location_id = int(location_id)
    exact = set() if exact_present_actor_ids is None else {int(x) for x in exact_present_actor_ids}
    if exact_scene_complete and exact_present_actor_ids is not None:
        return {aid: 1.0 for aid in sorted(exact)}

    missing = conn.execute(
        """SELECT 1 FROM actors a LEFT JOIN actor_presence_profiles p ON p.actor_id=a.id
           WHERE a.actor_type='character' AND a.status='active' AND p.actor_id IS NULL LIMIT 1"""
    ).fetchone()
    if missing:
        seed_presence_from_existing_state(conn, effective_day=day)

    # PERF-01: each basis for being here is an indexed lookup; the old OR across left joins scanned every
    # character for every place and day, so rumour spread slowed as the named population grew.
    rows = conn.execute(
        """SELECT a.id,a.status,a.home_location_id,a.current_location_id
           FROM actors a
           WHERE a.actor_type='character' AND a.status='active' AND a.id IN (
               SELECT actor_id FROM actor_presence_habits WHERE location_id=?
                   AND effective_from_day<=? AND (effective_to_day IS NULL OR effective_to_day>=?)
               UNION SELECT actor_id FROM actor_presence_profiles WHERE base_location_id=?
               UNION SELECT id FROM actors WHERE current_location_id=?
               UNION SELECT subject_id FROM travel_plans WHERE current_location_id=? AND subject_kind='actor'
                   AND status IN ('active','stalled'))
           ORDER BY a.id""",
        (location_id, day, day, location_id, location_id, location_id),
    ).fetchall()
    actor_by_id = {int(r["id"]): r for r in rows}
    ids = set(actor_by_id)
    ids.update(exact)
    if not ids:
        return {}

    ordinary_ids = sorted(actor_by_id)
    travel_by_actor: dict[int, sqlite3.Row] = {}
    profiles: dict[int, sqlite3.Row] = {}
    if ordinary_ids:
        marks = ",".join("?" for _ in ordinary_ids)
        for row in conn.execute(
            f"""SELECT * FROM travel_plans WHERE subject_kind='actor'
                 AND status IN ('active','stalled') AND subject_id IN ({marks})
                 ORDER BY subject_id,id DESC""",
            tuple(ordinary_ids),
        ).fetchall():
            aid = int(row["subject_id"])
            if aid not in travel_by_actor:
                travel_by_actor[aid] = row
        profiles = {int(r["actor_id"]): r for r in conn.execute(
            f"SELECT * FROM actor_presence_profiles WHERE actor_id IN ({marks})",
            tuple(ordinary_ids),
        ).fetchall()}

    habits_by_actor: dict[int, list[sqlite3.Row]] = {}
    for row in conn.execute(
        """SELECT * FROM actor_presence_habits WHERE location_id=?
           AND effective_from_day<=? AND (effective_to_day IS NULL OR effective_to_day>=?)
           ORDER BY actor_id,weight DESC,id""",
        (location_id, day, day),
    ).fetchall():
        habits_by_actor.setdefault(int(row["actor_id"]), []).append(row)

    large_location = _location_is_large(conn, location_id)
    out: dict[int, float] = {}
    for aid in sorted(ids):
        if aid in exact:
            out[aid] = 1.0
            continue
        actor = actor_by_id.get(aid)
        if actor is None or str(actor["status"]) != "active":
            continue
        travel = travel_by_actor.get(aid)
        if travel is not None:
            if travel["current_route_id"] is not None and travel["segment_due_day"] is not None and day < int(travel["segment_due_day"]):
                continue
            if int(travel["current_location_id"]) == location_id:
                out[aid] = 1.0
            continue
        rows_for_actor = habits_by_actor.get(aid, ())
        miss = 1.0
        has_basis = False
        for row in rows_for_actor:
            w = _clamp(float(row["weight"]) * (0.55 + 0.45 * float(row["confidence"])))
            if str(row["habit_kind"]) == "legacy_anchor" and large_location:
                w = min(w, 0.12)
            miss *= (1.0 - w)
            has_basis = True
        probability = 1.0 - miss
        profile = profiles.get(aid)
        if not has_basis and profile is not None and profile["base_location_id"] is not None and int(profile["base_location_id"]) == location_id:
            probability = 0.22 if large_location else 0.52
            has_basis = True
        if not has_basis and actor["current_location_id"] is not None and int(actor["current_location_id"]) == location_id:
            probability = 0.10 if large_location else 0.28
        probability = round(_clamp(probability), 4)
        if probability > 0.0:
            out[aid] = probability
    return out


def actors_plausibly_present(
    conn: sqlite3.Connection,
    location_id: int,
    *,
    day: int | None = None,
    purpose: str = "ordinary_contact",
    exact_present_actor_ids: Iterable[int] | None = None,
    exact_scene_complete: bool = False,
    probability_snapshot: dict[int, float] | None = None,
) -> list[int]:
    """Return deterministic plausible co-presence from a reusable probability snapshot."""
    day = _current_day(conn) if day is None else int(day)
    location_id = int(location_id)
    snapshot = probability_snapshot
    if snapshot is None:
        snapshot = presence_probability_snapshot(
            conn, location_id, day=day, exact_present_actor_ids=exact_present_actor_ids,
            exact_scene_complete=exact_scene_complete,
        )
    out = []
    for aid in sorted(snapshot):
        probability = float(snapshot[aid])
        if probability >= 1.0 or _stable_fraction("presence", aid, location_id, day, purpose) <= probability:
            out.append(aid)
    return out
