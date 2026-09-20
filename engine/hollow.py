from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from .household_life import mark_actor_deceased


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _actor(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _institution(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _living(conn: sqlite3.Connection, actor_id: int | None) -> bool:
    if actor_id is None:
        return False
    row = conn.execute(
        """SELECT a.status,lp.life_status FROM actors a
           LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""",
        (actor_id,),
    ).fetchone()
    return bool(row and str(row['status']) == 'active' and (row['life_status'] is None or str(row['life_status']) == 'living'))


def _meta(raw: str | None) -> dict[str, Any]:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _stage_score(conn: sqlite3.Connection, actor_id: int) -> float:
    row = conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    stage = str(row[0]) if row and row[0] else ''
    return {'First': 25, 'Temper': 38, 'Third': 52, 'Breach': 65, 'Fifth': 82, 'Sixth': 98}.get(stage, 35)


def _ensure_hollow_profile(
    conn: sqlite3.Connection,
    actor_id: int,
    *,
    coven_id: int | None,
    formal_affiliation: bool,
    personally_practiced: bool | None,
    basis: str,
) -> None:
    day = _day(conn)
    status = 'formal_coven' if formal_affiliation else 'independent'
    conn.execute(
        """INSERT INTO hollow_practice_profiles(
               actor_id,hollow_status,coven_institution_actor_id,accepts_extraction,practiced_extraction,
               mantle_eligibility,last_review_day,status,metadata_json
           ) VALUES (?,?,?,?,?,'unknown',?,'active',?)
           ON CONFLICT(actor_id) DO UPDATE SET
               hollow_status=excluded.hollow_status,
               coven_institution_actor_id=COALESCE(hollow_practice_profiles.coven_institution_actor_id,excluded.coven_institution_actor_id),
               accepts_extraction=MAX(hollow_practice_profiles.accepts_extraction,excluded.accepts_extraction),
               practiced_extraction=COALESCE(hollow_practice_profiles.practiced_extraction,excluded.practiced_extraction),
               metadata_json=excluded.metadata_json""",
        (
            actor_id, status, coven_id, 1, None if personally_practiced is None else int(personally_practiced), day,
            json.dumps({
                'authority': 'WORLD_BIBLE',
                'basis': basis,
                'important_distinction': 'Formal coven membership is sufficient Hollow affiliation; it is not evidence of personal extraction experience.',
            }, sort_keys=True),
        ),
    )


def activate_hollow_substrate(conn: sqlite3.Connection) -> dict[str, int]:
    """Seed current Hollow affiliation/practice and Grand Coven succession without inventing heirs.

    Deep Court elders are power-brokers, never heirs by virtue of Court office. Only actors separately
    established as Mantle heirs belong in grand_coven_heirs.
    """
    day = _day(conn)
    coven_names = {'Grand Coven', 'Greywater Coven', 'Black Reed Coven', 'Mallow Coven'}
    coven_ids = {
        int(r['id']): str(r['name']) for r in conn.execute(
            "SELECT id,name FROM actors WHERE actor_type='institution' AND name IN (?,?,?,?)",
            tuple(coven_names),
        ).fetchall()
    }

    profiles = 0
    rows = conn.execute(
        """SELECT a.id,a.name,cc.core_json FROM actors a
           JOIN continuity_cores cc ON cc.entity_kind='actor' AND cc.entity_id=a.id AND cc.core_type='general'
           WHERE a.actor_type='character' AND a.status='active' AND json_extract(cc.core_json,'$.current')='Hollow'"""
    ).fetchall()
    for r in rows:
        aid = int(r['id'])
        memberships = conn.execute(
            """SELECT im.institution_actor_id,i.name FROM institution_memberships im
               JOIN actors i ON i.id=im.institution_actor_id
               WHERE im.member_actor_id=? AND im.status='active'""",
            (aid,),
        ).fetchall()
        coven = next((int(m['institution_actor_id']) for m in memberships if int(m['institution_actor_id']) in coven_ids), None)
        formal = coven is not None
        # Independent Hollow status depends on actual practice; coven membership does not prove practice.
        practiced = None if formal else True
        _ensure_hollow_profile(
            conn, aid, coven_id=coven, formal_affiliation=formal, personally_practiced=practiced,
            basis='MASTER FINAL Part 24 Hollow seed population and Hollow affiliation boundary.',
        )
        profiles += 1

    grand = _institution(conn, 'Grand Coven')
    malric = _actor(conn, 'Malric Vell')
    dravik = _actor(conn, 'Dravik')
    bastian = _actor(conn, 'Bastian Crow')
    ronan = _actor(conn, 'Ronan Birch')
    succession = heirs = power_brokers = 0
    if grand is not None and malric is not None and dravik is not None:
        # The male-only rule is specific to the Mantle. These two are explicitly established by canon as living Inheritor / male heir.
        conn.execute("UPDATE hollow_practice_profiles SET mantle_eligibility='eligible' WHERE actor_id IN (?,?)", (malric,dravik))
        existing_state = conn.execute("SELECT 1 FROM grand_coven_succession_state WHERE institution_actor_id=?", (grand,)).fetchone()
        if not existing_state:
            conn.execute(
                """INSERT INTO grand_coven_succession_state(
                       institution_actor_id,inheritor_actor_id,foremost_heir_actor_id,succession_status,mantle_sealed,sealed_day,
                       transfer_available,last_review_day,next_review_day,metadata_json
                   ) VALUES (?,?,?,'open',0,NULL,1,?,?,?)""",
                (
                    grand, malric, dravik, day, day + 90,
                    json.dumps({
                        'authority': 'WORLD_BIBLE',
                        'inheritor_number': 12,
                        'law': 'Law of the Current',
                        'carrion_is_not_succession': True,
                        'living_abdication_forbidden': True,
                        'deep_court_elder_is_not_heir': True,
                        'opening_state': 'Malric is the living Twelfth Inheritor; Dravik is foremost recognized heir and current favored choice, but the Mantle is not Sealed.',
                    }, sort_keys=True),
                ),
            )
            succession = 1
            conn.execute(
                """INSERT INTO grand_coven_heirs(
                       institution_actor_id,actor_id,claim_kind,formal_status,teaching_access,authority_support,
                       martial_credibility,political_support,current_choice,created_day,updated_day,mantle_eligible,metadata_json
                   ) VALUES (?,?, 'recognized_heir','recognized',?,?,?,?,1,?,?,1,?)""",
                (
                    grand, dravik, 95.0, 88.0, _stage_score(conn, dravik), 82.0, day, day,
                    json.dumps({
                        'authority': 'WORLD_BIBLE',
                        'basis': 'Foremost recognized heir, most important direct disciple, openly favored and entrusted with senior authority.',
                        'not_yet_ruler': True,
                        'choice_is_not_sealing': True,
                    }, sort_keys=True),
                ),
            )
            heirs = 1
        # Explicitly separate institutional counterweights from the heir register. These inserts are
        # seed-only: repeated activation must never reset a later political stance.
        if bastian is not None:
            before = conn.execute("SELECT 1 FROM grand_coven_power_brokers WHERE institution_actor_id=? AND actor_id=? AND role_kind='deep_court_elder'", (grand,bastian)).fetchone()
            conn.execute(
                """INSERT OR IGNORE INTO grand_coven_power_brokers(institution_actor_id,actor_id,role_kind,institutional_weight,stance,supported_heir_actor_id,created_day,updated_day,metadata_json)
                   VALUES (?,?, 'deep_court_elder',88,'uncommitted',NULL,?,?,?)""",
                (grand, bastian, day, day, json.dumps({'authority':'WORLD_BIBLE','basis':'Deep Court senior, old teacher and inheritance figure. Deep Court office is not Mantle-heir status.'}, sort_keys=True)),
            )
            power_brokers += int(before is None)
        if ronan is not None:
            before = conn.execute("SELECT 1 FROM grand_coven_power_brokers WHERE institution_actor_id=? AND actor_id=? AND role_kind='senior_power'", (grand,ronan)).fetchone()
            conn.execute(
                """INSERT OR IGNORE INTO grand_coven_power_brokers(institution_actor_id,actor_id,role_kind,institutional_weight,stance,supported_heir_actor_id,created_day,updated_day,metadata_json)
                   VALUES (?,?, 'senior_power',80,'uncommitted',NULL,?,?,?)""",
                (grand, ronan, day, day, json.dumps({'authority':'WORLD_BIBLE','basis':'Expansionist senior Fifth and major Coven power; not established as a Mantle heir or Deep Court elder.'}, sort_keys=True)),
            )
            power_brokers += int(before is None)

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('hollow_activation_version','1')")
    return {
        'hollow_profiles': profiles,
        'grand_coven_succession_states': succession,
        'grand_coven_heirs': heirs,
        'grand_coven_power_brokers': power_brokers,
    }


def register_heir(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    actor_id: int,
    *,
    claim_kind: str,
    formal_status: str = 'potential',
    teaching_access: float = 0,
    authority_support: float = 0,
    political_support: float = 0,
    current_choice: bool = False,
    mantle_eligible: bool = True,
    metadata: dict[str, Any] | None = None,
) -> int:
    if claim_kind not in {'recognized_heir','rival_heir','carrion_riser','other_exalted'}:
        raise ValueError('Deep Court office is not an heir kind; register Court elders as power brokers instead.')
    if formal_status not in {'potential','recognized','pressed','withdrawn','settled','ineligible','deceased'}:
        raise ValueError('Invalid heir formal status')
    # Male-only Mantle eligibility is a canon rule. Reject explicitly female actors; unspecified sex
    # remains unresolved rather than silently treated as male.
    life = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    if mantle_eligible and life and str(life[0]) == 'female':
        raise ValueError('The Grand Coven Mantle is male-only; this actor is not Mantle-eligible.')
    day = _day(conn)
    conn.execute(
        """INSERT INTO grand_coven_heirs(institution_actor_id,actor_id,claim_kind,formal_status,teaching_access,authority_support,
               martial_credibility,political_support,current_choice,created_day,updated_day,mantle_eligible,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(institution_actor_id,actor_id) DO UPDATE SET claim_kind=excluded.claim_kind,formal_status=excluded.formal_status,
               teaching_access=excluded.teaching_access,authority_support=excluded.authority_support,martial_credibility=excluded.martial_credibility,
               political_support=excluded.political_support,current_choice=excluded.current_choice,updated_day=excluded.updated_day,
               mantle_eligible=excluded.mantle_eligible,metadata_json=excluded.metadata_json""",
        (
            institution_actor_id, actor_id, claim_kind, formal_status,
            max(0,min(100,float(teaching_access))), max(0,min(100,float(authority_support))), _stage_score(conn, actor_id),
            max(0,min(100,float(political_support))), int(current_choice), day, day, int(mantle_eligible),
            json.dumps(metadata or {}, sort_keys=True),
        ),
    )
    return int(conn.execute("SELECT id FROM grand_coven_heirs WHERE institution_actor_id=? AND actor_id=?", (institution_actor_id,actor_id)).fetchone()[0])


def set_power_broker_stance(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    actor_id: int,
    *,
    stance: str,
    supported_heir_actor_id: int | None = None,
) -> None:
    if stance not in {'supports','opposes','uncommitted','fractured'}:
        raise ValueError('Invalid succession stance')
    row = conn.execute(
        "SELECT id FROM grand_coven_power_brokers WHERE institution_actor_id=? AND actor_id=? ORDER BY id LIMIT 1",
        (institution_actor_id, actor_id),
    ).fetchone()
    if not row:
        raise ValueError('Actor is not registered as a Grand Coven succession power-broker')
    if supported_heir_actor_id is not None and not conn.execute(
        "SELECT 1 FROM grand_coven_heirs WHERE institution_actor_id=? AND actor_id=? AND formal_status NOT IN ('withdrawn','ineligible','deceased')",
        (institution_actor_id, supported_heir_actor_id),
    ).fetchone():
        raise ValueError('Power-brokers may support only an actual eligible heir/contender')
    conn.execute(
        "UPDATE grand_coven_power_brokers SET stance=?,supported_heir_actor_id=?,updated_day=? WHERE id=?",
        (stance, supported_heir_actor_id, _day(conn), int(row[0])),
    )


def press_heir_claim(conn: sqlite3.Connection, institution_actor_id: int, actor_id: int, *, reason: str = 'claim pressed') -> None:
    row = conn.execute(
        "SELECT * FROM grand_coven_heirs WHERE institution_actor_id=? AND actor_id=?",
        (institution_actor_id,actor_id),
    ).fetchone()
    if not row:
        raise ValueError('Only an actual heir/contender may press a Mantle claim; Deep Court status alone is not a claim.')
    if not int(row['mantle_eligible']) or str(row['formal_status']) in {'withdrawn','settled','ineligible','deceased'}:
        raise ValueError('Heir is not eligible to press a claim')
    day = _day(conn)
    conn.execute("UPDATE grand_coven_heirs SET formal_status='pressed',updated_day=? WHERE id=?", (day,int(row['id'])))
    conn.execute("UPDATE grand_coven_succession_state SET succession_status='contested',last_review_day=? WHERE institution_actor_id=? AND mantle_sealed=0", (day,institution_actor_id))
    conn.execute(
        "INSERT INTO grand_coven_mantle_events(institution_actor_id,day,event_kind,actor_id,metadata_json) VALUES (?,?,'claim_pressed',?,?)",
        (institution_actor_id,day,actor_id,json.dumps({'reason':reason},sort_keys=True)),
    )


def seal_mantle(conn: sqlite3.Connection, institution_actor_id: int, heir_actor_id: int) -> None:
    state = conn.execute("SELECT * FROM grand_coven_succession_state WHERE institution_actor_id=?", (institution_actor_id,)).fetchone()
    if not state or not _living(conn, state['inheritor_actor_id']):
        raise ValueError('A living Inheritor must Seal the Mantle')
    heir = conn.execute(
        "SELECT * FROM grand_coven_heirs WHERE institution_actor_id=? AND actor_id=?",
        (institution_actor_id,heir_actor_id),
    ).fetchone()
    if not heir or not int(heir['mantle_eligible']) or str(heir['formal_status']) in {'withdrawn','ineligible','deceased'}:
        raise ValueError('Mantle can be Sealed only on an eligible heir')
    day = _day(conn)
    conn.execute("UPDATE grand_coven_heirs SET formal_status=CASE WHEN actor_id=? THEN 'settled' ELSE CASE WHEN formal_status='deceased' THEN 'deceased' ELSE 'withdrawn' END END,current_choice=CASE WHEN actor_id=? THEN 1 ELSE 0 END,updated_day=? WHERE institution_actor_id=?", (heir_actor_id,heir_actor_id,day,institution_actor_id))
    conn.execute("UPDATE grand_coven_succession_state SET foremost_heir_actor_id=?,succession_status='sealed',mantle_sealed=1,sealed_day=?,last_review_day=?,next_review_day=? WHERE institution_actor_id=?", (heir_actor_id,day,day,day+90,institution_actor_id))
    conn.execute("INSERT INTO grand_coven_mantle_events(institution_actor_id,day,event_kind,actor_id,other_actor_id,metadata_json) VALUES (?,?,'sealed',?,?,?)", (institution_actor_id,day,heir_actor_id,int(state['inheritor_actor_id']),json.dumps({'lawful_field_closed':True},sort_keys=True)))


def extract_current(
    conn: sqlite3.Connection,
    practitioner_actor_id: int,
    source_actor_id: int,
    requested_current: float,
    *,
    context_kind: str = 'practice',
    metadata: dict[str, Any] | None = None,
) -> int:
    if requested_current <= 0:
        raise ValueError('requested_current must be positive')
    if practitioner_actor_id == source_actor_id:
        raise ValueError('Cannot extract from self')
    prof = conn.execute("SELECT * FROM hollow_practice_profiles WHERE actor_id=? AND status='active'", (practitioner_actor_id,)).fetchone()
    if not prof or not int(prof['accepts_extraction']):
        raise ValueError('Practitioner is not established as accepting the Hollow extraction boundary')
    p = conn.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?", (practitioner_actor_id,)).fetchone()
    s = conn.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?", (source_actor_id,)).fetchone()
    if not p or not s or str(p['core_state'])!='Open-Core' or str(s['core_state'])!='Open-Core':
        raise ValueError('Extraction requires two living Open-Core cultivation profiles')
    if not _living(conn, practitioner_actor_id) or not _living(conn, source_actor_id):
        raise ValueError('Extraction requires living participants')
    before_s = float(s['current_reserve']); before_p = float(p['current_reserve'])
    room = max(0.0, float(p['core_capacity']) - before_p)
    transferred = min(float(requested_current), before_s, room)
    status = 'completed' if transferred + 1e-9 >= float(requested_current) else ('partial' if transferred > 0 else 'failed')
    after_s = before_s - transferred; after_p = before_p + transferred
    day = _day(conn)
    conn.execute("UPDATE cultivation_profiles SET current_reserve=? WHERE actor_id=?", (after_s,source_actor_id))
    conn.execute("UPDATE cultivation_profiles SET current_reserve=? WHERE actor_id=?", (after_p,practitioner_actor_id))
    cur = conn.execute(
        """INSERT INTO hollow_extraction_events(day,practitioner_actor_id,source_actor_id,context_kind,requested_current,transferred_current,
               source_reserve_before,source_reserve_after,recipient_reserve_before,recipient_reserve_after,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (day,practitioner_actor_id,source_actor_id,context_kind,float(requested_current),transferred,before_s,after_s,before_p,after_p,status,json.dumps(metadata or {},sort_keys=True)),
    )
    if transferred > 0:
        conn.execute("UPDATE hollow_practice_profiles SET practiced_extraction=1,last_review_day=? WHERE actor_id=?", (day,practitioner_actor_id))
    # Deliberately no Stage, Vessel or Realization mutation here: extraction transfers current only.
    return int(cur.lastrowid)


def _transfer_mantle_current(conn: sqlite3.Connection, state: sqlite3.Row, heir_actor_id: int, requested: float | None) -> float:
    source = int(state['inheritor_actor_id'])
    s = conn.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?", (source,)).fetchone()
    h = conn.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?", (heir_actor_id,)).fetchone()
    if not s or not h:
        raise ValueError('Passing the Mantle requires cultivation profiles for predecessor and successor')
    available = float(s['current_reserve'])
    room = max(0.0, float(h['core_capacity']) - float(h['current_reserve']))
    amount = min(available, room, available if requested is None else max(0.0,float(requested)))
    conn.execute("UPDATE cultivation_profiles SET current_reserve=current_reserve-? WHERE actor_id=?", (amount,source))
    conn.execute("UPDATE cultivation_profiles SET current_reserve=current_reserve+? WHERE actor_id=?", (amount,heir_actor_id))
    return amount


def pass_mantle(conn: sqlite3.Connection, institution_actor_id: int, *, requested_current: float | None = None) -> float:
    state = conn.execute("SELECT * FROM grand_coven_succession_state WHERE institution_actor_id=?", (institution_actor_id,)).fetchone()
    if not state or not _living(conn,state['inheritor_actor_id']):
        raise ValueError('Passing requires the living Inheritor')
    if not int(state['mantle_sealed']) or state['foremost_heir_actor_id'] is None:
        raise ValueError('Passing requires a settled, Sealed successor')
    if not int(state['transfer_available']):
        raise ValueError("The predecessor\'s Mantle transfer is no longer available")
    heir=int(state['foremost_heir_actor_id'])
    if not _living(conn,heir):
        raise ValueError('Sealed heir is not living')
    amount=_transfer_mantle_current(conn,state,heir,requested_current)
    day=_day(conn)
    conn.execute("UPDATE grand_coven_succession_state SET transfer_available=0,last_review_day=? WHERE institution_actor_id=?",(day,institution_actor_id))
    conn.execute("INSERT INTO grand_coven_mantle_events(institution_actor_id,day,event_kind,actor_id,other_actor_id,current_transferred,metadata_json) VALUES (?,?,'passing',?,?,?,?)",(institution_actor_id,day,int(state['inheritor_actor_id']),heir,amount,json.dumps({'transfers':'current_only','does_not_transfer':['Stage','Vessel','Core capacity','Realization','memory']},sort_keys=True)))
    return amount


def _accede(conn: sqlite3.Connection, institution_actor_id: int, heir_actor_id: int, *, transition_kind: str) -> None:
    day=_day(conn)
    old=conn.execute("SELECT inheritor_actor_id FROM grand_coven_succession_state WHERE institution_actor_id=?",(institution_actor_id,)).fetchone()
    old_id=int(old[0]) if old and old[0] is not None else None
    if old_id is not None and _living(conn,old_id):
        raise ValueError('Living abdication is forbidden; the previous Inheritor must be dead before accession')
    conn.execute("UPDATE grand_coven_succession_state SET inheritor_actor_id=?,foremost_heir_actor_id=NULL,succession_status='open',mantle_sealed=0,sealed_day=NULL,transfer_available=1,last_review_day=?,next_review_day=?,metadata_json=json_set(metadata_json,'$.previous_inheritor_actor_id',?) WHERE institution_actor_id=?",(heir_actor_id,day,day+90,old_id,institution_actor_id))
    conn.execute("UPDATE grand_coven_heirs SET formal_status=CASE WHEN actor_id=? THEN 'settled' ELSE CASE WHEN formal_status='deceased' THEN 'deceased' ELSE 'withdrawn' END END,current_choice=0,updated_day=? WHERE institution_actor_id=?",(heir_actor_id,day,institution_actor_id))
    conn.execute("INSERT INTO grand_coven_mantle_events(institution_actor_id,day,event_kind,actor_id,other_actor_id,metadata_json) VALUES (?,?,'accession',?,?,?)",(institution_actor_id,day,heir_actor_id,old_id,json.dumps({'transition_kind':transition_kind,'new_inheritor_number':'next'},sort_keys=True)))


def process_inheritor_death(conn: sqlite3.Connection, institution_actor_id: int) -> bool:
    state=conn.execute("SELECT * FROM grand_coven_succession_state WHERE institution_actor_id=?",(institution_actor_id,)).fetchone()
    if not state or state['inheritor_actor_id'] is None or _living(conn,int(state['inheritor_actor_id'])):
        return False
    day=_day(conn)
    conn.execute("UPDATE grand_coven_succession_state SET transfer_available=0,last_review_day=? WHERE institution_actor_id=?",(day,institution_actor_id))
    heir=state['foremost_heir_actor_id']
    pressed=int(conn.execute("SELECT COUNT(*) FROM grand_coven_heirs WHERE institution_actor_id=? AND formal_status='pressed' AND mantle_eligible=1",(institution_actor_id,)).fetchone()[0])
    if heir is not None and _living(conn,int(heir)) and (int(state['mantle_sealed']) or pressed==0):
        conn.execute("INSERT INTO grand_coven_mantle_events(institution_actor_id,day,event_kind,actor_id,other_actor_id,metadata_json) VALUES (?,?,'sudden_death_transition',?,?,?)",(institution_actor_id,day,int(heir),int(state['inheritor_actor_id']),json.dumps({'carrion_triggered':False,'passing_lost':True,'contested':False},sort_keys=True)))
        _accede(conn,institution_actor_id,int(heir),transition_kind='sealed_successor' if int(state['mantle_sealed']) else 'known_favored_successor')
        return True
    conn.execute("UPDATE grand_coven_succession_state SET succession_status='vacant',next_review_day=? WHERE institution_actor_id=?",(day+30,institution_actor_id))
    conn.execute("INSERT INTO grand_coven_mantle_events(institution_actor_id,day,event_kind,actor_id,other_actor_id,metadata_json) VALUES (?,?,'sudden_death_transition',NULL,?,?)",(institution_actor_id,day,int(state['inheritor_actor_id']),json.dumps({'carrion_triggered':False,'passing_lost':True,'contested':pressed>0},sort_keys=True)))
    return True


def ascend_inheritor(conn: sqlite3.Connection, institution_actor_id: int, *, requested_current: float | None = None, event_logger: Callable[...,int] | None = None) -> float:
    state=conn.execute("SELECT * FROM grand_coven_succession_state WHERE institution_actor_id=?",(institution_actor_id,)).fetchone()
    if not state or not int(state['mantle_sealed']) or state['foremost_heir_actor_id'] is None:
        raise ValueError('Ascension requires a settled and Sealed successor')
    old=int(state['inheritor_actor_id']); heir=int(state['foremost_heir_actor_id'])
    amount=pass_mantle(conn,institution_actor_id,requested_current=requested_current)
    day=_day(conn)
    conn.execute("INSERT INTO grand_coven_mantle_events(institution_actor_id,day,event_kind,actor_id,other_actor_id,current_transferred,metadata_json) VALUES (?,?,'ascension',?,?,?,?)",(institution_actor_id,day,old,heir,amount,json.dumps({'terminal_rite':True,'carrion_triggered':False},sort_keys=True)))
    mark_actor_deceased(conn,old,reason='Grand Coven Ascension: terminal Passing of the Mantle',event_logger=event_logger)
    _accede(conn,institution_actor_id,heir,transition_kind='ascension')
    return amount


def next_hollow_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row=conn.execute("SELECT MIN(next_review_day) FROM grand_coven_succession_state WHERE next_review_day>? AND next_review_day<=?",(after_day,end_day)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def process_due_hollow(conn: sqlite3.Connection, day: int, *, event_logger: Callable[...,int] | None = None) -> dict[str,int]:
    rows=conn.execute("SELECT * FROM grand_coven_succession_state WHERE next_review_day<=? ORDER BY institution_actor_id",(day,)).fetchall()
    reviews=transitions=0
    for state in rows:
        reviews += 1
        inst=int(state['institution_actor_id'])
        if state['inheritor_actor_id'] is not None and not _living(conn,int(state['inheritor_actor_id'])):
            transitions += int(process_inheritor_death(conn,inst))
        # Mark dead heirs, but never promote Deep Court power-brokers into this table.
        for h in conn.execute("SELECT id,actor_id FROM grand_coven_heirs WHERE institution_actor_id=? AND formal_status NOT IN ('deceased','withdrawn','ineligible')",(inst,)).fetchall():
            if not _living(conn,int(h['actor_id'])):
                conn.execute("UPDATE grand_coven_heirs SET formal_status='deceased',current_choice=0,updated_day=? WHERE id=?",(day,int(h['id'])))
        conn.execute("UPDATE grand_coven_succession_state SET last_review_day=?,next_review_day=? WHERE institution_actor_id=?",(day,day+90,inst))
    return {'succession_reviews':reviews,'succession_transitions':transitions}


def hollow_summary(conn: sqlite3.Connection) -> dict[str,Any]:
    return {
        'hollow_profiles': int(conn.execute("SELECT COUNT(*) FROM hollow_practice_profiles").fetchone()[0]),
        'personal_extractors': int(conn.execute("SELECT COUNT(*) FROM hollow_practice_profiles WHERE practiced_extraction=1").fetchone()[0]),
        'extraction_events': int(conn.execute("SELECT COUNT(*) FROM hollow_extraction_events").fetchone()[0]),
        'succession_states': int(conn.execute("SELECT COUNT(*) FROM grand_coven_succession_state").fetchone()[0]),
        'heirs': int(conn.execute("SELECT COUNT(*) FROM grand_coven_heirs WHERE formal_status NOT IN ('withdrawn','ineligible','deceased')").fetchone()[0]),
        'deep_court_power_brokers': int(conn.execute("SELECT COUNT(*) FROM grand_coven_power_brokers WHERE role_kind='deep_court_elder'").fetchone()[0]),
        'mantle_events': int(conn.execute("SELECT COUNT(*) FROM grand_coven_mantle_events").fetchone()[0]),
    }
