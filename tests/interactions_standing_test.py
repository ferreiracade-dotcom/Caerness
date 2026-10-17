from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "istanding.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine import interactions as it
        from engine.relationships import ensure_relationship

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            plain = [int(r[0]) for r in conn.execute(
                """SELECT a.id FROM actors a WHERE a.actor_type='character' AND a.status NOT IN ('deceased','dead')
                   AND NOT EXISTS (SELECT 1 FROM kinship_links k WHERE a.id IN (k.actor_a_id,k.actor_b_id))
                   AND NOT EXISTS (SELECT 1 FROM household_members h WHERE h.actor_id=a.id)
                   AND NOT EXISTS (SELECT 1 FROM actor_drives d WHERE d.actor_id=a.id)
                   ORDER BY a.id LIMIT 6""")]
            parent, child, stranger, servant, boss = plain[0], plain[1], plain[2], plain[3], plain[4]
            conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?, 'parent','recognized',0)", (parent, child))
            conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?, 'child','recognized',0)", (child, parent))
            conn.execute("INSERT INTO households(id,name,head_actor_id,status,wealth,liquidity,staff_capacity,cohesion,hospitality,created_day,updated_day) "
                         "VALUES (900001,'Test House',?, 'active',50,50,50,50,50,0,0)", (boss,))
            conn.execute("INSERT INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status) VALUES (900001,?, 'head',90,0,0,'active')", (boss,))
            conn.execute("INSERT INTO household_service_terms(household_id,actor_id,service_role,start_day,review_day,loyalty,satisfaction,renewal_bias,status) "
                         "VALUES (900001,?, 'servant',0,365,60,60,0,'active')", (servant,))

            def meters(a_to_b: dict, b_to_a: dict, a: int, b: int):
                conn.execute("DELETE FROM relationships WHERE (actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)", (a, b, b, a))
                ensure_relationship(conn, a, b, day, **a_to_b)
                ensure_relationship(conn, b, a, day, **b_to_a)

            counter = [6000000]

            def rate(proposer, recipient, kind, terms, n=200):
                ok = 0
                for _ in range(n):
                    counter[0] += 1
                    conn.execute("SAVEPOINT r")
                    conn.execute(
                        """INSERT INTO interactions(id,created_day,proposer_actor_id,recipient_actor_id,interaction_type,status,
                               urgency,stakes,terms_json,rationale,canon_chunk_ids_json,response_due_day)
                           VALUES (?,?,?,?,?, 'pending',2,2,?,'','[]',?)""",
                        (counter[0], day, proposer, recipient, kind, json.dumps(terms), day))
                    res = it.resolve_interaction(conn, counter[0], day)
                    ok += res.response in ("comply", "accept")
                    conn.execute("ROLLBACK TO r")
                    conn.execute("RELEASE r")
                return ok / n

            def fair_terms(proposer, recipient, other, kind):
                """An incentive that puts a stranger near a coin flip, so differences show."""
                for inc in [i * 0.05 for i in range(0, 120)]:
                    t = {"incentive": inc}
                    if 0.25 <= rate(other, recipient, kind, t, 100) <= 0.4:
                        return t
                raise AssertionError("no incentive centres the stranger")

            neutral = dict(trust=0, stance=0, respect=0, fear=0, resentment=0, familiarity=20)

            # Kin accept a request more often than a stranger with identical meters.
            meters(neutral, neutral, child, parent)
            meters(neutral, neutral, child, stranger)
            t = fair_terms(parent, child, stranger, "request")
            kin_rate, str_rate = rate(parent, child, "request", t), rate(stranger, child, "request", t)
            assert kin_rate >= str_rate + 0.15, (kin_rate, str_rate)

            # A resentful child is not more compliant than a stranger.
            hot = dict(neutral, resentment=60)
            meters(hot, hot, child, parent)
            meters(hot, hot, child, stranger)
            assert rate(parent, child, "request", t) <= rate(stranger, child, "request", t) + 0.02

            # A household servant accepts an order more often than a stranger, but not always.
            meters(neutral, neutral, servant, boss)
            meters(neutral, neutral, servant, stranger)
            t = fair_terms(boss, servant, stranger, "request")
            s_rate, o_rate = rate(boss, servant, "request", t), rate(stranger, servant, "request", t)
            assert o_rate + 0.15 <= s_rate < 0.95, (s_rate, o_rate)
            t = fair_terms(boss, servant, stranger, "demand")
            d_rate, do_rate = rate(boss, servant, "demand", t), rate(stranger, servant, "demand", t)
            assert d_rate > do_rate and d_rate < 0.95, (d_rate, do_rate)

            # Fear raises demand compliance but not request compliance.
            afraid = dict(neutral, fear=80)
            meters(neutral, afraid, stranger, child)  # child fears stranger
            td = fair_terms(stranger, child, stranger, "demand")
            meters(neutral, neutral, stranger, child)
            calm_d, calm_r = rate(stranger, child, "demand", td), rate(stranger, child, "request", td)
            meters(neutral, afraid, stranger, child)
            assert rate(stranger, child, "demand", td) >= calm_d + 0.10
            assert rate(stranger, child, "request", td) == calm_r

            # Past threats by the proposer make the recipient less compliant.
            meters(neutral, neutral, stranger, child)
            before = rate(stranger, child, "request", td)
            for i in range(4):
                conn.execute("""INSERT INTO interactions(id,created_day,proposer_actor_id,recipient_actor_id,interaction_type,status,
                                  urgency,stakes,terms_json,rationale,canon_chunk_ids_json,response_due_day,resolved_day)
                                VALUES (?,?,?,?,'threat','rejected',2,2,'{}','','[]',?,?)""",
                             (6900000 + i, day - 20, stranger, child, day - 20, day - 20))
            assert rate(stranger, child, "request", td) <= before - 0.10, (before,)

            # The whole standing contribution is clamped, so it never decides alone.
            from engine.interactions import _standing_term
            meters(dict(neutral, respect=100, resentment=0), dict(neutral, respect=100, fear=100), child, parent)
            for kind in ("request", "offer", "demand", "threat", "conversation"):
                v = _standing_term(conn, parent, child, kind, day, 0)
                assert -0.6 <= v <= 0.6, (kind, v)
            assert abs(_standing_term(conn, stranger, servant, "conversation", day, 0)) <= 0.6
    print("interactions_standing_test passed")


if __name__ == "__main__":
    run()
