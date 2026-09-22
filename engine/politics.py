from __future__ import annotations

import json
import random
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _actor_is_institution(conn: sqlite3.Connection, actor_id: int) -> bool:
    r = conn.execute("SELECT actor_type FROM actors WHERE id=?", (actor_id,)).fetchone()
    return bool(r and r[0] == "institution")


def _actor_alive(conn: sqlite3.Connection, actor_id: int) -> bool:
    r = conn.execute("SELECT status FROM actors WHERE id=?", (actor_id,)).fetchone()
    return bool(r and str(r[0]).lower() not in {"dead", "deceased", "inactive", "destroyed"})


def _polity(conn: sqlite3.Connection, polity_id: int) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM political_polities WHERE id=?", (polity_id,)).fetchone()
    if not r:
        raise ValueError(f"Unknown polity #{polity_id}")
    return r


def _location_exists(conn: sqlite3.Connection, location_id: int) -> bool:
    return bool(conn.execute("SELECT 1 FROM locations WHERE id=?", (location_id,)).fetchone())


def _history(conn: sqlite3.Connection, transition_type: str, summary: str, *, polity_id: int | None = None,
             other_polity_id: int | None = None, location_id: int | None = None, actor_id: int | None = None,
             day: int | None = None, detail: dict[str, Any] | None = None) -> int:
    day = _day(conn) if day is None else day
    cur = conn.execute(
        """INSERT INTO political_history(day,transition_type,polity_id,other_polity_id,location_id,actor_id,summary,detail_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (day, transition_type, polity_id, other_polity_id, location_id, actor_id, summary,
         json.dumps(detail or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def configure_polity(conn: sqlite3.Connection, institution_actor_id: int, *, polity_kind: str,
                     ruler_actor_id: int | None = None, succession_method: str = "custom",
                     legitimacy: float = 50, stability: float = 50, administrative_capacity: float = 50,
                     military_capacity: float = 50, treasury_pressure: float = 0,
                     review_cadence_days: int = 30, founded_day: int | None = None,
                     metadata: dict[str, Any] | None = None) -> int:
    if not _actor_is_institution(conn, institution_actor_id):
        raise ValueError("Polity must reference an institution actor")
    if ruler_actor_id is not None and not _actor_alive(conn, ruler_actor_id):
        raise ValueError("Ruler must reference a living actor")
    if succession_method not in {"designated","hereditary","elective","appointment","custom","unsettled"}:
        raise ValueError("Invalid succession_method")
    if review_cadence_days < 1:
        raise ValueError("review_cadence_days must be >= 1")
    day = _day(conn)
    next_review = day + review_cadence_days
    conn.execute(
        """INSERT INTO political_polities(institution_actor_id,polity_kind,ruler_actor_id,succession_method,
               legitimacy,stability,administrative_capacity,military_capacity,treasury_pressure,status,founded_day,
               next_review_day,review_cadence_days,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,'active',?,?,?,?)
           ON CONFLICT(institution_actor_id) DO UPDATE SET polity_kind=excluded.polity_kind,
               ruler_actor_id=COALESCE(excluded.ruler_actor_id,political_polities.ruler_actor_id),
               succession_method=excluded.succession_method,legitimacy=excluded.legitimacy,stability=excluded.stability,
               administrative_capacity=excluded.administrative_capacity,military_capacity=excluded.military_capacity,
               treasury_pressure=excluded.treasury_pressure,review_cadence_days=excluded.review_cadence_days,
               metadata_json=excluded.metadata_json""",
        (institution_actor_id, polity_kind, ruler_actor_id, succession_method, legitimacy, stability,
         administrative_capacity, military_capacity, treasury_pressure, founded_day, next_review,
         review_cadence_days, json.dumps(metadata or {}, sort_keys=True)),
    )
    pid = int(conn.execute("SELECT id FROM political_polities WHERE institution_actor_id=?", (institution_actor_id,)).fetchone()[0])
    _history(conn, "polity_configured", f"Political polity configured for institution actor #{institution_actor_id}.", polity_id=pid)
    return pid


def create_dynasty(conn: sqlite3.Connection, name: str, *, home_polity_id: int | None = None,
                   prestige: float = 50, notes: str | None = None) -> int:
    if home_polity_id is not None:
        _polity(conn, home_polity_id)
    cur = conn.execute("INSERT INTO political_dynasties(name,home_polity_id,prestige,founded_day,notes) VALUES (?,?,?,?,?)",
                       (name, home_polity_id, prestige, _day(conn), notes))
    return int(cur.lastrowid)


def add_dynasty_member(conn: sqlite3.Connection, dynasty_id: int, actor_id: int, *, relation_label: str | None = None,
                       seniority: float = 50, status: str = "member") -> None:
    if not conn.execute("SELECT 1 FROM political_dynasties WHERE id=?", (dynasty_id,)).fetchone():
        raise ValueError("Unknown dynasty")
    if not conn.execute("SELECT 1 FROM actors WHERE id=?", (actor_id,)).fetchone():
        raise ValueError("Unknown actor")
    conn.execute(
        """INSERT INTO political_dynasty_members(dynasty_id,actor_id,relation_label,seniority,status,joined_day)
           VALUES (?,?,?,?,?,?) ON CONFLICT(dynasty_id,actor_id) DO UPDATE SET relation_label=excluded.relation_label,
           seniority=excluded.seniority,status=excluded.status""",
        (dynasty_id, actor_id, relation_label, seniority, status, _day(conn)),
    )


def set_ruler(conn: sqlite3.Connection, polity_id: int, actor_id: int, *, dynasty_id: int | None = None,
              reason: str = "succession resolved") -> None:
    _polity(conn, polity_id)
    if not _actor_alive(conn, actor_id):
        raise ValueError("Ruler must be living")
    if dynasty_id is not None and not conn.execute("SELECT 1 FROM political_dynasties WHERE id=?", (dynasty_id,)).fetchone():
        raise ValueError("Unknown dynasty")
    conn.execute("UPDATE political_polities SET ruler_actor_id=?,ruling_dynasty_id=?,status='active' WHERE id=?",
                 (actor_id, dynasty_id, polity_id))
    conn.execute("UPDATE political_succession_claims SET status='defeated',resolved_day=? WHERE polity_id=? AND status='active' AND claimant_actor_id<>?",
                 (_day(conn), polity_id, actor_id))
    conn.execute("UPDATE political_succession_claims SET status='chosen',resolved_day=? WHERE polity_id=? AND claimant_actor_id=? AND status='active'",
                 (_day(conn), polity_id, actor_id))
    _history(conn, "ruler_set", reason, polity_id=polity_id, actor_id=actor_id, detail={"dynasty_id": dynasty_id})
    # Keep the generic institutional authority bridge synchronized with the political owner.
    try:
        iid = int(conn.execute("SELECT institution_actor_id FROM political_polities WHERE id=?", (polity_id,)).fetchone()[0])
        conn.execute("""UPDATE institutional_authority_slots SET authority_kind='named_incumbent',incumbent_actor_id=?,status='active',
                     metadata_json=json_patch(metadata_json,?) WHERE institution_actor_id=? AND authority_key='head'""",
                     (actor_id, json.dumps({'political_succession_owner':True,'resolved_day':_day(conn)}), iid))
        conn.execute("""UPDATE leadership_transition_cases SET status='resolved',resolved_day=?,chosen_actor_id=?
                     WHERE institution_actor_id=? AND authority_key='head' AND status IN ('open','deferred')""",
                     (_day(conn), actor_id, iid))
    except sqlite3.OperationalError:
        pass
    try:
        from .organization_agency import start_regime
        from .organization_lifecycle import record_lifecycle_event
        iid = int(conn.execute("SELECT institution_actor_id FROM political_polities WHERE id=?", (polity_id,)).fetchone()[0])
        start_regime(conn, iid, leader_actor_id=actor_id, regime_kind="political_government",
                     metadata={"polity_id": polity_id, "reason": reason})
        record_lifecycle_event(conn, iid, "regime_change", reason, polity_id=polity_id,
                               detail={"ruler_actor_id": actor_id, "dynasty_id": dynasty_id, "country_continuity_preserved": True})
    except (sqlite3.OperationalError, ImportError):
        pass


def add_succession_claim(conn: sqlite3.Connection, polity_id: int, claimant_actor_id: int, *, dynasty_id: int | None = None,
                         legitimacy: float = 50, support: float = 0, priority: float = 50) -> int:
    _polity(conn, polity_id)
    if not _actor_alive(conn, claimant_actor_id):
        raise ValueError("Claimant must be living")
    cur = conn.execute(
        """INSERT INTO political_succession_claims(polity_id,claimant_actor_id,dynasty_id,legitimacy,support,priority,created_day)
           VALUES (?,?,?,?,?,?,?)""",
        (polity_id, claimant_actor_id, dynasty_id, legitimacy, support, priority, _day(conn)),
    )
    return int(cur.lastrowid)


def resolve_succession(conn: sqlite3.Connection, polity_id: int, *, chosen_actor_id: int | None = None,
                       require_clear_margin: bool = True) -> int | None:
    p = _polity(conn, polity_id)
    claims = conn.execute(
        """SELECT * FROM political_succession_claims WHERE polity_id=? AND status='active' ORDER BY id""", (polity_id,)
    ).fetchall()
    live = [r for r in claims if _actor_alive(conn, int(r["claimant_actor_id"]))]
    for r in claims:
        if not _actor_alive(conn, int(r["claimant_actor_id"])):
            conn.execute("UPDATE political_succession_claims SET status='dead',resolved_day=? WHERE id=?", (_day(conn), int(r["id"])))
    if chosen_actor_id is not None:
        chosen = next((r for r in live if int(r["claimant_actor_id"]) == chosen_actor_id), None)
        if not chosen:
            raise ValueError("Chosen ruler must have an active living succession claim")
    else:
        if not live:
            conn.execute("UPDATE political_polities SET ruler_actor_id=NULL,status='succession_crisis' WHERE id=?", (polity_id,))
            _history(conn, "succession_crisis", "The polity has no viable active succession claimant.", polity_id=polity_id)
            return None
        scored = sorted(live, key=lambda r: (float(r["legitimacy"])*0.45 + float(r["support"])*0.35 + float(r["priority"])*0.20, -int(r["id"])), reverse=True)
        if require_clear_margin and len(scored) > 1:
            a = float(scored[0]["legitimacy"])*0.45 + float(scored[0]["support"])*0.35 + float(scored[0]["priority"])*0.20
            b = float(scored[1]["legitimacy"])*0.45 + float(scored[1]["support"])*0.35 + float(scored[1]["priority"])*0.20
            if a - b < 5:
                conn.execute("UPDATE political_polities SET ruler_actor_id=NULL,status='succession_crisis' WHERE id=?", (polity_id,))
                _history(conn, "succession_crisis", "Competing succession claims remain too close to resolve routinely.", polity_id=polity_id)
                return None
        chosen = scored[0]
    set_ruler(conn, polity_id, int(chosen["claimant_actor_id"]), dynasty_id=chosen["dynasty_id"], reason="Political succession resolved.")
    return int(chosen["claimant_actor_id"])


def set_territorial_control(conn: sqlite3.Connection, polity_id: int, location_id: int, *, control_kind: str = "direct",
                            legitimacy: float = 50, integration: float = 50, notes: str | None = None,
                            reason: str = "territorial control recorded") -> None:
    p = _polity(conn, polity_id)
    if p["status"] == "dissolved":
        raise ValueError("Dissolved polity cannot control territory")
    if not _location_exists(conn, location_id):
        raise ValueError("Unknown location")
    old = conn.execute("SELECT controller_polity_id FROM territorial_control WHERE location_id=?", (location_id,)).fetchone()
    conn.execute(
        """INSERT INTO territorial_control(location_id,controller_polity_id,control_kind,since_day,legitimacy,integration,last_review_day,notes)
           VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(location_id) DO UPDATE SET controller_polity_id=excluded.controller_polity_id,
           control_kind=excluded.control_kind,since_day=excluded.since_day,legitimacy=excluded.legitimacy,integration=excluded.integration,
           last_review_day=excluded.last_review_day,notes=excluded.notes""",
        (location_id, polity_id, control_kind, _day(conn), legitimacy, integration, _day(conn), notes),
    )
    conn.execute("UPDATE locations SET political_owner=(SELECT a.name FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id WHERE p.id=?) WHERE id=?",
                 (polity_id, location_id))
    _history(conn, "territorial_control", reason, polity_id=polity_id,
             other_polity_id=(int(old[0]) if old and int(old[0]) != polity_id else None), location_id=location_id)


def transfer_territory(conn: sqlite3.Connection, location_id: int, to_polity_id: int, *, control_kind: str = "direct",
                       legitimacy: float = 40, integration: float = 10, reason: str = "territorial transfer") -> None:
    set_territorial_control(conn, to_polity_id, location_id, control_kind=control_kind, legitimacy=legitimacy,
                            integration=integration, reason=reason)


def add_territorial_claim(conn: sqlite3.Connection, claimant_polity_id: int, location_id: int, *, claim_kind: str = "historical",
                          legitimacy: float = 50, support: float = 0, pressure: float = 0, rate_per_30_days: float = 0,
                          volatility: float = 0, threshold: float = 75, resolution_policy: str = "dispute",
                          review_cadence_days: int = 30) -> int:
    _polity(conn, claimant_polity_id)
    if not _location_exists(conn, location_id):
        raise ValueError("Unknown location")
    if resolution_policy not in {"none","dispute","recognize","transfer"}:
        raise ValueError("Invalid resolution_policy")
    cur = conn.execute(
        """INSERT INTO territorial_claims(claimant_polity_id,location_id,claim_kind,legitimacy,support,pressure,
           rate_per_30_days,volatility,threshold,resolution_policy,created_day,last_review_day,next_review_day,review_cadence_days)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (claimant_polity_id, location_id, claim_kind, legitimacy, support, pressure, rate_per_30_days, volatility,
         threshold, resolution_policy, _day(conn), _day(conn), _day(conn)+review_cadence_days, review_cadence_days),
    )
    return int(cur.lastrowid)


def set_relation(conn: sqlite3.Connection, polity_a_id: int, polity_b_id: int, *, relation_kind: str = "neutral",
                 stance: float = 0, trust: float = 0, tension: float = 0, notes: str | None = None) -> None:
    _polity(conn, polity_a_id); _polity(conn, polity_b_id)
    if polity_a_id == polity_b_id:
        raise ValueError("A polity cannot have a relation with itself")
    a,b = sorted((polity_a_id, polity_b_id))
    conn.execute(
        """INSERT INTO political_relations(polity_a_id,polity_b_id,relation_kind,stance,trust,tension,updated_day,notes)
           VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(polity_a_id,polity_b_id) DO UPDATE SET relation_kind=excluded.relation_kind,
           stance=excluded.stance,trust=excluded.trust,tension=excluded.tension,updated_day=excluded.updated_day,notes=excluded.notes""",
        (a,b,relation_kind,stance,trust,tension,_day(conn),notes),
    )


def _active_link_reaches(conn: sqlite3.Connection, start: int, target: int) -> bool:
    todo=[start]; seen=set()
    while todo:
        x=todo.pop()
        if x in seen: continue
        seen.add(x)
        if x==target: return True
        rows=conn.execute("SELECT junior_polity_id FROM political_links WHERE senior_polity_id=? AND status='active' AND link_kind IN ('vassalage','protectorate','tributary')",(x,)).fetchall()
        todo.extend(int(r[0]) for r in rows)
    return False


def create_political_link(conn: sqlite3.Connection, senior_polity_id: int, junior_polity_id: int, link_kind: str,
                          *, autonomy: float = 50, terms: dict[str,Any] | None = None) -> int:
    _polity(conn, senior_polity_id); _polity(conn, junior_polity_id)
    if senior_polity_id == junior_polity_id:
        raise ValueError("Polity cannot subordinate itself")
    if link_kind in {"vassalage","protectorate","tributary"} and _active_link_reaches(conn, junior_polity_id, senior_polity_id):
        raise ValueError("Political hierarchy cycle detected")
    cur=conn.execute("INSERT INTO political_links(senior_polity_id,junior_polity_id,link_kind,start_day,autonomy,terms_json) VALUES (?,?,?,?,?,?)",
                     (senior_polity_id,junior_polity_id,link_kind,_day(conn),autonomy,json.dumps(terms or {},sort_keys=True)))
    _history(conn, "political_link", f"{link_kind} relationship created.", polity_id=senior_polity_id, other_polity_id=junior_polity_id)
    return int(cur.lastrowid)


def end_political_link(conn: sqlite3.Connection, link_id: int, *, broken: bool = False) -> None:
    r=conn.execute("SELECT * FROM political_links WHERE id=?",(link_id,)).fetchone()
    if not r: raise ValueError("Unknown political link")
    if r["status"]!='active': raise ValueError("Political link is not active")
    conn.execute("UPDATE political_links SET status=?,end_day=? WHERE id=?", ('broken' if broken else 'ended',_day(conn),link_id))
    _history(conn,"political_link_ended",f"{r['link_kind']} relationship ended.",polity_id=int(r['senior_polity_id']),other_polity_id=int(r['junior_polity_id']))


def add_political_process(conn: sqlite3.Connection, polity_id: int, process_type: str, *, location_id: int | None = None,
                          target_polity_id: int | None = None, rate_per_30_days: float = 0, volatility: float = 0,
                          threshold: float = 10, auto_action: str = "none", cadence_days: int = 30,
                          notes: str | None = None) -> int:
    _polity(conn,polity_id)
    if location_id is not None and not _location_exists(conn,location_id): raise ValueError("Unknown location")
    if target_polity_id is not None: _polity(conn,target_polity_id)
    cur=conn.execute("""INSERT INTO political_processes(polity_id,process_type,location_id,target_polity_id,rate_per_30_days,
                      volatility,threshold,auto_action,last_resolved_day,next_review_day,cadence_days,notes)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (polity_id,process_type,location_id,target_polity_id,rate_per_30_days,volatility,threshold,auto_action,_day(conn),_day(conn)+cadence_days,cadence_days,notes))
    return int(cur.lastrowid)


def dissolve_polity(conn: sqlite3.Connection, polity_id: int, *, successor_polity_id: int | None = None,
                    reason: str = "polity dissolved") -> None:
    p=_polity(conn,polity_id)
    if p["status"]=='dissolved': raise ValueError("Polity already dissolved")
    if successor_polity_id is not None:
        _polity(conn,successor_polity_id)
        if successor_polity_id==polity_id: raise ValueError("Successor must be another polity")
        locs=[int(r[0]) for r in conn.execute("SELECT location_id FROM territorial_control WHERE controller_polity_id=?",(polity_id,)).fetchall()]
        for loc in locs:
            transfer_territory(conn,loc,successor_polity_id,reason=f"Successor transfer after dissolution of polity #{polity_id}")
    elif conn.execute("SELECT 1 FROM territorial_control WHERE controller_polity_id=? LIMIT 1",(polity_id,)).fetchone():
        raise ValueError("Cannot dissolve a territorial polity without transferring its controlled locations")
    conn.execute("UPDATE political_polities SET status='dissolved',dissolved_day=?,ruler_actor_id=NULL WHERE id=?",(_day(conn),polity_id))
    conn.execute("UPDATE political_links SET status='ended',end_day=? WHERE status='active' AND (senior_polity_id=? OR junior_polity_id=?)",(_day(conn),polity_id,polity_id))
    conn.execute("UPDATE territorial_claims SET status='failed' WHERE claimant_polity_id=? AND status IN ('active','pressed','recognized')",(polity_id,))
    _history(conn,"polity_dissolved",reason,polity_id=polity_id,other_polity_id=successor_polity_id)
    try:
        from .organization_lifecycle import mark_polity_dissolved
        mark_polity_dissolved(conn, polity_id, successor_polity_id=successor_polity_id, reason=reason)
    except (sqlite3.OperationalError, ImportError):
        pass


def next_politics_due_day(conn: sqlite3.Connection, after_day: int, through_day: int) -> int | None:
    vals=[]
    for q in [
        ("SELECT MIN(next_review_day) FROM political_polities WHERE status<>'dissolved' AND next_review_day>? AND next_review_day<=?",),
        ("SELECT MIN(next_review_day) FROM territorial_claims WHERE status='active' AND next_review_day>? AND next_review_day<=?",),
        ("SELECT MIN(next_review_day) FROM political_processes WHERE active=1 AND next_review_day>? AND next_review_day<=?",),
    ]:
        r=conn.execute(q[0],(after_day,through_day)).fetchone()
        if r and r[0] is not None: vals.append(int(r[0]))
    return min(vals) if vals else None


def _rng(conn: sqlite3.Connection, salt: int, day: int) -> random.Random:
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed*1000003+salt*9187+day*37)


def _review_polity(conn: sqlite3.Connection, r: sqlite3.Row, day: int, event_logger) -> None:
    pid=int(r['id'])
    ruler=r['ruler_actor_id']
    if ruler is not None and not _actor_alive(conn,int(ruler)):
        conn.execute("UPDATE political_polities SET ruler_actor_id=NULL,status='succession_crisis' WHERE id=?",(pid,))
        _history(conn,"ruler_death_vacancy","The ruler is no longer living; the polity enters a succession vacancy.",polity_id=pid,actor_id=int(ruler),day=day)
        chosen=resolve_succession(conn,pid)
        if chosen is not None:
            event_logger(day=day,event_type='politics:succession',title='Political succession',summary=f'Polity #{pid} resolved a succession off-camera through established claims.',severity=3)
        else:
            event_logger(day=day,event_type='politics:succession_crisis',title='Succession crisis',summary=f'Polity #{pid} has no routine succession resolution.',severity=3)
    conn.execute("UPDATE political_polities SET next_review_day=? WHERE id=?",(day+int(r['review_cadence_days']),pid))


def _review_claim(conn: sqlite3.Connection, r: sqlite3.Row, day: int, event_logger) -> None:
    elapsed=max(0,day-int(r['last_review_day']))
    pressure=float(r['pressure'])
    if elapsed:
        base=float(r['rate_per_30_days'])*elapsed/30.0
        noise=_rng(conn,int(r['id'])*101,day).gauss(0,abs(base)*float(r['volatility'])) if base and float(r['volatility']) else 0
        pressure=max(0,min(100,pressure+base+noise))
    status='active'
    if pressure>=float(r['threshold']):
        status='pressed'; pol=int(r['claimant_polity_id']); loc=int(r['location_id']); policy=str(r['resolution_policy'])
        controller=conn.execute("SELECT controller_polity_id FROM territorial_control WHERE location_id=?",(loc,)).fetchone()
        if policy=='dispute':
            if controller:
                conn.execute("UPDATE territorial_control SET control_kind='disputed' WHERE location_id=?",(loc,))
            event_logger(day=day,event_type='politics:claim_pressed',title='Territorial claim pressed',summary=f'Polity #{pol} has pressed a claim over location #{loc}; control is now politically disputed.',severity=3,location_id=loc)
        elif policy=='recognize':
            status='recognized'
            event_logger(day=day,event_type='politics:claim_recognized',title='Territorial claim recognized',summary=f'A political claim by polity #{pol} over location #{loc} reached recognition threshold.',severity=2,location_id=loc)
        elif policy=='transfer':
            transfer_territory(conn,loc,pol,legitimacy=float(r['legitimacy']),integration=10,reason='Automatic campaign-configured territorial claim resolution')
            status='fulfilled'
            event_logger(day=day,event_type='politics:territorial_transfer',title='Territorial control changed',summary=f'Location #{loc} changed political control through an established campaign claim process.',severity=4,location_id=loc)
    conn.execute("UPDATE territorial_claims SET pressure=?,status=?,last_review_day=?,next_review_day=? WHERE id=?",
                 (pressure,status,day,day+int(r['review_cadence_days']),int(r['id'])))


def _review_process(conn: sqlite3.Connection, r: sqlite3.Row, day: int, event_logger) -> None:
    elapsed=max(0,day-int(r['last_resolved_day']))
    base=float(r['rate_per_30_days'])*elapsed/30.0
    noise=_rng(conn,int(r['id'])*211,day).gauss(0,abs(base)*float(r['volatility'])) if base and float(r['volatility']) else 0
    delta=base+noise; acc=float(r['accumulator'])+abs(delta)
    pid=int(r['polity_id']); ptype=str(r['process_type'])
    if ptype in {'legitimacy','stability','treasury'}:
        col={'legitimacy':'legitimacy','stability':'stability','treasury':'treasury_pressure'}[ptype]
        old=float(conn.execute(f"SELECT {col} FROM political_polities WHERE id=?",(pid,)).fetchone()[0])
        new=max(0,min(100,old+delta))
        conn.execute(f"UPDATE political_polities SET {col}=? WHERE id=?",(new,pid))
    elif ptype=='integration' and r['location_id'] is not None:
        loc=int(r['location_id']); tc=conn.execute("SELECT controller_polity_id,integration FROM territorial_control WHERE location_id=?",(loc,)).fetchone()
        if tc and int(tc['controller_polity_id'])==pid:
            conn.execute("UPDATE territorial_control SET integration=?,last_review_day=? WHERE location_id=?",(max(0,min(100,float(tc['integration'])+delta)),day,loc))
    while acc>=float(r['threshold']):
        acc-=float(r['threshold']); action=str(r['auto_action'])
        if action=='mark_disputed' and r['location_id'] is not None:
            conn.execute("UPDATE territorial_control SET control_kind='disputed' WHERE location_id=? AND controller_polity_id=?",(int(r['location_id']),pid))
        elif action=='open_claim' and r['location_id'] is not None:
            exists=conn.execute("SELECT 1 FROM territorial_claims WHERE claimant_polity_id=? AND location_id=? AND status='active'",(pid,int(r['location_id']))).fetchone()
            if not exists:
                add_territorial_claim(conn,pid,int(r['location_id']),claim_kind='process_generated',pressure=25,rate_per_30_days=max(0,float(r['rate_per_30_days'])),resolution_policy='dispute')
        elif action=='fragment':
            conn.execute("UPDATE political_polities SET status='fragmenting' WHERE id=?",(pid,))
        event_logger(day=day,event_type=f'politics:{ptype}',title='Political structural change',summary=f'An off-camera political process in polity #{pid} became world-significant.',severity=3,location_id=(int(r['location_id']) if r['location_id'] is not None else None))
    conn.execute("UPDATE political_processes SET accumulator=?,last_resolved_day=?,next_review_day=? WHERE id=?",(acc,day,day+int(r['cadence_days']),int(r['id'])))


def process_due_politics(conn: sqlite3.Connection, day: int, *, event_logger) -> dict[str,int]:
    polities=conn.execute("SELECT * FROM political_polities WHERE status<>'dissolved' AND next_review_day<=? ORDER BY next_review_day,id",(day,)).fetchall()
    claims=conn.execute("SELECT * FROM territorial_claims WHERE status='active' AND next_review_day<=? ORDER BY next_review_day,id",(day,)).fetchall()
    processes=conn.execute("SELECT * FROM political_processes WHERE active=1 AND next_review_day<=? ORDER BY next_review_day,id",(day,)).fetchall()
    for r in polities: _review_polity(conn,r,day,event_logger)
    for r in claims: _review_claim(conn,r,day,event_logger)
    for r in processes: _review_process(conn,r,day,event_logger)
    return {"polities":len(polities),"territorial_claims":len(claims),"political_processes":len(processes)}


def politics_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        'polities': int(conn.execute("SELECT COUNT(*) FROM political_polities WHERE status<>'dissolved'").fetchone()[0]),
        'dissolved_polities': int(conn.execute("SELECT COUNT(*) FROM political_polities WHERE status='dissolved'").fetchone()[0]),
        'territories': int(conn.execute("SELECT COUNT(*) FROM territorial_control").fetchone()[0]),
        'active_claims': int(conn.execute("SELECT COUNT(*) FROM territorial_claims WHERE status='active'").fetchone()[0]),
        'active_links': int(conn.execute("SELECT COUNT(*) FROM political_links WHERE status='active'").fetchone()[0]),
        'succession_crises': int(conn.execute("SELECT COUNT(*) FROM political_polities WHERE status='succession_crisis'").fetchone()[0]),
        'history_entries': int(conn.execute("SELECT COUNT(*) FROM political_history").fetchone()[0]),
        'principle': 'Political maps are campaign state: they may expand, contract, split, federate, or disappear without protagonist protection.'
    }
