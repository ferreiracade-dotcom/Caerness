"""Schema 117 (organisation core): the outfit tables become organisation tables.

Run: CAERNESS_DB_PATH=<tmp>.db PYTHONPATH=. python tests/org_migration_test.py
A fresh DB has the org tables and none of the old ones; one person can hold seats in two organisations (one per
organisation); a schema-116 Saint Jude DB with a hand-made outfit world migrates with every row and money total kept."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ORG_TABLES = ("org_profiles", "org_units", "org_seats", "org_holdings", "org_lines", "org_money", "org_agenda",
              "org_incidents", "org_arrangements")
OLD_TABLES = ("outfit_crews", "outfit_ranks", "outfit_holdings", "outfit_lines", "outfit_money", "outfit_agenda",
              "outfit_incidents", "pad_envelopes")
KINDS = ("take", "associate_earning", "kickup", "executive_share", "pad")
EXPECTED_FAILURES: set[str] = set()


def table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _scratch(name: str) -> Path:
    path = Path(tempfile.mkdtemp()) / name
    os.environ["CAERNESS_DB_PATH"] = str(path)
    return path


def fresh_db():
    from engine.db import connect, init_db
    _scratch("fresh.db")
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    init_db()
    return connect()


def _actor(conn, name: str, kind: str = "character") -> int:
    return int(conn.execute("INSERT INTO actors(name,actor_type) VALUES (?,?)", (name, kind)).lastrowid)


def test_fresh_db_has_org_tables():
    from engine.db import SCHEMA_VERSION
    conn = fresh_db()
    assert SCHEMA_VERSION == 119
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 119
    for t in ORG_TABLES:
        assert table_exists(conn, t), t
    for t in OLD_TABLES:
        assert not table_exists(conn, t), t
    conn.close()


def test_one_person_two_seats_allowed():
    conn = fresh_db()
    a = _actor(conn, "Dual Man")
    o1, o2 = _actor(conn, "Org One", "institution"), _actor(conn, "Org Two", "institution")
    conn.execute("INSERT INTO org_seats(actor_id,org_actor_id,role_key,level) VALUES (?,?,?,?)", (a, o1, "head", 4))
    conn.execute("INSERT INTO org_seats(actor_id,org_actor_id,role_key,level) VALUES (?,?,?,?)", (a, o2, "owner", 2))
    try:
        conn.execute("INSERT INTO org_seats(actor_id,org_actor_id,role_key,level) VALUES (?,?,?,?)", (a, o1, "other", 3))
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("a second seat for the same (actor, organisation) must be refused")
    for bad in (0, 5):
        try:
            conn.execute("INSERT INTO org_seats(actor_id,org_actor_id,role_key,level) VALUES (?,?,?,?)", (_actor(conn, f"L{bad}"), o1, "x", bad))
        except sqlite3.IntegrityError:
            continue
        raise AssertionError(f"level {bad} must be refused")
    conn.close()


def _build_116():
    """A scratch DB on the Saint Jude package, migrated only up to 116 (old outfit DDL), holding a hand-made outfit world."""
    from engine.db import _apply_migrations, connect, SCHEMA_PATH
    from engine.world_package import outfit_rules, package_for, set_campaign_package
    _scratch("old116.db")
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    conn = connect()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT OR IGNORE INTO world_state(id, world_name, current_day) VALUES (1, 'Saint Jude', 0)")  # as init_db does
    conn.execute("INSERT OR IGNORE INTO campaign_setup_state(id,bootstrap_complete,player_setup_complete) VALUES (1,0,0)")
    set_campaign_package(conn, "saintjude")
    _apply_migrations(conn, 0, 116)
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 116
    for t in OLD_TABLES:
        assert table_exists(conn, t), t
    specs = outfit_rules(package_for(conn))["outfits"]
    fam, club = specs["sabatini"], specs["horsemen"]
    assert fam["shape"] == "family" and club["shape"] == "club"
    fam_id, club_id = _actor(conn, fam["institution"], "institution"), _actor(conn, club["institution"], "institution")
    people = [_actor(conn, f"Man {i}") for i in range(8)]
    crews = {}
    for org, lead in ((fam_id, people[1]), (club_id, people[5])):
        crews[org] = int(conn.execute("INSERT INTO outfit_crews(outfit_actor_id,leader_actor_id,label,created_day) VALUES (?,?,?,?)",
                                      (org, lead, "crew", 3)).lastrowid)
    seats = [(0, fam_id, "boss", None, None, 4, 2), (1, fam_id, "capo", crews[fam_id], 0, 4, 5), (2, fam_id, "soldier", crews[fam_id], 1, 3, 7),
             (3, fam_id, "soldier", crews[fam_id], 1, 3, 8), (4, fam_id, "associate", crews[fam_id], 2, 3, None),
             (5, club_id, "president", None, None, 4, 9), (6, club_id, "officer", None, 5, 3, None), (7, club_id, "member", None, 6, 3, None)]
    for i, org, role, crew, sup, level, made in seats:
        conn.execute("""INSERT INTO outfit_ranks(actor_id,outfit_actor_id,rank_key,crew_id,superior_actor_id,level,joined_day,made_day)
                        VALUES (?,?,?,?,?,?,?,?)""", (people[i], org, role, crew, people[sup] if sup is not None else None, level, 1, made))
    holds = [int(conn.execute("INSERT INTO outfit_holdings(outfit_actor_id,pool_key,share_pct,yearly_take,source) VALUES (?,?,?,?,'opening')",
                              (org, pool, 50, 1e6)).lastrowid) for org, pool in ((fam_id, "numbers"), (fam_id, "loansharking"), (club_id, "drugs"))]
    lines = [int(conn.execute("INSERT INTO outfit_lines(holding_id,crew_id,holder_actor_id,description,weekly_take) VALUES (?,?,?,?,?)",
                              (h, crews[o], people[p], "a line", 1000.0 * (n + 1))).lastrowid)
             for n, (h, o, p) in enumerate(((holds[0], fam_id, 1), (holds[1], fam_id, 2), (holds[2], club_id, 5)))]
    # outfit_money rows of every kind; the pad row from a bagman to an officer, neither holding a seat
    bagman, officer = _actor(conn, "Bagman"), _actor(conn, "Officer")
    money = [(10, "take", None, people[1], lines[0], 500.0), (10, "take", None, people[5], lines[2], 300.0),
             (10, "associate_earning", people[2], people[4], None, 40.0), (10, "kickup", people[2], people[1], None, 70.0),
             (10, "executive_share", people[1], people[0], None, 25.0), (10, "pad", people[1], bagman, None, 60.0),
             (10, "pad", bagman, officer, None, 55.0)]
    conn.executemany("INSERT INTO outfit_money(day,kind,from_actor_id,to_actor_id,line_id,amount) VALUES (?,?,?,?,?,?)", money)
    conn.executemany("INSERT INTO outfit_agenda(actor_id,kind,due_day) VALUES (?,?,?)", [(people[2], "meeting", 20), (people[3], "meeting", 21)])
    conn.execute("INSERT INTO outfit_incidents(day,kind,offender_actor_id,victim_actor_id,raised_to_outfit_actor_id) VALUES (12,'theft',?,?,?)",
                 (people[3], people[4], fam_id))
    for n in range(3):
        conn.execute("INSERT INTO pad_envelopes(officer_actor_id,payer_outfit_actor_id,position_key,weekly_usd,bagman_actor_id,started_day) VALUES (?,?,?,?,?,0)",
                     (officer if n == 0 else _actor(conn, f"Officer {n}"), fam_id, f"p:{n}", 100.0 * (n + 1), bagman))
    conn.commit()
    return conn, fam, club, fam_id, club_id, people, bagman, officer


def test_116_saintjude_opening_survives_117():
    from engine.db import _apply_migrations, SCHEMA_VERSION
    conn, fam, club, fam_id, club_id, people, bagman, officer = _build_116()
    before = {
        "units": conn.execute("SELECT COUNT(*) FROM outfit_crews").fetchone()[0],
        "seats": conn.execute("SELECT COUNT(*) FROM outfit_ranks").fetchone()[0],
        "holdings": conn.execute("SELECT COUNT(*) FROM outfit_holdings").fetchone()[0],
        "lines": conn.execute("SELECT COUNT(*) FROM outfit_lines").fetchone()[0],
        "money": conn.execute("SELECT COUNT(*) FROM outfit_money").fetchone()[0],
        "agenda": conn.execute("SELECT COUNT(*) FROM outfit_agenda").fetchone()[0],
        "incidents": conn.execute("SELECT COUNT(*) FROM outfit_incidents").fetchone()[0],
        "arr": conn.execute("SELECT COUNT(*) FROM pad_envelopes").fetchone()[0],
        "sums": {k: float(conn.execute("SELECT COALESCE(SUM(amount),0) FROM outfit_money WHERE kind=?", (k,)).fetchone()[0]) for k in KINDS},
        "ranks": sorted((r[0], r[1], r[2]) for r in conn.execute("SELECT actor_id,rank_key,made_day FROM outfit_ranks")),
        "weekly": float(conn.execute("SELECT SUM(weekly_usd) FROM pad_envelopes").fetchone()[0]),
    }
    assert before["seats"] == 8 and before["money"] == 7 and before["arr"] == 3
    _apply_migrations(conn, 116)
    conn.commit()
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION == 119
    for t in OLD_TABLES:
        assert not table_exists(conn, t), t
    after = {
        "units": conn.execute("SELECT COUNT(*) FROM org_units").fetchone()[0],
        "seats": conn.execute("SELECT COUNT(*) FROM org_seats").fetchone()[0],
        "holdings": conn.execute("SELECT COUNT(*) FROM org_holdings").fetchone()[0],
        "lines": conn.execute("SELECT COUNT(*) FROM org_lines").fetchone()[0],
        "money": conn.execute("SELECT COUNT(*) FROM org_money").fetchone()[0],
        "agenda": conn.execute("SELECT COUNT(*) FROM org_agenda").fetchone()[0],
        "incidents": conn.execute("SELECT COUNT(*) FROM org_incidents").fetchone()[0],
        "arr": conn.execute("SELECT COUNT(*) FROM org_arrangements").fetchone()[0],
        "sums": {k: float(conn.execute("SELECT COALESCE(SUM(amount),0) FROM org_money WHERE kind=?", (k,)).fetchone()[0]) for k in KINDS},
        "ranks": sorted((r[0], r[1], r[2]) for r in conn.execute("SELECT actor_id,role_key,inducted_day FROM org_seats")),
        "weekly": float(conn.execute("SELECT SUM(weekly_usd) FROM org_arrangements").fetchone()[0]),
    }
    assert after == before, (before, after)
    # org_actor_id: the payer's seat organisation, else the payee's; the bagman-to-officer Pad row takes the arrangement's payer
    by = {(r["kind"], r["from_actor_id"], r["to_actor_id"]): r["org_actor_id"] for r in conn.execute("SELECT * FROM org_money")}
    assert by[("take", None, people[1])] == fam_id and by[("take", None, people[5])] == club_id
    assert by[("kickup", people[2], people[1])] == fam_id and by[("pad", people[1], bagman)] == fam_id
    assert by[("pad", bagman, officer)] == fam_id
    assert conn.execute("SELECT COUNT(*) FROM org_money WHERE org_actor_id IS NULL").fetchone()[0] == 0
    # arrangements: envelopes paid by an organisation, officer/bagman renamed
    rows = conn.execute("SELECT * FROM org_arrangements ORDER BY id").fetchall()
    assert all(r["kind"] == "envelope" and r["payer_kind"] == "org" and r["payer_id"] == fam_id and r["go_between_actor_id"] == bagman for r in rows)
    assert rows[0]["official_actor_id"] == officer
    # units and lines keep their ids and links; incident keeps its raised-to organisation
    assert conn.execute("SELECT COUNT(*) FROM org_lines l JOIN org_units u ON u.id=l.unit_id JOIN org_holdings h ON h.id=l.holding_id").fetchone()[0] == 3
    assert conn.execute("SELECT raised_to_org_actor_id FROM org_incidents").fetchone()[0] == fam_id
    # one profile per outfit institution, sphere underworld, kind = its shape
    profiles = {r["org_actor_id"]: (r["org_kind"], r["sphere"], r["package_key"]) for r in conn.execute("SELECT * FROM org_profiles")}
    assert profiles[fam_id] == ("family", "underworld", "sabatini") and profiles[club_id] == ("club", "underworld", "horsemen"), profiles
    assert len(profiles) == 2
    conn.close()


def test_caerness_migration_writes_no_profiles():
    conn = fresh_db()
    assert conn.execute("SELECT COUNT(*) FROM org_profiles").fetchone()[0] == 0
    conn.close()


def run():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"FAIL {name}: {exc!r}")
            import traceback
            traceback.print_exc()
    unexpected = [n for n in failed if n not in EXPECTED_FAILURES]
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(run())
