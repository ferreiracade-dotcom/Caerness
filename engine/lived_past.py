"""Work history, knowledge and memories for the people of the opening, drawn from what exists in the world.

A person at the opening is not new to it: they have worked for years, know their district, the people near them and the quarrels of the
body they belong to, and remember the things that happened to them (a marriage, an opening day, an incident, a favour owed). This reads the
rows the earlier opening steps made (seats, businesses, households, incidents, obligations, tension) and writes, tiered by what a person
holds, a career row, some facts and some memories. The tiers, depths and every sentence template are the package's (`neighbourhood.lived_past`);
no world words here. Insert-only, deterministic, and cheap: the rows are written in a few batched statements.
"""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import date, timedelta

from . import design
from .world_package import package_for


def _rng(conn: sqlite3.Connection, key: str) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:lived_past:{key}")


def _first_sentence(text: str, limit: int = 220) -> str:
    t = " ".join(str(text or "").split())
    cut = t.find(". ")
    t = t if cut < 0 else t[:cut + 1]
    return t[:limit].rstrip()


def _depth(rng: random.Random, span) -> int:
    lo, hi = int(span[0]), int(span[1])
    return rng.randint(lo, hi)


def build(conn: sqlite3.Connection) -> dict[str, int]:
    pkg = package_for(conn)
    path = pkg.data.get("neighbourhood")
    if path is None:
        return {}
    cfg = (json.loads(path.read_text(encoding="utf-8")) or {}).get("lived_past")
    if not cfg:
        return {}
    T = cfg["templates"]
    day0 = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    start = date.fromisoformat(str(pkg.calendar["start"]))

    def year_of(d: int) -> int:
        return (start + timedelta(days=int(d) - day0)).year

    names = {int(r[0]): str(r[1]) for r in conn.execute("SELECT id,name FROM actors WHERE actor_type IN ('character','institution')")}
    loc_name = {int(r[0]): (str(r[1]), str(r[2] or "")) for r in conn.execute("SELECT id,name,notes FROM locations")}
    people = conn.execute(
        """SELECT a.id,COALESCE(a.home_location_id,a.current_location_id) loc,lp.birth_day,lp.demographic_sex sex,p.occupation_domain dom
           FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id LEFT JOIN background_person_profiles p ON p.actor_id=a.id
           WHERE a.actor_type='character' AND a.status='active' AND lp.birth_day IS NOT NULL ORDER BY a.id""").fetchall()
    seat = {int(r["actor_id"]): r for r in conn.execute(
        "SELECT actor_id,org_actor_id,role_key,superior_actor_id FROM org_seats WHERE status='active' ORDER BY id")}
    owner_of: dict[int, list[sqlite3.Row]] = {}
    staff_of: dict[int, list[sqlite3.Row]] = {}
    for r in conn.execute("""SELECT e.id,e.name,e.owner_actor_id,e.location_id,es.founded_day FROM civilian_enterprises e
                             LEFT JOIN enterprise_ecology_state es ON es.enterprise_id=e.id WHERE e.status IN ('active','strained')"""):
        owner_of.setdefault(int(r["owner_actor_id"]), []).append(r)
    for r in conn.execute("""SELECT s.actor_id,e.name,e.owner_actor_id FROM enterprise_staff s JOIN civilian_enterprises e ON e.id=s.enterprise_id
                             WHERE s.status='active' AND s.role<>'owner'"""):
        staff_of.setdefault(int(r["actor_id"]), []).append(r)
    biz_by_loc: dict[int, list[sqlite3.Row]] = {}
    for rows in owner_of.values():
        for r in rows:
            biz_by_loc.setdefault(int(r["location_id"]), []).append(r)
    spouse = {}
    marry_day = {}
    for r in conn.execute("SELECT actor_a_id,actor_b_id,started_day FROM household_unions WHERE status='active'"):
        spouse[int(r[0])], spouse[int(r[1])] = int(r[1]), int(r[0])
        marry_day[int(r[0])] = marry_day[int(r[1])] = int(r[2])
    kids = {int(r[0]): int(r[1]) for r in conn.execute(
        """SELECT json_extract(constraints_json,'$.parent_actor_id'),SUM(count_estimate) FROM latent_entities
           WHERE latent_kind='kin_group' AND archetype='children' GROUP BY 1""") if r[0] is not None}
    quarrels: dict[int, list[tuple[int, str]]] = {}
    for r in conn.execute("""SELECT t.from_org,t.to_org,(SELECT note FROM org_tension_acts x WHERE x.from_org=t.from_org AND x.to_org=t.to_org
                                                         ORDER BY x.id LIMIT 1) note FROM org_tension t WHERE t.level>0 ORDER BY t.from_org,t.to_org"""):
        quarrels.setdefault(int(r[0]), []).append((int(r[1]), str(r[2] or "")))
    ground: dict[int, str] = {}
    for r in conn.execute("""SELECT s.org_actor_id,GROUP_CONCAT(DISTINCT l.name) FROM org_seats s JOIN org_units u ON u.id=s.unit_id
                             JOIN locations l ON l.id=u.ground_location_id GROUP BY s.org_actor_id"""):
        ground[int(r[0])] = ", ".join(sorted(set(str(r[1]).split(","))))
    incidents: dict[int, list[tuple[str, int, int, int]]] = {}
    for r in conn.execute("SELECT id,day,kind,offender_actor_id,victim_actor_id,metadata_json FROM org_incidents ORDER BY id"):
        meta = json.loads(r["metadata_json"] or "{}")
        if meta.get("canon"):
            continue
        incidents.setdefault(int(r["offender_actor_id"]), []).append(("offender", int(r["id"]), int(r["day"]), int(r["victim_actor_id"] or 0)))
        if r["victim_actor_id"]:
            incidents.setdefault(int(r["victim_actor_id"]), []).append(("victim", int(r["id"]), int(r["day"]), int(r["offender_actor_id"])))
    canon_by_org: dict[int, list[tuple[int, str]]] = {}
    for r in conn.execute("""SELECT i.day,s.org_actor_id,json_extract(i.metadata_json,'$.history') FROM org_incidents i JOIN org_seats s
                             ON s.actor_id=i.offender_actor_id WHERE json_extract(i.metadata_json,'$.canon')=1"""):
        canon_by_org.setdefault(int(r[1]), []).append((int(r[0]), str(r[2])))
    owed: dict[int, list[tuple[int, str]]] = {}
    for r in conn.execute("SELECT actor_id,id,description FROM obligations WHERE source_kind='opening_past' ORDER BY id"):
        owed.setdefault(int(r[0]), []).append((int(r[1]), str(r[2])))

    # career tracks: one per working domain, stages from the package
    stages = cfg["career_stages"]
    fallback = str(cfg.get("default_domain") or "work")
    domains = sorted({str(p["dom"]) for p in people if p["dom"]} | {fallback})
    track_id: dict[str, int] = {}
    stage_ids: dict[str, list[tuple[int, int]]] = {}
    for dom in domains:
        key = f"career:{dom}"
        conn.execute("INSERT OR IGNORE INTO career_tracks(key,name,domain,description,typical_entry_age,is_canon) VALUES (?,?,?,?,?,0)",
                     (key, dom.replace("_", " ").title(), dom, "Work in this domain, as a person at the opening has lived it.", int(cfg["working_age"])))
        tid = int(conn.execute("SELECT id FROM career_tracks WHERE key=?", (key,)).fetchone()[0])
        track_id[dom] = tid
        for i, (sk, sn, yrs) in enumerate(stages):
            conn.execute("INSERT OR IGNORE INTO career_stages(track_id,stage_key,stage_name,sequence_index) VALUES (?,?,?,?)", (tid, sk, sn, i))
        stage_ids[dom] = [(int(yrs), int(conn.execute("SELECT id FROM career_stages WHERE track_id=? AND stage_key=?", (tid, sk)).fetchone()[0]))
                          for sk, _sn, yrs in stages]

    leaders = set(cfg["leader_roles"])
    kn_rows: list[tuple] = []
    mem_rows: list[tuple] = []
    car_rows: list[tuple] = []
    for p in people:
        aid = int(p["id"])
        s = seat.get(aid)
        mine = owner_of.get(aid) or []
        works = staff_of.get(aid) or []
        tier = "leader" if s is not None and str(s["role_key"]) in leaders else "member" if s is not None else "owner" if mine else "staff" if works else None
        age = (day0 - int(p["birth_day"])) / 365.0
        r = _rng(conn, f"p:{aid}")
        loc = int(p["loc"]) if p["loc"] is not None else None
        # work history
        dom = str(p["dom"] or fallback)
        if age >= float(cfg["working_age"]) + 1 and dom in track_id and (tier is not None):
            years = max(1.0, age - float(cfg["working_age"]) - r.uniform(0.0, min(4.0, max(0.0, age - 17))))
            sid = [x for y, x in stage_ids[dom] if years >= y][-1]
            inst = int(s["org_actor_id"]) if s is not None else None
            mentor = int(s["superior_actor_id"]) if s is not None and s["superior_actor_id"] else None
            car_rows.append((aid, track_id[dom], sid, inst, mentor, day0 - int(years * 365), day0 - int(min(years, 3) * 365)))
        if tier is None:
            continue
        # facts
        facts: list[tuple[str, str]] = []
        dist = loc_name.get(loc) if loc is not None else None
        if dist:
            facts.append((f"district:{loc}", T["district"].format(district=dist[0], note=_first_sentence(dist[1]) or "it is home ground")))
        for b in (biz_by_loc.get(loc or -1) or [])[:40]:
            if int(b["owner_actor_id"]) != aid:
                facts.append((f"business:{b['id']}", T["business"].format(name=b["name"], district=dist[0] if dist else "", owner=names.get(int(b["owner_actor_id"]), "someone"))))
        r.shuffle(facts)
        facts = facts[:max(1, _depth(r, cfg["depth"][tier]) - 3)]
        if s is not None:
            org = int(s["org_actor_id"])
            if s["superior_actor_id"]:
                facts.append((f"person:{s['superior_actor_id']}", T["superior"].format(superior=names.get(int(s["superior_actor_id"]), "someone"))))
            if org in ground:
                facts.append((f"ground:{org}", T["ground"].format(org=names.get(org, ""), ground=ground[org])))
            if tier == "leader":
                for rv, hist in quarrels.get(org, []):
                    facts.append((f"quarrel:{org}:{rv}", T["quarrel"].format(org=names.get(org, ""), rival=names.get(rv, ""), history=hist or "an old grievance")))
        if aid in spouse:
            facts.append((f"person:{spouse[aid]}", T["spouse"].format(other=names.get(spouse[aid], "someone"))))
        for w in works[:1]:
            facts.append((f"workplace:{w['name']}", T["boss_of"].format(name=w["name"], owner=names.get(int(w["owner_actor_id"]), "someone"))))
        for b in mine[:1]:
            facts.append((f"owns:{b['id']}", T["owner_of"].format(name=b["name"], district=dist[0] if dist else "")))
        for fk, text in facts:
            kn_rows.append((aid, f"lived:{fk}", text, round(r.uniform(0.6, 0.9), 2), -r.randint(30, 2500)))
        # memories
        mem: list[tuple[str, str, int | None, float, float, int]] = []
        for kind, iid, d, other in incidents.get(aid, [])[:3]:
            mem.append((f"incident:{iid}", T["incident_" + kind].format(year=year_of(d), other=names.get(other, "someone")), other or None,
                        r.uniform(-0.7, -0.2) if kind == "victim" else r.uniform(-0.3, 0.2), r.uniform(0.4, 0.8), d))
        for oid, what in owed.get(aid, [])[:1]:
            mem.append((f"owed:{oid}", T["obligation"].format(what=what.split(" for ", 1)[-1]), s["superior_actor_id"] if s else None,
                        -0.1, 0.5, day0 - r.randint(30, 900)))
        if s is not None:
            for d, hist in canon_by_org.get(int(s["org_actor_id"]), []):
                if (d - int(p["birth_day"])) / 365.0 >= 18.0 and r.random() < 0.3:
                    mem.append((f"event:{d}", T["event"].format(history=hist), None, -0.2, 0.8, d))
        if aid in marry_day and aid in spouse:
            mem.append(("married", T["married"].format(other=names.get(spouse[aid], "someone"), year=year_of(marry_day[aid])), spouse[aid], 0.7, 0.8, marry_day[aid]))
        if kids.get(aid):
            n = int(kids[aid])
            mem.append(("children", T["children"].format(n=n, child_word=cfg["words"]["child_word_one" if n == 1 else "child_word_many"]), None, 0.6, 0.7, day0 - 365))
        for b in mine[:1]:
            fd = int(b["founded_day"] if b["founded_day"] is not None else day0 - 365)
            mem.append((f"opened:{b['id']}", T["opened"].format(name=b["name"], year=year_of(fd)), None, 0.3, 0.7, fd))
        if age >= float(cfg["working_age"]) + 3:
            wy = int(age - float(cfg["working_age"]))
            mem.append(("worked", T["worked"].format(years=wy, year=year_of(day0 - wy * 365)), None, 0.1, 0.5, day0 - wy * 365))
        r.shuffle(mem)
        for mk, text, subj, val, sig, d in mem[:_depth(r, cfg["memories"][tier])]:
            mem_rows.append((aid, subj if subj in names else None, mk, text, max(-1.0, min(1.0, round(val, 2))), round(max(0.0, min(1.0, sig)), 2), min(d, day0), day0))

    conn.executemany("INSERT OR IGNORE INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,truth_event_id,learned_day) VALUES (?,?,?,?,NULL,?)", kn_rows)
    conn.executemany("""INSERT OR IGNORE INTO actor_memories(actor_id,subject_actor_id,memory_key,summary,valence,significance,source_kind,source_id,created_day,last_reinforced_day)
                        VALUES (?,?,?,?,?,?,'admin',0,?,?)""", mem_rows)
    conn.executemany("""INSERT OR IGNORE INTO actor_careers(actor_id,track_id,current_stage_id,institution_actor_id,mentor_actor_id,started_day,stage_started_day,status)
                        VALUES (?,?,?,?,?,?,?,'active')""", car_rows)
    return {"knowledge": len(kn_rows), "memories": len(mem_rows), "careers": len(car_rows), "tracks": len(track_id)}
