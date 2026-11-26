# Three levels, nearby code: batch 4 of 5: Underworld, law and town economy

Same review as the first file (design revision 3.1 and its contract are already with you; not repeated).
This batch is the rest of the city sim. For each module, give the same verdict as before (keep as is, fold into the build, rework, or cut),
with the reason and function names, and when to do it.

Modules in this batch: engine/underworld.py, engine/crime_response.py, engine/civilian.py, engine/merchant.py, engine/craft.py, engine/civic_tick.py, engine/world.py.


## engine/underworld.py

```python
from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any, Callable

from .business import configure_enterprise_business
from .civilian import add_shadow_link, create_enterprise
from .ecology import evaluate_route_leg, find_route_path
from .resolution_controller import create_institution_candidate, update_institution_candidate


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _location(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _institution(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=? AND status NOT IN ('historical','ended','retired')", (name,)).fetchone()
    return int(row[0]) if row else None


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _ensure_front_enterprise(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    location_id: int,
    *,
    activation_key: str,
    name: str,
    enterprise_kind: str,
    archetype: str,
    notes: str,
    capital: float = 70.0,
    cash: float = 35.0,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM civilian_enterprises WHERE institution_actor_id=? AND (json_extract(metadata_json,'$.underworld_activation_key')=? OR json_extract(metadata_json,'$.activation_key')=?) LIMIT 1",
        (institution_actor_id, activation_key, activation_key),
    ).fetchone()
    made = False
    if row:
        enterprise_id = int(row[0])
        conn.execute("UPDATE civilian_enterprises SET location_id=COALESCE(location_id,?) WHERE id=?", (location_id, enterprise_id))
    else:
        # Reuse an older aggregate commercial arm where possible rather than pretending the
        # institution acquired a second literal front merely because the engine gained detail.
        row = conn.execute(
            "SELECT id,metadata_json FROM civilian_enterprises WHERE institution_actor_id=? AND status IN ('active','strained') ORDER BY id LIMIT 1",
            (institution_actor_id,),
        ).fetchone()
        if row:
            enterprise_id = int(row[0])
            meta = json.loads(row["metadata_json"] or "{}")
            meta.update({"underworld_activation_key": activation_key, "underworld_front": True, "authority": "CAMPAIGN_CALIBRATION", "underworld_basis": notes})
            conn.execute("UPDATE civilian_enterprises SET location_id=?,metadata_json=? WHERE id=?", (location_id, _j(meta), enterprise_id))
        else:
            enterprise_id = create_enterprise(
                conn,
                name,
                enterprise_kind,
                institution_actor_id=institution_actor_id,
                location_id=location_id,
                capital=capital,
                cash=cash,
                reputation=52,
                admin_quality=62,
                labor_capacity=62,
                risk_tolerance=65,
                metadata={
                    "activation_key": activation_key,
                    "underworld_activation_key": activation_key,
                    "underworld_front": True,
                    "authority": "CAMPAIGN_CALIBRATION",
                    "basis": notes,
                    "meaning": "aggregate legitimate/front operating footprint, not one literal named shop",
                },
            )
            made = True
    configure_enterprise_business(
        conn,
        enterprise_id,
        archetype,
        quality=55,
        price_position=48,
        capacity=62,
        clientele_fit=58,
        service_reliability=60,
        regulatory_pressure=20,
        cadence_days=30,
        metadata={"authority": "CAMPAIGN_CALIBRATION", "underworld_front": True},
    )
    return enterprise_id, made


def _ensure_shadow(conn: sqlite3.Connection, enterprise_id: int, link_kind: str, pressure: float, exposure: float, note_key: str) -> int:
    row = conn.execute(
        "SELECT id FROM shadow_market_links WHERE subject_kind='enterprise' AND subject_id=? AND link_kind=? AND notes LIKE ? ORDER BY id LIMIT 1",
        (enterprise_id, link_kind, f"%{note_key}%"),
    ).fetchone()
    if row:
        return int(row[0])
    sid = add_shadow_link(conn, "enterprise", enterprise_id, link_kind, pressure=pressure, exposure=exposure, notes=note_key)
    conn.execute("UPDATE shadow_market_links SET status='active' WHERE id=?", (sid,))
    return sid


def _upsert_underworld_profile(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    location_id: int | None,
    *,
    operating_model: str,
    legal_fronts: list[str],
    criminal_activities: list[str],
    continuity_depth: float,
    hidden_exposure: float,
    corrupt_access: float,
    metadata: dict[str, Any],
) -> None:
    day = _day(conn)
    conn.execute(
        """INSERT INTO underworld_institution_profiles(
               institution_actor_id,primary_location_id,operating_model,legal_fronts_json,criminal_activities_json,
               continuity_depth,hidden_exposure,corrupt_access,last_review_day,next_review_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,'active',?)
           ON CONFLICT(institution_actor_id) DO UPDATE SET
               primary_location_id=COALESCE(underworld_institution_profiles.primary_location_id,excluded.primary_location_id),
               operating_model=excluded.operating_model,legal_fronts_json=excluded.legal_fronts_json,
               criminal_activities_json=excluded.criminal_activities_json,continuity_depth=excluded.continuity_depth,
               hidden_exposure=excluded.hidden_exposure,corrupt_access=excluded.corrupt_access,metadata_json=excluded.metadata_json""",
        (
            institution_actor_id,
            location_id,
            operating_model,
            _j(legal_fronts),
            _j(criminal_activities),
            continuity_depth,
            hidden_exposure,
            corrupt_access,
            day,
            day + 30,
            _j(metadata),
        ),
    )


def _ensure_law_profile(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    location_id: int,
    authority_kind: str,
    *,
    capacity: float,
    integrity: float,
    corruption_pressure: float,
    inspection_focus: float,
    notes: str,
) -> bool:
    day = _day(conn)
    before = conn.execute("SELECT 1 FROM law_enforcement_profiles WHERE profile_key=?", (key,)).fetchone()
    conn.execute(
        """INSERT INTO law_enforcement_profiles(
               profile_key,name,location_id,authority_kind,capacity,integrity,corruption_pressure,inspection_focus,
               last_review_day,next_review_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,'active',?)
           ON CONFLICT(profile_key) DO UPDATE SET location_id=excluded.location_id,name=excluded.name,
               authority_kind=excluded.authority_kind,capacity=excluded.capacity,integrity=excluded.integrity,
               corruption_pressure=excluded.corruption_pressure,inspection_focus=excluded.inspection_focus,
               metadata_json=excluded.metadata_json""",
        (key, name, location_id, authority_kind, capacity, integrity, corruption_pressure, inspection_focus, day, day + 30,
         _j({"authority": "STRUCTURAL_AGGREGATE", "basis": notes, "does_not_mean": "omniscient policing or a fully named police roster"})),
    )
    return before is None


# ---------------------------------------------------------------------------
# v0.59 criminal organization morphology
# ---------------------------------------------------------------------------
# Organization type is descriptive form, never a rank. A gang may become large,
# durable and internally layered while remaining a gang. Mafia-family status is
# not awarded by size, wealth, violence or age; it requires explicit historical
# transformation into that institutional form and is therefore never automatic.

ORG_TYPES = {"gang","mafia_family","criminal_dynasty","syndicate","criminal_enterprise","network","crew","other"}
ORG_DIMENSIONS = {
    "territorial_presence","racket_breadth","front_depth","corrupt_access",
    "reputation_deterrence","violence_capacity","cohesion","membership_stability","succession_depth",
}


def create_underworld_organization(
    conn: sqlite3.Connection,
    organization_key: str,
    organization_type: str,
    *,
    name: str | None = None,
    founder_actor_id: int | None = None,
    institution_actor_id: int | None = None,
    anchor_enterprise_id: int | None = None,
    primary_location_id: int | None = None,
    member_count_estimate: float = 1.0,
    command_depth: int = 1,
    territorial_presence: float = 0.0,
    racket_breadth: float = 0.0,
    front_depth: float = 0.0,
    corrupt_access: float = 0.0,
    reputation_deterrence: float = 0.0,
    violence_capacity: float = 0.0,
    cohesion: float = 50.0,
    membership_stability: float = 50.0,
    succession_depth: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> int:
    if organization_type not in ORG_TYPES:
        raise ValueError(f"unknown underworld organization type: {organization_type}")
    day = _day(conn)
    meta = dict(metadata or {})
    if meta.get("auto_promoted_from_gang"):
        raise ValueError("gang-to-Mafia-family auto-promotion is forbidden")
    conn.execute(
        """INSERT INTO underworld_organizations(
               organization_key,organization_type,name,founder_actor_id,institution_actor_id,anchor_enterprise_id,
               primary_location_id,member_count_estimate,command_depth,territorial_presence,racket_breadth,
               front_depth,corrupt_access,reputation_deterrence,violence_capacity,cohesion,membership_stability,
               succession_depth,status,created_day,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)
           ON CONFLICT(organization_key) DO UPDATE SET
               name=COALESCE(underworld_organizations.name,excluded.name),
               founder_actor_id=COALESCE(underworld_organizations.founder_actor_id,excluded.founder_actor_id),
               institution_actor_id=COALESCE(underworld_organizations.institution_actor_id,excluded.institution_actor_id),
               anchor_enterprise_id=COALESCE(underworld_organizations.anchor_enterprise_id,excluded.anchor_enterprise_id),
               primary_location_id=COALESCE(underworld_organizations.primary_location_id,excluded.primary_location_id),
               updated_day=excluded.updated_day""",
        (
            organization_key,organization_type,name,founder_actor_id,institution_actor_id,anchor_enterprise_id,
            primary_location_id,max(0.0,float(member_count_estimate)),max(0,int(command_depth)),
            max(0,min(100,float(territorial_presence))),max(0,min(100,float(racket_breadth))),
            max(0,min(100,float(front_depth))),max(0,min(100,float(corrupt_access))),
            max(0,min(100,float(reputation_deterrence))),max(0,min(100,float(violence_capacity))),
            max(0,min(100,float(cohesion))),max(0,min(100,float(membership_stability))),
            max(0,min(100,float(succession_depth))),day,day,_j(meta),
        ),
    )
    oid = int(conn.execute("SELECT id FROM underworld_organizations WHERE organization_key=?",(organization_key,)).fetchone()[0])
    # An outfit without a heat row never reaches the monthly tick (process_due_rebuild_underworld joins on it).
    from .underworld_rebuild import ensure_heat_profile
    ensure_heat_profile(conn, oid)
    return oid


def underworld_organization_for_actor(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM underworld_organizations WHERE founder_actor_id=? AND status IN ('active','strained','fragmented') ORDER BY id LIMIT 1",
        (actor_id,),
    ).fetchone()


def underworld_organization_for_enterprise(conn: sqlite3.Connection, enterprise_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM underworld_organizations WHERE anchor_enterprise_id=? AND status IN ('active','strained','fragmented') ORDER BY id LIMIT 1",
        (enterprise_id,),
    ).fetchone()


def derive_gang_opening_membership(
    rng: random.Random, *,
    racket_breadth: float,
    territorial_presence: float,
    front_depth: float,
    violence_capacity: float,
    command_depth: int = 1,
    recurring_rackets: int = 0,
    has_operating_front: bool = False,
    can_mount_group_violence: bool = False,
    can_commission_targeted_killing: bool = False,
) -> dict[str, int | float]:
    """Resolve a *previously unspecified* gang's opening personnel from its operating footprint.

    This is deliberately not a size ladder and has no preferred gang headcount.  It is for
    crystallizing qualitative facts (territory, rackets, front, enforcement capacity) into a
    manpower stock only when a simulation actually needs that stock.  A gang can be smaller or
    much larger than the result; explicit canon/scenario headcounts always override this helper.

    Modern gang research is used only as a broad plausibility guard: gangs range from tiny crews
    to very large organizations, and membership commonly includes a durable core, active hands,
    and a wider fringe.  The numerical mapping below is Caerness calibration, not transplanted
    modern demographic statistics.
    """
    rb=max(0.0,min(100.0,float(racket_breadth)))
    tp=max(0.0,min(100.0,float(territorial_presence)))
    fd=max(0.0,min(100.0,float(front_depth)))
    vc=max(0.0,min(100.0,float(violence_capacity)))

    # Operational demand: recurring rackets and enforcement require people even when a gang is
    # deliberately lean.  Front depth contributes less because many legitimate workers need not
    # be gang members.  The stochastic multiplier prevents the same qualitative footprint from
    # collapsing to one canonical headcount.
    demand=(
        5.0
        + 0.28*rb
        + 0.20*tp
        + 0.12*fd
        + 0.18*vc
        + 2.0*max(0,int(recurring_rackets))
        + (2.0 if has_operating_front else 0.0)
        + (2.5 if can_mount_group_violence else 0.0)
        + (2.0 if can_commission_targeted_killing else 0.0)
        + 2.5*max(0,int(command_depth)-1)
    )
    # Broad log-normal-ish spread around functional demand, intentionally asymmetric so some
    # gangs run lean while others carry substantially more manpower for the same workload.
    multiplier=math.exp(rng.gauss(0.0,0.18))
    full=max(4,int(round(demand*multiplier)))

    # Core/active are analytic simulation strata, not necessarily formal gang ranks.
    core_share=max(0.16,min(0.36,0.23 + rng.gauss(0.0,0.045)))
    core=max(2,min(full-1,int(round(full*core_share)))) if full>2 else max(1,full)
    active=max(0,full-core)

    # A functioning front / protection market normally creates a wider orbit of helpers,
    # prospects, relatives, debtors, fences, drivers, and occasional muscle.  This is resolved
    # separately from full membership and can be small or substantial.
    fringe_rate=(0.18 + 0.004*rb + 0.0025*tp + (0.12 if has_operating_front else 0.0))
    fringe_mean=max(0.0,full*fringe_rate)
    peripheral=_poisson(rng,fringe_mean)
    return {
        'core_members': int(core),
        'active_members': int(active),
        'peripheral_associates': int(peripheral),
        'full_members': int(full),
        'wider_orbit': int(full+peripheral),
        'operational_demand': round(demand,3),
        'stochastic_multiplier': round(multiplier,4),
    }


def ensure_underworld_membership_profile(
    conn: sqlite3.Connection, organization_id: int, *,
    core_members: float | None = None, active_members: float | None = None,
    peripheral_associates: float | None = None, metadata: dict[str,Any] | None = None,
) -> sqlite3.Row:
    """Ensure a membership stock profile for an underworld organization.

    member_count_estimate continues to mean current full members (core + active).
    Peripheral associates are involved in the organization's orbit but are not counted as
    full members. The split is a simulation-resolution tool, not a claim that every gang
    uses formal membership categories.
    """
    org=conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    if not org:
        raise ValueError("unknown underworld organization")
    row=conn.execute("SELECT * FROM underworld_membership_profiles WHERE organization_id=?",(organization_id,)).fetchone()
    if row:
        return row
    total=max(0.0,float(org['member_count_estimate']))
    if core_members is None:
        # Small tracked gangs usually have a persistent hard core surrounded by more fluid hands.
        core_members=min(total,max(1.0,round(total*.35))) if total else 0.0
    if active_members is None:
        active_members=max(0.0,total-float(core_members))
    if peripheral_associates is None:
        # Do not manufacture an unrecorded fringe from the full-member headcount. If an
        # opening state says eight members, it begins with eight people in the tracked gang
        # unless associates are explicitly seeded. Peripheral associates must enter through
        # actual recruitment/contact flows or explicit scenario history.
        peripheral_associates=0.0
    full=max(0.0,float(core_members)+float(active_members))
    conn.execute("UPDATE underworld_organizations SET member_count_estimate=?,updated_day=? WHERE id=?",(full,_day(conn),organization_id))
    # Lazy profile creation must not erase elapsed membership history. Start the flow clock from
    # the organization's actual tracked creation/opening day, not from the day somebody first
    # asks for a resolved membership profile.
    initial_review_day=int(org['created_day']) if org['created_day'] is not None else _day(conn)
    conn.execute(
        """INSERT INTO underworld_membership_profiles(organization_id,core_members,active_members,peripheral_associates,lifetime_entries,lifetime_exits,last_review_day,metadata_json)
           VALUES (?,?,?,?,0,0,?,?)""",
        (organization_id,float(core_members),float(active_members),float(peripheral_associates),initial_review_day,_j(metadata or {'membership_categories_are_analytic':True})),
    )
    return conn.execute("SELECT * FROM underworld_membership_profiles WHERE organization_id=?",(organization_id,)).fetchone()


def underworld_membership_profile(conn: sqlite3.Connection, organization_id: int) -> sqlite3.Row:
    return ensure_underworld_membership_profile(conn,organization_id)


def record_underworld_membership_flow(
    conn: sqlite3.Connection, organization_id: int, flow_kind: str, count: float, *,
    from_tier: str | None = None, to_tier: str | None = None, source_event_id: int | None = None,
    metadata: dict[str,Any] | None = None, day: int | None = None,
) -> sqlite3.Row:
    """Persist a membership flow and reconcile the organization's current member stock."""
    allowed={'recruitment','desistance','defection','custody','death_or_incapacitation','relocation','associate_to_active','active_to_core','return_to_periphery'}
    if flow_kind not in allowed:
        raise ValueError(f'unknown membership flow: {flow_kind}')
    n=max(0.0,float(count))
    if n <= 0:
        return ensure_underworld_membership_profile(conn,organization_id)
    profile=ensure_underworld_membership_profile(conn,organization_id)
    stock={'core':float(profile['core_members']),'active':float(profile['active_members']),'peripheral':float(profile['peripheral_associates'])}
    entries=float(profile['lifetime_entries']); exits=float(profile['lifetime_exits'])
    if from_tier:
        if from_tier not in stock: raise ValueError('invalid from_tier')
        n=min(n,stock[from_tier])
        if n <= 0: return profile
        stock[from_tier]-=n
    if to_tier:
        if to_tier not in stock: raise ValueError('invalid to_tier')
        stock[to_tier]+=n
    if flow_kind=='recruitment':
        entries+=n
    if flow_kind in {'desistance','defection','custody','death_or_incapacitation','relocation'}:
        exits+=n
    d=_day(conn) if day is None else int(day)
    flow_cur = conn.execute(
        """INSERT INTO underworld_membership_flows(organization_id,day,flow_kind,count,from_tier,to_tier,source_event_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (organization_id,d,flow_kind,n,from_tier,to_tier,source_event_id,_j(metadata or {})),
    )
    flow_id = int(flow_cur.lastrowid)
    conn.execute(
        """UPDATE underworld_membership_profiles SET core_members=?,active_members=?,peripheral_associates=?,
           lifetime_entries=?,lifetime_exits=?,last_review_day=? WHERE organization_id=?""",
        (stock['core'],stock['active'],stock['peripheral'],entries,exits,d,organization_id),
    )
    conn.execute("UPDATE underworld_organizations SET member_count_estimate=?,updated_day=? WHERE id=?",(stock['core']+stock['active'],d,organization_id))
    # The analytic flow label intentionally combines deaths and incapacitation.  Population is
    # reduced only when the causal caller supplies an explicit death subset; absent that evidence
    # we do not silently reinterpret incapacitation as death.
    meta = dict(metadata or {})
    explicit_deaths = float(meta.get('deaths', 0) or 0) if flow_kind == 'death_or_incapacitation' else 0.0
    if explicit_deaths > 0:
        from .population_reconciliation import record_excess_mortality, population_source_for_location
        org = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
        loc = int(org[0]) if org and org[0] is not None else None
        pop_source = population_source_for_location(conn, loc)
        record_excess_mortality(
            conn, source_kind='underworld_membership_flow', source_id=flow_id,
            aggregate_deaths=min(n, explicit_deaths), tracked_deaths=int(meta.get('tracked_deaths',0) or 0),
            population_source_id=pop_source, metadata={'organization_id':organization_id,'location_id':loc,'flow_id':flow_id,**meta},
            adult_only=True,
        )
    return conn.execute("SELECT * FROM underworld_membership_profiles WHERE organization_id=?",(organization_id,)).fetchone()


def _poisson(rng: random.Random, lam: float) -> int:
    lam=max(0.0,float(lam))
    if lam <= 0: return 0
    # Membership reviews use small lambdas; Knuth is exact and sufficient here.
    limit=math.exp(-lam); product=1.0; k=0
    while product > limit:
        k+=1; product*=rng.random()
    return max(0,k-1)


def simulate_underworld_membership_turnover(
    conn: sqlite3.Connection, organization_id: int, rng: random.Random, *,
    cash: float = 0.0, violence_pressure: float = 0.0, event_logger: Callable[...,Any] | None = None,
    actor_id: int | None = None, location_id: int | None = None,
) -> dict[str,Any]:
    """Resolve ordinary recruitment and attrition since the last membership review.

    The model intentionally permits high gross turnover with low net growth. Real-world gang
    research is used only for the qualitative distinction between a durable hard core and a
    more fluid surrounding membership; Caerness rates remain setting calibration rather than
    transplanted modern statistics.
    """
    org=conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    if not org: raise ValueError('unknown underworld organization')
    p=ensure_underworld_membership_profile(conn,organization_id)
    day=_day(conn); elapsed=max(0,day-int(p['last_review_day']))
    if elapsed < 75:
        return {'reviewed':False}
    years=elapsed/365.0
    core=float(p['core_members']); active=float(p['active_members']); peripheral=float(p['peripheral_associates'])
    cohesion=float(org['cohesion'])/100.0; stability=float(org['membership_stability'])/100.0
    reputation=float(org['reputation_deterrence'])/100.0
    full=max(1.0,core+active)
    # v0.59 success coupling: prosperity and organizational competence change membership flows.
    # This is deliberately *not* a growth bonus or target. A successful gang can remain lean, but
    # a gang that pays, has work, is feared/respected, and can delegate should recruit and retain
    # differently from an equally violent failing crew.
    cash_per_full=max(0.0,float(cash))/full
    economic_support=max(0.0,min(1.0,cash_per_full/6.0))
    work_support=max(0.0,min(1.0,(float(org['racket_breadth'])+float(org['front_depth'])+float(org['territorial_presence']))/180.0))
    deterrence_support=max(0.0,min(1.0,reputation))
    command_support=max(0.0,min(1.0,(int(org['command_depth'])-1)/3.0))
    success_support=max(0.0,min(1.0,
        .34*economic_support + .26*work_support + .16*deterrence_support +
        .12*command_support + .07*cohesion + .05*stability
    ))
    # Recruitment feeds the periphery first. More work and reliable pay attract people; current
    # size still raises the social recruiting surface, while per-capita economics prevents runaway
    # growth when manpower outruns the operation that supports it.
    recruitment_lambda=years*(0.60 + full*(.055 + .055*success_support) + 1.00*economic_support + 1.10*work_support + .60*deterrence_support)
    recruits=_poisson(rng,recruitment_lambda)
    if recruits:
        record_underworld_membership_flow(conn,organization_id,'recruitment',recruits,to_tier='peripheral',metadata={'routine_turnover':True,'basis':'recruitment into gang orbit'},day=day)
    # Peripheral associates churn fastest; active members are stickier; core members rarely leave.
    p=underworld_membership_profile(conn,organization_id); peripheral=float(p['peripheral_associates']); active=float(p['active_members']); core=float(p['core_members'])
    # Success primarily matters through retention, not only recruitment. Stable work, pay,
    # deterrent reputation and functioning command reduce ordinary desistance/defection pressure;
    # violence can still overwhelm those advantages. Core members remain much stickier than the
    # surrounding active/peripheral population.
    peripheral_rate=max(.08,.25 + .12*(1.0-stability) - .16*success_support)
    active_rate=max(.014,.050 + .050*(1.0-cohesion) + .025*violence_pressure - .050*success_support)
    core_rate=max(.003,.009 + .016*(1.0-cohesion) + .011*violence_pressure - .012*success_support)
    peripheral_exit=_poisson(rng,years*peripheral*peripheral_rate)
    active_exit=_poisson(rng,years*active*active_rate)
    core_exit=_poisson(rng,years*core*core_rate)
    reasons=['desistance','defection','custody','death_or_incapacitation','relocation']
    weights=[.43,.17,.18,.10,.12]
    def reason():
        x=rng.random(); acc=0.0
        for r,w in zip(reasons,weights):
            acc+=w
            if x<=acc: return r
        return reasons[-1]
    exits_by_reason={}
    for tier,n in [('peripheral',peripheral_exit),('active',active_exit),('core',core_exit)]:
        for _ in range(int(n)):
            r=reason(); before=underworld_membership_profile(conn,organization_id); available=float(before[f'{tier}_members'] if tier!='peripheral' else before['peripheral_associates'])
            if available < 1: break
            record_underworld_membership_flow(conn,organization_id,r,1,from_tier=tier,metadata={'routine_turnover':True},day=day)
            exits_by_reason[r]=exits_by_reason.get(r,0)+1
    # Some peripheral associates become full active members; some established active members enter the hard core.
    p=underworld_membership_profile(conn,organization_id); peripheral=float(p['peripheral_associates']); active=float(p['active_members'])
    to_active=min(int(peripheral),_poisson(rng,years*peripheral*(.15 + .10*cohesion + .16*success_support)))
    if to_active:
        record_underworld_membership_flow(conn,organization_id,'associate_to_active',to_active,from_tier='peripheral',to_tier='active',metadata={'routine_turnover':True},day=day)
    p=underworld_membership_profile(conn,organization_id); active=float(p['active_members'])
    to_core=min(int(active),_poisson(rng,years*active*(.025 + .025*stability)))
    if to_core:
        record_underworld_membership_flow(conn,organization_id,'active_to_core',to_core,from_tier='active',to_tier='core',metadata={'routine_turnover':True},day=day)
    p=underworld_membership_profile(conn,organization_id)
    conn.execute("UPDATE underworld_membership_profiles SET last_review_day=? WHERE organization_id=?",(day,organization_id))
    # Keep the legacy crew_loyalty read-model synchronized to current full members for old systems.
    founder=org['founder_actor_id']
    if founder is not None:
        current_full=float(p['core_members'])+float(p['active_members'])
        rr=conn.execute("SELECT id FROM resources WHERE actor_id=? AND resource_type='crew_loyalty' ORDER BY id LIMIT 1",(int(founder),)).fetchone()
        if rr: conn.execute("UPDATE resources SET amount=?,updated_day=? WHERE id=?",(current_full,day,int(rr['id'])))
    changed=recruits+sum(exits_by_reason.values())+to_active+to_core
    if changed and event_logger is not None and actor_id is not None:
        # One compressed biography event records the staffing episode without turning every anonymous
        # associate into a named character or narrating routine churn individually.
        event_logger(day=day,event_type='underworld_membership_turnover',title='Gang membership changed',
                     summary=(f'{recruits} people entered the gang orbit; {sum(exits_by_reason.values())} left or were lost; '
                              f'{to_active} associates became active members and {to_core} active members entered the hard core.'),
                     severity=1,source_actor_id=actor_id,location_id=location_id)
    return {'reviewed':True,'recruits':recruits,'exits':sum(exits_by_reason.values()),'exit_reasons':exits_by_reason,'associate_to_active':to_active,'active_to_core':to_core,'success_support':round(success_support,4),'profile':dict(p)}


def update_underworld_organization(
    conn: sqlite3.Connection,
    organization_id: int,
    *,
    member_delta: float = 0.0,
    command_depth: int | None = None,
    dimension_deltas: dict[str,float] | None = None,
    metadata_update: dict[str,Any] | None = None,
) -> sqlite3.Row:
    row=conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    if not row:
        raise ValueError("unknown underworld organization")
    sets=["member_count_estimate=MAX(0,member_count_estimate+?)","updated_day=?"]
    vals:[Any]=[float(member_delta),_day(conn)]
    if command_depth is not None:
        sets.append("command_depth=MAX(0,?)"); vals.append(int(command_depth))
    for key,delta in (dimension_deltas or {}).items():
        if key not in ORG_DIMENSIONS:
            raise ValueError(f"not an organization dimension: {key}")
        sets.append(f"{key}=MAX(0,MIN(100,{key}+?))"); vals.append(float(delta))
    if metadata_update:
        meta=json.loads(row['metadata_json'] or '{}'); meta.update(metadata_update)
        if meta.get('auto_promoted_from_gang'):
            raise ValueError('gang-to-Mafia-family auto-promotion is forbidden')
        sets.append("metadata_json=?"); vals.append(_j(meta))
    vals.append(int(organization_id))
    conn.execute(f"UPDATE underworld_organizations SET {','.join(sets)} WHERE id=?",vals)
    return conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()


def ensure_actor_underworld_organization(
    conn: sqlite3.Connection, actor_id: int, enterprise_id: int | None = None,
    *, organization_type: str | None = None, name: str | None = None
) -> sqlite3.Row | None:
    existing=underworld_organization_for_actor(conn,actor_id)
    if existing:
        return existing
    actor=conn.execute("SELECT COALESCE(subtype,''),current_location_id FROM actors WHERE id=?",(actor_id,)).fetchone()
    if not actor:
        return None
    subtype=str(actor[0] or '').lower()
    ent=None
    if enterprise_id is not None:
        ent=conn.execute("SELECT * FROM civilian_enterprises WHERE id=?",(int(enterprise_id),)).fetchone()
    if organization_type is None:
        if 'gang' in subtype:
            organization_type='gang'
        elif ent is not None:
            try:
                meta=json.loads(ent['metadata_json'] or '{}')
            except Exception:
                meta={}
            if meta.get('front_for_minor_crew') or meta.get('gang_front'):
                organization_type='gang'
            else:
                organization_type='criminal_enterprise'
        else:
            return None
    loc=int(actor[1]) if actor[1] is not None else (int(ent['location_id']) if ent is not None and ent['location_id'] is not None else None)
    crew=conn.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type='crew_loyalty' ORDER BY id LIMIT 1",(actor_id,)).fetchone()
    members=max(1.0,float(crew[0])) if crew else 3.0
    key=f'actor-{actor_id}-{organization_type}'
    oid=create_underworld_organization(
        conn,key,organization_type,name=name,founder_actor_id=actor_id,anchor_enterprise_id=enterprise_id,primary_location_id=loc,
        member_count_estimate=members,command_depth=1,territorial_presence=12 if organization_type=='gang' else 5,
        racket_breadth=14,front_depth=18 if enterprise_id is not None else 3,corrupt_access=4,
        reputation_deterrence=12,violence_capacity=18,cohesion=58,membership_stability=48,succession_depth=2,
        metadata={'authority':'V0_59_STRUCTURAL','organization_form_is_not_rank':True,'auto_type_change':False},
    )
    return conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(oid,)).fetchone()


def organization_operational_factors(org: sqlite3.Row | None) -> dict[str,float]:
    if org is None:
        return {"people":1.0,"command":1.0,"rackets":1.0,"territory":1.0,"fronts":1.0,"deterrence":1.0,"violence":1.0}
    return {
        "people": 1.0 + min(2.5,max(0.0,float(org['member_count_estimate'])-4.0)/20.0),
        "command": 1.0 + min(1.5,max(0,int(org['command_depth'])-1)*0.35),
        "rackets": 1.0 + float(org['racket_breadth'])/100.0,
        "territory": 1.0 + float(org['territorial_presence'])/120.0,
        "fronts": 1.0 + float(org['front_depth'])/125.0,
        "deterrence": 1.0 + float(org['reputation_deterrence'])/110.0,
        "violence": 1.0 + float(org['violence_capacity'])/120.0,
    }


def maybe_deepen_gang_structure(conn: sqlite3.Connection, organization_id: int) -> sqlite3.Row:
    """Allow organizational depth to emerge without changing organizational type.

    More people plus durable rackets can justify lieutenants/subordinate collectors; this is not
    a promotion into a different category of criminal organization.
    """
    org=conn.execute("SELECT * FROM underworld_organizations WHERE id=?",(organization_id,)).fetchone()
    if not org:
        raise ValueError("unknown underworld organization")
    desired=1
    members=float(org['member_count_estimate']); breadth=float(org['racket_breadth']); cohesion=float(org['cohesion'])
    if members>=10 and breadth>=25 and cohesion>=40: desired=2
    if members>=28 and breadth>=45 and cohesion>=45: desired=3
    if members>=70 and breadth>=60 and cohesion>=50: desired=4
    if desired>int(org['command_depth']):
        return update_underworld_organization(conn,organization_id,command_depth=desired,dimension_deltas={'succession_depth':4.0 if desired>=2 else 0.0},metadata_update={'last_command_deepening_day':_day(conn)})
    return org

def activate_underworld_substrate(conn: sqlite3.Connection) -> dict[str, int]:
    """Activate only canonically established underworld structures.

    Tallow and Greyhook receive locations and aggregate fronts because MASTER FINAL establishes
    those facts. Their named leadership remains intentionally open. Law profiles are aggregate
    jurisdictional capacities, not newly canonized officeholders.
    """
    day = _day(conn)
    tallow, greyhook = _institution(conn, "Tallow Family"), _institution(conn, "Greyhook Wharf Company")
    aldergate, toll, cairn = _location(conn, "Aldergate"), _location(conn, "Toll’s Reach"), _location(conn, "Cairnholt")
    location_updates = fronts_created = profiles = shadow_links = law_created = stock_seeded = 0

    if tallow is not None and aldergate is not None:
        conn.execute("UPDATE actors SET home_location_id=?,current_location_id=? WHERE id=?", (aldergate, aldergate, tallow))
        conn.execute("UPDATE institution_profiles SET primary_location_id=? WHERE actor_id=?", (aldergate, tallow))
        location_updates += 1
        ent, made = _ensure_front_enterprise(
            conn, tallow, aldergate,
            activation_key="v037-tallow-front",
            name="Tallow Family — aggregate logistics/property fronts",
            enterprise_kind="merchant_house", archetype="warehouse",
            notes="MASTER FINAL: Tallow legitimate fronts include warehousing, cheap lodging, wagon repair, animal yards, freight handling and small lending in Aldergate.",
        )
        fronts_created += int(made)
        for kind, pressure, exposure in [("illicit_dealing", 58, 10), ("fencing_risk", 52, 8), ("corrupt_access", 44, 7)]:
            before = conn.execute("SELECT COUNT(*) FROM shadow_market_links").fetchone()[0]
            _ensure_shadow(conn, ent, kind, pressure, exposure, "v037:Tallow canon criminal-commercial structure")
            shadow_links += int(conn.execute("SELECT COUNT(*) FROM shadow_market_links").fetchone()[0] > before)
        _upsert_underworld_profile(
            conn, tallow, aldergate, operating_model="criminal_commercial_dynasty",
            legal_fronts=["warehousing", "cheap lodging", "wagon repair", "animal yards", "freight handling", "small lending"],
            criminal_activities=["cargo substitution", "stolen goods", "protection", "high-risk debt", "illegal gambling", "warehouse record manipulation"],
            continuity_depth=85, hidden_exposure=15, corrupt_access=45,
            metadata={"authority":"WORLD_BIBLE_CANON_STRUCTURE", "organization_type":"criminal_dynasty", "named_leadership":"INTENTIONALLY_OPEN", "violence":"controlled/selective"},
        ); profiles += 1

    if greyhook is not None and toll is not None:
        conn.execute("UPDATE actors SET home_location_id=?,current_location_id=? WHERE id=?", (toll, toll, greyhook))
        conn.execute("UPDATE institution_profiles SET primary_location_id=? WHERE actor_id=?", (toll, greyhook))
        location_updates += 1
        ent, made = _ensure_front_enterprise(
            conn, greyhook, toll,
            activation_key="v037-greyhook-front",
            name="Greyhook Wharf Company — aggregate wharf/warehouse front",
            enterprise_kind="shipping", archetype="warehouse",
            notes="MASTER FINAL: Greyhook is publicly a dock, salvage, small-boat and warehouse concern in Toll’s Reach; its criminal competence is smuggling through paperwork and port relationships.",
            capital=80, cash=40,
        )
        fronts_created += int(made)
        for kind, pressure, exposure in [("smuggling_risk", 68, 9), ("corrupt_access", 52, 8)]:
            before = conn.execute("SELECT COUNT(*) FROM shadow_market_links").fetchone()[0]
            _ensure_shadow(conn, ent, kind, pressure, exposure, "v037:Greyhook canon smuggling structure")
            shadow_links += int(conn.execute("SELECT COUNT(*) FROM shadow_market_links").fetchone()[0] > before)
        _upsert_underworld_profile(
            conn, greyhook, toll, operating_model="smuggling_logistics_company",
            legal_fronts=["dock work", "salvage", "small boats", "warehousing"],
            criminal_activities=["duty evasion", "stolen cargo movement", "restricted elixir movement", "forged cargo", "provenance laundering"],
            continuity_depth=72, hidden_exposure=12, corrupt_access=55,
            metadata={"authority":"WORLD_BIBLE_CANON_STRUCTURE", "organization_type":"criminal_enterprise", "named_leadership":"INTENTIONALLY_OPEN", "not":"pirate fleet"},
        ); profiles += 1
        # A small operational cloth stock is campaign calibration, not a claim about literal opening inventory.
        good = conn.execute("SELECT id FROM market_goods WHERE good_key='ordinary-cloth'").fetchone()
        if good:
            existing = conn.execute("SELECT quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?", (ent, toll, int(good[0]))).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json) VALUES (?,?,?,?,?,?)",
                    (ent, toll, int(good[0]), 12.0, day, _j({"authority":"CAMPAIGN_CALIBRATION","basis":"Greyhook legitimate port/warehouse trade; ordinary cloth chosen as fungible working cargo","not":"all cargo is illicit"})),
                )
                stock_seeded += 1

    # Aggregate jurisdictions. These encode who can notice/investigate ordinary crime, not named officers.
    if aldergate is not None:
        law_created += int(_ensure_law_profile(conn,"aldergate-watch","Aldergate ordinary watch / commercial enforcement (aggregate)",aldergate,"imperial_city_watch",capacity=63,integrity=58,corruption_pressure=27,inspection_focus=60,notes="MASTER FINAL mentions the Aldergate watch amid warehouse/cargo crime and Imperial ordinary law."))
    if toll is not None:
        law_created += int(_ensure_law_profile(conn,"toll-magistracy-customs","Toll’s Reach magistracy / customs enforcement (aggregate)",toll,"port_magistracy_customs",capacity=66,integrity=55,corruption_pressure=32,inspection_focus=72,notes="Toll’s Reach retains Imperial criminal law under its Port Council and Imperial-confirmed magistracy; port/customs crime is ordinary enforcement work."))
    if cairn is not None:
        law_created += int(_ensure_law_profile(conn,"cairnholt-imperial-policing","Cairnholt Imperial civic policing (aggregate)",cairn,"imperial_civic_policing",capacity=70,integrity=64,corruption_pressure=20,inspection_focus=62,notes="MASTER FINAL explicitly assigns ordinary crime/public order at Cairnholt events to Imperial officials."))

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_activation_version','1')")
    return {
        "underworld_location_updates": location_updates,
        "underworld_fronts_created": fronts_created,
        "underworld_profiles": profiles,
        "underworld_shadow_links_created": shadow_links,
        "law_enforcement_profiles_created": law_created,
        "underworld_working_stock_seeded": stock_seeded,
    }


def _evidence(
    conn: sqlite3.Connection,
    *,
    location_id: int | None,
    subject_kind: str,
    subject_id: int,
    evidence_kind: str,
    visibility: str,
    strength: float,
    source_kind: str,
    source_id: int,
    metadata: dict[str, Any] | None = None,
    day: int | None = None,
) -> int:
    day = _day(conn) if day is None else int(day)
    strength = max(0.0, min(100.0, float(strength)))
    conn.execute(
        """INSERT INTO underworld_evidence(location_id,subject_kind,subject_id,evidence_kind,visibility,strength,source_kind,source_id,status,created_day,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,'active',?,?,?)
           ON CONFLICT(source_kind,source_id,evidence_kind) DO UPDATE SET
              location_id=excluded.location_id,subject_kind=excluded.subject_kind,subject_id=excluded.subject_id,
              visibility=CASE WHEN underworld_evidence.visibility='public' THEN 'public' WHEN excluded.visibility='public' THEN 'public' WHEN underworld_evidence.visibility='local' THEN 'local' ELSE excluded.visibility END,
              strength=MAX(underworld_evidence.strength,excluded.strength),updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
        (location_id, subject_kind, int(subject_id), evidence_kind, visibility, strength, source_kind, int(source_id), day, day, _j(metadata or {})),
    )
    return int(conn.execute("SELECT id FROM underworld_evidence WHERE source_kind=? AND source_id=? AND evidence_kind=?", (source_kind, int(source_id), evidence_kind)).fetchone()[0])



def record_underworld_evidence(conn: sqlite3.Connection, *, location_id: int | None, subject_kind: str, subject_id: int, evidence_kind: str, visibility: str, strength: float, source_kind: str, source_id: int, metadata: dict[str, Any] | None = None, day: int | None = None) -> int:
    return _evidence(conn, location_id=location_id, subject_kind=subject_kind, subject_id=subject_id, evidence_kind=evidence_kind, visibility=visibility, strength=strength, source_kind=source_kind, source_id=source_id, metadata=metadata, day=day)

def _enterprise_location(conn: sqlite3.Connection, enterprise_id: int) -> int | None:
    row = conn.execute("SELECT location_id FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _sync_shadow_evidence(conn: sqlite3.Connection, day: int) -> int:
    changed = 0
    for row in conn.execute("SELECT * FROM shadow_market_links WHERE status IN ('active','exposed') ORDER BY id").fetchall():
        if str(row["subject_kind"]) != "enterprise":
            continue
        loc = _enterprise_location(conn, int(row["subject_id"]))
        visibility = "local" if str(row["status"]) == "exposed" else "hidden"
        strength = min(100.0, 0.55 * float(row["pressure"]) + 0.45 * float(row["exposure"]))
        _evidence(
            conn, location_id=loc, subject_kind="enterprise", subject_id=int(row["subject_id"]),
            evidence_kind=str(row["link_kind"]), visibility=visibility, strength=strength,
            source_kind="shadow_link", source_id=int(row["id"]), metadata={"shadow_status":str(row["status"])}, day=day,
        )
        changed += 1
    return changed


def _begin_smuggling_leg(conn: sqlite3.Connection, operation_id: int, day: int) -> bool:
    op = conn.execute("SELECT * FROM smuggling_operations WHERE id=?", (operation_id,)).fetchone()
    if not op or str(op["status"]) not in {"in_transit","stalled"}:
        return False
    current, destination = int(op["current_location_id"]), int(op["destination_location_id"])
    if current == destination:
        _deliver_smuggling(conn, op, day)
        return True
    path = find_route_path(conn, current, destination, day=day)
    if not path:
        conn.execute("UPDATE smuggling_operations SET status='stalled',current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?", (day + 3, operation_id))
        return False
    ev = evaluate_route_leg(conn, int(path[0]), current, day=day)
    if not bool(ev["usable"]):
        conn.execute("UPDATE smuggling_operations SET status='stalled',current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?", (day + 3, operation_id))
        return False
    due = day + max(1, int(math.ceil(float(ev["days"]))))
    meta = json.loads(op["metadata_json"] or "{}")
    meta.update({"segment_target_location_id":int(ev["target"]),"planned_path":[int(x) for x in path],"segment_hazard_pressure":float(ev["hazard"])})
    conn.execute(
        "UPDATE smuggling_operations SET status='in_transit',current_route_id=?,segment_due_day=?,next_review_day=?,metadata_json=? WHERE id=?",
        (int(path[0]), due, due, _j(meta), operation_id),
    )
    return True


def arrange_smuggling_operation(
    conn: sqlite3.Connection,
    enterprise_id: int,
    good_id: int,
    quantity: float,
    destination_location_id: int,
    *,
    organizer_institution_actor_id: int | None = None,
    destination_enterprise_id: int | None = None,
    violation_kind: str = "duty_evasion",
    concealment: float = 65.0,
    operation_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Move real commercial stock into illicit custody without creating or deleting cargo."""
    quantity = float(quantity)
    if quantity <= 0:
        raise ValueError("smuggling quantity must be positive")
    ent = conn.execute("SELECT * FROM civilian_enterprises WHERE id=? AND status IN ('active','strained')", (enterprise_id,)).fetchone()
    if not ent or ent["location_id"] is None:
        raise ValueError("source enterprise must be active and located")
    origin, destination = int(ent["location_id"]), int(destination_location_id)
    if origin == destination:
        raise ValueError("smuggling destination must differ from origin")
    stock = conn.execute("SELECT * FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?", (enterprise_id, origin, good_id)).fetchone()
    if not stock or float(stock["quantity"]) + 1e-9 < quantity:
        raise ValueError("insufficient commercial stock")
    if not find_route_path(conn, origin, destination, day=_day(conn)):
        raise ValueError("no traversable route")
    if operation_key:
        prior = conn.execute("SELECT id FROM smuggling_operations WHERE operation_key=?", (operation_key,)).fetchone()
        if prior:
            return int(prior[0])
    day = _day(conn)
    conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE enterprise_id=? AND location_id=? AND good_id=?", (quantity, day, enterprise_id, origin, good_id))
    cur = conn.execute(
        """INSERT INTO smuggling_operations(operation_key,organizer_institution_actor_id,enterprise_id,destination_enterprise_id,good_id,quantity,
               origin_location_id,destination_location_id,current_location_id,next_review_day,status,violation_kind,concealment,started_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,'in_transit',?,?,?,?)""",
        (operation_key, organizer_institution_actor_id, enterprise_id, destination_enterprise_id, good_id, quantity,
         origin, destination, origin, day, violation_kind, max(0.0,min(100.0,float(concealment))), day,
         _j({"authority":"ENGINE_DERIVED", "cargo_custody":"smuggling_operation", **(metadata or {})})),
    )
    oid = int(cur.lastrowid)
    _evidence(conn, location_id=origin, subject_kind="enterprise", subject_id=enterprise_id, evidence_kind="smuggling_activity",
              visibility="hidden", strength=42, source_kind="smuggling_operation", source_id=oid,
              metadata={"operation_id":oid,"violation_kind":violation_kind}, day=day)
    _begin_smuggling_leg(conn, oid, day)
    return oid


def _deliver_smuggling(conn: sqlite3.Connection, op: sqlite3.Row, day: int) -> None:
    if str(op["status"]) == "delivered":
        return
    target_enterprise = int(op["destination_enterprise_id"] or op["enterprise_id"])
    conn.execute(
        """INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
        (target_enterprise, int(op["destination_location_id"]), int(op["good_id"]), float(op["quantity"]), day,
         _j({"authority":"ENGINE_DERIVED","source_smuggling_operation_id":int(op["id"])})),
    )
    conn.execute("UPDATE smuggling_operations SET status='delivered',current_location_id=destination_location_id,current_route_id=NULL,segment_due_day=NULL,next_review_day=?,arrived_day=? WHERE id=?", (day,day,int(op["id"])))


def mark_smuggling_detected(conn: sqlite3.Connection, operation_id: int, location_id: int, *, strength: float = 60.0, day: int | None = None, source: str = "inspection") -> int:
    day = _day(conn) if day is None else int(day)
    op = conn.execute("SELECT * FROM smuggling_operations WHERE id=?", (operation_id,)).fetchone()
    if not op:
        raise ValueError("unknown smuggling operation")
    score = max(float(op["evidence_score"]), max(0.0,min(100.0,float(strength))))
    conn.execute("UPDATE smuggling_operations SET detected_day=COALESCE(detected_day,?),detected_location_id=COALESCE(detected_location_id,?),evidence_score=? WHERE id=?", (day,location_id,score,operation_id))
    return _evidence(conn, location_id=location_id, subject_kind="smuggling_operation", subject_id=operation_id,
                     evidence_kind="detected_smuggling", visibility="local", strength=score,
                     source_kind=f"smuggling_detection:{source}", source_id=operation_id,
                     metadata={"enterprise_id":int(op["enterprise_id"]),"violation_kind":str(op["violation_kind"])}, day=day)


def _inspection_check(conn: sqlite3.Connection, op: sqlite3.Row, location_id: int, day: int) -> bool:
    if op["detected_day"] is not None:
        return False
    profiles = conn.execute("SELECT * FROM law_enforcement_profiles WHERE location_id=? AND status='active' ORDER BY id", (location_id,)).fetchall()
    if not profiles:
        return False
    p = profiles[0]
    chance = 0.04 + float(p["inspection_focus"]) * 0.0018 + float(p["capacity"]) * 0.0011 - float(op["concealment"]) * 0.0016
    chance = max(0.01, min(0.45, chance))
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]) * 1000003 + int(op["id"]) * 1009 + day * 37 + location_id
    if random.Random(seed).random() >= chance:
        return False
    strength = min(95.0, 30.0 + (100.0-float(op["concealment"]))*0.30 + float(p["capacity"])*0.18)
    mark_smuggling_detected(conn, int(op["id"]), location_id, strength=strength, day=day, source="route_inspection")
    return True


def _process_smuggling(conn: sqlite3.Connection, op: sqlite3.Row, day: int, event_logger: Callable[...,int] | None = None) -> tuple[bool,bool]:
    if str(op["status"]) == "stalled":
        return _begin_smuggling_leg(conn, int(op["id"]), day), False
    if op["segment_due_day"] is None or int(op["segment_due_day"]) > day:
        return False, False
    meta = json.loads(op["metadata_json"] or "{}")
    target = meta.get("segment_target_location_id")
    if target is None:
        conn.execute("UPDATE smuggling_operations SET status='stalled',next_review_day=? WHERE id=?", (day+3,int(op["id"])))
        return False, False
    # Re-check the actual leg at completion time. A route closed after dispatch must stall cargo
    # rather than allowing it to teleport through a now-invalid edge.
    if op["current_route_id"] is not None:
        leg = evaluate_route_leg(conn,int(op["current_route_id"]),int(op["current_location_id"]),day=day)
        if not bool(leg["usable"]):
            conn.execute("UPDATE smuggling_operations SET status='stalled',current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?", (day+3,int(op["id"])))
            return False, False
    target = int(target)
    conn.execute("UPDATE smuggling_operations SET current_location_id=? WHERE id=?", (target,int(op["id"])))
    refreshed = conn.execute("SELECT * FROM smuggling_operations WHERE id=?", (int(op["id"]),)).fetchone()
    detected = _inspection_check(conn, refreshed, target, day)
    refreshed = conn.execute("SELECT * FROM smuggling_operations WHERE id=?", (int(op["id"]),)).fetchone()
    if target == int(refreshed["destination_location_id"]):
        _deliver_smuggling(conn, refreshed, day)
        if event_logger:
            event_logger(day=day,event_type="underworld:smuggling_arrived",title="Smuggling operation completed",
                         summary="Conserved cargo reached its destination through an illicit logistics operation.",severity=1,
                         source_actor_id=refreshed["organizer_institution_actor_id"],target_actor_ids=(),location_id=target)
        return True, detected
    return _begin_smuggling_leg(conn, int(op["id"]), day), detected


def _review_emergent_organizations(conn: sqlite3.Connection, day: int) -> tuple[int,int]:
    formed = updated = 0
    enterprises = conn.execute(
        """SELECT e.* FROM civilian_enterprises e
           WHERE e.status IN ('active','strained') AND e.institution_actor_id IS NULL"""
    ).fetchall()
    for ent in enterprises:
        eid = int(ent["id"])
        evs = conn.execute(
            "SELECT * FROM underworld_evidence WHERE subject_kind='enterprise' AND subject_id=? AND status='active' AND created_day<=? ORDER BY id",
            (eid, day-30),
        ).fetchall()
        kinds = {str(e["evidence_kind"]) for e in evs}
        if len(kinds) < 2:
            continue
        avg = sum(float(e["strength"]) for e in evs) / max(1,len(evs))
        score = min(75.0, 12.0 + len(kinds)*7.0 + avg*0.28 + min(10.0, math.log10(1.0+max(0.0,float(ent["capital"])+float(ent["cash"]))) * 4.0))
        candidate = conn.execute(
            "SELECT * FROM emergent_institution_candidates WHERE enterprise_id=? AND candidate_kind='criminal organization' AND status IN ('forming','eligible') ORDER BY id DESC LIMIT 1",
            (eid,),
        ).fetchone()
        evidence_payload = [{"evidence_id":int(e["id"]),"kind":str(e["evidence_kind"]),"visibility":str(e["visibility"]),"strength":float(e["strength"])} for e in evs]
        owner = int(ent["owner_actor_id"]) if ent["owner_actor_id"] is not None else None
        participants = [owner] if owner is not None else []
        resources = {"enterprise_id":eid,"capital":float(ent["capital"]),"cash":float(ent["cash"]),"location_id":ent["location_id"]}
        org = underworld_organization_for_enterprise(conn,eid)
        if org is not None:
            # Candidate significance and organization form are separate. A large gang remains a gang unless
            # an explicit historical transformation changes its institutional form.
            resources["organization_id"] = int(org["id"])
            resources["organization_type"] = str(org["organization_type"])
            resources["preexisting_organization"] = True
            resources["candidate_semantics"] = "tracking_preexisting_organization"
            resources["member_count_estimate"] = float(org["member_count_estimate"])
            resources["command_depth"] = int(org["command_depth"])
            resources["territorial_presence"] = float(org["territorial_presence"])
            resources["racket_breadth"] = float(org["racket_breadth"])
            resources["front_depth"] = float(org["front_depth"])
            resources["reputation_deterrence"] = float(org["reputation_deterrence"])
        if candidate is None:
            create_institution_candidate(
                conn,"criminal organization",location_id=ent["location_id"],enterprise_id=eid,founder_actor_id=owner,
                significance_score=score,resources=resources,participants=participants,evidence=evidence_payload,day=day,
            )
            # Newly-created candidates deliberately remain forming for this review; a later
            # sustained review may make them eligible. Formation is not instant crystallization.
            formed += 1
        else:
            existing_ids={int(x.get("evidence_id")) for x in json.loads(candidate["evidence_json"] or "[]") if isinstance(x,dict) and x.get("evidence_id") is not None}
            new_e = next((x for x in evidence_payload if int(x["evidence_id"]) not in existing_ids), None)
            update_institution_candidate(conn,int(candidate["id"]),significance_score=score,resources=resources,participants=participants,evidence_append=new_e,day=day)
            updated += 1
    return formed, updated


def _open_cases_from_visible_evidence(conn: sqlite3.Connection, day: int) -> int:
    opened = 0
    for ev in conn.execute("SELECT * FROM underworld_evidence WHERE status='active' AND visibility IN ('local','public') AND location_id IS NOT NULL ORDER BY id").fetchall():
        profiles = conn.execute("SELECT * FROM law_enforcement_profiles WHERE location_id=? AND status='active' ORDER BY id", (int(ev["location_id"]),)).fetchall()
        if not profiles:
            continue
        if str(ev["subject_kind"]) == "smuggling_operation":
            subject_kind, subject_id, allegation = "smuggling_operation", int(ev["subject_id"]), "smuggling/customs evasion"
        elif str(ev["subject_kind"]) == "enterprise":
            subject_kind, subject_id, allegation = "enterprise", int(ev["subject_id"]), str(ev["evidence_kind"])
        else:
            continue
        for p in profiles:
            prior = conn.execute(
                "SELECT id FROM law_enforcement_cases WHERE profile_id=? AND subject_kind=? AND subject_id=? AND allegation_kind=?",
                (int(p["id"]),subject_kind,subject_id,allegation),
            ).fetchone()
            if prior:
                continue
            initial = min(45.0, float(ev["strength"])*0.35)
            conn.execute(
                "INSERT INTO law_enforcement_cases(profile_id,subject_kind,subject_id,allegation_kind,evidence_score,status,opened_day,last_review_day,next_review_day,metadata_json) VALUES (?,?,?,?,?,'monitoring',?,?,?,?)",
                (int(p["id"]),subject_kind,subject_id,allegation,initial,day,day,day+14,_j({"opening_evidence_id":int(ev["id"]),"knowledge_boundary":"visible local evidence only"})),
            )
            opened += 1
    return opened


def _case_visible_evidence(conn: sqlite3.Connection, case: sqlite3.Row, location_id: int) -> float:
    rows = conn.execute(
        """SELECT strength FROM underworld_evidence WHERE status='active' AND visibility IN ('local','public')
           AND location_id=? AND subject_kind=? AND subject_id=?""",
        (location_id,str(case["subject_kind"]),int(case["subject_id"])),
    ).fetchall()
    return min(100.0, sum(float(r[0]) for r in rows))


def _ensure_law_action(conn: sqlite3.Connection, case_id: int, day: int, kind: str, score: float, metadata: dict[str,Any]) -> bool:
    before = conn.execute("SELECT 1 FROM law_enforcement_actions WHERE case_id=? AND action_kind=?", (case_id,kind)).fetchone()
    conn.execute("INSERT OR IGNORE INTO law_enforcement_actions(case_id,day,action_kind,evidence_score,metadata_json) VALUES (?,?,?,?,?)", (case_id,day,kind,score,_j(metadata)))
    return before is None


def _review_cases(conn: sqlite3.Connection, day: int, event_logger: Callable[...,int] | None = None) -> tuple[int,int]:
    reviewed = actions = 0
    cases = conn.execute(
        """SELECT c.*,p.location_id,p.capacity,p.integrity,p.corruption_pressure,p.name AS profile_name
           FROM law_enforcement_cases c JOIN law_enforcement_profiles p ON p.id=c.profile_id
           WHERE c.status IN ('monitoring','open','actionable') AND c.next_review_day<=? ORDER BY c.id""", (day,)
    ).fetchall()
    for c in cases:
        reviewed += 1
        visible = _case_visible_evidence(conn,c,int(c["location_id"]))
        effectiveness = max(0.15, (0.35 + float(c["capacity"])/180.0) * (0.65 + float(c["integrity"])/300.0) * (1.0 - float(c["corruption_pressure"])*0.004))
        gain = visible * 0.13 * effectiveness
        score = min(100.0, max(float(c["evidence_score"]), float(c["evidence_score"])+gain))
        status = "monitoring"
        if score >= 80: status = "referred"
        elif score >= 55: status = "actionable"
        elif score >= 30: status = "open"
        metadata={"jurisdiction_location_id":int(c["location_id"]),"visible_evidence":visible,"corruption_reduces_effectiveness_not_truth":True}
        if score >= 30: actions += int(_ensure_law_action(conn,int(c["id"]),day,"inquiry",score,metadata))
        if score >= 55: actions += int(_ensure_law_action(conn,int(c["id"]),day,"inspection",score,metadata))
        if score >= 80: actions += int(_ensure_law_action(conn,int(c["id"]),day,"referral",score,metadata))
        conn.execute("UPDATE law_enforcement_cases SET evidence_score=?,status=?,last_review_day=?,next_review_day=?,metadata_json=? WHERE id=?", (score,status,day,day+14,_j(metadata),int(c["id"])))
        if status == "referred" and event_logger:
            event_logger(day=day,event_type="law:case_referred",title="Local criminal case referred",
                         summary=f"{c['profile_name']} accumulated enough visible evidence to refer a case for further legal action.",severity=1,
                         source_actor_id=None,target_actor_ids=(),location_id=int(c["location_id"]))
    return reviewed, actions


def _autonomous_greyhook_smuggling(conn: sqlite3.Connection, day: int) -> int:
    greyhook = _institution(conn,"Greyhook Wharf Company")
    if greyhook is None:
        return 0
    profile = conn.execute("SELECT * FROM underworld_institution_profiles WHERE institution_actor_id=? AND status='active'", (greyhook,)).fetchone()
    if not profile:
        return 0
    ent = conn.execute("SELECT * FROM civilian_enterprises WHERE institution_actor_id=? AND (json_extract(metadata_json,'$.underworld_activation_key')='v037-greyhook-front' OR json_extract(metadata_json,'$.activation_key')='v037-greyhook-front') ORDER BY id LIMIT 1", (greyhook,)).fetchone()
    dest = _location(conn,"Aldergate")
    good = conn.execute("SELECT id FROM market_goods WHERE good_key='ordinary-cloth'").fetchone()
    if not ent or dest is None or not good:
        return 0
    meta = json.loads(profile["metadata_json"] or "{}")
    last = int(meta.get("last_smuggling_dispatch_day", -9999))
    if day - last < 75:
        return 0
    if conn.execute("SELECT 1 FROM smuggling_operations WHERE organizer_institution_actor_id=? AND status IN ('in_transit','stalled')", (greyhook,)).fetchone():
        return 0
    stock = conn.execute("SELECT quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?", (int(ent["id"]),int(ent["location_id"]),int(good[0]))).fetchone()
    if not stock or float(stock[0]) < 2.0:
        return 0
    opkey=f"greyhook-cloth-{day}"
    arrange_smuggling_operation(conn,int(ent["id"]),int(good[0]),2.0,dest,organizer_institution_actor_id=greyhook,
                                violation_kind="duty_evasion",concealment=68,operation_key=opkey,
                                metadata={"authority":"CAMPAIGN_CALIBRATION","basis":"MASTER FINAL explicitly identifies untaxed cloth among Greyhook smuggling cargo","not":"fixed literal annual volume"})
    meta["last_smuggling_dispatch_day"] = day
    conn.execute("UPDATE underworld_institution_profiles SET metadata_json=? WHERE institution_actor_id=?", (_j(meta),greyhook))
    return 1


def next_underworld_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    # v0.60 concrete organizations use their heat review clock as the autonomous monthly turn.
    try:
        from .underworld_rebuild import next_rebuild_underworld_due_day
        d = next_rebuild_underworld_due_day(conn, after_day, end_day)
        if d is not None: vals.append(int(d))
    except sqlite3.OperationalError:
        pass
    for sql in [
        "SELECT MIN(next_review_day) FROM underworld_institution_profiles WHERE status IN ('active','strained') AND next_review_day>? AND next_review_day<=?",
        "SELECT MIN(next_review_day) FROM law_enforcement_profiles WHERE status='active' AND next_review_day>? AND next_review_day<=?",
        "SELECT MIN(next_review_day) FROM smuggling_operations WHERE status IN ('in_transit','stalled') AND next_review_day>? AND next_review_day<=?",
        "SELECT MIN(next_review_day) FROM law_enforcement_cases WHERE status IN ('monitoring','open','actionable') AND next_review_day>? AND next_review_day<=?",
    ]:
        r=conn.execute(sql,(after_day,end_day)).fetchone()
        if r and r[0] is not None: vals.append(int(r[0]))
    return min(vals) if vals else None


def process_due_underworld(conn: sqlite3.Connection, day: int, *, event_logger: Callable[...,int] | None = None) -> dict[str,int]:
    profiles = conn.execute("SELECT * FROM underworld_institution_profiles WHERE status IN ('active','strained') AND next_review_day<=? ORDER BY institution_actor_id", (day,)).fetchall()
    law_profiles = conn.execute("SELECT * FROM law_enforcement_profiles WHERE status='active' AND next_review_day<=? ORDER BY id", (day,)).fetchall()
    synced = _sync_shadow_evidence(conn,day)
    dispatched = _autonomous_greyhook_smuggling(conn,day) if profiles else 0
    moved = detected = 0
    for op in conn.execute("SELECT * FROM smuggling_operations WHERE status IN ('in_transit','stalled') AND next_review_day<=? ORDER BY id", (day,)).fetchall():
        ch, det = _process_smuggling(conn,op,day,event_logger=event_logger); moved += int(ch); detected += int(det)
    formed, candidates_updated = _review_emergent_organizations(conn,day)
    cases_opened = _open_cases_from_visible_evidence(conn,day)
    cases_reviewed, law_actions = _review_cases(conn,day,event_logger=event_logger)
    rebuild = {}
    try:
        from .underworld_rebuild import process_due_rebuild_underworld
        rebuild = process_due_rebuild_underworld(conn, day, event_logger=event_logger)
    except sqlite3.OperationalError:
        rebuild = {}
    for p in profiles:
        conn.execute("UPDATE underworld_institution_profiles SET last_review_day=?,next_review_day=? WHERE institution_actor_id=?", (day,day+30,int(p["institution_actor_id"])))
    for p in law_profiles:
        conn.execute("UPDATE law_enforcement_profiles SET last_review_day=?,next_review_day=? WHERE id=?", (day,day+30,int(p["id"])))
    return {
        "underworld_profiles_due":len(profiles),"law_profiles_due":len(law_profiles),"shadow_evidence_synced":synced,
        "smuggling_dispatched":dispatched,"smuggling_moved":moved,"smuggling_detected":detected,
        "crime_candidates_formed":formed,"crime_candidates_updated":candidates_updated,"law_cases_opened":cases_opened,
        "law_cases_reviewed":cases_reviewed,"law_actions":law_actions,
        **rebuild,
    }


def underworld_summary(conn: sqlite3.Connection) -> dict[str,Any]:
    base = {
        "underworld_profiles":int(conn.execute("SELECT COUNT(*) FROM underworld_institution_profiles WHERE status IN ('active','strained')").fetchone()[0]),
        "smuggling_active":int(conn.execute("SELECT COUNT(*) FROM smuggling_operations WHERE status IN ('in_transit','stalled')").fetchone()[0]),
        "smuggling_delivered":int(conn.execute("SELECT COUNT(*) FROM smuggling_operations WHERE status='delivered'").fetchone()[0]),
        "smuggling_detected":int(conn.execute("SELECT COUNT(*) FROM smuggling_operations WHERE detected_day IS NOT NULL").fetchone()[0]),
        "crime_candidates":int(conn.execute("SELECT COUNT(*) FROM emergent_institution_candidates WHERE candidate_kind='criminal organization' AND status IN ('forming','eligible')").fetchone()[0]),
        "law_profiles":int(conn.execute("SELECT COUNT(*) FROM law_enforcement_profiles WHERE status='active'").fetchone()[0]),
        "law_cases":int(conn.execute("SELECT COUNT(*) FROM law_enforcement_cases WHERE status<>'closed'").fetchone()[0]),
        "law_actions":int(conn.execute("SELECT COUNT(*) FROM law_enforcement_actions").fetchone()[0]),
    }
    # v0.60 concrete rebuild summary. Aggregate values are read-models only; the counts below
    # expose the actual zones, crews, rackets, clients and operations now carrying the world.
    try:
        base.update({
            "criminal_organizations":int(conn.execute("SELECT COUNT(*) FROM underworld_organizations WHERE status IN ('active','strained','fragmented')").fetchone()[0]),
            "criminal_zones":int(conn.execute("SELECT COUNT(*) FROM underworld_zones WHERE status='active'").fetchone()[0]),
            "controlled_criminal_zones":int(conn.execute("SELECT COUNT(*) FROM underworld_zone_claims WHERE claim_kind='controller' AND status='active'").fetchone()[0]),
            "criminal_crews":int(conn.execute("SELECT COUNT(*) FROM underworld_crews WHERE status='active'").fetchone()[0]),
            "criminal_rackets":int(conn.execute("SELECT COUNT(*) FROM underworld_racket_sites WHERE status='active'").fetchone()[0]),
            "protection_accounts":int(conn.execute("SELECT COUNT(*) FROM underworld_protection_accounts WHERE status='active'").fetchone()[0]),
            "owned_fronts":int(conn.execute("SELECT COUNT(*) FROM underworld_business_links WHERE link_kind='owned_front' AND status='active'").fetchone()[0]),
            "underworld_operations":int(conn.execute("SELECT COUNT(*) FROM underworld_operations").fetchone()[0]),
            "underworld_enforcement_actions":int(conn.execute("SELECT COUNT(*) FROM underworld_enforcement_actions").fetchone()[0]),
        })
    except sqlite3.OperationalError:
        pass
    return base
```

## engine/crime_response.py

```python
"""Crime brings a law response (task B13): reports, publicity, cases, the arrangements' reach, arrests, dispositions and sentences.

Sphere-free. A crime is a `crime_reports` row (a harm row that someone could report, or a later sphere's own filing through
`open_report`: bribery, fraud, bid-rigging). Every figure comes from the package's law data (`law.json` "response"), each a Design
proposal with its reasoning; a logistic term there is a weighed pressure, never a threshold, and no outcome has a fixed share.

The chain: report -> `public_attention` (the weighed publicity, 0..100, a starting value the information layer will later move) ->
a case at the agency that takes the matter (and at the federal one when the victim is an officer) -> evidence -> the case officer and
the arrangements' reach (`org_arrangements` read where the offender is the payer or sits in the paying organisation) -> buried, an
arrest (`custody`), or open and reviewed -> bail -> a disposition (dismissed, plea, trial verdict) weighed from the evidence, a lawyer,
money, witness pressure and the arrangements -> on a conviction a `sentences` row and the man held until his scheduled release day,
which returns him. The organisations answer an arrest through `orgs` (his unit leader and head in every organisation where he sits
a seat get a `member_arrested` agenda item) and through the held-man decisions of the lifecycle process. Prison phase 1 will replace
the minimal disposition chain; the record shapes here are generic so it can extend them.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3

from . import orgs, org_motives
from .design import figure, run_seed
from .law_opening import agency_for
from .orgs import add_agenda, imposed, resolve_agenda
from .org_choices import register_agenda_action, register_executor
from .world_package import law_rules, package_for

DDL = """
CREATE TABLE IF NOT EXISTS public_attention (
    report_id INTEGER PRIMARY KEY REFERENCES crime_reports(id) ON DELETE CASCADE,
    publicity REAL NOT NULL,
    loudness REAL NOT NULL,
    audience_json TEXT NOT NULL DEFAULT '{}',
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS case_dispositions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    report_id INTEGER,
    actor_id INTEGER,
    day INTEGER NOT NULL,
    kind TEXT NOT NULL,
    factors_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS sentences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id),
    case_id INTEGER,
    report_id INTEGER,
    disposition_id INTEGER,
    crime_kind TEXT NOT NULL,
    victim_actor_id INTEGER,
    location_id INTEGER,
    term_days INTEGER NOT NULL,
    start_day INTEGER NOT NULL,
    earliest_release_day INTEGER NOT NULL,
    end_day INTEGER NOT NULL,
    facility TEXT,
    status TEXT NOT NULL DEFAULT 'serving',
    released_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sentences_release ON sentences(status, earliest_release_day);
CREATE INDEX IF NOT EXISTS idx_sentences_actor ON sentences(actor_id, status);
CREATE INDEX IF NOT EXISTS idx_case_dispositions_case ON case_dispositions(case_id);
"""

CURSOR_KEY = "crime_response_harm_cursor"
_READY: dict = {"key": None}


def ensure_tables(conn: sqlite3.Connection) -> None:
    """The three tables this layer adds (also created by the schema; a no-op once they exist)."""
    key = org_motives.db_key(conn)
    if _READY["key"] != key:
        fresh = conn.execute("SELECT 1 FROM engine_meta WHERE key=?", (CURSOR_KEY,)).fetchone() is None  # the tables come with the schema, so the cursor says whether this layer has run here
        for stmt in DDL.split(";"):  # not executescript: that commits, and a time skip is running inside a savepoint
            if stmt.strip():
                conn.execute(stmt)
        if fresh:  # a campaign that predates this layer: what was already done is not prosecuted after the fact
            conn.execute("INSERT INTO engine_meta(key,value) VALUES (?, CAST((SELECT COALESCE(MAX(id),0) FROM harm_incidents WHERE day < (SELECT current_day FROM world_state WHERE id=1)) AS TEXT)) ON CONFLICT(key) DO NOTHING", (CURSOR_KEY,))
        _READY["key"] = key


# ---- data ----

def _cfg(conn: sqlite3.Connection) -> dict:
    return law_rules(package_for(conn)).get("response") or {}


def _n(spec, default: float | None = None) -> float:
    """A number as written, or `{"value": n, ...}` with its reasoning."""
    if isinstance(spec, dict):
        spec = spec.get("value")
    if spec is None:
        if default is None:
            raise KeyError("a figure the law data should give is missing")
        return float(default)
    return float(spec)


def _rng(conn: sqlite3.Connection, stream: str, key) -> random.Random:
    return random.Random(f"{run_seed(conn)}:crime:{stream}:{key}")


def _meta(row) -> dict:
    try:
        return json.loads(row["metadata_json"] or "{}")
    except (ValueError, TypeError):
        return {}


def _logit(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _name(conn: sqlite3.Connection, actor_id) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(actor_id),)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def _living(conn: sqlite3.Connection, actor_id) -> bool:
    return actor_id is not None and orgs.is_living(conn, int(actor_id))


def _orgs_of(conn: sqlite3.Connection, actor_id) -> list[int]:
    if actor_id is None:
        return []
    return sorted({int(s["org_actor_id"]) for s in orgs.seats_of(conn, int(actor_id)) if s["status"] in ("active", "held")})


# ---- who is who in the law's eyes ----

def _police_institutions(conn: sqlite3.Connection) -> set[int]:
    return {int(r[0]) for r in conn.execute("SELECT institution_actor_id FROM law_enforcement_profiles WHERE institution_actor_id IS NOT NULL")}


def is_officer(conn: sqlite3.Connection, actor_id) -> bool:
    """A member of any institution that a law enforcement profile stands for."""
    if actor_id is None:
        return False
    return conn.execute(
        """SELECT 1 FROM institution_memberships m JOIN law_enforcement_profiles p ON p.institution_actor_id=m.institution_actor_id
           WHERE m.member_actor_id=? AND m.status='active' LIMIT 1""", (int(actor_id),)).fetchone() is not None


def _notable(conn: sqlite3.Connection, victim, spec: dict) -> tuple[float, str | None]:
    """How notable the victim is (0..1: the largest of the kinds he is) and which kind."""
    best, which = 0.0, None
    if victim is None:
        return best, which
    for key, k in sorted(spec.items()):
        x = _n(k.get("x"), 0.0)
        if x <= best:
            continue
        hit = False
        if key == "officer":
            hit = is_officer(conn, victim)
        elif key == "reporter":
            names = list(k.get("institutions") or [])
            if names:
                hit = conn.execute(
                    "SELECT 1 FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id WHERE m.member_actor_id=? AND m.status='active' AND i.name IN (%s) LIMIT 1"
                    % ",".join("?" * len(names)), (int(victim), *names)).fetchone() is not None
        elif key == "office_holder":
            hit = conn.execute("SELECT 1 FROM world_facts WHERE holder_actor_id=? AND key LIKE ? LIMIT 1", (int(victim), str(k.get("fact_prefix") or "") + "%")).fetchone() is not None
        elif key == "inducted":
            hit = conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND inducted_day IS NOT NULL LIMIT 1", (int(victim),)).fetchone() is not None
        if hit:
            best, which = x, key
    return best, which


# ---- publicity ----

def _publicity(conn: sqlite3.Connection, *, key, victim, location_id, declared_public: bool, meta: dict, victims_n: int, bystander: bool) -> dict:
    pc = _cfg(conn).get("publicity") or {}
    if not pc:
        return {"publicity": 100.0 if declared_public else 0.0, "drivers": {}, "witnesses": 0}
    w = pc["weights"]
    rng = _rng(conn, "publicity", key)
    kind = None
    if location_id is not None:
        r = conn.execute("SELECT kind FROM locations WHERE id=?", (int(location_id),)).fetchone()
        kind = r[0] if r else None
    hour = meta.get("hour")
    if hour is None:
        hour = rng.choices(range(len(pc["hour_weights"])), weights=pc["hour_weights"])[0]
    hour = int(hour) % len(pc["hour_exposure"])
    traffic = float(pc["hour_exposure"][hour])
    crowd = float(pc["place_crowd"].get(kind, pc["place_crowd"]["default"]))
    seen = _poisson(rng, crowd * traffic)
    notable, notable_kind = _notable(conn, victim, pc.get("notable") or {})
    method = meta.get("method")
    x = {
        "declared_public": 1.0 if declared_public else 0.0,
        "witnesses": 1.0 - math.exp(-seen / float(pc["witness_scale"])),
        "place": float(pc["place_exposure"].get(kind, pc["place_exposure"]["default"])),
        "time_of_day": traffic,
        "bystander": 1.0 if bystander else 0.0,
        "notable_victim": notable,
        "method": float(pc["method"].get(method, pc["method"]["default"])),
        "victims": 1.0 - math.exp(-max(0, victims_n - 1) / float(pc["victims_scale"])),
    }
    rest = 1.0
    for name, xi in x.items():
        rest *= 1.0 - _n(w.get(name), 0.0) * xi
    return {"publicity": round(100.0 * (1.0 - rest), 3), "drivers": {k: round(v, 4) for k, v in x.items()}, "witnesses": seen, "hour": hour,
            "place_kind": kind, "notable_kind": notable_kind, "officer_victim": notable_kind == "officer"}


def publicity_of(conn: sqlite3.Connection, report_id: int) -> float:
    """The report's publicity, 0..100: the public attention record's loudness when there is one (the information layer may have moved
    it), else the starting value in the report's metadata, else 0."""
    ensure_tables(conn)
    r = conn.execute("SELECT loudness FROM public_attention WHERE report_id=?", (int(report_id),)).fetchone()
    if r is not None:
        return float(r[0])
    r = conn.execute("SELECT metadata_json FROM crime_reports WHERE id=?", (int(report_id),)).fetchone()
    return float(_meta(r).get("publicity") or 0.0) if r is not None else 0.0


# ---- filing a report ----

def open_report(conn: sqlite3.Connection, *, crime_kind: str, day: int, offender_actor_id: int | None = None, victim_actor_id: int | None = None,
                location_id: int | None = None, public: bool = False, metadata: dict | None = None) -> int:
    """File a crime and run the law's first response to it (a case at the agency that takes this kind of matter, evidence, the
    arrangements' reach, an arrest or an open case). Later spheres call this for fraud, bribery and bid-rigging with no harm row."""
    ensure_tables(conn)
    meta = dict(metadata or {})
    harm_id = meta.get("harm_incident_id")
    if location_id is None and victim_actor_id is not None:
        r = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(victim_actor_id),)).fetchone()
        location_id = r[0] if r else None
    key = f"{harm_id}" if harm_id is not None else f"{crime_kind}:{day}:{offender_actor_id}:{victim_actor_id}:{location_id}"
    pub = _publicity(conn, key=key, victim=victim_actor_id, location_id=location_id, declared_public=bool(public), meta=meta,
                     victims_n=int(meta.get("victims") or 1), bystander=bool(meta.get("bystander")))
    meta.update(publicity=pub["publicity"], publicity_drivers=pub["drivers"], witnesses=pub["witnesses"], hour=pub.get("hour"),
                notable_victim=pub.get("notable_victim") or pub.get("notable_kind"), officer_victim=bool(pub.get("officer_victim")))
    if offender_actor_id is not None and harm_id is not None and "identified" not in meta and _cfg(conn).get("identification"):
        meta["identified"] = _identified_at_filing(conn, int(harm_id), int(day), offender_actor_id, victim_actor_id, pub)
    rid = int(conn.execute(
        """INSERT INTO crime_reports(day,harm_incident_id,crime_kind,location_id,victim_actor_id,offender_actor_id,public,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,'open',?)""",
        (int(day), harm_id, crime_kind, location_id, victim_actor_id, offender_actor_id, 1 if public else 0, json.dumps(meta, sort_keys=True, default=str))).lastrowid)
    audience = {"witnesses": pub["witnesses"], "place": location_id, "place_kind": pub.get("place_kind"),
                "orgs": sorted(set(_orgs_of(conn, offender_actor_id)) | set(_orgs_of(conn, victim_actor_id))),
                "scope": "place" if pub["publicity"] < 50 else "city"}
    conn.execute("INSERT OR REPLACE INTO public_attention(report_id,publicity,loudness,audience_json,updated_day,metadata_json) VALUES (?,?,?,?,?,?)",
                 (rid, pub["publicity"], pub["publicity"], json.dumps(audience, sort_keys=True), int(day), json.dumps({"drivers": pub["drivers"]}, sort_keys=True)))
    _respond(conn, rid, int(day))
    return rid


def _organised(conn: sqlite3.Connection, actor_id) -> float:
    """1 when the man holds a seat in any organisation, else 0."""
    return 1.0 if _orgs_of(conn, actor_id) else 0.0


def _identified_at_filing(conn: sqlite3.Connection, harm_id: int, day: int, offender, victim, pub: dict) -> bool:
    """Whether the law has the offender's name when the crime is filed (data `identification`): the witnesses and the loudness of the
    story raise it, an organised man's work and a victim from the same world lower it."""
    c = _cfg(conn)["identification"]
    x = pub.get("drivers") or {}
    z = (_n(c["bias"]) + _n(c["witnesses"]) * float(x.get("witnesses") or 0.0) + _n(c["publicity"]) * float(pub["publicity"]) / 100.0
         + _n(c["offender_organised"]) * _organised(conn, offender) + _n(c["victim_organised"]) * _organised(conn, victim))
    return org_motives._roll(conn, harm_id, day, "identify") < _logit(z)  # drawn as the arrangements' roll is, so a test can pin it


def _knows_offender(conn: sqlite3.Connection, rep) -> bool:
    """The report names an offender the law has: no offender, or one nobody has yet put a name to, is no one."""
    if rep["offender_actor_id"] is None:
        return False
    return bool(_meta(rep).get("identified", True))


# ---- agencies, officers, the arrangements' reach ----

def _agency_rule(conn: sqlite3.Connection, profile) -> dict:
    return (law_rules(package_for(conn)).get("agencies") or {}).get(profile["profile_key"], {})


def _threshold(conn: sqlite3.Connection, kind: str) -> float:
    rules = law_rules(package_for(conn)).get("rules") or {}
    spec = (rules.get(kind) or {}).get("evidence_threshold")
    if spec is None:
        return _n(_cfg(conn)["arrest"]["evidence"]["default_threshold"])
    if isinstance(spec, (int, float, dict)):
        return _n(spec)
    return float(figure(conn, spec))


def _review_days(conn: sqlite3.Connection, kind: str) -> int:
    rules = law_rules(package_for(conn)).get("rules") or {}
    spec = (rules.get(kind) or {}).get("review_days")
    return int(_n(spec)) if spec is not None else int(figure(conn, "case_review_days"))


def _effort(conn: sqlite3.Connection, profile, pub: float, officer_victim: bool) -> float:
    e = _cfg(conn)["arrest"]["effort"]
    rest = (1.0 - _n(e["base"])) * (1.0 - _n(e["publicity"]) * pub / 100.0) * (1.0 - (_n(e["officer_victim"]) if officer_victim else 0.0))
    return float(profile["capacity"]) / 100.0 * (1.0 - rest)


def case_officer(conn: sqlite3.Connection, profile, key) -> int | None:
    """The officer who catches a case at an agency: a seeded draw among the institution's living members weighted by role."""
    inst = profile["institution_actor_id"]
    if inst is None:
        return None
    roles = _cfg(conn)["arrest"]["officer_roles"]
    pool: list[tuple[int, float]] = []
    for r in conn.execute("SELECT member_actor_id,role_text FROM institution_memberships WHERE institution_actor_id=? AND status='active' ORDER BY member_actor_id", (int(inst),)):
        wt = max((_n(x["weight"]) for x in roles if str(r["role_text"] or "").startswith(x["prefix"])), default=0.0)
        if wt > 0 and orgs.is_living(conn, int(r[0])):
            pool.append((int(r[0]), wt))
    if not pool:
        return None
    return _rng(conn, "officer", f"{profile['id']}:{key}").choices([a for a, _ in pool], weights=[w for _, w in pool])[0]


def _envelope(conn: sqlite3.Connection, officer: int, offender: int):
    """An active arrangement paid to this officer by the offender or by an organisation he sits in."""
    mine = _orgs_of(conn, offender)
    return conn.execute(
        """SELECT * FROM org_arrangements WHERE official_actor_id=? AND status='active' AND
             ((payer_kind='actor' AND payer_id=?) OR (payer_kind='org' AND payer_id IN (%s))) ORDER BY id LIMIT 1""" % (",".join("?" * len(mine)) or "NULL"),
        (int(officer), int(offender), *mine)).fetchone()


def pad_reaches(conn: sqlite3.Connection, profile, officer: int | None, offender: int | None) -> bool:
    """Whether the arrangements reach this case: the agency is one they reach and its case officer holds an envelope from the offender
    (or the organisation he sits in)."""
    if officer is None or offender is None or not _agency_rule(conn, profile).get("arrangements_reach"):
        return False
    return _envelope(conn, int(officer), int(offender)) is not None


def _bought(conn: sqlite3.Connection, profile, officer, offender, kind: str, pub: float, officer_victim: bool, rid: int, day: int) -> bool:
    """The arrangements bury a case they reach, weighed: a homicide detective may be one of the honest ones (the package's share), and
    publicity and a killed officer resist, very strongly but never absolutely."""
    if not pad_reaches(conn, profile, officer, offender):
        return False
    c = _cfg(conn)
    limits = law_rules(package_for(conn)).get("pad_limits") or {}
    if kind == c["harm"]["fatal_kind"] and limits.get("honest_homicide_figure"):
        if org_motives._roll(conn, rid, day, "honest") < float(figure(conn, limits["honest_homicide_figure"])):
            return False
    p = c["arrest"]["arrangements"]
    resist = 1.0 - (1.0 - _n(p["publicity_resistance"]) * pub / 100.0) * (1.0 - (_n(p["officer_victim_resistance"]) if officer_victim else 0.0))
    return org_motives._roll(conn, rid, day, "pad_publicity") >= resist


# ---- cases ----

def _open_case(conn: sqlite3.Connection, profile, rid: int, kind: str, offender, victim, day: int, evidence: float, officer, note: dict) -> int:
    meta = {"crime_report_id": rid, "officer": officer, "victim": victim, "crime_kind": kind, **note}
    subject = int(offender) if offender is not None else -int(rid)  # no offender known: the case is about the event, keyed by the report
    args = (int(profile["id"]), "actor", subject)
    status = "open" if offender is not None else "monitoring"
    nxt = int(day) + _review_days(conn, kind)
    last: Exception = sqlite3.IntegrityError("case could not be filed")
    for allegation in (kind, f"{kind}:{rid}"):
        try:
            return int(conn.execute(
                """INSERT INTO law_enforcement_cases(profile_id,subject_kind,subject_id,allegation_kind,evidence_score,status,opened_day,last_review_day,next_review_day,metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""", (*args, allegation, round(min(100.0, max(0.0, 100.0 * evidence)), 3), status, int(day), int(day), nxt, json.dumps(meta, sort_keys=True))).lastrowid)
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" not in str(exc):
                raise
            last = exc
    raise last


def _respond(conn: sqlite3.Connection, rid: int, day: int) -> None:
    rep = conn.execute("SELECT * FROM crime_reports WHERE id=?", (rid,)).fetchone()
    meta, kind = _meta(rep), rep["crime_kind"]
    offender, victim, loc = (rep["offender_actor_id"] if _knows_offender(conn, rep) else None), rep["victim_actor_id"], rep["location_id"]
    actual = rep["offender_actor_id"]  # a paid precinct steers away from its payer before he is named: the arrangements look at the man who did it
    pub = float(meta.get("publicity") or 0.0)
    officer_victim = bool(meta.get("officer_victim"))
    primary = agency_for(conn, loc, kind)
    profiles = []
    if primary is not None:
        profiles.append(int(primary))
    if officer_victim and _cfg(conn)["arrest"].get("officer_victim_federal"):
        fed = agency_for(conn, loc, kind, federal=True)
        if fed is not None and int(fed) not in profiles:
            profiles.append(int(fed))
    if not profiles:
        meta["unrouted"] = True
        conn.execute("UPDATE crime_reports SET status='closed', metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), rid))
        return
    ev = _cfg(conn)["arrest"]["evidence"]
    rows = []
    for pid in profiles:
        prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE id=?", (pid,)).fetchone()
        effort = _effort(conn, prof, pub, officer_victim)
        noise = (_rng(conn, "evidence", f"{rid}:{pid}").random() * 2.0 - 1.0) * _n(ev["noise"])
        score = _n(ev["base"]) + _n(ev["publicity"]) * pub / 100.0 + (_n(ev["offender_known"]) if offender is not None else 0.0) + _n(ev["effort"]) * effort + noise
        officer = case_officer(conn, prof, rid)
        bought = _bought(conn, prof, officer, actual, kind, pub, officer_victim, rid, day)
        cid = _open_case(conn, prof, rid, kind, offender, victim, day, score, officer,
                         {"effort": round(effort, 4), "bought": bool(bought), **({"co_defendants": meta["co_defendants"]} if meta.get("co_defendants") else {})})
        if bought:
            conn.execute("UPDATE law_enforcement_cases SET status='closed', closed_day=? WHERE id=?", (int(day), cid))
            m = json.loads(conn.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (cid,)).fetchone()[0])
            m["reason"] = "arrangements"
            conn.execute("UPDATE law_enforcement_cases SET metadata_json=? WHERE id=?", (json.dumps(m, sort_keys=True), cid))
        rows.append({"case": cid, "profile": prof, "score": score, "bought": bought})
    meta["case_ids"] = [r["case"] for r in rows]
    first = rows[0]
    conn.execute("UPDATE crime_reports SET jurisdiction_id=NULL, agency_profile_id=?, case_id=?, metadata_json=? WHERE id=?",
                 (int(first["profile"]["id"]), first["case"], json.dumps(meta, sort_keys=True), rid))
    if offender is not None and _living(conn, offender):
        for r in rows:
            if not r["bought"] and r["score"] >= _threshold(conn, kind):
                _arrest(conn, rid, r["case"], r["profile"], int(offender), int(day))
                return
    if rows and all(r["bought"] for r in rows):
        meta["reason"] = "arrangements"
        conn.execute("UPDATE crime_reports SET status='buried', metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), rid))


# ---- arrest, bail, disposition, sentence, release ----

def _set_case_meta(conn: sqlite3.Connection, case_id: int, **kv) -> dict:
    row = conn.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (int(case_id),)).fetchone()
    m = json.loads(row[0] or "{}")
    m.update(kv)
    conn.execute("UPDATE law_enforcement_cases SET metadata_json=? WHERE id=?", (json.dumps(m, sort_keys=True, default=str), int(case_id)))
    return m


def _lognormal_days(conn: sqlite3.Connection, table: dict, kind: str, stream: str, key) -> int:
    spec = table.get(kind) or table["default"]
    return max(1, int(round(_n(spec["median"]) * math.exp(_n(spec["sigma"]) * _rng(conn, stream, key).gauss(0.0, 1.0)))))


def _arrest(conn: sqlite3.Connection, rid: int, case_id: int, profile, offender: int, day: int) -> None:
    c = _cfg(conn)
    rep = conn.execute("SELECT * FROM crime_reports WHERE id=?", (rid,)).fetchone()
    kind, meta = rep["crime_kind"], _meta(rep)
    bailable = c["arrest"]["bail"]["bailable"]
    bail_day = int(day) + int(figure(conn, "bail_days")) if bailable.get(kind, bailable["default"]) else None
    dispo = int(day) + _lognormal_days(conn, c["disposition"]["days"], kind, "dispo", rid)
    conn.execute("INSERT INTO custody(actor_id,case_id,agency_profile_id,kind,charge,since_day,until_day) VALUES (?,?,?,'held',?,?,NULL)",
                 (offender, case_id, int(profile["id"]), kind, int(day)))
    stage_day = bail_day if bail_day is not None else dispo
    with_him = []  # co-defendants on the one case: the men a sweep named with him are held on it as he is
    for co in (_meta_of_case(conn, case_id).get("co_defendants") or []):
        if int(co) != offender and _living(conn, co) and conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held' AND case_id IS NOT NULL LIMIT 1", (int(co),)).fetchone() is None:
            conn.execute("INSERT INTO custody(actor_id,case_id,agency_profile_id,kind,charge,since_day,until_day) VALUES (?,?,?,'held',?,?,NULL)", (int(co), case_id, int(profile["id"]), kind, int(day)))
            with_him.append(int(co))
    _set_case_meta(conn, case_id, stage="bail" if bail_day is not None else "disposition", bail_day=bail_day, disposition_day=dispo, arrest_day=int(day), arrested=offender, held_with=with_him)
    conn.execute("UPDATE law_enforcement_cases SET status='actionable', next_review_day=?, evidence_score=MAX(evidence_score,?) WHERE id=?",
                 (stage_day, float(conn.execute("SELECT evidence_score FROM law_enforcement_cases WHERE id=?", (case_id,)).fetchone()[0]), case_id))
    meta["arrest_day"] = int(day)
    conn.execute("UPDATE crime_reports SET status='arrest', metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), rid))
    _answer_arrest(conn, rid, case_id, offender, kind, int(day), float(meta.get("publicity") or 0.0))
    for co in with_him:
        _answer_arrest(conn, rid, case_id, co, kind, int(day), float(meta.get("publicity") or 0.0))


def _meta_of_case(conn: sqlite3.Connection, case_id: int) -> dict:
    row = conn.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (int(case_id),)).fetchone()
    return json.loads(row[0] or "{}") if row else {}


def _answer_arrest(conn: sqlite3.Connection, rid: int, case_id: int, offender: int, kind: str, day: int, pub: float) -> None:
    """What an arrest sets going: he is looked at tomorrow, his history is flagged, his organisations' heat rises, and his unit leader and
    head in each organisation where he holds a seat have `member_arrested` on their list."""
    from .org_lifecycle import mark_for_history
    imposed(conn, offender)
    mark_for_history(conn, offender, "was arrested", day)
    delay = int(_n(_cfg(conn)["arrest"]["respond_delay_days"]))
    seen: set[tuple[int, int]] = set()
    for org in _orgs_of(conn, offender):
        for who in (orgs.unit_leader_of(conn, offender, org), orgs.head_of(conn, org)):
            if who is None or int(who) == offender or (int(who), org) in seen or not _living(conn, who):
                continue
            seen.add((int(who), org))
            add_agenda(conn, int(who), "member_arrested", day + delay, subject_kind="actor", subject_id=offender,
                       metadata={"held": offender, "org": org, "case": case_id, "report": rid, "charge": kind})
    _heat(conn, offender, day, pub)


def _heat(conn: sqlite3.Connection, offender: int, day: int, pub: float) -> None:
    try:
        from . import org_heat
        if not org_heat.enabled(conn):
            return
    except (ImportError, sqlite3.OperationalError):
        return
    h = _cfg(conn)["arrest"]["heat"]
    own, city = org_heat._v(conn, org_heat._data(conn).get("own_full"), 1.0), org_heat._v(conn, org_heat._data(conn).get("city_full"), 1.0)
    for org in _orgs_of(conn, offender):
        org_heat.add(conn, org, day, investigative=_n(h["investigative_share"]) * own, public=_n(h["public_share"]) * city * pub / 100.0)


def _void_envelopes(conn: sqlite3.Connection, day: int) -> int:
    """A precinct whose commander has changed no longer has the envelope its old commander took: the arrangement is reopened (to be
    renegotiated). Read from the institution's membership: the first-tier envelope whose official is no longer a current commander."""
    c = _cfg(conn)["arrest"]
    tier = c["commander_tier"]
    prefix = c["commander_role_prefix"]
    n = 0
    for e in conn.execute("SELECT * FROM org_arrangements WHERE status='active' AND position_key LIKE ?", (f"%:{tier}:1",)).fetchall():
        row = conn.execute("SELECT institution_actor_id FROM institution_memberships WHERE member_actor_id=? AND role_text LIKE ? ORDER BY status='active' DESC LIMIT 1", (e["official_actor_id"], prefix + "%")).fetchone()
        if row is None:
            continue
        holders = {int(r[0]) for r in conn.execute("SELECT member_actor_id FROM institution_memberships WHERE institution_actor_id=? AND status='active' AND role_text LIKE ?", (row[0], prefix + "%"))}
        if holders and int(e["official_actor_id"]) not in holders:
            conn.execute("UPDATE org_arrangements SET status='reopened', ended_day=? WHERE id=?", (int(day), e["id"]))
            n += 1
    return n


def _intake(conn: sqlite3.Connection, day: int) -> int:
    c = _cfg(conn)
    h = c.get("harm") or {}
    if not h:
        return 0
    row = conn.execute("SELECT value FROM engine_meta WHERE key=?", (CURSOR_KEY,)).fetchone()
    cursor = int(row[0]) if row else 0
    top = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM harm_incidents").fetchone()[0])
    if top <= cursor:
        return 0
    intents = list(h["intents"]) + list(h["bystander_intents"])
    n = 0
    for r in conn.execute("SELECT * FROM harm_incidents WHERE id>? AND id<=? AND intent_class IN (%s) ORDER BY id" % ",".join("?" * len(intents)), (cursor, top, *intents)).fetchall():
        meta = _meta(r)
        if meta.get("crime") is False:
            continue
        offender = meta.get("offender_actor_id")
        bystander = r["intent_class"] in h["bystander_intents"]
        if bystander and offender is None:
            continue  # a plain accident is no one's crime
        if offender is not None and int(offender) == int(r["actor_id"]):
            continue
        near = conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE source_ref_id=? AND day=? AND intent_class IN (%s)" % ",".join("?" * len(intents)),
                            (r["source_ref_id"], r["day"], *intents)).fetchone()[0]
        others_hurt = conn.execute("SELECT 1 FROM harm_incidents WHERE source_ref_id=? AND day=? AND intent_class IN (%s) AND actor_id<>? LIMIT 1" % ",".join("?" * len(h["bystander_intents"])),
                                   (r["source_ref_id"], r["day"], *h["bystander_intents"], r["actor_id"])).fetchone()
        kind = h["fatal_kind"] if r["fatal"] else h["other_kind"]
        open_report(conn, crime_kind=kind, day=int(r["day"]), offender_actor_id=int(offender) if offender is not None else None, victim_actor_id=int(r["actor_id"]),
                    location_id=r["location_id"], public=bool(meta.get("public")),
                    metadata={"harm_incident_id": int(r["id"]), "method": meta.get("method"), "victims": int(near), "bystander": bool(bystander or others_hurt),
                              "source_kind": r["source_kind"]})
        n += 1
    conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (CURSOR_KEY, str(top)))
    return n


def _reviews(conn: sqlite3.Connection, day: int) -> int:
    """Open cases whose review has come: the work adds evidence (scaled by the effort and noise); an arrest follows when the offender is
    known and the evidence passes the kind's threshold (the arrangements may still bury it); a case not solved in `case_close_days` closes."""
    c = _cfg(conn)["arrest"]
    n = 0
    for cs in conn.execute("""SELECT * FROM law_enforcement_cases WHERE status IN ('monitoring','open') AND next_review_day<=?
                              AND json_extract(metadata_json,'$.crime_report_id') IS NOT NULL ORDER BY id""", (int(day),)).fetchall():
        m = _meta(cs)
        rep = conn.execute("SELECT * FROM crime_reports WHERE id=?", (m["crime_report_id"],)).fetchone()
        if rep is None:
            continue
        kind, offender = rep["crime_kind"], rep["offender_actor_id"]
        pub = publicity_of(conn, rep["id"])
        rng = _rng(conn, "review", f"{cs['id']}:{day}")
        named = 0.0
        if offender is not None and not _knows_offender(conn, rep):  # the work may put a name to it
            rate = _n(_cfg(conn)["identification"]["review_rate"]) * float(m.get("effort") or 0.0)
            if org_motives._roll(conn, int(rep["id"]), int(day), "name") < rate:
                rm = _meta(rep)
                named = _n(c["evidence"]["offender_known"])  # the name is evidence like any other
                rm.update(identified=True, identified_day=int(day))
                conn.execute("UPDATE crime_reports SET metadata_json=? WHERE id=?", (json.dumps(rm, sort_keys=True, default=str), rep["id"]))
            else:
                offender = None
        gain = (_n(c["review"]["gain"]) + (rng.random() * 2.0 - 1.0) * _n(c["review"]["noise"])) * float(m.get("effort") or 0.0)
        score = float(cs["evidence_score"]) / 100.0 + gain + named
        prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE id=?", (cs["profile_id"],)).fetchone()
        conn.execute("UPDATE law_enforcement_cases SET evidence_score=?, last_review_day=? WHERE id=?", (round(min(100.0, max(0.0, 100.0 * score)), 3), int(day), cs["id"]))  # the column's own 0-100 domain; the test below uses the unbounded score
        n += 1
        if offender is not None and _living(conn, offender) and score >= _threshold(conn, kind):
            if _bought(conn, prof, m.get("officer"), int(offender), kind, pub, bool(_meta(rep).get("officer_victim")), int(rep["id"]), int(day)):
                conn.execute("UPDATE law_enforcement_cases SET status='closed', closed_day=? WHERE id=?", (int(day), cs["id"]))
                _set_case_meta(conn, cs["id"], reason="arrangements")
                if conn.execute("SELECT COUNT(*) FROM law_enforcement_cases WHERE json_extract(metadata_json,'$.crime_report_id')=? AND status<>'closed'", (rep["id"],)).fetchone()[0] == 0:
                    conn.execute("UPDATE crime_reports SET status='buried' WHERE id=? AND status='open'", (rep["id"],))
                continue
            if rep["status"] in ("open",):
                _arrest(conn, int(rep["id"]), int(cs["id"]), prof, int(offender), int(day))
                continue
        if int(day) - int(cs["opened_day"]) >= int(figure(conn, "case_close_days")):
            conn.execute("UPDATE law_enforcement_cases SET status='closed', closed_day=? WHERE id=?", (int(day), cs["id"]))
            _set_case_meta(conn, cs["id"], reason="unsolved")
            if conn.execute("SELECT COUNT(*) FROM law_enforcement_cases WHERE json_extract(metadata_json,'$.crime_report_id')=? AND status<>'closed'", (rep["id"],)).fetchone()[0] == 0 and rep["status"] == "open":
                conn.execute("UPDATE crime_reports SET status='closed' WHERE id=?", (rep["id"],))
        else:
            conn.execute("UPDATE law_enforcement_cases SET next_review_day=? WHERE id=?", (int(day) + _review_days(conn, kind), cs["id"]))
    return n


def _stage_cases(conn: sqlite3.Connection, day: int):
    return conn.execute("""SELECT * FROM law_enforcement_cases WHERE status='actionable' AND next_review_day<=?
                           AND json_extract(metadata_json,'$.crime_report_id') IS NOT NULL ORDER BY id""", (int(day),)).fetchall()


def _bail(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    for cs in _stage_cases(conn, day):
        m = _meta(cs)
        if m.get("stage") != "bail":
            continue
        for a in [int(m["arrested"]), *[int(x) for x in m.get("held_with") or []]]:
            conn.execute("UPDATE custody SET kind='bailed', until_day=? WHERE case_id=? AND actor_id=? AND kind='held'", (int(day), cs["id"], a))
            imposed(conn, a)  # he is out: looked at tomorrow
        _set_case_meta(conn, cs["id"], stage="disposition", bailed_day=int(day))
        conn.execute("UPDATE law_enforcement_cases SET next_review_day=? WHERE id=?", (int(m["disposition_day"]), cs["id"]))
        n += 1
    return n


def _lawyer(conn: sqlite3.Connection, m: dict) -> float:
    half = _n(_cfg(conn)["backing"]["lawyer_half_fee"])
    fee = float(m.get("lawyer_fee") or 0.0)
    return fee / (fee + half) if fee > 0 else 0.0


def _witness_pressure(conn: sqlite3.Connection, offender: int, rep_meta: dict, day: int) -> float:
    try:
        from . import org_heat
        if not org_heat.enabled(conn):
            return 0.0
        own = max((org_heat.own_factor(conn, o, day) for o in _orgs_of(conn, offender)), default=0.0)
    except (ImportError, sqlite3.OperationalError):
        return 0.0
    seen = float(rep_meta.get("witnesses") or 0)
    share = 1.0 - math.exp(-seen / float(_cfg(conn)["publicity"]["witness_scale"]))
    return share * own


def _facility(conn: sqlite3.Connection, profile, term: int) -> str:
    f = _cfg(conn)["sentence"]["facilities"]
    spec = f.get(profile["authority_kind"]) or f.get("municipal")
    return str(spec["short"] if term <= int(_n(spec["short_max_days"])) else spec["long"])


def _dispose(conn: sqlite3.Connection, cs, day: int) -> None:
    """The case's disposition, once for the man arrested and once for each co-defendant held on it (his own plea, trial or walk)."""
    m = _meta(cs)
    lead = int(m["arrested"])
    for a in [lead, *[int(x) for x in m.get("held_with") or []]]:
        if a != lead and conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND case_id=? AND kind IN ('held','bailed') LIMIT 1", (a, cs["id"])).fetchone() is None:
            continue
        _dispose_one(conn, cs, day, a, cs["id"] if a == lead else f"{cs['id']}:{a}")


def _dispose_one(conn: sqlite3.Connection, cs, day: int, a: int, key) -> None:
    c = _cfg(conn)
    d = c["disposition"]
    m = _meta(cs)
    rep = conn.execute("SELECT * FROM crime_reports WHERE id=?", (m["crime_report_id"],)).fetchone()
    kind, rid = rep["crime_kind"], int(rep["id"])
    rmeta = _meta(rep)
    prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE id=?", (cs["profile_id"],)).fetchone()
    pub = publicity_of(conn, rid) / 100.0
    s = float(cs["evidence_score"]) / 100.0
    law = _lawyer(conn, m)
    padx = 1.0 if (m.get("officer") is not None and pad_reaches(conn, prof, m.get("officer"), a)) else 0.0
    wp = _witness_pressure(conn, a, rmeta, day)
    inducted = 1.0 if conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND inducted_day IS NOT NULL LIMIT 1", (a,)).fetchone() else 0.0
    x = {"strength": s, "lawyer": law, "arrangements": padx, "witness_pressure": wp, "publicity": pub, "inducted": inducted}

    def z(spec) -> float:
        return _n(spec["bias"]) + sum(_n(v) * x[k] for k, v in spec.items() if k in x)

    p_dismiss, p_trial, p_guilty = _logit(z(d["dismiss"])), _logit(z(d["trial"])), _logit(z(d["conviction"]))
    rng = _rng(conn, "disposition", key)
    r1, r2, r3 = rng.random(), rng.random(), rng.random()
    if r1 < p_dismiss:
        kind_out, convicted = "dismissed", False
    elif r2 < p_trial:
        convicted = r3 < p_guilty
        kind_out = "verdict_guilty" if convicted else "verdict_not_guilty"
    else:
        kind_out, convicted = "plea", True
    dispo_id = int(conn.execute("INSERT INTO case_dispositions(case_id,report_id,actor_id,day,kind,factors_json,metadata_json) VALUES (?,?,?,?,?,?,?)",
                                (cs["id"], rid, a, int(day), kind_out, json.dumps({**{k: round(v, 4) for k, v in x.items()}, "p_dismiss": round(p_dismiss, 4), "p_trial": round(p_trial, 4), "p_guilty": round(p_guilty, 4)}, sort_keys=True),
                                 json.dumps({"crime_kind": kind}))).lastrowid)
    conn.execute("UPDATE law_enforcement_cases SET status='closed', closed_day=? WHERE id=?", (int(day), cs["id"]))
    _set_case_meta(conn, cs["id"], stage="done", disposition=kind_out, disposition_id=dispo_id)
    rmeta["disposition"] = kind_out
    from .org_lifecycle import mark_for_history
    if not convicted:
        conn.execute("UPDATE custody SET kind='released', until_day=? WHERE case_id=? AND actor_id=? AND kind IN ('held','bailed')", (int(day), cs["id"], a))
        conn.execute("UPDATE crime_reports SET status='closed', metadata_json=? WHERE id=?", (json.dumps(rmeta, sort_keys=True), rid))
        imposed(conn, a)
        mark_for_history(conn, a, "walked free" if kind_out == "dismissed" else "was acquitted", int(day))
        return
    sen = c["sentence"]
    term = _lognormal_days(conn, sen["term_days"], kind, "term", cs["id"])
    term = max(1, int(round(term * (_n(sen["plea_factor"]) if kind_out == "plea" else 1.0) * (1.0 + _n(sen["publicity_factor"]) * pub)
                            * (1.0 + (_n(sen["officer_victim_factor"]) if rmeta.get("officer_victim") else 0.0)))))
    earliest = int(day) + max(1, int(round(term * _n(sen["parole_share"]))))
    facility = _facility(conn, prof, term)
    conn.execute(
        """INSERT INTO sentences(actor_id,case_id,report_id,disposition_id,crime_kind,victim_actor_id,location_id,term_days,start_day,earliest_release_day,end_day,facility,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'serving',?)""",
        (a, cs["id"], rid, dispo_id, kind, rep["victim_actor_id"], rep["location_id"], term, int(day), earliest, int(day) + term, facility,
         json.dumps({"how": kind_out, "agency_profile_id": int(prof["id"])}, sort_keys=True)))
    n = conn.execute("UPDATE custody SET kind='held', until_day=?, charge=? WHERE case_id=? AND actor_id=? AND kind IN ('held','bailed')", (earliest, kind, cs["id"], a)).rowcount
    if not n:
        conn.execute("INSERT INTO custody(actor_id,case_id,agency_profile_id,kind,charge,since_day,until_day) VALUES (?,?,?,'held',?,?,?)", (a, cs["id"], int(prof["id"]), kind, int(day), earliest))
    conn.execute("UPDATE crime_reports SET status='closed', metadata_json=? WHERE id=?", (json.dumps(rmeta, sort_keys=True), rid))
    imposed(conn, a)  # the seats weigh a long absence through the held-man decisions of the lifecycle
    mark_for_history(conn, a, f"was sentenced to {term} days at {facility}", int(day))


def _dispositions(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    for cs in _stage_cases(conn, day):
        if _meta(cs).get("stage") == "disposition":
            _dispose(conn, cs, int(day))
            n += 1
    return n


def _prison_holds_release(conn: sqlite3.Connection) -> bool:
    """A world with prison data frees its men through the prison layer's hearings and good time (J1), not at the earliest release day."""
    try:
        from . import prison
        return prison.enabled(conn)
    except (ImportError, sqlite3.OperationalError):
        return False


def _releases(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    if _prison_holds_release(conn):
        return n
    for s in conn.execute("SELECT * FROM sentences WHERE status='serving' AND earliest_release_day<=? ORDER BY id", (int(day),)).fetchall():
        a = int(s["actor_id"])
        if not _living(conn, a):
            conn.execute("UPDATE sentences SET status='ended', released_day=? WHERE id=?", (int(day), s["id"]))
            continue
        conn.execute("UPDATE sentences SET status='released', released_day=? WHERE id=?", (int(day), s["id"]))
        conn.execute("UPDATE custody SET kind='released', until_day=? WHERE case_id=? AND actor_id=? AND kind='held'", (int(day), s["case_id"], a))
        imposed(conn, a)  # what he does next is his own choice: he is looked at tomorrow
        from .org_lifecycle import mark_for_history
        mark_for_history(conn, a, "came home", int(day))
        try:
            from . import org_temperament
            org_temperament.drift(conn, a, "prison", int(day))
        except (ImportError, sqlite3.OperationalError):
            pass
        n += 1
    return n


# ---- the process ----

def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    try:
        if not _cfg(conn):
            return None
        ensure_tables(conn)
        due: list[int] = []
        cur = conn.execute("SELECT value FROM engine_meta WHERE key=?", (CURSOR_KEY,)).fetchone()
        if int(conn.execute("SELECT COALESCE(MAX(id),0) FROM harm_incidents").fetchone()[0]) > (int(cur[0]) if cur else 0):
            due.append(int(after_day) + 1)
        sqls = ["SELECT MIN(MAX(next_review_day, ?)) FROM law_enforcement_cases WHERE status IN ('monitoring','open','actionable') AND json_extract(metadata_json,'$.crime_report_id') IS NOT NULL"]
        if not _prison_holds_release(conn):
            sqls.append("SELECT MIN(MAX(earliest_release_day, ?)) FROM sentences WHERE status='serving'")
        for sql in sqls:
            r = conn.execute(sql, (int(after_day) + 1,)).fetchone()
            if r is not None and r[0] is not None:
                due.append(int(r[0]))
        d = min(due) if due else None
        return d if d is not None and d <= int(end_day) else None
    except sqlite3.OperationalError:
        return None


SWEEP_CURSOR = "crime_response_sweep_cursor"


def _sweeps(conn: sqlite3.Connection, day: int, since: int) -> int:
    """A killing the police take hard (a loud one, a hot group, an agency with the means) can bring a sweep: men tied to it, from the groups on
    either side, are picked up together under one joint case with co-defendants. The weighing is the package's (`response.sweep`): a pressure
    on the report, a number of men drawn around a mean that the pressure raises, and a pick weighted by how close each man stands to it. Nothing
    caps the men taken or the sweeps in a year."""
    sw = _cfg(conn).get("sweep")
    if not sw:
        return 0
    from . import org_heat
    kinds = list(sw["kinds"])
    n = 0
    for rep in conn.execute("SELECT * FROM crime_reports WHERE id>? AND crime_kind IN (%s) AND offender_actor_id IS NOT NULL ORDER BY id" % ",".join("?" * len(kinds)), (int(since), *kinds)).fetchall():
        meta = _meta(rep)
        if meta.get("source") == "sweep":
            continue
        offender, victim = int(rep["offender_actor_id"]), rep["victim_actor_id"]
        involved = sorted(set(_orgs_of(conn, offender)) | set(_orgs_of(conn, victim)))
        if not involved:
            continue
        pub = publicity_of(conn, int(rep["id"])) / 100.0
        heat = max((org_heat.own_factor(conn, o, int(day)) for o in involved), default=0.0) if org_heat.enabled(conn) else 0.0
        prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE id=?", (rep["agency_profile_id"],)).fetchone() if rep["agency_profile_id"] else None
        cap = float(prof["capacity"]) / 100.0 if prof is not None else 0.0
        x = {"publicity": pub, "heat": heat, "capacity": cap, "officer_victim": 1.0 if meta.get("officer_victim") else 0.0,
             "organised": 1.0 if _orgs_of(conn, offender) and _orgs_of(conn, victim) else 0.0}
        z = _n(sw["bias"]) + sum(_n(v) * x[k] for k, v in sw["weights"].items() if k in x)
        if _rng(conn, "sweep", rep["id"]).random() >= _logit(z):
            continue
        rng = _rng(conn, "sweep_men", rep["id"])
        want = _poisson(rng, _n(sw["men"]["base"]) + _n(sw["men"]["per_publicity"]) * pub + _n(sw["men"]["per_heat"]) * heat)
        pool = []
        offender_units = {int(r[0]) for r in conn.execute("SELECT unit_id FROM org_seats WHERE actor_id=? AND status='active' AND unit_id IS NOT NULL", (offender,))}
        offender_orgs = set(_orgs_of(conn, offender))
        for org in involved:
            for r in conn.execute("SELECT actor_id,unit_id,inducted_day FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id", (org,)).fetchall():
                a = int(r["actor_id"])
                if a == offender or a == victim or not _living(conn, a) or conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held' LIMIT 1", (a,)).fetchone():
                    continue
                w = (_n(sw["pick"]["base"]) + (_n(sw["pick"]["same_unit"]) if r["unit_id"] in offender_units else 0.0)
                     + (_n(sw["pick"]["offender_org"]) if org in offender_orgs else 0.0) + (_n(sw["pick"]["inducted"]) if r["inducted_day"] is not None else 0.0))
                pool.append((a, w))
        taken: list[int] = []
        while pool and len(taken) < want:
            pick = rng.random() * sum(w for _, w in pool)
            for i, (a, w) in enumerate(pool):
                pick -= w
                if pick < 0 or i == len(pool) - 1:
                    taken.append(a)
                    pool.pop(i)
                    break
        if not taken:
            continue
        lead, others = taken[0], taken[1:]
        jr = open_report(conn, crime_kind=sw["conspiracy_kind"], day=int(day), offender_actor_id=lead, victim_actor_id=victim, location_id=rep["location_id"],
                         metadata={"source": "sweep", "sweep_of": int(rep["id"]), "identified": True, "co_defendants": others})
        jrow = conn.execute("SELECT * FROM crime_reports WHERE id=?", (jr,)).fetchone()
        for a in taken:
            if conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held' LIMIT 1", (a,)).fetchone() is None:  # picked up for a few days (the arrest of the lead holds all of them on the case)
                days = _lognormal_days(conn, {"default": sw["hold_days"]}, "default", "sweep_hold", f"{rep['id']}:{a}")
                conn.execute("INSERT INTO custody(actor_id,kind,charge,since_day,until_day) VALUES (?,'held',?,?,?)", (a, "a sweep", int(day), int(day) + days))
                _answer_arrest(conn, jr, int(jrow["case_id"] or 0), a, sw["conspiracy_kind"], int(day), pub * 100.0)
            imposed(conn, a)
        n += 1
    return n


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    if not _cfg(conn):
        return {}
    ensure_tables(conn)
    cur = conn.execute("SELECT value FROM engine_meta WHERE key=?", (SWEEP_CURSOR,)).fetchone()
    since = int(cur[0]) if cur else int(conn.execute("SELECT COALESCE(MAX(id),0) FROM crime_reports").fetchone()[0])
    out = {"reports": _intake(conn, int(day))}
    out["swept"] = _sweeps(conn, int(day), since)
    conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (SWEEP_CURSOR, str(int(conn.execute("SELECT COALESCE(MAX(id),0) FROM crime_reports").fetchone()[0]))))
    out["envelopes_reopened"] = _void_envelopes(conn, int(day))
    out["reviewed"] = _reviews(conn, int(day))
    out["bailed"] = _bail(conn, int(day))
    out["disposed"] = _dispositions(conn, int(day))
    out["released"] = _releases(conn, int(day))
    return out


# ---- the answer to an arrest (an agenda item: the unit leader or head weighs a lawyer or waiting) ----

def _fee_range(conn: sqlite3.Connection) -> tuple[float, float]:
    f = _cfg(conn)["backing"]["lawyer_fee"]
    return _n(f["low"]), _n(f["high"])


def _still_held(conn: sqlite3.Connection, held: int) -> bool:
    return conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind IN ('held','bailed') AND case_id IS NOT NULL LIMIT 1", (int(held),)).fetchone() is not None


def arrest_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    from . import ledger
    m = _meta(item)
    held, org = int(m["held"]), int(m["org"])
    if not _still_held(conn, held):
        resolve_agenda(conn, int(item["id"]), int(day))
        return []
    b = _cfg(conn)["backing"]
    rel = conn.execute("SELECT loyalty FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(actor_id), held)).fetchone()
    loyalty = max(0.0, min(1.0, float(rel[0]) / 100.0)) if rel is not None else 0.5
    seat = orgs.seat_of(conn, held, org)
    standing = float(seat["standing"]) if seat is not None else 0.0
    low, high = _fee_range(conn)
    balance = ledger.balance(conn, ("person", int(actor_id)))
    base = {"payload": {"held": held, "org": org, "case": m.get("case"), "report": m.get("report"), "charge": m.get("charge")}, "target_actor_id": held}
    def utility(x: float) -> float:  # the same scale every organisation choice uses
        return float(figure(conn, "org_choice_utility_base", default=8.0)) + float(figure(conn, "org_choice_utility_span", default=10.0)) * orgs.clamp01(x)

    offers = [{**base, "kind": "member_arrested", "utility": utility(_n(b["wait_base"])), "rationale": "waits to see what the case brings",
               "payload": {**base["payload"], "response": "wait"}}]
    if balance >= low:
        offers.append({**base, "kind": "member_arrested", "cost": (low + high) / 2.0, "rationale": "sends him a lawyer",
                       "utility": utility(_n(b["send_base"]) + _n(b["send_loyalty"]) * loyalty + _n(b["send_standing"]) * standing
                                          - _n(b["send_cost"]) * (low + high) / 2.0 / max(balance, 1.0)),
                       "payload": {**base["payload"], "response": "send_lawyer"}})
    return offers


def execute_member_arrested(conn: sqlite3.Connection, actor_id: int, kind: str, payload: dict, day: int) -> dict:
    from . import ledger
    from .relationships import adjust_relationship
    held, resp = int(payload["held"]), str(payload.get("response") or "wait")
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    b = _cfg(conn)["backing"]
    text = f"{_name(conn, actor_id)} waited on {_name(conn, held)}'s case."
    if resp == "send_lawyer" and payload.get("case") is not None:
        low, high = _fee_range(conn)
        fee = low + _rng(conn, "fee", f"{actor_id}:{held}:{day}").random() * (high - low)
        paid = ledger.spend(conn, ("person", int(actor_id)), fee, purpose="a lawyer for a man in custody", allow_partial=True)
        cs = conn.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (int(payload["case"]),)).fetchone()
        if cs is not None and paid > 0:
            cm = _meta(cs)
            upd = {"lawyer_fee": float(cm.get("lawyer_fee") or 0.0) + paid}
            if cm.get("stage") == "bail" and cm.get("bail_day") is not None:
                bail = min(int(cm["bail_day"]), int(day) + max(1, int(round(int(figure(conn, "bail_days")) * _n(b["bail_after_lawyer_share"])))))
                upd["bail_day"] = bail
                conn.execute("UPDATE law_enforcement_cases SET next_review_day=? WHERE id=?", (bail, cs["id"]))
            _set_case_meta(conn, cs["id"], **upd)
        text = f"{_name(conn, actor_id)} sent a lawyer to {_name(conn, held)} (${paid:,.0f})."
    if str(payload.get("charge")) == _cfg(conn)["harm"]["fatal_kind"]:
        lo, hi = b["homicide_trust_drop"]
        drop = int(_rng(conn, "trust", f"{actor_id}:{held}:{day}").randint(int(lo), int(hi)))
        if drop:
            adjust_relationship(conn, int(actor_id), held, int(day), trust_delta=-float(drop))
    return {"summary": text}


register_executor("member_arrested", execute_member_arrested)
register_agenda_action("member_arrested", arrest_offers)
```

## engine/civilian.py

```python
from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any, Callable

from .civilian_life import create_building, process_due_civilian_life, civilian_life_summary
from .business import next_business_due_day, process_due_businesses, business_ecology_summary
from .household_life import next_household_life_due_day, process_due_household_life, household_life_summary
from .ecology import production_factor as ecology_production_factor, environmental_transport_pressure


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _seed(conn: sqlite3.Connection, salt: int) -> int:
    row = conn.execute("SELECT rng_seed,current_day FROM world_state WHERE id=1").fetchone()
    return int(row[0]) * 1_000_003 + int(row[1]) * 9_973 + int(salt)


def create_household(conn: sqlite3.Connection, name: str, *, head_actor_id: int | None = None,
                     location_id: int | None = None, wealth: float = 0, liquidity: float = 0,
                     staff_capacity: float = 50, cohesion: float = 70, hospitality: float = 50,
                     metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO households(name,head_actor_id,location_id,wealth,liquidity,staff_capacity,cohesion,hospitality,metadata_json,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (name, head_actor_id, location_id, wealth, liquidity, staff_capacity, cohesion, hospitality,
         json.dumps(metadata or {}, sort_keys=True), day, day),
    )
    hid = int(cur.lastrowid)
    if head_actor_id is not None:
        conn.execute(
            "INSERT OR IGNORE INTO household_members(household_id,actor_id,role,authority,dependency,joined_day) VALUES (?,?,?,?,?,?)",
            (hid, head_actor_id, "head", 100, 0, day),
        )
    return hid


def add_household_member(conn: sqlite3.Connection, household_id: int, actor_id: int, *, role: str = "member",
                         authority: float = 20, dependency: float = 20) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status)
           VALUES (?,?,?,?,?,?, 'active')""",
        (household_id, actor_id, role, authority, dependency, _day(conn)),
    )


def create_enterprise(conn: sqlite3.Connection, name: str, enterprise_kind: str, *, owner_actor_id: int | None = None,
                      institution_actor_id: int | None = None, household_id: int | None = None,
                      location_id: int | None = None, capital: float = 0, cash: float = 0, debt: float = 0,
                      reputation: float = 50, admin_quality: float = 50, labor_capacity: float = 50,
                      risk_tolerance: float = 50, metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO civilian_enterprises(name,enterprise_kind,owner_actor_id,institution_actor_id,household_id,location_id,
                                             capital,cash,debt,reputation,admin_quality,labor_capacity,risk_tolerance,metadata_json,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (name, enterprise_kind, owner_actor_id, institution_actor_id, household_id, location_id, capital, cash, debt,
         reputation, admin_quality, labor_capacity, risk_tolerance, json.dumps(metadata or {}, sort_keys=True), day, day),
    )
    return int(cur.lastrowid)


def ensure_good(conn: sqlite3.Connection, good_key: str, name: str, category: str, base_price: float, *,
                unit: str = "unit", perishability: float = 0, skill_intensity: float = 0.5,
                luxury: float = 0, notes: str | None = None) -> int:
    conn.execute(
        """INSERT OR IGNORE INTO market_goods(good_key,name,category,base_price,unit,perishability,skill_intensity,luxury,notes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (good_key, name, category, base_price, unit, perishability, skill_intensity, luxury, notes),
    )
    return int(conn.execute("SELECT id FROM market_goods WHERE good_key=?", (good_key,)).fetchone()[0])


def set_market_condition(conn: sqlite3.Connection, location_id: int, good_id: int, *, supply: float = 50,
                         demand: float = 50, transport_pressure: float = 0, risk_pressure: float = 0,
                         tax_pressure: float = 0, cadence_days: int = 30,
                         metadata: dict[str, Any] | None = None) -> None:
    base = float(conn.execute("SELECT base_price FROM market_goods WHERE id=?", (good_id,)).fetchone()[0])
    price = _price(base, supply, demand, transport_pressure, risk_pressure, tax_pressure)
    day = _day(conn)
    conn.execute(
        """INSERT INTO market_conditions(location_id,good_id,supply,demand,transport_pressure,risk_pressure,tax_pressure,current_price,last_review_day,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(location_id,good_id) DO UPDATE SET supply=excluded.supply,demand=excluded.demand,
             transport_pressure=excluded.transport_pressure,risk_pressure=excluded.risk_pressure,tax_pressure=excluded.tax_pressure,
             current_price=excluded.current_price,last_review_day=excluded.last_review_day,next_review_day=excluded.next_review_day,
             metadata_json=excluded.metadata_json""",
        (location_id, good_id, supply, demand, transport_pressure, risk_pressure, tax_pressure, price,
         day, day + max(1, cadence_days), json.dumps(metadata or {}, sort_keys=True)),
    )


def _price(base: float, supply: float, demand: float, transport: float, risk: float, tax: float) -> float:
    # Bounded directional economics. Supply/demand dominate; friction adds premiums.
    scarcity = (demand + 10.0) / (supply + 10.0)
    scarcity = max(0.35, min(3.0, scarcity))
    friction = 1.0 + 0.0035 * max(0, transport) + 0.0025 * max(0, risk) + 0.002 * max(0, tax)
    return round(max(0.01, base * scarcity * friction), 4)


def add_production_site(conn: sqlite3.Connection, enterprise_id: int, good_id: int, *, capacity_per_30: float = 10,
                        efficiency: float = 50, material_access: float = 50, skilled_labor: float = 50,
                        inventory: float = 0, notes: str | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO production_sites(enterprise_id,good_id,capacity_per_30,efficiency,material_access,skilled_labor,inventory,last_resolved_day,notes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (enterprise_id, good_id, capacity_per_30, efficiency, material_access, skilled_labor, inventory, _day(conn), notes),
    )
    return int(cur.lastrowid)


def create_project(conn: sqlite3.Connection, title: str, project_kind: str, *, patron_actor_id: int | None = None,
                   creator_actor_id: int | None = None, enterprise_id: int | None = None,
                   location_id: int | None = None, target_day: int | None = None,
                   quality_potential: float = 50, funding: float = 50, material_access: float = 50,
                   skilled_labor: float = 50, metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO civilian_projects(title,project_kind,patron_actor_id,creator_actor_id,enterprise_id,location_id,
                                         started_day,target_day,quality_potential,funding,material_access,skilled_labor,status,last_resolved_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?,?)""",
        (title, project_kind, patron_actor_id, creator_actor_id, enterprise_id, location_id, day, target_day,
         quality_potential, funding, material_access, skilled_labor, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def create_cultural_object(conn: sqlite3.Connection, title: str, object_kind: str, *, creator_actor_id: int | None = None,
                           workshop_actor_id: int | None = None, created_day: int | None = None,
                           project_id: int | None = None, owner_actor_id: int | None = None,
                           household_id: int | None = None, location_id: int | None = None,
                           quality: float = 50, market_value: float = 0, significance: str = "ordinary",
                           metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn) if created_day is None else int(created_day)
    cur = conn.execute(
        """INSERT INTO cultural_objects(title,object_kind,creator_actor_id,workshop_actor_id,created_day,project_id,
                                        current_owner_actor_id,current_household_id,current_location_id,quality,market_value,significance,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (title, object_kind, creator_actor_id, workshop_actor_id, day, project_id, owner_actor_id, household_id,
         location_id, quality, market_value, significance, json.dumps(metadata or {}, sort_keys=True)),
    )
    oid = int(cur.lastrowid)
    add_provenance(conn, oid, "created", f"{title} was created.", to_actor_id=owner_actor_id,
                   location_id=location_id, day=day, reliability=1.0)
    return oid


def add_provenance(conn: sqlite3.Connection, object_id: int, provenance_kind: str, record_text: str, *,
                   from_actor_id: int | None = None, to_actor_id: int | None = None,
                   location_id: int | None = None, day: int | None = None, reliability: float = 1.0,
                   source_record_id: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO object_provenance(object_id,day,provenance_kind,from_actor_id,to_actor_id,location_id,record_text,reliability,source_record_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (object_id, _day(conn) if day is None else day, provenance_kind, from_actor_id, to_actor_id,
         location_id, record_text, reliability, source_record_id, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def create_auction(conn: sqlite3.Connection, title: str, scheduled_day: int, *, location_id: int | None = None,
                   institution_actor_id: int | None = None, prestige: float = 50,
                   metadata: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO auctions(title,location_id,institution_actor_id,scheduled_day,prestige,metadata_json) VALUES (?,?,?,?,?,?)",
        (title, location_id, institution_actor_id, scheduled_day, prestige, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def add_auction_lot(conn: sqlite3.Connection, auction_id: int, object_id: int, *, seller_actor_id: int | None = None,
                    reserve_price: float = 0, estimate_low: float = 0, estimate_high: float = 0) -> int:
    cur = conn.execute(
        """INSERT INTO auction_lots(auction_id,object_id,seller_actor_id,reserve_price,estimate_low,estimate_high)
           VALUES (?,?,?,?,?,?)""",
        (auction_id, object_id, seller_actor_id, reserve_price, estimate_low, max(estimate_low, estimate_high)),
    )
    return int(cur.lastrowid)


def set_auction_interest(conn: sqlite3.Connection, lot_id: int, actor_id: int, *, interest: float = 50,
                         budget: float = 0, taste_fit: float = 50, status_motive: float = 0) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO auction_interest(lot_id,actor_id,interest,budget,taste_fit,status_motive)
           VALUES (?,?,?,?,?,?)""",
        (lot_id, actor_id, interest, budget, taste_fit, status_motive),
    )


def add_shadow_link(conn: sqlite3.Connection, subject_kind: str, subject_id: int, link_kind: str, *,
                    pressure: float = 0, exposure: float = 0, notes: str | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO shadow_market_links(subject_kind,subject_id,link_kind,pressure,exposure,notes,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?)""",
        (subject_kind, subject_id, link_kind, pressure, exposure, notes, day, day),
    )
    return int(cur.lastrowid)


def _record_account(conn: sqlite3.Connection, enterprise_id: int, day: int, kind: str, amount: float, desc: str,
                    good_id: int | None = None) -> None:
    conn.execute(
        """INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,related_good_id)
           VALUES (?,?,?,?,?,?)""",
        (enterprise_id, day, kind, max(0.0, amount), desc, good_id),
    )


def _resolve_market(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    meta = json.loads(row["metadata_json"] or "{}")
    elapsed = max(1, day - int(row["last_review_day"]))
    rng = random.Random(_seed(conn, int(row["location_id"]) * 100003 + int(row["good_id"]) * 97 + day))
    supply = max(0.0, float(row["supply"]) + float(meta.get("supply_trend_per_30", 0)) * elapsed / 30 + rng.gauss(0, 1.5))
    demand = max(0.0, float(row["demand"]) + float(meta.get("demand_trend_per_30", 0)) * elapsed / 30 + rng.gauss(0, 1.5))
    good = conn.execute("SELECT base_price FROM market_goods WHERE id=?", (row["good_id"],)).fetchone()
    eco_transport = environmental_transport_pressure(conn, int(row["location_id"]), day)
    price = _price(float(good[0]), supply, demand, float(row["transport_pressure"]) + eco_transport, float(row["risk_pressure"]), float(row["tax_pressure"]))
    cadence = int(meta.get("cadence_days", 30))
    conn.execute(
        "UPDATE market_conditions SET supply=?,demand=?,current_price=?,last_review_day=?,next_review_day=? WHERE location_id=? AND good_id=?",
        (supply, demand, price, day, day + max(1, cadence), row["location_id"], row["good_id"]),
    )


def _resolve_production(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    # CRAFT-01 tracked sites are resolved only by engine.craft; the legacy aggregate
    # material_access formula must never mint parallel output for them.
    if "production_mode" in row.keys() and str(row["production_mode"]) == "tracked":
        return
    elapsed = max(0, day - int(row["last_resolved_day"]))
    if elapsed <= 0:
        return
    ent = conn.execute("SELECT location_id,labor_capacity FROM civilian_enterprises WHERE id=?", (row["enterprise_id"],)).fetchone()
    market = None
    if ent and ent["location_id"] is not None:
        market = conn.execute("SELECT demand,current_price FROM market_conditions WHERE location_id=? AND good_id=?",
                              (ent["location_id"], row["good_id"])).fetchone()
    bottleneck = min(float(row["efficiency"]), float(row["material_access"]), float(row["skilled_labor"]), float(ent["labor_capacity"] if ent else 50)) / 100.0
    good_row = conn.execute("SELECT category FROM market_goods WHERE id=?", (row["good_id"],)).fetchone()
    eco_factor = ecology_production_factor(conn, int(ent["location_id"]) if ent and ent["location_id"] is not None else None, day, str(good_row[0]) if good_row else None)
    produced = float(row["capacity_per_30"]) * elapsed / 30.0 * bottleneck * eco_factor
    inventory = float(row["inventory"]) + max(0.0, produced)
    sold = 0.0
    revenue = 0.0
    if market:
        demand_fraction = max(0.05, min(1.0, float(market["demand"]) / 100.0))
        sold = min(inventory, float(row["capacity_per_30"]) * elapsed / 30.0 * demand_fraction)
        revenue = sold * float(market["current_price"])
        inventory -= sold
    cost = max(0.0, produced * (0.2 + (100 - float(row["efficiency"])) / 250.0))
    conn.execute("UPDATE production_sites SET inventory=?,last_resolved_day=? WHERE id=?", (inventory, day, row["id"]))
    erow = conn.execute("SELECT cash,debt,capital FROM civilian_enterprises WHERE id=?", (row["enterprise_id"],)).fetchone()
    if erow:
        raw_cash = float(erow["cash"]) + revenue - cost
        shortfall = max(0.0, -raw_cash)
        new_cash = max(0.0, raw_cash)
        new_debt = float(erow["debt"]) + shortfall
        new_capital = max(0.0, float(erow["capital"]) + revenue * 0.15 - cost * 0.08)
        conn.execute("UPDATE civilian_enterprises SET cash=?,debt=?,capital=?,updated_day=? WHERE id=?",
                     (new_cash, new_debt, new_capital, day, row["enterprise_id"]))
    if revenue:
        _record_account(conn, int(row["enterprise_id"]), day, "revenue", revenue, "Sales from ordinary production", int(row["good_id"]))
    if cost:
        _record_account(conn, int(row["enterprise_id"]), day, "expense", cost, "Production costs", int(row["good_id"]))


def _resolve_project(conn: sqlite3.Connection, row: sqlite3.Row, day: int, event_logger: Callable[..., int] | None) -> None:
    elapsed = max(0, day - int(row["last_resolved_day"]))
    if elapsed <= 0 or row["status"] != "active":
        return
    bottleneck = min(float(row["funding"]), float(row["material_access"]), float(row["skilled_labor"])) / 100.0
    pace = 100.0 / max(30.0, float((row["target_day"] or (int(row["started_day"]) + 180)) - int(row["started_day"])))
    progress = min(100.0, float(row["progress"]) + elapsed * pace * (0.35 + 0.9 * bottleneck))
    status = "completed" if progress >= 100 else "active"
    conn.execute("UPDATE civilian_projects SET progress=?,status=?,last_resolved_day=? WHERE id=?", (progress, status, day, row["id"]))
    if status == "completed":
        # Projects create durable history. Art/craft projects may also crystallize into cultural objects.
        if row["project_kind"] in {"artwork", "textile", "manuscript", "craft"}:
            kind_map = {"artwork":"painting", "textile":"textile", "manuscript":"manuscript", "craft":"other"}
            q = max(1.0, min(100.0, float(row["quality_potential"]) * (0.7 + 0.3 * bottleneck)))
            obj = create_cultural_object(conn, str(row["title"]), kind_map[row["project_kind"]],
                                         creator_actor_id=row["creator_actor_id"], project_id=int(row["id"]),
                                         owner_actor_id=row["patron_actor_id"], location_id=row["location_id"],
                                         quality=q, market_value=q * 1.2,
                                         significance="valuable" if q >= 75 else "ordinary")
            add_provenance(conn, obj, "commissioned", "Completed as a commissioned project.",
                           to_actor_id=row["patron_actor_id"], location_id=row["location_id"], day=day)
            if row["creator_actor_id"] is not None:
                try:
                    from .patronage import note_cultural_success
                    note_cultural_success(conn, int(row["creator_actor_id"]), q, day=day, object_id=obj)
                except sqlite3.OperationalError:
                    pass
        elif row["project_kind"] in {"architecture", "public_work"}:
            meta = json.loads(row["metadata_json"] or "{}")
            q = max(1.0, min(100.0, float(row["quality_potential"]) * (0.7 + 0.3 * bottleneck)))
            create_building(
                conn, str(row["title"]),
                str(meta.get("building_kind", "public_building" if row["project_kind"] == "public_work" else "other")),
                location_id=row["location_id"], owner_actor_id=meta.get("owner_actor_id", row["patron_actor_id"]),
                household_id=meta.get("household_id"), institution_actor_id=meta.get("institution_actor_id"),
                project_id=int(row["id"]), style_key=meta.get("style_key"), capacity=float(meta.get("capacity", 50)),
                condition=100, prestige=float(meta.get("prestige", q)), utility=float(meta.get("utility", q)),
                maintenance_burden=float(meta.get("maintenance_burden", max(5.0, q / 8.0))), completed_day=day,
                metadata={"quality_at_completion": q},
            )
        conn.execute(
            """INSERT INTO historical_anchors(entity_kind,entity_id,anchor_type,start_day,end_day,summary,source_kind,certainty,canon_scope,created_day)
               VALUES ('thread',?,'project_completed',?,?,?,'admin',1,'campaign',?)""",
            (int(row["id"]), int(row["started_day"]), day, f"Project completed: {row['title']}", day),
        )
        if event_logger:
            event_logger(day=day, event_type="civilian:project_completed", title=f"Completed: {row['title']}",
                         summary=f"The {row['project_kind']} project '{row['title']}' was completed.", severity=1,
                         source_actor_id=row["creator_actor_id"], target_actor_ids=tuple(x for x in [row["patron_actor_id"], row["creator_actor_id"]] if x),
                         location_id=row["location_id"])


def resolve_auction(conn: sqlite3.Connection, auction_id: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, Any]:
    auction = conn.execute("SELECT * FROM auctions WHERE id=?", (auction_id,)).fetchone()
    if not auction:
        raise ValueError("Unknown auction")
    day = _day(conn)
    results = []
    for lot in conn.execute("SELECT * FROM auction_lots WHERE auction_id=? AND status='listed' ORDER BY id", (auction_id,)).fetchall():
        obj = conn.execute("SELECT * FROM cultural_objects WHERE id=?", (lot["object_id"],)).fetchone()
        candidates = []
        for bid in conn.execute("SELECT * FROM auction_interest WHERE lot_id=?", (lot["id"],)).fetchall():
            rng = random.Random(_seed(conn, auction_id * 100000 + int(lot["id"]) * 100 + int(bid["actor_id"])))
            desire = (float(bid["interest"]) * 0.45 + float(bid["taste_fit"]) * 0.35 + float(bid["status_motive"]) * 0.20)
            max_bid = min(float(bid["budget"]), max(float(lot["estimate_low"]), float(obj["market_value"])) * (0.65 + desire / 100.0 * 0.8) * rng.uniform(0.93, 1.07))
            candidates.append((max_bid, int(bid["actor_id"])))
        candidates.sort(reverse=True)
        winner = None
        hammer = None
        if candidates and candidates[0][0] >= float(lot["reserve_price"]):
            winner = candidates[0][1]
            second = candidates[1][0] if len(candidates) > 1 else float(lot["reserve_price"])
            hammer = round(max(float(lot["reserve_price"]), min(candidates[0][0], second * 1.05)), 2)
            conn.execute("UPDATE auction_lots SET winning_actor_id=?,hammer_price=?,status='sold' WHERE id=?", (winner, hammer, lot["id"]))
            seller = lot["seller_actor_id"]
            conn.execute("UPDATE cultural_objects SET current_owner_actor_id=?,current_household_id=NULL,current_location_id=?,market_value=? WHERE id=?",
                         (winner, auction["location_id"], hammer, lot["object_id"]))
            add_provenance(conn, int(lot["object_id"]), "sold", f"Sold at {auction['title']} for {hammer:.2f}.",
                           from_actor_id=seller, to_actor_id=winner, location_id=auction["location_id"], day=day)
        else:
            conn.execute("UPDATE auction_lots SET status='unsold' WHERE id=?", (lot["id"],))
        results.append({"lot_id": int(lot["id"]), "object_id": int(lot["object_id"]), "winner_actor_id": winner, "hammer_price": hammer})
    conn.execute("UPDATE auctions SET status='resolved',resolved_day=? WHERE id=?", (day, auction_id))
    if event_logger:
        event_logger(day=day, event_type="civilian:auction", title=str(auction["title"]),
                     summary=f"{auction['title']} concluded with {sum(1 for r in results if r['winner_actor_id'])} sold lots.",
                     severity=1, source_actor_id=auction["institution_actor_id"], target_actor_ids=(), location_id=auction["location_id"])
    return {"auction_id": auction_id, "resolved_day": day, "lots": results}


def _resolve_households(conn: sqlite3.Connection, day: int) -> None:
    from . import tiers
    if tiers.batching(conn):
        # S1: a quiet household's money is brought up to date weekly (income, wages and upkeep all integrate the days since);
        # one whose head is rising stays daily.
        due = conn.execute(f"""SELECT * FROM households WHERE status IN ('active','declining')
                               AND (updated_day<=? OR head_actor_id IN ({tiers.sql_ids(conn, day)}))""", (day - tiers.BATCH_DAYS,)).fetchall()
    else:
        due = conn.execute("SELECT * FROM households WHERE status IN ('active','declining')").fetchall()
    for h in due:
        metadata = json.loads(h["metadata_json"] or "{}")
        # A structurally known household with unquantified canon finances is not a zero-money household.
        # Keep it persistent, but do not invent a budget simply to feed the economic resolver.
        if metadata.get("economic_resolution") == "STRUCTURAL_ONLY" or metadata.get("economic_state") == "NOT_SEPARATELY_QUANTIFIED":
            continue
        elapsed = max(0, day - int(h["updated_day"]))
        if elapsed <= 0:
            continue
        # Servants and stewards on service terms are paid as wages (to their purses) instead of an implicit per-head charge.
        from .payroll import run_household_payroll
        wages = run_household_payroll(conn, h, elapsed, day)
        # Households quantified from their means earn: working members a margin over their keep, wealth a yield (household_staff).
        from .household_staff import _upkeep, household_income
        income = household_income(conn, int(h["id"])) * elapsed / 30.0 if metadata.get("economic_basis") == "family_means" else 0.0
        upkeep = _upkeep(conn, h) * elapsed / 30.0
        liquidity = float(h["liquidity"]) + income - wages - upkeep
        wealth = float(h["wealth"])
        status = str(h["status"])
        if liquidity < 0:
            wealth = max(0.0, wealth + liquidity)
            liquidity = 0.0
            status = "declining" if wealth > 0 else "dissolved"
        elif status == "declining" and liquidity > 5:
            status = "active"
        conn.execute("UPDATE households SET liquidity=?,wealth=?,status=?,updated_day=? WHERE id=?",
                     (liquidity, wealth, status, day, h["id"]))


def _resolve_enterprise_status(conn: sqlite3.Connection, day: int) -> None:
    for e in conn.execute("SELECT * FROM civilian_enterprises WHERE status IN ('active','strained','insolvent')").fetchall():
        elapsed = max(0, day - int(e["updated_day"]))
        if elapsed <= 0:
            continue
        cash, debt, capital = float(e["cash"]), float(e["debt"]), float(e["capital"])
        interest = debt * 0.0025 * elapsed / 30.0
        cash -= interest
        if interest:
            _record_account(conn, int(e["id"]), day, "expense", interest, "Debt carrying cost")
        if cash < 0:
            # Unpaid carrying cost becomes additional liability rather than a negative cash balance.
            debt += -cash
            cash = 0.0
        defaulted_credit = conn.execute(
            "SELECT 1 FROM credit_agreements WHERE borrower_enterprise_id=? AND status='defaulted' LIMIT 1",
            (e["id"],),
        ).fetchone()
        if debt > max(1.0, capital * 1.5):
            status = "insolvent"
        elif defaulted_credit or debt > max(1.0, capital * 1.2):
            status = "strained"
        else:
            status = "active"
        conn.execute("UPDATE civilian_enterprises SET cash=?,debt=?,status=?,updated_day=? WHERE id=?", (cash, debt, status, day, e["id"]))



_BUSINESS_LABEL = {"wholesaler": "warehouse", "inn": "inn", "physician_practice": "physic house", "smithy": "smithy",
                   "moneylender": "counting house", "food_shop": "cookshop"}


def _emergent_business_name(conn: sqlite3.Connection, operator_id: int, archetype: str, location_id: int | None) -> str:
    """A new business takes its operator's name, as small concerns do: "Harrow's inn", else "Bren Harrow's inn"."""
    person = str(conn.execute("SELECT name FROM actors WHERE id=?", (int(operator_id),)).fetchone()[0])
    tokens = [t for t in person.split() if not t.isdigit()]
    label = _BUSINESS_LABEL.get(archetype, archetype.replace("_", " "))
    place = conn.execute("SELECT name FROM locations WHERE id=?", (location_id,)).fetchone() if location_id is not None else None
    for name in (f"{tokens[-1]}'s {label}", f"{' '.join(tokens)}'s {label}",
                 f"{' '.join(tokens)}'s {label}, {place[0] if place else ''}".rstrip(", ")):
        if not conn.execute("SELECT 1 FROM civilian_enterprises WHERE name=?", (name,)).fetchone():
            return name
    return f"{' '.join(tokens)}'s {label} {int(operator_id)}"


def _commercial_emergence_archetype(ctx: sqlite3.Row) -> str:
    choices = [
        (float(ctx["trade_flow"]), "wholesaler"),
        (float(ctx["traveler_flow"]), "inn"),
        (float(ctx["health_demand"]), "physician_practice"),
        (float(ctx["craft_demand"]), "smithy"),
        (float(ctx["credit_demand"]), "moneylender"),
        (float(ctx["foot_traffic"]), "food_shop"),
    ]
    return max(choices, key=lambda x: x[0])[1]


def _review_latent_commercial_emergence(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Annual structural business formation from existing local population and demand.

    This does not assign wealth to named characters. A one-person latent merchant/operator is
    resolved from the already-existing urban population, and the business receives a structural
    label rather than a canonized proper name. Sustained regional consequence can later raise
    that latent person to TRACKED resolution or form an unnamed merchant-house candidate.
    """
    meta = conn.execute("SELECT value FROM engine_meta WHERE key='commercial_emergence_next_day'").fetchone()
    next_day = int(meta[0]) if meta else 365
    if day < next_day:
        return {"commercial_emergence_reviews": 0, "latent_merchants_created": 0, "structural_enterprises_created": 0, "merchant_house_candidates": 0}
    while next_day <= day:
        next_day += 365
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('commercial_emergence_next_day',?)", (str(next_day),))

    reviewed = created = candidates = 0
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])

    # First update consequence for already-emergent merchants from actual enterprise history.
    rows = conn.execute("""SELECT e.*, l.id latent_id, l.historical_context_json
                           FROM civilian_enterprises e LEFT JOIN latent_entities l
                             ON json_extract(e.metadata_json,'$.latent_owner_entity_id')=l.id
                           WHERE json_extract(e.metadata_json,'$.emergent_business')=1
                           ORDER BY e.id""").fetchall()
    from .resolution_controller import create_institution_candidate, update_institution_candidate
    for e in rows:
        reviewed += 1
        age_days = max(0, day - int(e["created_day"]))
        material = max(0.0, float(e["capital"]) + float(e["cash"]) - float(e["debt"]))
        consequence = max(0.0, min(35.0, math.log1p(material) * 4.2 + max(0.0, float(e["reputation"]) - 45.0) * 0.22 + age_days / 365.0 * 1.4))
        try:
            hist = json.loads(e["historical_context_json"] or "{}")
        except Exception:
            hist = {}
        hist.update({
            "enterprise_id": int(e["id"]),
            "enterprise_status": str(e["status"]),
            "commercial_age_days": age_days,
            "regional_significance": round(consequence, 3),
            "consequence_score": round(consequence, 3),
        })
        if e["latent_id"] is not None:
            conn.execute("UPDATE latent_entities SET historical_context_json=?,updated_day=? WHERE id=?", (json.dumps(hist, sort_keys=True), day, int(e["latent_id"])))

        if age_days >= 3 * 365 and consequence >= 22.0 and str(e["status"]) in {"active", "strained"}:
            # A wholesaler is an enterprise, not automatically a merchant *house*.  Institutional
            # formation requires evidence that the business has grown beyond one operator into a
            # durable organization.  Family/dynastic merchant-house identity is a later, stronger
            # social form and is not fabricated here.
            existing = conn.execute("SELECT * FROM emergent_institution_candidates WHERE enterprise_id=? AND candidate_kind IN ('merchant firm','merchant house') AND status IN ('forming','eligible') ORDER BY id DESC LIMIT 1", (int(e["id"]),)).fetchone()
            active_staff = int(conn.execute("SELECT COUNT(*) FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (int(e["id"]),)).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_staff'").fetchone() else 0
            completed_contracts = int(conn.execute("SELECT COUNT(*) FROM merchant_trade_contracts WHERE (buyer_enterprise_id=? OR seller_enterprise_id=?) AND status IN ('fulfilled','settled','delivered')", (int(e["id"]),int(e["id"]))).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_trade_contracts'").fetchone() else 0
            distinct_trade_locations = int(conn.execute("SELECT COUNT(DISTINCT destination_location_id) FROM merchant_trade_contracts WHERE (buyer_enterprise_id=? OR seller_enterprise_id=?) AND destination_location_id IS NOT NULL", (int(e["id"]),int(e["id"]))).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_trade_contracts'").fetchone() else 0
            resources = {
                "capital":float(e["capital"]), "cash":float(e["cash"]), "debt":float(e["debt"]),
                "business_age_days":age_days, "active_staff":active_staff,
                "completed_trade_contracts":completed_contracts, "distinct_trade_locations":distinct_trade_locations,
                "branch_count":0, "institutional_form":"merchant_firm",
            }
            evidence = {"kind": "sustained_commercial_consequence", "enterprise_id": int(e["id"]), "age_days": age_days, "regional_significance": round(consequence,3),
                        "active_staff":active_staff, "completed_trade_contracts":completed_contracts, "distinct_trade_locations":distinct_trade_locations}
            score = min(70.0, 18.0 + consequence + min(15.0, age_days / 365.0 * 2.0))
            if existing is None:
                cid=create_institution_candidate(conn, "merchant firm", location_id=e["location_id"], enterprise_id=int(e["id"]), proposed_name=None, significance_score=score, resources=resources, participants=[], evidence=[evidence], day=day)
                # create_institution_candidate deliberately starts at forming; run the same domain
                # threshold immediately so truly institutional firms need not wait another year.
                update_institution_candidate(conn, cid, significance_score=score, resources=resources, day=day)
                candidates += 1
            else:
                if str(existing["candidate_kind"]) == "merchant house":
                    conn.execute("UPDATE emergent_institution_candidates SET candidate_kind='merchant firm' WHERE id=?", (int(existing["id"]),))
                update_institution_candidate(conn, int(existing["id"]), significance_score=score, resources=resources, evidence_append=evidence, day=day)

    # Then allow sparse new businesses where commercial context is strong enough.
    contexts = conn.execute("SELECT lc.*,l.name location_name FROM location_commercial_context lc JOIN locations l ON l.id=lc.location_id ORDER BY lc.location_id").fetchall()
    year_index = max(1, day // 365)
    from .business import configure_enterprise_business
    for ctx in contexts:
        loc = int(ctx["location_id"])
        opportunity = max(float(ctx[k]) for k in ("trade_flow","traveler_flow","foot_traffic","health_demand","craft_demand","credit_demand"))
        if opportunity < 65.0:
            continue
        existing_count = int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE location_id=? AND json_extract(metadata_json,'$.emergent_business')=1 AND status IN ('active','strained','insolvent')", (loc,)).fetchone()[0])
        capacity = max(1, min(3, 1 + int((opportunity - 65.0) // 15.0)))
        if existing_count >= capacity:
            continue
        rng = random.Random(seed * 1000003 + loc * 7919 + year_index * 104729)
        chance = min(0.42, 0.12 + max(0.0, opportunity - 65.0) / 100.0)
        if rng.random() >= chance:
            continue
        archetype = _commercial_emergence_archetype(ctx)
        # Formation needs a real operator. Resolve one from the pre-existing POPBACK ecology;
        # if none is suitable locally, no business appears this year. Demand never spawns an adult.
        from .person_ecology import resolve_background_person
        operator_id = resolve_background_person(
            conn, reason=f"local commercial opportunity at {ctx['location_name']}", location_id=loc,
            occupation_domains=("merchant","clerk","artisan","transport","hospitality"), min_age=20, max_age=70,
            economic_weight=1.0, command_weight=.15, subtype="Local business operator",
        )
        if operator_id is None:
            continue
        label = _emergent_business_name(conn, operator_id, archetype, loc)
        capital = round(12.0 + opportunity * 0.16 + rng.uniform(-2.0, 3.0), 3)
        cash = round(7.0 + opportunity * 0.09 + rng.uniform(-1.5, 2.0), 3)
        broad_kind = {"wholesaler":"other","inn":"service","physician_practice":"service","smithy":"workshop","moneylender":"service","food_shop":"shop"}[archetype]
        eid = create_enterprise(conn, label, broad_kind,
                                owner_actor_id=operator_id, location_id=loc, capital=max(8.0,capital), cash=max(4.0,cash), reputation=45+rng.random()*12, admin_quality=42+rng.random()*18, labor_capacity=42+rng.random()*20, risk_tolerance=35+rng.random()*40,
                                metadata={"emergent_business":True,"background_operator_actor_id":operator_id,"authority":"ENGINE_DERIVED_FROM_PREEXISTING_POPBACK_PLUS_CAMPAIGN_CALIBRATION","display_name_status":"GENERATED_NAME_NOT_CANON","opportunity_score":opportunity,"institutional_form":"ordinary_firm","population_delta":0})
        configure_enterprise_business(conn, eid, archetype, quality=46+rng.random()*12, price_position=45+rng.random()*12, capacity=35+rng.random()*18, clientele_fit=45+rng.random()*15, service_reliability=45+rng.random()*15, regulatory_pressure=10+rng.random()*15, cadence_days=30, metadata={"authority":"ENGINE_DERIVED_STRUCTURAL_BUSINESS","background_operator_actor_id":operator_id,"population_delta":0})
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_ecology_state'").fetchone():
            conn.execute("""INSERT INTO enterprise_ecology_state(enterprise_id,founded_day,crystallized_day,structural_origin,last_review_day,metadata_json)
                            VALUES (?,?,?,'formed_during_simulation',?,?) ON CONFLICT(enterprise_id) DO NOTHING""",
                         (eid,day,day,day,json.dumps({"real_popback_operator":True,"population_delta":0},sort_keys=True)))
        created += 1
    return {"commercial_emergence_reviews": reviewed, "latent_merchants_created": created, "structural_enterprises_created": created, "merchant_house_candidates": candidates}

def next_civilian_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals = []
    r = conn.execute("SELECT MIN(next_review_day) FROM market_conditions WHERE next_review_day>? AND next_review_day<=?", (after_day, end_day)).fetchone()[0]
    if r is not None: vals.append(int(r))
    r = conn.execute("SELECT MIN(scheduled_day) FROM auctions WHERE status='scheduled' AND scheduled_day>? AND scheduled_day<=?", (after_day, end_day)).fetchone()[0]
    if r is not None: vals.append(int(r))
    b = next_business_due_day(conn, after_day, end_day)
    if b is not None: vals.append(int(b))
    h = next_household_life_due_day(conn, after_day, end_day)
    if h is not None: vals.append(int(h))
    from . import agreement_terms, places, ventures
    for nxt in (agreement_terms.next_terms_due_day, places.next_places_due_day, ventures.next_ventures_due_day):
        try:
            v = nxt(conn, after_day, end_day)
        except sqlite3.OperationalError:  # a database made before the business layer's tables
            v = None
        if v is not None: vals.append(int(v))
    from . import tiers
    if tiers.batching(conn):
        try:
            r = conn.execute("""SELECT MIN(json_extract(experience_json,'$.next_review_day')) FROM actor_careers WHERE status='active'
                                AND json_extract(experience_json,'$.next_review_day')>? AND json_extract(experience_json,'$.next_review_day')<=?""",
                             (after_day, end_day)).fetchone()[0]
        except sqlite3.OperationalError:
            r = None
        if r is not None: vals.append(int(r))
    # Active civilian systems are updated at a coarse 30-day cadence; exact scheduled events still interrupt earlier.
    next_month = ((after_day // 30) + 1) * 30
    if next_month <= end_day and conn.execute(
        """SELECT 1 FROM civilian_projects WHERE status='active'
           UNION SELECT 1 FROM production_sites WHERE active=1
           UNION SELECT 1 FROM buildings WHERE status IN ('active','strained','derelict')
           UNION SELECT 1 FROM style_adoption
           UNION SELECT 1 FROM credit_agreements WHERE status IN ('current','late')
           UNION SELECT 1 FROM professional_memberships WHERE status='active'
           LIMIT 1"""
    ).fetchone():
        vals.append(next_month)
    return min(vals) if vals else None


def process_due_civilian(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    markets = conn.execute("SELECT * FROM market_conditions WHERE next_review_day<=? ORDER BY next_review_day,location_id,good_id", (day,)).fetchall()
    for row in markets:
        _resolve_market(conn, row, day)
    sites = conn.execute("SELECT * FROM production_sites WHERE active=1 AND last_resolved_day<?", (day,)).fetchall()
    for row in sites:
        _resolve_production(conn, row, day)
    try:
        projects = conn.execute("SELECT * FROM civilian_projects WHERE status='active' AND last_resolved_day<? AND id NOT IN (SELECT project_id FROM venture_details)", (day,)).fetchall()
    except sqlite3.OperationalError:  # no venture table yet: every project is a Caerness one
        projects = conn.execute("SELECT * FROM civilian_projects WHERE status='active' AND last_resolved_day<?", (day,)).fetchall()
    for row in projects:
        _resolve_project(conn, row, day, event_logger)
    auctions = conn.execute("SELECT id FROM auctions WHERE status='scheduled' AND scheduled_day<=? ORDER BY scheduled_day,id", (day,)).fetchall()
    for a in auctions:
        resolve_auction(conn, int(a[0]), event_logger=event_logger)
    _resolve_households(conn, day)
    _resolve_enterprise_status(conn, day)
    careers = review_careers(conn, day, event_logger=event_logger)
    shadow = _resolve_shadow_links(conn, day)
    from . import agreement_terms, places, ventures
    try:
        agreement_terms.process_due_terms(conn, day)  # first: rent paid this day is seen by the place
        places.process_due_places(conn, day)
        ventures.process_due_ventures(conn, day)
    except sqlite3.OperationalError:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agreement_terms'").fetchone():
            raise  # the tables are there: a real error
    businesses = process_due_businesses(conn, day)
    emergence = _review_latent_commercial_emergence(conn, day)
    deep = process_due_civilian_life(conn, day, event_logger=event_logger)
    household_life = process_due_household_life(conn, day, event_logger=event_logger)
    return {"markets": len(markets), "production_sites": len(sites), "projects": len(projects), "auctions": len(auctions),
            "careers": careers, "shadow_links": shadow, "business_cycles": len(businesses), **emergence, **deep, **household_life}


def civilian_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    base = {
        "day": _day(conn),
        "households": int(conn.execute("SELECT COUNT(*) FROM households WHERE status!='historical'").fetchone()[0]),
        "enterprises": int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE status!='historical'").fetchone()[0]),
        "market_conditions": int(conn.execute("SELECT COUNT(*) FROM market_conditions").fetchone()[0]),
        "production_sites": int(conn.execute("SELECT COUNT(*) FROM production_sites WHERE active=1").fetchone()[0]),
        "active_projects": int(conn.execute("SELECT COUNT(*) FROM civilian_projects WHERE status='active'").fetchone()[0]),
        "cultural_objects": int(conn.execute("SELECT COUNT(*) FROM cultural_objects WHERE status!='destroyed'").fetchone()[0]),
        "scheduled_auctions": int(conn.execute("SELECT COUNT(*) FROM auctions WHERE status='scheduled'").fetchone()[0]),
        "shadow_links": int(conn.execute("SELECT COUNT(*) FROM shadow_market_links WHERE status IN ('latent','active')").fetchone()[0]),
    }
    base.update(civilian_life_summary(conn))
    base["business_ecology"] = business_ecology_summary(conn)
    base["household_life"] = household_life_summary(conn)
    return base


def ensure_career_track(conn: sqlite3.Connection, key: str, name: str, domain: str, *, description: str | None = None,
                        typical_entry_age: int | None = None, institution_kind: str | None = None,
                        stages: list[dict[str, Any]] | None = None) -> int:
    conn.execute(
        """INSERT OR IGNORE INTO career_tracks(key,name,domain,description,typical_entry_age,institution_kind)
           VALUES (?,?,?,?,?,?)""",
        (key, name, domain, description, typical_entry_age, institution_kind),
    )
    tid = int(conn.execute("SELECT id FROM career_tracks WHERE key=?", (key,)).fetchone()[0])
    for idx, st in enumerate(stages or []):
        conn.execute(
            """INSERT OR IGNORE INTO career_stages(track_id,stage_key,stage_name,sequence_index,description,entry_requirements_json,responsibilities_json,exit_paths_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            (tid, st["key"], st.get("name", st["key"]), int(st.get("sequence", idx)), st.get("description"),
             json.dumps(st.get("requirements", {}), sort_keys=True), json.dumps(st.get("responsibilities", {}), sort_keys=True),
             json.dumps(st.get("exit_paths", []), sort_keys=True)),
        )
    return tid


def start_career(conn: sqlite3.Connection, actor_id: int, track_id: int, *, stage_key: str | None = None,
                 institution_actor_id: int | None = None, mentor_actor_id: int | None = None) -> int:
    day = _day(conn)
    if stage_key:
        stage = conn.execute("SELECT id FROM career_stages WHERE track_id=? AND stage_key=?", (track_id, stage_key)).fetchone()
    else:
        stage = conn.execute("SELECT id FROM career_stages WHERE track_id=? ORDER BY sequence_index,id LIMIT 1", (track_id,)).fetchone()
    sid = int(stage[0]) if stage else None
    cur = conn.execute(
        """INSERT INTO actor_careers(actor_id,track_id,current_stage_id,institution_actor_id,mentor_actor_id,started_day,stage_started_day,status,experience_json,reputation_json)
           VALUES (?,?,?,?,?,?,?,'active','{}','{}')""",
        (actor_id, track_id, sid, institution_actor_id, mentor_actor_id, day, day),
    )
    return int(cur.lastrowid)


def review_careers(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> int:
    reviewed = 0
    from . import tiers
    batching = tiers.batching(conn)
    if batching:
        # S1: a quiet person's career is brought up to date on its own weekly stamp (it integrates the days since, so nothing is
        # lost) or on the exact day its next stage's time gate opens; a rising person's career is reviewed daily.
        rising = tiers.sql_ids(conn, day)
        rows = conn.execute(
            f"""SELECT * FROM actor_careers WHERE status='active'
                AND (COALESCE(json_extract(experience_json,'$.next_review_day'),0)<=? OR actor_id IN ({rising}))""", (day,)).fetchall()
        rising_set = tiers.rising_actor_ids(conn, day)
    else:
        rows = conn.execute("SELECT * FROM actor_careers WHERE status='active'").fetchall()
        rising_set = frozenset()
    for c in rows:
        exp = json.loads(c["experience_json"] or "{}")
        first_time = "next_review_day" not in exp
        base_last = c["stage_started_day"] if c["stage_started_day"] is not None else (c["started_day"] if c["started_day"] is not None else day)
        last = int(exp.get("last_review_day", base_last))
        elapsed = max(0, day - last)
        if elapsed <= 0:
            continue
        reviewed += 1
        exp["days_in_career"] = int(exp.get("days_in_career", 0)) + elapsed
        exp["days_in_stage"] = int(exp.get("days_in_stage", 0)) + elapsed
        exp["last_review_day"] = day
        if batching:
            exp["next_review_day"] = day + 1 if int(c["actor_id"]) in rising_set else day + (1 + int(c["id"]) % tiers.BATCH_DAYS if first_time else tiers.BATCH_DAYS)
        current = conn.execute("SELECT * FROM career_stages WHERE id=?", (c["current_stage_id"],)).fetchone() if c["current_stage_id"] else None
        next_stage = None
        if current:
            next_stage = conn.execute("SELECT * FROM career_stages WHERE track_id=? AND sequence_index>? ORDER BY sequence_index,id LIMIT 1",
                                      (c["track_id"], current["sequence_index"])).fetchone()
        if next_stage:
            req = json.loads(next_stage["entry_requirements_json"] or "{}")
            min_days = int(req.get("min_days_in_stage", 0))
            eligible = int(exp.get("days_in_stage", 0)) >= min_days
            if batching and not eligible:
                remaining = min_days - int(exp.get("days_in_stage", 0))
                if remaining < int(exp["next_review_day"]) - day:
                    exp["next_review_day"] = day + remaining  # the exact day the time gate opens
            domain = req.get("competence_domain")
            min_score = float(req.get("min_competence", 0))
            if domain:
                row = conn.execute("SELECT ac.score FROM actor_competence ac JOIN competence_domains cd ON cd.id=ac.domain_id WHERE ac.actor_id=? AND cd.domain_key=?", (c["actor_id"], domain)).fetchone()
                eligible = eligible and bool(row and float(row[0]) >= min_score)
            if eligible:
                exp["eligible_stage_id"] = int(next_stage["id"])
                exp["eligible_since_day"] = exp.get("eligible_since_day", day)
                if bool(req.get("auto_advance", False)):
                    conn.execute("UPDATE actor_careers SET current_stage_id=?,stage_started_day=?,experience_json=? WHERE id=?",
                                 (next_stage["id"], day, json.dumps({**exp, "days_in_stage":0, "last_review_day":day, "next_review_day": day + 1}, sort_keys=True), c["id"]))
                    if event_logger:
                        actor = conn.execute("SELECT name,current_location_id FROM actors WHERE id=?", (c["actor_id"],)).fetchone()
                        event_logger(day=day,event_type="civilian:career_advance",title=f"Career advancement: {actor['name']}",
                                     summary=f"{actor['name']} advanced to {next_stage['stage_name']}.",severity=1,
                                     source_actor_id=c["actor_id"],target_actor_ids=(c["actor_id"],),location_id=actor["current_location_id"])
                    continue
        conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (json.dumps(exp, sort_keys=True), c["id"]))
    return reviewed


def _resolve_shadow_links(conn: sqlite3.Connection, day: int) -> int:
    # Exposure is a world-time process, not a checkpoint-count process. Before v0.37 every
    # invocation advanced exposure once, so adding unrelated simulation checkpoints could make
    # crime easier to discover. Use updated_day as the exposure clock instead.
    changed = 0
    for row in conn.execute("SELECT * FROM shadow_market_links WHERE status IN ('latent','active')").fetchall():
        elapsed = max(0, int(day) - int(row["updated_day"]))
        if elapsed <= 0:
            continue
        periods = elapsed / 30.0
        rng = random.Random(_seed(conn, 9000000 + int(row["id"]) * 211 + day))
        pressure = float(row["pressure"])
        drift = pressure * 0.015 * periods
        noise = rng.uniform(-1.0, 1.0) * max(0.15, periods ** 0.5)
        exposure = min(100.0, max(0.0, float(row["exposure"]) + drift + noise))
        status = "active" if pressure >= 25 else str(row["status"])
        if exposure >= 85:
            status = "exposed"
        conn.execute("UPDATE shadow_market_links SET exposure=?,status=?,updated_day=? WHERE id=?", (exposure,status,day,row["id"]))
        changed += 1
    return changed
```

## engine/merchant.py

```python
from __future__ import annotations

import json
import math
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def add_enterprise_staff(conn: sqlite3.Connection, enterprise_id: int, actor_id: int, *, role: str = "factor",
                         authority: float = 60, specialty: str = "trade", metadata: dict[str, Any] | None = None) -> None:
    conn.execute(
        """INSERT INTO enterprise_staff(enterprise_id,actor_id,role,authority,specialty,status,joined_day,metadata_json)
           VALUES (?,?,?,?,?,'active',?,?)
           ON CONFLICT(enterprise_id,actor_id) DO UPDATE SET role=excluded.role,authority=excluded.authority,
             specialty=excluded.specialty,status='active',metadata_json=excluded.metadata_json""",
        (enterprise_id, actor_id, role, max(0, min(100, float(authority))), specialty, _day(conn),
         json.dumps(metadata or {}, sort_keys=True)),
    )


def authorized_enterprises(conn: sqlite3.Connection, actor_id: int, *, minimum_authority: float = 40) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT DISTINCT e.* FROM civilian_enterprises e
           LEFT JOIN enterprise_staff s ON s.enterprise_id=e.id AND s.actor_id=? AND s.status='active'
           WHERE e.status IN ('active','strained','insolvent')
             AND (e.owner_actor_id=? OR (s.actor_id IS NOT NULL AND s.authority>=?))
           ORDER BY e.id""",
        (actor_id, actor_id, float(minimum_authority)),
    ).fetchall()


def record_market_observation(conn: sqlite3.Connection, enterprise_id: int, location_id: int, good_id: int, *,
                              observer_actor_id: int | None = None, observed_day: int | None = None,
                              received_day: int | None = None, source_kind: str = "market_report",
                              source_actor_id: int | None = None, reliability: float = .85,
                              price: float | None = None, supply: float | None = None, demand: float | None = None,
                              metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    observed_day = day if observed_day is None else int(observed_day)
    received_day = day if received_day is None else int(received_day)
    m = conn.execute(
        "SELECT current_price,supply,demand FROM market_conditions WHERE location_id=? AND good_id=?",
        (location_id, good_id),
    ).fetchone()
    if not m:
        raise ValueError("market condition does not exist")
    cur = conn.execute(
        """INSERT INTO merchant_market_observations(
               enterprise_id,observer_actor_id,location_id,good_id,observed_day,received_day,
               observed_price,observed_supply,observed_demand,source_kind,source_actor_id,reliability,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (enterprise_id, observer_actor_id, location_id, good_id, observed_day, received_day,
         float(m["current_price"] if price is None else price), float(m["supply"] if supply is None else supply),
         float(m["demand"] if demand is None else demand), source_kind, source_actor_id,
         max(0, min(1, float(reliability))), json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def commission_market_report(conn: sqlite3.Connection, enterprise_id: int, actor_id: int,
                             location_id: int, good_id: int) -> int:
    ent = conn.execute("SELECT location_id FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone()
    if not ent:
        raise ValueError("unknown enterprise")
    day = _day(conn)
    lag = 0
    if ent["location_id"] is not None and int(ent["location_id"]) != int(location_id):
        from .ecology import find_route_path, evaluate_route_leg
        current = int(ent["location_id"])
        path = find_route_path(conn, current, int(location_id), day=day)
        if not path:
            raise ValueError("market cannot be reached for report")
        for rid in path:
            ev = evaluate_route_leg(conn, int(rid), current, day=day)
            lag += max(1, int(math.ceil(float(ev["days"]))))
            current = int(ev["target"])
    return record_market_observation(
        conn, enterprise_id, location_id, good_id, observer_actor_id=actor_id, observed_day=day,
        received_day=day + lag, source_kind="commissioned_report", reliability=.82,
        metadata={"transmission_lag_days": lag},
    )


def latest_market_observation(conn: sqlite3.Connection, enterprise_id: int, location_id: int, good_id: int,
                              day: int | None = None) -> sqlite3.Row | None:
    day = _day(conn) if day is None else int(day)
    return conn.execute(
        """SELECT * FROM merchant_market_observations
           WHERE enterprise_id=? AND location_id=? AND good_id=? AND received_day<=?
           ORDER BY observed_day DESC,received_day DESC,id DESC LIMIT 1""",
        (enterprise_id, location_id, good_id, day),
    ).fetchone()


def create_trade_offer(conn: sqlite3.Connection, seller_enterprise_id: int, stock_id: int,
                       quantity: float, unit_price: float, *, expires_day: int | None = None,
                       metadata: dict[str, Any] | None = None) -> int:
    st = conn.execute(
        "SELECT * FROM commercial_stock WHERE id=? AND enterprise_id=?", (stock_id, seller_enterprise_id)
    ).fetchone()
    if not st:
        raise ValueError("seller does not own stock lot")
    quantity = float(quantity)
    if quantity <= 0 or quantity > float(st["quantity"]) + 1e-9:
        raise ValueError("invalid offer quantity")
    if unit_price <= 0:
        raise ValueError("unit price must be positive")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO merchant_trade_offers(
               seller_enterprise_id,stock_id,location_id,good_id,quantity_available,unit_price,
               published_day,expires_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,'open',?)""",
        (seller_enterprise_id, stock_id, int(st["location_id"]), int(st["good_id"]), quantity,
         float(unit_price), day, expires_day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def observe_trade_offer(conn: sqlite3.Connection, enterprise_id: int, actor_id: int, offer_id: int, *,
                        received_day: int | None = None) -> None:
    off = conn.execute("SELECT id FROM merchant_trade_offers WHERE id=? AND status='open'", (offer_id,)).fetchone()
    if not off:
        raise ValueError("offer unavailable")
    day = _day(conn)
    received = day if received_day is None else int(received_day)
    conn.execute(
        """INSERT INTO merchant_offer_awareness(enterprise_id,actor_id,offer_id,observed_day,received_day)
           VALUES (?,?,?,?,?)
           ON CONFLICT(enterprise_id,offer_id) DO UPDATE SET actor_id=excluded.actor_id,
             observed_day=excluded.observed_day,received_day=excluded.received_day""",
        (enterprise_id, actor_id, offer_id, day, received),
    )


def create_trade_contract(conn: sqlite3.Connection, buyer_enterprise_id: int, offer_id: int, quantity: float, *,
                          settlement_kind: str = "cash_on_delivery", due_day: int | None = None,
                          metadata: dict[str, Any] | None = None) -> int:
    off = conn.execute("SELECT * FROM merchant_trade_offers WHERE id=? AND status='open'", (offer_id,)).fetchone()
    if not off:
        raise ValueError("offer unavailable")
    quantity = float(quantity)
    if quantity <= 0 or quantity > float(off["quantity_available"]) + 1e-9:
        raise ValueError("quantity exceeds offer")
    buyer = conn.execute(
        "SELECT * FROM civilian_enterprises WHERE id=? AND status IN ('active','strained')", (buyer_enterprise_id,)
    ).fetchone()
    seller = conn.execute(
        "SELECT * FROM civilian_enterprises WHERE id=? AND status IN ('active','strained')",
        (int(off["seller_enterprise_id"]),),
    ).fetchone()
    if not buyer or not seller or buyer["location_id"] is None:
        raise ValueError("counterparty unavailable")
    amount = quantity * float(off["unit_price"])
    if settlement_kind == "cash_on_delivery" and float(buyer["cash"]) + 1e-9 < amount:
        raise ValueError("buyer lacks cash")
    if settlement_kind not in {"cash_on_delivery", "seller_credit"}:
        raise ValueError("unsupported settlement kind")
    day = _day(conn)
    due = day + 30 if due_day is None else int(due_day)
    cur = conn.execute(
        """INSERT INTO merchant_trade_contracts(
               offer_id,buyer_enterprise_id,seller_enterprise_id,good_id,quantity,unit_price,
               origin_location_id,destination_location_id,settlement_kind,agreed_day,due_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'accepted',?)""",
        (offer_id, buyer_enterprise_id, int(off["seller_enterprise_id"]), int(off["good_id"]), quantity,
         float(off["unit_price"]), int(off["location_id"]), int(buyer["location_id"]), settlement_kind,
         day, due, json.dumps(metadata or {}, sort_keys=True)),
    )
    cid = int(cur.lastrowid)
    remaining = float(off["quantity_available"]) - quantity
    conn.execute(
        "UPDATE merchant_trade_offers SET quantity_available=?,status=? WHERE id=?",
        (max(0, remaining), "filled" if remaining <= 1e-9 else "open", offer_id),
    )
    return cid



def _settle_contract(conn: sqlite3.Connection, contract: sqlite3.Row, day: int) -> bool:
    if str(contract['status']) in {'fulfilled','cancelled','breached'}:
        return False
    amount = float(contract['quantity']) * float(contract['unit_price'])
    buyer = int(contract['buyer_enterprise_id']); seller = int(contract['seller_enterprise_id'])
    if str(contract['settlement_kind']) == 'cash_on_delivery':
        b = conn.execute('SELECT cash FROM civilian_enterprises WHERE id=?',(buyer,)).fetchone()
        if not b or float(b['cash']) + 1e-9 < amount:
            conn.execute("UPDATE merchant_trade_contracts SET status='breached',delivered_quantity=quantity WHERE id=?", (int(contract['id']),))
            return False
        conn.execute('UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?',(amount,day,buyer))
        conn.execute('UPDATE civilian_enterprises SET cash=cash+?,updated_day=? WHERE id=?',(amount,day,seller))
        conn.execute("""INSERT INTO commercial_cash_transfers(day,from_enterprise_id,to_enterprise_id,amount,transfer_kind,trade_contract_id,metadata_json)
                        VALUES (?,?,?,?,'trade_settlement',?,'{}')""",(day,buyer,seller,amount,int(contract['id'])))
        conn.execute("""INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,related_good_id,source_kind,source_id)
                        VALUES (?,?,?,?,?,?,'merchant_contract',?)""",(seller,day,'revenue',amount,'Trade-contract sale',int(contract['good_id']),int(contract['id'])))
        conn.execute("""INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,related_good_id,source_kind,source_id)
                        VALUES (?,?,?,?,?,?,'merchant_contract',?)""",(buyer,day,'purchase',amount,'Trade-contract purchase',int(contract['good_id']),int(contract['id'])))
        paid=amount
    else:
        conn.execute("""INSERT INTO credit_agreements(lender_enterprise_id,borrower_enterprise_id,principal,outstanding,interest_rate_per_30,
                        opened_day,due_day,status,risk,last_review_day,metadata_json)
                        VALUES (?,?,?,?,0.03,?,?,'current',30,?,?)""",
                     (seller,buyer,amount,amount,day,int(contract['due_day']),day,json.dumps({'merchant01_contract_id':int(contract['id'])},sort_keys=True)))
        conn.execute('UPDATE civilian_enterprises SET debt=debt+?,updated_day=? WHERE id=?',(amount,day,buyer))
        paid=0.0
    conn.execute("""UPDATE merchant_trade_contracts SET delivered_quantity=quantity,amount_paid=?,status='fulfilled',fulfilled_day=? WHERE id=?""",
                 (paid,day,int(contract['id'])))
    return True

def dispatch_trade_contract(conn: sqlite3.Connection, contract_id: int, *,
                            carrier_enterprise_id: int | None = None) -> int | None:
    contract = conn.execute(
        "SELECT * FROM merchant_trade_contracts WHERE id=? AND status='accepted'", (contract_id,)
    ).fetchone()
    if not contract:
        raise ValueError("contract is not dispatchable")
    off = conn.execute("SELECT * FROM merchant_trade_offers WHERE id=?", (int(contract["offer_id"]),)).fetchone()
    if not off:
        raise ValueError("contract offer missing")
    if int(contract["origin_location_id"]) == int(contract["destination_location_id"]):
        stock = conn.execute("SELECT * FROM commercial_stock WHERE id=? AND enterprise_id=?",
                             (int(off["stock_id"]), int(contract["seller_enterprise_id"]))).fetchone()
        qty=float(contract["quantity"])
        if not stock or float(stock["quantity"]) + 1e-9 < qty:
            raise ValueError("insufficient seller stock for local delivery")
        day=_day(conn)
        conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?",(qty,day,int(stock["id"])))
        conn.execute("""INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
                        VALUES (?,?,?,?,?,?) ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
                        quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
                     (int(contract["buyer_enterprise_id"]),int(contract["destination_location_id"]),int(contract["good_id"]),qty,day,
                      json.dumps({"authority":"ENGINE_DERIVED","source":"local_trade_contract","contract_id":int(contract_id)},sort_keys=True)))
        conn.execute("UPDATE merchant_trade_contracts SET shipped_quantity=quantity,delivered_quantity=quantity WHERE id=?",(contract_id,))
        fresh=conn.execute("SELECT * FROM merchant_trade_contracts WHERE id=?",(contract_id,)).fetchone()
        _settle_contract(conn,fresh,day)
        return None
    from .logistics import arrange_stock_shipment
    sid = arrange_stock_shipment(
        conn, int(contract["seller_enterprise_id"]), int(off["stock_id"]), float(contract["quantity"]),
        int(contract["destination_location_id"]), recipient_enterprise_id=int(contract["buyer_enterprise_id"]),
        trade_contract_id=contract_id, carrier_enterprise_id=carrier_enterprise_id,
    )
    conn.execute(
        "UPDATE merchant_trade_contracts SET shipped_quantity=quantity,status='in_transit',shipment_id=? WHERE id=?",
        (sid, contract_id),
    )
    return sid


def settle_delivered_shipment(conn: sqlite3.Connection, shipment: sqlite3.Row, day: int) -> None:
    cid = shipment["trade_contract_id"] if "trade_contract_id" in shipment.keys() else None
    if cid is None:
        return
    contract = conn.execute("SELECT * FROM merchant_trade_contracts WHERE id=?", (int(cid),)).fetchone()
    if not contract:
        return
    _settle_contract(conn, contract, day)


def add_production_input_option(conn: sqlite3.Connection, production_site_id: int, input_good_id: int, *,
                                units_per_output: float = 1.0, substitution_group: str = "primary",
                                preference_weight: float = 1.0, initial_share: float = .5) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT INTO production_input_options(
               production_site_id,input_good_id,units_per_output,substitution_group,preference_weight,
               current_share,last_review_day,next_review_day
           ) VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(production_site_id,input_good_id) DO UPDATE SET units_per_output=excluded.units_per_output,
             substitution_group=excluded.substitution_group,preference_weight=excluded.preference_weight""",
        (production_site_id, input_good_id, float(units_per_output), substitution_group,
         float(preference_weight), max(0, min(1, float(initial_share))), day, day + 30),
    )
    return int(conn.execute(
        "SELECT id FROM production_input_options WHERE production_site_id=? AND input_good_id=?",
        (production_site_id, input_good_id),
    ).fetchone()[0])


def resolve_input_substitution(conn: sqlite3.Connection, production_site_id: int, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    site = conn.execute(
        """SELECT ps.*,e.location_id FROM production_sites ps
           JOIN civilian_enterprises e ON e.id=ps.enterprise_id WHERE ps.id=? AND ps.active=1""",
        (production_site_id,),
    ).fetchone()
    if not site or site["location_id"] is None:
        return {"changed": False}
    options = conn.execute(
        """SELECT o.*,mc.current_price FROM production_input_options o
           JOIN market_conditions mc ON mc.good_id=o.input_good_id AND mc.location_id=?
           WHERE o.production_site_id=? AND o.active=1 ORDER BY o.substitution_group,o.id""",
        (int(site["location_id"]), production_site_id),
    ).fetchall()
    if not options:
        return {"changed": False}
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in options:
        groups.setdefault(str(row["substitution_group"]), []).append(row)
    changes: list[dict[str, float | int]] = []
    total_output = float(site["capacity_per_30"])
    for rows in groups.values():
        weights = [
            max(.0001, float(r["preference_weight"])) /
            max(.01, float(r["current_price"]) * float(r["units_per_output"])) for r in rows
        ]
        denom = sum(weights) or 1.0
        for r, weight in zip(rows, weights):
            new_share = weight / denom
            old_share = float(r["current_share"])
            new_qty = total_output * float(r["units_per_output"]) * new_share
            old_qty = total_output * float(r["units_per_output"]) * old_share
            delta = new_qty - old_qty
            conn.execute(
                "UPDATE production_input_options SET current_share=?,last_review_day=?,next_review_day=? WHERE id=?",
                (new_share, day, day + 30, int(r["id"])),
            )
            mc = conn.execute(
                "SELECT demand FROM market_conditions WHERE location_id=? AND good_id=?",
                (int(site["location_id"]), int(r["input_good_id"])),
            ).fetchone()
            if mc:
                conn.execute(
                    "UPDATE market_conditions SET demand=? WHERE location_id=? AND good_id=?",
                    (max(0, float(mc["demand"]) + delta * 1.5), int(site["location_id"]), int(r["input_good_id"])),
                )
            changes.append({"good_id": int(r["input_good_id"]), "old_share": old_share,
                            "new_share": new_share, "demand_delta": delta})
    return {"changed": True, "production_site_id": production_site_id, "changes": changes}


def apply_supply_shock(conn: sqlite3.Connection, location_id: int, good_id: int, quantity: float, *,
                       source: str = "scenario") -> dict[str, float]:
    from .civilian import _price
    market = conn.execute(
        "SELECT * FROM market_conditions WHERE location_id=? AND good_id=?", (location_id, good_id)
    ).fetchone()
    if not market:
        raise ValueError("market condition does not exist")
    before = float(market["current_price"])
    supply = max(0, float(market["supply"]) + float(quantity))
    base = float(conn.execute("SELECT base_price FROM market_goods WHERE id=?", (good_id,)).fetchone()[0])
    price = _price(base, supply, float(market["demand"]), float(market["transport_pressure"]),
                   float(market["risk_pressure"]), float(market["tax_pressure"]))
    meta = json.loads(market["metadata_json"] or "{}")
    meta["last_supply_shock_source"] = source
    conn.execute(
        "UPDATE market_conditions SET supply=?,current_price=?,metadata_json=? WHERE location_id=? AND good_id=?",
        (supply, price, json.dumps(meta, sort_keys=True), location_id, good_id),
    )
    return {"supply_before": float(market["supply"]), "supply_after": supply,
            "price_before": before, "price_after": price}



def _merchant_cycle_due(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM engine_meta WHERE key='merchant_next_market_cycle_day'").fetchone()
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _route_information_lag(conn: sqlite3.Connection, origin: int, destination: int, day: int, *, route_snapshot=None) -> int | None:
    if int(origin) == int(destination):
        return 0
    if route_snapshot is not None:
        from .ecology import route_information_lag_snapshot
        return route_information_lag_snapshot(route_snapshot, int(origin), int(destination))
    from .ecology import find_route_path, evaluate_route_leg
    path = find_route_path(conn, int(origin), int(destination), day=day)
    if not path:
        return None
    current = int(origin); lag = 0
    for rid in path:
        ev = evaluate_route_leg(conn, int(rid), current, day=day)
        lag += max(1, int(math.ceil(float(ev['days']))))
        current = int(ev['target'])
    return lag


def _ordinary_market_cycle(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Low-resolution public-market routine for ordinary enterprises/factors.

    This is deliberately not omniscient strategic trading. It only (a) exposes owned physical
    stock as local public offers, (b) records the local market book for authorized factors, and
    (c) lets public offers travel to other authorized factors with route-derived information lag.
    Rich choices still belong to DEC-01 actors after the information reaches them.
    """
    conn.execute("UPDATE merchant_trade_offers SET status='expired' WHERE status='open' AND expires_day IS NOT NULL AND expires_day<?", (day,))
    offers_created = observations = awareness = 0

    # Ordinary public listing of a bounded share of actually owned physical stock.
    stocks = conn.execute(
        """SELECT s.*,e.status AS enterprise_status FROM commercial_stock s
           JOIN civilian_enterprises e ON e.id=s.enterprise_id
           WHERE s.quantity>0.75 AND e.status IN ('active','strained') ORDER BY s.id"""
    ).fetchall()
    for st in stocks:
        if conn.execute("SELECT 1 FROM merchant_trade_offers WHERE stock_id=? AND status='open'", (int(st['id']),)).fetchone():
            continue
        market = conn.execute("SELECT current_price FROM market_conditions WHERE location_id=? AND good_id=?",
                              (int(st['location_id']), int(st['good_id']))).fetchone()
        if not market:
            continue
        qty = min(10.0, max(0.5, float(st['quantity']) * .4))
        create_trade_offer(
            conn, int(st['enterprise_id']), int(st['id']), qty, max(.01, float(market['current_price']) * 1.02),
            expires_day=day + 60,
            metadata={'authority':'ENGINE_DERIVED','source':'ordinary_public_market_cycle','low_resolution_listing':True},
        )
        offers_created += 1

    staff = conn.execute(
        """SELECT s.enterprise_id,s.actor_id,e.location_id FROM enterprise_staff s
           JOIN civilian_enterprises e ON e.id=s.enterprise_id
           WHERE s.status='active' AND s.authority>=40 AND e.status IN ('active','strained') AND e.location_id IS NOT NULL
           ORDER BY s.enterprise_id,s.actor_id"""
    ).fetchall()
    offers = conn.execute(
        """SELECT o.* FROM merchant_trade_offers o
           WHERE o.status='open' AND (o.expires_day IS NULL OR o.expires_day>=?) ORDER BY o.id""", (day,)
    ).fetchall()
    # ROUTE-01: one authoritative read-only graph snapshot per market cycle.  This keeps
    # route/environment truth in SQL while avoiding thousands of repeated path queries.
    from .ecology import build_route_path_snapshot
    route_snapshot = build_route_path_snapshot(conn, day=day) if staff and offers else None
    for sf in staff:
        eid=int(sf['enterprise_id']); aid=int(sf['actor_id']); loc=int(sf['location_id'])
        # A factor physically based at a market can know its ordinary public price/supply book.
        for mc in conn.execute("SELECT good_id FROM market_conditions WHERE location_id=? ORDER BY good_id", (loc,)).fetchall():
            gid=int(mc['good_id'])
            last=conn.execute(
                """SELECT observed_day FROM merchant_market_observations
                   WHERE enterprise_id=? AND location_id=? AND good_id=? AND source_kind='ordinary_local_market_book'
                   ORDER BY observed_day DESC,id DESC LIMIT 1""", (eid,loc,gid)).fetchone()
            if last and day-int(last[0]) < 25:
                continue
            record_market_observation(
                conn,eid,loc,gid,observer_actor_id=aid,observed_day=day,received_day=day,
                source_kind='ordinary_local_market_book',reliability=.9,
                metadata={'authority':'ENGINE_DERIVED','low_resolution_public_market':True},
            )
            observations += 1
        # Public offers are not telepathy: remote awareness arrives after route-derived delay.
        for off in offers:
            if int(off['seller_enterprise_id']) == eid:
                continue
            if conn.execute("SELECT 1 FROM merchant_offer_awareness WHERE enterprise_id=? AND offer_id=?", (eid,int(off['id']))).fetchone():
                continue
            lag=_route_information_lag(conn,int(off['location_id']),loc,day,route_snapshot=route_snapshot)
            if lag is None:
                continue
            observe_trade_offer(conn,eid,aid,int(off['id']),received_day=day+lag)
            awareness += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('merchant_next_market_cycle_day',?)", (str(day+30),))
    return {'offers_created':offers_created,'observations':observations,'offer_awareness':awareness}

def next_merchant_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    candidates: list[int] = []
    from .aggregate_trade import next_aggregate_trade_due_day
    from .world_package import system_enabled
    aggregate_due = next_aggregate_trade_due_day(conn, after_day, end_day) if system_enabled(conn, "caerness_trade") else None
    if aggregate_due is not None:
        candidates.append(int(aggregate_due))
    cycle = _merchant_cycle_due(conn)
    if cycle is not None and after_day < cycle <= end_day:
        candidates.append(cycle)
    r = conn.execute(
        "SELECT MIN(next_review_day) FROM production_input_options WHERE active=1 AND next_review_day>? AND next_review_day<=?",
        (after_day, end_day),
    ).fetchone()
    if r and r[0] is not None:
        candidates.append(int(r[0]))
    r = conn.execute(
        "SELECT MIN(due_day) FROM merchant_trade_contracts WHERE status IN ('accepted','in_transit') AND due_day>? AND due_day<=?",
        (after_day, end_day),
    ).fetchone()
    if r and r[0] is not None:
        candidates.append(int(r[0]))
    return min(candidates) if candidates else None


def process_due_merchant(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str, int | float]:
    from .aggregate_trade import process_due_aggregate_trade
    from .world_package import system_enabled
    aggregate_result = process_due_aggregate_trade(conn, day, event_logger=event_logger) if system_enabled(conn, "caerness_trade") else {}
    cycle_result = {'offers_created':0,'observations':0,'offer_awareness':0}
    cycle = _merchant_cycle_due(conn)
    if cycle is not None and cycle <= day:
        cycle_result = _ordinary_market_cycle(conn, day)
    rows = conn.execute(
        "SELECT DISTINCT production_site_id FROM production_input_options WHERE active=1 AND next_review_day<=? ORDER BY production_site_id",
        (day,),
    ).fetchall()
    changed = 0
    for row in rows:
        if resolve_input_substitution(conn, int(row[0]), day).get("changed"):
            changed += 1
    overdue = conn.execute(
        "SELECT id FROM merchant_trade_contracts WHERE status IN ('accepted','in_transit') AND due_day<?",
        (day,),
    ).fetchall()
    for row in overdue:
        conn.execute(
            "UPDATE merchant_trade_contracts SET status='breached' WHERE id=? AND delivered_quantity<quantity",
            (int(row[0]),),
        )
    return {"substitution_reviews": len(rows), "changed": changed, "overdue_contracts": len(overdue), **aggregate_result, **cycle_result}


def _commerce_competence(conn: sqlite3.Connection, actor_id: int) -> float:
    row = conn.execute(
        """SELECT MAX(ac.score) FROM actor_competence ac
           JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key='commerce'""",
        (actor_id,),
    ).fetchone()
    return max(0.0, min(100.0, float(row[0] or 0.0)))


def merchant_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int,
                                 envelope: dict[str, Any]):
    from .decision_runtime import DecisionCandidate
    out: list[DecisionCandidate] = []
    commerce_skill = _commerce_competence(conn, actor_id)
    for ent in authorized_enterprises(conn, actor_id):
        eid = int(ent["id"])
        cash = float(ent["cash"])
        awareness = conn.execute(
            """SELECT a.enterprise_id,a.actor_id,a.offer_id,a.observed_day,a.received_day AS awareness_received,o.*
               FROM merchant_offer_awareness a JOIN merchant_trade_offers o ON o.id=a.offer_id
               WHERE a.enterprise_id=? AND a.received_day<=? AND o.status='open'
                 AND (o.expires_day IS NULL OR o.expires_day>=?)
               ORDER BY a.received_day DESC,o.id LIMIT 6""",
            (eid, day, day),
        ).fetchall()
        for offer in awareness:
            if int(offer["seller_enterprise_id"]) == eid:
                continue
            quantity = min(float(offer["quantity_available"]), max(1.0, cash / max(.01, float(offer["unit_price"])) * .35))
            cost = quantity * float(offer["unit_price"])
            if quantity <= 0 or cost > cash + 1e-9:
                continue
            observed = latest_market_observation(conn, eid, int(offer["location_id"]), int(offer["good_id"]), day)
            ref_price = float(observed["observed_price"]) if observed else float(offer["unit_price"])
            discount = max(-1.5, min(2.0, (ref_price - float(offer["unit_price"])) / max(.01, ref_price) * 4))
            reading_bonus = min(.6, commerce_skill / 200.0) if observed else 0.0
            out.append(DecisionCandidate(
                key=f"merchant:accept_offer:{eid}:{int(offer['offer_id'])}", provider_key="merchant",
                action_kind="accept_trade_offer", utility=4.2 + discount + reading_bonus,
                rationale=f"Accept the specific observed offer #{int(offer['offer_id'])} for {quantity:.2f} units.",
                execution_kind="merchant_action",
                payload={"enterprise_id": eid, "offer_id": int(offer["offer_id"]), "quantity": quantity,
                         "settlement_kind": "cash_on_delivery"},
                information_basis={"enterprise_id": eid, "offer_awareness_received_day": int(offer["awareness_received"]),
                                   "market_observation_id": int(observed["id"]) if observed else None,
                                   "commerce_competence": commerce_skill},
                tags=("merchant", "specific_offer", "bounded_information"), estimated_cost=cost,
                risk=max(.06, .16 - commerce_skill / 1200.0),
            ))
        stocks = conn.execute(
            "SELECT * FROM commercial_stock WHERE enterprise_id=? AND quantity>0.5 ORDER BY quantity DESC,id LIMIT 4",
            (eid,),
        ).fetchall()
        for stock in stocks:
            remote = conn.execute(
                """SELECT * FROM merchant_market_observations
                   WHERE enterprise_id=? AND good_id=? AND location_id<>? AND received_day<=?
                   ORDER BY observed_price DESC,observed_day DESC LIMIT 1""",
                (eid, int(stock["good_id"]), int(stock["location_id"]), day),
            ).fetchone()
            if not remote:
                continue
            local = latest_market_observation(conn, eid, int(stock["location_id"]), int(stock["good_id"]), day)
            if not local:
                continue
            local_price = float(local["observed_price"])
            minimum_premium = max(1.04, 1.14 - commerce_skill / 1000.0)
            if float(remote["observed_price"]) <= local_price * minimum_premium:
                continue
            quantity = min(float(stock["quantity"]) * .4, 10.0)
            out.append(DecisionCandidate(
                key=f"merchant:move_stock:{eid}:{int(stock['id'])}:{int(remote['location_id'])}", provider_key="merchant",
                action_kind="move_stock_to_market",
                utility=3.8 + min(2.0, (float(remote["observed_price"]) / local_price - 1) * 5),
                rationale="Move owned stock toward a specifically observed higher-price market.",
                execution_kind="merchant_action",
                payload={"enterprise_id": eid, "stock_id": int(stock["id"]), "quantity": quantity,
                         "destination_location_id": int(remote["location_id"])},
                information_basis={"remote_market_observation_id": int(remote["id"]),
                                   "local_market_observation_id": int(local["id"]),
                                   "commerce_competence": commerce_skill,
                                   "minimum_price_premium": round(minimum_premium, 4)},
                tags=("merchant", "stock", "shipment"), risk=max(.08, .22 - commerce_skill / 800.0),
            ))
        stale_after_days = max(20, int(round(45 - commerce_skill * .25)))
        stale = conn.execute(
            """SELECT * FROM merchant_market_observations
               WHERE enterprise_id=? AND received_day<=? AND (? - observed_day)>=?
               ORDER BY observed_day ASC LIMIT 1""",
            (eid, day, day, stale_after_days),
        ).fetchone()
        if stale:
            out.append(DecisionCandidate(
                key=f"merchant:refresh_report:{eid}:{int(stale['location_id'])}:{int(stale['good_id'])}",
                provider_key="merchant", action_kind="refresh_market_report", utility=4.0,
                rationale="Commission a fresh report because the enterprise record is stale.",
                execution_kind="merchant_action",
                payload={"enterprise_id": eid, "location_id": int(stale["location_id"]), "good_id": int(stale["good_id"])},
                information_basis={"stale_observation_id": int(stale["id"]),
                                   "commerce_competence": commerce_skill,
                                   "stale_after_days": stale_after_days},
                tags=("merchant", "information", "stale_record"), risk=.03,
            ))
    return out


def execute_merchant_action(conn: sqlite3.Connection, actor_id: int, action_kind: str,
                            payload: dict[str, Any], day: int) -> dict[str, Any]:
    eid = int(payload.get("enterprise_id") or 0)
    if eid not in {int(e["id"]) for e in authorized_enterprises(conn, actor_id)}:
        return {"summary": "Merchant action blocked: actor lacks enterprise authority.", "blocked": True}
    try:
        if action_kind == "accept_trade_offer":
            conn.execute("SAVEPOINT merchant_accept_offer")
            try:
                cid = create_trade_contract(
                    conn, eid, int(payload["offer_id"]), float(payload["quantity"]),
                    settlement_kind=str(payload.get("settlement_kind") or "cash_on_delivery"),
                )
                sid = dispatch_trade_contract(conn, cid)
                conn.execute("RELEASE SAVEPOINT merchant_accept_offer")
            except Exception:
                conn.execute("ROLLBACK TO SAVEPOINT merchant_accept_offer")
                conn.execute("RELEASE SAVEPOINT merchant_accept_offer")
                raise
            if sid is None:
                status=conn.execute("SELECT status FROM merchant_trade_contracts WHERE id=?",(cid,)).fetchone()
                return {"summary": f"Accepted observed local trade offer; contract #{cid} resolved as {status[0] if status else 'unknown'}.",
                        "contract_id": cid, "shipment_id": None}
            return {"summary": f"Accepted observed trade offer and dispatched contract #{cid} as shipment #{sid}.",
                    "contract_id": cid, "shipment_id": sid}
        if action_kind == "move_stock_to_market":
            from .logistics import arrange_stock_shipment
            sid = arrange_stock_shipment(
                conn, eid, int(payload["stock_id"]), float(payload["quantity"]), int(payload["destination_location_id"])
            )
            return {"summary": f"Dispatched owned stock as shipment #{sid}.", "shipment_id": sid}
        if action_kind == "refresh_market_report":
            oid = commission_market_report(conn, eid, actor_id, int(payload["location_id"]), int(payload["good_id"]))
            row = conn.execute("SELECT received_day FROM merchant_market_observations WHERE id=?", (oid,)).fetchone()
            return {"summary": f"Commissioned market report #{oid}; it becomes usable on day {int(row[0])}.",
                    "observation_id": oid}
        return {"summary": f"Merchant action blocked: unsupported action {action_kind}.", "blocked": True}
    except Exception as exc:
        return {"summary": f"Merchant action blocked: {exc}", "blocked": True}
```

## engine/craft.py

```python
from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def create_recipe(conn: sqlite3.Connection, recipe_key: str, name: str, output_good_id: int, *,
                  output_quantity: float = 1.0, base_duration_days: float = 1.0,
                  skill_domain: str = "craft", min_skill: float = 0.0,
                  metadata: dict[str, Any] | None = None) -> int:
    if output_quantity <= 0 or base_duration_days <= 0:
        raise ValueError("recipe output quantity and duration must be positive")
    if not conn.execute("SELECT 1 FROM market_goods WHERE id=?", (output_good_id,)).fetchone():
        raise ValueError("unknown recipe output good")
    conn.execute(
        """INSERT INTO craft_recipes(recipe_key,name,output_good_id,output_quantity,base_duration_days,
               skill_domain,min_skill,active,metadata_json)
           VALUES (?,?,?,?,?,?,?,1,?)
           ON CONFLICT(recipe_key) DO UPDATE SET name=excluded.name,output_good_id=excluded.output_good_id,
             output_quantity=excluded.output_quantity,base_duration_days=excluded.base_duration_days,
             skill_domain=excluded.skill_domain,min_skill=excluded.min_skill,active=1,metadata_json=excluded.metadata_json""",
        (recipe_key, name, output_good_id, float(output_quantity), float(base_duration_days), skill_domain,
         max(0.0, min(100.0, float(min_skill))), _json(metadata or {})),
    )
    return int(conn.execute("SELECT id FROM craft_recipes WHERE recipe_key=?", (recipe_key,)).fetchone()[0])


def add_recipe_input(conn: sqlite3.Connection, recipe_id: int, input_good_id: int, *,
                     group_key: str, units_per_batch: float = 1.0, preference_weight: float = 1.0,
                     metadata: dict[str, Any] | None = None) -> int:
    if units_per_batch <= 0 or preference_weight <= 0:
        raise ValueError("recipe input quantity and preference weight must be positive")
    cur = conn.execute(
        """INSERT INTO craft_recipe_inputs(recipe_id,group_key,input_good_id,units_per_batch,preference_weight,active,metadata_json)
           VALUES (?,?,?,?,?,1,?)
           ON CONFLICT(recipe_id,group_key,input_good_id) DO UPDATE SET units_per_batch=excluded.units_per_batch,
             preference_weight=excluded.preference_weight,active=1,metadata_json=excluded.metadata_json""",
        (recipe_id, group_key, input_good_id, float(units_per_batch), float(preference_weight), _json(metadata or {})),
    )
    if cur.lastrowid:
        return int(cur.lastrowid)
    return int(conn.execute(
        "SELECT id FROM craft_recipe_inputs WHERE recipe_id=? AND group_key=? AND input_good_id=?",
        (recipe_id, group_key, input_good_id),
    ).fetchone()[0])


def add_recipe_facility_requirement(conn: sqlite3.Connection, recipe_id: int, facility_kind: str, *,
                                    minimum_capacity: float = 1.0, minimum_condition: float = 20.0) -> None:
    conn.execute(
        """INSERT INTO craft_recipe_facility_requirements(recipe_id,facility_kind,minimum_capacity,minimum_condition)
           VALUES (?,?,?,?)
           ON CONFLICT(recipe_id,facility_kind) DO UPDATE SET minimum_capacity=excluded.minimum_capacity,
             minimum_condition=excluded.minimum_condition""",
        (recipe_id, facility_kind, max(0.01, float(minimum_capacity)), max(0.0, min(100.0, float(minimum_condition)))),
    )


def add_facility(conn: sqlite3.Connection, enterprise_id: int, location_id: int, facility_kind: str, name: str, *,
                 capacity: float = 1.0, condition: float = 100.0,
                 metadata: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO craft_facilities(enterprise_id,location_id,facility_kind,name,capacity,condition,active,metadata_json)
           VALUES (?,?,?,?,?,?,1,?)""",
        (enterprise_id, location_id, facility_kind, name, max(0.01, float(capacity)),
         max(0.0, min(100.0, float(condition))), _json(metadata or {})),
    )
    return int(cur.lastrowid)


def bind_recipe_to_site(conn: sqlite3.Connection, production_site_id: int, recipe_id: int, *, is_default: bool = True) -> None:
    site = conn.execute("SELECT good_id FROM production_sites WHERE id=? AND active=1", (production_site_id,)).fetchone()
    recipe = conn.execute("SELECT output_good_id FROM craft_recipes WHERE id=? AND active=1", (recipe_id,)).fetchone()
    if not site or not recipe:
        raise ValueError("active site and recipe required")
    if int(site["good_id"]) != int(recipe["output_good_id"]):
        raise ValueError("recipe output does not match production-site good")
    if is_default:
        conn.execute("UPDATE craft_site_recipes SET is_default=0 WHERE production_site_id=?", (production_site_id,))
    conn.execute(
        """INSERT INTO craft_site_recipes(production_site_id,recipe_id,is_default,active)
           VALUES (?,?,?,1)
           ON CONFLICT(production_site_id,recipe_id) DO UPDATE SET is_default=excluded.is_default,active=1""",
        (production_site_id, recipe_id, 1 if is_default else 0),
    )
    conn.execute("UPDATE production_sites SET production_mode='tracked' WHERE id=?", (production_site_id,))


def assign_site_worker(conn: sqlite3.Connection, production_site_id: int, actor_id: int, *,
                       role: str = "craftsperson", capacity_share: float = 1.0, active: bool = True) -> None:
    conn.execute(
        """INSERT INTO craft_site_workers(production_site_id,actor_id,role,capacity_share,status,assigned_day)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(production_site_id,actor_id) DO UPDATE SET role=excluded.role,
             capacity_share=excluded.capacity_share,status=excluded.status""",
        (production_site_id, actor_id, role, max(0.01, float(capacity_share)), "active" if active else "inactive", _day(conn)),
    )


def _craft_skill(conn: sqlite3.Connection, production_site_id: int, skill_domain: str, site_skill: float) -> tuple[float, list[int]]:
    rows = conn.execute(
        """SELECT w.actor_id,w.capacity_share,COALESCE(MAX(ac.score),0) AS score
           FROM craft_site_workers w
           LEFT JOIN competence_domains d ON d.domain_key=?
           LEFT JOIN actor_competence ac ON ac.actor_id=w.actor_id AND ac.domain_id=d.id
           WHERE w.production_site_id=? AND w.status='active'
           GROUP BY w.actor_id,w.capacity_share ORDER BY score DESC,w.actor_id""",
        (skill_domain, production_site_id),
    ).fetchall()
    if not rows:
        return max(0.0, min(100.0, float(site_skill))), []
    total = sum(float(r["capacity_share"]) for r in rows) or 1.0
    weighted = sum(float(r["score"]) * float(r["capacity_share"]) for r in rows) / total
    return max(0.0, min(100.0, weighted)), [int(r["actor_id"]) for r in rows]


def validate_recipe_dependency_closure(conn: sqlite3.Connection, recipe_id: int, enterprise_id: int | None = None) -> dict[str, Any]:
    """Validate structural material/facility closure at the selected tracked resolution."""
    recipe = conn.execute("SELECT * FROM craft_recipes WHERE id=? AND active=1", (recipe_id,)).fetchone()
    if not recipe:
        return {"closed": False, "missing": ["recipe"]}
    target_loc = None
    if enterprise_id is not None:
        erow = conn.execute("SELECT location_id FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone()
        target_loc = int(erow[0]) if erow and erow[0] is not None else None
    if target_loc is not None:
        from .ecology import find_route_path

    groups = conn.execute(
        "SELECT DISTINCT group_key FROM craft_recipe_inputs WHERE recipe_id=? AND active=1 ORDER BY group_key", (recipe_id,)
    ).fetchall()
    missing: list[str] = []
    for grow in groups:
        group = str(grow[0])
        opts = conn.execute(
            "SELECT input_good_id FROM craft_recipe_inputs WHERE recipe_id=? AND group_key=? AND active=1",
            (recipe_id, group),
        ).fetchall()
        possible = False
        for opt in opts:
            gid = int(opt[0])
            if enterprise_id is not None and conn.execute(
                "SELECT 1 FROM commercial_stock WHERE enterprise_id=? AND good_id=? AND quantity>0 LIMIT 1", (enterprise_id, gid)
            ).fetchone():
                possible = True
            if not possible:
                offers = conn.execute(
                    """SELECT o.location_id FROM merchant_trade_offers o JOIN commercial_stock s ON s.id=o.stock_id
                       WHERE o.good_id=? AND o.status='open' AND o.quantity_available>0 AND s.quantity>0""", (gid,)
                ).fetchall()
                for off in offers:
                    source_loc = int(off[0])
                    if target_loc is None or source_loc == target_loc or find_route_path(conn, source_loc, target_loc, day=_day(conn)):
                        possible = True; break
            if not possible:
                sources = conn.execute(
                    """SELECT e.location_id FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id
                       WHERE ps.good_id=? AND ps.active=1 AND e.location_id IS NOT NULL""", (gid,)
                ).fetchall()
                for src in sources:
                    source_loc = int(src[0])
                    if target_loc is None or source_loc == target_loc or find_route_path(conn, source_loc, target_loc, day=_day(conn)):
                        possible = True; break
            if possible:
                break
        if not possible:
            missing.append(f"input_group:{group}:no_source_path")
    if enterprise_id is not None:
        for req in conn.execute(
            "SELECT * FROM craft_recipe_facility_requirements WHERE recipe_id=? ORDER BY facility_kind", (recipe_id,)
        ).fetchall():
            q = """SELECT 1 FROM craft_facilities WHERE enterprise_id=? AND facility_kind=? AND active=1
                   AND capacity>=? AND condition>=?"""
            args: list[Any] = [enterprise_id, str(req["facility_kind"]), float(req["minimum_capacity"]), float(req["minimum_condition"])]
            if target_loc is not None:
                q += " AND location_id=?"; args.append(target_loc)
            q += " LIMIT 1"
            if not conn.execute(q, tuple(args)).fetchone():
                missing.append(f"facility:{req['facility_kind']}")
    return {"closed": not missing, "missing": missing}


def create_production_order(conn: sqlite3.Connection, production_site_id: int, requested_output_qty: float, *,
                            recipe_id: int | None = None, priority: int = 50, due_day: int | None = None,
                            metadata: dict[str, Any] | None = None) -> int:
    if requested_output_qty <= 0:
        raise ValueError("production quantity must be positive")
    site = conn.execute(
        """SELECT ps.*,e.location_id FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id
           WHERE ps.id=? AND ps.active=1""", (production_site_id,)
    ).fetchone()
    if not site:
        raise ValueError("unknown active production site")
    if recipe_id is None:
        r = conn.execute(
            """SELECT recipe_id FROM craft_site_recipes WHERE production_site_id=? AND active=1
               ORDER BY is_default DESC,recipe_id LIMIT 1""", (production_site_id,)
        ).fetchone()
        if not r:
            raise ValueError("production site has no bound craft recipe")
        recipe_id = int(r[0])
    if not conn.execute(
        "SELECT 1 FROM craft_site_recipes WHERE production_site_id=? AND recipe_id=? AND active=1",
        (production_site_id, recipe_id),
    ).fetchone():
        raise ValueError("recipe is not bound to production site")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO craft_production_orders(production_site_id,recipe_id,requested_output_qty,priority,status,
               created_day,due_day,next_review_day,blocked_reason,blocked_detail_json,metadata_json)
           VALUES (?,?,?,?, 'queued',?,?,?,NULL,'{}',?)""",
        (production_site_id, recipe_id, float(requested_output_qty), max(0, min(100, int(priority))), day,
         due_day, day + 1, _json(metadata or {})),
    )
    return int(cur.lastrowid)


def _observed_unit_price(conn: sqlite3.Connection, enterprise_id: int, location_id: int, good_id: int, day: int) -> float | None:
    row = conn.execute(
        """SELECT observed_price FROM merchant_market_observations
           WHERE enterprise_id=? AND location_id=? AND good_id=? AND received_day<=?
           ORDER BY observed_day DESC,received_day DESC,id DESC LIMIT 1""",
        (enterprise_id, location_id, good_id, day),
    ).fetchone()
    return float(row[0]) if row else None


def inspect_order(conn: sqlite3.Connection, order_id: int, *, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    row = conn.execute(
        """SELECT o.*,ps.enterprise_id,ps.location_id AS ignored,ps.capacity_per_30,ps.efficiency,ps.skilled_labor,
                  e.location_id,r.output_quantity,r.base_duration_days,r.skill_domain,r.min_skill,r.output_good_id
           FROM craft_production_orders o
           JOIN production_sites ps ON ps.id=o.production_site_id
           JOIN civilian_enterprises e ON e.id=ps.enterprise_id
           JOIN craft_recipes r ON r.id=o.recipe_id WHERE o.id=?""".replace(",ps.location_id AS ignored", ""),
        (order_id,),
    ).fetchone()
    if not row:
        raise ValueError("unknown craft order")
    if row["location_id"] is None:
        return {"feasible": False, "reason": "site_has_no_location", "missing": []}
    enterprise_id = int(row["enterprise_id"]); loc = int(row["location_id"])
    batches = float(row["requested_output_qty"]) / float(row["output_quantity"])
    facility_rows = []
    missing_facilities = []
    for req in conn.execute("SELECT * FROM craft_recipe_facility_requirements WHERE recipe_id=?", (int(row["recipe_id"]),)).fetchall():
        f = conn.execute(
            """SELECT * FROM craft_facilities WHERE enterprise_id=? AND location_id=? AND facility_kind=? AND active=1
               AND capacity>=? AND condition>=? ORDER BY condition DESC,capacity DESC,id LIMIT 1""",
            (enterprise_id, loc, str(req["facility_kind"]), float(req["minimum_capacity"]), float(req["minimum_condition"])),
        ).fetchone()
        if not f:
            missing_facilities.append(str(req["facility_kind"]))
        else:
            facility_rows.append(f)
    skill, workers = _craft_skill(conn, int(row["production_site_id"]), str(row["skill_domain"]), float(row["skilled_labor"]))
    if skill + 1e-9 < float(row["min_skill"]):
        return {"feasible": False, "reason": "insufficient_labor_skill", "skill": skill,
                "minimum_skill": float(row["min_skill"]), "workers": workers, "missing": []}
    if missing_facilities:
        return {"feasible": False, "reason": "missing_facility", "missing_facilities": missing_facilities,
                "skill": skill, "workers": workers, "missing": []}
    groups = conn.execute(
        "SELECT DISTINCT group_key FROM craft_recipe_inputs WHERE recipe_id=? AND active=1 ORDER BY group_key",
        (int(row["recipe_id"]),),
    ).fetchall()
    selections: list[dict[str, Any]] = []; missing: list[dict[str, Any]] = []
    for grow in groups:
        group = str(grow[0]); choices = []
        for opt in conn.execute(
            """SELECT * FROM craft_recipe_inputs WHERE recipe_id=? AND group_key=? AND active=1 ORDER BY id""",
            (int(row["recipe_id"]), group),
        ).fetchall():
            needed = float(opt["units_per_batch"]) * batches
            stock = conn.execute(
                """SELECT * FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=? AND quantity>=?
                   ORDER BY quantity DESC,id LIMIT 1""",
                (enterprise_id, loc, int(opt["input_good_id"]), needed),
            ).fetchone()
            observed = _observed_unit_price(conn, enterprise_id, loc, int(opt["input_good_id"]), day)
            score = (observed * needed / float(opt["preference_weight"])) if observed is not None else (needed / float(opt["preference_weight"]))
            choices.append((stock is not None, score, int(opt["id"]), opt, stock, needed, observed))
        # Choose the technically permitted material from enterprise-accessible price records first.
        # Do not silently fall back to a dearer alternative merely because it is already on the shelf:
        # a deliberate steel choice with insufficient steel is a procurement shortage, not copper production.
        chosen = min(choices, key=lambda c: (c[1], c[2]))
        opt, stock, needed, observed = chosen[3], chosen[4], chosen[5], chosen[6]
        if stock is None:
            missing.append({
                "group_key": group,
                "preferred_input_good_id": int(opt["input_good_id"]),
                "options": [{"input_good_id": int(opt["input_good_id"]), "required_qty": needed,
                             "observed_unit_price": observed}],
                "technically_valid_alternatives": [int(c[3]["input_good_id"]) for c in choices],
            })
            continue
        selections.append({"group_key": group, "recipe_input_id": int(opt["id"]), "input_good_id": int(opt["input_good_id"]),
                           "stock_id": int(stock["id"]), "required_qty": needed, "observed_unit_price": observed})
    facility_condition = min([float(f["condition"]) for f in facility_rows], default=100.0)
    return {"feasible": not missing, "reason": None if not missing else "missing_input", "missing": missing,
            "selections": selections, "skill": skill, "workers": workers, "facility_condition": facility_condition,
            "batches": batches, "enterprise_id": enterprise_id, "location_id": loc, "output_good_id": int(row["output_good_id"]),
            "base_duration_days": float(row["base_duration_days"]), "capacity_per_30": float(row["capacity_per_30"]),
            "efficiency": float(row["efficiency"])}


def _event(conn: sqlite3.Connection, order_id: int, day: int, event_kind: str, detail: dict[str, Any]) -> None:
    conn.execute("INSERT INTO craft_order_events(order_id,day,event_kind,detail_json) VALUES (?,?,?,?)",
                 (order_id, day, event_kind, _json(detail)))


def _reserve_and_start(conn: sqlite3.Connection, order: sqlite3.Row, inspection: dict[str, Any], day: int) -> None:
    for sel in inspection["selections"]:
        stock = conn.execute("SELECT quantity FROM commercial_stock WHERE id=?", (int(sel["stock_id"]),)).fetchone()
        qty = float(sel["required_qty"])
        if not stock or float(stock[0]) + 1e-9 < qty:
            raise RuntimeError("input stock changed before reservation")
        conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?", (qty, day, int(sel["stock_id"])))
        conn.execute(
            """INSERT INTO craft_input_reservations(order_id,recipe_input_id,stock_id,good_id,quantity_reserved,
                   quantity_consumed,status,reserved_day,consumed_day)
               VALUES (?,?,?,?,?,?,'consumed',?,?)""",
            (int(order["id"]), int(sel["recipe_input_id"]), int(sel["stock_id"]), int(sel["input_good_id"]),
             qty, qty, day, day),
        )
    efficiency = max(0.1, float(inspection["efficiency"]) / 100.0)
    skill_factor = max(0.25, float(inspection["skill"]) / 100.0)
    facility_factor = max(0.25, float(inspection["facility_condition"]) / 100.0)
    capacity_days = 30.0 * float(order["requested_output_qty"]) / max(0.01, float(inspection["capacity_per_30"]))
    recipe_days = float(inspection["base_duration_days"]) * float(inspection["batches"])
    duration = max(recipe_days, capacity_days) / max(0.1, (efficiency * skill_factor * facility_factor) ** (1/3))
    completion = day + max(1, int(math.ceil(duration)))
    conn.execute(
        """UPDATE craft_production_orders SET status='in_progress',started_day=COALESCE(started_day,?),next_review_day=?,
           blocked_reason=NULL,blocked_detail_json='{}',selected_inputs_json=? WHERE id=?""",
        (day, completion, _json(inspection["selections"]), int(order["id"])),
    )
    _event(conn, int(order["id"]), day, "started", {"completion_day": completion, "inputs": inspection["selections"],
                                                     "skill": inspection["skill"], "workers": inspection["workers"]})


def _complete_order(conn: sqlite3.Connection, order: sqlite3.Row, day: int) -> None:
    details = inspect_order(conn, int(order["id"]), day=day)
    recipe = conn.execute("SELECT * FROM craft_recipes WHERE id=?", (int(order["recipe_id"]),)).fetchone()
    site = conn.execute("SELECT * FROM production_sites WHERE id=?", (int(order["production_site_id"]),)).fetchone()
    ent = conn.execute("SELECT location_id FROM civilian_enterprises WHERE id=?", (int(site["enterprise_id"]),)).fetchone()
    loc = int(ent[0])
    qty = float(order["requested_output_qty"])
    skill = float(details.get("skill", site["skilled_labor"]))
    facility = float(details.get("facility_condition", 100.0))
    quality = max(1.0, min(100.0, 0.40 * skill + 0.35 * float(site["efficiency"]) + 0.25 * facility))
    conn.execute(
        """INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?) ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
             quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
        (int(site["enterprise_id"]), loc, int(recipe["output_good_id"]), qty, day,
         _json({"authority":"ENGINE_DERIVED", "source":"craft_order", "order_id":int(order["id"]), "quality":quality})),
    )
    stock_id = int(conn.execute(
        "SELECT id FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",
        (int(site["enterprise_id"]), loc, int(recipe["output_good_id"])),
    ).fetchone()[0])
    conn.execute(
        "INSERT INTO craft_output_lots(order_id,stock_id,good_id,quantity,quality,produced_day) VALUES (?,?,?,?,?,?)",
        (int(order["id"]), stock_id, int(recipe["output_good_id"]), qty, quality, day),
    )
    conn.execute(
        "UPDATE craft_production_orders SET status='completed',completed_day=?,next_review_day=?,quality=? WHERE id=?",
        (day, day, quality, int(order["id"])),
    )
    _event(conn, int(order["id"]), day, "completed", {"stock_id": stock_id, "quantity": qty, "quality": quality})


def process_order(conn: sqlite3.Connection, order_id: int, day: int) -> bool:
    order = conn.execute("SELECT * FROM craft_production_orders WHERE id=?", (order_id,)).fetchone()
    if not order or str(order["status"]) in {"completed", "cancelled"}:
        return False
    if str(order["status"]) == "in_progress":
        if int(order["next_review_day"]) <= day:
            _complete_order(conn, order, day)
            return True
        return False
    inspection = inspect_order(conn, order_id, day=day)
    if inspection["feasible"]:
        _reserve_and_start(conn, order, inspection, day)
        return True
    reason = str(inspection["reason"] or "blocked")
    status = {"missing_input":"waiting_input", "missing_facility":"waiting_facility",
              "insufficient_labor_skill":"waiting_labor"}.get(reason, "blocked")
    conn.execute(
        """UPDATE craft_production_orders SET status=?,blocked_reason=?,blocked_detail_json=?,next_review_day=? WHERE id=?""",
        (status, reason, _json(inspection), day + 3, order_id),
    )
    _event(conn, order_id, day, "blocked", {"reason": reason, "detail": inspection})
    return True


def next_craft_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row = conn.execute(
        """SELECT MIN(next_review_day) FROM craft_production_orders
           WHERE status IN ('queued','waiting_input','waiting_facility','waiting_labor','in_progress','blocked')
             AND next_review_day>? AND next_review_day<=?""", (after_day, end_day)
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def process_due_craft(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    rows = conn.execute(
        """SELECT id FROM craft_production_orders
           WHERE status IN ('queued','waiting_input','waiting_facility','waiting_labor','in_progress','blocked')
             AND next_review_day<=? ORDER BY priority DESC,next_review_day,id""", (day,)
    ).fetchall()
    changed = 0
    for row in rows:
        before = conn.execute("SELECT status FROM craft_production_orders WHERE id=?", (int(row[0]),)).fetchone()[0]
        if process_order(conn, int(row[0]), day):
            after = conn.execute("SELECT status FROM craft_production_orders WHERE id=?", (int(row[0]),)).fetchone()[0]
            changed += int(before != after or after in {"waiting_input","waiting_facility","waiting_labor","blocked"})
            if event_logger and after == "completed":
                event_logger(day=day, event_type="craft:order_completed", title="Production order completed",
                             summary=f"Tracked production order #{int(row[0])} completed with conserved inputs and output.",
                             severity=1, source_actor_id=None, target_actor_ids=())
    return {"due": len(rows), "changed": changed}


def _missing_good_needs(conn: sqlite3.Connection, order: sqlite3.Row) -> list[dict[str, Any]]:
    try:
        detail = json.loads(order["blocked_detail_json"] or "{}")
    except Exception:
        return []
    needs = []
    for group in detail.get("missing") or []:
        for opt in group.get("options") or []:
            needs.append({"group_key": group.get("group_key"), **opt})
    return needs


def craft_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]):
    """Procurement candidates for actual blocked orders, executed by the merchant domain owner."""
    from .decision_runtime import DecisionCandidate
    try:
        from .merchant import authorized_enterprises
        enterprise_ids = [int(e["id"]) for e in authorized_enterprises(conn, actor_id)]
    except Exception:
        return []
    out: list[DecisionCandidate] = []
    for eid in enterprise_ids:
        orders = conn.execute(
            """SELECT o.* FROM craft_production_orders o JOIN production_sites ps ON ps.id=o.production_site_id
               WHERE ps.enterprise_id=? AND o.status='waiting_input' ORDER BY o.priority DESC,o.id LIMIT 4""", (eid,)
        ).fetchall()
        ent = conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()
        cash = float(ent[0] if ent else 0)
        for order in orders:
            for need in _missing_good_needs(conn, order):
                gid = int(need["input_good_id"]); required = float(need["required_qty"])
                offers = conn.execute(
                    """SELECT a.received_day AS awareness_received,o.* FROM merchant_offer_awareness a
                       JOIN merchant_trade_offers o ON o.id=a.offer_id
                       WHERE a.enterprise_id=? AND a.received_day<=? AND o.good_id=? AND o.status='open'
                         AND o.quantity_available>0 AND (o.expires_day IS NULL OR o.expires_day>=?)
                       ORDER BY o.unit_price,o.id""", (eid, day, gid, day)
                ).fetchall()
                for offer in offers:
                    if int(offer["seller_enterprise_id"]) == eid:
                        continue
                    qty = min(required, float(offer["quantity_available"]))
                    cost = qty * float(offer["unit_price"])
                    if qty + 1e-9 < required or cost > cash + 1e-9:
                        continue
                    out.append(DecisionCandidate(
                        key=f"craft:procure:{int(order['id'])}:{int(offer['id'])}", provider_key="craft",
                        action_kind="accept_trade_offer", utility=6.2 + float(order["priority"]) / 100.0,
                        rationale=f"Procure the specific missing input for tracked production order #{int(order['id'])} from an observed offer.",
                        execution_kind="merchant_action",
                        payload={"enterprise_id": eid, "offer_id": int(offer["id"]), "quantity": qty,
                                 "settlement_kind": "cash_on_delivery", "production_order_id": int(order["id"])},
                        information_basis={"production_order_id": int(order["id"]), "offer_awareness_received_day": int(offer["awareness_received"]),
                                           "missing_group": need.get("group_key"), "required_qty": required},
                        tags=("craft", "procurement", "bounded_information"), estimated_cost=cost, risk=.12,
                    ))
                    break
    return out


def craft_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "recipes": int(conn.execute("SELECT COUNT(*) FROM craft_recipes WHERE active=1").fetchone()[0]),
        "facilities": int(conn.execute("SELECT COUNT(*) FROM craft_facilities WHERE active=1").fetchone()[0]),
        "open_orders": int(conn.execute("SELECT COUNT(*) FROM craft_production_orders WHERE status NOT IN ('completed','cancelled')").fetchone()[0]),
        "completed_orders": int(conn.execute("SELECT COUNT(*) FROM craft_production_orders WHERE status='completed'").fetchone()[0]),
        "reserved_or_consumed_input": float(conn.execute("SELECT COALESCE(SUM(quantity_consumed),0) FROM craft_input_reservations").fetchone()[0]),
        "output_quantity": float(conn.execute("SELECT COALESCE(SUM(quantity),0) FROM craft_output_lots").fetchone()[0]),
    }
```

## engine/civic_tick.py

```python
"""The politics tick, the protagonist's view and the pushes (politics P1).

One process the world clock runs next to the others. It does nothing in a world whose package carries no offices. Each time it runs
it opens and moves the races, counts the items whose day has come, answers the approvals waiting, runs the vacancy rules, seats the
convicted out, and for each whole week since it last ran draws the exposures of standing payments and lets the field shift. Elections,
votes and vacancy days are dated events: `next_due_day` names them so the skip planner stops on them. Events that touch the player
(a vote on his item or in his body, his primary or his election) go to the event log with him as the source, which is what a skip
stops for; a few things are also entered in his delivery ledger. Impressions are read lazily where they are needed.
"""
from __future__ import annotations

import json
import sqlite3

from . import civic_corruption, civic_graft, civic_seams, civic_shift, civic_votes, offices, races
from .design import figure

CURSOR = "civic_week_cursor"
LAST = "civic_last_day"
WEEK = 7


def enabled(conn) -> bool:
    return offices.enabled(conn)


def _get(conn, key: str) -> int | None:
    r = conn.execute("SELECT value FROM engine_meta WHERE key=?", (key,)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _set(conn, key: str, value: int) -> None:
    conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(int(value))))


def _player(conn) -> int | None:
    from . import player
    p = player.get_player(conn)
    return int(p["player_actor_id"]) if p is not None else None


# ---- when it next has something to do --------------------------------------------------------------------------------

def next_due_day(conn: sqlite3.Connection, after_day: int, through_day: int) -> int | None:
    if not enabled(conn):
        return None
    cands: list[int] = []
    cands.append((int(after_day) // WEEK + 1) * WEEK)  # the weekly pass falls on whole weeks of the calendar
    window = int(figure(conn, "race_open_days", 330))
    for r in conn.execute("SELECT * FROM races WHERE status='open' ORDER BY id").fetchall():
        for d in (races.filing_close(conn, r), r["primary_day"], r["election_day"]):
            if d is not None:
                cands.append(int(d))
    for r in conn.execute("SELECT result_json FROM races WHERE status='decided' ORDER BY id").fetchall():
        res = json.loads(r[0] or "{}")
        if not res.get("seated") and res.get("term_start_day") is not None:
            cands.append(int(res["term_start_day"]))
    for o in conn.execute("SELECT office_key FROM offices WHERE filled_by='elected' ORDER BY id").fetchall():
        nd = offices.next_dates(conn, o[0], int(after_day))
        if nd:
            cands.append(int(nd["election_day"]) - window)
    for (d,) in conn.execute("SELECT vote_day FROM civic_items WHERE status='open'").fetchall():
        cands.append(int(d))
    wait = int(figure(conn, "vacancy_fill_days", 21))
    for (d,) in conn.execute("SELECT since_day FROM office_vacancies WHERE status='pending'").fetchall():
        cands.append(int(d) + wait)
    cands = [d for d in cands if int(after_day) < d <= int(through_day)]
    return min(cands) if cands else None


# ---- the run -------------------------------------------------------------------------------------------------------

def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    if not enabled(conn):
        return {}
    day = int(day)
    prev = _get(conn, LAST)
    prev = day - 1 if prev is None else prev
    out: dict = {}
    out["races"] = races.advance(conn, day)
    out["items"] = civic_votes.advance(conn, day)
    out["vacancies"] = offices.process_vacancies(conn, day)
    out["convicted"] = civic_corruption.convictions(conn, day)
    cur = _get(conn, CURSOR)
    cur = (day // WEEK) * WEEK - WEEK if cur is None else cur
    weeks = {"exposed": 0, "weakened": 0, "transferred": 0, "taken_up": 0, "walkouts": 0}
    while cur + WEEK <= day:
        cur += WEEK
        for k, v in civic_graft.weekly(conn, cur).items():
            weeks[k] = weeks.get(k, 0) + v
        weeks["exposed"] += len(civic_corruption.exposure_check(conn, cur))
        for k, v in civic_shift.weekly_shift(conn, cur).items():
            weeks[k] = weeks.get(k, 0) + v
        out["convicted"] += civic_corruption.convictions(conn, cur)
    out.update(weeks)
    _set(conn, CURSOR, cur)
    _set(conn, LAST, day)
    if event_logger is not None or _player(conn) is not None:
        _tell_player(conn, prev, day, event_logger)
    return out


def _sits_in(conn, actor: int, body_key: str) -> bool:
    return actor in {a for _, _, a in offices.members(conn, body_key)}


def _tell_player(conn, prev: int, day: int, logger) -> None:
    """Events and pushes for the protagonist: each is a dated happening he is part of."""
    me = _player(conn)
    if me is None:
        return
    from .simulation import SimEvent, log_event

    def emit(d: int, kind: str, title: str, text: str, ref: dict, push: str | None = None) -> None:
        if logger is not None:
            logger(day=d, event_type=f"politics:{kind}", title=title, summary=text, severity=4, source_actor_id=me)
        else:
            log_event(conn, SimEvent(day=d, event_type=f"politics:{kind}", title=title, summary=text, severity=4, source_actor_id=me))
        if push:
            civic_seams.push(conn, me, kind, push, d, ref)

    for it in conn.execute("SELECT * FROM civic_items WHERE vote_day>? AND vote_day<=? AND status<>'open' ORDER BY vote_day,id", (int(prev), int(day))).fetchall():
        sub = json.loads(it["subject_json"] or "{}")
        sponsor = sub.get("sponsor")
        if (sponsor is not None and int(sponsor) == me) or _sits_in(conn, me, it["body_office_key"]):
            what = sub.get("title") or it["item_kind"]
            emit(int(it["vote_day"]), "vote", f"A vote: {what}", f"{it['body_office_key']}: {what} {it['status']}.", {"item": int(it["id"])},
                 push=(f"The vote on {what} is in: {it['status']}." if sponsor is not None and int(sponsor) == me else None))
    for r in conn.execute("""SELECT r.*,o.office_key FROM races r JOIN offices o ON o.id=r.office_id
                             WHERE ((r.primary_day>? AND r.primary_day<=?) OR (r.election_day>? AND r.election_day<=?)) ORDER BY r.election_day,r.id""",
                          (int(prev), int(day), int(prev), int(day))).fetchall():
        if not (me in races.candidates(conn, int(r["id"])) or offices.holder(conn, r["office_key"]) == me or _backer(conn, me, r)):
            continue
        if r["primary_day"] is not None and int(prev) < int(r["primary_day"]) <= int(day):
            emit(int(r["primary_day"]), "primary", f"The primary for {r['office_key']}", f"The primary for {r['office_key']} is held.", {"race": int(r["id"])})
        if int(prev) < int(r["election_day"]) <= int(day):
            res = json.loads(r["result_json"] or "{}")
            emit(int(r["election_day"]), "election", f"Election night: {r['office_key']}", f"The count for {r['office_key']} is in.", {"race": int(r["id"])},
                 push=f"Election night for {r['office_key']}: " + (f"the winner is {_name(conn, res.get('winner'))}." if res.get("winner") is not None else "no result."))
    owed_to = {int(str(e["debtor_ref"]).split(":")[1]) for e in civic_seams.ledger_open(conn, me) if str(e["debtor_ref"]).startswith("person:")} \
        | {int(str(e["creditor_ref"]).split(":")[1]) for e in civic_seams.ledger_open(conn, me) if str(e["creditor_ref"]).startswith("person:")}
    owed_to.discard(me)
    if owed_to:
        q = ",".join("?" * len(owed_to))
        for c in conn.execute(f"SELECT id,day,offender_actor_id,crime_kind FROM crime_reports WHERE offender_actor_id IN ({q}) AND day>? AND day<=? ORDER BY day,id",
                              (*sorted(owed_to), int(prev), int(day))).fetchall():
            civic_seams.push(conn, me, "indictment", f"{_name(conn, c['offender_actor_id'])}, who you deal with, is accused of {c['crime_kind']}.", int(c["day"]), {"report": int(c["id"])})


def _backer(conn, me: int, race) -> bool:
    """He holds a seat in an organisation that has a man in the race."""
    return bool(conn.execute("""SELECT 1 FROM race_candidates c JOIN org_seats s ON s.org_actor_id=c.party_org_id AND s.actor_id=? AND s.status='active'
                                WHERE c.race_id=? LIMIT 1""", (int(me), int(race["id"]))).fetchone())


def _name(conn, actor) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(actor),)).fetchone() if actor is not None else None
    return r[0] if r else "no one"


# ---- the view (behind the firewall) -------------------------------------------------------------------------------------

def view(conn, observer: int, day: int) -> dict:
    """What the protagonist can know of the politics around him: the seats he holds and those near him, who owes him and whom he owes,
    the calendar ahead, how the voters hold him, and the standing payments he is part of. Nothing he is not party to."""
    me = int(observer)
    held = offices.offices_of(conn, me)
    near: list[dict] = []
    seen = set(held)
    for key in held:
        o = offices.office(conn, key)
        body = offices._json(o["body_json"], {})
        for k in (body.get("members") or []) + ([o["appointer_office_key"]] if o["appointer_office_key"] else []):
            if k and k not in seen:
                seen.add(k)
                h = offices.holder(conn, k)
                near.append({"office": k, "holder": _name(conn, h) if h is not None else None})
    owes, owed = [], []
    for e in civic_seams.ledger_open(conn, me):
        mine = e["debtor_ref"] == f"person:{me}"
        other = e["creditor_ref"] if mine else e["debtor_ref"]
        who = _name(conn, int(str(other).split(":")[1])) if str(other).startswith("person:") else str(other)
        (owes if mine else owed).append({"who": who, "what": e["purpose"] if e["purpose"] else e["ref_kind"], "kind": e["ref_kind"]})
    ahead: list[dict] = []
    for r in conn.execute("SELECT r.*,o.office_key FROM races r JOIN offices o ON o.id=r.office_id WHERE r.status='open' ORDER BY r.election_day").fetchall():
        if me in races.candidates(conn, int(r["id"])) or offices.holder(conn, r["office_key"]) == me or r["office_key"] in held:
            if r["primary_day"] is not None and int(r["primary_day"]) >= int(day):
                ahead.append({"what": f"primary for {r['office_key']}", "day": int(r["primary_day"])})
            ahead.append({"what": f"election for {r['office_key']}", "day": int(r["election_day"])})
    for it in conn.execute("SELECT * FROM civic_items WHERE status='open' AND vote_day>=? ORDER BY vote_day", (int(day),)).fetchall():
        sub = json.loads(it["subject_json"] or "{}")
        if (sub.get("sponsor") is not None and int(sub["sponsor"]) == me) or _sits_in(conn, me, it["body_office_key"]):
            ahead.append({"what": f"vote: {sub.get('title') or it['item_kind']}", "day": int(it["vote_day"])})
    key = civic_seams._electorate_key(conn)
    voters = [{"voters": r["label"], "held": r["text"], "day": int(r["day"])} for r in conn.execute(
        """SELECT a.label,c.text,c.day FROM claims c JOIN audiences a ON a.id=c.holder_id
           WHERE c.holder_kind='audience' AND c.subject_actor_id=? AND a.key=? ORDER BY c.day DESC LIMIT 8""", (me, key)).fetchall()]
    pay = []
    for a in conn.execute("""SELECT * FROM org_arrangements WHERE status='active' AND (official_actor_id=? OR go_between_actor_id=? OR (payer_kind='actor' AND payer_id=?)) ORDER BY id""",
                          (me, me, me)).fetchall():
        pay.append({"kind": a["kind"], "weekly_usd": float(a["weekly_usd"]), "official": _name(conn, a["official_actor_id"])})
    out = {"holds": held, "near": near, "owes": owes, "owed_by": owed, "ahead": sorted(ahead, key=lambda x: x["day"]), "voters": voters, "payments": pay}
    return {k: v for k, v in out.items() if v}
```

## engine/world.py

```python
from __future__ import annotations

import math
import random
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class WorldProcessResult:
    process_id: int
    day: int
    emitted_events: int
    metric_delta: float


def _rng(conn: sqlite3.Connection, process_id: int, day: int) -> random.Random:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed * 97_531 + process_id * 8_191 + day * 31_337)


def next_world_process_due_day(conn: sqlite3.Connection, after_day: int, through_day: int) -> int | None:
    row = conn.execute(
        """SELECT MIN(next_review_day) FROM world_processes
           WHERE active=1 AND next_review_day>? AND next_review_day<=?""",
        (after_day, through_day),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _clamp(value: float, lower: float | None, upper: float | None) -> float:
    if lower is not None:
        value = max(value, lower)
    if upper is not None:
        value = min(value, upper)
    return value


def _record_location_metric(
    conn: sqlite3.Connection,
    location_id: int,
    key: str,
    delta: float,
    day: int,
) -> None:
    row = conn.execute(
        "SELECT id,value,min_value,max_value FROM location_metrics WHERE location_id=? AND key=?",
        (location_id, key),
    ).fetchone()
    if row:
        value = _clamp(
            float(row["value"]) + delta,
            float(row["min_value"]) if row["min_value"] is not None else None,
            float(row["max_value"]) if row["max_value"] is not None else None,
        )
        conn.execute(
            "UPDATE location_metrics SET value=?,updated_day=? WHERE id=?",
            (value, day, int(row["id"])),
        )
    else:
        conn.execute(
            "INSERT INTO location_metrics(location_id,key,value,updated_day) VALUES (?,?,?,?)",
            (location_id, key, delta, day),
        )


def resolve_world_process(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    day: int,
    *,
    event_logger,
) -> WorldProcessResult:
    """Advance one location/regional process without requiring any actor to be present.

    `event_logger` is injected to avoid importing simulation.py here and creating a cycle.
    It must accept a SimEvent-compatible object or keyword bundle through the local shim below.
    """
    elapsed = max(0, day - int(row["last_resolved_day"]))
    if elapsed <= 0:
        conn.execute(
            "UPDATE world_processes SET next_review_day=? WHERE id=?",
            (day + int(row["cadence_days"]), int(row["id"])),
        )
        return WorldProcessResult(int(row["id"]), day, 0, 0.0)

    process_id = int(row["id"])
    rng = _rng(conn, process_id, day)
    base_delta = float(row["rate_per_30_days"]) * elapsed / 30.0
    noise_scale = abs(base_delta) * float(row["volatility"])
    noise = rng.gauss(0.0, noise_scale) if noise_scale else 0.0
    delta = base_delta + noise
    accumulator = float(row["accumulator"]) + abs(delta)

    if row["location_id"] is not None and row["metric_key"]:
        _record_location_metric(conn, int(row["location_id"]), str(row["metric_key"]), delta, day)

    emitted = 0
    threshold = float(row["event_threshold"])
    while accumulator >= threshold:
        accumulator -= threshold
        emitted += 1
        loc_name = "the wider region"
        if row["location_id"] is not None:
            found = conn.execute("SELECT name FROM locations WHERE id=?", (int(row["location_id"]),)).fetchone()
            if found:
                loc_name = str(found[0])
        event_logger(
            day=day,
            event_type=f"world:{row['process_type']}",
            title=f"Regional change: {loc_name}",
            summary=(
                f"The off-screen regional process '{row['name']}' in {loc_name} accumulated enough change "
                "to become world-significant. This occurred independently of player presence."
            ),
            severity=int(row["event_severity"]),
            location_id=int(row["location_id"]) if row["location_id"] is not None else None,
        )

    conn.execute(
        """UPDATE world_processes
           SET accumulator=?,last_resolved_day=?,next_review_day=? WHERE id=?""",
        (accumulator, day, day + int(row["cadence_days"]), process_id),
    )
    return WorldProcessResult(process_id, day, emitted, delta)


def process_due_world_processes(conn: sqlite3.Connection, day: int, *, event_logger) -> list[WorldProcessResult]:
    rows = conn.execute(
        "SELECT * FROM world_processes WHERE active=1 AND next_review_day<=? ORDER BY next_review_day,id",
        (day,),
    ).fetchall()
    return [resolve_world_process(conn, row, day, event_logger=event_logger) for row in rows]


def catch_up_world_processes(conn: sqlite3.Connection, day: int, *, event_logger) -> list[WorldProcessResult]:
    rows = conn.execute(
        "SELECT * FROM world_processes WHERE active=1 AND last_resolved_day<? ORDER BY id",
        (day,),
    ).fetchall()
    return [resolve_world_process(conn, row, day, event_logger=event_logger) for row in rows]


def world_activity_summary(conn: sqlite3.Connection, since_day: int = 0) -> dict:
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    player_id = int(player[0]) if player and player[0] is not None else None

    total_events = int(conn.execute("SELECT COUNT(*) FROM events WHERE day>=?", (since_day,)).fetchone()[0])
    world_events = int(conn.execute("SELECT COUNT(*) FROM events WHERE day>=? AND event_type LIKE 'world:%'", (since_day,)).fetchone()[0])
    background_events = int(conn.execute("SELECT COUNT(*) FROM events WHERE day>=? AND event_type LIKE 'background:%'", (since_day,)).fetchone()[0])
    npc_decisions = int(conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE day>=?" + (" AND actor_id<>?" if player_id is not None else ""),
        (since_day, player_id) if player_id is not None else (since_day,),
    ).fetchone()[0])
    npc_interactions = int(conn.execute(
        """SELECT COUNT(*) FROM interactions WHERE created_day>=?""" + (
            " AND proposer_actor_id<>? AND recipient_actor_id<>?" if player_id is not None else ""
        ),
        (since_day, player_id, player_id) if player_id is not None else (since_day,),
    ).fetchone()[0])
    player_events = 0
    if player_id is not None:
        player_events = int(conn.execute(
            """SELECT COUNT(DISTINCT e.id) FROM events e
               LEFT JOIN event_targets et ON et.event_id=e.id
               WHERE e.day>=? AND (e.source_actor_id=? OR et.actor_id=?)""",
            (since_day, player_id, player_id),
        ).fetchone()[0])

    return {
        "since_day": since_day,
        "total_events": total_events,
        "regional_world_events": world_events,
        "actor_background_events": background_events,
        "npc_decisions": npc_decisions,
        "npc_to_npc_interactions": npc_interactions,
        "events_directly_involving_player": player_events,
        "camera_principle": (
            "Player presence changes what is observed, not what exists. Off-screen actors and regional processes continue independently."
        ),
    }
```


(End of batch 4 of 5.)
