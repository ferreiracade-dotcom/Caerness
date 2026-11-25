"""P2: a newborn never gets a number in their name, and a save's epithet and numbered names are repaired wherever they are
stored, keeping the given name; a station called by its number stays."""
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
            two = conn.execute("SELECT id,name FROM actors WHERE actor_type='character' AND name NOT LIKE '% % %' ORDER BY id LIMIT 3").fetchall()
            (a, an), (b, bn), (f, fn) = [(int(r[0]), r[1]) for r in two]

            # every given name of the family taken: a middle initial, never a number
            given, family = an.split()
            demographic_sex.package_given_pool = lambda c, sex, fam=None: [given]
            got = household_life._newborn_name(conn, a, b, "male", "birth:1:908:10:1")
            assert not re.search(r"\d", got) and got != an and got.endswith(family), got

            conn.execute("UPDATE actors SET name=? WHERE id=?", (f"{an} the Thin", a))
            conn.execute("UPDATE actors SET name=? WHERE id=?", (f"{bn} 908", b))
            conn.execute("UPDATE actors SET name=? WHERE id=?", (f"{bn.split()[0]} X. {bn.split()[1]}", f))
            ev = conn.execute("INSERT INTO events(day,event_type,title,summary) VALUES (1,'life:birth',?,?)",
                              (f"Birth: {bn} 908", f"{an} the Thin saw {bn} 908.")).lastrowid
            shop = conn.execute("SELECT id FROM civilian_enterprises WHERE owner_actor_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0]
            conn.execute("UPDATE civilian_enterprises SET name='Redhand''s Bar',owner_actor_id=? WHERE id=?", (a, shop))
            conn.execute("UPDATE events SET summary=summary||' At Redhand''s Bar.' WHERE id=?", (ev,))
            station = conn.execute("SELECT name FROM actors WHERE name='Channel 4'").fetchone()

            changed = name_repair.repair_names(conn)
            assert len(changed) >= 2
            na, nb = [conn.execute("SELECT name FROM actors WHERE id=?", (i,)).fetchone()[0] for i in (a, b)]
            assert na.startswith(an.split()[0]) and "the Thin" not in na, na
            assert nb.startswith(bn.split()[0]) and not re.search(r"\d", nb), nb
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
