"""B1: everybody has a body. It is drawn from the package's norms, a child takes after both parents, work builds it and
drink wears it down, injuries show, what was said about somebody stands, and in a fight it weighs on the odds without
deciding them. The protagonist is measured like anybody else.

Run: PYTHONPATH=. python tests/b1_physique_test.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs)


def today(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def men(conn, low: int, high: int) -> list[int]:
    day = today(conn)
    return [int(r[0]) for r in conn.execute(
        """SELECT l.actor_id FROM actor_life_profiles l WHERE l.life_status='living' AND l.demographic_sex='male'
           AND l.birth_day BETWEEN ? AND ? ORDER BY l.actor_id""", (day - int(high * 365.25), day - int(low * 365.25)))]


def drawn(conn, physique) -> None:
    living = conn.execute("""SELECT COUNT(*) FROM actor_life_profiles WHERE life_status='living' AND birth_day IS NOT NULL
                             AND demographic_sex IN ('female','male')""").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM physical_records").fetchone()[0] == living > 1000
    young = [physique._body(conn, a) for a in men(conn, 20, 45)]
    height, weight = mean(b["height"] for b in young), mean(b["weight"] for b in young)
    assert 67.5 < height < 70.5 and 160 < weight < 190, (height, weight)
    by_load: dict[bool, list] = {True: [], False: []}
    for b in young:
        by_load[float(json.loads(b["rec"]["work_json"]).get("load", 0)) >= 0.5].append(b)
    assert by_load[True] and by_load[False]
    hard, light = mean(b["strength"] for b in by_load[True]), mean(b["strength"] for b in by_load[False])
    assert hard > light * 1.08, (hard, light)
    day = today(conn)
    women = [physique._body(conn, int(r[0])) for r in conn.execute(
        """SELECT actor_id FROM actor_life_profiles WHERE life_status='living' AND demographic_sex='female'
           AND birth_day BETWEEN ? AND ? ORDER BY actor_id""", (day - int(45 * 365.25), day - int(20 * 365.25)))]
    assert height - mean(b["height"] for b in women) > 3.5
    print(f"{living} bodies; men 20-45 {height:.1f} in {weight:.0f} lb; strength hard work {hard:.2f} light {light:.2f}")


def born(conn, physique, father: int, mother: int) -> None:
    """Children born later get their bodies at the weekly pass, and take after both parents."""
    for parent in (father, mother):
        conn.execute("UPDATE physical_records SET height_z=2.5, frame=-2.0 WHERE actor_id=?", (parent,))
    day = today(conn)
    children = []
    for i in range(60):
        child = conn.execute("INSERT INTO actors(name,actor_type) VALUES (?,'character')", (f"Child{i} Testperson",)).lastrowid
        conn.execute("""INSERT INTO actor_life_profiles(actor_id,birth_day,demographic_sex,life_stage) VALUES (?,?,?,'infant')""",
                     (child, day - i, "male" if i % 2 else "female"))
        for parent in (father, mother):
            conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,started_day) VALUES (?,?,'parent',?)",
                         (parent, child, day - i))
        children.append(int(child))
    assert physique.weekly(conn, day)["bodies_added"] == len(children)
    marks = ",".join("?" * len(children))
    tall, frame = conn.execute(f"SELECT AVG(height_z), AVG(frame) FROM physical_records WHERE actor_id IN ({marks})", children).fetchone()
    assert tall > 1.4 and frame < -1.0, (tall, frame)
    infant = physique.appearance(conn, children[0])
    assert "strength" not in infant and "looks" not in infant, infant
    print(f"children of tall slight parents: height {tall:.2f} sd, frame {frame:.2f} sd")


def reads_do_not_write(conn, physique, who: int) -> None:
    conn.execute("DELETE FROM physical_records WHERE actor_id=?", (who,))
    before = conn.total_changes
    seen = physique.appearance(conn, who)
    assert seen and seen["line"] and physique.describe(conn, who) == seen["line"]
    assert physique.force(conn, who) > 0 and conn.total_changes == before
    physique.ensure(conn, who)
    assert physique.describe(conn, who) == seen["line"], "the saved record is the one that was shown"


def lived(conn, physique, who: int) -> None:
    start = today(conn)
    conn.execute("DELETE FROM enterprise_staff WHERE actor_id=?", (who,))
    conn.execute("DELETE FROM background_person_profiles WHERE actor_id=?", (who,))
    conn.execute("UPDATE actors SET subtype='accounts clerk', notes=NULL WHERE id=?", (who,))
    conn.execute("DELETE FROM physical_records WHERE actor_id=?", (who,))
    physique.ensure(conn, who)

    def pass_years(years: float) -> tuple[float, float]:
        for _ in range(int(years * 4)):
            now = today(conn) + 91
            conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (now,))
            physique.weekly(conn, now)
        b = physique._body(conn, who)
        return float(b["rec"]["muscle"]), b["strength"]

    desk = pass_years(1)
    conn.execute("UPDATE actors SET subtype='dock worker on the piers' WHERE id=?", (who,))
    docks = pass_years(3)
    words = physique.appearance(conn, who)
    assert docks[0] > desk[0] + 0.6 and docks[1] > desk[1] * 1.08, (desk, docks)
    assert "dock" in words["build"], words
    conn.execute("""INSERT INTO dependency_profiles(actor_id,dependency_kind,status,functional_impairment,last_review_day,next_review_day)
                    VALUES (?,'intoxicant','dependent',60,?,?)""", (who, today(conn), today(conn) + 30))
    drinking = pass_years(3)
    conn.execute("UPDATE actors SET subtype='accounts clerk' WHERE id=?", (who,))
    after = pass_years(6)
    assert after[0] < drinking[0] < docks[0] and after[1] < drinking[1] < docks[1], (docks, drinking, after)
    print(f"muscle desk {desk[0]:.2f}, docks {docks[0]:.2f}, drinking {drinking[0]:.2f}, desk again {after[0]:.2f}")
    conn.execute("DELETE FROM dependency_profiles WHERE actor_id=?", (who,))
    conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (start,))


def injury_shows(conn, physique, who: int) -> None:
    from engine.harm import record_harm
    before = physique.force(conn, who)
    record_harm(conn, who, source_kind="b1_test", source_ref_id=1, severity=60, method="blade", outcome_override="persistent")
    seen = physique.appearance(conn, who)
    marks = " ".join(seen["marks"])
    assert "knife scar" in marks and "healing knife cut" in seen["line"], seen
    assert physique.force(conn, who) < before, "an injury still healing takes strength"


def switched_off(conn, physique, a: int, b: int) -> None:
    os.environ["CAERNESS_PHYSIQUE"] = "off"
    try:
        assert physique.describe(conn, a) is None and physique.appearance(conn, a) is None
        assert (physique.odds(conn, a, b), physique.blow(conn, a, b, "fists"), physique.standoff(conn, a, b),
                physique.capacity_factor(conn, a)) == (0.5, 1.0, 1.0, 1.0)
        assert physique.seed_all(conn) == 0 and physique.weekly(conn, today(conn) + 400) == {}
        assert not physique.apply_note(conn, "actor", a, "Appearance: tall")
    finally:
        del os.environ["CAERNESS_PHYSIQUE"]


def through_the_connector(tmp: str) -> None:
    """The GM sees bodies in plain words, and what the story says about somebody is what stays."""
    os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    base = build_saintjude(Path(tmp))
    from connector import campaign, server
    campaign._packaged_db = lambda pkg_id: base
    campaign.open_campaign("b1", package="saintjude")
    proposal = {"name": "Danny Ruane", "sex": "male", "age": 28, "place": "Kerrytown", "work": "mechanic at a family garage",
                "concept": "a 28-year-old Kerrytown mechanic", "draw": 0, "appearance": "6'2\", red hair, a broken nose"}
    draft = server.author("b1-1", "protagonist", proposal)
    assert draft["status"] == "draft" and draft["appearance"]["height"] == "about 6'2\"", draft
    made = server.author("b1-2", "protagonist", {**proposal, "accept": True})
    assert made["status"] == "created" and made["appearance"]["line"] == draft["appearance"]["line"], (draft, made)
    me = int(made["actor_id"])
    scene = server.scene()
    assert "red hair" in scene["protagonist"]["looks"], scene["protagonist"]
    assert scene["present"] and all(p.get("looks") for p in scene["present"]), scene["present"]
    other = int(scene["present"][0]["id"])
    seen = server.lookup(str(other))["appearance"]
    assert seen["line"] == scene["present"][0]["looks"] and seen.get("against_you"), seen
    noted = server.note("b1-3", "Short and heavyset, dark-haired, very good looking.", subject_kind="actor", subject_id=other,
                        field="appearance")
    after = server.lookup(str(other))["appearance"]
    assert noted["appearance"] == after["line"] and "heavyset" in after["line"] and after["line"] != seen["line"], (noted, after)
    plain = server.note("b1-4", "Owes the garage for a clutch.", subject_kind="actor", subject_id=other)
    assert "appearance" not in plain and server.lookup(str(other))["appearance"] == after, plain
    server.note("b1-5", "Tall and wiry, with a scar over one eye.", kind="sheet", field="appearance")
    mine = server.lookup(str(me))["appearance"]["line"]
    assert "wiry" in mine and "scar over one eye" in mine, mine
    new = server.author("b1-6", "person", {"name": "Rita Calloway", "age": 24, "sex": "female", "work": "waitress",
                                           "appearance": "tiny, platinum blonde"})
    assert new.get("actor_id") and "platinum blonde" in new["appearance"], new
    print(f"connector: {scene['protagonist']['looks']} | {after['line']} | {new['appearance']}")


def older_save(db: Path, tmp: str, who: int) -> None:
    from engine import db as engine_db, physique
    conn = connect(db)
    conn.executescript((ROOT / "connector" / "schema.sql").read_text(encoding="utf-8"))
    conn.execute("DROP TABLE physical_records")
    conn.execute("""INSERT INTO gm_notes(subject_kind,subject_id,text,world_day,call_id)
                    VALUES ('actor',?,'Appearance: 6''3", broad-shouldered, a scar along the jaw.',0,'t')""", (who,))
    conn.execute("UPDATE engine_meta SET value='132' WHERE key='schema_version'")
    conn.execute("DELETE FROM schema_migrations WHERE version>=133")
    conn.commit()
    conn.close()
    os.environ["CAERNESS_TEST_MODE"] = "1"
    os.environ["CAERNESS_BACKUP_DIR"] = str(Path(tmp) / "backups")
    engine_db.init_db()
    conn = connect(db)
    try:
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == engine_db.SCHEMA_VERSION
        assert conn.execute("SELECT COUNT(*) FROM physical_records").fetchone()[0] > 1000
        seen = physique.appearance(conn, who)
        assert seen["height"] == "about 6'3\"" and "scar along the jaw" in seen["line"] and "build" not in seen, seen
    finally:
        conn.close()


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = build_saintjude(Path(tmp))
        os.environ["CAERNESS_DB_PATH"] = str(db)
        os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
        conn = connect(db)
        try:
            from engine import physique
            drawn(conn, physique)
            a, b, c = men(conn, 22, 30)[:3]
            woman = int(conn.execute("""SELECT actor_id FROM actor_life_profiles WHERE life_status='living'
                                        AND demographic_sex='female' AND birth_day<? ORDER BY actor_id""",
                                     (today(conn) - int(25 * 365.25),)).fetchone()[0])
            born(conn, physique, c, woman)
            reads_do_not_write(conn, physique, a)
            lived(conn, physique, b)
            injury_shows(conn, physique, c)
            switched_off(conn, physique, a, b)
            conn.commit()
        finally:
            conn.close()
        older_save(db, tmp, a)
        through_the_connector(tmp)
    print("PASS b1_physique_test")


if __name__ == "__main__":
    main()
