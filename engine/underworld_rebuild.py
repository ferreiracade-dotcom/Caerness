from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable

from .business import commercial_context, configure_enterprise_business
from .civilian import create_enterprise
from .civilian_life import create_building
from .continuity import set_resolution, upsert_continuity_core
from .health import ensure_health_profile
from .underworld import create_underworld_organization, ensure_underworld_membership_profile
from .territorial_events import append_territorial_event


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        out = json.loads(value)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _seed(conn: sqlite3.Connection, salt: int = 0) -> int:
    r = conn.execute("SELECT rng_seed,current_day FROM world_state WHERE id=1").fetchone()
    return int(r[0]) * 1_000_003 + int(r[1]) * 9_973 + int(salt)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


# Form is institutional grammar, never a power tier. The defaults are priors for a newly
# generated organization; history can move every continuous dimension without changing form.


LEGACY_UNDERWORLD_QUARRY_NAMES = (
    # Anti-grandfathering targets the old city-assigned durable criminal organizations, not
    # every pre-existing underworld-adjacent institution/ecology in the current World Bible.
    "Tallow Family", "Greyhook Wharf Company", "Saltwake Combine",
)

def enforce_rebuild_firewall(conn: sqlite3.Connection) -> int:
    """Retire inherited underworld answers after seed import as well as during migration.

    Fresh campaigns import the current seed after schema migrations, so migration-time retirement
    alone is insufficient. The larger world remains intact; only underworld-specific named answers
    are moved to quarry unless deliberately re-adopted later.
    """
    day=_day(conn); retired=0
    for name in LEGACY_UNDERWORLD_QUARRY_NAMES:
        row=conn.execute("SELECT id,status FROM actors WHERE actor_type='institution' AND name=?",(name,)).fetchone()
        if not row: continue
        aid=int(row['id'])
        conn.execute("INSERT OR IGNORE INTO underworld_rebuild_quarry(actor_id,retired_name,retired_day,reason,metadata_json) VALUES (?,?,?,?,?)",
                     (aid,name,day,'v0.60 clean underworld rebuild; retained only as historical quarry',_j({'not_grandfathered':True,'post_seed_firewall':True})))
        if str(row['status'])!='retired':
            conn.execute("UPDATE actors SET status='retired' WHERE id=?",(aid,)); retired+=1
        conn.execute("UPDATE underworld_institution_profiles SET status='retired' WHERE institution_actor_id=?",(aid,))
        conn.execute("UPDATE underworld_organizations SET status='dormant' WHERE institution_actor_id=?",(aid,))
        conn.execute("UPDATE civilian_enterprises SET status='historical' WHERE institution_actor_id=? AND json_extract(metadata_json,'$.underworld_front')=1",(aid,))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_rebuild_firewall_post_seed','1')")
    return retired

FORM_DEFAULTS: dict[str, dict[str, Any]] = {
    "gang": {
        "membership_model": "fluid", "continuity_model": "personalist",
        "territorial_orientation": 82, "formality": 28, "violence_governance": 35,
        "open_core_command_bias": 86, "identity_strength": 78, "induction_required": 0,
        "hereditary_headship_preference": 5,
    },
    "mafia_family": {
        "membership_model": "sworn", "continuity_model": "corporate",
        "territorial_orientation": 66, "formality": 84, "violence_governance": 78,
        "open_core_command_bias": 82, "identity_strength": 92, "induction_required": 1,
        "hereditary_headship_preference": 8,
    },
    "criminal_dynasty": {
        "membership_model": "blood_household", "continuity_model": "dynastic",
        "territorial_orientation": 58, "formality": 64, "violence_governance": 62,
        "open_core_command_bias": 80, "identity_strength": 90, "induction_required": 0,
        "hereditary_headship_preference": 88,
    },
    "syndicate": {
        "membership_model": "contractual", "continuity_model": "commercial",
        "territorial_orientation": 30, "formality": 72, "violence_governance": 70,
        "open_core_command_bias": 66, "identity_strength": 48, "induction_required": 0,
        "hereditary_headship_preference": 3,
    },
    "criminal_enterprise": {
        "membership_model": "contractual", "continuity_model": "commercial",
        "territorial_orientation": 38, "formality": 58, "violence_governance": 58,
        "open_core_command_bias": 68, "identity_strength": 44, "induction_required": 0,
        "hereditary_headship_preference": 10,
    },
    "network": {
        "membership_model": "networked", "continuity_model": "federated",
        "territorial_orientation": 12, "formality": 22, "violence_governance": 45,
        "open_core_command_bias": 52, "identity_strength": 35, "induction_required": 0,
        "hereditary_headship_preference": 0,
    },
    "crew": {
        "membership_model": "fluid", "continuity_model": "personalist",
        "territorial_orientation": 62, "formality": 18, "violence_governance": 28,
        "open_core_command_bias": 82, "identity_strength": 70, "induction_required": 0,
        "hereditary_headship_preference": 0,
    },
    "other": {
        "membership_model": "fluid", "continuity_model": "personalist",
        "territorial_orientation": 45, "formality": 40, "violence_governance": 45,
        "open_core_command_bias": 70, "identity_strength": 50, "induction_required": 0,
        "hereditary_headship_preference": 10,
    },
}

# These are activity-specific norms, not morality labels attached to organizational form.
# Values: forbid / disfavor / tolerate / permit. New organizations draw their own code.
TABOO_ACTIVITIES = (
    "coercive_human_trafficking", "child_predation", "indiscriminate_local_robbery",
    "unauthorized_murder", "hard_drug_trade", "kidnapping_for_ransom",
)


def ensure_organization_culture(
    conn: sqlite3.Connection,
    organization_id: int,
    *,
    overrides: dict[str, Any] | None = None,
    rng: random.Random | None = None,
) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM underworld_organization_culture WHERE organization_id=?", (organization_id,)).fetchone()
    if row:
        return row
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
    if not org:
        raise ValueError("unknown underworld organization")
    base = dict(FORM_DEFAULTS.get(str(org["organization_type"]), FORM_DEFAULTS["other"]))
    if rng is None:
        rng = random.Random(_seed(conn, organization_id * 701))
    # Codes vary by organization. Form can affect governance strength but does not decide which
    # harms are acceptable. This is intentionally independent of gang/mafia/dynasty identity.
    taboo: dict[str, str] = {}
    for activity in TABOO_ACTIVITIES:
        x = rng.random()
        if activity == "child_predation":
            taboo[activity] = "forbid" if x < .72 else ("disfavor" if x < .94 else "permit")
        elif activity == "unauthorized_murder":
            taboo[activity] = "forbid" if x < .22 else ("disfavor" if x < .68 else "permit")
        else:
            taboo[activity] = "forbid" if x < .18 else ("disfavor" if x < .48 else ("tolerate" if x < .76 else "permit"))
    base["taboo_policy_json"] = _j(taboo)
    base["metadata_json"] = _j({"generated_from_form_grammar": True, "form_is_not_power_tier": True, "form_is_not_morality": True})
    if overrides:
        for k, v in overrides.items():
            if k == "taboo_policy_json" and isinstance(v, dict):
                base[k] = _j(v)
            elif k in base:
                base[k] = v
    cols = [
        "organization_id", "membership_model", "continuity_model", "territorial_orientation", "formality",
        "violence_governance", "open_core_command_bias", "identity_strength", "induction_required",
        "hereditary_headship_preference", "taboo_policy_json", "metadata_json",
    ]
    vals = [organization_id] + [base[c] for c in cols[1:]]
    conn.execute(
        f"INSERT INTO underworld_organization_culture({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
        vals,
    )
    return conn.execute("SELECT * FROM underworld_organization_culture WHERE organization_id=?", (organization_id,)).fetchone()


def set_organization_taboo(conn: sqlite3.Connection, organization_id: int, activity: str, policy: str) -> None:
    if policy not in {"forbid", "disfavor", "tolerate", "permit"}:
        raise ValueError("invalid taboo policy")
    row = ensure_organization_culture(conn, organization_id)
    policies = _loads(row["taboo_policy_json"])
    policies[str(activity)] = policy
    conn.execute("UPDATE underworld_organization_culture SET taboo_policy_json=? WHERE organization_id=?", (_j(policies), organization_id))


def organization_code_allows(conn: sqlite3.Connection, organization_id: int, activity: str) -> bool:
    row = ensure_organization_culture(conn, organization_id)
    policy = _loads(row["taboo_policy_json"]).get(activity, "tolerate")
    return policy in {"tolerate", "permit"}


def _zone_location_id(conn: sqlite3.Connection, zone_id: int | None) -> int | None:
    if zone_id is None:
        return None
    row = conn.execute("SELECT anchor_location_id, city_location_id FROM underworld_zones WHERE id=?", (zone_id,)).fetchone()
    if not row:
        return None
    return int(row[0]) if row[0] is not None else (int(row[1]) if row[1] is not None else None)


def _organization_actor_id(conn: sqlite3.Connection, organization_id: int | None) -> int | None:
    if organization_id is None:
        return None
    row = conn.execute("SELECT institution_actor_id FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _event_severity_from_100(raw: float) -> int:
    return max(1, min(5, int(round(1 + (_clamp(raw) / 100.0) * 4))))


def _record_territorial_occurrence(
    conn: sqlite3.Connection, *, event_logger: Callable[..., int] | None, event_type: str, title: str, summary: str,
    severity_0_100: float = 25, zone_id: int | None = None, source_organization_id: int | None = None,
    target_organization_id: int | None = None, visibility: str | None = None, tags: list[str] | None = None,
    operation_id: int | None = None, incident_id: int | None = None, metadata: dict[str, Any] | None = None,
) -> int | None:
    """Record a machine-readable territorial occurrence, Phase 2A section 3.2/3.3.

    This intentionally reuses the engine's existing events/event_targets/causal_links
    tables rather than building a parallel occurrence framework. If territorial sovereignty
    is later migrated onto full event-sourcing, this call site already carries clean
    event_type names and cause links instead of starting from prose. event_logger is the
    same Callable[...,int] convention used throughout the engine (see household_life.py);
    when a caller has none available, the underworld_operations/underworld_incidents row
    remains the authoritative record and no event is created.
    """
    if event_logger is None:
        return None
    day = _day(conn)
    meta = dict(metadata or {})
    if zone_id is not None:
        meta.setdefault("zone_id", zone_id)
    if source_organization_id is not None:
        meta.setdefault("source_organization_id", source_organization_id)
    if target_organization_id is not None:
        meta.setdefault("target_organization_id", target_organization_id)
    if tags:
        meta["tags"] = list(tags)
    location_id = _zone_location_id(conn, zone_id)
    source_actor_id = _organization_actor_id(conn, source_organization_id)
    target_actor_id = _organization_actor_id(conn, target_organization_id)
    target_actor_ids = tuple(a for a in (target_actor_id,) if a is not None)
    try:
        event_id = event_logger(
            day=day, event_type=event_type, title=title, summary=summary,
            severity=_event_severity_from_100(severity_0_100), source_actor_id=source_actor_id,
            target_actor_ids=target_actor_ids, location_id=location_id, visibility=visibility,
        )
    except TypeError:
        # Some callers' event_logger signatures may not accept every kwarg; degrade to the
        # minimal common convention rather than lose the record entirely.
        event_id = event_logger(day=day, event_type=event_type, title=title, summary=summary,
                                 severity=_event_severity_from_100(severity_0_100))
    if event_id is not None:
        for kind, rid in (("underworld_operation", operation_id), ("underworld_incident", incident_id)):
            if rid is not None:
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO causal_links(day,source_kind,source_id,target_kind,target_id,relation)
                           VALUES (?,?,?,?,?,?)""",
                        (day, "world_process", int(rid), "event", int(event_id), kind),
                    )
                except sqlite3.Error:
                    pass
    return event_id


def create_zone(
    conn: sqlite3.Connection, city_location_id: int, zone_key: str, name: str, *,
    zone_kind: str = "mixed", population_scale: float = 50, commercial_intensity: float = 50,
    street_visibility: float = 50, policing_pressure: float = 50, metadata: dict[str, Any] | None = None,
) -> int:
    key = f"{city_location_id}:{zone_key}"
    conn.execute(
        """INSERT INTO underworld_zones(city_location_id,zone_key,name,zone_kind,population_scale,commercial_intensity,street_visibility,policing_pressure,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,'active',?)
           ON CONFLICT(zone_key) DO UPDATE SET name=excluded.name,zone_kind=excluded.zone_kind,
             population_scale=excluded.population_scale,commercial_intensity=excluded.commercial_intensity,
             street_visibility=excluded.street_visibility,policing_pressure=excluded.policing_pressure,metadata_json=excluded.metadata_json""",
        (city_location_id, key, name, zone_kind, _clamp(population_scale), _clamp(commercial_intensity),
         _clamp(street_visibility), _clamp(policing_pressure), _j(metadata or {})),
    )
    return int(conn.execute("SELECT id FROM underworld_zones WHERE zone_key=?", (key,)).fetchone()[0])


def set_zone_adjacency(conn: sqlite3.Connection, zone_a_id: int, zone_b_id: int, *, permeability: float = 50, metadata: dict[str, Any] | None = None) -> None:
    if zone_a_id == zone_b_id:
        return
    a, b = sorted((int(zone_a_id), int(zone_b_id)))
    conn.execute(
        """INSERT INTO underworld_zone_adjacency(zone_a_id,zone_b_id,permeability,metadata_json) VALUES (?,?,?,?)
           ON CONFLICT(zone_a_id,zone_b_id) DO UPDATE SET permeability=excluded.permeability,metadata_json=excluded.metadata_json""",
        (a, b, _clamp(permeability), _j(metadata or {})),
    )


class UnderworldZoneGraph:
    """Read-only adjacency abstraction over underworld_zone_adjacency.

    SQL remains authoritative here; this class exists so decision logic and future
    Phase 2 code stop hand-rolling adjacency SQL and can later swap in a NetworkX,
    rustworkx or NetworKit backend without changing any caller. No graph library is
    used yet because plain SQL/Python is sufficient for the current zone counts.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def neighbors(self, zone_id: int) -> list[int]:
        rows = self._conn.execute(
            """SELECT CASE WHEN zone_a_id=? THEN zone_b_id ELSE zone_a_id END AS other
               FROM underworld_zone_adjacency WHERE zone_a_id=? OR zone_b_id=? ORDER BY other""",
            (zone_id, zone_id, zone_id),
        ).fetchall()
        return [int(r[0]) for r in rows]

    def are_adjacent(self, zone_a_id: int, zone_b_id: int) -> bool:
        if int(zone_a_id) == int(zone_b_id):
            return False
        a, b = sorted((int(zone_a_id), int(zone_b_id)))
        return bool(self._conn.execute(
            "SELECT 1 FROM underworld_zone_adjacency WHERE zone_a_id=? AND zone_b_id=? LIMIT 1", (a, b)
        ).fetchone())

    def permeability(self, zone_a_id: int, zone_b_id: int) -> float | None:
        if int(zone_a_id) == int(zone_b_id):
            return None
        a, b = sorted((int(zone_a_id), int(zone_b_id)))
        row = self._conn.execute(
            "SELECT permeability FROM underworld_zone_adjacency WHERE zone_a_id=? AND zone_b_id=? LIMIT 1", (a, b)
        ).fetchone()
        return float(row[0]) if row else None

    def reachable_from(self, zone_ids: list[int], *, max_depth: int | None = None) -> list[int]:
        """Zones reachable by crossing adjacency edges from the given starting set.

        Excludes the starting zones themselves. Deterministic: neighbor expansion is
        ordered by zone id, and each zone appears once, at the depth it was first seen.
        """
        frontier = list(dict.fromkeys(int(z) for z in zone_ids))
        seen = set(frontier)
        order: list[int] = []
        depth = 0
        while frontier and (max_depth is None or depth < max_depth):
            nxt: list[int] = []
            for zid in frontier:
                for other in self.neighbors(zid):
                    if other not in seen:
                        seen.add(other)
                        nxt.append(other)
                        order.append(other)
            frontier = nxt
            depth += 1
        return order


def zone_controller(conn: sqlite3.Connection, zone_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM underworld_zone_claims WHERE zone_id=? AND claim_kind='controller' AND status='active' ORDER BY id LIMIT 1",
        (zone_id,),
    ).fetchone()


def set_zone_controller(
    conn: sqlite3.Connection, zone_id: int, organization_id: int, *, strength: float = 60,
    local_support: float = 45, fear: float = 55, metadata: dict[str, Any] | None = None,
    event_logger: Callable[..., int] | None = None,
) -> int:
    day = _day(conn)
    old = zone_controller(conn, zone_id)
    if old and int(old["organization_id"]) == int(organization_id):
        conn.execute(
            "UPDATE underworld_zone_claims SET strength=?,local_support=?,fear=?,metadata_json=? WHERE id=?",
            (_clamp(strength), _clamp(local_support), _clamp(fear), _j(metadata or _loads(old["metadata_json"])), int(old["id"])),
        )
        append_territorial_event(conn, "territory.zone_control_set", {
            "zone_id": int(zone_id), "new_controller_organization_id": int(organization_id),
            "strength": _clamp(strength), "local_support": _clamp(local_support), "fear": _clamp(fear),
            "started_day": int(old["started_day"]),
        }, day=day, cause_kind="underworld_zone_claim", cause_id=int(old["id"]))
        return int(old["id"])
    old_organization_id = int(old["organization_id"]) if old else None
    if old:
        conn.execute("UPDATE underworld_zone_claims SET status='lost' WHERE id=?", (int(old["id"]),))
    cur = conn.execute(
        """INSERT INTO underworld_zone_claims(zone_id,organization_id,claim_kind,strength,local_support,fear,started_day,status,metadata_json)
           VALUES (?,?,'controller',?,?,?,?, 'active',?)""",
        (zone_id, organization_id, _clamp(strength), _clamp(local_support), _clamp(fear), day, _j(metadata or {})),
    )
    claim_id = int(cur.lastrowid)
    _refresh_territory_summary(conn, organization_id)
    if old:
        _refresh_territory_summary(conn, old_organization_id)
    append_territorial_event(conn, "territory.zone_control_set", {
        "zone_id": int(zone_id), "new_controller_organization_id": int(organization_id),
        "strength": _clamp(strength), "local_support": _clamp(local_support), "fear": _clamp(fear),
        "started_day": day, "old_controller_organization_id": old_organization_id,
    }, day=day, cause_kind="underworld_zone_claim", cause_id=claim_id)
    zone_name = conn.execute("SELECT name FROM underworld_zones WHERE id=?", (zone_id,)).fetchone()
    zname = str(zone_name[0]) if zone_name else f"zone {zone_id}"
    if old_organization_id is None:
        _record_territorial_occurrence(
            conn, event_logger=event_logger, event_type="underworld_zone_claim_established",
            title=f"Territorial claim established: {zname}", summary=f"An organization established uncontested control of {zname}.",
            severity_0_100=30, zone_id=zone_id, source_organization_id=organization_id,
            metadata={"claim_id": claim_id, "strength": strength},
        )
    else:
        _record_territorial_occurrence(
            conn, event_logger=event_logger, event_type="underworld_zone_control_changed",
            title=f"Territorial control changed: {zname}", summary=f"Control of {zname} passed to a new organization.",
            severity_0_100=45, zone_id=zone_id, source_organization_id=organization_id,
            target_organization_id=old_organization_id, tags=["territorial_change"],
            metadata={"claim_id": claim_id, "old_controller_organization_id": old_organization_id, "new_controller_organization_id": organization_id, "strength": strength},
        )
    return claim_id


def add_zone_challenger(
    conn: sqlite3.Connection, zone_id: int, organization_id: int, *, strength: float = 35, severity: float = 35,
    metadata: dict[str, Any] | None = None, event_logger: Callable[..., int] | None = None,
) -> int:
    day = _day(conn)
    had_challenger_before = bool(conn.execute(
        "SELECT 1 FROM underworld_zone_claims WHERE zone_id=? AND claim_kind='challenger' AND status='active' LIMIT 1", (zone_id,)
    ).fetchone())
    row = conn.execute(
        "SELECT id FROM underworld_zone_claims WHERE zone_id=? AND organization_id=? AND claim_kind='challenger' AND status='active' ORDER BY id LIMIT 1",
        (zone_id, organization_id),
    ).fetchone()
    if row:
        conn.execute("UPDATE underworld_zone_claims SET strength=MAX(strength,?) WHERE id=?", (_clamp(strength), int(row[0])))
        cid = int(row[0])
    else:
        cid = int(conn.execute(
            """INSERT INTO underworld_zone_claims(zone_id,organization_id,claim_kind,strength,local_support,fear,started_day,status,metadata_json)
               VALUES (?,?,'challenger',?,35,50,?,'active',?)""",
            (zone_id, organization_id, _clamp(strength), day, _j(metadata or {})),
        ).lastrowid)
    ctrl = zone_controller(conn, zone_id)
    controller_organization_id = int(ctrl["organization_id"]) if ctrl else None
    incident_id = int(conn.execute(
        """INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
           VALUES (?,?,?,?,?,?, 'open',?)""",
        (day, zone_id, organization_id, controller_organization_id, "territorial_challenge", _clamp(severity), _j(metadata or {})),
    ).lastrowid)
    append_territorial_event(conn, "territory.challenger_added", {
        "zone_id": int(zone_id), "organization_id": int(organization_id),
        "strength": _clamp(strength), "started_day": day,
    }, day=day, cause_kind="underworld_incident", cause_id=incident_id)
    if not had_challenger_before:
        zone_name = conn.execute("SELECT name FROM underworld_zones WHERE id=?", (zone_id,)).fetchone()
        zname = str(zone_name[0]) if zone_name else f"zone {zone_id}"
        _record_territorial_occurrence(
            conn, event_logger=event_logger, event_type="underworld_zone_became_contested",
            title=f"Zone contested: {zname}", summary=f"{zname} became actively contested territory.",
            severity_0_100=severity, zone_id=zone_id, source_organization_id=organization_id,
            target_organization_id=controller_organization_id, incident_id=incident_id, tags=["contest"],
            metadata={"challenger_claim_id": cid},
        )
    return cid


def grant_operating_permission(
    conn: sqlite3.Connection, zone_id: int, controller_organization_id: int, guest_organization_id: int,
    activity_kind: str, *, tribute_rate: float = 0.0, expiry_day: int | None = None, metadata: dict[str, Any] | None = None,
    event_logger: Callable[..., int] | None = None,
) -> int:
    ctrl = zone_controller(conn, zone_id)
    if not ctrl or int(ctrl["organization_id"]) != int(controller_organization_id):
        raise ValueError("permission can only be granted by the active territorial controller")
    day = _day(conn)
    superseded = conn.execute(
        "SELECT * FROM underworld_operating_permissions WHERE zone_id=? AND guest_organization_id=? AND activity_kind=? AND status='active'",
        (zone_id, guest_organization_id, activity_kind),
    ).fetchone()
    conn.execute(
        "UPDATE underworld_operating_permissions SET status='revoked' WHERE zone_id=? AND guest_organization_id=? AND activity_kind=? AND status='active'",
        (zone_id, guest_organization_id, activity_kind),
    )
    permission_id = int(conn.execute(
        """INSERT INTO underworld_operating_permissions(zone_id,controller_organization_id,guest_organization_id,activity_kind,tribute_rate,started_day,expiry_day,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,'active',?)""",
        (zone_id, controller_organization_id, guest_organization_id, activity_kind, max(0.0, min(1.0, float(tribute_rate))), day, expiry_day, _j(metadata or {})),
    ).lastrowid)
    if superseded:
        append_territorial_event(conn, "territory.permission_revoked", {
            "permission_id": int(superseded["id"]), "zone_id": int(zone_id), "reason": "superseded"
        }, day=day, cause_kind="underworld_permission", cause_id=int(superseded["id"]))
    append_territorial_event(conn, "territory.permission_granted", {
        "permission_id": permission_id, "zone_id": int(zone_id),
        "controller_organization_id": int(controller_organization_id), "guest_organization_id": int(guest_organization_id),
        "activity_kind": str(activity_kind), "tribute_rate": max(0.0, min(1.0, float(tribute_rate))),
        "started_day": day, "expiry_day": int(expiry_day) if expiry_day is not None else None,
    }, day=day, cause_kind="underworld_permission", cause_id=permission_id)
    zone_name = conn.execute("SELECT name FROM underworld_zones WHERE id=?", (zone_id,)).fetchone()
    zname = str(zone_name[0]) if zone_name else f"zone {zone_id}"
    if superseded:
        _record_territorial_occurrence(
            conn, event_logger=event_logger, event_type="underworld_operating_permission_revoked",
            title=f"Operating permission superseded: {zname}", summary=f"A prior {activity_kind} permission in {zname} was superseded by a new grant.",
            severity_0_100=15, zone_id=zone_id, source_organization_id=controller_organization_id,
            target_organization_id=guest_organization_id, tags=["permission", activity_kind],
            metadata={"permission_id": int(superseded[0]), "activity_kind": activity_kind, "reason": "superseded"},
        )
    _record_territorial_occurrence(
        conn, event_logger=event_logger, event_type="underworld_operating_permission_granted",
        title=f"Operating permission granted: {zname}", summary=f"The controller of {zname} granted a {activity_kind} permission.",
        severity_0_100=15, zone_id=zone_id, source_organization_id=controller_organization_id,
        target_organization_id=guest_organization_id, tags=["permission", activity_kind],
        metadata={"permission_id": permission_id, "activity_kind": activity_kind, "tribute_rate": tribute_rate},
    )
    return permission_id


def revoke_operating_permission(
    conn: sqlite3.Connection, permission_id: int, *, reason: str = "revoked", event_logger: Callable[..., int] | None = None,
) -> bool:
    """Explicit revocation, distinct from the implicit supersede-on-regrant in grant_operating_permission."""
    row = conn.execute("SELECT * FROM underworld_operating_permissions WHERE id=? AND status='active'", (permission_id,)).fetchone()
    if not row:
        return False
    conn.execute("UPDATE underworld_operating_permissions SET status='revoked' WHERE id=?", (permission_id,))
    append_territorial_event(conn, "territory.permission_revoked", {
        "permission_id": int(permission_id), "zone_id": int(row["zone_id"]), "reason": str(reason)
    }, day=_day(conn), cause_kind="underworld_permission", cause_id=int(permission_id))
    zone_name = conn.execute("SELECT name FROM underworld_zones WHERE id=?", (int(row["zone_id"]),)).fetchone()
    zname = str(zone_name[0]) if zone_name else f"zone {row['zone_id']}"
    _record_territorial_occurrence(
        conn, event_logger=event_logger, event_type="underworld_operating_permission_revoked",
        title=f"Operating permission revoked: {zname}", summary=f"A {row['activity_kind']} permission in {zname} was revoked ({reason}).",
        severity_0_100=20, zone_id=int(row["zone_id"]), source_organization_id=int(row["controller_organization_id"]),
        target_organization_id=int(row["guest_organization_id"]), tags=["permission", str(row["activity_kind"])],
        metadata={"permission_id": permission_id, "activity_kind": row["activity_kind"], "reason": reason},
    )
    return True


TERRITORIAL_ACTIVITIES = {
    "protection", "collections", "patrol", "open_recruitment", "street_gambling", "local_bookmaking",
    "local_debt_enforcement", "brothel_protection", "street_distribution", "local_extortion",
}


# Racket kinds and their real numbers. "Universal" kinds are plausible in any city, any
# zone, because gambling, debt, fencing, and nightlife are ordinary underworld economy
# everywhere per the World Bible, not something specific to one city's flavor. The
# "warehouse-flavored" kinds get extra weight in warehouse/commercial/caravan zones (the
# paperwork-and-cargo crime the Bible calls out for Aldergate specifically), but they are
# not exclusive to Aldergate and not a replacement for the universal baseline: zone_kind
# decides the weighting, not city identity, so this generalizes to any city's own
# warehouse district without hardcoding a place name.
#
# income_mult/heat_mult scale the existing gross_income_per_30/heat contribution relative
# to a kind-neutral baseline of 1.0. secrecy_base/violence_base are the defaults
# create_racket_site uses when a caller does not specify its own. activity is the real
# TERRITORIAL_ACTIVITIES entry this racket kind actually is, replacing the old two-bucket
# substring guess.
RACKET_PROFILES: dict[str, dict[str, Any]] = {
    "protection collections": {"income_mult": 1.0, "heat_mult": 0.9, "secrecy_base": 55, "violence_base": 30, "activity": "protection", "preferred_zone_kinds": ()},
    "unlicensed bookmaking": {"income_mult": 1.05, "heat_mult": 0.95, "secrecy_base": 50, "violence_base": 12, "activity": "local_bookmaking", "preferred_zone_kinds": ("market", "mixed")},
    "illegal gaming": {"income_mult": 1.0, "heat_mult": 1.0, "secrecy_base": 45, "violence_base": 10, "activity": "street_gambling", "preferred_zone_kinds": ("market", "mixed")},
    "high-risk debt": {"income_mult": 1.3, "heat_mult": 1.15, "secrecy_base": 45, "violence_base": 28, "activity": "local_debt_enforcement", "preferred_zone_kinds": ()},
    "stolen goods": {"income_mult": 1.15, "heat_mult": 1.05, "secrecy_base": 55, "violence_base": 15, "activity": "street_distribution", "preferred_zone_kinds": ("warehouse",)},
    "brothel protection": {"income_mult": 1.1, "heat_mult": 0.9, "secrecy_base": 50, "violence_base": 20, "activity": "brothel_protection", "preferred_zone_kinds": ("mixed", "residential")},
    "courtesan house leverage": {"income_mult": 1.25, "heat_mult": 0.55, "secrecy_base": 74, "violence_base": 2, "activity": "local_extortion", "preferred_zone_kinds": ("mixed", "market")},
    "cargo fraud": {"income_mult": 1.35, "heat_mult": 0.75, "secrecy_base": 68, "violence_base": 4, "activity": "collections", "preferred_zone_kinds": ("warehouse", "caravan")},
    "invoice fraud": {"income_mult": 1.4, "heat_mult": 0.65, "secrecy_base": 75, "violence_base": 0, "activity": "collections", "preferred_zone_kinds": ("warehouse", "commercial")},
    "warehouse theft": {"income_mult": 1.2, "heat_mult": 0.85, "secrecy_base": 60, "violence_base": 8, "activity": "collections", "preferred_zone_kinds": ("warehouse",)},
    "seal manipulation": {"income_mult": 1.25, "heat_mult": 0.6, "secrecy_base": 78, "violence_base": 0, "activity": "collections", "preferred_zone_kinds": ("warehouse", "commercial")},
}

UNIVERSAL_RACKET_KINDS = ("protection collections", "unlicensed bookmaking", "illegal gaming", "high-risk debt", "stolen goods", "brothel protection", "courtesan house leverage")
WAREHOUSE_FLAVORED_RACKET_KINDS = ("cargo fraud", "invoice fraud", "warehouse theft", "seal manipulation")


def racket_kind_options(conn: sqlite3.Connection, zone_id: int | None, rng: random.Random, *, count: int = 1) -> list[str]:
    """Pick racket kinds with the universal baseline always available everywhere, and the
    warehouse-flavored kinds given extra weight (not exclusivity) when the zone's own
    zone_kind matches. No zone -> universal pool only, since there is nothing to flavor
    against.
    """
    weighted: list[str] = list(UNIVERSAL_RACKET_KINDS)
    if zone_id is not None:
        zone = conn.execute("SELECT zone_kind FROM underworld_zones WHERE id=?", (zone_id,)).fetchone()
        zone_kind = str(zone[0]) if zone else None
        for kind in WAREHOUSE_FLAVORED_RACKET_KINDS:
            weight = 3 if zone_kind in RACKET_PROFILES[kind]["preferred_zone_kinds"] else 1
            weighted += [kind] * weight
    else:
        weighted += list(WAREHOUSE_FLAVORED_RACKET_KINDS)
    return [rng.choice(weighted) for _ in range(count)]


def activity_authorized(conn: sqlite3.Connection, zone_id: int, organization_id: int, activity_kind: str) -> bool:
    ctrl = zone_controller(conn, zone_id)
    if not ctrl or int(ctrl["organization_id"]) == int(organization_id):
        return True
    if activity_kind not in TERRITORIAL_ACTIVITIES:
        return True
    row = conn.execute(
        """SELECT 1 FROM underworld_operating_permissions
           WHERE zone_id=? AND guest_organization_id=? AND activity_kind=? AND status='active'
             AND (expiry_day IS NULL OR expiry_day>=?) LIMIT 1""",
        (zone_id, organization_id, activity_kind, _day(conn)),
    ).fetchone()
    return bool(row)


def attempt_local_activity(
    conn: sqlite3.Connection, zone_id: int, organization_id: int, activity_kind: str, *, severity: float = 25,
    enterprise_id: int | None = None, metadata: dict[str, Any] | None = None, event_logger: Callable[..., int] | None = None,
) -> dict[str, Any]:
    if activity_authorized(conn, zone_id, organization_id, activity_kind):
        return {"authorized": True, "incident_id": None}
    ctrl = zone_controller(conn, zone_id)
    controller_organization_id = int(ctrl["organization_id"]) if ctrl else None
    day = _day(conn)
    meta = dict(metadata or {})
    if enterprise_id is not None:
        meta["enterprise_id"] = int(enterprise_id)
    incident = conn.execute(
        """INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
           VALUES (?,?,?,?,?,?, 'open',?)""",
        (day, zone_id, organization_id, controller_organization_id,
         f"encroachment:{activity_kind}", _clamp(severity), _j(meta)),
    )
    incident_id = int(incident.lastrowid)
    add_zone_challenger(conn, zone_id, organization_id, strength=max(20, severity), severity=severity,
                         metadata={"cause": activity_kind}, event_logger=event_logger)
    zone_name = conn.execute("SELECT name FROM underworld_zones WHERE id=?", (zone_id,)).fetchone()
    zname = str(zone_name[0]) if zone_name else f"zone {zone_id}"
    cross_system_tags = ["encroachment", activity_kind]
    if enterprise_id is not None:
        cross_system_tags.append("enterprise_affected")
    _record_territorial_occurrence(
        conn, event_logger=event_logger, event_type="underworld_encroachment_attempted",
        title=f"Unauthorized {activity_kind} in {zname}", summary=f"An organization attempted unauthorized {activity_kind} in {zname} without permission.",
        severity_0_100=severity, zone_id=zone_id, source_organization_id=organization_id,
        target_organization_id=controller_organization_id, incident_id=incident_id, tags=cross_system_tags,
        metadata={"activity_kind": activity_kind, "enterprise_id": enterprise_id},
    )
    return {"authorized": False, "incident_id": incident_id}


def _refresh_territory_summary(conn: sqlite3.Connection, organization_id: int) -> None:
    rows = conn.execute(
        """SELECT z.population_scale,z.commercial_intensity,c.strength FROM underworld_zone_claims c
           JOIN underworld_zones z ON z.id=c.zone_id
           WHERE c.organization_id=? AND c.claim_kind='controller' AND c.status='active' AND z.status='active'""",
        (organization_id,),
    ).fetchall()
    if not rows:
        score = 0.0
    else:
        # Summary only: concrete zones own truth.
        raw = sum((float(r[0]) * .35 + float(r[1]) * .25 + float(r[2]) * .40) for r in rows)
        score = _clamp(12.0 * math.sqrt(len(rows)) + raw / max(1, len(rows)) * .55)
    conn.execute("UPDATE underworld_organizations SET territorial_presence=?,updated_day=? WHERE id=?", (score, _day(conn), organization_id))


_FIRST_NAMES = [
    "Alden","Bren","Caro","Darian","Elias","Garran","Hale","Iven","Joren","Kellan","Lucan","Marek","Nolan","Orin","Perrin","Rafe","Soren","Tomas","Varen","Willem",
]
_SURNAMES = [
    "Vale","Kerr","Marr","Rooke","Brann","Voss","Dane","Kestrel","Torve","Renn","Holt","Serrin","Marrow","Verran","Dorn","Pell","Reese","Ashe","Lowe","March",
]
_GANG_WORDS = ["Hounds","Crows","Hooks","Knives","Boars","Lanterns","Rooks","Hawks","Bells","Foxes","Hammers","Jacks"]
_GANG_PREFIX = ["Black","Red","Iron","Grey","Low","East","Ash","White","Old","River","South","North"]


def _unique_actor_name(conn: sqlite3.Connection, rng: random.Random, *, family_name: str | None = None) -> str:
    for i in range(200):
        first = rng.choice(_FIRST_NAMES)
        last = family_name or rng.choice(_SURNAMES)
        name = f"{first} {last}" if i < 50 else f"{first} {last} {i}"
        if not conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
            return name
    raise RuntimeError("could not generate unique actor name")


def _create_person(
    conn: sqlite3.Connection, name: str, location_id: int, *, subtype: str, age: int,
    open_core: bool, stage: str | None = None, notes: str = "Generated underworld actor",
) -> int:
    day = _day(conn)
    aid = int(conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'character',?,?,?,'active',?,0)",
        (name, subtype, location_id, location_id, notes),
    ).lastrowid)
    birth = day - int(age * 365.2425)
    life_stage = "elder" if age >= 60 else "adult"
    conn.execute(
        """INSERT INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json)
           VALUES (?,?,?,1,'living',?,?)""",
        (aid, birth, life_stage, day, _j({"generated_underworld": True, "source_age": age})),
    )
    core_state = "Open-Core" if open_core else "Closed-Core"
    conn.execute(
        """INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
               training_effort,resource_access,teacher_support,injury_constraint,realization_aptitude,vessel_aptitude,
               next_realization_check_day,last_review_day,next_review_day,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (aid, core_state, stage if open_core else None, 1 if open_core and stage else 0,
         34 if open_core else 0, 22 if open_core else 0, 54 if open_core else 0, 48, 0, 0, 1.0, 1.0,
         day + 365, day, day + 30, "active" if open_core and stage else "paused",
         _j({"generated_underworld": True, "not_canon": True})),
    )
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold)
           VALUES (?,'DORMANT',180,.35,.65,?,?,3)""",
        (aid, day, day + 180),
    )
    # Generated command figures need ordinary drives because autonomous criminal decisions use
    # the same ambition/risk/patience substrate as other NPCs. These are varied, not type-locked.
    rr = random.Random(aid * 104729 + day * 131)
    conn.execute(
        """INSERT OR IGNORE INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism)
           VALUES (?,?,?,?,?,?,?)""",
        (aid, rr.uniform(.30,.80), rr.uniform(.35,.82), rr.uniform(.30,.78), rr.uniform(.38,.88), rr.uniform(.45,.92), rr.uniform(.42,.90)),
    )
    ensure_health_profile(conn, aid, longevity_class=(stage or "ordinary").lower())
    upsert_continuity_core(
        conn, "actor", aid,
        {"generated_underworld": True, "core_state": core_state, "stage": stage, "role": subtype, "age": age, "age_known": True},
        source_kind="engine", notes="Procedurally crystallized underworld actor; not World Bible canon.",
    )
    set_resolution(conn, "actor", aid, "TRACKED", reason="Underworld command figure has causal authority", review_cadence_days=90, next_review_day=day + 90,
                   metadata={"generated_underworld": True})
    return aid


def _leader_open_core(rng: random.Random, command_bias: float, role_kind: str) -> bool:
    role_bonus = {"boss": 8, "underboss": 4, "lieutenant": 0, "crew_leader": -4}.get(role_kind, -12)
    p = _clamp(command_bias + role_bonus, 5, 98) / 100.0
    return rng.random() < p


def _leader_stage(rng: random.Random, role_kind: str) -> str | None:
    # Crownlands/Aldergate leaders are mostly First/Temper when Open-Core, with Third uncommon
    # and Breach exceptional. This is a leadership selection prior, not a city-wide cultivator census.
    x = rng.random()
    if role_kind == "boss":
        if x < .025: return "Breach"
        if x < .18: return "Third"
        if x < .62: return "Temper"
        return "First"
    if x < .06: return "Third"
    if x < .42: return "Temper"
    return "First"


def create_personnel(
    conn: sqlite3.Connection, organization_id: int, *, role_kind: str, crew_id: int | None = None,
    membership_status: str | None = None, actor_id: int | None = None, rng: random.Random | None = None,
    family_name: str | None = None,
) -> int:
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
    if not org:
        raise ValueError("unknown organization")
    culture = ensure_organization_culture(conn, organization_id)
    if rng is None:
        rng = random.Random(_seed(conn, organization_id * 811 + len(role_kind)))
    loc = int(org["primary_location_id"]) if org["primary_location_id"] is not None else None
    if loc is None:
        raise ValueError("organization needs a primary location to crystallize personnel")
    if actor_id is None:
        oc = _leader_open_core(rng, float(culture["open_core_command_bias"]), role_kind) if role_kind in {"boss","underboss","lieutenant","crew_leader","enforcer"} else rng.random() < .10
        stage = _leader_stage(rng, role_kind) if oc else None
        age_floor, age_ceil = ((32, 68) if role_kind == "boss" else (24, 58))
        age = rng.randint(age_floor, age_ceil)
        name = _unique_actor_name(conn, rng, family_name=family_name if str(org["organization_type"]) == "criminal_dynasty" else None)
        actor_id = _create_person(conn, name, loc, subtype=f"underworld_{role_kind}", age=age, open_core=oc, stage=stage)
    if membership_status is None:
        model = str(culture["membership_model"])
        membership_status = "sworn_member" if model == "sworn" else ("blood_family" if model == "blood_household" else "member")
    authority = {"boss": 100, "underboss": 82, "lieutenant": 68, "crew_leader": 62, "enforcer": 42, "accountant": 46, "fixer": 44, "collector": 28, "specialist": 34, "member": 18, "associate": 8}.get(role_kind, 20)
    conn.execute(
        """INSERT INTO underworld_personnel(actor_id,organization_id,crew_id,role_kind,membership_status,authority,earning_power,inducted_day,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?, 'active',?)
           ON CONFLICT(actor_id) DO UPDATE SET organization_id=excluded.organization_id,crew_id=excluded.crew_id,
             role_kind=excluded.role_kind,membership_status=excluded.membership_status,authority=excluded.authority,status='active'""",
        (actor_id, organization_id, crew_id, role_kind, membership_status, authority, max(10, authority * .65), _day(conn), _j({"generated_underworld": True})),
    )
    if role_kind == "boss":
        conn.execute("UPDATE underworld_organizations SET current_leader_actor_id=? WHERE id=?", (actor_id, organization_id))
        _ensure_leader_decision_cadence(conn,int(actor_id))
        conn.execute(
            "INSERT OR IGNORE INTO underworld_leader_wealth(actor_id,organization_id,last_review_day,metadata_json) VALUES (?,?,?,?)",
            (actor_id, organization_id, _day(conn), _j({"generated_underworld": True})),
        )
    return int(actor_id)


def create_crew(
    conn: sqlite3.Connection, organization_id: int, name: str, *, leader_actor_id: int | None = None,
    home_zone_id: int | None = None, purpose_kind: str = "general", size_estimate: float = 8,
    open_core_estimate: float | None = None, staged_estimate: float | None = None,
    cohesion: float = 60, loyalty: float = 60, rng: random.Random | None = None,
) -> int:
    if rng is None:
        rng = random.Random(_seed(conn, organization_id * 913 + len(name)))
    if open_core_estimate is None:
        open_core_estimate = max(0.0, float(size_estimate) * rng.uniform(.07, .16))
    if staged_estimate is None:
        staged_estimate = max(0.0, float(open_core_estimate) * rng.uniform(.45, .78))
    cur = conn.execute(
        """INSERT INTO underworld_crews(organization_id,name,leader_actor_id,home_zone_id,purpose_kind,size_estimate,open_core_estimate,staged_estimate,assigned_patrol_strength,cohesion,loyalty,status,created_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?)""",
        (organization_id, name, leader_actor_id, home_zone_id, purpose_kind, max(0, size_estimate), max(0, open_core_estimate), max(0, staged_estimate),
         min(max(0.0, size_estimate), max(0.0, size_estimate) * .35), _clamp(cohesion), _clamp(loyalty), _day(conn), _j({"generated_underworld": True})),
    )
    cid = int(cur.lastrowid)
    if leader_actor_id is None:
        leader_actor_id = create_personnel(conn, organization_id, role_kind="crew_leader", crew_id=cid, rng=rng)
        conn.execute("UPDATE underworld_crews SET leader_actor_id=? WHERE id=?", (leader_actor_id, cid))
    else:
        conn.execute("UPDATE underworld_personnel SET crew_id=? WHERE actor_id=?", (cid, leader_actor_id))
    return cid


def _insert_economic_interest(
    conn: sqlite3.Connection, *, interest_kind: str,
    holder_actor_id: int | None = None, holder_crew_id: int | None = None,
    holder_organization_id: int | None = None, holder_household_id: int | None = None,
    target_enterprise_id: int | None = None, target_racket_id: int | None = None,
    share_fraction: float | None = None, metadata: dict[str, Any] | None = None,
) -> int:
    holders=[holder_actor_id,holder_crew_id,holder_organization_id,holder_household_id]
    targets=[target_enterprise_id,target_racket_id]
    if sum(x is not None for x in holders)!=1 or sum(x is not None for x in targets)!=1:
        raise ValueError("economic interest needs exactly one holder and one target")
    if share_fraction is not None and not (0 <= float(share_fraction) <= 1):
        raise ValueError("share_fraction must be between 0 and 1")
    # Avoid decorative duplicate rows when creation/backfill paths are re-entered.
    clauses=["interest_kind=?","status='active'"]
    params:list[Any]=[interest_kind]
    for col,val in (
        ("holder_actor_id",holder_actor_id),("holder_crew_id",holder_crew_id),
        ("holder_organization_id",holder_organization_id),("holder_household_id",holder_household_id),
        ("target_enterprise_id",target_enterprise_id),("target_racket_id",target_racket_id),
    ):
        if val is None:
            clauses.append(f"{col} IS NULL")
        else:
            clauses.append(f"{col}=?"); params.append(int(val))
    existing=conn.execute("SELECT id FROM economic_interests WHERE "+" AND ".join(clauses)+" ORDER BY id LIMIT 1",tuple(params)).fetchone()
    if existing:
        return int(existing[0])
    return int(conn.execute(
        """INSERT INTO economic_interests(holder_actor_id,holder_crew_id,holder_organization_id,holder_household_id,
               target_enterprise_id,target_racket_id,interest_kind,share_fraction,started_day,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,'active',?)""",
        (holder_actor_id,holder_crew_id,holder_organization_id,holder_household_id,
         target_enterprise_id,target_racket_id,interest_kind,share_fraction,_day(conn),_j(metadata or {})),
    ).lastrowid)


def _record_economic_flow(
    conn: sqlite3.Connection, flow_kind: str, amount: float, *,
    source_actor_id: int | None = None, source_crew_id: int | None = None,
    source_organization_id: int | None = None, source_household_id: int | None = None,
    source_enterprise_id: int | None = None, source_racket_id: int | None = None,
    target_actor_id: int | None = None, target_crew_id: int | None = None,
    target_organization_id: int | None = None, target_household_id: int | None = None,
    target_enterprise_id: int | None = None, target_racket_id: int | None = None,
    racket_id: int | None = None, protection_account_id: int | None = None,
    cadence_kind: str = "one_off", rate: float | None = None,
    status: str = "realized", metadata: dict[str, Any] | None = None,
) -> int:
    sources=[source_actor_id,source_crew_id,source_organization_id,source_household_id,source_enterprise_id,source_racket_id]
    targets=[target_actor_id,target_crew_id,target_organization_id,target_household_id,target_enterprise_id,target_racket_id]
    if sum(x is not None for x in sources)!=1 or sum(x is not None for x in targets)!=1:
        raise ValueError("economic flow needs exactly one source and one target")
    if amount < 0:
        raise ValueError("economic flow amount must be nonnegative")
    return int(conn.execute(
        """INSERT INTO economic_flows(day,flow_kind,amount,
               source_actor_id,source_crew_id,source_organization_id,source_household_id,source_enterprise_id,source_racket_id,
               target_actor_id,target_crew_id,target_organization_id,target_household_id,target_enterprise_id,target_racket_id,
               racket_id,protection_account_id,cadence_kind,rate,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_day(conn),flow_kind,float(amount),source_actor_id,source_crew_id,source_organization_id,source_household_id,source_enterprise_id,source_racket_id,
         target_actor_id,target_crew_id,target_organization_id,target_household_id,target_enterprise_id,target_racket_id,
         racket_id,protection_account_id,cadence_kind,rate,status,_j(metadata or {})),
    ).lastrowid)


def _ensure_protection_racket(conn: sqlite3.Connection, organization_id: int, zone_id: int, *, operator_actor_id: int | None = None, operator_crew_id: int | None = None) -> int:
    row=conn.execute(
        """SELECT id FROM underworld_racket_sites
           WHERE organization_id=? AND zone_id=? AND racket_kind='protection collections' AND status='active'
           ORDER BY id LIMIT 1""", (organization_id,zone_id)
    ).fetchone()
    if row:
        return int(row[0])
    # Zero gross here is intentional: protection-account payments carry the operation's gross,
    # preventing the container racket from double-counting the same money in monthly income.
    return create_racket_site(conn, organization_id, "protection collections", zone_id=zone_id,
                              gross_income_per_30=0, labor_required=2,
                              operator_actor_id=operator_actor_id, operator_crew_id=operator_crew_id,
                              metadata={"econ01_protection_container":True})


def set_racket_status(conn: sqlite3.Connection, racket_id: int, status: str) -> bool:
    if status not in {"active","suppressed","seized","abandoned"}:
        raise ValueError("invalid racket status")
    row=conn.execute("SELECT * FROM underworld_racket_sites WHERE id=?",(racket_id,)).fetchone()
    if not row or str(row["status"])==status:
        return False
    conn.execute("UPDATE underworld_racket_sites SET status=? WHERE id=?",(status,racket_id))
    if status!="active":
        conn.execute("UPDATE underworld_protection_accounts SET status='ended' WHERE racket_id=? AND status='active'",(racket_id,))
        conn.execute("UPDATE economic_interests SET status='ended',ended_day=? WHERE target_racket_id=? AND status='active'",(_day(conn),racket_id))
    if row["organization_id"] is not None:
        _refresh_racket_summary(conn,int(row["organization_id"]))
    return True


def pay_bribe(conn: sqlite3.Connection, organization_id: int, target_actor_id: int, amount: float, *, metadata: dict[str, Any] | None = None) -> int:
    amount=max(0.0,float(amount))
    if amount<=0:
        raise ValueError("bribe amount must be positive")
    row=conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    if not row or float(row[0]) < amount:
        raise ValueError("organization treasury cannot fund bribe")
    if not conn.execute("SELECT 1 FROM actors WHERE id=?",(target_actor_id,)).fetchone():
        raise ValueError("unknown bribe recipient")
    conn.execute("UPDATE underworld_organizations SET treasury=treasury-?,updated_day=? WHERE id=?",(amount,_day(conn),organization_id))
    ensure_heat_profile(conn,organization_id)
    # Temporary projection: the concrete payment is authority; corruption_cover is only a derived
    # operational effect until a full corruption-relationship owner exists.
    conn.execute("UPDATE underworld_heat SET corruption_cover=MIN(100,corruption_cover+?) WHERE organization_id=?",(min(12.0,amount*.6),organization_id))
    _finance(conn,organization_id,"bribe",-amount,metadata={"target_actor_id":target_actor_id,**(metadata or {})})
    return _record_economic_flow(conn,"bribe",amount,source_organization_id=organization_id,target_actor_id=target_actor_id,
                                 metadata={"recipient_balance_unmodeled_until_personal_estates":True,**(metadata or {})})


def pay_member_household_support(conn: sqlite3.Connection, organization_id: int, member_actor_id: int, amount: float, *, metadata: dict[str, Any] | None = None) -> int:
    amount=max(0.0,float(amount))
    if amount<=0:
        raise ValueError("support amount must be positive")
    row=conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    if not row or float(row[0]) < amount:
        raise ValueError("organization treasury cannot fund support")
    hh=conn.execute("""SELECT hm.household_id FROM household_members hm
                       WHERE hm.actor_id=? AND hm.status='active' ORDER BY hm.authority DESC,hm.household_id LIMIT 1""",(member_actor_id,)).fetchone()
    if not hh:
        raise ValueError("member has no active household to support")
    hid=int(hh[0])
    conn.execute("UPDATE underworld_organizations SET treasury=treasury-?,updated_day=? WHERE id=?",(amount,_day(conn),organization_id))
    conn.execute("UPDATE households SET liquidity=liquidity+?,wealth=wealth+?,updated_day=? WHERE id=?",(amount,amount,_day(conn),hid))
    _finance(conn,organization_id,"household_support",-amount,metadata={"member_actor_id":member_actor_id,"household_id":hid,**(metadata or {})})
    return _record_economic_flow(conn,"support",amount,source_organization_id=organization_id,target_household_id=hid,
                                 metadata={"member_actor_id":member_actor_id,**(metadata or {})})


def protect_business(
    conn: sqlite3.Connection, organization_id: int, enterprise_id: int, zone_id: int, *, payment_per_30: float = 1,
    service_strength: float = 50, fear_component: float = 50, metadata: dict[str, Any] | None = None,
    event_logger: Callable[..., int] | None = None, racket_id: int | None = None,
    operator_actor_id: int | None = None, operator_crew_id: int | None = None,
) -> dict[str, Any]:
    auth = attempt_local_activity(conn, zone_id, organization_id, "protection", severity=36, enterprise_id=enterprise_id, event_logger=event_logger)
    if racket_id is not None:
        rr=conn.execute("SELECT * FROM underworld_racket_sites WHERE id=?",(racket_id,)).fetchone()
        if not rr or str(rr["status"])!="active" or str(rr["racket_kind"])!="protection collections" \
           or rr["organization_id"] is None or int(rr["organization_id"])!=int(organization_id) \
           or rr["zone_id"] is None or int(rr["zone_id"])!=int(zone_id):
            raise ValueError("racket_id must name an active protection racket for this organization and zone")
    existing = conn.execute("SELECT * FROM underworld_protection_accounts WHERE enterprise_id=? AND status='active'", (enterprise_id,)).fetchone()
    if existing and int(existing["protector_organization_id"]) != int(organization_id):
        conn.execute("UPDATE underworld_protection_accounts SET disputed=1 WHERE id=?", (int(existing["id"]),))
        poach_incident_id = int(conn.execute(
            """INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
               VALUES (?,?,?,?, 'protection_poach',45,'open',?)""",
            (_day(conn), zone_id, organization_id, int(existing["protector_organization_id"]), _j({"enterprise_id": enterprise_id})),
        ).lastrowid)
        _record_territorial_occurrence(
            conn, event_logger=event_logger, event_type="underworld_protection_poach_attempted",
            title="Protection poach attempted", summary="A rival organization attempted to poach an existing protection client.",
            severity_0_100=45, zone_id=zone_id, source_organization_id=organization_id,
            target_organization_id=int(existing["protector_organization_id"]), incident_id=poach_incident_id,
            tags=["protection", "poach", "enterprise_affected"], metadata={"enterprise_id": enterprise_id, "account_id": int(existing["id"]), "racket_id": existing["racket_id"]},
        )
        return {"created": False, "disputed": True, "authorized": auth["authorized"], "account_id": int(existing["id"]), "racket_id": existing["racket_id"]}
    if not auth["authorized"]:
        return {"created": False, "disputed": True, "authorized": False, "account_id": None, "racket_id": None}
    if existing:
        rid=int(existing["racket_id"]) if existing["racket_id"] is not None else (racket_id or _ensure_protection_racket(conn,organization_id,zone_id,operator_actor_id=operator_actor_id,operator_crew_id=operator_crew_id))
        if existing["racket_id"] is None:
            conn.execute("UPDATE underworld_protection_accounts SET racket_id=? WHERE id=?",(rid,int(existing["id"])))
        return {"created": False, "disputed": bool(existing["disputed"]), "authorized": True, "account_id": int(existing["id"]), "racket_id": rid}
    rid=racket_id or _ensure_protection_racket(conn,organization_id,zone_id,operator_actor_id=operator_actor_id,operator_crew_id=operator_crew_id)
    aid = int(conn.execute(
        """INSERT INTO underworld_protection_accounts(protector_organization_id,enterprise_id,zone_id,payment_per_30,service_strength,fear_component,disputed,started_day,status,metadata_json,racket_id)
           VALUES (?,?,?,?,?,?,0,?,'active',?,?)""",
        (organization_id, enterprise_id, zone_id, max(0.0, payment_per_30), _clamp(service_strength), _clamp(fear_component), _day(conn), _j(metadata or {}), rid),
    ).lastrowid)
    conn.execute(
        """INSERT OR IGNORE INTO underworld_business_links(organization_id,enterprise_id,zone_id,link_kind,ownership_share,started_day,status,metadata_json)
           VALUES (?,?,?,'protected_client',0,?,'active',?)""",
        (organization_id, enterprise_id, zone_id, _day(conn), _j(metadata or {})),
    )
    return {"created": True, "disputed": False, "authorized": True, "account_id": aid, "racket_id": rid}


def create_racket_site(
    conn: sqlite3.Connection, organization_id: int | None, racket_kind: str, *, zone_id: int | None = None,
    enterprise_id: int | None = None, gross_income_per_30: float = 3, labor_required: float = 3,
    violence_requirement: float | None = None, secrecy: float | None = None,
    operator_actor_id: int | None = None, operator_crew_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    profile = RACKET_PROFILES.get(racket_kind)
    if zone_id is not None:
        if organization_id is None:
            # ECON-01 deliberately does not invent a person-level territorial-permission system.
            # Independent rackets are representable now; local operation inside settled turf will
            # gain person/crew permissions in the later permission/decision work.
            raise ValueError("zone-bound independent racket requires a future person/crew permission owner")
        activity = profile["activity"] if profile else "collections"
        auth = attempt_local_activity(conn, zone_id, organization_id, activity, severity=30, enterprise_id=enterprise_id)
        if not auth["authorized"]:
            raise PermissionError("territorial controller has not authorized this recurring local racket")
    if operator_actor_id is not None and operator_crew_id is not None:
        raise ValueError("racket may have one default operator in this bounded slice")
    if operator_crew_id is not None:
        crew=conn.execute("SELECT organization_id FROM underworld_crews WHERE id=? AND status='active'",(operator_crew_id,)).fetchone()
        if not crew:
            raise ValueError("unknown/inactive operator crew")
        if organization_id is None:
            organization_id=int(crew[0])
        elif int(crew[0])!=int(organization_id):
            raise ValueError("operator crew does not belong to affiliated organization")
    profile = RACKET_PROFILES.get(racket_kind)
    income_mult = profile["income_mult"] if profile else 1.0
    if violence_requirement is None:
        violence_requirement = profile["violence_base"] if profile else 25
    if secrecy is None:
        secrecy = profile["secrecy_base"] if profile else 50
    rid = int(conn.execute(
        """INSERT INTO underworld_racket_sites(organization_id,zone_id,enterprise_id,racket_kind,gross_income_per_30,labor_required,violence_requirement,secrecy,status,created_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,'active',?,?)""",
        (organization_id, zone_id, enterprise_id, racket_kind, max(0, gross_income_per_30 * income_mult), max(0, labor_required), _clamp(violence_requirement), _clamp(secrecy), _day(conn), _j(metadata or {})),
    ).lastrowid)
    # organization_id is affiliation/umbrella authority, not ownership. The default beneficial
    # controller follows the concrete operator. Only an organization-operated racket is therefore
    # organization-controlled by default; a soldier/crew-operated racket may still owe kick-up
    # without the family literally owning it.
    if operator_actor_id is not None:
        _insert_economic_interest(conn,interest_kind="operator",holder_actor_id=operator_actor_id,target_racket_id=rid,metadata={"source":"create_racket_site"})
        _insert_economic_interest(conn,interest_kind="beneficial_controller",holder_actor_id=operator_actor_id,target_racket_id=rid,metadata={"source":"create_racket_site","default_from_operator":True})
    elif operator_crew_id is not None:
        _insert_economic_interest(conn,interest_kind="operator",holder_crew_id=operator_crew_id,target_racket_id=rid,metadata={"source":"create_racket_site"})
        _insert_economic_interest(conn,interest_kind="beneficial_controller",holder_crew_id=operator_crew_id,target_racket_id=rid,metadata={"source":"create_racket_site","default_from_operator":True})
    elif organization_id is not None:
        _insert_economic_interest(conn,interest_kind="operator",holder_organization_id=organization_id,target_racket_id=rid,metadata={"source":"create_racket_site","default_operator":True})
        _insert_economic_interest(conn,interest_kind="beneficial_controller",holder_organization_id=organization_id,target_racket_id=rid,metadata={"source":"create_racket_site","default_from_operator":True})
    if organization_id is not None:
        _refresh_racket_summary(conn, organization_id)
    return rid


def _refresh_racket_summary(conn: sqlite3.Connection, organization_id: int) -> None:
    rows = conn.execute("SELECT gross_income_per_30,labor_required,violence_requirement FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (organization_id,)).fetchall()
    score = 0.0 if not rows else _clamp(8 * math.sqrt(len(rows)) + sum(float(r[0]) * 1.8 + float(r[1]) * .5 + float(r[2]) * .08 for r in rows))
    conn.execute("UPDATE underworld_organizations SET racket_breadth=?,updated_day=? WHERE id=?", (score, _day(conn), organization_id))


def _refresh_front_summary(conn: sqlite3.Connection, organization_id: int) -> None:
    cnt = int(conn.execute("SELECT COUNT(*) FROM underworld_business_links WHERE organization_id=? AND link_kind IN ('owned_front','controlled_front') AND status='active'", (organization_id,)).fetchone()[0])
    conn.execute("UPDATE underworld_organizations SET front_depth=?,updated_day=? WHERE id=?", (_clamp(10 * math.sqrt(cnt) + cnt * 3), _day(conn), organization_id))


def attach_front_use(
    conn: sqlite3.Connection, organization_id: int, enterprise_id: int, *, zone_id: int | None,
    ownership_share: float = 0.0, organization_legal_owner: bool = False,
    legal_owner_actor_id: int | None = None, operator_actor_id: int | None = None,
    operator_crew_id: int | None = None, metadata: dict[str, Any] | None = None,
) -> int:
    """Mark an existing ordinary enterprise as a criminally used/controlled front.

    Front is a use/relationship, not an asset class. Legal ownership may remain entirely outside
    the organization while beneficial control and criminal operation are persisted separately.
    """
    org=conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    ent=conn.execute("SELECT * FROM civilian_enterprises WHERE id=?",(enterprise_id,)).fetchone()
    if not org or not ent:
        raise ValueError("unknown organization/enterprise")
    if legal_owner_actor_id is not None and organization_legal_owner:
        raise ValueError("choose actor or organization legal ownership")
    if operator_actor_id is not None and operator_crew_id is not None:
        raise ValueError("front may have one default operator in this bounded slice")
    if legal_owner_actor_id is not None:
        _insert_economic_interest(conn,interest_kind="legal_owner",holder_actor_id=legal_owner_actor_id,target_enterprise_id=enterprise_id,share_fraction=1.0,metadata={"source":"attach_front_use"})
    if organization_legal_owner:
        _insert_economic_interest(conn,interest_kind="legal_owner",holder_organization_id=organization_id,target_enterprise_id=enterprise_id,share_fraction=max(0.0,min(1.0,ownership_share or 1.0)),metadata={"source":"attach_front_use"})
    _insert_economic_interest(conn,interest_kind="beneficial_controller",holder_organization_id=organization_id,target_enterprise_id=enterprise_id,metadata={"source":"attach_front_use","front_use":True})
    if operator_actor_id is not None:
        _insert_economic_interest(conn,interest_kind="operator",holder_actor_id=operator_actor_id,target_enterprise_id=enterprise_id,metadata={"source":"attach_front_use"})
    elif operator_crew_id is not None:
        _insert_economic_interest(conn,interest_kind="operator",holder_crew_id=operator_crew_id,target_enterprise_id=enterprise_id,metadata={"source":"attach_front_use"})
    else:
        _insert_economic_interest(conn,interest_kind="operator",holder_organization_id=organization_id,target_enterprise_id=enterprise_id,metadata={"source":"attach_front_use","default_operator":True})
    link_kind="owned_front" if organization_legal_owner else "controlled_front"
    cur=conn.execute("""INSERT INTO underworld_business_links(organization_id,enterprise_id,zone_id,link_kind,ownership_share,started_day,status,metadata_json)
                        VALUES (?,?,?,?,?,?,'active',?)""",
                     (organization_id,enterprise_id,zone_id,link_kind,max(0.0,min(1.0,ownership_share if organization_legal_owner else 0.0)),_day(conn),_j(metadata or {})))
    _refresh_front_summary(conn,organization_id)
    return int(cur.lastrowid)


def create_front(
    conn: sqlite3.Connection, organization_id: int, name: str, enterprise_kind: str, *, zone_id: int | None,
    archetype: str = "general_store", capital: float = 20, cash: float = 8, ownership_share: float = 1.0,
    legal_owner_actor_id: int | None = None, organization_legal_owner: bool = True,
    operator_actor_id: int | None = None, operator_crew_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Attach criminal front-use to an ordinary enterprise without equating 'front' with boss ownership.

    The autonomous purchase path defaults to institution/organization legal ownership because the
    organization paid for the business. Callers can instead supply a legal actor owner and set
    organization_legal_owner=False; the organization then holds beneficial control/use only.
    """
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
    if not org:
        raise ValueError("unknown organization")
    if legal_owner_actor_id is not None and organization_legal_owner:
        raise ValueError("choose either an actor legal owner or organization legal ownership")
    if operator_actor_id is not None and operator_crew_id is not None:
        raise ValueError("front may have one default operator in this bounded slice")
    loc = int(org["primary_location_id"]) if org["primary_location_id"] is not None else None
    institution_actor_id=int(org["institution_actor_id"]) if organization_legal_owner and org["institution_actor_id"] is not None else None
    eid = create_enterprise(conn, name, enterprise_kind, owner_actor_id=legal_owner_actor_id, institution_actor_id=institution_actor_id,
                            location_id=loc, capital=capital, cash=cash,
                            reputation=45, admin_quality=50, labor_capacity=45, risk_tolerance=65,
                            metadata={"underworld_front": True, "generated_underworld": True, **(metadata or {})})
    try:
        configure_enterprise_business(conn, eid, archetype, quality=48, capacity=48, clientele_fit=48, service_reliability=48, regulatory_pressure=25,
                                      metadata={"underworld_front": True, "generated_underworld": True})
    except Exception:
        pass
    attach_front_use(conn,organization_id,eid,zone_id=zone_id,ownership_share=ownership_share,
                     organization_legal_owner=organization_legal_owner,legal_owner_actor_id=legal_owner_actor_id,
                     operator_actor_id=operator_actor_id,operator_crew_id=operator_crew_id,metadata=metadata)
    return eid


def seize_front(conn: sqlite3.Connection, business_link_id: int, *, reason: str = "enforcement", event_logger: Callable[..., int] | None = None) -> bool:
    """A gang's front was not invincible in the data model (underworld_business_links
    already allows a 'seized' status); nothing ever used it. This is that mechanic: the
    cover business is shut down along with the criminal link, mirroring a racket raid.
    """
    link = conn.execute("SELECT * FROM underworld_business_links WHERE id=? AND status='active'", (business_link_id,)).fetchone()
    if not link:
        return False
    conn.execute("UPDATE underworld_business_links SET status='seized' WHERE id=?", (business_link_id,))
    legal_org = conn.execute("""SELECT 1 FROM economic_interests WHERE holder_organization_id=? AND target_enterprise_id=?
                              AND interest_kind='legal_owner' AND status='active' LIMIT 1""",
                             (int(link["organization_id"]),int(link["enterprise_id"]))).fetchone()
    enterprise_closed = bool(legal_org) or str(link["link_kind"]) == 'owned_front'
    if enterprise_closed:
        conn.execute("UPDATE civilian_enterprises SET status='closed' WHERE id=?", (int(link["enterprise_id"]),))
    conn.execute("UPDATE economic_interests SET status='ended',ended_day=? WHERE target_enterprise_id=? AND holder_organization_id=? AND interest_kind IN ('beneficial_controller','operator') AND status='active'",
                 (_day(conn),int(link["enterprise_id"]),int(link["organization_id"])))
    _refresh_front_summary(conn, int(link["organization_id"]))
    zname = None
    if link["zone_id"] is not None:
        row = conn.execute("SELECT name FROM underworld_zones WHERE id=?", (int(link["zone_id"]),)).fetchone()
        zname = str(row[0]) if row else None
    _record_territorial_occurrence(
        conn, event_logger=event_logger, event_type="underworld_front_seized",
        title=f"Front seized{f': {zname}' if zname else ''}", summary=f"A criminal front business was seized ({reason}).",
        severity_0_100=45, zone_id=int(link["zone_id"]) if link["zone_id"] is not None else None,
        source_organization_id=int(link["organization_id"]), tags=["enterprise_affected", "asset_seizure"],
        metadata={"business_link_id": business_link_id, "enterprise_id": int(link["enterprise_id"]), "reason": reason, "enterprise_closed": enterprise_closed},
    )
    return True


def _organization_name(conn: sqlite3.Connection, rng: random.Random, form: str, family_name: str | None = None) -> tuple[str, str | None]:
    if form in {"mafia_family", "criminal_dynasty"}:
        last = family_name or rng.choice(_SURNAMES)
        base = f"{last} Family" if form == "mafia_family" else f"{last} House"
        name = base
        n = 2
        while conn.execute("SELECT 1 FROM underworld_organizations WHERE name=?", (name,)).fetchone():
            name = f"{base} {n}"; n += 1
        return name, last
    if form == "gang":
        base = f"{rng.choice(_GANG_PREFIX)} {rng.choice(_GANG_WORDS)}"
    elif form == "syndicate":
        base = f"{rng.choice(_SURNAMES)} Exchange"
    elif form == "network":
        base = f"{rng.choice(_GANG_PREFIX)} Thread"
    else:
        base = f"{rng.choice(_SURNAMES)} Company"
    name = base; n = 2
    while conn.execute("SELECT 1 FROM underworld_organizations WHERE name=?", (name,)).fetchone():
        name = f"{base} {n}"; n += 1
    return name, None


def _city_form_mix(rng: random.Random, territorial_count: int, institutional_depth: float, commercial_depth: float) -> list[str]:
    forms = ["gang"] * territorial_count
    # Additional institutional forms are possible at city start but not mandatory. Their
    # appearance follows local historical/commercial depth rather than a power ladder.
    if rng.random() < (.10 + .0055 * institutional_depth):
        forms.append("mafia_family")
    if rng.random() < (.12 + .0045 * institutional_depth):
        forms.append("criminal_dynasty")
    if rng.random() < (.18 + .0050 * commercial_depth):
        forms.append("syndicate")
    if rng.random() < .55:
        forms.append("network")
    if rng.random() < (.18 + .0035 * commercial_depth):
        forms.append("criminal_enterprise")
    return forms


def _zone_templates() -> list[tuple[str, str, str, float, float, float]]:
    return [
        ("exchange", "Exchange Ward", "commercial", 76, 92, 78),
        ("warehouse_east", "East Warehouse Ward", "warehouse", 62, 88, 60),
        ("warehouse_west", "West Warehouse Ward", "warehouse", 58, 84, 58),
        ("caravan_north", "North Caravan Ward", "caravan", 70, 82, 72),
        ("caravan_south", "South Caravan Ward", "caravan", 72, 80, 74),
        ("market", "Market Ward", "market", 84, 86, 86),
        ("craft", "Craft Ward", "mixed", 82, 64, 75),
        ("old_quarter", "Old Quarter", "residential", 86, 52, 70),
        ("river_gate", "River Gate Ward", "transit", 66, 75, 68),
        ("east_road", "East Road Ward", "transit", 72, 70, 65),
        ("south_yards", "South Yards", "labor", 80, 62, 58),
        ("north_residential", "North Residential Ward", "residential", 88, 46, 72),
    ]


def ensure_zone_anchor_locations(conn: sqlite3.Connection, city_location_id: int) -> dict[str, int]:
    """Backfill district-scale locations rows for zones that lack one, Phase 2A section 3.5.

    Additive and idempotent: already-anchored zones are left untouched, and re-running
    creates nothing new for them. This does not assert World Bible canon. It gives each
    zone a queryable place a future merchant/law/household system can resolve to, marked
    exactly as non-canon as seed_city_underworld already marks its zones
    ("not_world_bible_canon"). Grounding real named Aldergate districts in canon prose,
    if that is ever wanted, updates these rows later without changing what
    anchor_location_id means to callers.
    """
    city = conn.execute("SELECT name FROM locations WHERE id=?", (city_location_id,)).fetchone()
    city_name = str(city[0]) if city else f"location {city_location_id}"
    linked: dict[str, int] = {}
    zones = conn.execute(
        """SELECT id, zone_key, name FROM underworld_zones
           WHERE city_location_id=? AND status='active' AND anchor_location_id IS NULL ORDER BY id""",
        (city_location_id,),
    ).fetchall()
    for z in zones:
        zid, zkey, zname = int(z["id"]), str(z["zone_key"]), str(z["name"])
        loc_name = f"{city_name}: {zname}"
        existing = conn.execute("SELECT id FROM locations WHERE name=?", (loc_name,)).fetchone()
        if existing:
            lid = int(existing[0])
        else:
            lid = int(conn.execute(
                """INSERT INTO locations(name,kind,parent_location_id,notes,is_canon,identity_certainty,placement_certainty,coordinate_status,source_anchor)
                   VALUES (?,?,?,?,0,?,?,?,?)""",
                (loc_name, "district", city_location_id, f"Working district-scale anchor for underworld zone '{zname}'.",
                 "UNSPECIFIED", "UNSPECIFIED", "OPEN_NOT_REQUIRED", "v0.60 Phase 2A procedural zone anchor; not_world_bible_canon"),
            ).lastrowid)
        conn.execute("UPDATE underworld_zones SET anchor_location_id=? WHERE id=?", (lid, zid))
        linked[zkey] = lid
    return linked


# World Bible cross-check (plan section 6.8), Aldergate only. The Bible's Aldergate entry
# names an "Exchange Quarter, warehouses, caravan wards and finance houses" as the city's
# defining commercial features; it does not name specific wards, fix their count, or set
# their adjacency. So these five of the twelve procedural zones have their THEME grounded
# in canon (this dict is the citation); the zone count, exact boundaries, adjacency graph
# and the other seven zones remain working/generated, unchanged. This does not touch
# _zone_templates() or reseed anything: it only annotates zones already created by
# seed_city_underworld with an honest distinction between "canon-themed" and "procedural."
ALDERGATE_WORLD_BIBLE_ZONE_THEMES: dict[str, str] = {
    "exchange": "World Bible, Aldergate: the city is described as having an 'Exchange Quarter' among its defining commercial features. Ward boundaries/count are not specified in canon and remain procedural.",
    "warehouse_east": "World Bible, Aldergate: 'warehouses' are named among the city's defining commercial features; canon does not fix how many warehouse wards exist or their boundaries.",
    "warehouse_west": "World Bible, Aldergate: 'warehouses' are named among the city's defining commercial features; canon does not fix how many warehouse wards exist or their boundaries.",
    "caravan_north": "World Bible, Aldergate: 'caravan wards' are named among the city's defining commercial features; canon does not fix how many caravan wards exist or their boundaries.",
    "caravan_south": "World Bible, Aldergate: 'caravan wards' are named among the city's defining commercial features; canon does not fix how many caravan wards exist or their boundaries.",
}


def apply_world_bible_zone_theme_citations(conn: sqlite3.Connection, city_location_id: int) -> list[str]:
    """Annotate zones whose broad theme (not boundary, count, or name) is canon-grounded.

    Safe no-op for any city whose zone_keys don't appear in ALDERGATE_WORLD_BIBLE_ZONE_THEMES.
    Marks metadata_json with world_bible_theme_citation and world_bible_theme_grounded=True
    without changing not_world_bible_canon, is_canon, or anything about zone identity/count/
    adjacency, since only the theme is confirmed, not the specific zone as a fixed place.
    """
    touched: list[str] = []
    zones = conn.execute(
        "SELECT id, zone_key, metadata_json FROM underworld_zones WHERE city_location_id=? AND status='active'",
        (city_location_id,),
    ).fetchall()
    for z in zones:
        bare_key = str(z["zone_key"]).split(":", 1)[-1]
        citation = ALDERGATE_WORLD_BIBLE_ZONE_THEMES.get(bare_key)
        if not citation:
            continue
        meta = _loads(z["metadata_json"])
        if meta.get("world_bible_theme_citation") == citation:
            continue
        meta["world_bible_theme_grounded"] = True
        meta["world_bible_theme_citation"] = citation
        conn.execute("UPDATE underworld_zones SET metadata_json=? WHERE id=?", (_j(meta), int(z["id"])))
        touched.append(bare_key)
    return touched


def seed_city_underworld(
    conn: sqlite3.Connection, *, city_location_id: int | None = None, city_name: str | None = None,
    force: bool = False, salt: int = 6000,
) -> dict[str, Any]:
    if city_location_id is None:
        if not city_name:
            raise ValueError("city_location_id or city_name required")
        row = conn.execute("SELECT id FROM locations WHERE name=?", (city_name,)).fetchone()
        if not row:
            raise ValueError(f"unknown city: {city_name}")
        city_location_id = int(row[0])
    loc = conn.execute("SELECT * FROM locations WHERE id=?", (city_location_id,)).fetchone()
    if not loc:
        raise ValueError("unknown city location")
    if not force:
        existing = int(conn.execute("SELECT COUNT(*) FROM underworld_zones WHERE city_location_id=? AND status='active'", (city_location_id,)).fetchone()[0])
        if existing:
            return city_underworld_snapshot(conn, city_location_id)
    rng = random.Random(_seed(conn, salt + city_location_id * 97))
    ctx = commercial_context(conn, city_location_id)
    trade = float(ctx.get("trade_flow", ctx.get("merchant_traffic", 58)))
    travelers = float(ctx.get("traveler_flow", 52))
    credit = float(ctx.get("credit_demand", 52))
    regulation = float(ctx.get("regulation", ctx.get("regulatory_pressure", 48)))
    institutional_depth = _clamp((trade + credit + regulation) / 3)
    commercial_depth = _clamp((trade * .55 + travelers * .25 + credit * .20))

    zones: list[int] = []
    for key, name, kind, pop, comm, vis in _zone_templates():
        policing = _clamp(regulation + rng.uniform(-12, 12))
        zones.append(create_zone(conn, city_location_id, key, name, zone_kind=kind, population_scale=pop, commercial_intensity=comm,
                                 street_visibility=vis, policing_pressure=policing,
                                 metadata={"procedural_city_ecology": True, "not_world_bible_canon": True}))
    # Ring plus cross-links yields borders without pretending a precise street map is canon.
    for i, zid in enumerate(zones):
        set_zone_adjacency(conn, zid, zones[(i + 1) % len(zones)], permeability=rng.uniform(45, 80))
    for a, b in ((0,5),(1,8),(2,10),(3,9),(4,10),(6,11)):
        set_zone_adjacency(conn, zones[a], zones[b], permeability=rng.uniform(35, 72))

    territorial_count = rng.randint(7, 10)
    forms = _city_form_mix(rng, territorial_count, institutional_depth, commercial_depth)
    orgs: list[int] = []
    gang_orgs: list[int] = []
    zone_cursor = list(zones)
    rng.shuffle(zone_cursor)
    for idx, form in enumerate(forms):
        name, family_name = _organization_name(conn, rng, form)
        territorial = form == "gang" or (form in {"mafia_family", "criminal_dynasty"} and rng.random() < .65)
        full = rng.randint(34, 82) if form == "gang" else rng.randint(24, 70)
        if form in {"syndicate","network","criminal_enterprise"}:
            full = rng.randint(10, 42)
        command_depth = 2 if full >= 42 else 1
        org_id = create_underworld_organization(
            conn, f"v060:{city_location_id}:{idx}:{name.lower().replace(' ','-')}", form, name=name,
            primary_location_id=city_location_id, member_count_estimate=full, command_depth=command_depth,
            territorial_presence=0, racket_breadth=0, front_depth=0, violence_capacity=rng.uniform(25, 62),
            cohesion=rng.uniform(48, 78), membership_stability=rng.uniform(42, 72), succession_depth=rng.uniform(8, 34),
            metadata={"generated_underworld": True, "not_world_bible_canon": True, "v060_clean_rebuild": True},
        )
        ensure_organization_culture(conn, org_id, rng=rng)
        ensure_heat_profile(conn, org_id)
        # Opening manpower is mostly Closed-Core. The exact Open-Core stock is an estimate; named
        # leadership is crystallized separately and heavily selected from that scarce minority.
        open_share = rng.uniform(.075, .155) if form in {"gang","mafia_family","criminal_dynasty"} else rng.uniform(.055, .135)
        open_est = max(1, round(full * open_share))
        staged_est = max(0, round(open_est * rng.uniform(.45, .75)))
        core = max(4, round(full * rng.uniform(.18, .34)))
        ensure_underworld_membership_profile(conn, org_id, core_members=core, active_members=full-core,
                                             peripheral_associates=round(full * rng.uniform(.18, .48)),
                                             metadata={"opening_open_core_estimate": open_est, "opening_staged_estimate": staged_est, "v060": True})
        boss = create_personnel(conn, org_id, role_kind="boss", rng=rng, family_name=family_name)
        conn.execute("UPDATE underworld_organizations SET founder_actor_id=?,current_leader_actor_id=? WHERE id=?", (boss, boss, org_id))
        crew_count = max(1, min(5, math.ceil(full / rng.uniform(18, 28)))) if territorial else max(1, min(3, math.ceil(full / 22)))
        remaining = float(full)
        for c in range(crew_count):
            size = remaining / (crew_count-c) if c == crew_count-1 else max(5, round(full / crew_count * rng.uniform(.78, 1.18)))
            size = min(remaining, size); remaining -= size
            home = zone_cursor[(idx + c) % len(zone_cursor)] if territorial else None
            create_crew(conn, org_id, f"{name.split()[0]} Crew {c+1}", home_zone_id=home,
                        purpose_kind=rng.choice(["general","collections","enforcement","gambling","freight"]), size_estimate=size,
                        open_core_estimate=max(0, open_est / crew_count), staged_estimate=max(0, staged_est / crew_count), rng=rng)
        if territorial and zone_cursor:
            zid = zone_cursor.pop(0)
            set_zone_controller(conn, zid, org_id, strength=rng.uniform(48, 72), local_support=rng.uniform(32, 66), fear=rng.uniform(42, 76),
                                metadata={"opening_control": True})
        # Concrete opening criminal economy.
        racket_count = rng.randint(1, 4) if form in {"gang","mafia_family","criminal_dynasty"} else rng.randint(1, 3)
        controlled = conn.execute("SELECT zone_id FROM underworld_zone_claims WHERE organization_id=? AND claim_kind='controller' AND status='active' ORDER BY id", (org_id,)).fetchall()
        home_zone = int(controlled[0][0]) if controlled else None
        for _ in range(racket_count):
            rk = racket_kind_options(conn, home_zone if territorial else None, rng, count=1)[0]
            # non-territorial forms can operate without claiming a local protection monopoly.
            try:
                create_racket_site(conn, org_id, rk, zone_id=home_zone if territorial else None,
                                   gross_income_per_30=rng.uniform(2.5, 8.5), labor_required=rng.uniform(2, 7),
                                   metadata={"opening_racket": True})
            except PermissionError:
                pass
        if rng.random() < (.48 if form in {"gang","mafia_family","criminal_dynasty"} else .32):
            create_front(conn, org_id, f"{name.split()[0]} Yard {idx+1}", "service", zone_id=home_zone,
                         archetype="general_store", capital=rng.uniform(12, 34), cash=rng.uniform(5, 16),
                         metadata={"opening_front": True})
        orgs.append(org_id)
        if form == "gang":
            gang_orgs.append(org_id)

    # Assign any still-vacant zones to the territorial gangs rather than inventing a city where
    # most criminal ground has no local power at opening. Some zones can remain genuinely open.
    vacant = [z for z in zones if zone_controller(conn, z) is None]
    rng.shuffle(vacant)
    for zid in vacant[: max(0, len(vacant) - rng.randint(1, 3))]:
        if not gang_orgs:
            break
        controller = rng.choice(gang_orgs)
        set_zone_controller(conn, zid, controller, strength=rng.uniform(40, 62), local_support=rng.uniform(30, 58), fear=rng.uniform(38, 66),
                            metadata={"opening_secondary_control": True})

    # Concrete control must have concrete people assigned to it. Split existing crews where
    # necessary; any territory that remains understaffed is visible as a vulnerability rather
    # than being supported by phantom manpower.
    for oid in orgs:
        ensure_zone_staffing(conn,oid,rng=rng)
    # Seed relations from actual adjacency of controlled territory.
    _ensure_relations_from_borders(conn, city_location_id, rng)
    _seed_opening_clients(conn, city_location_id, rng)
    return city_underworld_snapshot(conn, city_location_id)


def _ensure_relations_from_borders(conn: sqlite3.Connection, city_location_id: int, rng: random.Random) -> None:
    pairs = conn.execute(
        """SELECT DISTINCT MIN(ca.organization_id,cb.organization_id) a, MAX(ca.organization_id,cb.organization_id) b
           FROM underworld_zone_adjacency za
           JOIN underworld_zone_claims ca ON ca.zone_id=za.zone_a_id AND ca.claim_kind='controller' AND ca.status='active'
           JOIN underworld_zone_claims cb ON cb.zone_id=za.zone_b_id AND cb.claim_kind='controller' AND cb.status='active'
           JOIN underworld_zones z ON z.id=za.zone_a_id
           WHERE z.city_location_id=? AND ca.organization_id<>cb.organization_id""",
        (city_location_id,),
    ).fetchall()
    day = _day(conn)
    for a,b in pairs:
        hostility = rng.uniform(28, 64)
        kind = "rival" if hostility >= 40 else "neutral"
        conn.execute(
            """INSERT OR IGNORE INTO underworld_relations(organization_a_id,organization_b_id,relation_kind,hostility,respect,tribute_rate,started_day,last_changed_day,metadata_json)
               VALUES (?,?,?,?,?,0,?,?,?)""",
            (int(a), int(b), kind, hostility, rng.uniform(12,48), day, day, _j({"shared_border": True})),
        )


def _seed_opening_clients(conn: sqlite3.Connection, city_location_id: int, rng: random.Random) -> None:
    # Prefer existing ordinary businesses; create a small procedural substrate only when the city
    # has too few concrete enterprises to support protection/racket play.
    existing = conn.execute("SELECT id,name FROM civilian_enterprises WHERE location_id=? AND status IN ('active','strained') ORDER BY id", (city_location_id,)).fetchall()
    needed = max(0, 28 - len(existing))
    kinds = [("service","tavern"),("shop","restaurant"),("service","inn"),("shop","general_store"),("service","warehouse"),("service","general_store")]
    for i in range(needed):
        ek, arche = rng.choice(kinds)
        eid = create_enterprise(conn, f"City Business {city_location_id}-{i+1}", ek, location_id=city_location_id,
                                capital=rng.uniform(5,18), cash=rng.uniform(2,8), reputation=rng.uniform(35,65),
                                admin_quality=rng.uniform(35,62), labor_capacity=rng.uniform(25,58), risk_tolerance=rng.uniform(28,65),
                                metadata={"procedural_city_business": True, "not_world_bible_canon": True})
        try:
            configure_enterprise_business(conn, eid, arche, quality=rng.uniform(38,60), capacity=rng.uniform(30,62), clientele_fit=rng.uniform(38,65), service_reliability=rng.uniform(38,62), regulatory_pressure=rng.uniform(25,58), metadata={"procedural_city_business": True})
        except Exception:
            pass
    businesses = conn.execute("SELECT id FROM civilian_enterprises WHERE location_id=? AND status IN ('active','strained') ORDER BY id", (city_location_id,)).fetchall()
    rng.shuffle(businesses)
    zones = conn.execute("SELECT id FROM underworld_zones WHERE city_location_id=? AND status='active' ORDER BY id", (city_location_id,)).fetchall()
    if not zones:
        return
    for br in businesses[: min(len(businesses), 24)]:
        zid = int(rng.choice(zones)[0])
        ctrl = zone_controller(conn, zid)
        if not ctrl:
            continue
        if rng.random() < .68:
            protect_business(conn, int(ctrl["organization_id"]), int(br[0]), zid, payment_per_30=rng.uniform(.35,1.8),
                             service_strength=rng.uniform(35,72), fear_component=rng.uniform(35,78), metadata={"opening_account": True})


def city_underworld_snapshot(conn: sqlite3.Connection, city_location_id: int) -> dict[str, Any]:
    forms = {str(r[0]): int(r[1]) for r in conn.execute(
        "SELECT organization_type,COUNT(*) FROM underworld_organizations WHERE primary_location_id=? AND status IN ('active','strained','fragmented') GROUP BY organization_type",
        (city_location_id,),
    ).fetchall()}
    org_ids = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_organizations WHERE primary_location_id=? AND status IN ('active','strained','fragmented')", (city_location_id,)).fetchall()]
    total_members = sum(float(r[0]) for r in conn.execute("SELECT member_count_estimate FROM underworld_organizations WHERE primary_location_id=? AND status IN ('active','strained','fragmented')", (city_location_id,)).fetchall())
    cmd = conn.execute(
        """SELECT COUNT(*),SUM(CASE WHEN cp.core_state='Open-Core' THEN 1 ELSE 0 END)
           FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id LEFT JOIN cultivation_profiles cp ON cp.actor_id=a.id
           JOIN underworld_organizations o ON o.id=p.organization_id
           WHERE o.primary_location_id=? AND p.status='active' AND p.role_kind IN ('boss','underboss','lieutenant','crew_leader')""",
        (city_location_id,),
    ).fetchone()
    # Estimated overall Open-Core stock comes from crew estimates, deliberately separate from named command figures.
    manpower = conn.execute(
        """SELECT COALESCE(SUM(c.size_estimate),0),COALESCE(SUM(c.open_core_estimate),0),COALESCE(SUM(c.staged_estimate),0)
           FROM underworld_crews c JOIN underworld_organizations o ON o.id=c.organization_id
           WHERE o.primary_location_id=? AND c.status='active'""",
        (city_location_id,),
    ).fetchone()
    return {
        "city_location_id": city_location_id,
        "organizations": len(org_ids), "forms": forms,
        "zones": int(conn.execute("SELECT COUNT(*) FROM underworld_zones WHERE city_location_id=? AND status='active'", (city_location_id,)).fetchone()[0]),
        "controlled_zones": int(conn.execute("SELECT COUNT(*) FROM underworld_zone_claims c JOIN underworld_zones z ON z.id=c.zone_id WHERE z.city_location_id=? AND c.claim_kind='controller' AND c.status='active'", (city_location_id,)).fetchone()[0]),
        "crews": int(conn.execute("SELECT COUNT(*) FROM underworld_crews c JOIN underworld_organizations o ON o.id=c.organization_id WHERE o.primary_location_id=? AND c.status='active'", (city_location_id,)).fetchone()[0]),
        "full_members_estimate": round(total_members,2),
        "crew_manpower_estimate": round(float(manpower[0] or 0),2),
        "open_core_manpower_estimate": round(float(manpower[1] or 0),2),
        "staged_manpower_estimate": round(float(manpower[2] or 0),2),
        "command_figures": int(cmd[0] or 0), "open_core_command_figures": int(cmd[1] or 0),
        "rackets": int(conn.execute("SELECT COUNT(*) FROM underworld_racket_sites r JOIN underworld_organizations o ON o.id=r.organization_id WHERE o.primary_location_id=? AND r.status='active'", (city_location_id,)).fetchone()[0]),
        "fronts": int(conn.execute("SELECT COUNT(*) FROM underworld_business_links l JOIN underworld_organizations o ON o.id=l.organization_id WHERE o.primary_location_id=? AND l.link_kind IN ('owned_front','controlled_front') AND l.status='active'", (city_location_id,)).fetchone()[0]),
        "protection_accounts": int(conn.execute("SELECT COUNT(*) FROM underworld_protection_accounts p JOIN underworld_zones z ON z.id=p.zone_id WHERE z.city_location_id=? AND p.status='active'", (city_location_id,)).fetchone()[0]),
    }


def organization_snapshot(conn: sqlite3.Connection, organization_id: int) -> dict[str, Any]:
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
    if not org:
        raise ValueError("unknown organization")
    culture = ensure_organization_culture(conn, organization_id)
    return {
        "id": organization_id, "name": org["name"], "form": org["organization_type"], "status": org["status"],
        "leader_actor_id": org["current_leader_actor_id"], "treasury": float(org["treasury"]),
        "members": float(org["member_count_estimate"]), "command_depth": int(org["command_depth"]),
        "culture": {k: culture[k] for k in ("membership_model","continuity_model","territorial_orientation","formality","violence_governance","open_core_command_bias","identity_strength","induction_required","hereditary_headship_preference")},
        "taboos": _loads(culture["taboo_policy_json"]),
        "zones": int(conn.execute("SELECT COUNT(*) FROM underworld_zone_claims WHERE organization_id=? AND claim_kind='controller' AND status='active'", (organization_id,)).fetchone()[0]),
        "crews": int(conn.execute("SELECT COUNT(*) FROM underworld_crews WHERE organization_id=? AND status='active'", (organization_id,)).fetchone()[0]),
        "rackets": int(conn.execute("SELECT COUNT(*) FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (organization_id,)).fetchone()[0]),
        "fronts": int(conn.execute("SELECT COUNT(*) FROM underworld_business_links WHERE organization_id=? AND link_kind IN ('owned_front','controlled_front') AND status='active'", (organization_id,)).fetchone()[0]),
        "protected_clients": int(conn.execute("SELECT COUNT(*) FROM underworld_protection_accounts WHERE protector_organization_id=? AND status='active'", (organization_id,)).fetchone()[0]),
    }


def _relation_pair(a: int, b: int) -> tuple[int, int]:
    if a == b:
        raise ValueError("organization cannot have a relation with itself")
    return tuple(sorted((int(a), int(b))))


def ensure_relation(conn: sqlite3.Connection, a: int, b: int, *, relation_kind: str = "neutral", hostility: float = 20, respect: float = 20) -> sqlite3.Row:
    x, y = _relation_pair(a, b)
    row = conn.execute("SELECT * FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (x, y)).fetchone()
    if not row:
        day = _day(conn)
        conn.execute(
            """INSERT INTO underworld_relations(organization_a_id,organization_b_id,relation_kind,hostility,respect,tribute_rate,started_day,last_changed_day,metadata_json)
               VALUES (?,?,?,?,?,0,?,?,?)""",
            (x, y, relation_kind, _clamp(hostility), _clamp(respect), day, day, '{}'),
        )
    return conn.execute("SELECT * FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (x, y)).fetchone()


def change_relation(conn: sqlite3.Connection, a: int, b: int, *, kind: str | None = None, hostility_delta: float = 0, respect_delta: float = 0,
                    tribute_rate: float | None = None, patron_organization_id: int | None = None, metadata: dict[str, Any] | None = None) -> sqlite3.Row:
    row = ensure_relation(conn, a, b)
    new_kind = kind or str(row["relation_kind"])
    allowed = {"neutral","rival","war","truce","ally","tributary","patron","hostile_peace"}
    if new_kind not in allowed:
        raise ValueError("invalid underworld relation kind")
    tr = float(row["tribute_rate"]) if tribute_rate is None else max(0.0, min(1.0, float(tribute_rate)))
    conn.execute(
        """UPDATE underworld_relations SET relation_kind=?,hostility=?,respect=?,tribute_rate=?,patron_organization_id=?,last_changed_day=?,metadata_json=?
           WHERE organization_a_id=? AND organization_b_id=?""",
        (new_kind, _clamp(float(row["hostility"]) + hostility_delta), _clamp(float(row["respect"]) + respect_delta), tr,
         patron_organization_id, _day(conn), _j(metadata or _loads(row["metadata_json"])), int(row["organization_a_id"]), int(row["organization_b_id"])),
    )
    return ensure_relation(conn, a, b)


def _finance(conn: sqlite3.Connection, organization_id: int, kind: str, amount: float, *, crew_id: int | None = None,
             enterprise_id: int | None = None, counterparty_organization_id: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    return int(conn.execute(
        """INSERT INTO underworld_finance_transactions(organization_id,day,transaction_kind,amount,crew_id,enterprise_id,counterparty_organization_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (organization_id, _day(conn), kind, float(amount), crew_id, enterprise_id, counterparty_organization_id, _j(metadata or {})),
    ).lastrowid)


def _operation(conn: sqlite3.Connection, organization_id: int, kind: str, *, zone_id: int | None = None, target_organization_id: int | None = None,
               target_actor_id: int | None = None, enterprise_id: int | None = None, crew_id: int | None = None,
               result: str = "attempted", success: float = 0.0, event_id: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    return int(conn.execute(
        """INSERT INTO underworld_operations(day,organization_id,operation_kind,zone_id,target_organization_id,target_actor_id,enterprise_id,crew_id,result,success,event_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_day(conn), organization_id, kind, zone_id, target_organization_id, target_actor_id, enterprise_id, crew_id, result, max(0.0,min(1.0,float(success))), event_id, _j(metadata or {})),
    ).lastrowid)


def ensure_heat_profile(conn: sqlite3.Connection, organization_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM underworld_heat WHERE organization_id=?", (organization_id,)).fetchone()
    if not row:
        org = conn.execute("SELECT corrupt_access FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
        if not org:
            raise ValueError("unknown organization")
        day = _day(conn)
        conn.execute(
            "INSERT INTO underworld_heat(organization_id,public_heat,investigative_heat,violence_heat,corruption_cover,last_review_day,next_review_day,metadata_json) VALUES (?,?,?,?,?,?,?,?)",
            (organization_id, 0, 0, 0, _clamp(float(org[0]) * .65), day, day + 30, '{}'),
        )
    return conn.execute("SELECT * FROM underworld_heat WHERE organization_id=?", (organization_id,)).fetchone()


def add_heat(conn: sqlite3.Connection, organization_id: int, *, public: float = 0, investigative: float = 0, violence: float = 0) -> sqlite3.Row:
    h = ensure_heat_profile(conn, organization_id)
    conn.execute(
        "UPDATE underworld_heat SET public_heat=?,investigative_heat=?,violence_heat=? WHERE organization_id=?",
        (_clamp(float(h["public_heat"]) + public), _clamp(float(h["investigative_heat"]) + investigative), _clamp(float(h["violence_heat"]) + violence), organization_id),
    )
    return ensure_heat_profile(conn, organization_id)


def _org_controlled_zones(conn: sqlite3.Connection, organization_id: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        "SELECT zone_id FROM underworld_zone_claims WHERE organization_id=? AND claim_kind='controller' AND status='active' ORDER BY zone_id", (organization_id,)
    ).fetchall()]


def _available_crew_capacity(conn: sqlite3.Connection, organization_id: int) -> tuple[float, float]:
    row = conn.execute(
        "SELECT COALESCE(SUM(size_estimate),0),COALESCE(SUM(assigned_patrol_strength),0) FROM underworld_crews WHERE organization_id=? AND status='active'",
        (organization_id,),
    ).fetchone()
    return float(row[0] or 0), float(row[1] or 0)


def _required_zone_manpower(conn: sqlite3.Connection, zone_id: int) -> float:
    z = conn.execute("SELECT * FROM underworld_zones WHERE id=?", (zone_id,)).fetchone()
    if not z:
        return 0.0
    rackets = conn.execute("SELECT COALESCE(SUM(labor_required),0) FROM underworld_racket_sites WHERE zone_id=? AND status='active'", (zone_id,)).fetchone()[0]
    accounts = conn.execute("SELECT COUNT(*) FROM underworld_protection_accounts WHERE zone_id=? AND status='active'", (zone_id,)).fetchone()[0]
    return 4.0 + float(z["population_scale"]) * .055 + float(z["commercial_intensity"]) * .045 + float(rackets or 0) * .40 + float(accounts or 0) * .18


def organization_manpower_balance(conn: sqlite3.Connection, organization_id: int) -> dict[str, float]:
    size, patrol = _available_crew_capacity(conn, organization_id)
    zones = _org_controlled_zones(conn, organization_id)
    required = sum(_required_zone_manpower(conn, z) for z in zones)
    return {"crew_manpower": size, "assigned_patrol": patrol, "territorial_requirement": required, "slack": size - required}


def collect_monthly_income(conn: sqlite3.Connection, organization_id: int) -> dict[str, float]:
    """Resolve the organization's monthly criminal cashflow.

    Rackets represent earning activity by members/crews. The treasury receives an upward share;
    it does not pay every member a central salary. Protection payments enter more directly.
    """
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
    if not org or str(org["status"]) not in {"active","strained","fragmented"}:
        return {"gross":0,"treasury_net":0,"leader_draw":0}
    culture = ensure_organization_culture(conn, organization_id)
    rackets = conn.execute("SELECT * FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (organization_id,)).fetchall()
    protections = conn.execute("SELECT * FROM underworld_protection_accounts WHERE protector_organization_id=? AND status='active'", (organization_id,)).fetchall()
    # More formal/corporate organizations generally centralize a larger share; this remains
    # institutional accounting, not an assertion of moral sophistication.
    kick_rate = .34 + float(culture["formality"]) / 100 * .23
    racket_gross = sum(float(r["gross_income_per_30"]) for r in rackets)
    protection_gross = sum(float(p["payment_per_30"]) for p in protections if not int(p["disputed"]))
    treasury_gross = racket_gross * kick_rate + protection_gross * .78
    # ECON-01 records the money path explicitly. Racket gross is still a gross earning estimate
    # here; the later personal-estate/merchant integration will model every client-side balance.
    for r in rackets:
        gross=float(r["gross_income_per_30"])
        if gross>0:
            _record_economic_flow(conn,"racket_kickup",gross*kick_rate,source_racket_id=int(r["id"]),target_organization_id=organization_id,
                                  racket_id=int(r["id"]),cadence_kind="monthly",rate=kick_rate,metadata={"gross_estimate":gross})
    for p in protections:
        if int(p["disputed"]):
            continue
        rid=int(p["racket_id"]) if p["racket_id"] is not None else _ensure_protection_racket(conn,organization_id,int(p["zone_id"]))
        if p["racket_id"] is None:
            conn.execute("UPDATE underworld_protection_accounts SET racket_id=? WHERE id=?",(rid,int(p["id"])))
        pay=float(p["payment_per_30"])
        if pay>0:
            _record_economic_flow(conn,"protection_payment",pay,source_enterprise_id=int(p["enterprise_id"]),target_racket_id=rid,
                                  racket_id=rid,protection_account_id=int(p["id"]),cadence_kind="monthly",metadata={"client_side_cash_not_yet_projected":True})
            _record_economic_flow(conn,"racket_kickup",pay*.78,source_racket_id=rid,target_organization_id=organization_id,
                                  racket_id=rid,protection_account_id=int(p["id"]),cadence_kind="monthly",rate=.78)
    # Overhead is bribes, specialists, safehouses, funerals, legal help, messengers and emergency
    # support. It is intentionally not payroll proportional to every member.
    crew_count = int(conn.execute("SELECT COUNT(*) FROM underworld_crews WHERE organization_id=? AND status='active'", (organization_id,)).fetchone()[0])
    front_count = int(conn.execute("SELECT COUNT(*) FROM underworld_business_links WHERE organization_id=? AND link_kind IN ('owned_front','controlled_front') AND status='active'", (organization_id,)).fetchone()[0])
    overhead = 0.10 * treasury_gross + crew_count * .10 + front_count * .08
    # Tribute is paid from the subordinate's take upward.
    tribute_paid = 0.0
    rels = conn.execute("SELECT * FROM underworld_relations WHERE (organization_a_id=? OR organization_b_id=?) AND relation_kind='tributary'", (organization_id,organization_id)).fetchall()
    for rel in rels:
        patron = rel["patron_organization_id"]
        if patron is not None and int(patron) != organization_id:
            amount = max(0.0, treasury_gross * float(rel["tribute_rate"]))
            tribute_paid += amount
            conn.execute("UPDATE underworld_organizations SET treasury=treasury+? WHERE id=?", (amount, int(patron)))
            _finance(conn, organization_id, "tribute_paid", -amount, counterparty_organization_id=int(patron))
            _finance(conn, int(patron), "tribute_received", amount, counterparty_organization_id=organization_id)
            _record_economic_flow(conn,"tribute",amount,source_organization_id=organization_id,target_organization_id=int(patron),cadence_kind="monthly",rate=float(rel["tribute_rate"]))
    net = max(0.0, treasury_gross - overhead - tribute_paid)
    draw_rate = float(org["monthly_leader_draw_rate"] or .08)
    leader_draw = net * draw_rate
    treasury_add = max(0.0, net - leader_draw)
    conn.execute("UPDATE underworld_organizations SET treasury=treasury+?,updated_day=? WHERE id=?", (treasury_add, _day(conn), organization_id))
    if treasury_gross:
        _finance(conn, organization_id, "criminal_income_kickup", treasury_gross, metadata={"racket_gross":racket_gross,"protection_gross":protection_gross,"kick_rate":kick_rate})
    if overhead:
        _finance(conn, organization_id, "organizational_overhead", -overhead)
    leader = org["current_leader_actor_id"]
    if leader is not None and leader_draw > 0:
        ensure_heat_profile(conn, organization_id)
        conn.execute("INSERT OR IGNORE INTO underworld_leader_wealth(actor_id,organization_id,last_review_day,metadata_json) VALUES (?,?,?,?)", (int(leader), organization_id, _day(conn), '{}'))
        conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=liquid_wealth+?,last_review_day=? WHERE actor_id=?", (leader_draw, _day(conn), int(leader)))
        _finance(conn, organization_id, "leader_draw", -leader_draw, metadata={"leader_actor_id":int(leader)})
        _record_economic_flow(conn,"leader_draw",leader_draw,source_organization_id=organization_id,target_actor_id=int(leader),cadence_kind="monthly",rate=draw_rate)
    return {"gross":treasury_gross,"treasury_net":treasury_add,"leader_draw":leader_draw,"overhead":overhead,"tribute_paid":tribute_paid}


def _boss_drives(conn: sqlite3.Connection, organization_id: int) -> dict[str, float]:
    row = conn.execute(
        """SELECT d.* FROM underworld_organizations o JOIN actor_drives d ON d.actor_id=o.current_leader_actor_id WHERE o.id=?""", (organization_id,)
    ).fetchone()
    if not row:
        return {"aggression":.5,"risk_tolerance":.5,"patience":.5,"loyalty":.5,"ambition":.6,"pragmatism":.6}
    return {k:float(row[k]) for k in ("aggression","risk_tolerance","patience","loyalty","ambition","pragmatism")}


def _adjacent_targets(conn: sqlite3.Connection, organization_id: int) -> list[tuple[int,int]]:
    graph = UnderworldZoneGraph(conn)
    own = _org_controlled_zones(conn, organization_id)
    out: list[tuple[int,int]] = []
    for zid in own:
        for other in graph.neighbors(zid):
            ctrl = zone_controller(conn, other)
            if ctrl and int(ctrl["organization_id"]) != organization_id:
                out.append((other, int(ctrl["organization_id"])))
    # deterministic unique order
    return list(dict.fromkeys(out))


def _vacant_adjacent_zones(conn: sqlite3.Connection, organization_id: int) -> list[int]:
    graph = UnderworldZoneGraph(conn)
    own = _org_controlled_zones(conn, organization_id)
    seen: list[int] = []
    for zid in own:
        for other in graph.neighbors(zid):
            if zone_controller(conn, other) is None and other not in seen:
                seen.append(other)
    return seen


def _recruit(conn: sqlite3.Connection, organization_id: int, rng: random.Random) -> int:
    from .underworld import record_underworld_membership_flow
    bal = organization_manpower_balance(conn, organization_id)
    treasury = float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()[0])
    base = 2 + max(0, -bal["slack"]) * .20 + min(5, treasury * .025)
    n = max(1, int(round(base * rng.uniform(.65,1.35))))
    record_underworld_membership_flow(conn, organization_id, "recruitment", n, to_tier="peripheral", metadata={"deliberate_push":True})
    _operation(conn, organization_id, "recruit", result="completed", success=1, metadata={"new_peripheral_associates":n})
    return n


def _open_new_racket(conn: sqlite3.Connection, organization_id: int, rng: random.Random) -> bool:
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
    zones = _org_controlled_zones(conn, organization_id)
    if not zones or float(org["treasury"]) < 3:
        return False
    zid = rng.choice(zones)
    existing = {str(r[0]) for r in conn.execute("SELECT racket_kind FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (organization_id,)).fetchall()}
    candidates = racket_kind_options(conn, zid, rng, count=6)
    choices = [x for x in candidates if x not in existing] or candidates
    rk = rng.choice(choices)
    cost = rng.uniform(1.2,3.5)
    if float(org["treasury"]) < cost:
        return False
    conn.execute("UPDATE underworld_organizations SET treasury=MAX(0,treasury-?) WHERE id=?", (cost, organization_id))
    _finance(conn, organization_id, "racket_investment", -cost)
    create_racket_site(conn, organization_id, rk, zone_id=zid, gross_income_per_30=rng.uniform(2.8,8.0), labor_required=rng.uniform(2.5,7), metadata={"autonomous_expansion":True})
    _operation(conn, organization_id, "open_racket", zone_id=zid, result="completed", success=1, metadata={"racket_kind":rk})
    heat_mult = RACKET_PROFILES.get(rk, {}).get("heat_mult", 1.0)
    add_heat(conn, organization_id, public=.5*heat_mult, investigative=.8*heat_mult)
    return True


def _buy_front(conn: sqlite3.Connection, organization_id: int, rng: random.Random) -> bool:
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
    if float(org["treasury"]) < 8:
        return False
    zones = _org_controlled_zones(conn, organization_id)
    zid = rng.choice(zones) if zones else None
    cost = rng.uniform(6,14)
    if float(org["treasury"]) < cost:
        return False
    conn.execute("UPDATE underworld_organizations SET treasury=treasury-? WHERE id=?", (cost,organization_id))
    _finance(conn,organization_id,"front_purchase",-cost)
    short = str(org["name"] or f"Org {organization_id}").split()[0]
    eid=create_front(conn,organization_id,f"{short} Front {int(_day(conn))}-{rng.randrange(1000)}","service",zone_id=zid,capital=cost,cash=cost*.25,metadata={"autonomous_purchase":True})
    _operation(conn,organization_id,"buy_front",zone_id=zid,enterprise_id=eid,result="completed",success=1)
    add_heat(conn,organization_id,public=.3,investigative=.25)
    return True


def _patrol(conn: sqlite3.Connection, organization_id: int, rng: random.Random) -> bool:
    zones=_org_controlled_zones(conn,organization_id)
    if not zones: return False
    # Prefer zones with open incidents/challengers.
    ranked=[]
    for zid in zones:
        pressure=int(conn.execute("SELECT COUNT(*) FROM underworld_incidents WHERE zone_id=? AND status='open'",(zid,)).fetchone()[0])
        ranked.append((pressure+rng.random(),zid))
    _,zid=max(ranked)
    crews=conn.execute("SELECT * FROM underworld_crews WHERE organization_id=? AND status='active' ORDER BY loyalty DESC,size_estimate DESC",(organization_id,)).fetchall()
    if not crews: return False
    crew=crews[0]; strength=min(float(crew["size_estimate"])*.45,max(2,float(crew["size_estimate"])*rng.uniform(.18,.35)))
    conn.execute("UPDATE underworld_crews SET assigned_patrol_strength=? WHERE id=?",(strength,int(crew["id"])))
    claim=zone_controller(conn,zid)
    if claim and int(claim["organization_id"])==organization_id:
        conn.execute("UPDATE underworld_zone_claims SET strength=MIN(100,strength+?),fear=MIN(100,fear+?) WHERE id=?",(rng.uniform(.5,2.0),rng.uniform(.2,1.2),int(claim["id"])))
    _operation(conn,organization_id,"patrol",zone_id=zid,crew_id=int(crew["id"]),result="completed",success=1,metadata={"patrol_strength":strength})
    return True


def _take_vacant_turf(conn: sqlite3.Connection, organization_id: int, rng: random.Random, *, event_logger: Callable[..., int] | None = None) -> bool:
    vacant=_vacant_adjacent_zones(conn,organization_id)
    if not vacant: return False
    bal=organization_manpower_balance(conn,organization_id)
    zid=rng.choice(vacant); need=_required_zone_manpower(conn,zid)
    if bal["slack"] < need*.65: return False
    set_zone_controller(conn,zid,organization_id,strength=rng.uniform(35,52),local_support=rng.uniform(25,48),fear=rng.uniform(34,58),metadata={"autonomous_expansion":True},event_logger=event_logger)
    _operation(conn,organization_id,"occupy_vacant_turf",zone_id=zid,result="completed",success=1)
    add_heat(conn,organization_id,public=.7)
    return True


def _territorial_attack(conn: sqlite3.Connection, organization_id: int, rng: random.Random, *, event_logger: Callable[..., int] | None = None) -> bool:
    targets=_adjacent_targets(conn,organization_id)
    if not targets: return False
    own_bal=organization_manpower_balance(conn,organization_id)
    if own_bal["slack"] < 2: return False
    # Prefer hostile target.
    scored=[]
    for zid,target in targets:
        rel=ensure_relation(conn,organization_id,target)
        scored.append((float(rel["hostility"])+rng.uniform(-12,12),zid,target))
    score,zid,target=max(scored)
    if score < 42: return False
    zone_name = conn.execute("SELECT name FROM underworld_zones WHERE id=?", (zid,)).fetchone()
    zname = str(zone_name[0]) if zone_name else f"zone {zid}"
    _record_territorial_occurrence(
        conn, event_logger=event_logger, event_type="underworld_territorial_attack",
        title=f"Territorial attack: {zname}", summary=f"An organization launched a territorial attack on {zname}.",
        severity_0_100=60, zone_id=zid, source_organization_id=organization_id, target_organization_id=target,
        tags=["violence", "territorial_change"],
    )
    ctrl=zone_controller(conn,zid)
    defense=float(ctrl["strength"]) if ctrl else 35
    atk_org=conn.execute("SELECT violence_capacity,reputation_deterrence FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    def_org=conn.execute("SELECT violence_capacity,reputation_deterrence FROM underworld_organizations WHERE id=?",(target,)).fetchone()
    attack=float(atk_org[0])*.40 + min(40,own_bal["slack"]*1.25)+rng.uniform(0,28)
    defend=defense*.45+float(def_org[0])*.35+rng.uniform(0,25)
    success=1/(1+math.exp(-(attack-defend)/12))
    won=rng.random()<success
    # Membership losses are concrete flows, mostly active full members in organized street fights.
    from .underworld import record_underworld_membership_flow
    att_prof=ensure_underworld_membership_profile(conn,organization_id); def_prof=ensure_underworld_membership_profile(conn,target)
    att_loss=min(float(att_prof["active_members"]), rng.uniform(.2,1.4)*(1.2 if not won else .7))
    def_loss=min(float(def_prof["active_members"]), rng.uniform(.3,1.8)*(1.2 if won else .7))
    if att_loss>0: record_underworld_membership_flow(conn,organization_id,"death_or_incapacitation",att_loss,from_tier="active",metadata={"territorial_fight":True,"target":target})
    if def_loss>0: record_underworld_membership_flow(conn,target,"death_or_incapacitation",def_loss,from_tier="active",metadata={"territorial_fight":True,"attacker":organization_id})
    if won:
        # Conquest only sticks if the attacker can staff the new zone after losses.
        post=organization_manpower_balance(conn,organization_id)
        if post["slack"] >= _required_zone_manpower(conn,zid)*.55:
            cid=_split_crew_for_zone(conn,organization_id,zid,_required_zone_manpower(conn,zid),rng=rng)
            if cid is not None:
                set_zone_controller(conn,zid,organization_id,strength=rng.uniform(35,55),local_support=rng.uniform(22,44),fear=rng.uniform(52,75),metadata={"won_from":target,"garrison_crew_id":cid},event_logger=event_logger)
                # Existing local protection switches only after control changes. ECON-01 requires
                # the account to move with a real protection operation, not become a hybrid row
                # pointing at the defeated organization's racket. The old racket remains part of
                # the defeated organization's history; the active client relationship moves to a
                # valid winner-side protection book.
                winner_protection_racket=_ensure_protection_racket(conn,organization_id,zid)
                conn.execute("""UPDATE underworld_protection_accounts
                                SET protector_organization_id=?,racket_id=?,disputed=0
                                WHERE zone_id=? AND status='active'""",
                             (organization_id,winner_protection_racket,zid))
                conn.execute("UPDATE underworld_business_links SET organization_id=? WHERE zone_id=? AND link_kind='protected_client' AND status='active'",(organization_id,zid))
            else:
                won=False
        else:
            won=False
    change_relation(conn,organization_id,target,kind="war",hostility_delta=10 if won else 6,respect_delta=3 if won else 0)
    attack_op_id=_operation(conn,organization_id,"territorial_attack",zone_id=zid,target_organization_id=target,result="won" if won else "repulsed",success=success,
               metadata={"attack_score":attack,"defense_score":defend,"attacker_losses":att_loss,"defender_losses":def_loss})
    add_heat(conn,organization_id,public=2.5,investigative=2.0,violence=5.0)
    add_heat(conn,target,public=1.2,investigative=1.0,violence=3.0)
    _record_territorial_occurrence(
        conn, event_logger=event_logger, event_type="underworld_territorial_attack_resolved",
        title=f"Territorial attack resolved: {zname}", summary=f"The attack on {zname} was {'won' if won else 'repulsed'}.",
        severity_0_100=70 if won else 55, zone_id=zid, source_organization_id=organization_id, target_organization_id=target,
        operation_id=attack_op_id, tags=["violence", "territorial_change" if won else "territorial_defense"],
        metadata={"result": "won" if won else "repulsed", "attacker_losses": att_loss, "defender_losses": def_loss},
    )
    if won:
        resolve_defeated_organization(conn,target,organization_id,rng=rng)
    return True


def _targeted_hit(conn: sqlite3.Connection, organization_id: int, rng: random.Random, *, event_logger: Callable[...,int] | None=None) -> bool:
    rels=conn.execute("SELECT * FROM underworld_relations WHERE (organization_a_id=? OR organization_b_id=?) AND relation_kind IN ('war','rival') AND hostility>=58 ORDER BY hostility DESC",(organization_id,organization_id)).fetchall()
    if not rels: return False
    rel=rels[0]; target=int(rel["organization_b_id"] if int(rel["organization_a_id"])==organization_id else rel["organization_a_id"])
    candidates=conn.execute("SELECT p.*,a.name FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.status='active' AND p.role_kind IN ('boss','underboss','lieutenant','crew_leader') AND a.status='active' ORDER BY p.authority DESC",(target,)).fetchall()
    if not candidates: return False
    victim=candidates[0]
    att=conn.execute("SELECT violence_capacity,cohesion FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    targ=conn.execute("SELECT violence_capacity,cohesion FROM underworld_organizations WHERE id=?",(target,)).fetchone()
    chance=_clamp(22+float(att[0])*.42+float(att[1])*.12-float(targ[0])*.22-float(targ[1])*.08+rng.uniform(-12,12),5,88)/100
    success=rng.random()<chance
    if success:
        from .household_life import mark_actor_deceased
        mark_actor_deceased(conn,int(victim["actor_id"]),reason="killed in an underworld hit",event_logger=event_logger)
        conn.execute("UPDATE underworld_personnel SET status='dead' WHERE actor_id=?",(int(victim["actor_id"]),))
    _operation(conn,organization_id,"targeted_hit",target_organization_id=target,target_actor_id=int(victim["actor_id"]),result="killed" if success else "failed",success=chance)
    change_relation(conn,organization_id,target,kind="war",hostility_delta=12 if success else 7,respect_delta=2 if success else 0)
    add_heat(conn,organization_id,public=2 if success else 1,investigative=5,violence=8)
    return True



def _ensure_leader_decision_cadence(conn: sqlite3.Connection, actor_id: int) -> None:
    """Underworld command is strategically causal, so its actor review cannot remain a 180-day dormant cadence."""
    day=_day(conn)
    row=conn.execute("SELECT 1 FROM simulation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if row:
        conn.execute("UPDATE simulation_profiles SET tier='STRATEGIC',cadence_days=MIN(cadence_days,30),next_review_day=MIN(next_review_day,?) WHERE actor_id=?",(day+30,actor_id))
    else:
        conn.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) VALUES (?,'STRATEGIC',30,.35,.75,?,?,3)",(actor_id,day,day+30))

def ensure_organization_leader(conn: sqlite3.Connection, organization_id: int, rng: random.Random | None=None) -> int | None:
    if rng is None: rng=random.Random(_seed(conn,organization_id*1901+_day(conn)))
    org=conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    if not org: return None
    current=org["current_leader_actor_id"]
    if current is not None:
        alive=conn.execute("SELECT a.status,lp.life_status FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?",(int(current),)).fetchone()
        if alive and str(alive[0])=='active' and (alive[1] is None or str(alive[1])=='living'):
            _ensure_leader_decision_cadence(conn,int(current))
            return int(current)
    culture=ensure_organization_culture(conn,organization_id)
    model=str(culture["membership_model"])
    candidates=conn.execute("""SELECT p.*,cp.core_state,cp.current_stage FROM underworld_personnel p LEFT JOIN cultivation_profiles cp ON cp.actor_id=p.actor_id
        JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.status='active' AND a.status='active'
        AND p.role_kind IN ('underboss','lieutenant','crew_leader','enforcer','accountant','fixer') ORDER BY p.authority DESC,p.earning_power DESC""",(organization_id,)).fetchall()
    def eligible(p:sqlite3.Row)->bool:
        ms=str(p['membership_status'])
        if model=='sworn': return ms=='sworn_member'
        if model=='blood_household': return ms=='blood_family'
        return ms in {'member','sworn_member','blood_family','employee'}
    pool=[p for p in candidates if eligible(p)]
    if not pool:
        # Causal importance promotes one anonymous member to a named contender. This is resolution,
        # not retroactive invention of an adult who was never in the organization.
        family=None
        if model=='blood_household':
            nm=str(org['name'] or '').split()[0]; family=nm if nm else None
        aid=create_personnel(conn,organization_id,role_kind='lieutenant',rng=rng,family_name=family,
                             membership_status='blood_family' if model=='blood_household' else ('sworn_member' if model=='sworn' else 'member'))
        pool=[conn.execute("SELECT p.*,cp.core_state,cp.current_stage FROM underworld_personnel p LEFT JOIN cultivation_profiles cp ON cp.actor_id=p.actor_id WHERE p.actor_id=?",(aid,)).fetchone()]
    def score(p:sqlite3.Row)->float:
        oc=12 if str(p['core_state'])=='Open-Core' else 0
        stage={'First':3,'Temper':7,'Third':13,'Breach':20,'Fifth':30,'Sixth':40}.get(str(p['current_stage']),0)
        blood=18 if model=='blood_household' and str(p['membership_status'])=='blood_family' else 0
        sworn=14 if model=='sworn' and str(p['membership_status'])=='sworn_member' else 0
        return float(p['authority'])*.65+float(p['earning_power'])*.20+oc+stage+blood+sworn+rng.uniform(0,8)
    winner=max(pool,key=score)
    aid=int(winner['actor_id'])
    former=int(current) if current is not None else None
    conn.execute("UPDATE underworld_personnel SET role_kind='boss',authority=100 WHERE actor_id=?",(aid,))
    conn.execute("UPDATE underworld_organizations SET current_leader_actor_id=?,succession_depth=MIN(100,succession_depth+2),updated_day=? WHERE id=?",(aid,_day(conn),organization_id))
    conn.execute("INSERT OR IGNORE INTO underworld_leader_wealth(actor_id,organization_id,last_review_day,metadata_json) VALUES (?,?,?,?)",(aid,organization_id,_day(conn),'{}'))
    conn.execute("INSERT INTO underworld_succession_history(organization_id,day,former_leader_actor_id,new_leader_actor_id,succession_kind,contested,metadata_json) VALUES (?,?,?,?,?,?,?)",
                 (organization_id,_day(conn),former,aid,model,0,_j({'selected_from_existing_membership':True})))
    _ensure_leader_decision_cadence(conn,aid)
    return aid


def review_leader_lifestyle(conn: sqlite3.Connection, organization_id: int, rng: random.Random) -> bool:
    org=conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone(); leader=org['current_leader_actor_id'] if org else None
    if leader is None: return False
    wealth=conn.execute("SELECT * FROM underworld_leader_wealth WHERE actor_id=?",(int(leader),)).fetchone()
    if not wealth: return False
    liquid=float(wealth['liquid_wealth']); current_value=float(wealth['property_value'])
    tiers=[('guarded townhouse','residence',18,18,42),('city mansion','residence',55,65,67),('country estate','fortified_residence',140,180,84)]
    target=None
    for kind,building_kind,cost,value,lifestyle in tiers:
        if liquid>=cost and current_value<value*.75: target=(kind,cost,value,lifestyle)
    if not target: return False
    kind,cost,value,lifestyle=target
    loc=int(org['primary_location_id']) if org['primary_location_id'] is not None else None
    name=conn.execute("SELECT name FROM actors WHERE id=?",(int(leader),)).fetchone()[0]
    bid=create_building(conn,f"{name}'s {kind}",building_kind,location_id=loc,owner_actor_id=int(leader),capacity=55,condition=100,prestige=lifestyle,utility=70,maintenance_burden=max(8,lifestyle*.12),metadata={'underworld_leader_property':True,'leader_property_tier':kind})
    conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=liquid_wealth-?,property_value=property_value+?,lifestyle_level=?,residence_building_id=?,last_review_day=? WHERE actor_id=?",
                 (cost,value,lifestyle,bid,_day(conn),int(leader)))
    _finance(conn,organization_id,'leader_property_purchase',-cost,metadata={'leader_actor_id':int(leader),'building_id':bid,'kind':kind})
    return True


def _review_heat(conn: sqlite3.Connection, organization_id: int, rng: random.Random, *, event_logger: Callable[..., int] | None = None) -> int:
    h=ensure_heat_profile(conn,organization_id)
    cover=float(h['corruption_cover'])
    public=max(0,float(h['public_heat'])-1.2-cover*.006)
    violent=max(0,float(h['violence_heat'])-1.5-cover*.004)
    investigative=max(0,float(h['investigative_heat'])-.7-cover*.010 + public*.018 + violent*.025)
    actions=0
    effective=investigative+violent*.35+public*.18-cover*.30
    if effective>=28:
        if effective>=65: kind='targeted_investigation'; sev=min(100,effective)
        elif effective>=48: kind='racket_raid'; sev=effective
        else: kind='patrol_surge'; sev=effective
        zones=_org_controlled_zones(conn,organization_id); zid=rng.choice(zones) if zones else None
        conn.execute("INSERT INTO underworld_enforcement_actions(organization_id,day,action_kind,severity,zone_id,result,metadata_json) VALUES (?,?,?,?,?,'applied',?)",
                     (organization_id,_day(conn),kind,_clamp(sev),zid,_j({'effective_pressure':effective,'corruption_cover':cover})))
        actions=1
        # Enforcement hurts operations without automatically destroying a successful organization.
        if kind=='racket_raid':
            rackets=conn.execute("SELECT id,secrecy FROM underworld_racket_sites WHERE organization_id=? AND status='active' ORDER BY id",(organization_id,)).fetchall()
            fronts=conn.execute(
                """SELECT bl.id AS link_id, ce.admin_quality FROM underworld_business_links bl
                   JOIN civilian_enterprises ce ON ce.id=bl.enterprise_id
                   WHERE bl.organization_id=? AND bl.link_kind IN ('owned_front','controlled_front') AND bl.status='active' ORDER BY bl.id""",
                (organization_id,),
            ).fetchall()
            # A racket's secrecy and a front's own bookkeeping quality both now actually
            # protect it, instead of a raid picking a random racket and never touching fronts.
            pool=[("racket",int(r["id"]),max(1.0,100.0-float(r["secrecy"]))) for r in rackets]
            pool+=[("front",int(f["link_id"]),max(1.0,100.0-float(f["admin_quality"]))) for f in fronts]
            if pool and rng.random()<.45:
                idx=rng.choices(range(len(pool)),weights=[p[2] for p in pool],k=1)[0]
                target_kind,target_id,_=pool[idx]
                if target_kind=="racket":
                    racket=conn.execute("SELECT zone_id,racket_kind FROM underworld_racket_sites WHERE id=?",(target_id,)).fetchone()
                    set_racket_status(conn,target_id,"suppressed")
                    _record_territorial_occurrence(
                        conn, event_logger=event_logger, event_type="underworld_racket_suppressed",
                        title="Racket suppressed", summary=f"A {racket['racket_kind']} racket was suppressed by enforcement.",
                        severity_0_100=sev, zone_id=int(racket["zone_id"]) if racket and racket["zone_id"] is not None else None,
                        source_organization_id=organization_id, tags=["asset_seizure"],
                        metadata={"racket_id": target_id, "racket_kind": racket["racket_kind"] if racket else None},
                    )
                else:
                    seize_front(conn,target_id,reason="racket_raid",event_logger=event_logger)
                investigative=max(0,investigative-4)
        elif kind=='targeted_investigation':
            investigative=max(0,investigative-6); public=max(0,public-2)
    conn.execute("UPDATE underworld_heat SET public_heat=?,investigative_heat=?,violence_heat=?,last_review_day=?,next_review_day=? WHERE organization_id=?",
                 (_clamp(public),_clamp(investigative),_clamp(violent),_day(conn),_day(conn)+30,organization_id))
    return actions


@dataclass(frozen=True)
class UnderworldCandidateAction:
    """A concrete, inspectable option pointing at real objects, Phase 2A section 3.4.

    This is deliberately thin. It is not a decision, a score, or a probability; it is a
    fact about what a real organization could concretely do right now, so that whatever
    replaces the current heuristic selector (Minerva-style candidate/utility split,
    PsychSim-style belief-bounded reasoning, or otherwise) has something real to select
    from instead of hard-coded option strings.
    """
    action_kind: str
    organization_id: int
    target_zone_id: int | None = None
    target_organization_id: int | None = None
    basis: str = ""
    requirements: dict[str, Any] = field(default_factory=dict)
    estimated_cost: float = 0.0
    risk_hint: float = 0.0
    reason_tags: tuple[str, ...] = ()


def underworld_candidate_actions(
    conn: sqlite3.Connection, organization_id: int, decision_view: dict[str, Any] | None = None,
) -> list[UnderworldCandidateAction]:
    """Enumerate real, concrete candidate actions for one organization. Read-only.

    Every candidate names a real zone id and/or a real rival organization id drawn from
    current adjacency/control/treasury facts; there is no abstract "attack" option that
    does not resolve to an actual reachable target. This performs no mutation, including
    no lazy-default relationship rows: hostility is read directly, defaulting to the same
    baseline ensure_relation would otherwise have written.
    """
    view = decision_view or {}
    drives = view.get("drives") or _boss_drives(conn, organization_id)
    treasury = view.get("treasury")
    if treasury is None:
        row = conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (organization_id,)).fetchone()
        treasury = float(row[0]) if row else 0.0

    candidates: list[UnderworldCandidateAction] = []
    for zid in _vacant_adjacent_zones(conn, organization_id):
        candidates.append(UnderworldCandidateAction(
            action_kind="occupy_vacant_turf", organization_id=organization_id, target_zone_id=zid,
            basis="known_vacant_adjacent_zone", requirements={"manpower_slack_fraction_of_need": .65},
            estimated_cost=_required_zone_manpower(conn, zid), risk_hint=.15, reason_tags=("expansion",),
        ))
    for zid, target in _adjacent_targets(conn, organization_id):
        x, y = _relation_pair(organization_id, target)
        rel = conn.execute("SELECT hostility FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (x, y)).fetchone()
        hostility = float(rel[0]) if rel else 20.0
        candidates.append(UnderworldCandidateAction(
            action_kind="challenge_organization", organization_id=organization_id, target_zone_id=zid,
            target_organization_id=target, basis="known_hostile_or_neutral_neighbor", requirements={"manpower_slack": 2},
            estimated_cost=2.0, risk_hint=_clamp(hostility) / 100.0, reason_tags=("conquest", "violence"),
        ))
    for zid in _org_controlled_zones(conn, organization_id):
        candidates.append(UnderworldCandidateAction(
            action_kind="patrol_zone", organization_id=organization_id, target_zone_id=zid,
            basis="controlled_zone", reason_tags=("defense",),
        ))
    if treasury >= 3:
        candidates.append(UnderworldCandidateAction(
            action_kind="open_racket", organization_id=organization_id, basis="treasury_threshold",
            requirements={"treasury": 3}, estimated_cost=3.0, risk_hint=.2, reason_tags=("income",),
        ))
    if treasury >= 8:
        candidates.append(UnderworldCandidateAction(
            action_kind="buy_front", organization_id=organization_id, basis="treasury_threshold",
            requirements={"treasury": 8}, estimated_cost=8.0, risk_hint=.1, reason_tags=("income", "legitimacy"),
        ))
    candidates.append(UnderworldCandidateAction(action_kind="recruit", organization_id=organization_id, basis="manpower_deficit_or_ambient"))
    candidates.append(UnderworldCandidateAction(action_kind="hold", organization_id=organization_id, basis="always_available"))
    return candidates


def autonomous_organization_turn(conn: sqlite3.Connection, organization_id: int, *, rng: random.Random | None=None, event_logger:Callable[...,int]|None=None) -> dict[str,Any]:
    if rng is None: rng=random.Random(_seed(conn,organization_id*3571+_day(conn)))
    org=conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    if not org or str(org['status']) not in {'active','strained','fragmented'}: return {'acted':False}
    leader=ensure_organization_leader(conn,organization_id,rng)
    ensure_crew_leadership(conn,organization_id,rng=rng)
    ensure_zone_staffing(conn,organization_id,rng=rng)
    cash=collect_monthly_income(conn,organization_id)
    # Anonymous membership still turns over in the background. Concrete crews are reconciled
    # immediately afterward so aggregate growth/loss cannot detach from operational manpower.
    from .underworld import simulate_underworld_membership_turnover
    h0=ensure_heat_profile(conn,organization_id)
    simulate_underworld_membership_turnover(conn,organization_id,rng,cash=float(conn.execute('select treasury from underworld_organizations where id=?',(organization_id,)).fetchone()[0]),
                                            violence_pressure=float(h0['violence_heat'])/100.0,event_logger=event_logger,actor_id=leader,location_id=int(org['primary_location_id']) if org['primary_location_id'] is not None else None)
    reconcile_crews_to_membership(conn,organization_id,rng=rng)
    # DEC-01 owns strategic choice through the leader actor's information-bounded decision review.
    # This monthly organization process now performs only institutional maintenance/accounting; it
    # no longer runs a second hard-coded criminal "brain" or fires random strategic hits.
    action='decision_runtime_owned'; acted=False; hit=False
    lifestyle=review_leader_lifestyle(conn,organization_id,rng)
    enforcement=_review_heat(conn,organization_id,rng,event_logger=event_logger)
    return {'acted':acted,'action':action,'hit':hit,'leader_actor_id':leader,'income':cash,'lifestyle_purchase':lifestyle,'enforcement_actions':enforcement}


def next_rebuild_underworld_due_day(conn:sqlite3.Connection,after_day:int,end_day:int)->int|None:
    r=conn.execute("SELECT MIN(next_review_day) FROM underworld_heat h JOIN underworld_organizations o ON o.id=h.organization_id WHERE o.status IN ('active','strained','fragmented') AND h.next_review_day>? AND h.next_review_day<=?",(after_day,end_day)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def process_due_rebuild_underworld(conn:sqlite3.Connection,day:int,*,event_logger:Callable[...,int]|None=None)->dict[str,int]:
    orgs=conn.execute("""SELECT o.id FROM underworld_organizations o JOIN underworld_heat h ON h.organization_id=o.id
        WHERE o.status IN ('active','strained','fragmented') AND h.next_review_day<=? ORDER BY o.id""",(day,)).fetchall()
    actions=hits=enforcement=succession=0
    for rr in orgs:
        oid=int(rr[0]); before=conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?",(oid,)).fetchone()[0]
        out=autonomous_organization_turn(conn,oid,event_logger=event_logger)
        actions+=int(bool(out.get('acted'))); hits+=int(bool(out.get('hit'))); enforcement+=int(out.get('enforcement_actions',0))
        after=conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?",(oid,)).fetchone()[0]
        succession+=int(before!=after)
    return {'rebuild_underworld_orgs_due':len(orgs),'rebuild_underworld_actions':actions,'rebuild_underworld_hits':hits,'rebuild_underworld_enforcement':enforcement,'rebuild_underworld_successions':succession}


def _membership_status_for_absorbed(culture: sqlite3.Row) -> str:
    model=str(culture['membership_model'])
    # Sworn-family membership cannot be acquired merely by conquest. Outsiders enter as
    # associates until separately inducted. Blood dynasties likewise do not manufacture kin.
    if model=='sworn': return 'associate'
    if model=='blood_household': return 'employee'
    return 'member'


def make_tributary(conn:sqlite3.Connection, subordinate_id:int, patron_id:int,*,tribute_rate:float=.15,metadata:dict[str,Any]|None=None)->None:
    if subordinate_id==patron_id: raise ValueError('self tribute impossible')
    change_relation(conn,subordinate_id,patron_id,kind='tributary',hostility_delta=-18,respect_delta=8,
                    tribute_rate=max(0.0,min(.75,float(tribute_rate))),patron_organization_id=patron_id,
                    metadata={'imposed_tribute':True,**(metadata or {})})
    _operation(conn,patron_id,'impose_tribute',target_organization_id=subordinate_id,result='completed',success=1,
               metadata={'tribute_rate':tribute_rate})


def make_truce(conn:sqlite3.Connection,a:int,b:int,*,metadata:dict[str,Any]|None=None)->None:
    change_relation(conn,a,b,kind='truce',hostility_delta=-32,respect_delta=3,metadata={'negotiated_truce':True,**(metadata or {})})
    _operation(conn,a,'truce',target_organization_id=b,result='completed',success=1,metadata=metadata)


def absorb_organization(conn:sqlite3.Connection,winner_id:int,loser_id:int,*,metadata:dict[str,Any]|None=None)->dict[str,Any]:
    """Absorb an organization without changing the winner's institutional form.

    A gang does not become a Mafia family by absorbing one; a Mafia family does not automatically
    make conquered gang members sworn members. Assets, crews and people move as concrete objects.
    """
    if winner_id==loser_id: raise ValueError('self absorption impossible')
    winner=conn.execute('select * from underworld_organizations where id=?',(winner_id,)).fetchone()
    loser=conn.execute('select * from underworld_organizations where id=?',(loser_id,)).fetchone()
    if not winner or not loser: raise ValueError('unknown organization')
    culture=ensure_organization_culture(conn,winner_id)
    wprof=ensure_underworld_membership_profile(conn,winner_id); lprof=ensure_underworld_membership_profile(conn,loser_id)
    # Transfer concrete territorial/economic assets first.
    loser_zones=_org_controlled_zones(conn,loser_id)
    for zid in loser_zones:
        set_zone_controller(conn,zid,winner_id,strength=42,local_support=30,fear=58,metadata={'absorbed_from':loser_id})
    conn.execute("update underworld_crews set organization_id=? where organization_id=? and status='active'",(winner_id,loser_id))
    new_status=_membership_status_for_absorbed(culture)
    conn.execute("update underworld_personnel set organization_id=?,membership_status=?,role_kind=case when role_kind='boss' then 'lieutenant' else role_kind end where organization_id=? and status='active'",
                 (winner_id,new_status,loser_id))
    # Transfer racket affiliation before protection accounts so ECON-01's protection invariant
    # never observes a winner-side client attached to a loser-side protection book. Historical
    # economic flows remain untouched; only active ownership/control interests transfer.
    conn.execute("update underworld_racket_sites set organization_id=? where organization_id=? and status='active'",(winner_id,loser_id))
    conn.execute("update economic_interests set holder_organization_id=? where holder_organization_id=? and status='active'",(winner_id,loser_id))
    # Organization-owned fronts are concrete assets: move the legal institution owner too.
    win_inst=winner['institution_actor_id']; lose_inst=loser['institution_actor_id']
    if win_inst is not None and lose_inst is not None:
        conn.execute("""update civilian_enterprises set institution_actor_id=? where institution_actor_id=? and id in
                     (select enterprise_id from underworld_business_links where organization_id=? and link_kind='owned_front' and status='active')""",
                     (int(win_inst),int(lose_inst),loser_id))
    conn.execute("update underworld_protection_accounts set protector_organization_id=? where protector_organization_id=? and status='active'",(winner_id,loser_id))
    conn.execute("update underworld_business_links set organization_id=? where organization_id=? and status='active'",(winner_id,loser_id))
    # Merge aggregate stocks to match the concrete transferred crews/people. This is not
    # recruitment provenance: they were already members of the absorbed organization.
    conn.execute("""update underworld_membership_profiles set core_members=core_members+?,active_members=active_members+?,
                 peripheral_associates=peripheral_associates+?,lifetime_entries=lifetime_entries+?,last_review_day=? where organization_id=?""",
                 (float(lprof['core_members']),float(lprof['active_members']),float(lprof['peripheral_associates']),
                  float(lprof['core_members'])+float(lprof['active_members'])+float(lprof['peripheral_associates']),_day(conn),winner_id))
    conn.execute("update underworld_membership_profiles set core_members=0,active_members=0,peripheral_associates=0,last_review_day=? where organization_id=?",(_day(conn),loser_id))
    total=float(wprof['core_members'])+float(wprof['active_members'])+float(lprof['core_members'])+float(lprof['active_members'])
    conn.execute("update underworld_organizations set member_count_estimate=?,treasury=treasury+?,updated_day=? where id=?",
                 (total,float(loser['treasury']),_day(conn),winner_id))
    conn.execute("update underworld_organizations set member_count_estimate=0,treasury=0,status='merged',updated_day=? where id=?",(_day(conn),loser_id))
    # Historical personnel from loser remain queryable after transfer through operation metadata.
    _operation(conn,winner_id,'absorb_organization',target_organization_id=loser_id,result='completed',success=1,
               metadata={'winner_form_preserved':str(winner['organization_type']),'loser_form':str(loser['organization_type']),**(metadata or {})})
    if win_inst is not None and lose_inst is not None:
        try:
            from .organization_lifecycle import record_absorption
            record_absorption(conn,int(win_inst),int(lose_inst),domain='underworld',
                              detail={'winner_organization_id':winner_id,'loser_organization_id':loser_id,
                                      'winner_form_preserved':str(winner['organization_type']),'loser_form':str(loser['organization_type'])})
        except (sqlite3.OperationalError, ImportError):
            pass
    _refresh_territory_summary(conn,winner_id); _refresh_racket_summary(conn,winner_id)
    return {'winner_id':winner_id,'loser_id':loser_id,'transferred_zones':len(loser_zones),'winner_form':str(winner['organization_type'])}


def ensure_crew_leadership(conn:sqlite3.Connection,organization_id:int,*,rng:random.Random|None=None)->int:
    if rng is None: rng=random.Random(_seed(conn,organization_id*2243+_day(conn)))
    repaired=0
    crews=conn.execute("select * from underworld_crews where organization_id=? and status='active' order by id",(organization_id,)).fetchall()
    org=conn.execute('select * from underworld_organizations where id=?',(organization_id,)).fetchone()
    family=str(org['name'] or '').split()[0] if org and str(org['organization_type'])=='criminal_dynasty' else None
    culture=ensure_organization_culture(conn,organization_id)
    for crew in crews:
        lid=crew['leader_actor_id']
        living=False
        if lid is not None:
            r=conn.execute("select a.status,p.status from actors a left join underworld_personnel p on p.actor_id=a.id where a.id=?",(int(lid),)).fetchone()
            living=bool(r and str(r[0])=='active' and str(r[1])=='active')
        if living: continue
        membership='blood_family' if str(culture['membership_model'])=='blood_household' and rng.random()<.72 else ('sworn_member' if str(culture['membership_model'])=='sworn' else 'member')
        aid=create_personnel(conn,organization_id,role_kind='crew_leader',crew_id=int(crew['id']),membership_status=membership,rng=rng,family_name=family)
        conn.execute('update underworld_crews set leader_actor_id=? where id=?',(aid,int(crew['id']))); repaired+=1
    return repaired


def _split_crew_for_zone(conn:sqlite3.Connection,organization_id:int,zone_id:int,required:float,*,rng:random.Random)->int|None:
    # One unit of manpower cannot be assigned to several territories at once. New territorial
    # control therefore requires either an existing unassigned crew or a physical split.
    free=conn.execute("select * from underworld_crews where organization_id=? and status='active' and home_zone_id is null order by size_estimate desc limit 1",(organization_id,)).fetchone()
    if free and float(free['size_estimate'])>=max(4,required*.55):
        conn.execute('update underworld_crews set home_zone_id=? where id=?',(zone_id,int(free['id']))); return int(free['id'])
    donor=conn.execute("select * from underworld_crews where organization_id=? and status='active' and size_estimate>=? order by size_estimate desc limit 1",
                       (organization_id,max(10,required*1.35))).fetchone()
    if not donor: return None
    split=max(5,min(float(donor['size_estimate'])*.42,required*.85))
    if float(donor['size_estimate'])-split<5: return None
    ratio=split/max(.001,float(donor['size_estimate']))
    conn.execute("update underworld_crews set size_estimate=size_estimate-?,open_core_estimate=max(0,open_core_estimate-?),staged_estimate=max(0,staged_estimate-?) where id=?",
                 (split,float(donor['open_core_estimate'])*ratio,float(donor['staged_estimate'])*ratio,int(donor['id'])))
    name=f"Split Crew {zone_id}-{_day(conn)}-{rng.randrange(1000)}"
    return create_crew(conn,organization_id,name,home_zone_id=zone_id,purpose_kind='territorial',size_estimate=split,
                       open_core_estimate=float(donor['open_core_estimate'])*ratio,staged_estimate=float(donor['staged_estimate'])*ratio,
                       cohesion=max(35,float(donor['cohesion'])-rng.uniform(0,6)),loyalty=max(35,float(donor['loyalty'])-rng.uniform(0,5)),rng=rng)


def ensure_zone_staffing(conn:sqlite3.Connection,organization_id:int,*,rng:random.Random|None=None)->dict[str,Any]:
    if rng is None: rng=random.Random(_seed(conn,organization_id*2689+_day(conn)))
    zones=_org_controlled_zones(conn,organization_id); assigned=0; understaffed=[]
    for zid in zones:
        rows=conn.execute("select * from underworld_crews where organization_id=? and home_zone_id=? and status='active' order by size_estimate desc",(organization_id,zid)).fetchall()
        required=_required_zone_manpower(conn,zid)
        staffed=sum(float(r['size_estimate']) for r in rows)
        if staffed>=required*.55: continue
        cid=_split_crew_for_zone(conn,organization_id,zid,required-staffed,rng=rng)
        if cid is None: understaffed.append(zid)
        else: assigned+=1
    return {'zones':len(zones),'new_assignments':assigned,'understaffed_zones':understaffed}


def resolve_defeated_organization(conn:sqlite3.Connection,loser_id:int,winner_id:int,*,rng:random.Random|None=None)->str|None:
    if rng is None: rng=random.Random(_seed(conn,loser_id*3011+winner_id*17+_day(conn)))
    loser=conn.execute('select * from underworld_organizations where id=?',(loser_id,)).fetchone()
    winner=conn.execute('select * from underworld_organizations where id=?',(winner_id,)).fetchone()
    if not loser or not winner or str(loser['status']) not in {'active','strained','fragmented'}: return None
    zones=_org_controlled_zones(conn,loser_id)
    profile=ensure_underworld_membership_profile(conn,loser_id)
    full=float(profile['core_members'])+float(profile['active_members'])
    if zones and full>=10: return None
    cohesion=float(loser['cohesion']); stability=float(loser['membership_stability']); treasury=float(loser['treasury'])
    form=str(loser['organization_type'])
    # Losing street sovereignty does not automatically destroy non-territorial commercial forms.
    culture=ensure_organization_culture(conn,loser_id)
    territorial=float(culture['territorial_orientation'])
    x=rng.random()
    if full<6 or (territorial>60 and not zones and cohesion<42):
        if x<.48:
            absorb_organization(conn,winner_id,loser_id,metadata={'defeat_resolution':True}); return 'absorbed'
        conn.execute("update underworld_organizations set status='fragmented',updated_day=? where id=?",(_day(conn),loser_id))
        return 'fragmented'
    if not zones and territorial>55:
        if x<.42:
            make_tributary(conn,loser_id,winner_id,tribute_rate=rng.uniform(.10,.24),metadata={'defeat_resolution':True}); return 'tributary'
        if x<.72:
            make_truce(conn,loser_id,winner_id,metadata={'defeat_resolution':True,'withdrawal':True}); return 'truce'
        # Survives as displaced organization while seeking new ground.
        conn.execute("update underworld_organizations set status='strained',updated_day=? where id=?",(_day(conn),loser_id)); return 'displaced'
    if treasury<2 and stability<45 and x<.35:
        absorb_organization(conn,winner_id,loser_id,metadata={'commercial_collapse_after_defeat':True}); return 'absorbed'
    return None


def reconcile_crews_to_membership(conn:sqlite3.Connection,organization_id:int,*,rng:random.Random|None=None)->dict[str,Any]:
    """Make concrete crew manpower equal the organization's current full-member stock.

    Aggregate membership is allowed to stay low-resolution, but it cannot float free of the crews
    that actually patrol, collect, fight and hold territory. New command figures crystallize only
    when the organization causally needs another crew leader.
    """
    if rng is None: rng=random.Random(_seed(conn,organization_id*3253+_day(conn)))
    p=ensure_underworld_membership_profile(conn,organization_id)
    target=max(0.0,float(p['core_members'])+float(p['active_members']))
    crews=conn.execute("select * from underworld_crews where organization_id=? and status='active' order by id",(organization_id,)).fetchall()
    if not crews and target>0:
        create_crew(conn,organization_id,f'Core Crew {_day(conn)}',size_estimate=target,open_core_estimate=target*.11,staged_estimate=target*.065,rng=rng)
        crews=conn.execute("select * from underworld_crews where organization_id=? and status='active' order by id",(organization_id,)).fetchall()
    current=sum(float(c['size_estimate']) for c in crews)
    created=depleted=0
    if target>current+.01:
        delta=target-current
        # Existing crews can absorb some people, but very large crews fork into additional units.
        while delta>0.01:
            crews=conn.execute("select * from underworld_crews where organization_id=? and status='active' order by size_estimate asc,id",(organization_id,)).fetchall()
            avg=target/max(1,len(crews))
            if avg>30 or (delta>=12 and all(float(c['size_estimate'])>=24 for c in crews)):
                add=min(delta,rng.uniform(12,22))
                ratio=rng.uniform(.08,.15)
                create_crew(conn,organization_id,f'Crew {len(crews)+1}-{_day(conn)}-{rng.randrange(1000)}',size_estimate=add,
                            open_core_estimate=add*ratio,staged_estimate=add*ratio*rng.uniform(.45,.75),purpose_kind='general',rng=rng)
                delta-=add; created+=1
            else:
                c=crews[0]; room=max(1,28-float(c['size_estimate'])); add=min(delta,room)
                ratio=(float(c['open_core_estimate'])/max(1,float(c['size_estimate']))) if float(c['size_estimate'])>0 else .11
                conn.execute("update underworld_crews set size_estimate=size_estimate+?,open_core_estimate=open_core_estimate+?,staged_estimate=staged_estimate+? where id=?",
                             (add,add*ratio,add*ratio*.60,int(c['id'])))
                delta-=add
    elif current>target+.01 and current>0:
        remove=current-target
        crews=conn.execute("select * from underworld_crews where organization_id=? and status='active' order by size_estimate asc,id",(organization_id,)).fetchall()
        for c in crews:
            if remove<=.01: break
            size=float(c['size_estimate']); floor=3.0
            take=min(remove,max(0,size-floor))
            if take>0:
                ratio=take/max(.001,size)
                conn.execute("update underworld_crews set size_estimate=size_estimate-?,open_core_estimate=max(0,open_core_estimate-?),staged_estimate=max(0,staged_estimate-?) where id=?",
                             (take,float(c['open_core_estimate'])*ratio,float(c['staged_estimate'])*ratio,int(c['id'])))
                remove-=take
        if remove>.01:
            # If the organization has collapsed below viable multi-crew size, whole units disappear.
            crews=conn.execute("select * from underworld_crews where organization_id=? and status='active' order by size_estimate asc,id",(organization_id,)).fetchall()
            for c in crews:
                if remove<=.01: break
                size=float(c['size_estimate'])
                if len(crews)-depleted<=1: break
                conn.execute("update underworld_crews set status='depleted',size_estimate=0,open_core_estimate=0,staged_estimate=0,assigned_patrol_strength=0 where id=?",(int(c['id']),))
                remove-=size; depleted+=1
    ensure_crew_leadership(conn,organization_id,rng=rng)
    crew_count=int(conn.execute("select count(*) from underworld_crews where organization_id=? and status='active'",(organization_id,)).fetchone()[0])
    depth=1 if crew_count<=1 else (2 if crew_count<=4 else (3 if crew_count<=11 else 4))
    conn.execute("update underworld_organizations set command_depth=?,updated_day=? where id=?",(depth,_day(conn),organization_id))
    final=float(conn.execute("select coalesce(sum(size_estimate),0) from underworld_crews where organization_id=? and status='active'",(organization_id,)).fetchone()[0])
    return {'target_full_members':target,'crew_manpower':final,'crews_created':created,'crews_depleted':depleted,'command_depth':depth}
