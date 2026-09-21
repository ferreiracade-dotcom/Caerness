from __future__ import annotations

"""PROFESSION-01 runtime owner.

``professional_profiles`` is a provider/standing projection over real tracked people. It never
creates population. Profiles are derived from already-existing competence, professional
memberships, or a PERSONECO identity that was profiled before demand exposed that person.
"""

import json
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, ensure_ascii=False)


_OCCUPATION_DOMAINS: dict[str, tuple[str, ...]] = {
    "medicine": ("physician",),
    "vein_mending": ("physician",),
    "martial_instruction": ("teacher", "soldier", "labor", "artisan"),
    "teaching": ("teacher",),
    "commerce": ("merchant", "clerk"),
    "craft": ("artisan",),
    "administration": ("clerk", "merchant"),
    "art_culture": ("artist",),
    "transport": ("transport",),
    "hospitality": ("hospitality",),
    "underworld": ("criminal",),
    "command": ("soldier",),
}


def _occupation_domain(occupation: str) -> str | None:
    return {
        "physician": "medicine", "teacher": "teaching", "merchant": "commerce",
        "clerk": "administration", "artisan": "craft", "artist": "art_culture",
        "transport": "transport", "hospitality": "hospitality", "criminal": "underworld",
        "soldier": "command",
    }.get(str(occupation))


def _background_profile_for_actor(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT p.* FROM background_person_profiles p
           JOIN person_resolution_provenance rp
             ON rp.partition_id=p.partition_id AND rp.local_uid=p.local_uid
           WHERE rp.actor_id=? ORDER BY rp.resolved_day DESC,p.partition_id,p.local_uid LIMIT 1""",
        (int(actor_id),),
    ).fetchone()


def _competence_score(conn: sqlite3.Connection, actor_id: int, domain_key: str) -> float | None:
    row = conn.execute(
        """SELECT MAX(ac.score) FROM actor_competence ac
           JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=?""", (int(actor_id), str(domain_key)),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _membership_standing(conn: sqlite3.Connection, actor_id: int, domain_key: str) -> float | None:
    row = conn.execute(
        """SELECT MAX(standing) FROM professional_memberships
           WHERE actor_id=? AND profession_domain=? AND status='active'""", (int(actor_id), str(domain_key)),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _default_capacity(domain_key: str) -> float:
    return {
        "medicine":2.0,"vein_mending":1.0,"martial_instruction":3.0,"teaching":3.0,
        "commerce":4.0,"administration":3.0,"craft":2.0,"art_culture":2.0,
        "transport":4.0,"hospitality":6.0,"underworld":2.0,"command":2.0,
    }.get(str(domain_key),2.0)


def upsert_professional_profile(conn: sqlite3.Connection, actor_id: int, domain_key: str, *,
                                competence: float | None=None, reputation: float | None=None,
                                capacity: float | None=None, source_kind: str="derived_existing_state",
                                source_id: int | None=None, metadata: dict[str,Any] | None=None) -> dict[str,Any]:
    actor=conn.execute("SELECT status FROM actors WHERE id=? AND actor_type='character'",(int(actor_id),)).fetchone()
    if not actor: raise ValueError("professional profile requires a real character actor")
    existing=conn.execute("SELECT * FROM professional_profiles WHERE actor_id=? AND domain_key=?",(int(actor_id),str(domain_key))).fetchone()
    c=_competence_score(conn,actor_id,domain_key) if competence is None else float(competence)
    standing=_membership_standing(conn,actor_id,domain_key)
    if c is None: c=float(existing['competence']) if existing else (standing if standing is not None else 45.0)
    rep=reputation
    if rep is None: rep=float(existing['reputation']) if existing else (standing if standing is not None else max(35.0,min(75.0,30.0+c*.45)))
    cap=float(capacity if capacity is not None else (existing['capacity'] if existing else _default_capacity(domain_key)))
    status='dead' if str(actor[0]).lower() in {'dead','deceased','historical'} else 'active'
    load=float(conn.execute("SELECT COUNT(*) FROM service_requests WHERE provider_actor_id=? AND domain_key=? AND status IN ('matched','open')",(int(actor_id),str(domain_key))).fetchone()[0])
    conn.execute(
        """INSERT INTO professional_profiles(actor_id,domain_key,competence,reputation,capacity,current_load,status,source_kind,source_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(actor_id,domain_key) DO UPDATE SET
           competence=excluded.competence,reputation=excluded.reputation,capacity=excluded.capacity,current_load=excluded.current_load,
           status=excluded.status,source_kind=CASE WHEN professional_profiles.source_kind='canon' THEN professional_profiles.source_kind ELSE excluded.source_kind END,
           source_id=COALESCE(professional_profiles.source_id,excluded.source_id),metadata_json=excluded.metadata_json""",
        (int(actor_id),str(domain_key),max(0,min(100,float(c))),max(0,min(100,float(rep))),max(0,cap),max(0,load),status,str(source_kind),source_id,_j({'population_delta':0,**(metadata or {})}))
    )
    return dict(conn.execute("SELECT * FROM professional_profiles WHERE actor_id=? AND domain_key=?",(int(actor_id),str(domain_key))).fetchone())


def sync_actor_professions(conn: sqlite3.Connection, actor_id: int) -> int:
    actor=conn.execute("SELECT status FROM actors WHERE id=? AND actor_type='character'",(int(actor_id),)).fetchone()
    if not actor: return 0
    domains:set[str]=set()
    for r in conn.execute("SELECT DISTINCT profession_domain FROM professional_memberships WHERE actor_id=? AND status='active'",(int(actor_id),)): domains.add(str(r[0]))
    for r in conn.execute("""SELECT d.domain_key,MAX(ac.score) score FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
                              WHERE ac.actor_id=? GROUP BY d.domain_key HAVING MAX(ac.score)>=45""",(int(actor_id),)): domains.add(str(r['domain_key']))
    bg=_background_profile_for_actor(conn,actor_id)
    if bg:
        dom=_occupation_domain(str(bg['occupation_domain']))
        if dom: domains.add(dom)
        if str(bg['occupation_domain'])=='teacher' and bool(bg['open_core']): domains.add('martial_instruction')
        if str(bg['occupation_domain'])=='physician' and float(bg['medical_aptitude'])>=70: domains.add('vein_mending')
    n=0
    for domain in sorted(domains):
        meta={'projected_from_existing_evidence':True}; comp=None
        if bg:
            if domain in {'medicine','vein_mending'}: comp=max(42.0,float(bg['medical_aptitude']))
            elif domain in {'martial_instruction','teaching'}: comp=max(42.0,float(bg['teaching_aptitude']))
            elif domain in {'commerce','administration','transport','hospitality'}: comp=max(40.0,float(bg['economic_aptitude']))
            elif domain=='command': comp=max(40.0,float(bg['command_aptitude']))
            elif domain=='underworld': comp=max(40.0,float(bg['criminal_familiarity']))
            meta.update({'background_partition_id':int(bg['partition_id']),'background_local_uid':int(bg['local_uid'])})
        upsert_professional_profile(conn,actor_id,domain,competence=comp,source_kind='resolved_background' if bg else 'derived_existing_state',metadata=meta); n+=1
    return n


def activate_profession_runtime(conn: sqlite3.Connection) -> dict[str,int]:
    projected=0
    for r in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' ORDER BY id"): projected += sync_actor_professions(conn,int(r[0]))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('profession01_runtime_version','1')")
    return {'professional_profile_projections':projected,'professional_profiles':int(conn.execute('SELECT COUNT(*) FROM professional_profiles').fetchone()[0])}


def resolve_background_professional(conn: sqlite3.Connection, domain_key: str, *, location_id: int|None=None, reason: str, min_competence: float=45.0) -> int|None:
    from .person_ecology import resolve_background_person
    occupations=_OCCUPATION_DOMAINS.get(str(domain_key),()); kwargs:dict[str,float]={}
    if domain_key in {'medicine','vein_mending'}: kwargs['medical_weight']=1.0
    elif domain_key in {'martial_instruction','teaching'}: kwargs['teaching_weight']=1.0
    elif domain_key in {'commerce','administration','transport','hospitality'}: kwargs['economic_weight']=1.0
    elif domain_key=='command': kwargs['command_weight']=1.0
    elif domain_key=='underworld': kwargs['criminal_weight']=1.0
    aid=resolve_background_person(conn,reason=reason,demand_kind='professional_provider_search',location_id=location_id,occupation_domains=occupations or None,min_age=21,max_age=82,require_open_core=True if domain_key in {'martial_instruction','vein_mending'} else None,subtype=f'resolved {domain_key} professional',**kwargs)
    if aid is None: return None
    sync_actor_professions(conn,aid)
    row=conn.execute("SELECT 1 FROM professional_profiles WHERE actor_id=? AND domain_key=?",(aid,str(domain_key))).fetchone()
    if not row:
        bg=_background_profile_for_actor(conn,aid); competence=min_competence
        if bg:
            if domain_key in {'medicine','vein_mending'}: competence=max(min_competence,float(bg['medical_aptitude']))
            elif domain_key in {'martial_instruction','teaching'}: competence=max(min_competence,float(bg['teaching_aptitude']))
            elif domain_key in {'commerce','administration','transport','hospitality'}: competence=max(min_competence,float(bg['economic_aptitude']))
            elif domain_key=='command': competence=max(min_competence,float(bg['command_aptitude']))
            elif domain_key=='underworld': competence=max(min_competence,float(bg['criminal_familiarity']))
        upsert_professional_profile(conn,aid,domain_key,competence=competence,source_kind='resolved_background',metadata={'resolved_for_real_demand':True,'population_delta':0})
    return aid


def available_professional_providers(conn: sqlite3.Connection, domain_key: str, *, location_id: int|None=None, min_competence: float=0) -> list[sqlite3.Row]:
    where=["p.domain_key=?","p.status='active'","p.competence>=?","p.current_load<p.capacity","a.status='active'"]; args:list[Any]=[str(domain_key),float(min_competence)]
    if location_id is not None: where.append('a.current_location_id=?'); args.append(int(location_id))
    return conn.execute(f"SELECT p.*,a.current_location_id,a.name FROM professional_profiles p JOIN actors a ON a.id=p.actor_id WHERE {' AND '.join(where)} ORDER BY p.competence DESC,p.reputation DESC,p.actor_id",args).fetchall()


def next_profession_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int|None:
    if not conn.execute('SELECT 1 FROM professional_profiles LIMIT 1').fetchone(): return None
    d=((int(after_day)//30)+1)*30
    return d if d<=int(end_day) else None


def process_due_profession(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str,int]:
    reviewed=dead=0
    for row in conn.execute('SELECT actor_id,domain_key FROM professional_profiles ORDER BY actor_id,domain_key'):
        p=upsert_professional_profile(conn,int(row['actor_id']),str(row['domain_key'])); reviewed+=1; dead += int(str(p['status'])=='dead')
    return {'professional_profiles_reviewed':reviewed,'professional_profiles_dead':dead}
