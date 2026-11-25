"""P2: real money in dollars. Cash, jobs with deposits and collateral, IOUs, shares, wages; payers pay from what they have."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"}},
               "family_business": {"owner": "father", "type": "auto repair garage", "name": "Basile & Sons Auto Repair", "works": ["self"]},
               "accept": True}
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"m{_n[0]:03d}"


def main() -> None:
    from engine import ledger
    assert ledger.amount_of("$350") == 350 and ledger.amount_of("$1,249") == 1249 and ledger.amount_of("modest") == 3

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("money", package="saintjude")
        made = server.author(cid(), "protagonist", PROTAGONIST)
        me = made["actor_id"]

        def money(op, **details):
            out = server.money(cid(), op, details)
            assert "error" not in out and out.get("status") != "refused", (op, details, out)
            return out

        def cash(a) -> float:
            with connect() as conn:
                return ledger.balance(conn, ("person", a))

        def day() -> int:
            return server.scene()["day"]

        def skip(n):
            out = server.advance(cid(), n, "work at the garage", from_day=day())
            assert "error" not in out, out
            return out

        def person(name, sex="male"):
            out = server.author(cid(), "person", {"name": name, "sex": sex, "age": 30, "place": "South Hill"})
            assert out.get("actor_id"), out
            return out["actor_id"]

        sam, rocco, frank = person("Samuel Harris"), person("Rocco Ferrante"), person("Frank Amato")

        money("set_cash", holder="me", amount="$200", reason="his savings")
        s = server.scene()
        assert s["money"]["cash"] == "$200", s.get("money")
        assert s["holdings"]["means"]["purse"] == "$200", s["holdings"]["means"]

        # a job: quote, deposit, collateral, a share for the friend who brought the work
        money("set_cash", holder=sam, amount=500, reason="what he has on him")
        money("share", to=frank, share="10%", applies="referred", note="finder's cut")
        deal = money("deal", customer=sam, job="Camaro tune and head work", quote="$350", deposit=175, parts=100, due_in_days=7,
                     referrer=frank, collateral="registration and title")
        assert (deal["paid"], deal["owing"]) == ("$175", "$175"), deal
        assert cash(me) == 375 and cash(sam) == 325
        told = server.resume_current()["scene"]["money"]
        assert told["owed_to_him"][0]["owing"] == "$175" and "title" in told["owed_to_him"][0]["holding"], told

        # a customer who is short pays what they can spare, and the rest stays owed
        money("set_cash", holder=rocco, amount=40, reason="what he has on him")
        nova = money("deal", customer=rocco, job="Nova brakes", quote=85, due_in_days=3)
        out = skip(8)
        assert cash(sam) == 150 and cash(frank) >= 25, (cash(sam), cash(frank))
        said = " | ".join(out["money"])
        assert "Samuel Harris paid $175" in said and "Rocco Ferrante" in said and "still owes" in said, said
        listed = money("show")
        owing = {d["deal_id"]: d for d in listed["owed_to_him"]}
        assert deal["deal_id"] not in owing, listed  # paid in full: closed, and the papers went back
        with connect() as conn:
            assert conn.execute("SELECT status FROM deal_collateral WHERE deal_id=?", (deal["deal_id"],)).fetchone()[0] == "returned"
            assert conn.execute("SELECT SUM(amount_usd) FROM share_payments WHERE deal_id=?", (deal["deal_id"],)).fetchone()[0] == 25
            paid = conn.execute("SELECT SUM(amount_usd) FROM deal_payments WHERE deal_id=?", (nova["deal_id"],)).fetchone()[0]
        assert 0 < paid < 85 and owing[nova["deal_id"]]["owing"] == f"${85 - paid:,.0f}", (paid, owing)

        # several debts at once and not enough: split in proportion; enough: paid in full, however little is left
        sal, lou = person("Salvatore Greco"), person("Louie Marchetti")
        money("set_cash", holder=sal, amount=100, reason="x")
        a = money("deal", customer=sal, job="exhaust", quote=100, due_in_days=1)["deal_id"]
        b = money("deal", customer=sal, job="clutch", quote=100, due_in_days=1)["deal_id"]
        money("set_cash", holder=lou, amount=90, reason="x")
        c = money("deal", customer=lou, job="starter", quote=90, due_in_days=1)["deal_id"]
        skip(2)
        with connect() as conn:
            got = dict(conn.execute("SELECT deal_id,SUM(amount_usd) FROM deal_payments WHERE deal_id IN (?,?,?) GROUP BY deal_id", (a, b, c)))
        assert got[c] == 90 and got[a] == got[b] and 0 < got[a] <= 50, got

        # his own debt is his to pay: nothing leaves his purse for it unasked
        mine = money("deal", customer=me, provider=lou, job="a set of used wheels", quote=60, due_in_days=1)
        before = cash(me)
        out = skip(2)
        with connect() as conn:
            assert not conn.execute("SELECT 1 FROM deal_payments WHERE deal_id=?", (mine["deal_id"],)).fetchone()
        assert any("owes Louie Marchetti $60" in m for m in out.get("money", [])), out.get("money")
        paid = money("pay", deal_id=mine["deal_id"], amount=60)
        assert paid["owing"] == "$0", paid

        # the agreed wage, once a week, from the shop; payroll does not pay him a second time
        with connect() as conn:
            shop = conn.execute("SELECT enterprise_id FROM enterprise_staff WHERE actor_id=? AND status='active'", (me,)).fetchone()[0]
        money("set_cash", holder=f"business:{shop}", amount=5000, reason="the shop's till")
        money("wage", worker=me, business=shop, weekly=125, first_in_days=1)
        before = cash(me)
        with connect() as conn:
            mark = conn.execute("SELECT COALESCE(MAX(id),0) FROM economic_flows").fetchone()[0]

        def flows(where, *args):
            with connect() as conn:
                return conn.execute(f"SELECT COUNT(*),COALESCE(SUM(amount),0) FROM economic_flows WHERE id>? AND {where}",
                                    (mark, *args)).fetchone()

        out = skip(15)
        with connect() as conn:
            owed = conn.execute("SELECT owed_usd,status FROM agreement_terms WHERE ref_kind='wage'").fetchone()
        assert tuple(owed) == (0.0, "active"), tuple(owed)
        assert tuple(flows("target_actor_id=? AND source_enterprise_id=?", me, shop)) == (3, 375.0)
        assert any("$125 (wage)" in m for m in out["money"]), out["money"]
        with connect() as conn:
            from engine import payroll
            payroll.run_business_payroll(conn, shop, 1000.0, 0.0)
            conn.commit()
        assert tuple(flows("target_actor_id=? AND source_enterprise_id=?", me, shop)) == (3, 375.0), "paid twice"

        # money is conserved: his cash moved only by recorded payments
        change, came, went = cash(me) - before, flows("target_actor_id=?", me)[1], flows("source_actor_id=?", me)[1]
        assert abs(change - (came - went)) < 0.01 and came >= 375, (change, came, went)

        # an IOU between people, listed until paid
        money("owe", debtor=rocco, creditor=me, amount=15, what="parts fronted", due_in_days=30)
        assert any(i["owing"] == "$15" for i in money("show")["ious_to_him"])
        refused = server.money(cid(), "set_cash", {"holder": "me", "amount": 9})
        assert refused.get("status") == "refused" or "error" in refused, refused  # a correction needs its reason
    print("PASS p2_money_test")


if __name__ == "__main__":
    main()
