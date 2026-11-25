"""P2: a newborn never gets a number in their name, and a save's epithet, numbered and initialled names are repaired
wherever they are stored, keeping the family name; a station called by its number stays."""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tests.sj_fixture import build_saintjude  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "play.db"
        shutil.copyfile(build_saintjude(Path(tmp)), db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        import leak_scan
        from engine import demographic_sex, household_life, name_repair
        from engine.db import connect

        with connect() as conn:
            two = conn.execute("SELECT id,name FROM actors WHERE actor_type='character' AND name NOT LIKE '% % %' ORDER BY id LIMIT 4").fetchall()
            (a, an), (b, bn), (f, fn), (g, gn) = [(int(r[0]), r[1]) for r in two]

            # every given name of the family taken: a middle initial, never a number
            given, family = an.split()
            pool = demographic_sex.package_given_pool
            demographic_sex.package_given_pool = lambda c, sex, fam=None: [given]
            got = household_life._newborn_name(conn, a, b, "male", "birth:1:908:10:1")
            demographic_sex.package_given_pool = pool
            assert not re.search(r"\d", got) and got != an and got.endswith(family), got

            conn.execute("UPDATE actors SET name=? WHERE id=?", (f"{an} the Thin", a))
            conn.execute("UPDATE actors SET name=? WHERE id=?", (f"{bn} 908", b))
            conn.execute("UPDATE actors SET name=? WHERE id=?", (f"{bn.split()[0]} X. {bn.split()[1]}", f))
            conn.execute("UPDATE actors SET name=? WHERE id=?", (f"{an} the Tall", g))  # two who strip to one name
            ev = conn.execute("INSERT INTO events(day,event_type,title,summary) VALUES (1,'life:birth',?,?)",
                              (f"Birth: {bn} 908", f"{an} the Thin saw {bn} 908.")).lastrowid
            shop = conn.execute("SELECT id FROM civilian_enterprises WHERE owner_actor_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0]
            conn.execute("UPDATE civilian_enterprises SET name='Redhand''s Bar',owner_actor_id=? WHERE id=?", (a, shop))
            conn.execute("UPDATE events SET summary=summary||' At Redhand''s Bar.' WHERE id=?", (ev,))
            station = conn.execute("SELECT name FROM actors WHERE name='Channel 4'").fetchone()

            crowd = conn.execute("""SELECT a.id,a.name FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                                    WHERE a.actor_type='character' AND a.name NOT LIKE '% % %' AND a.id NOT IN (?,?,?,?)
                                    ORDER BY a.id LIMIT 2""", (a, b, f, g)).fetchall()
            (h, hn), (i, _) = [(int(r[0]), r[1]) for r in crowd]
            conn.execute("UPDATE actors SET name=? WHERE id=?", (f"{hn} the Dark", i))  # the usual names all borne
            demographic_sex.package_given_pool = lambda c, sex, fam=None: [hn.split()[0]]

            # somebody the player named for his life keeps that name, initial and all
            j, jn = [(int(r[0]), r[1]) for r in conn.execute(
                """SELECT id,name FROM actors WHERE actor_type='character' AND name NOT LIKE '% % %' AND id>? ORDER BY id LIMIT 2""",
                (i,)).fetchall()][0]
            k = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND name NOT LIKE '% % %' AND id>? ORDER BY id LIMIT 1",
                                 (j,)).fetchone()[0])
            kept = f"{jn.split()[0]} Q. {jn.split()[1]}"
            conn.execute("UPDATE actors SET name=? WHERE id=?", (kept, k))
            conn.execute("""INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day)
                            VALUES (?,?,'a tie',1.0,1)""", (a, f"lived:tie:{a}:{k}"))

            changed = name_repair.repair_names(conn)
            assert conn.execute("SELECT name FROM actors WHERE id=?", (k,)).fetchone()[0] == kept
            demographic_sex.package_given_pool = pool
            assert len(changed) >= 2
            ni = conn.execute("SELECT name FROM actors WHERE id=?", (i,)).fetchone()[0]
            assert ni != hn and re.fullmatch(r"\S+ " + re.escape(hn.split()[-1]), ni), (ni, hn)
            assert not [n for n in changed.values() if re.search(r" [A-Z]\. ", n)], changed
            na, nb = [conn.execute("SELECT name FROM actors WHERE id=?", (i,)).fetchone()[0] for i in (a, b)]
            assert na.startswith(an.split()[0]) and "the Thin" not in na, na
            assert nb.startswith(bn.split()[0]) and not re.search(r"\d", nb), nb
            nf, ng = [conn.execute("SELECT name FROM actors WHERE id=?", (i,)).fetchone()[0] for i in (f, g)]
            for new, base in ((nf, bn), (ng, an)):  # another given name, the family name kept, no initial
                assert re.fullmatch(r"\S+ " + re.escape(base.split()[-1]), new) and new != base, (new, base)
            assert len({na, nb, nf, ng}) == 4
            title, summary = conn.execute("SELECT title,summary FROM events WHERE id=?", (ev,)).fetchone()
            bar = f"{an.split()[-1]}'s Bar"
            assert title == f"Birth: {nb}" and summary == f"{na} saw {nb}. At {bar}.", (title, summary)
            assert conn.execute("SELECT name FROM civilian_enterprises WHERE id=?", (shop,)).fetchone()[0] == bar
            assert conn.execute("SELECT name FROM actors WHERE name='Channel 4'").fetchone() == station
            assert not name_repair.repair_names(conn), "a second repair changed something"
            names = [r[0] for r in conn.execute("SELECT name FROM actors WHERE actor_type='character' UNION ALL SELECT name FROM civilian_enterprises")]
            bad = [(n, h) for n in names for h in leak_scan.find_hits(n) if h[0] in ("epithet name", "fantasy epithet")]
            assert not bad, bad[:10]

        # the scan itself sees both kinds of spoiled name
        small = Path(tmp) / "small.db"
        c = sqlite3.connect(small)
        c.executescript("CREATE TABLE actors(name TEXT, actor_type TEXT, id INTEGER PRIMARY KEY);"
                        "INSERT INTO actors(name,actor_type) VALUES ('Ann Lee 12','character'),('Ann Lee the Thin','character'),"
                        "('Station 4','institution');")
        c.commit()
        c.close()
        seen = sorted(k.matched for k in leak_scan.scan(small))
        assert seen == ["epithet name", "numbered name"], seen
    print("PASS p2_name_repair_test")


if __name__ == "__main__":
    main()
