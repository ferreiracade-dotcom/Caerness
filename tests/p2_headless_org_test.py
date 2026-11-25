"""P2.22: when an organisation's head goes and no one the data names can stand or succeed (a small splinter group), the best
member left takes the seat, so nobody is left answering to a dead man.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        import os
        db = build_saintjude(Path(tmp))
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine import org_lifecycle, orgs
        from engine.db import connect

        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]) + 1
            org = int(conn.execute("SELECT org_actor_id FROM org_profiles WHERE org_kind='party' ORDER BY org_actor_id LIMIT 1").fetchone()[0])
            head = orgs.head_of(conn, org)
            rules = orgs.kind_rules(conn, org)
            plain = "committeeman"
            # a splinter group: its head, committeemen and workers; nobody in a role the succession or the contest names,
            # and the head himself ran the one ward organisation
            conn.execute("DELETE FROM org_seats WHERE org_actor_id=? AND role_key IN ('treasurer',?)", (org, rules["unit_leader"]))
            conn.execute("UPDATE org_units SET leader_actor_id=? WHERE org_actor_id=?", (head, org))
            men = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active'", (org, plain))]
            assert men, "the party has no committeemen to test with"
            conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND status='active' AND actor_id<>?", (head, org, head))
            conn.execute("UPDATE actors SET status='deceased' WHERE id=?", (head,))
            conn.execute("UPDATE actor_life_profiles SET life_status='deceased' WHERE actor_id=?", (head,))
            org_lifecycle.process_due(conn, day)
            new = orgs.head_of(conn, org)
            assert new is not None and new != head and orgs.is_living(conn, new), new
            bad = conn.execute("""SELECT s.actor_id,s.role_key,s.superior_actor_id FROM org_seats s WHERE s.org_actor_id=? AND s.status='active'
                                  AND s.actor_id<>? AND NOT EXISTS (SELECT 1 FROM org_seats t WHERE t.actor_id=s.superior_actor_id
                                  AND t.org_actor_id=s.org_actor_id AND t.status IN ('active','held'))""", (org, new)).fetchall()
            assert not bad, [tuple(r) for r in bad][:5]
    print("PASS p2_headless_org_test")


if __name__ == "__main__":
    main()
