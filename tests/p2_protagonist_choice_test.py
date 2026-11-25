"""P2: the engine never marries the protagonist, moves them to another organisation or seats them: those are choices
made in play. Another person in the same spot is still chosen."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "play.db"
        shutil.copyfile(build_saintjude(Path(tmp)), db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine import opening_family, org_dealings, org_membership, player, prison
        from engine.db import connect

        with connect() as conn:
            day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            grid = (day // 30 + 1) * 30

            # marriage into the unnamed population: two single adults, both certain to marry; only the other one does
            rows = opening_family._person_rows(conn, grid)
            single = [r for r in rows if 22 <= (grid - r["birth_day"]) / 365 <= 35 and not conn.execute(
                "SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)", (r["id"], r["id"])).fetchone()
                and "canon_partial" not in (r["metadata_json"] or "")][:2]
            me, other = int(single[0]["id"]), int(single[1]["id"])
            player.set_player(conn, me)
            opening_family._person_rows = lambda c, d: single
            opening_family.first_marriage_hazard = lambda age, curve: 1.0
            assert opening_family.resolve_unnamed_marriages(conn, grid) == 1
            married = {int(r[0]) for r in conn.execute("SELECT actor_a_id FROM household_unions WHERE status='active' UNION "
                                                       "SELECT actor_b_id FROM household_unions WHERE status='active'")}
            assert other in married and me not in married, (me, other)

            # a dependant who could be put forward is not, once they are the protagonist
            found = None
            for r in conn.execute("SELECT DISTINCT org_actor_id,unit_id FROM org_seats WHERE status='active' AND unit_id IS NOT NULL").fetchall():
                men = org_membership.eligible(conn, r[0], r[1], day)
                if men:
                    found = (int(r[0]), int(r[1]), men[0])
                    break
            org, unit, man = found
            player.set_player(conn, man)
            assert man not in org_membership.eligible(conn, org, unit, day)

            # nor is the protagonist moved to another organisation
            new = next(int(o[0]) for o in conn.execute("SELECT DISTINCT org_actor_id FROM org_seats WHERE org_actor_id<>?", (org,))
                       if org_dealings.dependent_role(conn, int(o[0])))
            assert org_dealings.change_side(conn, man, org, new, "poached", day) is False
            assert org_dealings.change_side(conn, org_membership.eligible(conn, org, unit, day)[0] if org_membership.eligible(
                conn, org, unit, day) else int(conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND actor_id<>?",
                                                            (org, man)).fetchone()[0]), org, new, "poached", day) is True

            # nor seated in a group on being held
            group = conn.execute("SELECT id,org_actor_id FROM facility_groups ORDER BY id LIMIT 1").fetchone()
            if group is not None:
                player.set_player(conn, me)
                prison._seat_inside(conn, me, group[0], day)
                assert not conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND org_actor_id=?", (me, group[1])).fetchone()
            conn.rollback()
    print("PASS p2_protagonist_choice_test")


if __name__ == "__main__":
    main()
