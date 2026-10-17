"""Give an existing protagonist a fresh lived past (gap 5, Task 5b): family, origin kin, ties, competence, knowledge, memories and standing.

For a campaign whose protagonist was made before the new-character work (Ansel Fane): his outfit, businesses, household and every
existing row stay as they are; the past is insert-only and a second run adds nothing.

    python tools/give_lived_past.py --campaign ansel            # dry run on a copy; prints a short digest
    python tools/give_lived_past.py --campaign ansel --apply    # backup + integrity_check first, then writes to the campaign

On the server, run it after deploying migration 115. Never run on the server from a development session.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def give_lived_past(conn: sqlite3.Connection) -> dict:
    """Run the lived past for the current protagonist of an open campaign connection. Does not commit."""
    from engine import new_character as nc
    from engine import veto
    from engine.player import get_player

    p = get_player(conn)
    if not p:
        raise SystemExit("the campaign has no protagonist")
    me = int(p["player_actor_id"])
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    prof = conn.execute("SELECT occupation_domain FROM background_person_profiles WHERE actor_id=?", (me,)).fetchone()
    cat = str(prof[0]) if prof and prof[0] else veto.categorise(conn.execute("SELECT COALESCE(subtype,'') FROM actors WHERE id=?", (me,)).fetchone()[0])
    boss = conn.execute("SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active' ORDER BY authority DESC LIMIT 1", (me,)).fetchone()
    aff = {"kind": "outfit", "id": int(boss[0])} if boss else None
    owned = int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained')", (me,)).fetchone()[0])
    # the people who work for him already: business managers and the household's staff
    also = [int(r[0]) for r in conn.execute(
        """SELECT s.actor_id FROM enterprise_staff s JOIN civilian_enterprises e ON e.id=s.enterprise_id WHERE e.owner_actor_id=? AND s.actor_id<>?
           AND s.status='active' ORDER BY s.authority DESC, s.actor_id LIMIT 3""", (me, me))]
    also += [int(r[0]) for r in conn.execute(
        """SELECT t.actor_id FROM household_service_terms t JOIN households h ON h.id=t.household_id WHERE h.head_actor_id=? AND t.status='active'
           ORDER BY (t.service_role='steward') DESC, t.actor_id LIMIT 3""", (me,))]
    proposal = {"work": cat, "category": cat, "_affiliation": aff, "_holds": owned + (2 if boss else 0), "_ties_with": also}
    return nc.fill_lived_past(conn, me, key=f"lived:{seed}:{me}", proposal=proposal)


def _campaign_path(name: str) -> Path:
    from connector.campaign import campaign_dir
    path = campaign_dir() / f"{name}.db"
    if not path.exists():
        raise SystemExit(f"no campaign file {path}")
    return path


def _digest(conn: sqlite3.Connection, before: dict, result: dict) -> str:
    after = _counts(conn)
    lines = [f"{k}: +{after[k] - before[k]}" for k in before if after[k] != before[k]]
    return f"lived past {'already given' if result.get('already') else 'given'}: " + (", ".join(lines) if lines else "nothing added")


def _counts(conn: sqlite3.Connection) -> dict:
    return {t: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in
            ("actors", "kinship_links", "relationships", "knowledge", "actor_memories", "household_members", "teaching_relationships")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--apply", action="store_true", help="write to the campaign (after a verified backup); default is a dry run on a copy")
    a = ap.parse_args()
    src = _campaign_path(a.campaign)
    target = src
    tmp = None
    if a.apply:
        from connector.backup import copy_consistent
        from connector.campaign import campaign_dir
        from connector.settings import Settings
        bdir = Settings.from_env().backup_dir or (campaign_dir() / "backups")
        bdir.mkdir(parents=True, exist_ok=True)
        dest = bdir / f"{a.campaign}.pre-livedpast-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db"
        copy_consistent(src, dest)  # online backup API, then integrity_check of the copy; raises on any failure
        print(f"backup: {dest}", file=sys.stderr)
    else:
        tmp = Path(tempfile.mkdtemp())
        target = tmp / src.name
        shutil.copy2(src, target)
        print("dry run on a copy; nothing is written to the campaign", file=sys.stderr)
    os.environ["CAERNESS_DB_PATH"] = str(target)
    from engine.db import connect, init_db
    init_db()
    conn = connect()
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        before = _counts(conn)
        result = give_lived_past(conn)
        conn.commit()
        print(_digest(conn, before, result))
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("integrity_check failed after the run")
    finally:
        conn.close()
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
