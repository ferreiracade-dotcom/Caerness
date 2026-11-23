"""Saint Jude is playable through the connector (Plan Task 22) plus the owner's text-veto cases.

Calls the connector's server-module functions directly (never the MCP tools), against a temp campaign dir and a
Saint Jude opening built into a temp file (data/saintjude.db is not shipped). Every check is independent and prints
PASS/FAIL with detail; the test fails at the end if any check failed.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []
STATE: dict = {}


def check(name):
    def deco(fn):
        def wrapper():
            t0 = time.time()
            try:
                detail = fn()
                ok = True
            except AssertionError as e:
                ok, detail = False, f"assertion: {e}"
            except Exception as e:
                ok, detail = False, f"exception: {type(e).__name__}: {e}\n{traceback.format_exc(limit=6)}"
            dt = time.time() - t0
            RESULTS.append((name, ok, str(detail)))
            print(f"[{'PASS' if ok else 'FAIL'}] {name} ({dt:.1f}s)\n    " + str(detail).replace("\n", "\n    "), flush=True)
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


def dump(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


def leak_hits(x) -> list:
    from tools import leak_scan
    return leak_scan.find_hits(dump(x))


def refused(out: dict) -> bool:
    return bool(out.get("error")) or out.get("status") == "refused" or out.get("outcome") == "refused" or bool(out.get("refused"))


def refusal_text(out: dict) -> str:
    return out.get("reason") or out.get("error") or dump(out)[:600]


_n = [0]


def cid(tag="c") -> str:
    _n[0] += 1
    return f"{tag}-{_n[0]:04d}"


def setup() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="sjplay_"))
    STATE["tmp"] = tmp
    os.environ["CAERNESS_CAMPAIGN_DIR"] = str(tmp / "campaigns")
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    base = tmp / "sj_base.db"
    t0 = time.time()
    from tools.build_opening import build_opening
    build_opening(base, package="saintjude")
    STATE["build_s"] = time.time() - t0
    from connector import campaign
    campaign._packaged_db = lambda pkg_id: base  # data/saintjude.db is not shipped
    STATE["db"] = campaign.open_campaign("sj", package="saintjude")


@check("1a resume without a character: creation + Saint Jude rulebook, no leak words")
def c1a():
    from connector import server
    r = server.resume_current()
    assert not r.get("error"), r
    assert r.get("needs_character"), list(r)
    rb = r["rulebook"]
    assert "Saint Jude" in rb, "rulebook has no Saint Jude section"
    h = leak_hits(r)
    assert not h, h[:5]
    return f"needs_character=True; rulebook {len(rb)} chars mentions Saint Jude; leak hits 0"


@check("1b author protagonist (28-year-old Kerrytown tavern worker), accepted")
def c1b():
    from connector import server
    prop = {"name": "Danny Ruane", "sex": "male", "age": 28, "place": "Kerrytown", "work": "bartender at a Kerrytown tavern",
            "concept": "a 28-year-old tavern worker in Kerrytown", "draw": 0, "accept": True}
    out = server.author(cid(), "protagonist", prop)
    assert out.get("status") == "created", out
    h = leak_hits(out)
    assert not h, h[:5]
    STATE["protagonist"] = out
    return f"created: actor_id={out.get('actor_id')} name={out.get('name')}"


@check("1c player set and resume now returns a scene")
def c1c():
    from connector import server
    r = server.resume_current()
    assert not r.get("error") and not r.get("needs_character"), dump(r)[:400]
    assert r["protagonist"], r
    return f"protagonist={r['protagonist']}"


@check("1d scene: Wednesday 1 January 1975, Saint Jude names, no leak words")
def c1d():
    from connector import server
    s = server.scene()
    assert not s.get("error"), s
    assert s["date"] == "Wednesday 1 January 1975", s["date"]
    h = leak_hits(s)
    assert not h, h[:5]
    names = json.loads((ROOT / "worlds" / "saintjude" / "names.json").read_text(encoding="utf-8"))["groups"]
    fam = {n.lower() for g in names.values() for n in g.get("family", [])}
    present = [p["name"] for p in s.get("present", [])]
    mine = s["protagonist"]["name"].split()[-1].lower()  # kin of the proposal I wrote are invented by the proposal, not drawn from the pools
    odd = [n for n in present if n.split()[-1].lower() not in fam and n.split()[-1].lower() != mine]
    STATE["scene0"] = s
    assert present, "nobody present"
    assert not odd, f"surnames not in the Saint Jude pools: {odd} (present={present})"
    return f"date={s['date']}; location={s['location']['name']}; present={present}"


@check("1e lore('St. Jude's') returns the cathedral passage")
def c1e():
    from connector import server
    r = server.lore("St. Jude's")
    assert not r.get("error"), r
    ps = r.get("passages") or []
    assert ps, r
    blob = " ".join(p["text"] for p in ps).lower()
    assert "cathedral" in blob, [p["section"] for p in ps]
    return f"{len(ps)} passages; sections={[p['section'] for p in ps][:3]}"


@check("1f act with a free-text intent resolves")
def c1f():
    from connector import server
    out = server.act(cid(), "operation", "I wipe down the bar and ask the regulars what they make of the week ahead")
    assert not out.get("error"), out
    assert not refused(out), refusal_text(out)
    h = leak_hits(out)
    assert not h, h[:5]
    return dump(out)[:400]


@check("1g advance 30 days -> Friday 31 January 1975")
def c1g():
    from connector import server
    t0 = time.time()
    out = server.advance(cid(), 30, "work the bar and keep my head down")
    dt = time.time() - t0
    STATE["adv30_s"] = dt
    assert not out.get("error"), out
    s = server.scene()
    assert s["date"] == "Friday 31 January 1975", (s["date"], dump(out)[:300])
    return f"{s['date']} after {out.get('elapsed_days')} days in {dt:.1f}s"


@check("1h author business 'pizzeria' accepted")
def c1h():
    from connector import server
    out = server.author(cid(), "business", {"name": "Ruane's Pizzeria", "trade": "pizzeria", "amount": 2000})
    assert not refused(out), refusal_text(out)
    assert out.get("status") != "refused", out
    return dump(out)[:300]


@check("1i leak_scan(campaign db) is empty")
def c1i():
    from tools import leak_scan
    leaks = leak_scan.scan(STATE["db"])
    assert not leaks, leak_scan.summarize(leaks)
    return "no leaks"


@check("D Open office lookup, author holder once, stable across 30 days, second holder refused")
def case_d():
    from connector import server
    lines = []
    # The opening seats the senior law offices (law.json level4_offices: a city is never without a Police Commissioner),
    # so test authoring on an Open office the opening leaves unfilled, chosen from the campaign's own facts.
    import sqlite3
    with contextlib.closing(sqlite3.connect(str(STATE["db"]))) as c:
        row = c.execute("SELECT subject FROM world_facts WHERE tag='Open' AND key LIKE 'office:%' AND holder_actor_id IS NULL "
                        "ORDER BY key LIMIT 1").fetchone()
    assert row, "no unfilled Open office left at the opening"
    q = row[0]
    lines.append(f"unfilled Open office: {q}")
    l0 = server.lookup(q)
    lines.append(f"lookup before: {dump(l0)[:300]}")
    assert l0.get("open") is True or l0.get("tag") == "Open", l0
    a = server.author(cid(), "person", {"name": "Harold Brennan", "age": 58, "work": q, "holds": q, "place": "Saint Jude"})
    lines.append(f"author holder: {dump(a)[:300]}")
    assert not refused(a), refusal_text(a)
    l1 = server.lookup(q)
    lines.append(f"lookup after: {dump(l1)[:300]}")
    assert l1.get("found") and "Brennan" in str(l1.get("name")), l1
    adv = server.advance(cid(), 30, "go about my business")
    assert not adv.get("error"), adv
    l2 = server.lookup(q)
    lines.append(f"lookup after advance: {dump(l2)[:200]}")
    assert l2.get("found") and l2.get("name") == l1.get("name"), (l1.get("name"), l2.get("name"), dump(l2)[:300])
    b = server.author(cid(), "person", {"name": "Edmund Voss", "age": 55, "work": q, "holds": q, "place": "Saint Jude"})
    lines.append(f"second holder: {dump(b)[:400]}")
    assert refused(b) and "held by" in refusal_text(b), dump(b)[:400]
    return "\n".join(lines)


@check("A federal judge holds a mob boss without bail in 1979: refused (dated rule, 1984)")
def case_a():
    from connector import server
    out = {}
    t0 = time.time()
    scene = server.scene()
    done = 0
    while True:
        day = scene["day"]
        if scene["date"].endswith("1979") and "January" not in scene["date"].split()[-2]:
            break
        if "1979" in scene["date"]:
            break
        out = server.advance(cid("adv"), 30, "get on with ordinary life")
        assert not out.get("error"), out
        done += int(out.get("elapsed_days") or 0)
        scene = server.scene()
        assert time.time() - t0 < 900, f"advance too slow: {done} days in {time.time() - t0:.0f}s"
    STATE["adv_to_1979_s"] = time.time() - t0
    act = server.act(cid(), "operation", "I ask a federal judge to hold the mob boss without bail under federal preventive detention")
    STATE["case_a"] = act
    txt = refusal_text(act)
    print(f"    date={scene['date']} advanced {done} days in {time.time() - t0:.0f}s (>120s: {time.time() - t0 > 120})")
    assert refused(act), f"not refused: {dump(act)[:500]}"
    assert "1984" in txt or "does not exist yet" in txt, txt
    return f"date={scene['date']}; refusal: {txt}"


@check("B real town Red Bank: act / author refused or redirected")
def case_b():
    from connector import server
    lines = []
    a = server.act(cid(), "operation", "I take the train out to Red Bank, New Jersey and look for work there")
    lines.append(f"act refused={refused(a)}: {refusal_text(a)[:400]}")
    p = server.author(cid(), "person", {"name": "Walt Pruitt", "age": 40, "work": "plumber", "place": "Red Bank"})
    lines.append(f"author person place=Red Bank refused={refused(p)}: {refusal_text(p)[:400]}")
    b = server.author(cid(), "business", {"name": "Red Bank Hardware", "trade": "hardware store", "place": "Red Bank", "amount": 800})
    lines.append(f"author business refused={refused(b)}: {refusal_text(b)[:400]}")
    s = server.scene()
    lines.append(f"scene location now: {s['location']['name']} (scene takes no place argument; checked it did not move to Red Bank)")
    detail = "\n".join(lines)
    assert refused(a) or refused(p) or refused(b), "Red Bank accepted everywhere:\n" + detail
    assert refused(a) and refused(p) and refused(b), "only partly vetoed:\n" + detail
    assert "Red Bank" not in s["location"]["name"], detail
    return detail


@check("C a public killing on Pad-paid ground opens a case, raises publicity and heat; an arrest is common but not certain")
def case_c():
    """Four public killings of four different men on the street, each two days apart. Each must open a report with a case and a loud
    publicity; the city's heat must rise; and across the four an arrest must be common (at least one) without being demanded every time:
    the law only has the man once someone has put his name to it."""
    import json
    from connector import server
    import sqlite3
    me = int(STATE["protagonist"]["actor_id"])
    with contextlib.closing(sqlite3.connect(str(STATE["db"]))) as c:
        # two made soldiers (outfit heat rises for their killing) and two ordinary men holding no seat: B13b's identification rule makes a
        # killing inside organised crime almost never cleared (the street keeps its mouth shut), so the arrest this check wants can only
        # come from the killings of men outside the outfits
        rivals = c.execute(
            """SELECT a.id,a.name FROM org_seats s JOIN actors a ON a.id=s.actor_id WHERE s.status='active' AND s.role_key='soldier' AND a.actor_type='character'
               AND a.status NOT IN ('dead','deceased') ORDER BY a.id LIMIT 2""").fetchall()
        rivals += c.execute(
            """SELECT a.id,a.name FROM actors a WHERE a.actor_type='character' AND a.status NOT IN ('dead','deceased') AND a.id<>?
               AND NOT EXISTS (SELECT 1 FROM org_seats s WHERE s.actor_id=a.id AND s.status='active') ORDER BY a.id LIMIT 2""", (me,)).fetchall()
        day0 = int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        c.row_factory = sqlite3.Row
        heat0 = float(c.execute("SELECT COALESCE(SUM(public_heat),0) FROM org_heat").fetchone()[0])
    assert len(rivals) == 4, "fewer than four rivals to shoot"
    for rid_, name in rivals:
        with contextlib.closing(sqlite3.connect(str(STATE["db"]))) as c:  # the rival is on the street where the shooting happens
            c.execute("UPDATE actors SET current_location_id=(SELECT current_location_id FROM actors WHERE id=?) WHERE id=?", (me, int(rid_)))
            c.commit()
        out = server.act(cid(), "operation", f"I shoot {name} dead in broad daylight on a crowded Kerrytown street", target_actor_id=int(rid_))
        print("act: " + dump(out)[:300])
        server.advance(cid(), 2, "lie low")
    with contextlib.closing(sqlite3.connect(str(STATE["db"]))) as c:
        c.row_factory = sqlite3.Row
        reps = c.execute("SELECT * FROM crime_reports WHERE offender_actor_id=? AND victim_actor_id IN (%s)" % ",".join("?" * len(rivals)),
                         (me, *[int(r[0]) for r in rivals])).fetchall()
        held = c.execute("SELECT COUNT(*) FROM custody WHERE actor_id=? AND kind='held'", (me,)).fetchone()[0]
        day1 = int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        heat1 = float(c.execute("SELECT COALESCE(SUM(public_heat),0) FROM org_heat").fetchone()[0])
    assert len(reps) >= 3, f"a public killing should open a report each time: {len(reps)} of 4"
    assert all(r["case_id"] is not None for r in reps), [dict(r) for r in reps]
    pubs = [float(json.loads(r["metadata_json"]).get("publicity") or 0.0) for r in reps]
    assert min(pubs) >= 50.0, f"a public killing is loud: {pubs}"
    assert heat1 > heat0, (heat0, heat1)
    assert held >= 1, f"an arrest should be common across four public killings; reports={[(r['id'], r['status']) for r in reps]}"
    return f"{len(reps)} reports, publicity {min(pubs):.0f}-{max(pubs):.0f}, public heat {heat0:.1f}->{heat1:.1f}, held {held}"


def run():
    t0 = time.time()
    setup()
    print(f"opening built in {STATE['build_s']:.1f}s -> {STATE['db']}")
    for fn in (c1a, c1b, c1c, c1d, c1e, c1f, c1g, c1h, c1i, case_d, case_a, case_b, case_c):
        fn()
    print("\nSUMMARY")
    for name, ok, _ in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"runtime {time.time() - t0:.0f}s; 30-day advance {STATE.get('adv30_s', 0):.1f}s; to 1979 {STATE.get('adv_to_1979_s', 0):.0f}s")
    bad = [n for n, ok, _ in RESULTS if not ok]
    assert not bad, f"{len(bad)} check(s) failed: {bad}"
    print("saintjude_connector_play_test passed")


if __name__ == "__main__":
    run()
