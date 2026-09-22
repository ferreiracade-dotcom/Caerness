from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainActionOption:
    kind: str
    score: float
    rationale: str
    mode: str = "direct"  # direct | interaction
    target_actor_id: int | None = None
    interaction_type: str | None = None
    payload: dict[str, Any] | None = None


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _rng(conn: sqlite3.Connection, actor_id: int, day: int, salt: int = 0) -> random.Random:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed * 1_000_003 + actor_id * 31_337 + day * 9_973 + salt)


def _name(conn: sqlite3.Connection, actor_id: int) -> str:
    row = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()
    return str(row[0]) if row else f"Actor {actor_id}"


def _actor_type(conn: sqlite3.Connection, actor_id: int) -> str | None:
    row = conn.execute("SELECT actor_type FROM actors WHERE id=?", (actor_id,)).fetchone()
    return str(row[0]) if row else None


def _current_location(conn: sqlite3.Connection, actor_id: int) -> int | None:
    row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _competence(conn: sqlite3.Connection, actor_id: int, domain_key: str) -> float:
    row = conn.execute(
        """SELECT MAX(ac.score) FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=?""",
        (actor_id, domain_key),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _resource(conn: sqlite3.Connection, actor_id: int, *keys: str) -> float:
    if not keys:
        return 0.0
    marks = ",".join("?" for _ in keys)
    row = conn.execute(
        f"SELECT SUM(amount) FROM resources WHERE actor_id=? AND resource_type IN ({marks})",
        (actor_id, *keys),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _source_payload(conn: sqlite3.Connection, actor_id: int) -> dict[str, Any]:
    row = conn.execute(
        """SELECT source_payload_json FROM source_identity_map
           WHERE entity_kind='actor' AND entity_id=? AND source_namespace='caerness_seed_v1_1'
           ORDER BY id LIMIT 1""",
        (actor_id,),
    ).fetchone()
    return _loads(row[0], {}) if row else {}


def _authoritative_stage(conn: sqlite3.Connection, actor_id: int, source: dict[str, Any] | None = None) -> str | None:
    # v0.32 cultivation profiles own current Stage once present; the imported source payload is
    # opening provenance and must not become permanent truth after a breakthrough.
    row=conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if row is not None:
        return row[0]
    src=source if source is not None else _source_payload(conn,actor_id)
    return src.get('stage')


def _log_attempt(
    conn: sqlite3.Connection,
    actor_id: int | None,
    kind: str,
    domain_key: str,
    status: str,
    *,
    institution_actor_id: int | None = None,
    reason: str | None = None,
    inputs: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    day: int | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO autonomous_action_attempts(
               day,actor_id,institution_actor_id,action_kind,domain_key,status,reason,input_json,result_json
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            _day(conn) if day is None else int(day), actor_id, institution_actor_id, kind, domain_key, status, reason,
            json.dumps(inputs or {}, sort_keys=True, default=str), json.dumps(result or {}, sort_keys=True, default=str),
        ),
    )
    return int(cur.lastrowid)


def _active_union(conn: sqlite3.Connection, actor_id: int) -> bool:
    return conn.execute(
        """SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?) LIMIT 1""",
        (actor_id, actor_id),
    ).fetchone() is not None


def _training_options(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, drives: dict[str, float]) -> list[DomainActionOption]:
    out: list[DomainActionOption] = []
    active = conn.execute(
        """SELECT e.id,e.practice_quality,e.program_id,p.name,p.domain_key,p.institution_actor_id
           FROM education_enrollments e JOIN education_programs p ON p.id=e.program_id
           WHERE e.actor_id=? AND e.status='active' ORDER BY e.id""",
        (actor_id,),
    ).fetchall()
    if active:
        # This is a real decision over the authoritative enrollment state, not a duplicate training clock.
        # The education subsystem still owns progress and completion; the actor only adjusts effort quality.
        row = active[0]
        tier_scale = {"ACTIVE": 1.0, "STRATEGIC": 0.88, "DORMANT": 0.65}.get(tier, 0.75)
        score = (4.7 + 1.5 * drives.get("ambition", 0.5) + 1.1 * drives.get("patience", 0.5)) * tier_scale
        out.append(DomainActionOption(
            "adjust_training_effort", score,
            f"Choose how much effort to sustain in {row['name']} rather than merely passing time.",
            payload={"enrollment_id": int(row["id"]), "program_id": int(row["program_id"])},
        ))
        return out

    paused = conn.execute(
        """SELECT e.id,p.name,p.status AS program_status,p.min_teacher_score,e.primary_teacher_actor_id
           FROM education_enrollments e JOIN education_programs p ON p.id=e.program_id
           WHERE e.actor_id=? AND e.status='paused' ORDER BY e.id LIMIT 1""",
        (actor_id,),
    ).fetchone()
    if paused and str(paused["program_status"]) == "active":
        teacher = paused["primary_teacher_actor_id"]
        teacher_ok = float(paused["min_teacher_score"]) <= 0
        if teacher is not None:
            a = conn.execute("SELECT status FROM actors WHERE id=?", (teacher,)).fetchone()
            teacher_ok = bool(a and str(a[0]).lower() not in {"dead", "deceased"})
        if teacher_ok:
            out.append(DomainActionOption(
                "resume_training", 7.2,
                f"Resume the interrupted program {paused['name']} while its teaching conditions remain available.",
                payload={"enrollment_id": int(paused["id"])},
            ))
            return out

    # Seeking a new program is conservative in the current-canon import: only an actor whose source
    # record already says training is active may autonomously seek formal placement. This prevents
    # Open-Core people from being pushed into cultivation simply to create activity.
    source = _source_payload(conn, actor_id)
    tr = ((source.get("runtime_v1_1") or {}).get("training_state") or {})
    if not tr.get("active") or _authoritative_stage(conn, actor_id, source) not in {"First", "Temper"}:
        return out
    memberships = [int(r[0]) for r in conn.execute(
        "SELECT institution_actor_id FROM institution_memberships WHERE member_actor_id=? AND status='active'",
        (actor_id,),
    ).fetchall()]
    for iid in memberships:
        program = conn.execute(
            """SELECT p.*, (SELECT COUNT(*) FROM education_enrollments e WHERE e.program_id=p.id AND e.status='active') AS active_count
               FROM education_programs p WHERE p.institution_actor_id=? AND p.status='active'
               ORDER BY CASE p.program_kind WHEN 'martial_foundation' THEN 0 ELSE 1 END,p.id LIMIT 1""",
            (iid,),
        ).fetchone()
        if not program or int(program["active_count"]) >= int(program["capacity"]):
            continue
        if _competence(conn, actor_id, str(program["domain_key"])) < float(program["min_entry_score"]):
            continue
        if conn.execute(
            "SELECT 1 FROM education_enrollments WHERE actor_id=? AND program_id=? AND status IN ('active','paused','completed')",
            (actor_id, int(program["id"])),
        ).fetchone():
            continue
        out.append(DomainActionOption(
            "seek_training", 6.7,
            f"Seek admission to {program['name']} through the institution already connected to the actor.",
            mode="interaction", target_actor_id=iid, interaction_type="request",
            payload={"program_id": int(program["id"]), "institution_actor_id": iid},
        ))
        break
    return out


def _treatment_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    condition = conn.execute(
        """SELECT c.* FROM health_conditions c
           WHERE c.actor_id=? AND c.status IN ('active','recovering','chronic')
             AND NOT EXISTS(SELECT 1 FROM medical_treatments mt WHERE mt.condition_id=c.id AND mt.status='active')
           ORDER BY c.severity DESC,c.id LIMIT 1""",
        (actor_id,),
    ).fetchone()
    if not condition:
        return None
    loc = _current_location(conn, actor_id)
    if loc is None:
        return None
    req = str(condition["specialist_requirement"] or "none")
    if req in {"vein_mender", "legendary_vein_mender"}:
        domain = "vein_mending"; minimum = 90.0 if req == "legendary_vein_mender" else 55.0; treatment = "vein_mending"
    else:
        domain = "medicine"; minimum = 35.0; treatment = "ordinary_medicine"
    provider = conn.execute(
        """SELECT a.id,MAX(ac.score) score FROM actors a
           JOIN actor_competence ac ON ac.actor_id=a.id JOIN competence_domains d ON d.id=ac.domain_id
           WHERE a.actor_type='character' AND a.status='active' AND a.current_location_id=? AND a.id<>?
             AND d.domain_key=?
           GROUP BY a.id HAVING MAX(ac.score)>=? ORDER BY score DESC,a.id LIMIT 1""",
        (loc, actor_id, domain, minimum),
    ).fetchone()
    if not provider:
        return None
    return DomainActionOption(
        "seek_treatment", min(10.0, 5.5 + float(condition["severity"]) / 15.0),
        f"Seek treatment for {condition['label']} from an available qualified provider.",
        mode="interaction", target_actor_id=int(provider["id"]), interaction_type="request",
        payload={"condition_id": int(condition["id"]), "treatment_kind": treatment, "provider_actor_id": int(provider["id"])},
    )


def _union_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    lp = conn.execute(
        "SELECT family_formation_eligible,life_stage,life_status,demographic_sex FROM actor_life_profiles WHERE actor_id=?",
        (actor_id,),
    ).fetchone()
    if not lp or not int(lp["family_formation_eligible"] or 0) or str(lp["life_status"]) != "living" or str(lp["life_stage"]) not in {"adult", "elder"}:
        return None
    if str(lp["demographic_sex"] or "unspecified") not in {"female", "male"}:
        # FAMILY-02 treats missing demographic sex as incomplete state, not as permission to
        # manufacture a marriage trajectory. Background people with resolved sex remain eligible.
        return None
    if _active_union(conn, actor_id):
        return None
    loc = _current_location(conn, actor_id)
    if loc is None:
        return None
    # Existing positive relationship + time is required. Named-roster shortage never causes a match.
    rels = conn.execute(
        """SELECT r.*, r.actor_b_id partner_id
           FROM relationships r
           JOIN actors p ON p.id=r.actor_b_id
           JOIN actor_life_profiles lp ON lp.actor_id=p.id
           LEFT JOIN (SELECT actor_a_id,actor_b_id,MIN(started_day) started_day FROM social_contact_links
                      WHERE status='active' GROUP BY actor_a_id,actor_b_id) sc
             ON sc.actor_a_id=MIN(r.actor_a_id,r.actor_b_id) AND sc.actor_b_id=MAX(r.actor_a_id,r.actor_b_id)
           WHERE r.actor_a_id=? AND p.actor_type='character' AND p.status='active'
             AND p.current_location_id=? AND lp.life_status='living' AND lp.family_formation_eligible=1
             AND lp.life_stage='adult' AND lp.demographic_sex IN ('female','male') AND r.trust>=30 AND r.stance>=20
             AND COALESCE(sc.started_day,r.updated_day)<=?
           ORDER BY (r.trust+r.stance+r.obligation) DESC,r.id""",
        (actor_id, loc, day - 180),
    ).fetchall()
    for r in rels:
        partner = int(r["partner_id"])
        if _active_union(conn, partner):
            continue
        # FAMILY-02 hard feasibility lives in household_life so every mutation path agrees.
        from .household_life import prohibited_union_kinship_reason
        if prohibited_union_kinship_reason(conn, actor_id, partner):
            continue
        return DomainActionOption(
            "propose_union", 6.0 + min(2.5, (float(r["trust"]) + float(r["stance"])) / 80.0),
            f"Propose household formation to {_name(conn, partner)} after an established positive relationship.",
            mode="interaction", target_actor_id=partner, interaction_type="offer",
            payload={"partner_actor_id": partner, "union_kind": "marriage"},
        )
    return None


def _business_option(conn: sqlite3.Connection, actor_id: int, day: int, drives: dict[str, float]) -> DomainActionOption | None:
    if _actor_type(conn, actor_id) != "character":
        return None
    if conn.execute(
        "SELECT 1 FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained','insolvent') LIMIT 1",
        (actor_id,),
    ).fetchone():
        return None
    capital = _resource(conn, actor_id, "capital", "operating_reserve", "savings")
    if capital < 20:
        return None
    loc = _current_location(conn, actor_id)
    if loc is None:
        return None
    # A generic context row must exist. Default vocabulary values alone are not an opportunity signal.
    ctx = conn.execute("SELECT * FROM location_commercial_context WHERE location_id=?", (loc,)).fetchone()
    if not ctx:
        return None
    commerce = _competence(conn, actor_id, "commerce")
    craft = _competence(conn, actor_id, "craft")
    medicine = _competence(conn, actor_id, "medicine")
    if medicine >= 35 and float(ctx["health_demand"]) >= 55:
        archetype = "physician_practice"
    elif craft >= 35 and float(ctx["craft_demand"]) >= 55:
        archetype = "smithy"
    elif commerce >= 25 and float(ctx["trade_flow"]) >= 55:
        archetype = "wholesaler"
    elif float(ctx["traveler_flow"]) >= 65:
        archetype = "inn"
    elif float(ctx["foot_traffic"]) >= 65:
        archetype = "food_shop"
    else:
        return None
    opportunity = max(float(ctx["trade_flow"]), float(ctx["traveler_flow"]), float(ctx["foot_traffic"]), float(ctx["craft_demand"]), float(ctx["health_demand"]))
    score = 4.0 + opportunity / 25.0 + 1.6 * drives.get("ambition", 0.5) + 1.2 * drives.get("risk_tolerance", 0.5)
    return DomainActionOption(
        "found_enterprise", score,
        f"Commit available capital to a grounded local {archetype.replace('_', ' ')} opportunity.",
        payload={"archetype_key": archetype, "location_id": loc, "capital_commitment": min(capital * 0.6, 40.0)},
    )



def _work_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    """Seek an explicitly configured career opening; never invent an employer or career track."""
    if _actor_type(conn, actor_id) != "character":
        return None
    if conn.execute("SELECT 1 FROM actor_careers WHERE actor_id=? AND status='active' LIMIT 1", (actor_id,)).fetchone():
        return None
    loc = _current_location(conn, actor_id)
    if loc is None:
        return None
    rows = conn.execute(
        """SELECT ct.*,ip.actor_id AS institution_actor_id
           FROM career_tracks ct
           JOIN institution_profiles ip ON ip.institution_kind=ct.institution_kind
           JOIN actors ia ON ia.id=ip.actor_id
           WHERE ct.institution_kind IS NOT NULL AND ia.status='active' AND ia.current_location_id=?
           ORDER BY ct.is_canon DESC,ct.id,ip.actor_id""",
        (loc,),
    ).fetchall()
    for row in rows:
        track_id = int(row["id"])
        # Honor the first configured stage's explicit entry requirement if there is one.
        stage = conn.execute(
            "SELECT entry_requirements_json FROM career_stages WHERE track_id=? ORDER BY sequence_index,id LIMIT 1",
            (track_id,),
        ).fetchone()
        req = _loads(stage[0], {}) if stage else {}
        domain = str(req.get("competence_domain") or row["domain"] or "")
        minimum = float(req.get("min_competence", 0) or 0)
        if domain and minimum > 0 and _competence(conn, actor_id, domain) < minimum:
            continue
        inst = int(row["institution_actor_id"])
        return DomainActionOption(
            "seek_work", 5.9,
            f"Seek entry into the configured {row['name']} career through {_name(conn, inst)}.",
            mode="interaction", target_actor_id=inst, interaction_type="request",
            payload={"track_id": track_id, "institution_actor_id": inst},
        )
    return None


def _obligation_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    """Propose a bounded due-date renegotiation only for a real active obligation and counterparty."""
    row = conn.execute(
        """SELECT o.*,a.status AS counterparty_status FROM obligations o
           JOIN actors a ON a.id=o.counterparty_actor_id
           WHERE o.actor_id=? AND o.status='active' AND o.counterparty_actor_id IS NOT NULL
             AND o.due_day IS NOT NULL AND o.due_day<=? AND a.status='active'
           ORDER BY o.importance DESC,o.due_day,o.id LIMIT 1""",
        (actor_id, day + 30),
    ).fetchone()
    if not row:
        return None
    due = int(row["due_day"])
    extension = 30 if due >= day else min(60, 30 + max(0, day - due))
    proposed = max(due + 30, day + extension)
    urgency = max(0, day - due)
    score = 6.0 + float(row["importance"]) * 0.55 + min(2.0, urgency / 15.0)
    return DomainActionOption(
        "renegotiate_obligation", score,
        f"Ask {_name(conn, int(row['counterparty_actor_id']))} to renegotiate the due date of an existing obligation.",
        mode="interaction", target_actor_id=int(row["counterparty_actor_id"]), interaction_type="negotiation",
        payload={"obligation_id": int(row["id"]), "prior_due_day": due, "proposed_due_day": proposed},
    )


def _household_service_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    """Seek real household service only where finances/staff capacity are quantitatively resolved."""
    if _actor_type(conn, actor_id) != 'character':
        return None
    if conn.execute("SELECT 1 FROM household_service_terms WHERE actor_id=? AND status='active' LIMIT 1", (actor_id,)).fetchone():
        return None
    if conn.execute("SELECT 1 FROM actor_careers WHERE actor_id=? AND status='active' LIMIT 1", (actor_id,)).fetchone():
        return None
    loc=_current_location(conn,actor_id)
    if loc is None:
        return None
    rows=conn.execute(
        """SELECT h.*,a.status AS head_status FROM households h JOIN actors a ON a.id=h.head_actor_id
           WHERE h.location_id=? AND h.status='active' AND h.head_actor_id IS NOT NULL AND h.head_actor_id<>?
           ORDER BY h.liquidity DESC,h.staff_capacity DESC,h.id""", (loc,actor_id)
    ).fetchall()
    for h in rows:
        meta=_loads(h['metadata_json'],{})
        if meta.get('economic_resolution')=='STRUCTURAL_ONLY' or meta.get('economic_state')=='NOT_SEPARATELY_QUANTIFIED':
            continue
        if str(h['head_status'])!='active' or float(h['liquidity'])<10 or float(h['wealth'])<=0 or float(h['staff_capacity'])<35:
            continue
        active=int(conn.execute("SELECT COUNT(*) FROM household_service_terms WHERE household_id=? AND status='active'",(int(h['id']),)).fetchone()[0])
        slots=max(1,int(float(h['staff_capacity'])//20))
        if active>=slots:
            continue
        return DomainActionOption(
            'seek_household_service',5.6 + min(1.5,float(h['liquidity'])/40.0),
            f"Seek ordinary household service with {h['name']}, which has resolved means and staff capacity.",
            mode='interaction',target_actor_id=int(h['head_actor_id']),interaction_type='request',
            payload={'household_id':int(h['id']),'service_role':'servant','household_head_actor_id':int(h['head_actor_id'])},
        )
    return None


def _household_migration_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    """A declining, quantitatively resolved household may move toward an adjacent demonstrably better node."""
    row=conn.execute(
        """SELECT * FROM households WHERE head_actor_id=? AND status='declining' AND location_id IS NOT NULL
           ORDER BY id LIMIT 1""",(actor_id,)
    ).fetchone()
    if not row:
        return None
    meta=_loads(row['metadata_json'],{})
    if meta.get('economic_resolution')=='STRUCTURAL_ONLY' or meta.get('economic_state')=='NOT_SEPARATELY_QUANTIFIED':
        return None
    hid=int(row['id']); origin=int(row['location_id'])
    if conn.execute("SELECT 1 FROM household_migration_plans WHERE household_id=? AND status IN ('planned','in_transit')",(hid,)).fetchone():
        return None
    octx=conn.execute("SELECT * FROM location_commercial_context WHERE location_id=?",(origin,)).fetchone()
    if not octx:
        return None
    candidates=[]
    routes=conn.execute(
        """SELECT * FROM travel_routes WHERE status IN ('open','restricted') AND
           (from_location_id=? OR (bidirectional=1 AND to_location_id=?)) ORDER BY base_days,id""",(origin,origin)
    ).fetchall()
    for r in routes:
        dest=int(r['to_location_id']) if int(r['from_location_id'])==origin else int(r['from_location_id'])
        dctx=conn.execute("SELECT * FROM location_commercial_context WHERE location_id=?",(dest,)).fetchone()
        if not dctx or float(r['reliability'])<40:
            continue
        security_gain=float(dctx['security'])-float(octx['security'])
        trade_gain=float(dctx['trade_flow'])-float(octx['trade_flow'])
        health_gain=float(dctx['health_demand'])-float(octx['health_demand'])
        if security_gain<12 and trade_gain<18 and health_gain<20:
            continue
        score=security_gain*1.2 + trade_gain*0.5 + health_gain*0.25 - float(r['base_days'])*0.5
        candidates.append((score,dest,int(r['id']),security_gain,trade_gain,health_gain))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    score,dest,rid,sg,tg,hg=candidates[0]
    return DomainActionOption(
        'schedule_household_migration',6.2 + min(2.0,max(0.0,score)/25.0),
        'Move a genuinely declining household toward an adjacent node with materially better conditions.',
        payload={'household_id':hid,'destination_location_id':dest,'route_id':rid,'planned_day':day+7,
                 'reason':f'Household decline; destination comparison security {sg:+.1f}, trade {tg:+.1f}, health {hg:+.1f}.'},
    )


def _credit_options(conn: sqlite3.Connection, actor_id: int, day: int) -> list[DomainActionOption]:
    """Service real debt first; otherwise seek a real local lender only for a cash-stressed owned enterprise."""
    out=[]
    owned=conn.execute(
        """SELECT * FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained','insolvent')
           ORDER BY CASE status WHEN 'insolvent' THEN 0 WHEN 'strained' THEN 1 ELSE 2 END,id LIMIT 1""",(actor_id,)
    ).fetchone()
    if not owned:
        return out
    eid=int(owned['id'])
    credit=conn.execute(
        """SELECT * FROM credit_agreements WHERE borrower_enterprise_id=? AND status IN ('current','late')
           ORDER BY CASE status WHEN 'late' THEN 0 ELSE 1 END,COALESCE(due_day,999999999),id LIMIT 1""",(eid,)
    ).fetchone()
    if credit:
        cash=float(owned['cash']); outstanding=float(credit['outstanding'])
        if cash>=2.5 and outstanding>0:
            amount=min(outstanding,max(1.0,min(cash*0.20,8.0)))
            urgency=2.0 if str(credit['status'])=='late' else (1.0 if credit['due_day'] is not None and int(credit['due_day'])<=day+30 else 0.0)
            out.append(DomainActionOption('service_credit',6.0+urgency,
                'Use available enterprise cash to service an existing real credit agreement.',
                payload={'agreement_id':int(credit['id']),'enterprise_id':eid,'amount':amount}))
        return out

    cash=float(owned['cash']); capital=max(1.0,float(owned['capital']))
    stressed=str(owned['status']) in {'strained','insolvent'} or cash < max(3.0,capital*0.12)
    if not stressed or owned['location_id'] is None:
        return out
    loc=int(owned['location_id'])
    need=max(5.0,min(20.0,max(0.0,capital*0.25-cash)))
    lenders=conn.execute(
        """SELECT e.id AS lender_enterprise_id,e.institution_actor_id,e.cash,a.name
           FROM civilian_enterprises e JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id
           JOIN business_archetypes ba ON ba.id=bp.archetype_id
           JOIN actors a ON a.id=e.institution_actor_id
           WHERE e.location_id=? AND e.status='active' AND ba.archetype_key='loan_house'
             AND e.institution_actor_id IS NOT NULL AND e.cash>=? AND a.status='active'
           ORDER BY e.cash DESC,e.id""",(loc,need+2.0)
    ).fetchall()
    if lenders:
        l=lenders[0]
        out.append(DomainActionOption('seek_credit',7.0 if str(owned['status'])!='active' else 6.1,
            f"Seek working-capital credit from {l['name']} because the owned enterprise is genuinely cash-stressed.",
            mode='interaction',target_actor_id=int(l['institution_actor_id']),interaction_type='contract',
            payload={'borrower_enterprise_id':eid,'lender_enterprise_id':int(l['lender_enterprise_id']),
                     'principal':need,'due_day':day+180}))
    return out


def _enterprise_sale_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    """Offer a sole-owned distressed enterprise to a known buyer with explicit transferable capital."""
    row = conn.execute(
        """SELECT * FROM civilian_enterprises
           WHERE owner_actor_id=? AND institution_actor_id IS NULL AND household_id IS NULL
             AND status IN ('strained','insolvent') ORDER BY CASE status WHEN 'insolvent' THEN 0 ELSE 1 END,id LIMIT 1""",
        (actor_id,),
    ).fetchone()
    if not row:
        return None
    loc = row["location_id"]
    if loc is None:
        return None
    book_value = max(5.0, float(row["capital"]) + max(0.0, float(row["cash"])) - max(0.0, float(row["debt"])))
    buyers = conn.execute(
        """SELECT r.actor_b_id buyer_id,r.trust,r.stance
           FROM relationships r JOIN actors b ON b.id=r.actor_b_id
           WHERE r.actor_a_id=? AND b.actor_type='character' AND b.status='active'
             AND b.current_location_id=? AND r.trust>=10 AND r.stance>=0
           ORDER BY (r.trust+r.stance) DESC,r.id""",
        (actor_id, loc),
    ).fetchall()
    for b in buyers:
        buyer = int(b["buyer_id"])
        cap = conn.execute(
            "SELECT id,amount,unit FROM resources WHERE actor_id=? AND resource_type='capital' AND amount>=? ORDER BY id LIMIT 1",
            (buyer, book_value),
        ).fetchone()
        if not cap:
            continue
        return DomainActionOption(
            "sell_enterprise", 7.2 if str(row["status"]) == "insolvent" else 6.2,
            f"Offer the distressed enterprise {row['name']} to {_name(conn, buyer)} at its current book-value basis.",
            mode="interaction", target_actor_id=buyer, interaction_type="contract",
            payload={"enterprise_id": int(row["id"]), "buyer_actor_id": buyer, "price": book_value, "buyer_capital_resource_id": int(cap["id"])},
        )
    return None


def _admit_pupil_option(conn: sqlite3.Connection, institution_actor_id: int, day: int) -> DomainActionOption | None:
    """Offer admission from an existing program to a grounded current-source candidate."""
    if _actor_type(conn, institution_actor_id) != "institution":
        return None
    loc = _current_location(conn, institution_actor_id)
    programs = conn.execute(
        """SELECT p.*,(SELECT COUNT(*) FROM education_enrollments e WHERE e.program_id=p.id AND e.status='active') active_count
           FROM education_programs p WHERE p.institution_actor_id=? AND p.status='active'
           ORDER BY p.id""",
        (institution_actor_id,),
    ).fetchall()
    if not programs:
        return None
    candidates = conn.execute(
        """SELECT a.id FROM actors a
           JOIN source_identity_map sim ON sim.entity_kind='actor' AND sim.entity_id=a.id AND sim.source_namespace='caerness_seed_v1_1'
           WHERE a.actor_type='character' AND a.status='active' AND (? IS NULL OR a.current_location_id=?)
           ORDER BY a.id""",
        (loc, loc),
    ).fetchall()
    for p in programs:
        if int(p["active_count"]) >= int(p["capacity"]):
            continue
        for c in candidates:
            aid = int(c["id"])
            src = _source_payload(conn, aid)
            tr = ((src.get("runtime_v1_1") or {}).get("training_state") or {})
            if not tr.get("active") or _authoritative_stage(conn, aid, src) not in {"First", "Temper"}:
                continue
            if conn.execute("SELECT 1 FROM education_enrollments WHERE actor_id=? AND program_id=? AND status IN ('active','paused','completed')", (aid, int(p["id"]))).fetchone():
                continue
            if _competence(conn, aid, str(p["domain_key"])) < float(p["min_entry_score"]):
                continue
            return DomainActionOption(
                "admit_pupil", 6.4,
                f"Offer {_name(conn, aid)} a place in {p['name']} while real capacity exists.",
                mode="interaction", target_actor_id=aid, interaction_type="offer",
                payload={"program_id": int(p["id"]), "institution_actor_id": institution_actor_id, "student_actor_id": aid},
            )
    return None


def _shipment_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    """Move owned, existing inventory toward a demonstrably stronger market over a real route."""
    typ = _actor_type(conn, actor_id)
    if typ not in {"character", "institution"}:
        return None
    if typ == "character":
        owner_clause = "e.owner_actor_id=?"
    else:
        owner_clause = "e.institution_actor_id=?"
    rows = conn.execute(
        f"""SELECT ps.*,e.location_id AS origin_location_id,e.name AS enterprise_name,e.id AS enterprise_id,
                    mc.current_price AS origin_price
             FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id
             JOIN market_conditions mc ON mc.location_id=e.location_id AND mc.good_id=ps.good_id
             WHERE {owner_clause} AND e.status IN ('active','strained') AND ps.active=1 AND ps.inventory>0.5
             ORDER BY ps.inventory DESC,ps.id""",
        (actor_id,),
    ).fetchall()
    if not rows:
        return None
    from .ecology import find_route_path
    for ps in rows:
        origin = int(ps["origin_location_id"])
        candidates = conn.execute(
            """SELECT mc.location_id,mc.current_price,mc.demand,mc.supply
               FROM market_conditions mc WHERE mc.good_id=? AND mc.location_id<>?
                 AND mc.current_price>=? ORDER BY mc.current_price DESC,mc.demand DESC,mc.location_id""",
            (int(ps["good_id"]), origin, float(ps["origin_price"]) * 1.10),
        ).fetchall()
        for market in candidates:
            dest = int(market["location_id"])
            if not find_route_path(conn, origin, dest, day=day):
                continue
            qty = min(float(ps["inventory"]) * 0.40, max(1.0, float(ps["capacity_per_30"]) * 0.5))
            if qty <= 0.5:
                continue
            spread = float(market["current_price"]) / max(0.01, float(ps["origin_price"])) - 1.0
            return DomainActionOption(
                "arrange_shipment", 6.0 + min(3.0, spread * 8.0),
                f"Dispatch existing {ps['inventory']:.1f}-unit stock from {ps['enterprise_name']} toward a stronger connected market.",
                payload={"enterprise_id":int(ps["enterprise_id"]), "source_production_site_id":int(ps["id"]),
                         "quantity":qty, "destination_location_id":dest},
            )
    return None

def _instructor_option(conn: sqlite3.Connection, institution_actor_id: int, day: int) -> DomainActionOption | None:
    if _actor_type(conn, institution_actor_id) != "institution":
        return None
    rp = conn.execute("SELECT * FROM institution_reproduction_profiles WHERE institution_actor_id=?", (institution_actor_id,)).fetchone()
    if not rp:
        return None
    if float(rp["instructor_depth"]) >= 40 and float(rp["continuity_pressure"]) < 55:
        return None
    loc = _current_location(conn, institution_actor_id)
    candidates = conn.execute(
        """SELECT a.id,MAX(ac.score) score FROM actors a
           JOIN actor_competence ac ON ac.actor_id=a.id JOIN competence_domains d ON d.id=ac.domain_id
           WHERE a.actor_type='character' AND a.status='active' AND d.domain_key='martial_instruction'
             AND (? IS NULL OR a.current_location_id=?)
           GROUP BY a.id HAVING MAX(ac.score)>=60 ORDER BY score DESC,a.id""",
        (loc, loc),
    ).fetchall()
    for c in candidates:
        aid = int(c["id"])
        if conn.execute(
            """SELECT 1 FROM professional_memberships WHERE actor_id=? AND institution_actor_id=?
               AND profession_domain='martial_instruction' AND status='active' LIMIT 1""",
            (aid, institution_actor_id),
        ).fetchone():
            continue
        return DomainActionOption(
            "hire_instructor", 7.0 + float(rp["continuity_pressure"]) / 30.0,
            f"Recruit {_name(conn, aid)} into an instructor role because teaching depth is under pressure.",
            mode="interaction", target_actor_id=aid, interaction_type="offer",
            payload={"institution_actor_id": institution_actor_id, "teacher_actor_id": aid},
        )
    return None



def _martial_challenge_option(conn: sqlite3.Connection, actor_id: int, day: int) -> DomainActionOption | None:
    """Offer a controlled challenge only from existing sustained local tension; refusal remains valid."""
    cp=conn.execute("SELECT core_state,active,status FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if not cp or cp['core_state']!='Open-Core' or not int(cp['active']) or cp['status']!='active': return None
    loc=_current_location(conn,actor_id)
    if loc is None:return None
    if conn.execute("SELECT 1 FROM combat_engagements ce JOIN duel_combatants dc ON dc.engagement_id=ce.id WHERE dc.actor_id=? AND ce.status='active' LIMIT 1",(actor_id,)).fetchone():return None
    rows=conn.execute("""SELECT r.*,r.actor_b_id opponent_id
        FROM relationships r JOIN actors o ON o.id=r.actor_b_id
        JOIN cultivation_profiles cp ON cp.actor_id=o.id
        WHERE r.actor_a_id=? AND o.actor_type='character' AND o.status='active' AND o.current_location_id=?
          AND cp.core_state='Open-Core' AND cp.active=1 AND cp.status='active' AND r.stance<=-25 AND r.updated_day<=?
        ORDER BY r.stance ASC,r.trust ASC,r.id LIMIT 5""",(actor_id,loc,day-30)).fetchall()
    for r in rows:
        opp=int(r['opponent_id'])
        if conn.execute("SELECT 1 FROM combat_engagements ce JOIN duel_combatants dc ON dc.engagement_id=ce.id WHERE dc.actor_id=? AND ce.status='active' LIMIT 1",(opp,)).fetchone():continue
        if conn.execute("SELECT 1 FROM interactions WHERE status='pending' AND ((proposer_actor_id=? AND recipient_actor_id=?) OR (proposer_actor_id=? AND recipient_actor_id=?)) AND terms_json LIKE '%propose_martial_challenge%' LIMIT 1",(actor_id,opp,opp,actor_id)).fetchone():continue
        return DomainActionOption('propose_martial_challenge',6.0+min(2.0,abs(float(r['stance']))/40.0),
            f"Offer {_name(conn,opp)} a controlled witnessed martial challenge arising from an existing local rivalry; refusal carries no automatic cowardice rule.",
            mode='interaction',target_actor_id=opp,interaction_type='offer',payload={'opponent_actor_id':opp,'location_id':loc,'terms_kind':'controlled','lethal':False})
    return None

def domain_action_options(
    conn: sqlite3.Connection,
    actor_id: int,
    tier: str,
    day: int,
    *,
    context: dict[str, Any] | None = None,
    drives: dict[str, float] | None = None,
) -> list[DomainActionOption]:
    drives = drives or {"ambition": 0.5, "risk_tolerance": 0.5, "patience": 0.5, "pragmatism": 0.5}
    typ = _actor_type(conn, actor_id)
    if typ is None:
        return []
    out: list[DomainActionOption] = []
    if typ == "character":
        out.extend(_training_options(conn, actor_id, tier, day, drives))
        t = _treatment_option(conn, actor_id, day)
        if t: out.append(t)
        u = _union_option(conn, actor_id, day)
        if u: out.append(u)
        b = _business_option(conn, actor_id, day, drives)
        if b: out.append(b)
        w = _work_option(conn, actor_id, day)
        if w: out.append(w)
        service = _household_service_option(conn, actor_id, day)
        if service: out.append(service)
        migration = _household_migration_option(conn, actor_id, day)
        if migration: out.append(migration)
        o = _obligation_option(conn, actor_id, day)
        if o: out.append(o)
        out.extend(_credit_options(conn, actor_id, day))
        challenge=_martial_challenge_option(conn,actor_id,day)
        if challenge: out.append(challenge)
        sale = _enterprise_sale_option(conn, actor_id, day)
        if sale: out.append(sale)
        shipment = _shipment_option(conn, actor_id, day)
        if shipment: out.append(shipment)
    elif typ == "institution":
        i = _instructor_option(conn, actor_id, day)
        if i: out.append(i)
        pupil = _admit_pupil_option(conn, actor_id, day)
        if pupil: out.append(pupil)
        shipment = _shipment_option(conn, actor_id, day)
        if shipment: out.append(shipment)
    return out


def _create_domain_interaction(conn: sqlite3.Connection, actor_id: int, option: DomainActionOption, day: int, canon_chunk_ids: tuple[int, ...] = ()) -> dict[str, Any]:
    from .interactions import create_interaction
    if option.target_actor_id is None or option.interaction_type is None:
        raise ValueError("Interaction domain action requires a target and interaction type")
    terms = {
        "purpose": option.rationale,
        "domain_action": {"kind": option.kind, "payload": option.payload or {}, "initiator_actor_id": actor_id},
        "incentive": 0.2,
        "burden": 0.15,
    }
    iid = create_interaction(
        conn, actor_id, option.target_actor_id, option.interaction_type, day,
        urgency=2, stakes=2 if option.kind not in {"propose_union"} else 3,
        terms=terms, rationale=option.rationale, canon_chunk_ids=canon_chunk_ids,
    )
    attempt = _log_attempt(
        conn, actor_id, option.kind, _domain_for(option.kind), "eligible",
        institution_actor_id=(actor_id if _actor_type(conn, actor_id) == "institution" else (option.payload or {}).get("institution_actor_id")),
        reason="proposal created; authoritative mutation waits for recipient response",
        inputs=option.payload or {}, result={"interaction_id": iid}, day=day,
    )
    return {"summary": f"Created domain interaction #{iid}: {option.kind}.", "interaction_id": iid, "attempt_id": attempt}


def _domain_for(kind: str) -> str:
    if kind in {"adjust_training_effort", "resume_training", "seek_training", "hire_instructor", "admit_pupil", "seek_personal_instruction"}: return "education"
    if kind in {"seek_treatment"}: return "health"
    if kind in {"propose_union", "seek_household_service", "schedule_household_migration"}: return "household"
    if kind in {"found_enterprise", "sell_enterprise", "seek_work", "seek_direct_procurement", "seek_provider_service"}: return "business"
    if kind in {"accept_institutional_appointment", "accept_opportunity_proposal"}: return "institutional_service"
    if kind in {"renegotiate_obligation"}: return "obligations"
    if kind in {"seek_credit", "service_credit"}: return "credit"
    if kind in {"arrange_shipment"}: return "logistics"
    if kind in {"propose_martial_challenge"}: return "combat"
    return "cross_system"


def execute_domain_action(
    conn: sqlite3.Connection,
    actor_id: int,
    option: DomainActionOption,
    day: int,
    *,
    canon_chunk_ids: tuple[int, ...] = (),
) -> dict[str, Any]:
    if option.mode == "interaction":
        return _create_domain_interaction(conn, actor_id, option, day, canon_chunk_ids)

    payload = option.payload or {}
    kind = option.kind
    try:
        if kind == "adjust_training_effort":
            eid = int(payload["enrollment_id"])
            row = conn.execute("SELECT * FROM education_enrollments WHERE id=? AND actor_id=? AND status='active'", (eid, actor_id)).fetchone()
            if not row:
                raise ValueError("active enrollment no longer exists")
            drives_row = conn.execute("SELECT ambition,patience,risk_tolerance FROM actor_drives WHERE actor_id=?", (actor_id,)).fetchone()
            ambition = float(drives_row[0]) if drives_row else 0.5
            patience = float(drives_row[1]) if drives_row else 0.5
            risk = float(drives_row[2]) if drives_row else 0.5
            rng = _rng(conn, actor_id, day, eid)
            target = max(0.70, min(1.30, 0.82 + 0.24 * ambition + 0.18 * patience - 0.06 * risk + rng.uniform(-0.06, 0.06)))
            prior = float(row["practice_quality"])
            applied = prior + (target - prior) * 0.35
            conn.execute("UPDATE education_enrollments SET practice_quality=? WHERE id=?", (applied, eid))
            result = {"enrollment_id": eid, "practice_quality_before": prior, "practice_quality_after": applied}
            aid = _log_attempt(conn, actor_id, kind, "education", "applied", inputs=payload, result=result, day=day)
            return {"summary": f"Training effort changed from {prior:.2f} to {applied:.2f}.", "attempt_id": aid, **result}

        if kind == "resume_training":
            from .education import resume_enrollment
            eid = int(payload["enrollment_id"])
            resume_enrollment(conn, eid)
            result = {"enrollment_id": eid}
            aid = _log_attempt(conn, actor_id, kind, "education", "applied", inputs=payload, result=result, day=day)
            return {"summary": f"Resumed enrollment #{eid}.", "attempt_id": aid, **result}

        if kind == "found_enterprise":
            from .business import configure_enterprise_business
            from .civilian import create_enterprise
            archetype = str(payload["archetype_key"])
            loc = int(payload["location_id"])
            commitment = max(0.0, float(payload["capital_commitment"]))
            available = _resource(conn, actor_id, "capital", "operating_reserve", "savings")
            if available + 1e-9 < commitment or commitment < 10:
                raise ValueError("capital no longer available")
            # Spend in deterministic resource-type order without inventing a currency conversion.
            remaining = commitment
            for key in ("capital", "operating_reserve", "savings"):
                r = conn.execute("SELECT id,amount FROM resources WHERE actor_id=? AND resource_type=?", (actor_id, key)).fetchone()
                if not r or remaining <= 0: continue
                take = min(remaining, float(r["amount"]))
                conn.execute("UPDATE resources SET amount=amount-?,updated_day=? WHERE id=?", (take, day, int(r["id"])))
                remaining -= take
            name = f"Working concern of {_name(conn, actor_id)}"
            eid = create_enterprise(
                conn, name, "other", owner_actor_id=actor_id, location_id=loc,
                capital=commitment, cash=commitment * 0.45, debt=0, reputation=30,
                admin_quality=max(35.0, _competence(conn, actor_id, "commerce")), labor_capacity=35,
                risk_tolerance=45,
                metadata={"authority":"ENGINE_DERIVED", "formation_day":day, "working_name":True, "founding_action":"autonomous_domain_action"},
            )
            configure_enterprise_business(conn, eid, archetype, quality=45, capacity=35, clientele_fit=40, service_reliability=45,
                                          regulatory_pressure=10, cadence_days=30,
                                          metadata={"authority":"ENGINE_DERIVED", "founder_actor_id":actor_id})
            result = {"enterprise_id": eid, "archetype_key": archetype, "capital_committed": commitment}
            aid = _log_attempt(conn, actor_id, kind, "business", "applied", inputs=payload, result=result, day=day)
            return {"summary": f"Founded enterprise #{eid} as a {archetype.replace('_',' ')}.", "attempt_id": aid, **result}

        if kind == "schedule_household_migration":
            from .household_life import schedule_household_migration
            hid=int(payload['household_id'])
            h=conn.execute("SELECT head_actor_id,status,metadata_json FROM households WHERE id=?",(hid,)).fetchone()
            if not h or h['head_actor_id'] is None or int(h['head_actor_id'])!=actor_id or str(h['status'])!='declining':
                raise ValueError('actor no longer heads a declining household')
            meta=_loads(h['metadata_json'],{})
            if meta.get('economic_resolution')=='STRUCTURAL_ONLY' or meta.get('economic_state')=='NOT_SEPARATELY_QUANTIFIED':
                raise ValueError('structural-only household cannot receive invented migration pressure')
            mid=schedule_household_migration(conn,hid,int(payload['destination_location_id']),int(payload['planned_day']),reason=str(payload.get('reason') or 'household relocation'))
            result={'migration_plan_id':mid,'household_id':hid,'destination_location_id':int(payload['destination_location_id'])}
            aid=_log_attempt(conn,actor_id,kind,'household','applied',inputs=payload,result=result,day=day)
            return {'summary':f"Scheduled household migration #{mid}.",'attempt_id':aid,**result}

        if kind == "service_credit":
            from .civilian_life import make_credit_payment
            agreement_id=int(payload['agreement_id']); amount=float(payload['amount'])
            row=conn.execute("SELECT c.borrower_enterprise_id,e.owner_actor_id,e.cash FROM credit_agreements c JOIN civilian_enterprises e ON e.id=c.borrower_enterprise_id WHERE c.id=? AND c.status IN ('current','late')",(agreement_id,)).fetchone()
            if not row or row['owner_actor_id'] is None or int(row['owner_actor_id'])!=actor_id or float(row['cash'])+1e-9<amount:
                raise ValueError('credit payment no longer matches owned enterprise/cash')
            outstanding=make_credit_payment(conn,agreement_id,amount)
            result={'agreement_id':agreement_id,'amount':amount,'outstanding':outstanding}
            aid=_log_attempt(conn,actor_id,kind,'credit','applied',inputs=payload,result=result,day=day)
            return {'summary':f"Paid {amount:.2f} toward credit agreement #{agreement_id}.",'attempt_id':aid,**result}

        if kind == "arrange_shipment":
            from .logistics import arrange_shipment
            sid = arrange_shipment(
                conn, int(payload["enterprise_id"]), int(payload["source_production_site_id"]),
                float(payload["quantity"]), int(payload["destination_location_id"]),
                metadata={"autonomous_actor_id":actor_id, "decision_day":day},
            )
            result = {"shipment_id":sid, "enterprise_id":int(payload["enterprise_id"]),
                      "quantity":float(payload["quantity"]), "destination_location_id":int(payload["destination_location_id"])}
            aid = _log_attempt(conn, actor_id, kind, "logistics", "applied", inputs=payload, result=result, day=day)
            return {"summary": f"Dispatched commercial shipment #{sid}.", "attempt_id": aid, **result}

        raise ValueError(f"Unsupported direct domain action: {kind}")
    except Exception as exc:
        aid = _log_attempt(conn, actor_id, kind, _domain_for(kind), "blocked", reason=str(exc), inputs=payload, day=day)
        return {"summary": f"Domain action blocked: {exc}", "attempt_id": aid, "blocked": True}


def apply_accepted_interaction_domain_action(conn: sqlite3.Connection, interaction: sqlite3.Row, day: int) -> dict[str, Any] | None:
    terms = _loads(interaction["terms_json"], {})
    spec = terms.get("domain_action")
    if not isinstance(spec, dict):
        return None
    kind = str(spec.get("kind") or "")
    payload = spec.get("payload") if isinstance(spec.get("payload"), dict) else {}
    initiator = int(spec.get("initiator_actor_id") or interaction["proposer_actor_id"])
    recipient = int(interaction["recipient_actor_id"])
    domain = _domain_for(kind)
    try:
        if kind == "seek_training":
            from .education import enroll
            pid = int(payload["program_id"])
            p = conn.execute("SELECT institution_actor_id,min_teacher_score,domain_key FROM education_programs WHERE id=? AND status='active'", (pid,)).fetchone()
            if not p or p["institution_actor_id"] is None or int(p["institution_actor_id"]) != recipient:
                raise ValueError("program/institution no longer matches accepted request")
            teacher = None
            if float(p["min_teacher_score"]) > 0:
                teacher_row = conn.execute(
                    """SELECT tr.teacher_actor_id FROM teaching_relationships tr JOIN actors a ON a.id=tr.teacher_actor_id
                       WHERE tr.institution_actor_id=? AND tr.domain_key=? AND tr.status='active' AND a.status='active'
                       ORDER BY tr.responsibility DESC,tr.id LIMIT 1""",
                    (recipient, str(p["domain_key"])),
                ).fetchone()
                teacher = int(teacher_row[0]) if teacher_row else None
            eid = enroll(conn, initiator, pid, primary_teacher_actor_id=teacher, practice_quality=1.0,
                         metadata={"authority":"ENGINE_DERIVED", "accepted_interaction_id":int(interaction["id"])})
            result = {"enrollment_id": eid, "program_id": pid}

        elif kind == "seek_personal_instruction":
            from .education import enroll, create_teaching_relationship
            from .seeking import mark_intent_fulfilled
            pid = int(payload["program_id"])
            offering_id = int(payload["offering_id"])
            teacher = int(payload.get("teacher_actor_id") or recipient)
            if teacher != recipient:
                raise ValueError("accepted teacher does not match offering")
            off = conn.execute("SELECT * FROM seekable_offerings WHERE id=? AND provider_actor_id=? AND offer_kind='instruction' AND status='active'", (offering_id, teacher)).fetchone()
            if not off:
                raise ValueError("instruction offering is no longer available")
            p = conn.execute("SELECT * FROM education_programs WHERE id=? AND status='active'", (pid,)).fetchone()
            if not p:
                raise ValueError("personal instruction program is no longer active")
            meta = _loads(p["metadata_json"], {})
            if int(meta.get("personal_teacher_actor_id") or 0) != teacher:
                raise ValueError("program no longer belongs to accepted teacher")
            eid = enroll(conn, initiator, pid, primary_teacher_actor_id=teacher, practice_quality=1.0,
                         metadata={"authority":"ENGINE_DERIVED", "accepted_interaction_id":int(interaction["id"]), "seek_offering_id":offering_id})
            try:
                trid = create_teaching_relationship(conn, teacher, initiator, "personal_master", str(p["domain_key"]), responsibility=85,
                                                    notes=f"Began after seeker approach interaction {int(interaction['id'])}.")
            except sqlite3.IntegrityError:
                tr = conn.execute("SELECT id FROM teaching_relationships WHERE teacher_actor_id=? AND student_actor_id=? AND relation_kind='personal_master' AND domain_key=? AND status='active'", (teacher, initiator, str(p["domain_key"]))).fetchone()
                trid = int(tr[0]) if tr else None
            seek_intent_id = int(terms.get("seek_intent_id") or 0)
            if seek_intent_id:
                mark_intent_fulfilled(conn, seek_intent_id, detail={"kind":"personal_instruction","teacher_actor_id":teacher,"enrollment_id":eid,"teaching_relationship_id":trid})
            result = {"enrollment_id":eid,"teaching_relationship_id":trid,"teacher_actor_id":teacher,"offering_id":offering_id}

        elif kind == "seek_direct_procurement":
            from .seeking import mark_intent_fulfilled
            from .logistics import arrange_shipment, arrange_stock_shipment
            offering_id=int(payload["offering_id"]); seller_eid=int(payload["seller_enterprise_id"]); good_id=int(payload["good_id"]); qty=float(payload["quantity"])
            off=conn.execute("SELECT * FROM seekable_offerings WHERE id=? AND provider_actor_id=? AND provider_enterprise_id=? AND offer_kind='goods' AND status='active'",(offering_id,recipient,seller_eid)).fetchone()
            ent=conn.execute("SELECT * FROM civilian_enterprises WHERE id=? AND status IN ('active','strained')",(seller_eid,)).fetchone()
            good=conn.execute("SELECT * FROM market_goods WHERE id=?",(good_id,)).fetchone()
            if not off or not ent or not good or qty<=0:
                raise ValueError("procurement offering is no longer feasible")
            if ent["location_id"] is None:
                raise ValueError("seller has no shipping origin")
            source_site=conn.execute("SELECT * FROM production_sites WHERE enterprise_id=? AND good_id=? AND active=1 AND inventory>=? ORDER BY inventory DESC,id LIMIT 1",(seller_eid,good_id,qty)).fetchone()
            source_stock=conn.execute("SELECT * FROM commercial_stock WHERE enterprise_id=? AND good_id=? AND quantity>=? ORDER BY quantity DESC,id LIMIT 1",(seller_eid,good_id,qty)).fetchone() if source_site is None else None
            if source_site is None and source_stock is None:
                raise ValueError("seller no longer has enough real stock for the procurement")
            seek_intent_id=int(terms.get("seek_intent_id") or 0)
            imeta={}
            if seek_intent_id:
                ir=conn.execute("SELECT metadata_json,preferred_location_id FROM actor_seek_intents WHERE id=?",(seek_intent_id,)).fetchone()
                if ir: imeta=_loads(ir["metadata_json"],{})
            buyer_polity_id=imeta.get("buyer_polity_id")
            destination=_current_location(conn,initiator)
            if seek_intent_id:
                ir=conn.execute("SELECT preferred_location_id FROM actor_seek_intents WHERE id=?",(seek_intent_id,)).fetchone()
                if ir and ir[0] is not None: destination=int(ir[0])
            if destination is None:
                raise ValueError("buyer has no delivery location")
            quality=float(off["quality"]); unit_price=float(good["base_price"])*(0.72+quality/100.0*.78); due=day+max(30,int(math.ceil(qty/max(.1,float(off["capacity_per_30"]))))*30)
            cur=conn.execute("""INSERT INTO seek_procurement_contracts(intent_id,offering_id,buyer_actor_id,buyer_polity_id,seller_actor_id,seller_enterprise_id,good_id,quantity,unit_price,agreed_quality,origin_location_id,destination_location_id,agreed_day,due_day,status,metadata_json)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'accepted',?)""",
                             (seek_intent_id or None,offering_id,initiator,int(buyer_polity_id) if buyer_polity_id is not None else None,recipient,seller_eid,good_id,qty,unit_price,quality,int(ent["location_id"]),destination,day,due,json.dumps({"accepted_interaction_id":int(interaction["id"])},sort_keys=True)))
            cid=int(cur.lastrowid); shipment_id=None
            if int(ent["location_id"])==int(destination):
                if source_site is not None:
                    conn.execute("UPDATE production_sites SET inventory=inventory-? WHERE id=?",(qty,int(source_site["id"])))
                else:
                    conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?",(qty,day,int(source_stock["id"])))
                total=qty*unit_price
                conn.execute("UPDATE civilian_enterprises SET cash=cash+?,reputation=MIN(100,reputation+?),updated_day=? WHERE id=?",(total,min(2.5,qty*.08),day,seller_eid))
                conn.execute("UPDATE seek_procurement_contracts SET status='fulfilled',fulfilled_day=? WHERE id=?",(day,cid))
                if buyer_polity_id is not None and str(good["good_key"])=='horses_remounts':
                    bump=min(8.0,qty*.22*(.65+quality/100.0*.5))
                    conn.execute("UPDATE military_logistics_profiles SET transport_capacity=MIN(100,transport_capacity+?),readiness=MIN(100,readiness+?),next_review_day=MIN(next_review_day,?) WHERE polity_id=?",(bump,bump*.35,day+1,int(buyer_polity_id)))
                    conn.execute("UPDATE political_polities SET treasury_pressure=MIN(100,treasury_pressure+?) WHERE id=?",(min(5.0,total/450.0),int(buyer_polity_id)))
                if seek_intent_id: mark_intent_fulfilled(conn,seek_intent_id,detail={"kind":"procurement","contract_id":cid,"quantity":qty,"good_id":good_id})
            else:
                meta={"seek_procurement_contract_id":cid,"buyer_polity_id":buyer_polity_id,"agreed_quality":quality,"seek_intent_id":seek_intent_id}
                if source_site is not None:
                    shipment_id=arrange_shipment(conn,seller_eid,int(source_site["id"]),qty,destination,metadata=meta)
                else:
                    shipment_id=arrange_stock_shipment(conn,seller_eid,int(source_stock["id"]),qty,destination,metadata=meta)
                conn.execute("UPDATE seek_procurement_contracts SET shipment_id=?,status='in_transit' WHERE id=?",(shipment_id,cid))
            result={"procurement_contract_id":cid,"shipment_id":shipment_id,"seller_enterprise_id":seller_eid,"quantity":qty,"good_id":good_id}

        elif kind == "accept_institutional_appointment":
            from .attention import accept_institutional_appointment
            case_id = int(payload["attention_case_id"])
            result = accept_institutional_appointment(conn, case_id, recipient, int(interaction["id"]), day)

        elif kind == "accept_opportunity_proposal":
            from .opportunity import accept_proposal
            proposal_id = int(payload["proposal_id"])
            result = accept_proposal(conn, proposal_id, recipient, int(interaction["id"]), day=day)

        elif kind == "seek_provider_service":
            from .seeking import mark_intent_fulfilled
            offering_id=int(payload["offering_id"])
            off=conn.execute("SELECT * FROM seekable_offerings WHERE id=? AND provider_actor_id=? AND status='active'",(offering_id,recipient)).fetchone()
            if not off: raise ValueError("provider service is no longer available")
            seek_intent_id=int(terms.get("seek_intent_id") or 0)
            if seek_intent_id: mark_intent_fulfilled(conn,seek_intent_id,detail={"kind":"service_agreement","offering_id":offering_id,"provider_actor_id":recipient})
            result={"offering_id":offering_id,"provider_actor_id":recipient}

        elif kind == "seek_treatment":
            from .health import add_treatment
            cid = int(payload["condition_id"])
            treatment_kind = str(payload.get("treatment_kind") or "ordinary_medicine")
            tid = add_treatment(conn, initiator, treatment_kind, condition_id=cid, provider_actor_id=recipient,
                                quality=55, adherence=70,
                                metadata={"authority":"ENGINE_DERIVED", "accepted_interaction_id":int(interaction["id"])})
            result = {"treatment_id": tid, "condition_id": cid, "provider_actor_id": recipient}

        elif kind == "propose_union":
            from .household_life import create_union
            partner = int(payload.get("partner_actor_id") or recipient)
            if partner != recipient:
                raise ValueError("accepted recipient does not match proposed partner")
            household_name = f"Household of {_name(conn, initiator)} and {_name(conn, partner)}"
            uid = create_union(conn, initiator, partner, union_kind=str(payload.get("union_kind") or "marriage"),
                               create_new_household_name=household_name)
            # Whether this couple later has children is a trajectory, not a reward flag.
            # FAMILY-02 requires a resolved biological pair before auto-birth can ever be scheduled.
            from .household_life import resolved_biological_birth_parent
            h=(min(initiator,partner)*73 + max(initiator,partner)*41 + day*7)
            birth_parent=resolved_biological_birth_parent(conn,initiator,partner)
            family_plan={
                "mode":"ENGINE_DERIVED_OPEN_FAMILY_CONTINUITY",
                "auto_children": bool(birth_parent is not None and h % 100 < 62),
                "desired_children": 1 + (h % 3),
                "spacing_days": 730 + (h % 366),
                "earliest_next_child_day": day + 365 + (h % 365),
                "birth_parent_actor_id": birth_parent,
                "authority":"CAMPAIGN_CALIBRATION_NOT_CANON_DESTINY",
                "family02_reproductive_state":"resolved" if birth_parent is not None else "unresolved_no_auto_birth",
            }
            conn.execute("UPDATE household_unions SET family_plan_json=?,metadata_json=? WHERE id=?",
                         (json.dumps(family_plan,sort_keys=True),json.dumps({"authority":"ENGINE_DERIVED", "accepted_interaction_id":int(interaction["id"])}, sort_keys=True), uid))
            result = {"union_id": uid, "partner_actor_id": partner}

        elif kind == "seek_work":
            from .civilian import start_career
            track_id = int(payload["track_id"])
            inst = int(payload.get("institution_actor_id") or recipient)
            if inst != recipient:
                raise ValueError("accepted employer does not match work request")
            track = conn.execute("SELECT institution_kind FROM career_tracks WHERE id=?", (track_id,)).fetchone()
            ip = conn.execute("SELECT institution_kind FROM institution_profiles WHERE actor_id=?", (inst,)).fetchone()
            if not track or not ip or str(track[0]) != str(ip[0]):
                raise ValueError("career track no longer matches employer type")
            if conn.execute("SELECT 1 FROM actor_careers WHERE actor_id=? AND status='active' LIMIT 1", (initiator,)).fetchone():
                raise ValueError("actor already has an active career")
            cid = start_career(conn, initiator, track_id, institution_actor_id=inst)
            result = {"career_id": cid, "track_id": track_id, "institution_actor_id": inst}

        elif kind == "seek_household_service":
            from .household_life import add_service_term
            hid=int(payload['household_id'])
            h=conn.execute("SELECT * FROM households WHERE id=? AND status='active'",(hid,)).fetchone()
            if not h or h['head_actor_id'] is None or int(h['head_actor_id'])!=recipient:
                raise ValueError('accepted household head no longer matches service request')
            meta=_loads(h['metadata_json'],{})
            if meta.get('economic_resolution')=='STRUCTURAL_ONLY' or meta.get('economic_state')=='NOT_SEPARATELY_QUANTIFIED':
                raise ValueError('household finances remain structural-only')
            if float(h['liquidity'])<5 or float(h['wealth'])<=0:
                raise ValueError('household no longer has resolved means for service')
            sid=add_service_term(conn,hid,initiator,str(payload.get('service_role') or 'servant'),review_in_days=365,loyalty=50,satisfaction=55,renewal_bias=50)
            result={'service_term_id':sid,'household_id':hid,'actor_id':initiator}

        elif kind == "seek_credit":
            from .civilian_life import create_credit_agreement
            borrower=int(payload['borrower_enterprise_id']); lender=int(payload['lender_enterprise_id']); principal=float(payload['principal'])
            be=conn.execute("SELECT owner_actor_id,status,cash,capital FROM civilian_enterprises WHERE id=?",(borrower,)).fetchone()
            le=conn.execute("SELECT institution_actor_id,status,cash FROM civilian_enterprises WHERE id=?",(lender,)).fetchone()
            if not be or be['owner_actor_id'] is None or int(be['owner_actor_id'])!=initiator or str(be['status']) not in {'active','strained','insolvent'}:
                raise ValueError('borrower enterprise no longer belongs to requester')
            if not le or le['institution_actor_id'] is None or int(le['institution_actor_id'])!=recipient or str(le['status'])!='active' or float(le['cash'])+1e-9<principal:
                raise ValueError('accepted lender no longer has the matching enterprise/cash')
            if conn.execute("SELECT 1 FROM credit_agreements WHERE borrower_enterprise_id=? AND status IN ('current','late')",(borrower,)).fetchone():
                raise ValueError('borrower already has unresolved credit')
            lender_name=_name(conn,recipient)
            rate=0.05 if lender_name=='Counting House' else 0.03
            risk=60 if str(be['status'])=='insolvent' else 45 if str(be['status'])=='strained' else 30
            cid=create_credit_agreement(conn,principal=principal,lender_enterprise_id=lender,borrower_enterprise_id=borrower,
                                        interest_rate_per_30=rate,due_day=int(payload.get('due_day') or day+180),risk=risk,
                                        metadata={'authority':'ENGINE_DERIVED','accepted_interaction_id':int(interaction['id']),'terms_status':'CAMPAIGN_CALIBRATION'})
            result={'credit_agreement_id':cid,'borrower_enterprise_id':borrower,'lender_enterprise_id':lender,'principal':principal}

        elif kind == "propose_martial_challenge":
            from .tournaments import create_accepted_challenge
            opp=int(payload.get('opponent_actor_id') or recipient); loc=int(payload['location_id'])
            if opp!=recipient:
                raise ValueError('accepted challenge opponent mismatch')
            pa=conn.execute("SELECT current_location_id,status FROM actors WHERE id=?",(initiator,)).fetchone(); pb=conn.execute("SELECT current_location_id,status FROM actors WHERE id=?",(recipient,)).fetchone()
            if not pa or not pb or pa['status']!='active' or pb['status']!='active' or pa['current_location_id'] is None or pb['current_location_id'] is None or int(pa['current_location_id'])!=loc or int(pb['current_location_id'])!=loc:
                raise ValueError('challenge participants are no longer together at the accepted location')
            terms=str(payload.get('terms_kind') or 'controlled')
            if terms=='lethal' and not bool(payload.get('lethal')):
                raise ValueError('lethal challenge requires explicit lethal terms')
            result=create_accepted_challenge(conn,initiator,recipient,loc,day,interaction_id=int(interaction['id']),terms_kind=terms)

        elif kind == "renegotiate_obligation":
            oid = int(payload["obligation_id"])
            row = conn.execute("SELECT * FROM obligations WHERE id=? AND actor_id=? AND status='active'", (oid, initiator)).fetchone()
            if not row or row["counterparty_actor_id"] is None or int(row["counterparty_actor_id"]) != recipient:
                raise ValueError("active obligation/counterparty no longer matches negotiation")
            proposed = int(payload["proposed_due_day"])
            if row["due_day"] is None or proposed <= int(row["due_day"]):
                raise ValueError("renegotiated due date must extend the existing obligation")
            note = f"Renegotiated through accepted interaction {int(interaction['id'])} on day {day}."
            conn.execute("UPDATE obligations SET due_day=?,updated_day=?,notes=CASE WHEN notes IS NULL OR notes='' THEN ? ELSE notes || ' ' || ? END WHERE id=?",
                         (proposed, day, note, note, oid))
            result = {"obligation_id": oid, "prior_due_day": int(row["due_day"]), "new_due_day": proposed}

        elif kind == "sell_enterprise":
            eid = int(payload["enterprise_id"])
            buyer = int(payload.get("buyer_actor_id") or recipient)
            price = float(payload["price"])
            if buyer != recipient or price <= 0:
                raise ValueError("accepted buyer/price does not match sale offer")
            ent = conn.execute("SELECT * FROM civilian_enterprises WHERE id=? AND owner_actor_id=? AND status IN ('strained','insolvent')", (eid, initiator)).fetchone()
            if not ent:
                raise ValueError("seller no longer owns a distressed enterprise eligible for sale")
            br = conn.execute("SELECT id,amount,unit FROM resources WHERE id=? AND actor_id=? AND resource_type='capital'", (int(payload["buyer_capital_resource_id"]), buyer)).fetchone()
            if not br or float(br["amount"]) + 1e-9 < price:
                raise ValueError("buyer capital is no longer sufficient")
            conn.execute("UPDATE resources SET amount=amount-?,updated_day=? WHERE id=?", (price, day, int(br["id"])))
            seller_cap = conn.execute("SELECT id FROM resources WHERE actor_id=? AND resource_type='capital'", (initiator,)).fetchone()
            if seller_cap:
                conn.execute("UPDATE resources SET amount=amount+?,updated_day=? WHERE id=?", (price, day, int(seller_cap["id"])))
            else:
                conn.execute("INSERT INTO resources(actor_id,resource_type,amount,unit,updated_day) VALUES (?,'capital',?,?,?)", (initiator, price, br["unit"], day))
            meta = _loads(ent["metadata_json"], {})
            hist = list(meta.get("ownership_history") or [])
            hist.append({"day": day, "from_actor_id": initiator, "to_actor_id": buyer, "price": price, "interaction_id": int(interaction["id"])})
            meta["ownership_history"] = hist
            meta["authority"] = meta.get("authority", "ENGINE_DERIVED")
            conn.execute("UPDATE civilian_enterprises SET owner_actor_id=?,updated_day=?,metadata_json=? WHERE id=?", (buyer, day, json.dumps(meta, sort_keys=True), eid))
            result = {"enterprise_id": eid, "seller_actor_id": initiator, "buyer_actor_id": buyer, "price": price}

        elif kind == "admit_pupil":
            from .education import enroll
            pid = int(payload["program_id"])
            inst = int(payload.get("institution_actor_id") or initiator)
            student = int(payload.get("student_actor_id") or recipient)
            if inst != initiator or student != recipient:
                raise ValueError("accepted parties do not match admission offer")
            p = conn.execute("SELECT * FROM education_programs WHERE id=? AND institution_actor_id=? AND status='active'", (pid, inst)).fetchone()
            if not p:
                raise ValueError("program no longer available")
            active_count = int(conn.execute("SELECT COUNT(*) FROM education_enrollments WHERE program_id=? AND status='active'", (pid,)).fetchone()[0])
            if active_count >= int(p["capacity"]):
                raise ValueError("program capacity is full")
            if conn.execute("SELECT 1 FROM education_enrollments WHERE actor_id=? AND program_id=? AND status IN ('active','paused','completed')", (student, pid)).fetchone():
                raise ValueError("student already has this program history")
            eid = enroll(conn, student, pid, practice_quality=1.0, metadata={"authority":"ENGINE_DERIVED", "accepted_interaction_id":int(interaction["id"])})
            result = {"enrollment_id": eid, "program_id": pid, "student_actor_id": student, "institution_actor_id": inst}

        elif kind == "hire_instructor":
            from .civilian_life import create_professional_membership
            inst = int(payload.get("institution_actor_id") or initiator)
            teacher = int(payload.get("teacher_actor_id") or recipient)
            if inst != initiator or teacher != recipient:
                raise ValueError("accepted parties do not match instructor proposal")
            mid = create_professional_membership(conn, teacher, inst, "martial_instruction", role="instructor", standing=50, influence=20,
                                                 metadata={"authority":"ENGINE_DERIVED", "accepted_interaction_id":int(interaction["id"])})
            rp = conn.execute("SELECT instructor_depth FROM institution_reproduction_profiles WHERE institution_actor_id=?", (inst,)).fetchone()
            if rp:
                conn.execute("UPDATE institution_reproduction_profiles SET instructor_depth=MIN(100,instructor_depth+5) WHERE institution_actor_id=?", (inst,))
            result = {"professional_membership_id": mid, "institution_actor_id": inst, "teacher_actor_id": teacher}

        else:
            raise ValueError(f"unsupported accepted domain action: {kind}")

        aid = _log_attempt(conn, initiator, kind, domain, "applied",
                           institution_actor_id=(initiator if _actor_type(conn, initiator) == "institution" else payload.get("institution_actor_id")),
                           inputs=payload, result={**result, "interaction_id": int(interaction["id"])}, day=day)
        return {"attempt_id": aid, **result}
    except Exception as exc:
        aid = _log_attempt(conn, initiator, kind, domain, "blocked",
                           institution_actor_id=(initiator if _actor_type(conn, initiator) == "institution" else payload.get("institution_actor_id")),
                           reason=str(exc), inputs=payload, result={"interaction_id": int(interaction["id"])}, day=day)
        return {"attempt_id": aid, "blocked": True, "reason": str(exc)}
