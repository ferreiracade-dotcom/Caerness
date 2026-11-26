"""What waits on the protagonist is closed by his answer in play, so it never later lapses as though he had said nothing."""
from __future__ import annotations

import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine import hearsay, ledger, life_matters as lm
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("answers", package="saintjude")
        made = server.author("a1", "protagonist", {
            "name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic", "accept": True,
            "people": [{"name": "Rosa Greco", "relation": "friend", "age": 23, "sex": "female"},
                       {"name": "Sal Moretti", "relation": "friend", "age": 25, "sex": "male"}]})
        assert made["status"] == "created", made
        me = made["actor_id"]
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            rosa = conn.execute("SELECT id FROM actors WHERE name='Rosa Greco'").fetchone()[0]
            sal = conn.execute("SELECT id FROM actors WHERE name='Sal Moretti'").fetchone()[0]
            ledger._credit(conn, ("person", me), 100)

        def ask(kind, subject, other, stage, amount=None, **data):
            with connect() as conn:
                p = lm._Pass(conn, day)
                m = lm._open(p, kind, subject, other, random.Random(1))
                m["amount"], m["data"] = amount, dict(data)
                lm._wait(p, m, stage)
                return m["id"]

        def row(mid):
            with connect() as conn:
                return dict(conn.execute("SELECT status,awaiting,stage,summary,data_json FROM life_matters WHERE id=?", (mid,)).fetchone())

        n = [0]

        def answer(mid, word, **more):
            n[0] += 1
            return server.act(f"x{n[0]}", "answer", "answer it", details={"matter": mid, "answer": word, **more})

        liking = ask("romance", rosa, me, "interest_in_him")
        # the GM is shown what waits and by which number to close it
        skip = server.advance("s0", 1, "work", from_day=day)
        assert any(w["matter"] == liking and "Rosa Greco" in w["what"] for w in skip["waiting_on_you"]), skip
        day = skip["day_ended"]
        got = answer(liking, "yes")
        assert got["status"] == "applied", got
        assert row(liking)["stage"] == "courting" and row(liking)["status"] == "open" and row(liking)["awaiting"] == 0, row(liking)

        quarrel = ask("quarrel", sal, me, "words", topic="a bet")
        assert answer(quarrel, "yes")["status"] == "applied"
        assert (row(quarrel)["status"], row(quarrel)["stage"]) == ("closed", "made_up"), row(quarrel)

        loan = ask("money", sal, me, "asks", amount=5000)
        poor = answer(loan, "yes")
        assert poor["status"] == "refused" and poor["reason_kind"] == "contradiction", poor
        assert row(loan)["awaiting"] == 1
        loan2 = ask("money", rosa, me, "asks", amount=40)
        with connect() as conn:
            had = ledger.balance(conn, ("person", me))
        assert answer(loan2, "yes")["status"] == "applied"
        with connect() as conn:
            assert ledger.balance(conn, ("person", me)) == had - 40
        assert row(loan2)["stage"] == "borrowed" and row(loan2)["status"] == "open" and row(loan2)["awaiting"] == 0, row(loan2)
        assert answer(loan, "no")["status"] == "applied"
        assert (row(loan)["status"], row(loan)["stage"]) == ("closed", "refused")

        job = ask("work", me, rosa, "asked", amount=60, trade="auto repair garage", job="the brakes", enterprise_id=1)
        assert answer(job, "yes")["status"] == "applied"
        assert row(job)["status"] == "open" and row(job)["awaiting"] == 0 and row(job)["stage"] == "agreed", row(job)

        other = ask("quarrel", rosa, me, "words", topic="money owed")
        said = answer(other, "settled", how="They talked it through at the diner.")
        assert said["status"] == "applied", said
        assert row(other)["status"] == "closed" and row(other)["summary"] == "They talked it through at the diner.", row(other)
        again = answer(other, "no")
        assert again["status"] == "refused", again

        dare = ask("scuffle", sal, me, "at_him", venue="Abate's")
        assert answer(dare, "no")["status"] == "applied"
        assert (row(dare)["status"], row(dare)["stage"]) == ("closed", "lapsed")

        # coming to blows with him answers a challenge, without being told to
        dare2 = ask("scuffle", sal, me, "at_him", venue="Abate's")
        with connect() as conn:
            lm.acted(conn, me, "attack", sal, day)
        assert row(dare2)["status"] == "closed", row(dare2)

        with connect() as conn:
            left = hearsay.waiting(conn, me)
            assert not {w["matter"] for w in left} & {liking, quarrel, loan, loan2, job, other, dare, dare2}, left
    print("PASS p2_answer_matter_test")


if __name__ == "__main__":
    main()
