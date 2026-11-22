"""Races: an election as a venture, the vote from drivers, and fraud (politics P1).

A race opens a set number of days before an office's election. Candidates file by a weighed choice (the protagonist only by his
own act); the primary and the general are votes counted group by group: a group's turnout (`electorate.turnout`) times each
candidate's share of it, a softmax over a score made of drivers, every weight a package figure. Nothing fixes a result: the seeded
noise is part of the score, and a close race goes either way across seeds. The race is a venture of the business layer's campaign
kind (parked: this module moves its stage). A lasting result is held through the history intake.
"""
from __future__ import annotations

import json
import math
import random

from . import civic_field, civic_seams, design, electorate, offices, orgs
from .design import figure
from .world_package import package_for, politics_rules


def _rules(conn) -> dict:
    return politics_rules(package_for(conn))


def _drivers(conn) -> dict:
    return _rules(conn).get("vote_drivers") or {}


def _f(conn, name: str, default: float = 0.0) -> float:
    return float(figure(conn, name, default)) if name else default


def _rng(conn, *key) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:race:" + ":".join(str(k) for k in key))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _j(text, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


PARKED = 2_000_000_000


# ---- reading ------------------------------------------------------------------------------------------------------

def race(conn, race_id: int):
    return conn.execute("SELECT * FROM races WHERE id=?", (int(race_id),)).fetchone()


def office_key(conn, race_id: int) -> str:
    return str(conn.execute("SELECT o.office_key FROM races r JOIN offices o ON o.id=r.office_id WHERE r.id=?", (int(race_id),)).fetchone()[0])


def candidates(conn, race_id: int) -> list[int]:
    return [int(r[0]) for r in conn.execute("SELECT actor_id FROM race_candidates WHERE race_id=? AND dropped_day IS NULL ORDER BY filed_day,actor_id", (int(race_id),))]


def _result(conn, race_id: int) -> dict:
    return _j(race(conn, race_id)["result_json"], {})


def _save(conn, race_id: int, res: dict) -> None:
    conn.execute("UPDATE races SET result_json=? WHERE id=?", (json.dumps(res, sort_keys=True, default=str), int(race_id)))


def _is_player(conn, actor: int) -> bool:
    from . import player
    p = player.get_player(conn)
    return p is not None and int(p["player_actor_id"]) == int(actor)


def party_of(conn, actor: int) -> int | None:
    """The field organisation (one that holds stakes) a person sits in, else none: an independent."""
    r = conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active' AND org_actor_id IN "
                     "(SELECT DISTINCT holder_id FROM field_holdings WHERE holder_kind='org' AND ended_day IS NULL) ORDER BY id LIMIT 1", (int(actor),)).fetchone()
    return int(r[0]) if r else None


def _standing(conn, actor: int, org: int | None) -> float:
    if org is None:
        return 0.0
    r = conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active' LIMIT 1", (int(actor), int(org))).fetchone()
    return float(r[0] or 0.0) if r else 0.0


def _venture_park(conn, vid: int) -> None:
    conn.execute("UPDATE venture_details SET next_due_day=? WHERE project_id=?", (PARKED, int(vid)))


def _stage(conn, race_id: int, stage: str, day: int) -> None:
    conn.execute("UPDATE races SET stage=? WHERE id=?", (stage, int(race_id)))
    vid = race(conn, race_id)["venture_id"]
    if vid is not None:
        civic_seams.advance_venture(conn, int(vid), stage, int(day))
        _venture_park(conn, int(vid))


def _ensure_venture(conn, race_id: int, backer: int, day: int) -> None:
    r = race(conn, race_id)
    if r["venture_id"] is not None:
        return
    kind = (_rules(conn).get("race_stages") or {}).get("venture_kind")
    if not kind:
        return
    vid = civic_seams.open_venture(conn, kind, int(backer), meta={"title": f"race {office_key(conn, race_id)} {r['election_day']}", "day": int(day)})
    conn.execute("UPDATE races SET venture_id=? WHERE id=?", (vid, int(race_id)))
    _venture_park(conn, vid)
    if r["stage"] != "filing":
        _stage(conn, race_id, r["stage"], day)


# ---- scheduling ---------------------------------------------------------------------------------------------------

def filing_close(conn, r) -> int:
    first = r["primary_day"] if r["primary_day"] is not None else r["election_day"]
    return int(first) - int(_f(conn, "race_filing_lead_days", 45))


def schedule(conn, day: int) -> int:
    """Open a race for every elected office whose next election falls within the opening window."""
    n = 0
    window = int(_f(conn, "race_open_days", 330))
    for o in conn.execute("SELECT * FROM offices WHERE filled_by='elected' ORDER BY id").fetchall():
        nd = offices.next_dates(conn, o["office_key"], int(day) - 1)
        if not nd or int(nd["election_day"]) - int(day) > window:
            continue
        if conn.execute("SELECT 1 FROM races WHERE office_id=? AND election_day=?", (int(o["id"]), int(nd["election_day"]))).fetchone():
            continue
        rid = int(conn.execute("INSERT INTO races(office_id,seat_no,stage,primary_day,election_day,result_json) VALUES (?,?,?,?,?,?)",
                               (int(o["id"]), 1, "filing", nd.get("primary_day"), int(nd["election_day"]),
                                json.dumps({"term_start_day": int(nd["term_start_day"]), "year": int(nd["year"])}))).lastrowid)
        n += 1
    return n


# ---- filing -------------------------------------------------------------------------------------------------------

def pool(conn, race_id: int) -> list[int]:
    """Who weighs filing: the incumbent and the man each organisation with a hold on the district would put up."""
    key = office_key(conn, race_id)
    out: list[int] = []
    inc = offices.holder(conn, key)
    if inc is not None:
        out.append(int(inc))
    seen_orgs: set[int] = set()
    for g in electorate._district_groups(conn, key):
        for h in civic_field.holders_of(conn, "delivery", g["group_key"]):
            if h["holder_kind"] == "org" and int(h["holder_id"]) not in seen_orgs:
                seen_orgs.add(int(h["holder_id"]))
                who = civic_field._filler(conn, int(h["holder_id"]), key)
                if who is not None and who not in out:
                    out.append(int(who))
    return [a for a in out if not _is_player(conn, a)]


def _backing(conn, org: int | None, key: str) -> float:
    if org is None:
        return 0.0
    gs = electorate._district_groups(conn, key)
    return sum(electorate.delivery(conn, int(g["id"]), "org", org) for g in gs) / max(1, len(gs))


def _file(conn, actor: int, race_id: int, day: int) -> None:
    org = party_of(conn, actor)
    conn.execute("INSERT OR IGNORE INTO race_candidates(race_id,actor_id,party_org_id,filed_day) VALUES (?,?,?,?)", (int(race_id), int(actor), org, int(day)))
    _ensure_venture(conn, race_id, actor, day)


def consider_filing(conn, actor: int, race_id: int, day: int) -> bool:
    """A weighed choice from standing, backing and incumbency. Never the protagonist's: he files by his own act (`file`)."""
    if _is_player(conn, actor):
        return False
    key = office_key(conn, race_id)
    ok, _ = offices.eligible(conn, int(actor), key, int(day))
    if not ok:
        return False
    d = (_drivers(conn).get("filing") or {})
    org = party_of(conn, actor)
    z = (_f(conn, d.get("base")) + _f(conn, d.get("incumbent")) * (1.0 if offices.holder(conn, key) == int(actor) else 0.0)
         + _f(conn, d.get("backing")) * _backing(conn, org, key) + _f(conn, d.get("standing")) * _standing(conn, actor, org))
    if _rng(conn, race_id, actor, "file").random() < _sigmoid(z):
        _file(conn, actor, race_id, day)
        return True
    return False


def file(conn, actor: int, race_id: int, day: int) -> bool:
    """A person files by his own act. A veto with its reason: the office's eligibility, and the filing window."""
    r = race(conn, race_id)
    if r["status"] != "open" or int(day) > filing_close(conn, r) or r["stage"] != "filing":
        raise ValueError("filing_closed")
    ok, why = offices.eligible(conn, int(actor), office_key(conn, race_id), int(day))
    if not ok:
        raise ValueError(why or "ineligible")
    _file(conn, actor, race_id, day)
    return True


def drop(conn, race_id: int, actor: int, reason: str, day: int) -> None:
    conn.execute("UPDATE race_candidates SET dropped_day=?,drop_reason=? WHERE race_id=? AND actor_id=? AND dropped_day IS NULL", (int(day), reason, int(race_id), int(actor)))


def _screen(conn, race_id: int, day: int) -> None:
    """A candidate who has become ineligible since filing is dropped, with the reason."""
    key = office_key(conn, race_id)
    for a in candidates(conn, race_id):
        ok, why = offices.eligible(conn, a, key, int(day))
        if not ok:
            drop(conn, race_id, a, why or "ineligible", day)


# ---- the vote -----------------------------------------------------------------------------------------------------

def _score(conn, race_id: int, c: int, party: int | None, g, day: int, key: str, d: dict, incumbent: int | None) -> dict[str, float]:
    gid = int(g["id"])
    deliv = electorate.delivery(conn, gid, "org", party) if party is not None else 0.0
    deliv += sum(electorate.delivery(conn, gid, "actor", c) for _ in (0,))
    home = conn.execute("SELECT COALESCE(home_location_id,current_location_id) FROM actors WHERE id=?", (int(c),)).fetchone()
    local = 1.0 if (home and home[0] is not None and g["location_id"] is not None and offices._inside(conn, int(home[0]), int(g["location_id"]))) else 0.0
    return {"incumbent": _f(conn, d.get("incumbent")) * (1.0 if incumbent == c else 0.0),
            "delivery": _f(conn, d.get("delivery")) * deliv,
            "regard": _f(conn, d.get("regard")) * electorate.regard(conn, gid, c, day),
            "local": _f(conn, d.get("local")) * local,
            "noise": _rng(conn, race_id, gid, c).gauss(0.0, _f(conn, d.get("noise_sd")))}


def vote_shares(conn, race_id: int, stage: str, day: int, among: list[int] | None = None, *, _why: dict | None = None) -> dict[int, float]:
    """Votes per candidate, summed over the groups of the district. Each group: turnout (times the primary's factor in a primary) times
    a softmax of the candidates' scores; fraud logged for the general is added in the group where it was done."""
    key = office_key(conn, race_id)
    d = _drivers(conn)
    cands = list(among) if among is not None else candidates(conn, race_id)
    out = {c: 0.0 for c in cands}
    if not cands:
        return out
    parties = {c: conn.execute("SELECT party_org_id FROM race_candidates WHERE race_id=? AND actor_id=?", (int(race_id), c)).fetchone()[0] for c in cands}
    incumbent = offices.holder(conn, key)
    temp = max(1e-6, _f(conn, d.get("temperature"), 1.0))
    factor = _f(conn, d.get("primary_turnout"), 1.0) if stage == "primary" else 1.0
    weights = {c: {} for c in cands}
    total_w = 0.0
    for g in electorate._district_groups(conn, key):
        scores = {c: _score(conn, race_id, c, parties[c], g, day, key, d, incumbent) for c in cands}
        z = {c: sum(s.values()) / temp for c, s in scores.items()}
        m = max(z.values())
        ex = {c: math.exp(v - m) for c, v in z.items()}
        tot = sum(ex.values())
        mass = float(g["size"]) * electorate.turnout(conn, int(g["id"]), race_id, day) * factor
        total_w += mass
        for c in cands:
            out[c] += mass * ex[c] / tot
            for name, v in scores[c].items():
                weights[c][name] = weights[c].get(name, 0.0) + mass * v
    if stage != "primary":
        for f in _result(conn, race_id).get("fraud") or []:
            if int(f["actor"]) in out:
                out[int(f["actor"])] += float(f["size"])
    if _why is not None:
        for c in cands:
            _why[c] = {k: v / total_w if total_w else 0.0 for k, v in weights[c].items()}
    return out


def run_primary(conn, race_id: int, day: int) -> dict:
    """Candidates of one party meet in its primary; the winner goes on and the others are dropped. Independents go straight to the general."""
    _screen(conn, race_id, day)
    by_party: dict[int, list[int]] = {}
    for c in candidates(conn, race_id):
        p = conn.execute("SELECT party_org_id FROM race_candidates WHERE race_id=? AND actor_id=?", (int(race_id), c)).fetchone()[0]
        if p is not None:
            by_party.setdefault(int(p), []).append(c)
    res: dict = {}
    for p, cs in by_party.items():
        if len(cs) < 2:
            continue
        v = vote_shares(conn, race_id, "primary", day, cs)
        order = sorted(cs, key=lambda a: (-v[a], a))
        total = sum(v.values()) or 1.0
        for a in cs:
            conn.execute("UPDATE race_candidates SET primary_share=? WHERE race_id=? AND actor_id=?", (v[a] / total, int(race_id), a))
        for a in order[1:]:
            drop(conn, race_id, a, "lost_primary", day)
        res[str(p)] = {"winner": order[0], "votes": {str(a): v[a] for a in cs}}
    r = _result(conn, race_id)
    r["primary"] = res
    _save(conn, race_id, r)
    return res


def run_general(conn, race_id: int, day: int) -> dict:
    _screen(conn, race_id, day)
    cs = candidates(conn, race_id)
    r = _result(conn, race_id)
    key = office_key(conn, race_id)
    if not cs:
        conn.execute("UPDATE races SET status='void',stage='result' WHERE id=?", (int(race_id),))
        r["void"] = "no candidate left"
        _save(conn, race_id, r)
        _finish_venture(conn, race_id, "failed", "no candidate", day)
        return r
    why: dict = {}
    v = vote_shares(conn, race_id, "general", day, cs, _why=why)
    total = sum(v.values()) or 1.0
    order = sorted(cs, key=lambda a: (-v[a], a))
    top = [a for a in order if abs(v[a] - v[order[0]]) < 1e-9]
    winner = top[0] if len(top) == 1 else _rng(conn, race_id, "tie").choice(top)
    for a in cs:
        conn.execute("UPDATE race_candidates SET general_share=? WHERE race_id=? AND actor_id=?", (v[a] / total, int(race_id), a))
    r.update(winner=winner, votes={str(a): v[a] for a in cs}, why={str(a): w for a, w in why.items()}, decided_day=int(day))
    conn.execute("UPDATE races SET status='decided',stage='result' WHERE id=?", (int(race_id),))
    _save(conn, race_id, r)
    name = conn.execute("SELECT name FROM actors WHERE id=?", (winner,)).fetchone()[0]
    label = offices.spec(conn, key).get("role_text") or key
    civic_seams.hold_outcome(conn, what=f"{name} won the election for {label}", people=[winner] + [a for a in cs if a != winner],
                             dates={"start_day": int(r.get("term_start_day", day))}, consequences=[f"holds {key} from day {r.get('term_start_day', day)}"], day=int(day))
    for g in electorate._district_groups(conn, key):
        civic_seams.tell_group(conn, int(g["id"]), winner, f"won the election for {label}", source="election", confidence=0.9, valence=0.3, day=int(day))
        for a in cs:
            if a != winner:
                civic_seams.tell_group(conn, int(g["id"]), a, f"lost the election for {label}", source="election", confidence=0.9, valence=-0.1, day=int(day))
    _finish_venture(conn, race_id, "completed", None, day)
    return r


def _finish_venture(conn, race_id: int, outcome: str, reason, day: int) -> None:
    vid = race(conn, race_id)["venture_id"]
    if vid is not None:
        civic_seams.advance_venture(conn, int(vid), "result", int(day), outcome={"outcome": outcome, "reason": reason})


def result_why(conn, race_id: int) -> dict:
    """The drivers behind each candidate's vote: his score's terms averaged over the votes cast."""
    r = _result(conn, race_id)
    return {"winner": r.get("winner"), "votes": r.get("votes", {}), "why": r.get("why", {})}


# ---- fraud ----------------------------------------------------------------------------------------------------------

def commit_fraud(conn, actor: int, race_id: int, group_id: int, kind: str, size: int, day: int) -> dict:
    """Add `size` votes for a candidate in one group. The chance it is caught rises with the delivery of his rivals there (their
    poll watchers) and with the size; a caught fraud opens a crime report and costs him with the district's groups."""
    from . import crime_response
    d = _drivers(conn).get("fraud") or {}
    r = _result(conn, race_id)
    if int(actor) not in candidates(conn, race_id):
        raise ValueError("not a candidate")
    mine = party_of(conn, actor)
    watchers = sum(electorate.delivery(conn, int(group_id), h["holder_kind"], int(h["holder_id"]))
                   for h in civic_field.holders_of(conn, "delivery", electorate.group(conn, group_id)["group_key"])
                   if not (h["holder_kind"] == "org" and int(h["holder_id"]) == mine))
    fl = r.setdefault("fraud", [])
    p = _sigmoid(_f(conn, d.get("base")) + _f(conn, d.get("watchers")) * watchers + _f(conn, d.get("size")) * math.log1p(size))
    exposed = _rng(conn, race_id, group_id, actor, "fraud", len(fl)).random() < p
    rec = {"actor": int(actor), "group": int(group_id), "kind": kind, "size": int(size), "day": int(day), "exposed": bool(exposed)}
    out = {"gain": int(size), "exposed": bool(exposed), "chance": p, "report_id": None}
    if exposed:
        rid = crime_response.open_report(conn, crime_kind=str(_drivers(conn).get("crime_kind") or "fraud"), day=int(day), offender_actor_id=int(actor), public=True,
                                         metadata={"race_id": int(race_id), "group_id": int(group_id), "fraud_kind": kind})
        rec["report_id"] = out["report_id"] = int(rid)
        for g in electorate._district_groups(conn, office_key(conn, race_id)):
            civic_seams.tell_group(conn, int(g["id"]), int(actor), "was caught cheating in the count", source="press", confidence=0.9, valence=-0.8,
                                   force=0.5, costly=True, day=int(day))
    fl.append(rec)
    _save(conn, race_id, r)
    return out


# ---- the weekly step -----------------------------------------------------------------------------------------------

def seat_winners(conn, day: int) -> int:
    """A decided race's winner takes the office on the term's start day."""
    n = 0
    for r in conn.execute("SELECT * FROM races WHERE status='decided' ORDER BY id").fetchall():
        res = _j(r["result_json"], {})
        if res.get("seated") or int(res.get("term_start_day", 1 << 40)) > int(day):
            continue
        key = office_key(conn, int(r["id"]))
        start = int(res["term_start_day"])
        offices.seat_holder(conn, key, int(res["winner"]), how="elected", day=start, seat_no=int(r["seat_no"]), source_id=int(r["id"]))
        if civic_field.holder_of(conn, "patronage", key) is not None:
            from . import civic_patronage
            civic_patronage.follow(conn, key, int(res["winner"]), day=start, cause="election")
        res["seated"] = start
        _save(conn, int(r["id"]), res)
        n += 1
    return n


def advance(conn, day: int) -> dict:
    """Open, move and decide every race up to `day` (safe to call over a jump of days: each step happens in its order)."""
    out = {"opened": schedule(conn, day), "decided": 0, "void": 0}
    for r in conn.execute("SELECT * FROM races WHERE status='open' ORDER BY election_day,id").fetchall():
        rid = int(r["id"])
        res = _result(conn, rid)
        if r["stage"] == "filing" and int(day) >= filing_close(conn, r):
            if not res.get("considered"):
                for a in pool(conn, rid):
                    consider_filing(conn, a, rid, filing_close(conn, r))
                res = _result(conn, rid)
                res["considered"] = True
                _save(conn, rid, res)
            if not candidates(conn, rid):
                conn.execute("UPDATE races SET status='void',stage='result' WHERE id=?", (rid,))
                res["void"] = "nobody filed"
                _save(conn, rid, res)
                out["void"] += 1
                continue
            _stage(conn, rid, "primary" if r["primary_day"] is not None else "campaign", filing_close(conn, r))
            r = race(conn, rid)
        if r["stage"] == "primary" and int(day) >= int(r["primary_day"]):
            run_primary(conn, rid, int(r["primary_day"]))
            _stage(conn, rid, "campaign", int(r["primary_day"]))
            r = race(conn, rid)
        if r["stage"] == "campaign" and int(day) >= int(r["election_day"]):
            _stage(conn, rid, "general", int(r["election_day"]))
            run_general(conn, rid, int(r["election_day"]))
            if race(conn, rid)["status"] == "decided":
                out["decided"] += 1
    seat_winners(conn, day)
    return out
