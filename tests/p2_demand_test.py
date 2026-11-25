"""P2: ordinary wording is not a demand; money already owed is collected from what the debtor has, with no haggling;
a plain talk is answered unless there is real hostility."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"}}, "accept": True}
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"d{_n[0]:03d}"


def main() -> None:
    from engine.free_operation import classify
    for words in ("Make sure Anthony tells Mom about dinner.", "Force the seized bolt to turn.", "Make him stop fussing and eat.",
                  "Ask around about the demand for rebuilt carburettors.", "Talk to his sister Ally about the car.",
                  "Parts are made on demand at the foundry; look into it."):
        assert classify(words, None) != "demand", words
    for words in ("Demand that he stays off our corner.", "I demand my money from him.", "Extort the grocer.", "Threaten him.",
                  "Offer a truce to the Greco crew."):
        assert classify(words, None) == "demand", words

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine import ledger
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("demand", package="saintjude")
        me = server.author(cid(), "protagonist", PROTAGONIST)["actor_id"]

        def person(name):
            return server.author(cid(), "person", {"name": name, "sex": "male", "age": 30, "place": "South Hill"})["actor_id"]

        def count(sql, *args):
            with connect() as conn:
                return conn.execute(sql, args).fetchone()[0]

        sam, rocco, lou = person("Samuel Harris"), person("Rocco Ferrante"), person("Louie Marchetti")
        server.money(cid(), "set_cash", {"holder": sam, "amount": 40, "reason": "in his pocket"})
        server.money(cid(), "set_cash", {"holder": rocco, "amount": 40, "reason": "in his pocket"})
        one = server.money(cid(), "deal", {"customer": sam, "job": "Camaro", "quote": 25, "due_in_days": 2})["deal_id"]
        two = server.money(cid(), "deal", {"customer": rocco, "job": "Nova", "quote": 85, "due_in_days": 2})["deal_id"]
        before = count("SELECT COUNT(*) FROM interactions")

        got = server.act(cid(), "demand", "Collect the last of the Camaro money.", target_actor_id=sam,
                         details={"what": "payment", "amount": "$25"})
        assert got["status"] == "applied" and "$25" in got["summary"], got
        assert count("SELECT COALESCE(SUM(amount_usd),0) FROM deal_payments WHERE deal_id=?", one) == 25

        # plain words, no kind: still a collection, never the protagonist paying the debtor
        mine = count("SELECT amount FROM resources WHERE actor_id=? AND resource_type='cash'", me) if count(
            "SELECT COUNT(*) FROM resources WHERE actor_id=? AND resource_type='cash'", me) else 0
        got = server.act(cid(), "operation", "Ask Rocco to pay what he owes.", target_actor_id=rocco)
        paid = count("SELECT COALESCE(SUM(amount_usd),0) FROM deal_payments WHERE deal_id=?", two)
        assert got["status"] == "partial" and paid == 15 and "$70" in got["summary"], (got, paid)
        with connect() as conn:
            assert ledger.balance(conn, ("person", me)) == mine + 15
        assert count("SELECT COUNT(*) FROM interactions") == before, "collecting a debt is not a negotiation"

        # nothing to spare: told so, nothing moves
        got = server.act(cid(), "demand", "Collect again.", target_actor_id=rocco, details={"what": "payment"})
        assert got["status"] == "partial" and count("SELECT COALESCE(SUM(amount_usd),0) FROM deal_payments WHERE deal_id=?", two) == 15, got

        # a plain talk with someone who has nothing against him is answered, never "rejected"
        from engine.interactions import create_interaction, resolve_interaction
        from engine.relationships import adjust_relationship
        with connect() as conn:
            day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            others = [r[0] for r in conn.execute(
                "SELECT id FROM actors WHERE status='active' AND actor_type='character' AND id NOT IN (?,?) ORDER BY id LIMIT 60", (me, lou))]
            outcomes = []
            for other in others:
                iid = create_interaction(conn, me, other, "conversation", day, stakes=1, rationale="passing the time")
                if conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()[0] == "pending":
                    outcomes.append(resolve_interaction(conn, iid, day).response)
            assert len(outcomes) > 30 and set(outcomes) == {"accept"}, outcomes
            adjust_relationship(conn, lou, me, day, resentment_delta=90, trust_delta=-90, stance_delta=-90)
            adjust_relationship(conn, me, lou, day, resentment_delta=90, trust_delta=-90, stance_delta=-90)
            iid = create_interaction(conn, me, lou, "conversation", day, stakes=1, rationale="clear the air")
            assert resolve_interaction(conn, iid, day).response == "reject"
            conn.rollback()
    print("PASS p2_demand_test")


if __name__ == "__main__":
    main()
