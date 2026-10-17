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
