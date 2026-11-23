"""The races of the opening year: every elected office whose election falls inside the opening window gets its race, and the people who
would by their own driver already have declared are on the ballot.

Nothing is invented here. `races.schedule` opens a race exactly as the civic clock does on the first day of a run (so the clock finds it and
does not open a second); `races.consider_filing` is the run's own weighed filing choice (standing, backing, incumbency), applied on the
opening day to those the office's pool would put up, and a person it says yes to files early. Whoever it says no to is weighed again at the
close of filing, as in every race. The protagonist is never filed (races.pool_for leaves him out). No world words: the offices, dates and
drivers are the package's politics data.
"""
from __future__ import annotations

import sqlite3

from . import races
from .world_package import package_for, politics_rules


def build(conn: sqlite3.Connection) -> dict[str, int]:
    if not (politics_rules(package_for(conn)) or {}).get("offices"):
        return {}
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    opened = races.schedule(conn, day)
    filed = 0
    for r in conn.execute("SELECT id FROM races WHERE status='open' AND stage='filing' ORDER BY id").fetchall():
        rid = int(r["id"])
        for a in races.pool(conn, rid):
            if races.consider_filing(conn, a, rid, day):
                filed += 1
    return {"races": opened, "declared": filed}
