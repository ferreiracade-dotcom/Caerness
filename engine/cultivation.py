from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any, Callable

from .health import add_condition, configure_health_profile
from .ecology import environment_effects
from .groundbinding import groundbinding_context

STAGES = ("First", "Temper", "Third", "Breach", "Fifth", "Sixth")
NEXT_STAGE = {None: "First", "First": "Temper", "Temper": "Third", "Third": "Breach", "Breach": "Fifth", "Fifth": "Sixth", "Sixth": None}
LONGEVITY = {"First":"first","Temper":"temper","Third":"third","Breach":"breach","Fifth":"fifth","Sixth":"sixth"}
CORE_CAPACITY = {None:20.0,"First":30.0,"Temper":42.0,"Third":55.0,"Breach":70.0,"Fifth":86.0,"Sixth":105.0}

# Explicit campaign calibration, not setting canon and not a hidden destiny model.
# World-Bible alignment: cultivation begins as a Vessel problem and increasingly becomes a
# Realization problem. Lower transitions are ordinary maturation thresholds; Third -> Breach is
# the first true Realization wall and the first unmistakable Master threshold.
REQUIREMENTS = {
    # No age or nominal duration target exists. Stage change is causal state, never calendar catch-up.
    None:    {"vessel":55.0,"realization":24.0,"practice_cap":30.0,"transition_mode":"vessel_maturation","check_interval":120},
    "First": {"vessel":72.0,"realization":32.0,"practice_cap":40.0,"transition_mode":"vessel_maturation","check_interval":120},
    "Temper":{"vessel":90.0,"realization":44.0,"practice_cap":52.0,"transition_mode":"vessel_maturation","check_interval":180},
    "Third": {"vessel":84.0,"realization":76.0,"practice_cap":65.0,"transition_mode":"realization_wall","check_interval":720,"opportunity_chance":0.055,"success_base":0.22},
    "Breach":{"vessel":86.0,"realization":86.0,"practice_cap":80.0,"transition_mode":"realization_wall","check_interval":730,"opportunity_chance":0.045,"success_base":0.13},
    "Fifth": {"vessel":93.0,"realization":95.0,"practice_cap":88.0,"transition_mode":"realization_wall","check_interval":1095,"opportunity_chance":0.055,"success_base":0.11},
}

# Approximate internal depth immediately after a breakthrough. Opening characters are NOT all
# placed here: their within-Stage depth is unknown and receives heterogeneous campaign calibration.
STAGE_ENTRY_FACTORS = {
    None:(20.0,10.0), "First":(32.0,18.0), "Temper":(32.0,28.0), "Third":(28.0,22.0),
    "Breach":(28.0,22.0), "Fifth":(22.0,28.0), "Sixth":(55.0,65.0),
}
RESOURCE_BANDS = {
    "NONE":15.0,"LOW":25.0,"LOW_MEDIUM":40.0,"MEDIUM":55.0,"MEDIUM_HIGH":70.0,"HIGH":85.0,"VERY_HIGH":95.0,
}

# The Hearth advantage is ecological AND social. These are campaign-calibration fallbacks for
# places whose exact current profile is deliberately not quantified in the World Bible. They are
# not regional Stage caps: an outer-kingdom prodigy can still advance exceptionally quickly, and
# a Hearth cultivator can still plateau through injury, weak teaching, low effort, poor resources
# or an unresolved Realization problem.
HEARTH_SETTLEMENTS = {
    'Hearthlands','Central Hearth','Eastern Hearth','Fellmarch','Ashgrave',
    'Cairnholt','Rivermoor','Amber Court','Toll’s Reach','Redford','Blackfen','Stonecross',
    'Mirehold','Waymeet','Oakridge','Britterwatch','Verenwood','Greywatch','Lysmere','Aldenmoor',
    'Eastwatch','Grand Coven complex','Southern Road belt','Nine Ferries country',
    'Reedmark / Blackwood country','Kastel sphere','Renlow estates','Corr seat district',
    'Wrenfield seat district','White Laurel foothills','Ashgrave margin',
    # Canon cultivation sites embedded in the Hearth/Spine-facing cultivation world. Several of
    # these still lack complete containment edges in the structured seed, so identity is enough.
    'Stillwater','Bell Hollow','Stonepool','Brackwater Springs','Deepwell Basin','Clearwell',
    'Stonewake Caverns','Redroot Vale','Ashgrave Wells','Silent Peak','White Laurel Heights',
}
OUTER_ECOLOGY_BASELINE = {
    'Dunmoor': 42.0, 'Greywood': 40.0, 'Windmere': 40.0, 'Sunreach Confederacy': 40.0,
    'Thornward': 38.0, 'Stormhollow': 39.0, 'Underheaven Empire': 42.0,
}
OUTER_MILIEU_BASELINE = {
    'Dunmoor': 55.0, 'Greywood': 50.0, 'Windmere': 51.0, 'Sunreach Confederacy': 51.0,
    'Thornward': 47.0, 'Stormhollow': 48.0, 'Underheaven Empire': 55.0,
}
# Physical ecology matters most in the Vessel-heavy lower ladder, then less as the bottleneck
# becomes conceptual. Fifth->Sixth rises slightly again because Sixth is explicitly geography-
# sensitive. Milieu captures the Hearth's dense teachers/manuals/peers/medicine/infrastructure.
CONTEXT_WEIGHTS = {
    # Physical ecology and training milieu matter most while Vessel development is dominant.
    # This creates the Bible's Churn/outer-world social offset without any regional Stage cap.
    None:    {'vessel_env':0.65,'vessel_milieu':0.24,'real_env':0.10,'real_milieu':0.22,'opportunity':0.20},
    'First': {'vessel_env':0.65,'vessel_milieu':0.24,'real_env':0.10,'real_milieu':0.24,'opportunity':0.20},
    'Temper':{'vessel_env':0.70,'vessel_milieu':0.30,'real_env':0.10,'real_milieu':0.24,'opportunity':0.18},
    'Third': {'vessel_env':0.28,'vessel_milieu':0.12,'real_env':0.10,'real_milieu':0.30,'opportunity':0.22},
    'Breach':{'vessel_env':0.18,'vessel_milieu':0.10,'real_env':0.08,'real_milieu':0.32,'opportunity':0.18},
    'Fifth': {'vessel_env':0.30,'vessel_milieu':0.08,'real_env':0.12,'real_milieu':0.34,'opportunity':0.22},
    'Sixth': {'vessel_env':0.30,'vessel_milieu':0.06,'real_env':0.10,'real_milieu':0.18,'opportunity':0.0},
}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _load(raw: str | None, default):
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _history(conn: sqlite3.Connection, actor_id: int, kind: str, summary: str, *, stage_before: str | None = None,
             stage_after: str | None = None, metadata: dict[str,Any] | None = None, day: int | None = None) -> int:
    p=conn.execute("SELECT vessel_adaptation,realization_integration FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    cur=conn.execute(
        """INSERT INTO cultivation_history(actor_id,day,history_kind,stage_before,stage_after,summary,vessel_snapshot,realization_snapshot,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (actor_id,_day(conn) if day is None else int(day),kind,stage_before,stage_after,summary,
         (float(p[0]) if p else None),(float(p[1]) if p else None),json.dumps(metadata or {},sort_keys=True)),
    )
    return int(cur.lastrowid)


def _attainment_age_days(conn: sqlite3.Connection, actor_id: int, day: int) -> int | None:
    row=conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if not row or row[0] is None:
        return None
    return max(0,int(day)-int(row[0]))


def _record_stage_attainment(conn: sqlite3.Connection, actor_id: int, stage: str, *,
                              day: int | None, provenance: str, chronology_certainty: str,
                              source_history_id: int | None = None, metadata: dict[str,Any] | None = None) -> None:
    if stage not in STAGES:
        return
    age_days=_attainment_age_days(conn,actor_id,int(day)) if day is not None else None
    conn.execute(
        """INSERT INTO cultivation_stage_attainments
           (actor_id,stage,attained_day,attained_age_days,chronology_certainty,provenance,source_history_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(actor_id,stage) DO UPDATE SET
             attained_day=CASE WHEN excluded.chronology_certainty='known' THEN excluded.attained_day ELSE cultivation_stage_attainments.attained_day END,
             attained_age_days=CASE WHEN excluded.chronology_certainty='known' THEN excluded.attained_age_days ELSE cultivation_stage_attainments.attained_age_days END,
             chronology_certainty=CASE WHEN excluded.chronology_certainty='known' THEN 'known' ELSE cultivation_stage_attainments.chronology_certainty END,
             provenance=CASE WHEN excluded.chronology_certainty='known' THEN excluded.provenance ELSE cultivation_stage_attainments.provenance END,
             source_history_id=COALESCE(excluded.source_history_id,cultivation_stage_attainments.source_history_id),
             metadata_json=CASE WHEN excluded.chronology_certainty='known' THEN excluded.metadata_json ELSE cultivation_stage_attainments.metadata_json END""",
        (actor_id,stage,day,age_days,chronology_certainty,provenance,source_history_id,json.dumps(metadata or {},sort_keys=True)),
    )


def _record_opening_stage_chain(conn: sqlite3.Connection, actor_id: int, current_stage: str | None) -> None:
    if current_stage not in STAGES:
        return
    upto=STAGES.index(current_stage)
    for i,stage in enumerate(STAGES[:upto+1]):
        _record_stage_attainment(
            conn,actor_id,stage,day=None,chronology_certainty='unknown',
            provenance='opening_current_stage' if i==upto else 'opening_prior_stage',
            metadata={'attainment_date_inferred':False,'inverse_age_stage_rule':True},
        )


def record_realization_anchor(conn: sqlite3.Connection, actor_id: int, anchor_kind: str, *, source_kind: str,
                              source_id: int | None = None, weight: float = 1.0, description: str | None = None,
                              metadata: dict[str,Any] | None = None, day: int | None = None) -> int:
    profile=conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if not profile:
        raise ValueError("Actor has no cultivation profile")
    meta=dict(metadata or {})
    # Realization evidence belongs to the problem the practitioner was actually facing. It may
    # remain part of biography after a breakthrough, but it must not become reusable credit for
    # later Stages. This is especially important once Third -> Breach becomes a true insight wall.
    meta.setdefault('stage_at_creation',profile[0])
    meta.setdefault('stage_bound',True)
    anchor_day=_day(conn) if day is None else int(day)
    cur=conn.execute(
        """INSERT INTO realization_anchors(actor_id,day,anchor_kind,source_kind,source_id,weight,description,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (actor_id,anchor_day,anchor_kind,source_kind,source_id,max(0.01,float(weight)),description,
         json.dumps(meta,sort_keys=True)),
    )
    # A concrete Stage-relevant experience should be considered promptly even for a compressed
    # DORMANT/STRATEGIC life.  This changes resolution timing, not the chance or outcome.
    if source_kind!='cultivation_process' and profile[0] in ('Third','Breach','Fifth'):
        conn.execute("""UPDATE cultivation_profiles SET next_review_day=MIN(next_review_day,?)
                        WHERE actor_id=? AND active=1 AND status='active'""",(anchor_day+1,actor_id))
    return int(cur.lastrowid)


def _resource_value(raw: Any) -> float:
    if isinstance(raw,(int,float)):
        return max(0.0,min(100.0,float(raw)))
    return RESOURCE_BANDS.get(str(raw or "MEDIUM").upper(),50.0)


def _teacher_support(conn: sqlite3.Connection, actor_id: int) -> float:
    direct=int(conn.execute("SELECT COUNT(*) FROM teaching_relationships WHERE student_actor_id=? AND status='active'",(actor_id,)).fetchone()[0])
    programs=int(conn.execute("SELECT COUNT(*) FROM education_enrollments WHERE actor_id=? AND status='active'",(actor_id,)).fetchone()[0])
    if direct or programs:
        return min(100.0,20.0 + direct*30.0 + programs*15.0)
    # Continuing membership in a real martial institution still implies ordinary instructors, peers,
    # correction and access to the institution's training environment after a finite foundation
    # course ends. This is not a personal-master relationship and is deliberately weaker.
    rows=conn.execute("""SELECT ip.institution_kind FROM institution_memberships im
                         JOIN institution_profiles ip ON ip.actor_id=im.institution_actor_id
                         WHERE im.member_actor_id=? AND im.status='active'""",(actor_id,)).fetchall()
    martial_tokens=('sect','clan','house','coven','order','military','academy','school')
    if any(token in str(r[0] or '').lower() for r in rows for token in martial_tokens):
        return 35.0
    return 20.0


def _training_effort(conn: sqlite3.Connection, actor_id: int, fallback: float) -> float:
    rows=conn.execute("SELECT practice_quality FROM education_enrollments WHERE actor_id=? AND status='active'",(actor_id,)).fetchall()
    if not rows:
        return max(0.0,min(100.0,float(fallback)))
    avg=sum(float(r[0]) for r in rows)/len(rows)
    return max(0.0,min(100.0,avg/1.5*100.0))


def _injury_constraint(conn: sqlite3.Connection, actor_id: int) -> float:
    rows=conn.execute("""SELECT severity,capacity_impact FROM health_conditions
                         WHERE actor_id=? AND status IN ('active','recovering','chronic')""",(actor_id,)).fetchall()
    if not rows:
        return 0.0
    return min(100.0,max(max(float(r[0]),float(r[1])) for r in rows))


def _source_payload(conn: sqlite3.Connection, actor_id: int) -> dict[str,Any]:
    row=conn.execute("""SELECT source_payload_json FROM source_identity_map
                        WHERE entity_kind='actor' AND entity_id=? AND source_namespace='caerness_seed_v1_1'
                        ORDER BY id LIMIT 1""",(actor_id,)).fetchone()
    return _load(row[0],{}) if row else {}


def _location_chain(conn: sqlite3.Connection, location_id: int | None) -> list[sqlite3.Row]:
    out=[]; seen=set(); lid=location_id
    while lid is not None and int(lid) not in seen and len(out)<8:
        seen.add(int(lid))
        row=conn.execute("SELECT * FROM locations WHERE id=?",(int(lid),)).fetchone()
        if not row: break
        out.append(row); lid=row['parent_location_id']
    return out


def _hearth_context(conn: sqlite3.Connection, actor_id: int, chain: list[sqlite3.Row]) -> bool:
    names={str(r['name']) for r in chain}
    if 'Hearthlands' in names or names & HEARTH_SETTLEMENTS:
        return True
    # Unknown geography does not erase known Churn social context. This is a milieu fallback, not a
    # claim that the actor's exact current coordinates are inside the Hearth.
    if not chain:
        src=_source_payload(conn,actor_id)
        return str(src.get('current') or '') in {'Concord','Undertow','Unsworn','Hollow'}
    return False


def _environment_profile_for_chain(conn: sqlite3.Connection, chain: list[sqlite3.Row]) -> sqlite3.Row | None:
    for loc in chain:
        row=conn.execute("SELECT * FROM location_environment_profiles WHERE location_id=? AND status!='inactive'",(int(loc['id']),)).fetchone()
        if row: return row
    return None


def _institutional_milieu_bonus(conn: sqlite3.Connection, actor_id: int) -> float:
    rows=conn.execute("""SELECT ip.institution_kind
                         FROM institution_memberships im JOIN institution_profiles ip ON ip.actor_id=im.institution_actor_id
                         WHERE im.member_actor_id=? AND im.status='active'""",(actor_id,)).fetchall()
    if not rows: return 0.0
    kinds={str(r[0] or '').lower() for r in rows}
    martial_tokens=('sect','clan','house','coven','order','military','academy','school')
    if any(token in kind for kind in kinds for token in martial_tokens):
        return 10.0
    return 5.0


def _cultivation_context(conn: sqlite3.Connection, actor_id: int, stage: str | None = None, *, day: int | None = None) -> dict[str,Any]:
    """Physical current ecology + surrounding cultivation infrastructure.

    The World Bible makes the Hearth unusually productive because several causes compound: rich
    current, dense teachers, manuals, peers, medicine, Root/elixir and old institutions. This helper
    keeps those causes separate. It never assigns a regional ceiling or automatic promotion.
    """
    a=conn.execute("SELECT current_location_id FROM actors WHERE id=?",(actor_id,)).fetchone()
    lid=int(a[0]) if a and a[0] is not None else None
    chain=_location_chain(conn,lid)
    hearth=_hearth_context(conn,actor_id,chain)
    profile=_environment_profile_for_chain(conn,chain)
    owner=next((str(r['political_owner']) for r in chain if r['political_owner']),None)
    source='fallback'
    load_ratio=0.0
    if profile:
        source='profile'
        repl_factor=1.0
        try:
            repl_factor=float(environment_effects(conn,int(profile['location_id']),_day(conn) if day is None else int(day))['current_replenishment_factor'])
        except Exception:
            repl_factor=1.0
        density=float(profile['current_density']); stability=float(profile['current_stability'])
        repl=float(profile['current_replenishment'])*max(0.25,min(1.75,repl_factor))
        concentration=float(profile['current_concentration'])
        # Stability is valuable but does not turn thin current into rich current. Silent Peak should
        # remain excellent for sealcraft/Groundbinding while only middling for ordinary growth.
        ecology=0.50*density + 0.28*repl + 0.10*stability + 0.12*concentration
        cap=float(profile['current_carrying_capacity']); load=float(profile['current_load'])
        load_ratio=(load/cap) if cap>0 else 0.0
        ecology*=max(0.55,min(1.05,1.02-0.32*load_ratio))
    elif hearth:
        ecology=55.0; source='hearth-regional-fallback'
    else:
        ecology=OUTER_ECOLOGY_BASELINE.get(owner,45.0); source='outer-or-unknown-fallback'

    if hearth:
        milieu=76.0
    else:
        milieu=OUTER_MILIEU_BASELINE.get(owner,50.0)
    if not chain:
        src=_source_payload(conn,actor_id)
        if str(src.get('current') or '') in {'Concord','Undertow','Unsworn','Hollow'}:
            milieu=max(milieu,70.0)
        if bool(src.get('long_road')):
            # Unknown-road location: use a slightly less institution-dense default, while explicit
            # teachers/resources/Realization anchors still travel with the person.
            milieu-=5.0
    milieu+=_institutional_milieu_bonus(conn,actor_id)
    milieu=max(20.0,min(95.0,milieu))
    ecology=max(15.0,min(95.0,ecology))

    w=CONTEXT_WEIGHTS.get(stage,CONTEXT_WEIGHTS[None])
    en=(ecology-50.0)/50.0; mn=(milieu-50.0)/50.0
    vessel_factor=max(0.55,min(1.55,1.0+w['vessel_env']*en+w['vessel_milieu']*mn))
    realization_factor=max(0.65,min(1.45,1.0+w['real_env']*en+w['real_milieu']*mn))
    opportunity_factor=max(0.55,min(1.50,1.0+w['opportunity']*(0.58*en+0.42*mn)))
    # The Temper -> Third transition asks the Vessel to normalize whole-body circulation. The
    # anatomy is universal, but sustaining that volume of adaptation is disproportionately easier
    # in current-rich ground. This is the Bible's outer-world Third bottleneck expressed as
    # ecology, not as a regional Stage cap. Exceptionally rich outer sites can erase the penalty.
    whole_vessel_current_factor=1.0
    if stage=='Temper':
        whole_vessel_current_factor=max(0.25,min(1.12,(ecology/55.0)**4.00))
        vessel_factor*=whole_vessel_current_factor
    gb=groundbinding_context(conn,actor_id)
    if gb:
        vessel_factor*=float(gb['vessel_factor']); realization_factor*=float(gb['realization_factor']); opportunity_factor*=float(gb['opportunity_factor'])
    return {
        'ecology_quality':round(ecology,4),'milieu_quality':round(milieu,4),'hearth_context':hearth,
        'ecology_source':source,'political_owner':owner,'current_load_ratio':round(load_ratio,4),
        'vessel_growth_factor':round(max(0.20,min(1.70,vessel_factor)),6),'realization_growth_factor':round(max(0.25,min(1.60,realization_factor)),6),
        'opportunity_factor':round(max(0.20,min(1.60,opportunity_factor)),6),'whole_vessel_current_factor':round(whole_vessel_current_factor,6),'location_id':lid,
        'groundbinding':gb,
    }


def _environment_quality(conn: sqlite3.Connection, actor_id: int) -> float:
    return float(_cultivation_context(conn,actor_id).get('ecology_quality',45.0))



def _vessel_aptitude(conn: sqlite3.Connection, actor_id: int) -> float:
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    rng=random.Random(seed*1000003 + int(actor_id)*19001 + 460046)
    # Most people cluster around ordinary response, with rare fast/slow tails. This is rate, not destiny.
    return round(max(0.40,min(2.35,math.exp(rng.gauss(-0.05,0.34)))),6)


def _opening_depth_calibration(conn: sqlite3.Connection, actor_id: int, stage: str | None, age: Any,
                               vessel_aptitude: float, realization_aptitude: float) -> tuple[float,float,int]:
    """Heterogeneous within-Stage opening depth without inventing an attainment date.

    The source tells us current Stage, not when it was attained. Current age is therefore
    deliberately ignored: age 60 does not imply that a First is a deep First, any more than
    age 30 implies that a practitioner ought to be Third. Known time-since-attainment may
    inform future calibration; present age alone may not.
    """
    if stage is None:
        return STAGE_ENTRY_FACTORS[None][0],STAGE_ENTRY_FACTORS[None][1],0
    if stage=='Sixth':
        seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
        rng=random.Random(seed*1000003 + actor_id*23003 + 460061)
        d=0.15+0.80*((rng.random()+rng.random())/2.0)
        return 55.0+40.0*d,65.0+32.0*d,int(365*(2.0+8.0*d))
    req=REQUIREMENTS[stage]
    ev,er=STAGE_ENTRY_FACTORS[stage]
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    rng=random.Random(seed*1000003 + actor_id*23003 + 460060)
    base=(rng.random()+rng.random())/2.0
    vessel_depth=max(0.03,min(0.97,0.08+0.84*base+0.08*(vessel_aptitude-1.0)))
    # Insight is related but distinct: exceptional Vessel and exceptional Realization need not coincide.
    rbase=(rng.random()+rng.random())/2.0
    real_depth=max(0.03,min(0.97,0.08+0.84*rbase+0.10*(realization_aptitude-1.0)))
    vessel=ev+(float(req['vessel'])-ev)*vessel_depth
    # An opening practitioner can already have substantial unresolved insight; this is still below
    # the next-Stage solution, and no attainment date is inferred.
    real_ceiling=max(float(req['practice_cap']),float(req['realization'])-0.5)
    real=er+(real_ceiling-er)*real_depth
    # Historical time-since-attainment is unknown at opening and must not be fabricated from
    # current age or cross-sectional Stage averages. observed_stage_days starts at zero.
    return round(vessel,4),round(real,4),0

def seed_cultivation_from_current_source(conn: sqlite3.Connection) -> dict[str,int]:
    """Create authoritative runtime profiles from current source facts plus explicit neutral calibration.

    Stage/Core facts come from the current seed. Stage-relative maturity factors are campaign calibration
    because the World Bible deliberately does not specify how long every named person has held a Stage.
    """
    created=updated=0
    rows=conn.execute("""SELECT a.id,a.status,s.source_payload_json
                         FROM actors a JOIN source_identity_map s ON s.entity_kind='actor' AND s.entity_id=a.id
                         WHERE a.actor_type='character' AND s.source_namespace='caerness_seed_v1_1'""").fetchall()
    for r in rows:
        src=_load(r['source_payload_json'],{})
        stage=src.get('stage') if src.get('stage') in STAGES else None
        core=str(src.get('core_state') or ('Open-Core' if stage else 'Unknown'))
        if core not in {'Open-Core','Closed-Core','Damaged-Core','Destroyed-Core'}:
            core='Unknown'
        rt=src.get('runtime_v1_1') or {}; tr=rt.get('training_state') or {}
        active=bool(str(r['status']).lower()=='active' and core=='Open-Core' and (tr.get('active', stage is not None)))
        aptitude=_realization_aptitude(conn,int(r['id']))
        vessel_aptitude=_vessel_aptitude(conn,int(r['id']))
        vessel,real,opening_maturity_days=_opening_depth_calibration(conn,int(r['id']),stage,src.get('age'),vessel_aptitude,aptitude)
        resource=_resource_value(tr.get('resource_access_band','MEDIUM'))
        injury=0.0 if tr.get('injury_constraint') in (None,'NO_SPECIFIC_INJURY_SEEDED') else 15.0
        teacher=_teacher_support(conn,int(r['id']))
        existing=conn.execute("SELECT actor_id FROM cultivation_profiles WHERE actor_id=?",(int(r['id']),)).fetchone()
        metadata={
            'authority':'SOURCE_FACTS_PLUS_CAMPAIGN_CALIBRATION',
            'source_stage':stage,'source_core_state':src.get('core_state'),
            'stage_attainment_date':'UNKNOWN','final_stage':'NOT_STORED',
            'opening_factor_basis':'heterogeneous within-Stage runtime calibration; not an inferred attainment date or destiny',
            'opening_stage_duration':'UNKNOWN_NOT_INFERRED_FROM_AGE',
            'source_current':src.get('current'),'source_state_sphere':src.get('state_sphere'),'source_long_road':bool(src.get('long_road')),
        }
        cap=CORE_CAPACITY[stage] if core=='Open-Core' else 0.0
        reserve=cap*0.60 if active else 0.0
        # Opening check timing varies with individual tempo; it is not a minimum Stage duration.
        first_check=int(_next_check_day(conn,int(r['id']),0,stage,failed=False)) if stage!='Sixth' else 3650
        opening_review=max(7,min(30,first_check)) if active else 30
        conn.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
                        training_effort,resource_access,teacher_support,injury_constraint,realization_aptitude,vessel_aptitude,next_realization_check_day,
                        core_capacity,current_reserve,sediment_burden,observed_stage_days,plateau_days,last_review_day,next_review_day,status,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?, ?,?)
                        ON CONFLICT(actor_id) DO UPDATE SET core_state=excluded.core_state,
                          current_stage=COALESCE(cultivation_profiles.current_stage,excluded.current_stage),
                          active=CASE WHEN cultivation_profiles.status IN ('retired','ended') THEN 0 ELSE excluded.active END,
                          resource_access=excluded.resource_access,teacher_support=excluded.teacher_support,
                          realization_aptitude=CASE WHEN cultivation_profiles.realization_aptitude=1.0 THEN excluded.realization_aptitude ELSE cultivation_profiles.realization_aptitude END,
                          vessel_aptitude=CASE WHEN cultivation_profiles.vessel_aptitude=1.0 THEN excluded.vessel_aptitude ELSE cultivation_profiles.vessel_aptitude END,
                          next_realization_check_day=CASE WHEN cultivation_profiles.next_realization_check_day<=0 THEN excluded.next_realization_check_day ELSE cultivation_profiles.next_realization_check_day END,
                          core_capacity=CASE WHEN cultivation_profiles.core_capacity<=0 THEN excluded.core_capacity ELSE cultivation_profiles.core_capacity END,
                          current_reserve=CASE WHEN cultivation_profiles.core_capacity<=0 THEN excluded.current_reserve ELSE cultivation_profiles.current_reserve END,
                          metadata_json=excluded.metadata_json""",
                     (int(r['id']),core,stage,1 if active else 0,vessel,real,60.0 if active else 0.0,resource,teacher,injury,aptitude,vessel_aptitude,first_check,cap,reserve,0.0,opening_maturity_days,opening_review,
                      'active' if active else 'paused',json.dumps(metadata,sort_keys=True)))
        _record_opening_stage_chain(conn,int(r['id']),stage)
        if existing:
            updated+=1
        else:
            created+=1
            _history(conn,int(r['id']),'opening_observation',
                     f"Opening cultivation state observed: Core={core}, Stage={stage or 'unstaged/unknown'}.",
                     stage_before=stage,stage_after=stage,metadata={'attainment_day_inferred':False,'authority':'CURRENT_SEED'})
    return {'cultivation_profiles_created':created,'cultivation_profiles_refreshed':updated}


def _rng(conn: sqlite3.Connection, actor_id: int, day: int, salt: int=0) -> random.Random:
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed*1000003 + actor_id*9176 + day*131 + salt)


def _growth_rates(stage: str | None) -> tuple[float,float]:
    # Per 30 days before opportunity/injury/environment multipliers. Realization grows more slowly
    # than Vessel adaptation and is capped by ordinary practice at a stage-specific plateau.
    return {
        None:(2.2,0.95), 'First':(1.65,0.85), 'Temper':(0.90,0.60), 'Third':(1.00,0.68),
        'Breach':(0.85,0.62), 'Fifth':(0.42,0.40), 'Sixth':(0.25,0.28),
    }[stage]


def _realization_aptitude(conn: sqlite3.Connection, actor_id: int) -> float:
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    rng=random.Random(seed*1000003 + int(actor_id)*17011 + 420042)
    return round(0.55 + rng.random()*0.90, 6)


def _next_check_day(conn: sqlite3.Connection, actor_id: int, day: int, stage: str | None, *, failed: bool=False) -> int:
    req=REQUIREMENTS.get(stage)
    if not req:
        return int(day)+3650
    interval=float(req['check_interval'])
    row=conn.execute("SELECT realization_aptitude,vessel_aptitude FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if row:
        ra=float(row[0]); va=float(row[1])
    else:
        ra=_realization_aptitude(conn,actor_id); va=_vessel_aptitude(conn,actor_id)
    ctx=_cultivation_context(conn,actor_id,stage)
    mode=str(req.get('transition_mode','realization_wall'))
    rng=_rng(conn,actor_id,day,421 if failed else 420)
    if mode=='vessel_maturation':
        # Early development is comparatively trainable and predictable. Personal Vessel response
        # and actual conditions dominate; Realization aptitude has only a small timing effect.
        context_tempo=max(0.65,min(1.55,float(ctx['vessel_growth_factor'])**0.85))
        tempo=max(0.50,min(2.20,max(0.35,va)**0.48 * max(0.45,ra)**0.08 * context_tempo))
        jitter=0.72 + rng.random()*0.58
        if failed:
            jitter*=1.08+rng.random()*0.12
    else:
        # Genuine Realization walls have broad, irregular opportunity timing. A powerful body can
        # be ready for years without producing the insight needed for the next Stage.
        context_tempo=max(0.72,min(1.35,float(ctx['opportunity_factor'])**0.65))
        tempo=max(0.48,min(2.05,(max(0.35,ra)*max(0.35,va))**0.32 * context_tempo))
        jitter=0.22 + rng.random()*1.55
        if failed:
            jitter *= 1.20 + rng.random()*0.35
    return int(day + max(7, round(interval*jitter/tempo)))

def _can_seek_breakthrough(conn: sqlite3.Connection, profile: sqlite3.Row) -> bool:
    """Causal readiness for the next Stage, with no minimum time-at-Stage.

    Lower transitions are Vessel-dominant maturation thresholds: ordinary training can supply the
    competence needed once the body is ready. From Third -> Breach onward, routine practice stops
    below the full conceptual requirement and a genuine Realization opportunity is needed.
    """
    stage=profile['current_stage']
    if stage=='Sixth' or stage not in REQUIREMENTS:
        return False
    req=REQUIREMENTS[stage]
    mode=str(req.get('transition_mode','realization_wall'))
    if mode=='vessel_maturation':
        real_floor=float(req['realization'])
    else:
        external=_external_realization_weight(conn,int(profile['actor_id']))
        real_floor=float(req['practice_cap'])*(0.52 if external>=1.0 else 0.68)
    return (float(profile['vessel_adaptation'])>=float(req['vessel']) and
            float(profile['realization_integration'])>=real_floor and
            float(profile['injury_constraint'])<82 and float(profile['training_effort'])>=20)



def _external_realization_rows(conn: sqlite3.Connection, actor_id: int) -> list[sqlite3.Row]:
    stage_row=conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    stage=stage_row[0] if stage_row else None
    out=[]
    rows=conn.execute("""SELECT id,weight,metadata_json FROM realization_anchors
                         WHERE actor_id=? AND consumed_day IS NULL AND source_kind<>'cultivation_process'
                         ORDER BY day,id""",(actor_id,)).fetchall()
    for row in rows:
        meta=_load(row['metadata_json'],{})
        if bool(meta.get('stage_bound',False)) and meta.get('stage_at_creation')!=stage:
            continue
        out.append(row)
    return out


def _consume_external_realization_rows(conn: sqlite3.Connection, rows: list[sqlite3.Row], day: int) -> int:
    """A concrete experience can inform one genuine Stage check, not be rerolled forever."""
    n=0
    for row in rows:
        conn.execute("UPDATE realization_anchors SET consumed_day=? WHERE id=? AND consumed_day IS NULL",(day,int(row['id'])))
        n += int(conn.total_changes > 0)
    return n

def _external_realization_weight(conn: sqlite3.Connection, actor_id: int) -> float:
    return sum(float(r['weight']) for r in _external_realization_rows(conn,actor_id))


def _consume_old_stage_anchors(conn: sqlite3.Connection, actor_id: int, old_stage: str | None, day: int) -> int:
    """Close unresolved Stage-bound insight after a breakthrough.

    The experience remains in history, but an insight from a First-stage problem cannot be banked
    until Third and then spent on Breach. Unbound legacy anchors are left alone for compatibility.
    """
    consumed=0
    rows=conn.execute("""SELECT id,metadata_json FROM realization_anchors
                         WHERE actor_id=? AND consumed_day IS NULL""",(actor_id,)).fetchall()
    for row in rows:
        meta=_load(row['metadata_json'],{})
        if bool(meta.get('stage_bound',False)) and meta.get('stage_at_creation')==old_stage:
            conn.execute("UPDATE realization_anchors SET consumed_day=? WHERE id=?",(day,int(row['id'])))
            consumed+=1
    return consumed



def _post_breakthrough_state(conn: sqlite3.Connection, p: sqlite3.Row, nxt: str, req: dict[str,float], day: int) -> tuple[float,float,int]:
    """Stage-relative starting depth after a breakthrough, preserving exceptional momentum.

    Metrics are stage-relative, so they do step down when the practitioner encounters a new
    problem, but an exceptional body/insight does not get flattened back to the same clone state
    as everyone else. This permits rare very-fast follow-on development without guaranteeing it.
    """
    ev,er=STAGE_ENTRY_FACTORS[nxt]
    va=float(p['vessel_aptitude']) if 'vessel_aptitude' in p.keys() else 1.0
    ra=float(p['realization_aptitude']) if 'realization_aptitude' in p.keys() else 1.0
    rng=_rng(conn,int(p['actor_id']),day,4607)
    surplus=max(0.0,float(p['vessel_adaptation'])-float(req['vessel']))
    vessel_bonus=min(28.0,surplus*0.65 + max(0.0,va-1.0)*13.0 + rng.random()*4.0)
    real_bonus=min(18.0,max(0.0,ra-1.0)*9.0 + rng.random()*3.0)
    nv=min(100.0,ev+vessel_bonus); nr=min(100.0,er+real_bonus)
    tempo=max(0.60,min(2.20,(max(0.35,va)*max(0.35,ra))**0.42))
    review_delay=max(7,min(45,round(30/tempo)))
    return round(nv,4),round(nr,4),int(review_delay)

def _apply_stage_success(conn: sqlite3.Connection, p: sqlite3.Row, day: int, *,
                         event_logger: Callable[...,int] | None, transition_mode: str,
                         trigger_metadata: dict[str,Any] | None = None) -> str:
    actor_id=int(p['actor_id']); stage=p['current_stage']; req=REQUIREMENTS[stage]
    nxt=NEXT_STAGE[stage]
    if not nxt:
        return stage
    nv,nr,review_delay=_post_breakthrough_state(conn,p,nxt,req,day)
    new_capacity=CORE_CAPACITY[nxt]
    next_check=_next_check_day(conn,actor_id,day,nxt,failed=False) if nxt!='Sixth' else day+3650
    conn.execute("""UPDATE cultivation_profiles SET current_stage=?,vessel_adaptation=?,realization_integration=?,
                  core_capacity=MAX(core_capacity,?),current_reserve=MIN(current_reserve,MAX(core_capacity,?)),
                  observed_stage_days=0,plateau_days=0,last_review_day=?,next_review_day=?,next_realization_check_day=?,
                  last_breakthrough_attempt_day=? WHERE actor_id=?""",
                 (nxt,nv,nr,new_capacity,new_capacity,day,day+review_delay,next_check,day,actor_id))
    configure_health_profile(conn,actor_id,longevity_class=LONGEVITY[nxt],
                             metadata={'cultivation_stage_authority':'cultivation_profiles','last_breakthrough_day':day})
    consumed=_consume_old_stage_anchors(conn,actor_id,stage,day)
    meta={'historical_event':nxt=='Sixth','transition_mode':transition_mode,
          'stage_bound_anchors_closed':consumed,'demographic_pressure':None,'population_counts_are_runtime_quota':False}
    meta.update(trigger_metadata or {})
    history_id=_history(conn,actor_id,'breakthrough_success',f"Stage advancement achieved: {stage or 'unstaged'} -> {nxt}.",
             stage_before=stage,stage_after=nxt,metadata=meta,day=day)
    _record_stage_attainment(conn,actor_id,nxt,day=day,chronology_certainty='known',
                             provenance='runtime_breakthrough',source_history_id=history_id,
                             metadata={'stage_before':stage,'inverse_age_stage_rule':True,'transition_mode':transition_mode})
    if event_logger:
        name=conn.execute("SELECT name FROM actors WHERE id=?",(actor_id,)).fetchone()[0]
        sev=5 if nxt=='Sixth' else (4 if nxt=='Fifth' else (3 if nxt=='Breach' else 1))
        event_logger(day=day,event_type='cultivation_breakthrough',title=f'{name} reaches {nxt} Stage',
                     summary=f'{name} achieved a cultivation breakthrough from {stage or "unstaged cultivation"} to {nxt} Stage.',
                     severity=sev,source_actor_id=actor_id,target_actor_ids=(actor_id,),
                     visibility='limited' if nxt not in ('Fifth','Sixth') else 'public',rumorability=0.75,reliability=0.9)
    return nxt


def _attempt_maturation_breakthrough(conn: sqlite3.Connection, p: sqlite3.Row, day: int, *,
                                      event_logger: Callable[...,int] | None) -> tuple[bool,bool]:
    """Resolve a lower-Stage, Vessel-dominant maturation threshold.

    Once the body and ordinary teachable competence are actually ready, this is not a rare
    enlightenment lottery. The causal uncertainty happened in how quickly that readiness was
    produced by Vessel aptitude, environment, teaching, resources, injury and effort.
    """
    actor_id=int(p['actor_id']); stage=p['current_stage']; req=REQUIREMENTS[stage]
    if day < int(p['next_realization_check_day']):
        return False,False
    if not _can_seek_breakthrough(conn,p):
        conn.execute("UPDATE cultivation_profiles SET next_realization_check_day=? WHERE actor_id=?",
                     (_next_check_day(conn,actor_id,day,stage,failed=False),actor_id))
        return False,False
    readiness_v=float(p['vessel_adaptation'])/max(1.0,float(req['vessel']))
    readiness_r=float(p['realization_integration'])/max(1.0,float(req['realization']))
    _history(conn,actor_id,'breakthrough_attempt',
             'Vessel development and ordinary trained competence reached and consolidated the next Stage threshold.',
             stage_before=stage,stage_after=stage,
             metadata={'transition_mode':'vessel_maturation','vessel_readiness_ratio':readiness_v,
                       'ordinary_realization_ratio':readiness_r,'rare_realization_required':False,
                       'success_probability':1.0,'probability_authority':'STRUCTURAL_READINESS_NOT_LOTTERY'},day=day)
    _apply_stage_success(conn,p,day,event_logger=event_logger,transition_mode='vessel_maturation',
                         trigger_metadata={'rare_realization_required':False})
    return True,True


def _attempt_breakthrough(conn: sqlite3.Connection, p: sqlite3.Row, day: int, *, event_logger: Callable[...,int] | None) -> tuple[bool,bool]:
    actor_id=int(p['actor_id']); stage=p['current_stage']; req=REQUIREMENTS[stage]
    if str(req.get('transition_mode','realization_wall'))=='vessel_maturation':
        return _attempt_maturation_breakthrough(conn,p,day,event_logger=event_logger)
    if day < int(p['next_realization_check_day']):
        return False,False
    rnd=_rng(conn,actor_id,day,73)
    aptitude=float(p['realization_aptitude']) if 'realization_aptitude' in p.keys() else 1.0
    vessel_apt=float(p['vessel_aptitude']) if 'vessel_aptitude' in p.keys() else 1.0
    teacher=float(p['teacher_support'])/100.0; resources=float(p['resource_access'])/100.0
    injury=float(p['injury_constraint'])/100.0; effort=float(p['training_effort'])/100.0
    external_rows=_external_realization_rows(conn,actor_id)
    external=sum(float(r['weight']) for r in external_rows)

    cctx=_cultivation_context(conn,actor_id,stage,day=day)
    context=max(0.40,min(1.40,0.78 + 0.12*(teacher-.5) + 0.10*(resources-.5) + 0.08*(effort-.5) - 0.20*injury))
    opp_chance=float(req['opportunity_chance'])*aptitude*context*float(cctx['opportunity_factor'])
    if external>0:
        # A real Stage-bound crisis/duel/teaching insight can materially raise the chance, but
        # still does not guarantee comprehension.
        opp_chance=max(opp_chance,min(0.80,0.18*external*aptitude))
    opp_chance=max(0.0001,min(0.80,opp_chance))

    consumed_external=_consume_external_realization_rows(conn,external_rows,day) if external_rows else 0
    if rnd.random()>=opp_chance:
        conn.execute("UPDATE cultivation_profiles SET next_realization_check_day=?,plateau_days=plateau_days+? WHERE actor_id=?",
                     (_next_check_day(conn,actor_id,day,stage,failed=False),max(30,int(req['check_interval'])//3),actor_id))
        return False,False

    # The opportunity itself supplies the missing insight that routine practice could not grind out.
    before_real=float(p['realization_integration'])
    insight=max(1.0,float(req['realization'])-before_real) + 0.5 + rnd.random()*3.5
    after_real=min(100.0,before_real+insight)
    conn.execute("UPDATE cultivation_profiles SET realization_integration=?,last_realization_day=? WHERE actor_id=?",
                 (after_real,day,actor_id))
    anchor=record_realization_anchor(conn,actor_id,'emergent_realization',source_kind='cultivation_process',weight=1.0,
                                     description='A genuine stage-relevant problem or insight became available through accumulated practice.',
                                     metadata={'stage':stage,'not_guaranteed_breakthrough':True,'insight_gain':insight,'external_anchor_weight':external},day=day)
    _history(conn,actor_id,'realization_opportunity','A stage-relevant Realization opportunity emerged from accumulated conditions.',
             stage_before=stage,stage_after=stage,metadata={'anchor_id':anchor,'opportunity_probability':opp_chance,
             'realization_aptitude':aptitude,'vessel_aptitude':vessel_apt,'elapsed_time_bonus':False,
             'transition_mode':'realization_wall','cultivation_context':cctx,'external_anchors_consumed_for_check':consumed_external},day=day)

    readiness=(float(p['vessel_adaptation'])+after_real)/200.0
    success=float(req['success_base'])*max(0.45,min(1.55,aptitude))*max(0.55,min(1.35,0.88 + 0.22*(readiness-.75) + 0.12*(teacher-.5) + 0.08*(resources-.5) + 0.08*(effort-.5) - 0.22*injury))
    success=max(0.005,min(0.78,success))
    conn.execute("UPDATE cultivation_profiles SET last_breakthrough_attempt_day=? WHERE actor_id=?",(day,actor_id))
    _history(conn,actor_id,'breakthrough_attempt','The cultivator attempted to resolve the available Stage problem.',
             stage_before=stage,stage_after=stage,metadata={'anchor_id':anchor,'success_probability':success,
             'transition_mode':'realization_wall','probability_authority':'CAMPAIGN_CALIBRATION'},day=day)
    conn.execute("UPDATE realization_anchors SET consumed_day=? WHERE id=?",(day,anchor))
    if rnd.random()<success:
        _apply_stage_success(conn,p,day,event_logger=event_logger,transition_mode='realization_wall',
                             trigger_metadata={'anchor_id':anchor,'rare_realization_required':True})
        return True,True

    # Failure is durable history and creates a longer interval before another genuine opportunity.
    conn.execute("UPDATE cultivation_profiles SET plateau_days=plateau_days+90,next_realization_check_day=? WHERE actor_id=?",
                 (_next_check_day(conn,actor_id,day,stage,failed=True),actor_id))
    _history(conn,actor_id,'breakthrough_failure','The available Stage problem was not resolved; training continues from the failed attempt.',
             stage_before=stage,stage_after=stage,metadata={'anchor_id':anchor,'transition_mode':'realization_wall'},day=day)
    rupture=False
    strain=max(0.0,(float(p['training_effort'])-70.0)/30.0) + max(0.0,float(p['injury_constraint'])/100.0)
    rupture_chance=(0.006 if stage in ('Third','Breach') else 0.012) * (1.0+strain)
    if rnd.random()<rupture_chance:
        severity=18.0 + rnd.random()*22.0
        cid=add_condition(conn,actor_id,'rupture','Cultivation Rupture',severity=severity,body_system='Vessel/Channels',
                          capacity_impact=severity*0.65,pain_impact=severity*0.5,recovery_rate_per_30=1.5,
                          specialist_requirement='vein_mender',metadata={'cause':'failed_breakthrough_attempt','stage':stage,'anchor_id':anchor})
        conn.execute("UPDATE cultivation_profiles SET injury_constraint=MIN(100,injury_constraint+?) WHERE actor_id=?",(severity*0.7,actor_id))
        _history(conn,actor_id,'rupture','A failed cultivation attempt caused anatomical Rupture.',stage_before=stage,stage_after=stage,
                 metadata={'health_condition_id':cid,'severity':severity},day=day)
        rupture=True
    return True,rupture

def _resolution_review_floor(conn: sqlite3.Connection, actor_id: int) -> int:
    """Long-horizon resolution changes sampling frequency, never cultivation causality.

    Growth is integrated over elapsed days, so low-resolution actors do not need monthly rows merely
    to remain alive in the simulation.  TRACKED/fast STRATEGIC actors keep near-monthly reviews;
    ordinary STRATEGIC and DORMANT actors are compressed to their persisted simulation cadence.
    A concrete external Realization anchor can still wake the cultivation profile immediately.
    """
    row=conn.execute("SELECT tier,cadence_days FROM simulation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if not row:
        return 30
    tier=str(row['tier'] or '').upper(); cadence=max(1,int(row['cadence_days'] or 30))
    if tier=='DORMANT':
        return max(90,min(240,cadence))
    if tier=='STRATEGIC':
        return max(30,min(120,cadence))
    return max(14,min(60,cadence))


def _next_review_delay(conn: sqlite3.Connection, p: sqlite3.Row, day: int, cctx: dict[str,Any]) -> int:
    """Review rhythm respects actor resolution while preserving elapsed-time integration."""
    va=float(p['vessel_aptitude']) if 'vessel_aptitude' in p.keys() else 1.0
    ra=float(p['realization_aptitude']) if 'realization_aptitude' in p.keys() else 1.0
    tempo=max(0.55,min(2.4,(max(0.35,va)*max(0.35,ra))**0.33 * float(cctx['vessel_growth_factor'])**0.25))
    rng=_rng(conn,int(p['actor_id']),day,4612)
    jitter=0.72+rng.random()*0.62
    plateau=max(0,int(p['plateau_days']))
    plateau_factor=1.0+min(0.65,plateau/3650.0*0.45)
    intrinsic=max(7,min(60,int(round(30.0*jitter*plateau_factor/tempo))))
    return max(intrinsic,_resolution_review_floor(conn,int(p['actor_id'])))


def _review_one(conn: sqlite3.Connection, p: sqlite3.Row, day: int, event_logger) -> tuple[int,int,int,int]:
    actor_id=int(p['actor_id'])
    live=conn.execute("SELECT a.status,lp.life_status FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?",(actor_id,)).fetchone()
    if not live or str(live[0]).lower()!='active' or (live[1] is not None and str(live[1])!='living'):
        conn.execute("UPDATE cultivation_profiles SET active=0,status='ended',last_review_day=?,next_review_day=? WHERE actor_id=?",(day,day+365,actor_id))
        return 1,0,0,0
    if not int(p['active']) or str(p['status'])!='active' or str(p['core_state'])!='Open-Core':
        conn.execute("UPDATE cultivation_profiles SET last_review_day=?,next_review_day=? WHERE actor_id=?",(day,day+90,actor_id))
        return 1,0,0,0

    delta=max(1,day-int(p['last_review_day'])); months=delta/30.0
    effort=_training_effort(conn,actor_id,float(p['training_effort']))
    teacher=_teacher_support(conn,actor_id); injury=_injury_constraint(conn,actor_id)
    cctx=_cultivation_context(conn,actor_id,p['current_stage'],day=day); env=float(cctx['ecology_quality']); milieu=float(cctx['milieu_quality'])
    resource=float(p['resource_access'])
    vb,rb=_growth_rates(p['current_stage'])
    vessel_apt=float(p['vessel_aptitude']) if 'vessel_aptitude' in p.keys() else 1.0
    realization_apt=float(p['realization_aptitude']) if 'realization_aptitude' in p.keys() else 1.0
    sediment=float(p['sediment_burden']) if 'sediment_burden' in p.keys() else 0.0
    # Personal support remains distinct from regional ecology/milieu: a well-supported outer
    # student can outperform a neglected Hearth one, while the Hearth is better on average.
    support=max(0.12,min(1.35,0.48 + effort/250.0 + teacher/500.0 + resource/700.0 - injury/180.0 - sediment/220.0))
    vg=max(0.0,vb*months*support*max(0.35,min(2.35,vessel_apt))*float(cctx['vessel_growth_factor']))
    rg=max(0.0,rb*months*support*max(0.55,min(1.55,0.82+0.18*realization_apt))*float(cctx['realization_growth_factor']))
    vessel=min(100.0,float(p['vessel_adaptation'])+vg)
    stage_req=REQUIREMENTS.get(p['current_stage'])
    practice_cap=float(stage_req['practice_cap']) if stage_req else 100.0
    # Routine practice cannot solve the final Realization problem by accumulation alone. Existing
    # post-opportunity insight is never erased; only ordinary growth is capped.
    real_before=float(p['realization_integration'])
    real=min(100.0,max(real_before,min(practice_cap,real_before+rg)))
    rg=max(0.0,real-real_before)
    plateau=int(p['plateau_days'])
    if vg+rg < 0.65*months or injury>=60:
        plateau += delta
    elif plateau:
        plateau=max(0,plateau-delta//2)
    conn.execute("""UPDATE cultivation_profiles SET vessel_adaptation=?,realization_integration=?,training_effort=?,teacher_support=?,
                  injury_constraint=?,observed_stage_days=observed_stage_days+?,plateau_days=?,last_review_day=?,next_review_day=? WHERE actor_id=?""",
                 (vessel,real,effort,teacher,injury,delta,plateau,day,day+_next_review_delay(conn,p,day,cctx),actor_id))
    _history(conn,actor_id,'practice_review','Cultivation practice advanced according to current body, teaching, resources, environment and injury.',
             stage_before=p['current_stage'],stage_after=p['current_stage'],metadata={'days':delta,'vessel_gain':vg,'realization_gain':rg,'environment_quality':env,'milieu_quality':milieu,'cultivation_context':cctx,'teacher_support':teacher,'resource_access':resource,'training_effort':effort,'injury_constraint':injury,'sediment_burden':sediment,'vessel_aptitude':vessel_apt,'realization_aptitude':realization_apt},day=day)
    updated=conn.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    opportunity=success=rupture=0
    external_now=_external_realization_weight(conn,actor_id)
    if _can_seek_breakthrough(conn,updated) and (day>=int(updated['next_realization_check_day']) or external_now>0):
        # A real external Realization anchor is itself an opportunity trigger and does not wait
        # for the ordinary cadence. Time-at-Stage remains evidence, never a calendar lock.
        if external_now>0 and day<int(updated['next_realization_check_day']):
            conn.execute('UPDATE cultivation_profiles SET next_realization_check_day=? WHERE actor_id=?',(day,actor_id))
            updated=conn.execute('SELECT * FROM cultivation_profiles WHERE actor_id=?',(actor_id,)).fetchone()
        opp,extra=_attempt_breakthrough(conn,updated,day,event_logger=event_logger)
        opportunity=1 if opp else 0
        if opp:
            # Determine success from actual current stage after attempt.
            now=conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()[0]
            success=1 if now!=updated['current_stage'] else 0
            rupture=1 if extra and not success else 0
    return 1,opportunity,success,rupture


def next_cultivation_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row=conn.execute("""SELECT MIN(next_review_day) FROM cultivation_profiles
                        WHERE status IN ('active','paused') AND next_review_day>? AND next_review_day<=?""",(after_day,end_day)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def process_due_cultivation(conn: sqlite3.Connection, day: int, *, event_logger: Callable[...,int] | None = None) -> dict[str,int]:
    rows=conn.execute("SELECT * FROM cultivation_profiles WHERE next_review_day<=? AND status IN ('active','paused') ORDER BY actor_id",(day,)).fetchall()
    reviewed=opportunities=breakthroughs=ruptures=0
    for p in rows:
        a,o,b,r=_review_one(conn,p,day,event_logger)
        reviewed+=a; opportunities+=o; breakthroughs+=b; ruptures+=r
    return {'profiles_reviewed':reviewed,'realization_opportunities':opportunities,'breakthroughs':breakthroughs,'ruptures':ruptures}


def cultivation_summary(conn: sqlite3.Connection) -> dict[str,Any]:
    by_stage={str(r[0] if r[0] is not None else 'Unstaged'):int(r[1]) for r in conn.execute("SELECT current_stage,COUNT(*) FROM cultivation_profiles WHERE core_state='Open-Core' GROUP BY current_stage")}
    return {
        'profiles':int(conn.execute('SELECT COUNT(*) FROM cultivation_profiles').fetchone()[0]),
        'active_cultivators':int(conn.execute("SELECT COUNT(*) FROM cultivation_profiles WHERE active=1 AND status='active' AND core_state='Open-Core'").fetchone()[0]),
        'by_stage':by_stage,
        'realization_anchors':int(conn.execute('SELECT COUNT(*) FROM realization_anchors').fetchone()[0]),
        'breakthroughs':int(conn.execute("SELECT COUNT(*) FROM cultivation_history WHERE history_kind='breakthrough_success'").fetchone()[0]),
        'ruptures':int(conn.execute("SELECT COUNT(*) FROM cultivation_history WHERE history_kind='rupture'").fetchone()[0]),
    }
