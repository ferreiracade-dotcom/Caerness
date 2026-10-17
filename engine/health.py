from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any, Callable

# Tonal longevity anchors (World Bible: "demographic/tonal curves", never guaranteed dates).
# Sixth is fitted to the canon census (all ~40 living Sixths: median age 88, p90 108, oldest 118,
# described as "old" at 87-97, "ancient" at 104-110, "very old" at 118).  Fifth follows the canon text
# ("vigorous" at 80; outlives a Closed-Core spouse "by decades").  Third satisfies "a sixty-year-old
# Third can appear older than an eighty-year-old Fifth".  Lower stages are spaced between.
LONGEVITY_MIDPOINT = {
    'ordinary': 77.5,
    'first': 80.0,
    'temper': 83.0,
    'third': 86.5,
    'breach': 91.5,
    'fifth': 99.5,
    'sixth': 111.0,
}
DECLINE_START = {
    'ordinary': 55.0,
    'first': 57.0,
    'temper': 60.0,
    'third': 63.0,
    'breach': 68.0,
    'fifth': 76.0,
    'sixth': 87.0,
}
DEFAULT_COHORT_MORTALITY = {
    '0_4': 0.045,
    '5_12': 0.008,
    '13_17': 0.005,
    '18_39': 0.0045,
    '40_59': 0.017,
    '60_plus': 0.11,
}
# Share of live births who die in their first year (DEMO-04).  Caerness is premodern: most births have
# a midwife, but infection, fever and childbirth complications still take many infants.
FIRST_YEAR_MORTALITY = 0.10


def childhood_annual_hazard(age: float) -> float:
    """The world's premodern childhood mortality (DEMO-04), shared by every population model."""
    if age < 1:
        return FIRST_YEAR_MORTALITY
    if age < 5:
        return DEFAULT_COHORT_MORTALITY['0_4']
    if age < 13:
        return DEFAULT_COHORT_MORTALITY['5_12']
    return DEFAULT_COHORT_MORTALITY['13_17']

# Named natural mortality (Gompertz-Makeham).  Ordinary adults follow the world's own demography: the
# background tracked-person bands (15-49 0.18%, 50-64 0.9%, 65-74 3%, 75+ 8.5%) with risk doubling
# about every 7.3 years, which puts the ordinary adult median death age at the 77.5 anchor.
_BACKGROUND_ADULT_HAZARD = 0.0018   # everyday illness/accident risk at any adult age
_HAZARD_AT_70 = 0.03                # ordinary age-70 hazard (background 65-74 band)
_GOMPERTZ_SLOPE = 0.095
_MAX_ANNUAL_HAZARD = 0.6


def _ordinary_life_course(age: float, longevity_class: str) -> tuple[float, float]:
    """Map a cultivator's age onto the ordinary life course: (equivalent age, biological years per year).

    "Cultivation extends the prime before it extends old age": the prime (18 → decline start) and
    old age (decline start → longevity midpoint) are stretched separately onto their ordinary spans,
    so a cultivator also ages more slowly through each span.
    """
    if age < 18 or longevity_class == 'ordinary':
        return age, 1.0
    decline, mid = DECLINE_START[longevity_class], LONGEVITY_MIDPOINT[longevity_class]
    o_decline, o_mid = DECLINE_START['ordinary'], LONGEVITY_MIDPOINT['ordinary']
    if age <= decline:
        rate = (o_decline - 18) / (decline - 18)
        return 18 + (age - 18) * rate, rate
    # "Their decline slows": cultivation never makes old age run faster than ordinary ageing.
    rate = min(1.0, (o_mid - o_decline) / (mid - decline))
    return o_decline + (age - decline) * rate, rate


def natural_annual_hazard(age: float, longevity_class: str, *, childhood_multiplier: float = 1.0) -> float:
    """Annual probability of natural death: never zero for anyone living, never a scheduled date.

    Risk is ordinary risk per *biological* year, so each class's median death age lands on its
    longevity anchor and cultivators' preserved health also lowers everyday illness risk.  A child's
    risk is the world average scaled by the family's circumstances (``childhood_circumstance``).
    """
    if age < 15:
        return min(_MAX_ANNUAL_HAZARD, childhood_annual_hazard(age) * childhood_multiplier)
    eff, rate = _ordinary_life_course(age, longevity_class)
    per_bio_year = min(_MAX_ANNUAL_HAZARD, _BACKGROUND_ADULT_HAZARD + _HAZARD_AT_70 * math.exp(_GOMPERTZ_SLOPE * (eff - 70)))
    return min(_MAX_ANNUAL_HAZARD, 1.0 - (1.0 - per_bio_year) ** rate)


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


# "Wealth buys insulation from weather; poverty experiences it directly"; "a wealthy free city can possess
# extraordinary medicine while nearby countryside remains poorly served"; Great Houses and sects keep
# infirmaries and estate physicians.  The DEMO-04 childhood rates are the population *average*; a named
# family's risk is scaled by two things, never by a group label alone:
#   * means   - what the family can actually command (0-100, 50 = ordinary; unknown stays ordinary);
#   * access  - care it can reach: a local care network or an institutional infirmary helps, and
#               remoteness hurts in proportion to poverty (a rich remote family brings the physician in).
# Historical elites lost about a fifth of their children where the general population lost a third, so a
# wealthy house with its own infirmary lands near 0.65.
_SETTLED_LOCATION_WORDS = ("settlement", "district", "city", "town", "port", "palace", "node", "inn", "street", "fortress")
_GREAT_LINEAGE_KINDS = {"royal house", "imperial dynasty", "great house"}
_DEPENDENT_FAMILY_WORDS = ("retainer", "affiliated", "servant", "household guard", "dependent")


def _family_means(conn: sqlite3.Connection, ids: list[int]) -> tuple[float, list[str]]:
    from .opening_family import LINEAGE_KINDS
    marks = ",".join("?" * len(ids))
    means, tags = 50.0, []
    kinds = {str(r[0]) for r in conn.execute(
        f"""SELECT ip.institution_kind FROM institution_memberships im JOIN institution_profiles ip ON ip.actor_id=im.institution_actor_id
            WHERE im.member_actor_id IN ({marks}) AND im.status='active'""", ids)}
    if kinds & LINEAGE_KINDS:
        # Standing inside the house matters: retainer and affiliated families serve it, they do not own it.
        text = " ".join(
            " ".join(str(v or "") for v in (json.loads(r[0] or "{}").get(k) for k in ("role", "public_identity_text")))
            for r in conn.execute(f"SELECT source_payload_json FROM source_identity_map WHERE entity_kind='actor' AND entity_id IN ({marks})", ids)
        ).lower()
        text += " " + " ".join(str(r[0] or "").lower() for r in conn.execute(
            f"SELECT role_text FROM institution_memberships WHERE member_actor_id IN ({marks}) AND status='active'", ids))
        if any(w in text for w in _DEPENDENT_FAMILY_WORDS):
            means = max(means, 60.0); tags.append("dependent_house_family")
        elif kinds & _GREAT_LINEAGE_KINDS:
            means = max(means, 90.0); tags.append("great_house_family")
        else:
            means = max(means, 80.0); tags.append("house_family")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='underworld_personnel'").fetchone():
        r = conn.execute(
            f"""SELECT MAX(MAX(p.earning_power,COALESCE(w.lifestyle_level,0))) FROM underworld_personnel p
                LEFT JOIN underworld_leader_wealth w ON w.actor_id=p.actor_id
                WHERE p.actor_id IN ({marks}) AND p.status='active'""", ids).fetchone()[0]
        if r is not None:
            means = max(means, float(r)) if float(r) >= 50 else min(means, float(r)); tags.append("underworld_earnings")
    try:
        if conn.execute(f"SELECT 1 FROM civilian_enterprises WHERE owner_actor_id IN ({marks}) AND status IN ('active','strained') LIMIT 1", ids).fetchone():
            means = max(means, 70.0); tags.append("enterprise_owner")
    except sqlite3.OperationalError:
        pass
    w = conn.execute(
        f"""SELECT MAX(h.wealth) FROM actor_life_profiles lp JOIN households h ON h.id=lp.current_household_id
            WHERE lp.actor_id IN ({marks}) AND h.wealth>0""", ids).fetchone()[0]
    if w is not None:
        means = max(means, min(100.0, 50.0 + float(w) / 2.0)); tags.append("household_wealth")
    return means, tags


def childhood_circumstance(conn: sqlite3.Connection, *, parent_ids: list[int], location_id: int | None) -> tuple[float, list[str]]:
    """Multiplier on the world's childhood mortality for a family, and the factors behind it."""
    ids = [int(x) for x in parent_ids if x is not None]
    means, tags = _family_means(conn, ids) if ids else (50.0, [])
    mult = 1.0 + (50.0 - means) * 0.007           # means 100 -> 0.65, 50 -> 1.0, 0 -> 1.35
    if ids:
        marks = ",".join("?" * len(ids))
        if conn.execute(f"SELECT 1 FROM institution_memberships WHERE member_actor_id IN ({marks}) AND status='active' LIMIT 1", ids).fetchone():
            mult *= 0.93; tags.append("institutional_infirmary")
    if location_id is not None:
        if conn.execute("SELECT 1 FROM health_care_sites WHERE location_id=? AND status='active' LIMIT 1", (int(location_id),)).fetchone():
            mult *= 0.93; tags.append("care_network")
        else:
            kind = conn.execute("SELECT kind FROM locations WHERE id=?", (int(location_id),)).fetchone()
            if kind and not any(w in str(kind[0]).lower() for w in _SETTLED_LOCATION_WORDS):
                penalty = 0.20 * max(0.0, 1.0 - means / 100.0)
                if penalty > 0.01:
                    mult *= 1.0 + penalty; tags.append("remote_care_distance")
    return round(max(0.5, min(1.5, mult)), 4), tags + [f"means:{round(means)}"]


def _child_circumstance(conn: sqlite3.Connection, actor_id: int) -> tuple[float, list[str]]:
    parents = [int(r[0]) for r in conn.execute(
        "SELECT actor_a_id FROM kinship_links WHERE actor_b_id=? AND kin_kind IN ('parent','adoptive_parent') AND legal_status<>'former'",
        (actor_id,))]
    loc = conn.execute("SELECT COALESCE(home_location_id,current_location_id) FROM actors WHERE id=?", (actor_id,)).fetchone()
    return childhood_circumstance(conn, parent_ids=parents, location_id=int(loc[0]) if loc and loc[0] is not None else None)


def _seed(conn: sqlite3.Connection, salt: int) -> int:
    base = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return (base * 1000003 + salt * 9176) & 0x7FFFFFFF




def _actor_is_living(conn: sqlite3.Connection, actor_id: int) -> bool:
    row = conn.execute("SELECT a.status,l.life_status FROM actors a LEFT JOIN actor_life_profiles l ON l.actor_id=a.id WHERE a.id=?", (actor_id,)).fetchone()
    return bool(row and str(row['status']) != 'deceased' and (row['life_status'] is None or str(row['life_status']) == 'living'))


def _require_living_actor(conn: sqlite3.Connection, actor_id: int, *, role: str = 'actor') -> None:
    if not _actor_is_living(conn, actor_id):
        raise ValueError(f"{role} must be a living actor")


def _competence_score(conn: sqlite3.Connection, actor_id: int, domain_key: str) -> float:
    row = conn.execute(
        """SELECT MAX(ac.score) FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=?""",
        (actor_id, domain_key),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _provider_requirement(condition: sqlite3.Row | None, treatment_kind: str) -> tuple[str | None, float]:
    req = str(condition['specialist_requirement']) if condition is not None else 'none'
    if treatment_kind == 'vein_mending':
        return 'vein_mending', 90.0 if req == 'legendary_vein_mender' else 55.0
    if treatment_kind in ('guided_circulation','elixir_stabilization'):
        return 'vein_mending', 90.0 if req == 'legendary_vein_mender' else 35.0
    if treatment_kind == 'surgery':
        return 'medicine', 55.0
    if treatment_kind == 'ordinary_medicine':
        return 'medicine', 35.0
    if treatment_kind == 'other':
        if req == 'legendary_vein_mender': return 'vein_mending', 90.0
        if req == 'vein_mender': return 'vein_mending', 55.0
        if req == 'physician': return 'medicine', 35.0
    return None, 0.0


def _actor_name(conn: sqlite3.Connection, actor_id: int) -> str:
    row = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()
    return str(row[0]) if row else f"Actor {actor_id}"


def _birth_day(conn: sqlite3.Connection, actor_id: int) -> int | None:
    row = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _age_years(conn: sqlite3.Connection, actor_id: int, day: int | None = None) -> float | None:
    b = _birth_day(conn, actor_id)
    if b is None:
        return None
    return max(0.0, ((day if day is not None else _day(conn)) - b) / 365.0)


def _aging_phase(age: float | None, longevity_class: str) -> str:
    if age is None:
        return 'prime'
    if age < 18:
        return 'growth'
    return 'late_decline' if age >= DECLINE_START[longevity_class] else 'prime'


def ensure_health_profile(conn: sqlite3.Connection, actor_id: int, *, longevity_class: str = 'ordinary',
                          baseline_health: float = 80.0, metadata: dict[str, Any] | None = None) -> None:
    _require_living_actor(conn, actor_id)
    if longevity_class not in LONGEVITY_MIDPOINT:
        raise ValueError('Unknown longevity class')
    day = _day(conn)
    age = _age_years(conn, actor_id, day)
    phase = _aging_phase(age, longevity_class)
    conn.execute(
        """INSERT OR IGNORE INTO actor_health_profiles(actor_id,longevity_class,aging_phase,baseline_health,last_review_day,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?)""",
        (actor_id, longevity_class, phase, max(0,min(100,baseline_health)), day, day+30+(int(actor_id)*37)%150,  # first reviews are spread out, not all on one day
         json.dumps(metadata or {}, sort_keys=True)),
    )


def configure_health_profile(conn: sqlite3.Connection, actor_id: int, *, longevity_class: str | None = None,
                             baseline_health: float | None = None, metadata: dict[str, Any] | None = None) -> None:
    _require_living_actor(conn, actor_id)
    row = conn.execute("SELECT * FROM actor_health_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    if not row:
        ensure_health_profile(conn, actor_id, longevity_class=longevity_class or 'ordinary',
                              baseline_health=80 if baseline_health is None else baseline_health,
                              metadata=metadata)
        return
    updates=[]; vals=[]
    merged=json.loads(row['metadata_json'] or '{}')
    if longevity_class is not None:
        if longevity_class not in LONGEVITY_MIDPOINT:
            raise ValueError('Unknown longevity class')
        old_class=str(row['longevity_class'])
        age=_age_years(conn, actor_id)
        old_phase=str(row['aging_phase'])
        old_penalty=0.0
        if age is not None and old_phase=='late_decline':
            old_penalty=min(55.0,max(0.0,(age-DECLINE_START[old_class])*1.35))
        new_phase=_aging_phase(age, longevity_class)
        # A later breakthrough can slow future aging but cannot erase decline already accrued,
        # whether the new class would place the actor back in prime or merely in a milder decline.
        if old_phase=='late_decline':
            merged['age_penalty_floor']=max(float(merged.get('age_penalty_floor',0.0)), old_penalty)
            merged['mortality_pressure_floor']=max(float(merged.get('mortality_pressure_floor',0.0)), float(row['mortality_pressure']))
            new_phase='late_decline'
        updates.append('longevity_class=?'); vals.append(longevity_class)
        updates.append('aging_phase=?'); vals.append(new_phase)
    if baseline_health is not None:
        updates.append('baseline_health=?'); vals.append(max(0,min(100,float(baseline_health))))
    if metadata is not None:
        merged.update(metadata)
    if longevity_class is not None or metadata is not None:
        updates.append('metadata_json=?'); vals.append(json.dumps(merged, sort_keys=True))
    if updates:
        vals.append(actor_id)
        conn.execute(f"UPDATE actor_health_profiles SET {','.join(updates)} WHERE actor_id=?", vals)
        _recalculate_profile(conn, actor_id, _day(conn))


def add_condition(conn: sqlite3.Connection, actor_id: int, condition_kind: str, label: str, *,
                  severity: float, body_system: str | None = None, capacity_impact: float = 0,
                  pain_impact: float = 0, recovery_rate_per_30: float = 0,
                  progression_rate_per_30: float = 0, fatality_pressure: float = 0,
                  specialist_requirement: str = 'none', next_review_days: int = 14,
                  status: str = 'active', metadata: dict[str, Any] | None = None) -> int:
    _require_living_actor(conn, actor_id)
    ensure_health_profile(conn, actor_id)
    day=_day(conn)
    cur=conn.execute(
        """INSERT INTO health_conditions(actor_id,condition_kind,label,body_system,severity,capacity_impact,pain_impact,
             recovery_rate_per_30,progression_rate_per_30,fatality_pressure,specialist_requirement,status,onset_day,last_review_day,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (actor_id,condition_kind,label,body_system,max(0,min(100,severity)),max(0,min(100,capacity_impact)),
         max(0,min(100,pain_impact)),float(recovery_rate_per_30),float(progression_rate_per_30),
         max(0,min(100,fatality_pressure)),specialist_requirement,status,day,day,day+max(1,int(next_review_days)),
         json.dumps(metadata or {},sort_keys=True)),
    )
    cid=int(cur.lastrowid)
    _health_event(conn, actor_id, cid, 'condition_onset', f"{label} began.")
    _recalculate_profile(conn, actor_id, day)
    return cid



def apply_condition_harm(conn: sqlite3.Connection, condition_id: int, *, severity_delta: float, reason: str, metadata: dict[str, Any] | None = None) -> None:
    row=conn.execute("SELECT * FROM health_conditions WHERE id=?",(condition_id,)).fetchone()
    if not row or str(row['status']) not in ('active','recovering','chronic'):
        raise ValueError('Harm requires an unresolved health condition')
    day=_day(conn); old=float(row['severity']); new=max(0,min(100,old+max(0,float(severity_delta))))
    meta=json.loads(row['metadata_json'] or '{}'); meta.setdefault('external_harm',[]).append({'day':day,'reason':reason,**(metadata or {})})
    conn.execute("UPDATE health_conditions SET severity=?,status='active',last_review_day=?,next_review_day=?,metadata_json=? WHERE id=?",(new,day,day+14,json.dumps(meta,sort_keys=True),condition_id))
    _health_event(conn,int(row['actor_id']),condition_id,'worsened',f"{row['label']} worsened: {reason}.",{'severity':new},day)
    _recalculate_profile(conn,int(row['actor_id']),day)

def add_treatment(conn: sqlite3.Connection, actor_id: int, treatment_kind: str, *, condition_id: int | None = None,
                  provider_actor_id: int | None = None, quality: float = 50, adherence: float = 70,
                  end_day: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    _require_living_actor(conn, actor_id, role='patient')
    condition = None
    if condition_id is not None:
        condition=conn.execute("SELECT * FROM health_conditions WHERE id=?",(condition_id,)).fetchone()
        if not condition or int(condition['actor_id']) != actor_id:
            raise ValueError('Condition does not belong to actor')
        if str(condition['status']) not in ('active','recovering','chronic'):
            raise ValueError('Treatment requires an unresolved condition')
    day=_day(conn)
    if end_day is not None and int(end_day) <= day:
        raise ValueError('Treatment end_day must be after the current story day')
    domain, minimum = _provider_requirement(condition, treatment_kind)
    if domain is not None:
        if provider_actor_id is None:
            meta=metadata or {}; site_id=meta.get('care_site_id')
            structural_ok=False
            if meta.get('structural_provider_pool') and site_id is not None:
                site=conn.execute("SELECT * FROM health_care_sites WHERE id=? AND status IN ('active','strained')",(int(site_id),)).fetchone()
                structural_ok=bool(site and _aggregate_provider_available(site,domain,minimum,used_today=0))
            if not structural_ok:
                raise ValueError(f'{treatment_kind} requires a qualified provider')
        else:
            _require_living_actor(conn, int(provider_actor_id), role='provider')
            score=_competence_score(conn,int(provider_actor_id),domain)
            if score < minimum:
                raise ValueError(f'Provider lacks required {domain} competence ({minimum:g}+ required)')
    elif provider_actor_id is not None:
        _require_living_actor(conn, int(provider_actor_id), role='provider')
    cur=conn.execute(
        """INSERT INTO medical_treatments(actor_id,condition_id,provider_actor_id,treatment_kind,quality,adherence,status,started_day,end_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (actor_id,condition_id,provider_actor_id,treatment_kind,max(0,min(100,quality)),max(0,min(100,adherence)),
         'active',day,end_day,json.dumps(metadata or {},sort_keys=True)),
    )
    _health_event(conn, actor_id, condition_id, 'treatment', f"Treatment started: {treatment_kind}.")
    return int(cur.lastrowid)


def add_disability(conn: sqlite3.Connection, actor_id: int, label: str, *, source_condition_id: int | None = None,
                   mobility_impact: float = 0, stamina_impact: float = 0, capacity_impact: float = 0,
                   adaptation: float = 0, metadata: dict[str, Any] | None = None) -> int:
    _require_living_actor(conn, actor_id)
    if source_condition_id is not None:
        src=conn.execute("SELECT actor_id FROM health_conditions WHERE id=?",(source_condition_id,)).fetchone()
        if not src or int(src[0]) != actor_id:
            raise ValueError('Source condition does not belong to actor')
    day=_day(conn)
    cur=conn.execute(
        """INSERT INTO disabilities(actor_id,source_condition_id,label,mobility_impact,stamina_impact,capacity_impact,adaptation,status,started_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (actor_id,source_condition_id,label,max(0,min(100,mobility_impact)),max(0,min(100,stamina_impact)),
         max(0,min(100,capacity_impact)),max(0,min(100,adaptation)),'active',day,json.dumps(metadata or {},sort_keys=True)),
    )
    did=int(cur.lastrowid)
    _health_event(conn, actor_id, source_condition_id, 'disability', f"Lasting impairment recorded: {label}.")
    _recalculate_profile(conn, actor_id, day)
    return did


def resolve_disability(conn: sqlite3.Connection, disability_id: int, *, reason: str = 'impairment resolved') -> None:
    row=conn.execute("SELECT * FROM disabilities WHERE id=?",(disability_id,)).fetchone()
    if not row:
        raise ValueError('Unknown disability')
    if str(row['status'])=='resolved':
        return
    day=_day(conn)
    conn.execute("UPDATE disabilities SET status='resolved',ended_day=? WHERE id=?",(day,disability_id))
    _health_event(conn,int(row['actor_id']),row['source_condition_id'],'other',f"Disability resolved: {row['label']}.",{'reason':reason},day)
    _recalculate_profile(conn,int(row['actor_id']),day)


def _health_event(conn: sqlite3.Connection, actor_id: int | None, condition_id: int | None, kind: str,
                  summary: str, metadata: dict[str, Any] | None = None, day: int | None = None) -> int:
    cur=conn.execute(
        "INSERT INTO health_events(day,actor_id,condition_id,event_kind,summary,metadata_json) VALUES (?,?,?,?,?,?)",
        (_day(conn) if day is None else day,actor_id,condition_id,kind,summary,json.dumps(metadata or {},sort_keys=True)),
    )
    return int(cur.lastrowid)


def _treatment_modifier(conn: sqlite3.Connection, cond: sqlite3.Row, start_day: int, day: int) -> tuple[float,float]:
    rows=conn.execute(
        "SELECT * FROM medical_treatments WHERE actor_id=? AND started_day<? AND (end_day IS NULL OR end_day>?) AND (condition_id IS NULL OR condition_id=?)",
        (cond['actor_id'],day,start_day,cond['id']),
    ).fetchall()
    recovery_bonus=0.0; progression_reduction=0.0
    kind=str(cond['condition_kind'])
    interval=max(1,day-start_day)
    vein_condition=kind in ('vein_channel','vein_core','rupture')
    ordinary_condition=kind in ('injury','illness','chronic','fatigue','other')
    for t in rows:
        active_start=max(start_day,int(t['started_day']))
        active_end=min(day,int(t['end_day'])) if t['end_day'] is not None else day
        overlap=max(0,active_end-active_start)
        if overlap<=0:
            continue
        time_weight=overlap/interval
        q=(float(t['quality'])/100.0)*(float(t['adherence'])/100.0)*time_weight
        if t['provider_actor_id'] is not None:
            domain='vein_mending' if str(t['treatment_kind']) in ('vein_mending','guided_circulation','elixir_stabilization') else 'medicine'
            skill=_competence_score(conn,int(t['provider_actor_id']),domain)
            q*=0.70+0.60*(skill/100.0)
        tk=str(t['treatment_kind'])
        if vein_condition:
            if tk in ('vein_mending','guided_circulation','elixir_stabilization'):
                recovery_bonus += 0.60*q
                progression_reduction += 0.45*q
            elif tk in ('ordinary_medicine','surgery','rehabilitation','rest'):
                recovery_bonus += 0.15*q
                progression_reduction += 0.10*q
        elif ordinary_condition:
            if tk in ('ordinary_medicine','surgery','rehabilitation','rest'):
                recovery_bonus += 0.60*q
                progression_reduction += 0.45*q
            # Vein-specific treatment does not become a universal cure for ordinary illness/injury.
        else:
            if tk in ('ordinary_medicine','rehabilitation','rest','other'):
                recovery_bonus += 0.35*q
                progression_reduction += 0.25*q
    return min(1.5,recovery_bonus), min(0.9,progression_reduction)


def _resolve_condition(conn: sqlite3.Connection, cond: sqlite3.Row, day: int,
                       event_logger: Callable[..., int] | None) -> tuple[bool,bool]:
    if str(cond['status']) not in ('active','recovering','chronic'):
        return False,False
    elapsed=max(1,min(day-int(cond['last_review_day']),365))
    periods=elapsed/30.0
    rec_bonus, prog_red=_treatment_modifier(conn,cond,int(cond['last_review_day']),day)
    hp=conn.execute("SELECT recovery_capacity FROM actor_health_profiles WHERE actor_id=?",(cond['actor_id'],)).fetchone()
    recovery_factor=max(0.20,min(1.0,float(hp[0])/100.0)) if hp else 1.0
    recovery=float(cond['recovery_rate_per_30'])*(1.0+rec_bonus)*periods*recovery_factor
    progression=float(cond['progression_rate_per_30'])*(1.0-prog_red)*periods
    old=float(cond['severity'])
    new=max(0.0,min(100.0,old + progression - recovery))
    status=str(cond['status'])
    if new <= 0.5 and status != 'chronic':
        status='resolved'; new=0.0
        conn.execute("UPDATE health_conditions SET severity=0,status='resolved',resolved_day=?,last_review_day=?,next_review_day=? WHERE id=?",
                     (day,day,day,cond['id']))
        conn.execute("UPDATE medical_treatments SET status='completed',end_day=COALESCE(end_day,?) WHERE condition_id=? AND status='active'",(day,cond['id']))
        _health_event(conn,int(cond['actor_id']),int(cond['id']),'resolved',f"{cond['label']} resolved.",day=day)
        return True,False
    # Severe injuries can leave lasting impairment; this is bounded and deterministic.
    meta=json.loads(cond['metadata_json'] or '{}')
    if old >= 70 and new < old and meta.get('can_leave_disability') and not meta.get('disability_recorded'):
        impact=max(5.0,min(35.0,old*0.25))
        add_disability(conn,int(cond['actor_id']),f"Aftereffects of {cond['label']}",source_condition_id=int(cond['id']),
                       mobility_impact=impact if meta.get('mobility_related',True) else 0,
                       stamina_impact=impact*0.6,capacity_impact=impact*0.5)
        meta['disability_recorded']=True
    if status!='chronic':
        status='recovering' if new < old else 'active'
    next_day=day+(14 if new>=60 else 30 if new>=25 else 60)
    conn.execute("UPDATE health_conditions SET severity=?,status=?,last_review_day=?,next_review_day=?,metadata_json=? WHERE id=?",
                 (new,status,day,next_day,json.dumps(meta,sort_keys=True),cond['id']))
    if abs(new-old)>=5:
        kind='improved' if new<old else 'worsened'
        _health_event(conn,int(cond['actor_id']),int(cond['id']),kind,
                      f"{cond['label']} {'improved' if new<old else 'worsened'}.",{'severity':round(new,2)},day)
    # Fatality is driven by actual severe pathology, not merely age or a narrative desire for adversity.
    fatal_pressure=max(0.0,float(cond['fatality_pressure']))*(new/100.0)
    if new>=85 and fatal_pressure>0:
        rng=random.Random(_seed(conn,int(cond['id'])*100003+day))
        annual=min(0.98,fatal_pressure/100.0)
        interval_prob=1.0-(1.0-annual)**(max(1,elapsed)/365.0)
        if rng.random()<interval_prob or new>=99.5 and fatal_pressure>=90:
            conn.execute("UPDATE health_conditions SET status='fatal',severity=?,resolved_day=? WHERE id=?",(new,day,cond['id']))
            conn.execute("UPDATE medical_treatments SET status='stopped',end_day=COALESCE(end_day,?) WHERE condition_id=? AND status='active'",(day,cond['id']))
            return True,True
    return True,False


def _recalculate_profile(conn: sqlite3.Connection, actor_id: int, day: int) -> None:
    p=conn.execute("SELECT * FROM actor_health_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if not p:
        return
    age=_age_years(conn,actor_id,day)
    lc=str(p['longevity_class'])
    meta=json.loads(p['metadata_json'] or '{}')
    phase=_aging_phase(age,lc)
    baseline=float(p['baseline_health'])
    age_penalty=0.0
    if age is not None and phase=='late_decline':
        age_penalty=min(55.0,max(0.0,(age-DECLINE_START[lc])*1.35))
    age_penalty=max(age_penalty,float(meta.get('age_penalty_floor',0.0)))
    if age_penalty>0 and phase=='prime':
        phase='late_decline'
    conds=conn.execute("SELECT * FROM health_conditions WHERE actor_id=? AND status IN ('active','recovering','chronic')",(actor_id,)).fetchall()
    disabilities=conn.execute("SELECT * FROM disabilities WHERE actor_id=? AND status IN ('active','adapted')",(actor_id,)).fetchall()
    cap=sum(float(c['capacity_impact'])*(float(c['severity'])/100.0) for c in conds)
    pain=sum(float(c['pain_impact'])*(float(c['severity'])/100.0) for c in conds)
    chronic=sum(float(c['severity']) for c in conds if str(c['status'])=='chronic' or str(c['condition_kind'])=='chronic')*0.35
    dis_cap=sum(float(d['capacity_impact'])*(1.0-float(d['adaptation'])/140.0) for d in disabilities)
    dis_mob=sum(float(d['mobility_impact'])*(1.0-float(d['adaptation'])/130.0) for d in disabilities)
    dis_sta=sum(float(d['stamina_impact'])*(1.0-float(d['adaptation'])/130.0) for d in disabilities)
    functional=max(0,min(100,baseline + 20 - age_penalty - cap - dis_cap))
    recovery=max(5,min(100,100 - age_penalty*1.15 - chronic*0.4))
    resilience=max(5,min(100,100 - age_penalty*1.25 - chronic*0.25))
    stamina=max(0,min(100,100 - age_penalty - dis_sta - cap*0.35))
    mobility=max(0,min(100,100 - age_penalty*0.65 - dis_mob - cap*0.25))
    # Natural mortality pressure rises around the tonal lifespan range but never guarantees a date.
    mortality=0.0
    if age is not None:
        mid=LONGEVITY_MIDPOINT[lc]
        mortality=max(0.0,min(95.0, 2.0 + 93.0/(1.0+math.exp(-(age-mid)/7.5)) - 7.0))
    mortality=max(mortality,float(meta.get('mortality_pressure_floor',0.0)))
    mortality=max(mortality,min(95.0,sum(float(c['fatality_pressure'])*(float(c['severity'])/100.0) for c in conds)))
    # Conditions retain monthly review. Stable late decline is a slower physiological clock:
    # mortality uses elapsed-time hazard, so quarterly review preserves cumulative risk while
    # avoiding a century-scale monthly wakeup for every elderly named character.
    next_review=day+(30 if conds else (90 if phase=='late_decline' else 180))
    conn.execute(
        """UPDATE actor_health_profiles SET aging_phase=?,functional_capacity=?,recovery_capacity=?,injury_resilience=?,
           stamina_capacity=?,mobility=?,pain_burden=?,chronic_burden=?,mortality_pressure=?,last_review_day=?,next_review_day=? WHERE actor_id=?""",
        (phase,functional,recovery,resilience,stamina,mobility,min(100,pain),min(100,chronic),mortality,day,next_review,actor_id),
    )




def refresh_health_profile(conn: sqlite3.Connection, actor_id: int, day: int | None = None) -> None:
    """Public refresh hook for subsystems that directly change condition state."""
    _recalculate_profile(conn, actor_id, _day(conn) if day is None else int(day))

def _process_disability_adaptation(conn: sqlite3.Connection, day: int) -> int:
    rows=conn.execute("""SELECT d.* FROM disabilities d JOIN actors a ON a.id=d.actor_id
                         WHERE a.status<>'deceased' AND d.status IN ('active','adapted') AND d.adaptation<80""").fetchall()
    changed=0; actors=set()
    for d in rows:
        dmeta=json.loads(d['metadata_json'] or '{}')
        anchor=int(dmeta.get('last_adaptation_day',d['started_day']))
        full_years=max(0,(day-anchor)//365)
        if full_years<=0:
            continue
        new_adapt=min(80.0,float(d['adaptation'])+3.0*full_years)
        dmeta['last_adaptation_day']=anchor+365*full_years
        conn.execute("UPDATE disabilities SET adaptation=?,status=?,metadata_json=? WHERE id=?",
                     (new_adapt,'adapted' if new_adapt>=40 else 'active',json.dumps(dmeta,sort_keys=True),d['id']))
        actors.add(int(d['actor_id'])); changed+=1
    for aid in actors:
        _recalculate_profile(conn,aid,day)
    return changed

def _natural_mortality_check(conn: sqlite3.Connection, actor_id: int, day: int, elapsed_days: int) -> bool:
    p=conn.execute("SELECT * FROM actor_health_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if not p:
        return False
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mortality_audit'").fetchone():
        prior=conn.execute("SELECT died FROM mortality_audit WHERE actor_id=? AND day=? AND source_kind='ordinary_health' ORDER BY id DESC LIMIT 1",(actor_id,day)).fetchone()
        if prior:
            return bool(prior[0])
    age=_age_years(conn,actor_id,day)
    pressure=float(p['mortality_pressure'])
    annual=0.0; draw=None; prob=0.0; died=False
    child_mult, child_tags = (1.0, [])
    if age is not None:
        if age < 15:
            child_mult, child_tags = _child_circumstance(conn, actor_id)
        # Natural ageing risk applies to everyone living; condition-driven pressure can only raise it
        # (max, not sum, so the age component inside mortality_pressure is not counted twice).
        annual=natural_annual_hazard(age,str(p['longevity_class']),childhood_multiplier=child_mult)
        if age >= 45 and pressure >= 8:
            annual=max(annual,min(0.45,(pressure/100.0)**3*0.55))
        prob=1.0-(1.0-annual)**(max(1,elapsed_days)/365.0)
        rng=random.Random(_seed(conn,actor_id*1009+day)); draw=rng.random(); died=draw<prob
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mortality_audit'").fetchone():
        conn.execute(
            """INSERT INTO mortality_audit(actor_id,day,age_years,annual_hazard,elapsed_days,draw,died,source_kind,metadata_json)
               VALUES (?,?,?,?,?,?,?,'ordinary_health',?)""",
            (actor_id,day,age,annual,max(0,int(elapsed_days)),draw,1 if died else 0,
             json.dumps({'mortality_pressure':pressure,'period_probability':prob,'hazard_model':'gompertz_makeham_v1','same_rule_for_named_and_resolved_background':True,
                         **({'childhood_multiplier':child_mult,'childhood_factors':child_tags} if child_tags else {})},sort_keys=True)),
        )
    return died

def _ensure_profiles_for_living_actors(conn: sqlite3.Connection) -> int:
    count=0
    rows=conn.execute("""SELECT a.id FROM actors a JOIN actor_life_profiles l ON l.actor_id=a.id
                         WHERE a.actor_type='character' AND a.status<>'deceased' AND l.life_status='living'
                         AND NOT EXISTS(SELECT 1 FROM actor_health_profiles h WHERE h.actor_id=a.id)""").fetchall()
    for r in rows:
        ensure_health_profile(conn,int(r[0])); count+=1
    return count


def set_demographic_mortality(conn: sqlite3.Connection, cohort_id: int, annual_rate: float, *,
                              health_modifier: float = 1.0, metadata: dict[str, Any] | None = None) -> None:
    if not 0 <= annual_rate <= 1:
        raise ValueError('annual_rate must be between 0 and 1')
    day=_day(conn)
    conn.execute(
        """INSERT INTO demographic_health_state(cohort_id,annual_mortality_rate,health_modifier,last_review_day,metadata_json)
           VALUES (?,?,?,?,?) ON CONFLICT(cohort_id) DO UPDATE SET annual_mortality_rate=excluded.annual_mortality_rate,
             health_modifier=excluded.health_modifier,metadata_json=excluded.metadata_json""",
        (cohort_id,annual_rate,max(0,float(health_modifier)),day,json.dumps(metadata or {},sort_keys=True)),
    )


def _ensure_demographic_health(conn: sqlite3.Connection) -> int:
    count=0
    rows=conn.execute("""SELECT d.id,d.age_band,d.last_review_day FROM demographic_cohorts d
                         WHERE NOT EXISTS(SELECT 1 FROM demographic_health_state h WHERE h.cohort_id=d.id)""").fetchall()
    for r in rows:
        conn.execute("INSERT INTO demographic_health_state(cohort_id,annual_mortality_rate,health_modifier,last_review_day) VALUES (?,?,1,?)",
                     (r['id'],DEFAULT_COHORT_MORTALITY[str(r['age_band'])],r['last_review_day']))
        count+=1
    return count


def _process_demographic_mortality(conn: sqlite3.Connection, day: int) -> int:
    _ensure_demographic_health(conn)
    rows=conn.execute("""SELECT h.*,d.population,d.age_band FROM demographic_health_state h
                         JOIN demographic_cohorts d ON d.id=h.cohort_id WHERE h.last_review_day+365<=?""",(day,)).fetchall()
    count=0
    for r in rows:
        years=(day-int(r['last_review_day']))/365.0
        rate=max(0,min(1,float(r['annual_mortality_rate'])*float(r['health_modifier'])))
        survival=(1.0-rate)**years
        new_pop=max(0.0,float(r['population'])*survival)
        conn.execute("UPDATE demographic_cohorts SET population=? WHERE id=?",(new_pop,r['cohort_id']))
        conn.execute("UPDATE demographic_health_state SET last_review_day=? WHERE cohort_id=?",(day,r['cohort_id']))
        count+=1
    return count



# ---------------------------------------------------------------------------
# INTEGRATION-01: treatment access/capacity. Condition progression remains
# independent; these functions merely determine whether/when treatment exists.

def create_care_site(conn: sqlite3.Connection, site_key: str, name: str, *, location_id: int,
                     enterprise_id: int | None = None, quality: float = 50, capacity_per_day: float = 1,
                     beds: int = 0, status: str = 'active', metadata: dict[str, Any] | None = None) -> int:
    cur=conn.execute("""INSERT INTO health_care_sites(site_key,name,enterprise_id,location_id,quality,capacity_per_day,beds,status,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                     (site_key,name,enterprise_id,location_id,max(0,min(100,float(quality))),max(0,float(capacity_per_day)),
                      max(0,int(beds)),status,json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def assign_care_provider(conn: sqlite3.Connection, site_id: int, actor_id: int, *, domain_key: str = 'medicine',
                         capacity_per_day: float = 1, metadata: dict[str, Any] | None = None) -> None:
    _require_living_actor(conn,actor_id,role='provider')
    conn.execute("""INSERT INTO health_provider_assignments(site_id,actor_id,domain_key,capacity_per_day,status,metadata_json)
                        VALUES (?,?,?,?, 'active',?)
                        ON CONFLICT(site_id,actor_id,domain_key) DO UPDATE SET capacity_per_day=excluded.capacity_per_day,status='active',metadata_json=excluded.metadata_json""",
                 (site_id,actor_id,domain_key,max(0,float(capacity_per_day)),json.dumps(metadata or {},sort_keys=True)))


def request_care(conn: sqlite3.Connection, actor_id: int, condition_id: int, *, treatment_kind: str = 'ordinary_medicine',
                 site_id: int | None = None, urgency: float | None = None, metadata: dict[str,Any] | None = None) -> int:
    _require_living_actor(conn,actor_id,role='patient')
    cond=conn.execute("SELECT * FROM health_conditions WHERE id=?",(condition_id,)).fetchone()
    if not cond or int(cond['actor_id'])!=actor_id or str(cond['status']) not in ('active','recovering','chronic'):
        raise ValueError('care request requires an unresolved condition owned by the patient')
    if site_id is not None and not conn.execute("SELECT 1 FROM health_care_sites WHERE id=?",(site_id,)).fetchone():
        raise ValueError('unknown care site')
    existing=conn.execute("SELECT id FROM health_care_requests WHERE actor_id=? AND condition_id=? AND status IN ('waiting','scheduled') ORDER BY id LIMIT 1",(actor_id,condition_id)).fetchone()
    if existing: return int(existing[0])
    day=_day(conn); urg=max(0,min(100,float(cond['severity']) if urgency is None else float(urgency)))
    cur=conn.execute("""INSERT INTO health_care_requests(actor_id,condition_id,site_id,requested_day,urgency,treatment_kind,status,next_review_day,metadata_json)
                        VALUES (?,?,?,?,?,?,'waiting',?,?)""",
                     (actor_id,condition_id,site_id,day,urg,treatment_kind,day+1,json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def _care_location(conn: sqlite3.Connection, actor_id: int) -> int | None:
    r=conn.execute("SELECT COALESCE(current_location_id,home_location_id) FROM actors WHERE id=?",(actor_id,)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _select_site(conn: sqlite3.Connection, request: sqlite3.Row, day: int) -> sqlite3.Row | None:
    if request['site_id'] is not None:
        return conn.execute("SELECT * FROM health_care_sites WHERE id=? AND status IN ('active','strained')",(int(request['site_id']),)).fetchone()
    loc=_care_location(conn,int(request['actor_id']))
    if loc is None: return None
    return conn.execute("""SELECT s.* FROM health_care_sites s WHERE s.location_id=? AND s.status IN ('active','strained')
                           ORDER BY s.quality DESC,s.capacity_per_day DESC,s.id LIMIT 1""",(loc,)).fetchone()


def _select_provider(conn: sqlite3.Connection, site_id: int, condition: sqlite3.Row, treatment_kind: str, day: int) -> int | None:
    domain,minimum=_provider_requirement(condition,treatment_kind)
    if domain is None: return None
    rows=conn.execute("""SELECT p.* FROM health_provider_assignments p JOIN actors a ON a.id=p.actor_id
                         WHERE p.site_id=? AND p.status='active' AND p.domain_key=? AND a.status='active' ORDER BY p.actor_id""",(site_id,domain)).fetchall()
    for r in rows:
        if _competence_score(conn,int(r['actor_id']),domain) < minimum: continue
        used=conn.execute("SELECT COUNT(*) FROM health_care_requests WHERE assigned_provider_actor_id=? AND treated_day=? AND status='treated'",(int(r['actor_id']),day)).fetchone()[0]
        if float(used) < float(r['capacity_per_day']): return int(r['actor_id'])
    return None


def _aggregate_provider_available(site: sqlite3.Row, domain: str | None, minimum: float, *, used_today: int) -> bool:
    """Structural/latent provider pool for ordinary opening-world medicine.

    This is deliberately not a named physician. It represents the shallow population that already
    exists off camera; when a particular provider becomes causally important they can crystallize
    through the normal resolution machinery.
    """
    if domain is None:
        return True
    try:
        meta=json.loads(site['metadata_json'] or '{}')
    except Exception:
        return False
    pools=meta.get('aggregate_provider_domains') or {}
    raw=pools.get(domain)
    if raw is None: return False
    if isinstance(raw,(int,float)):
        competence=float(raw); capacity=float(site['capacity_per_day'])
    else:
        competence=float(raw.get('competence',0)); capacity=float(raw.get('capacity_per_day',site['capacity_per_day']))
    return competence >= float(minimum) and float(used_today) < max(0.0,capacity)


def _auto_request_severe_care(conn: sqlite3.Connection, day: int) -> int:
    """Create care demand only when real local capacity exists; no site means no magical care request/provider."""
    made=0
    rows=conn.execute("""SELECT h.* FROM health_conditions h JOIN actors a ON a.id=h.actor_id
                         WHERE a.status='active' AND h.status IN ('active','recovering','chronic') AND h.severity>=55
                         ORDER BY h.severity DESC,h.id""").fetchall()
    for cond in rows:
        aid=int(cond['actor_id'])
        if conn.execute("SELECT 1 FROM health_care_requests WHERE actor_id=? AND condition_id=? AND status IN ('waiting','scheduled','treated')",(aid,int(cond['id']))).fetchone():
            continue
        loc=_care_location(conn,aid)
        if loc is None or not conn.execute("SELECT 1 FROM health_care_sites WHERE location_id=? AND status IN ('active','strained') LIMIT 1",(loc,)).fetchone():
            continue
        kind=str(cond['condition_kind']); req=str(cond['specialist_requirement'])
        if kind in ('vein_channel','vein_core','rupture') or req in ('vein_mender','legendary_vein_mender'):
            treatment='vein_mending'
        elif kind=='injury' and float(cond['severity'])>=78:
            treatment='surgery'
        else:
            treatment='ordinary_medicine'
        request_care(conn,aid,int(cond['id']),treatment_kind=treatment,urgency=float(cond['severity']),metadata={'auto_requested':True})
        made+=1
    return made


def _process_due_care_requests(conn: sqlite3.Connection, day: int) -> dict[str,int]:
    rows=conn.execute("""SELECT * FROM health_care_requests WHERE status IN ('waiting','scheduled') AND next_review_day<=?
                         ORDER BY urgency DESC,requested_day,id""",(day,)).fetchall()
    treated=0; delayed=0; abandoned=0
    for req in rows:
        cond=conn.execute("SELECT * FROM health_conditions WHERE id=?",(int(req['condition_id']),)).fetchone()
        if not cond or str(cond['status']) not in ('active','recovering','chronic'):
            conn.execute("UPDATE health_care_requests SET status='abandoned',next_review_day=? WHERE id=?",(day,int(req['id']))); abandoned+=1; continue
        site=_select_site(conn,req,day)
        if not site:
            conn.execute("UPDATE health_care_requests SET delay_days=?,next_review_day=? WHERE id=?",(max(0,day-int(req['requested_day'])),day+1,int(req['id']))); delayed+=1; continue
        used=conn.execute("SELECT COUNT(*) FROM health_care_requests WHERE site_id=? AND treated_day=? AND status='treated'",(int(site['id']),day)).fetchone()[0]
        if float(used) >= float(site['capacity_per_day']):
            conn.execute("UPDATE health_care_requests SET site_id=?,delay_days=?,next_review_day=? WHERE id=?",(int(site['id']),max(0,day-int(req['requested_day'])),day+1,int(req['id']))); delayed+=1; continue
        domain,minimum=_provider_requirement(cond,str(req['treatment_kind']))
        provider=_select_provider(conn,int(site['id']),cond,str(req['treatment_kind']),day)
        structural_provider=False
        if domain is not None and provider is None:
            structural_provider=_aggregate_provider_available(site,domain,minimum,used_today=int(used))
            if not structural_provider:
                conn.execute("UPDATE health_care_requests SET site_id=?,delay_days=?,next_review_day=? WHERE id=?",(int(site['id']),max(0,day-int(req['requested_day'])),day+1,int(req['id']))); delayed+=1; continue
        duration=21 if str(req['treatment_kind'])=='surgery' else 14
        tid=add_treatment(conn,int(req['actor_id']),str(req['treatment_kind']),condition_id=int(req['condition_id']),
                          provider_actor_id=provider,quality=float(site['quality']),adherence=80,end_day=day+duration,
                          metadata={'care_request_id':int(req['id']),'care_site_id':int(site['id']),'delay_days':int(req['delay_days']),
                                    'structural_provider_pool':structural_provider,'provider_domain':domain})
        conn.execute("""UPDATE health_care_requests SET site_id=?,status='treated',assigned_provider_actor_id=?,treated_day=?,next_review_day=?
                        WHERE id=?""",(int(site['id']),provider,day,day,int(req['id'])))
        treated+=1
    return {'care_treated':treated,'care_delayed':delayed,'care_abandoned':abandoned}

def next_health_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    r=conn.execute("SELECT MIN(next_review_day) FROM health_care_requests WHERE status IN ('waiting','scheduled') AND next_review_day>? AND next_review_day<=?",(after_day,end_day)).fetchone()[0]
    if r is not None: vals.append(int(r))
    for sql in (
        "SELECT MIN(next_review_day) FROM actor_health_profiles WHERE next_review_day>? AND next_review_day<=?",
        "SELECT MIN(next_review_day) FROM health_conditions WHERE status IN ('active','recovering','chronic') AND next_review_day>? AND next_review_day<=?",
        "SELECT MIN(end_day) FROM medical_treatments WHERE status='active' AND end_day IS NOT NULL AND end_day>? AND end_day<=?",
    ):
        r=conn.execute(sql,(after_day,end_day)).fetchone()[0]
        if r is not None: vals.append(int(r))
    # Newly created life profiles should acquire health state promptly.
    if conn.execute("""SELECT 1 FROM actor_life_profiles l JOIN actors a ON a.id=l.actor_id
                       WHERE l.life_status='living' AND a.status<>'deceased'
                       AND NOT EXISTS(SELECT 1 FROM actor_health_profiles h WHERE h.actor_id=l.actor_id) LIMIT 1""").fetchone():
        d=min(end_day,after_day+1)
        if d>after_day: vals.append(d)
    if conn.execute("SELECT 1 FROM demographic_cohorts d WHERE NOT EXISTS(SELECT 1 FROM demographic_health_state h WHERE h.cohort_id=d.id) LIMIT 1").fetchone():
        d=min(end_day,after_day+1)
        if d>after_day: vals.append(d)
    for r in conn.execute("SELECT last_review_day FROM demographic_health_state").fetchall():
        d=int(r[0])+365
        if after_day<d<=end_day: vals.append(d)
    for r in conn.execute("SELECT started_day,metadata_json,adaptation FROM disabilities WHERE status IN ('active','adapted') AND adaptation<80").fetchall():
        meta=json.loads(r['metadata_json'] or '{}')
        d=int(meta.get('last_adaptation_day',r['started_day']))+365
        if after_day<d<=end_day: vals.append(d)
    return min(vals) if vals else None


def process_due_health(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str,int]:
    from .household_life import mark_actor_deceased
    created=_ensure_profiles_for_living_actors(conn)
    auto_requests=_auto_request_severe_care(conn,day)
    care=_process_due_care_requests(conn,day)
    # Expired treatment must stop before condition resolution at this checkpoint.
    conn.execute("UPDATE medical_treatments SET status='completed' WHERE status='active' AND end_day IS NOT NULL AND end_day<=?",(day,))
    cond_count=0; deaths=0; profile_count=0
    due=conn.execute("""SELECT h.* FROM health_conditions h JOIN actors a ON a.id=h.actor_id
                        WHERE a.status<>'deceased' AND h.status IN ('active','recovering','chronic')
                        AND h.next_review_day<=? ORDER BY h.next_review_day,h.id""",(day,)).fetchall()
    fatal_actors=set()
    for c in due:
        changed,fatal=_resolve_condition(conn,c,day,event_logger)
        if changed: cond_count+=1
        if fatal: fatal_actors.add(int(c['actor_id']))
    profiles=conn.execute("""SELECT h.* FROM actor_health_profiles h JOIN actors a ON a.id=h.actor_id
                             WHERE a.status<>'deceased' AND h.next_review_day<=? ORDER BY h.next_review_day,h.actor_id""",(day,)).fetchall()
    for p in profiles:
        aid=int(p['actor_id'])
        old_phase=str(p['aging_phase'])
        elapsed_days=max(1,day-int(p['last_review_day']))
        _recalculate_profile(conn,aid,day); profile_count+=1
        new=conn.execute("SELECT aging_phase FROM actor_health_profiles WHERE actor_id=?",(aid,)).fetchone()[0]
        if new!=old_phase and new=='late_decline':
            _health_event(conn,aid,None,'decline',f"{_actor_name(conn,aid)} entered late decline.",day=day)
        if aid not in fatal_actors and _natural_mortality_check(conn,aid,day,elapsed_days):
            fatal_actors.add(aid)
    for aid in sorted(fatal_actors):
        actor=conn.execute("SELECT status FROM actors WHERE id=?",(aid,)).fetchone()
        if actor and str(actor[0])!='deceased':
            mark_actor_deceased(conn,aid,reason='health decline or illness',event_logger=event_logger)
            conn.execute("UPDATE medical_treatments SET status='stopped',end_day=COALESCE(end_day,?) WHERE actor_id=? AND status='active'",(day,aid))
            _health_event(conn,aid,None,'death',f"{_actor_name(conn,aid)} died after health decline.",day=day)
            deaths+=1
    adaptations=_process_disability_adaptation(conn,day)
    dem=_process_demographic_mortality(conn,day)
    return {'profiles_created':created,'profiles_reviewed':profile_count,'conditions_reviewed':cond_count,
            'deaths':deaths,'disabilities_adapted':adaptations,'demographic_cohorts':dem,'care_auto_requested':auto_requests,**care}


def health_summary(conn: sqlite3.Connection, actor_id: int | None = None) -> dict[str,Any]:
    if actor_id is None:
        return {
            'health_profiles':int(conn.execute("SELECT COUNT(*) FROM actor_health_profiles").fetchone()[0]),
            'active_conditions':int(conn.execute("SELECT COUNT(*) FROM health_conditions h JOIN actors a ON a.id=h.actor_id WHERE a.status<>'deceased' AND h.status IN ('active','recovering','chronic')").fetchone()[0]),
            'active_disabilities':int(conn.execute("SELECT COUNT(*) FROM disabilities d JOIN actors a ON a.id=d.actor_id WHERE a.status<>'deceased' AND d.status IN ('active','adapted')").fetchone()[0]),
            'active_treatments':int(conn.execute("SELECT COUNT(*) FROM medical_treatments t JOIN actors a ON a.id=t.actor_id WHERE a.status<>'deceased' AND t.status='active'").fetchone()[0]),
            'health_events':int(conn.execute("SELECT COUNT(*) FROM health_events").fetchone()[0]),
        }
    p=conn.execute("SELECT * FROM actor_health_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    return {
        'profile':dict(p) if p else None,
        'conditions':[dict(r) for r in conn.execute("SELECT * FROM health_conditions WHERE actor_id=? ORDER BY status,id",(actor_id,)).fetchall()],
        'disabilities':[dict(r) for r in conn.execute("SELECT * FROM disabilities WHERE actor_id=? ORDER BY status,id",(actor_id,)).fetchall()],
        'treatments':[dict(r) for r in conn.execute("SELECT * FROM medical_treatments WHERE actor_id=? ORDER BY status,id",(actor_id,)).fetchall()],
        'recent_events':[dict(r) for r in conn.execute("SELECT * FROM health_events WHERE actor_id=? ORDER BY day DESC,id DESC LIMIT 20",(actor_id,)).fetchall()],
    }


def build_health_packet(conn: sqlite3.Connection, actor_id: int) -> dict[str,Any]:
    if not conn.execute("SELECT 1 FROM actor_health_profiles WHERE actor_id=?",(actor_id,)).fetchone():
        ensure_health_profile(conn,actor_id)
    p=conn.execute("SELECT * FROM actor_health_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    conds=conn.execute("SELECT label,condition_kind,severity,status,pain_impact FROM health_conditions WHERE actor_id=? AND status IN ('active','recovering','chronic') ORDER BY severity DESC,id",(actor_id,)).fetchall()
    dis=conn.execute("SELECT label,mobility_impact,stamina_impact,capacity_impact,adaptation,status FROM disabilities WHERE actor_id=? AND status IN ('active','adapted') ORDER BY id",(actor_id,)).fetchall()
    return {
        'aging_phase':p['aging_phase'],'longevity_class':p['longevity_class'],
        'functional_capacity':round(float(p['functional_capacity']),1),'recovery_capacity':round(float(p['recovery_capacity']),1),
        'stamina_capacity':round(float(p['stamina_capacity']),1),'mobility':round(float(p['mobility']),1),
        'pain_burden':round(float(p['pain_burden']),1),'conditions':[dict(r) for r in conds],
        'disabilities':[dict(r) for r in dis],
        'rule':'Health changes capacity and trajectory; it does not toggle characters between combat-ready and dead.'
    }
