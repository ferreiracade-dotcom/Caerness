"""S1: who is rising, and the coarse clock for everyone who is not.

Background upkeep that only integrates elapsed time (careers, household stage and money, enterprise accounts, planned births,
courtship contacts) does not need to run for every person every day. A *quiet* person's rows are brought up to date every
BATCH_DAYS on the row's own stamp (the load spreads, and every scan already integrates `elapsed`, so no time is lost). A *rising*
person's rows stay on the daily clock.

Who is rising is read from live state, never from where anyone is or how far he is from the player: a seat in an organisation, a
party to a venture, the owner of an enterprise, a candidate in an open race, an office holder, a person who owes or is owed on a
standing agreement, a person harmed in the last month, a person forced to a faster tier. Because it is derived at the moment a scan
runs, a man who gains any of these is on the daily clock the next time the scan runs: nobody has to call anything to promote him.

`CAERNESS_TIERS=off` makes everyone rising (the all-full-tier baseline used by the equivalence tests).
"""
from __future__ import annotations

import os
import sqlite3

BATCH_DAYS = 7
RECENT_HARM_DAYS = 30


def enabled(conn: sqlite3.Connection | None = None) -> bool:
    return os.environ.get("CAERNESS_TIERS", "on").strip().lower() not in ("off", "0", "false")


def _ids(conn: sqlite3.Connection, sql: str, *args) -> set[int]:
    try:
        return {int(r[0]) for r in conn.execute(sql, args).fetchall() if r[0] is not None}
    except sqlite3.OperationalError:  # a database made before the layer that owns the table
        return set()


def _compute(conn: sqlite3.Connection, day: int) -> frozenset[int]:
    out: set[int] = set()
    out |= _ids(conn, "SELECT actor_id FROM org_seats WHERE status IN ('active','held')")
    out |= _ids(conn, "SELECT CAST(substr(party_ref,8) AS INTEGER) FROM venture_parties vp JOIN civilian_projects p ON p.id=vp.project_id "
                      "WHERE vp.party_ref LIKE 'person:%' AND p.status='active'")
    out |= _ids(conn, "SELECT owner_actor_id FROM civilian_enterprises WHERE status IN ('active','strained','insolvent') AND owner_actor_id IS NOT NULL")
    out |= _ids(conn, "SELECT actor_id FROM race_candidates rc JOIN races r ON r.id=rc.race_id WHERE r.status='open' AND rc.dropped_day IS NULL")
    out |= _ids(conn, "SELECT actor_id FROM office_terms WHERE end_day IS NULL")
    out |= _ids(conn, "SELECT CAST(substr(debtor_ref,8) AS INTEGER) FROM agreement_terms WHERE status IN ('active','breached') AND debtor_ref LIKE 'person:%' AND (missed_count>0 OR owed_usd>0)")
    out |= _ids(conn, "SELECT actor_id FROM harm_incidents WHERE day>=?", day - RECENT_HARM_DAYS)
    out |= _ids(conn, "SELECT actor_id FROM simulation_profiles WHERE forced_tier IS NOT NULL AND COALESCE(forced_until_day,0)>=?", day)
    return frozenset(out)


def rising_actor_ids(conn: sqlite3.Connection, day: int) -> frozenset[int]:
    """The people on the daily clock today. Computed once per simulated day inside a time skip."""
    from .world_package import pass_memo
    return pass_memo(conn, f"rising:{int(day)}", lambda: _compute(conn, int(day)))


def is_rising(conn: sqlite3.Connection, actor_id: int, day: int) -> bool:
    return (not enabled(conn)) or int(actor_id) in rising_actor_ids(conn, day)


def sql_ids(conn: sqlite3.Connection, day: int) -> str:
    """The rising ids as a SQL list literal, for `... OR actor_id IN (<list>)`. With tiers off the caller must not filter at all
    (see `batching(conn)`)."""
    ids = sorted(rising_actor_ids(conn, day))
    return ",".join(str(i) for i in ids) if ids else "NULL"


def batching(conn: sqlite3.Connection) -> bool:
    """True when quiet people's rows may wait for their batch day."""
    return enabled(conn)
