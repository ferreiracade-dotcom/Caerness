"""Fixture for the organisation core: a scratch DB on a minimal, non-Saint-Jude test package.

The package ("orgtest") has no outfits, no places and no names: its orgs.json declares two organisation kinds,
`firm` (head "chair", unit leader "manager") and `solo` (head "owner", no unit leader), and the flows
["take", "salary", "gift"] (gift: the flow of the `envelope` arrangement kind). Nothing here names a Saint Jude role.

    from tests.org_core_fixture import build
    f = build(); conn = f.conn
    f.firm, f.chair, f.managers, f.clerks, f.lines, f.solo ...
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ORGS = {
    "period_days": 28,
    "cadence_days": {"4": 1, "3": 7},
    "flows": ["take", "salary", "gift"],
    "ledger_kinds": {"salary": "wage"},
    "ledger_purpose": "org {flow}",
    "arrangement_kinds": {"envelope": {"flow": "gift", "ledger_kind": "bribe", "purpose": "an envelope"}},
    "kinds": {
        "firm": {"sphere": "commerce", "head": "chair", "unit_leader": "manager", "purse_roles": ["manager"], "courtship_scan": True,
                 "labels": {"chair": "Chair", "manager": "Manager", "clerk": "Clerk"}, "rules": [],
                 "motives": {"promote": [{"name": "restless", "weight": 0.8}]}, "rates": {"promote": {"base_rate": 1.0}}},
        "solo": {"sphere": "commerce", "head": "owner", "unit_leader": None, "courtship_scan": True,
                 "labels": {"owner": "Owner", "hand": "Hand"}, "rules": []},
    },
}


class Fixture:
    pass


def _package(root: Path) -> None:
    pkg = root / "orgtest"
    pkg.mkdir(parents=True)
    (pkg / "world.json").write_text(json.dumps({
        "id": "orgtest", "display_name": "Org test", "calendar": {"kind": "gregorian", "start": "2000-01-01"},
        "bible_path": "bible.md", "seed_path": "seed.json", "seed_namespace": "orgtest", "data": {"orgs": "orgs.json"}}), encoding="utf-8")
    (pkg / "bible.md").write_text("test package\n", encoding="utf-8")
    (pkg / "seed.json").write_text("{}", encoding="utf-8")
    (pkg / "orgs.json").write_text(json.dumps(ORGS), encoding="utf-8")


def person(conn: sqlite3.Connection, name: str) -> int:
    return int(conn.execute("INSERT INTO actors(name,actor_type,subtype) VALUES (?, 'character', 'test person')", (name,)).lastrowid)


def org(conn: sqlite3.Connection, name: str, kind: str) -> int:
    oid = int(conn.execute("INSERT INTO actors(name,actor_type) VALUES (?, 'institution')", (name,)).lastrowid)
    conn.execute("INSERT INTO org_profiles(org_actor_id,org_kind,sphere,package_key) VALUES (?,?,?,?)", (oid, kind, "commerce", name.lower()))
    return oid


def line(conn: sqlite3.Connection, holding_id: int, unit_id: int | None, holder: int, weekly: float) -> int:
    return int(conn.execute(
        "INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,weekly_take,started_day) VALUES (?,?,?,?,?,0)",
        (holding_id, unit_id, holder, "a test line", weekly)).lastrowid)


def kill(conn: sqlite3.Connection, actor_id: int) -> None:
    """A person dies: his actor row and every seat he holds say so (what the money code checks)."""
    conn.execute("UPDATE actors SET status='dead' WHERE id=?", (int(actor_id),))
    conn.execute("UPDATE org_seats SET status='dead' WHERE actor_id=?", (int(actor_id),))


def build() -> Fixture:
    """A fresh scratch DB. One firm: a chair, two managers, four clerks (two per manager), one holding, two lines on
    clerk 1 and clerk 3. One `solo` organisation (an owner and a hand) with a line on the hand."""
    tmp = Path(tempfile.mkdtemp())
    worlds = tmp / "worlds"
    _package(worlds)
    os.environ["CAERNESS_DB_PATH"] = str(tmp / "orgtest.db")
    for k in ("CAERNESS_WORLDS_DIR", "CAERNESS_WORLD_PACKAGE"):
        os.environ.pop(k, None)
    from engine import db
    db.init_db()  # built on the default package, then bound to the test package
    conn = db.connect()
    os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "orgtest"
    from engine import orgs
    from engine.world_package import set_campaign_package
    set_campaign_package(conn, "orgtest")

    f = Fixture()
    f.conn = conn
    f.firm = org(conn, "Alpha Firm", "firm")
    f.chair = person(conn, "Chair One")
    f.managers = [person(conn, f"Manager {i}") for i in (1, 2)]
    f.clerks = [person(conn, f"Clerk {i}") for i in (1, 2, 3, 4)]
    unit = [int(conn.execute("INSERT INTO org_units(org_actor_id,leader_actor_id,label) VALUES (?,?,?)",
                             (f.firm, m, f"unit of {m}")).lastrowid) for m in f.managers]
    orgs.seat(conn, f.chair, f.firm, "chair", unit_id=None, superior_actor_id=None, level=4, day=0)
    for m, u in zip(f.managers, unit):
        orgs.seat(conn, m, f.firm, "manager", unit_id=u, superior_actor_id=f.chair, level=4, day=0)
    for i, c in enumerate(f.clerks):
        orgs.seat(conn, c, f.firm, "clerk", unit_id=unit[i // 2], superior_actor_id=f.managers[i // 2], level=3, day=0)
    holding = int(conn.execute("INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) "
                               "VALUES (?, 'trade', 100, 52000, 'opening', 0)", (f.firm,)).lastrowid)
    f.lines = [line(conn, holding, unit[0], f.clerks[0], 500.0), line(conn, holding, unit[1], f.clerks[2], 500.0)]

    f.solo = org(conn, "Solo Shop", "solo")
    f.owner, f.hand = person(conn, "Owner One"), person(conn, "Hand One")
    orgs.seat(conn, f.owner, f.solo, "owner", unit_id=None, superior_actor_id=None, level=4, day=0)
    orgs.seat(conn, f.hand, f.solo, "hand", unit_id=None, superior_actor_id=f.owner, level=3, day=0)
    solo_holding = int(conn.execute("INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) "
                                    "VALUES (?, 'trade', 100, 26000, 'opening', 0)", (f.solo,)).lastrowid)
    f.solo_line = line(conn, solo_holding, None, f.hand, 500.0)
    conn.commit()
    return f
