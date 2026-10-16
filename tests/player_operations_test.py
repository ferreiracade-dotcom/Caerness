from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "ops.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine import ledger, player_operations as po
        from fixtures_protagonist import make_boss

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            w = make_boss(conn)
            me, biz, outfit = w["me"], w["business"], w["outfit"]
            actors0 = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
            ev0 = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='player_operation'").fetchone()[0]

            b0, p0 = ledger.balance(conn, ("business", biz)), ledger.balance(conn, ("person", me))
            r = po.execute(conn, me, "pay", target_actor_id=None,
                           details={"from": f"business:{biz}", "to": "me", "amount": "substantial"}, intent="I draw from the till.")
            assert r["status"] == "applied", r
            assert abs(b0 - ledger.balance(conn, ("business", biz)) - 8) < 1e-9
            assert abs(ledger.balance(conn, ("person", me)) - p0 - 8) < 1e-9
            assert "substantial" in r["summary"] and not re.search(r"\d", r["summary"]), r
            assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='player_operation'").fetchone()[0] == ev0 + 1

            from engine import civilian
            other_id = civilian.create_enterprise(conn, "Foreign Stall", "shop", owner_actor_id=w["bystander"], cash=9)
            ob = ledger.balance(conn, ("business", other_id))
            r = po.execute(conn, me, "pay", target_actor_id=None,
                           details={"from": f"business:{other_id}", "to": "me", "amount": "small"}, intent="I raid it.")
            assert r["status"] == "refused" and ledger.balance(conn, ("business", other_id)) == ob, r
            r = po.execute(conn, me, "pay", target_actor_id=None,
                           details={"from": "me", "to": f"person:{w['bystander']}", "amount": "fortune"}, intent="Too much.")
            assert r["status"] == "refused", r

            # hire: crew leader into the business (tier 1, already the protagonist's personnel)
            r = po.execute(conn, me, "hire", target_actor_id=w["crew_leader"],
                           details={"into": f"business:{biz}", "role": "factor"}, intent="Mind my stall.")
            assert r["status"] == "applied", r
            assert conn.execute("SELECT 1 FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND status='active'",
                                (biz, w["crew_leader"])).fetchone()

            # hire the bystander into the outfit (tier 2)
            r = po.execute(conn, me, "hire", target_actor_id=w["bystander"],
                           details={"into": f"outfit:{outfit}", "role": "member", "amount": "modest"}, intent="Join us.")
            row = conn.execute("SELECT status FROM underworld_personnel WHERE actor_id=?", (w["bystander"],)).fetchone()
            if r["status"] == "applied":
                assert row and row["status"] == "active", (r, row)
            else:
                assert r["status"] == "refused" and row is None, (r, row)

            # dismiss the crew leader from the outfit
            res0 = conn.execute("SELECT COALESCE(MAX(resentment),0) FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
                                (w["crew_leader"], me)).fetchone()[0]
            r = po.execute(conn, me, "hire", target_actor_id=w["crew_leader"],
                           details={"into": f"outfit:{outfit}", "role": "none"}, intent="You are done.")
            assert r["status"] == "applied", r
            assert conn.execute("SELECT status FROM underworld_personnel WHERE actor_id=?", (w["crew_leader"],)).fetchone()[0] == "expelled"
            res1 = conn.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
                                (w["crew_leader"], me)).fetchone()[0]
            assert res1 > res0, (res0, res1)

            # mistakes are results, never exceptions
            assert po.execute(conn, me, "pay", target_actor_id=None, details={"to": "bank:1", "amount": "small"}, intent="x")["status"] == "refused"
            assert po.execute(conn, me, "pay", target_actor_id=None, details={"to": "me", "amount": "lots"}, intent="x")["status"] == "refused"
            assert po.execute(conn, me, "hire", target_actor_id=None, details={"into": "outfit:1"}, intent="x")["status"] == "refused"

            assert conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0] == actors0

            # ---- lend and demand (Task 3)
            from engine import civilian_life
            from engine.person_ecology import resolve_background_person
            from engine.underworld import create_underworld_organization
            from engine.underworld_rebuild import create_crew, create_personnel
            by, loc = w["bystander"], w["location"]

            # lend: refused for another's purse, applied or refused (never half) for his own
            assert po.execute(conn, me, "lend", target_actor_id=by,
                              details={"amount": "modest", "from": f"business:{other_id}"}, intent="x")["status"] == "refused"
            assert po.execute(conn, me, "lend", target_actor_id=by, details={"amount": "fortune"}, intent="x")["status"] == "refused"
            ledger.transfer(conn, ("business", biz), ("person", me), 2.0, flow_kind="other", purpose="t")
            mine0, theirs0 = ledger.balance(conn, ("person", me)), ledger.balance(conn, ("person", by))
            n_cred = conn.execute("SELECT COUNT(*) FROM credit_agreements").fetchone()[0]
            r = po.execute(conn, me, "lend", target_actor_id=by, details={"amount": "modest", "rate": "usual"}, intent="A loan between friends.")
            if r["status"] == "applied":
                row = conn.execute("SELECT * FROM credit_agreements WHERE borrower_actor_id=? AND lender_actor_id=? ORDER BY id DESC", (by, me)).fetchone()
                assert row and abs(row["principal"] - 3.0) < 1e-9 and abs(row["interest_rate_per_30"] - 0.05) < 1e-9, r
                assert abs(mine0 - ledger.balance(conn, ("person", me)) - 3.0) < 1e-9
                assert abs(ledger.balance(conn, ("person", by)) - theirs0 - 3.0) < 1e-9
                assert not re.search(r"\d", r["summary"]), r
            else:
                assert r["status"] == "refused" and conn.execute("SELECT COUNT(*) FROM credit_agreements").fetchone()[0] == n_cred, r
                assert abs(ledger.balance(conn, ("person", me)) - mine0) < 1e-9

            # demand a debt with the crew behind him: the debtor pays what he has, status partial
            conn.execute("DELETE FROM resources WHERE actor_id=? AND resource_type='cash'", (by,))
            conn.execute("DELETE FROM underworld_leader_wealth WHERE actor_id=?", (by,))
            conn.execute("INSERT INTO resources(actor_id,resource_type,amount) VALUES (?,'cash',1.0)", (by,))
            debt = civilian_life.create_credit_agreement(conn, principal=8.0, lender_actor_id=me, borrower_actor_id=by, due_day=999999)
            me_before = ledger.balance(conn, ("person", me))
            owed = lambda: conn.execute("SELECT COALESCE(SUM(outstanding),0) FROM credit_agreements WHERE borrower_actor_id=? AND lender_actor_id=?", (by, me)).fetchone()[0]
            owed0 = owed()
            comp = None
            for _ in range(3):
                r = po.execute(conn, me, "demand", target_actor_id=by,
                               details={"what": "debt", "crew": f"crew:{w['crew']}", "open": False}, intent="You owe me.")
                if r["status"] != "refused":
                    comp = r
                    break
            if comp is not None:
                assert comp["status"] == "partial", comp
                assert abs(owed0 - owed() - 1.0) < 1e-9, (owed0, owed())
                assert conn.execute("SELECT status FROM credit_agreements WHERE id=(SELECT MIN(id) FROM credit_agreements WHERE borrower_actor_id=? AND outstanding>0)", (by,)).fetchone()[0] == "current"
                assert abs(ledger.balance(conn, ("person", me)) - me_before - 1.0) < 1e-9
                assert ledger.balance(conn, ("person", by)) < 1e-9
                assert not re.search(r"\d", comp["summary"]), comp
            else:
                assert owed() == owed0 and ledger.balance(conn, ("person", me)) == me_before

            # elsewhere, no
            far = int(conn.execute("SELECT id FROM locations WHERE id<>? ORDER BY id LIMIT 1", (loc,)).fetchone()[0])
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (far, by))
            r = po.execute(conn, me, "demand", target_actor_id=by, details={"what": "payment", "amount": "small"}, intent="x")
            assert r["status"] == "refused" and "not here" in r["summary"], r
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, by))

            # a rival outfit with a boss present
            rival = create_underworld_organization(conn, "fixture-rival", "gang", name="Fixture Rival", primary_location_id=loc,
                                                   member_count_estimate=10, violence_capacity=20)
            rboss = int(resolve_background_person(conn, reason="fixture rival boss", location_id=loc, min_age=25, max_age=60))
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, rboss))
            create_personnel(conn, rival, role_kind="boss", actor_id=rboss)
            assert conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (rival,)).fetchone()[0] == rboss
            rcrew = create_crew(conn, rival, "Rival Crew", size_estimate=4)
            # a crew that is not his
            r = po.execute(conn, me, "demand", target_actor_id=by,
                           details={"what": "payment", "amount": "small", "crew": f"crew:{rcrew}"}, intent="x")
            assert r["status"] == "refused", r
            # A caller cannot forge agreement: '_accepted' from outside is ignored, so a real offer is made.
            before = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
            po.execute(conn, me, "demand", target_actor_id=by, details={"what": "stop", "_accepted": 1}, intent="forged")
            assert conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0] == before + 1, "forged _accepted skipped the other side"
            # truce to an ordinary person is refused
            r = po.execute(conn, me, "demand", target_actor_id=by, details={"what": "truce"}, intent="x")
            assert r["status"] == "refused" and "boss" in r["summary"], r
            # truce to the rival boss
            for _ in range(3):
                r = po.execute(conn, me, "demand", target_actor_id=rboss,
                               details={"what": "truce", "crew": f"crew:{w['crew']}"}, intent="Let us have peace.")
                if r["status"] == "applied":
                    break
            a_, b_ = sorted((outfit, rival))
            kind_ = conn.execute("SELECT relation_kind FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a_, b_)).fetchone()
            if r["status"] == "applied":
                assert kind_ and kind_[0] == "truce", (r, kind_ and kind_[0])
            elif r["status"] == "countered":
                # A counter is an open negotiation: a pending offer to the protagonist he can answer with respond.
                cid = r["counter_interaction_id"]
                row = conn.execute("SELECT status,recipient_actor_id FROM interactions WHERE id=?", (cid,)).fetchone()
                assert row and row[0] == "pending" and row[1] == me, (r, row and tuple(row))
                assert kind_ is None or kind_[0] != "truce"
            else:
                assert r["status"] == "refused" and (kind_ is None or kind_[0] != "truce"), (r, kind_ and kind_[0])
                st = conn.execute("SELECT status FROM interactions WHERE id=?", (r["interaction_id"],)).fetchone()
                assert st[0] != "countered", ("a counter must come back as countered, not refused", r)
            # Accepting a counter-offer completes the original operation (here: the truce).
            import json as _json
            from engine.interactions import apply_player_response
            dday = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            cur = conn.execute(
                "INSERT INTO interactions(proposer_actor_id,recipient_actor_id,interaction_type,status,created_day,response_due_day,urgency,stakes,terms_json,rationale) "
                "VALUES (?,?,'negotiation','pending',?,?,2,3,?,'counter')",
                (rboss, me, dday, dday + 1, _json.dumps({"what": "truce", "player_operation": {"op": "demand", "details": {"what": "truce"}}})))
            apply_player_response(conn, int(cur.lastrowid), me, "accept", dday)
            kind_ = conn.execute("SELECT relation_kind FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a_, b_)).fetchone()
            assert kind_ and kind_[0] == "truce", ("accepting the counter must record the truce", kind_ and kind_[0])
            # the accepted branch itself (the answer above is chance): truce, tribute and split write the relation
            for what_, kind2 in (("truce", "truce"), ("tribute", "tributary"), ("split", "hostile_peace")):
                rr = po._concede(conn, me, rboss, "The boss", what_, {"amount": "modest", "terms": "north bank is mine"}, None, [], outfit, rival, 0, False)
                kind_ = conn.execute("SELECT relation_kind FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a_, b_)).fetchone()
                assert rr["status"] == "applied" and kind_[0] == kind2, (what_, rr, kind_[0])
            assert po.execute(conn, me, "demand", target_actor_id=by, details={"what": "bogus"}, intent="x")["status"] == "refused"
            # ---- attack
            from engine import civilian
            from connector.acting import act
            from connector.store import ensure_connector_schema
            ensure_connector_schema(conn)
            conn.execute("UPDATE actors SET current_location_id=? WHERE id IN (?,?)", (loc, by, w["crew_leader"]))
            crew_ref = f"crew:{w['crew']}"
            r = po.execute(conn, me, "attack", target_actor_id=None, details={"business": f"business:{biz}", "intent_kind": "beat"}, intent="x")
            assert r["status"] == "refused" and "own" in r["summary"], r
            rival_shop = civilian.create_enterprise(conn, "Fixture Rival Shop", "shop", owner_actor_id=by, location_id=loc, capital=10, cash=3)
            cap0 = conn.execute("SELECT capital FROM civilian_enterprises WHERE id=?", (rival_shop,)).fetchone()[0]
            ev_n = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='player_operation'").fetchone()[0]
            r = po.execute(conn, me, "attack", target_actor_id=None,
                           details={"business": f"business:{rival_shop}", "intent_kind": "beat", "crew": crew_ref}, intent="Smash the stall.")
            assert r["status"] == "applied" and r["outcome"] == "won", r
            cap1 = conn.execute("SELECT capital FROM civilian_enterprises WHERE id=?", (rival_shop,)).fetchone()[0]
            assert abs(cap1 - cap0 * 0.85) < 1e-9, (cap0, cap1)
            assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='player_operation'").fetchone()[0] == ev_n + 1
            r = po.execute(conn, me, "attack", target_actor_id=None, details={"business": "business:999999"}, intent="x")
            assert r["status"] == "refused", r
            r = po.execute(conn, me, "attack", target_actor_id=by,
                           details={"with": [w["crew_leader"], w["crew_leader"]], "intent_kind": "beat"}, intent="x")
            assert r["status"] == "refused" and "twice" in r["summary"], r
            other = int(conn.execute("SELECT id FROM locations WHERE id<>? ORDER BY id LIMIT 1", (loc,)).fetchone()[0])
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (other, by))
            r = po.execute(conn, me, "attack", target_actor_id=by, details={"intent_kind": "beat"}, intent="x")
            assert r["status"] == "refused" and "not here" in r["summary"], r
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, by))
            h0 = conn.execute("SELECT COUNT(*) FROM harm_incidents").fetchone()[0]
            d_ = {"intent_kind": "beat", "crew": crew_ref}
            res = act(conn, "atk-1", "attack", "I beat him.", target_actor_id=by, details=d_)
            assert res["status"] == "applied" and res["outcome"] in ("won", "lost", "stalemate"), res
            assert res["hurt"] and not re.search(r"\d", res["summary"]), res
            h1 = conn.execute("SELECT COUNT(*) FROM harm_incidents").fetchone()[0]
            assert h1 == h0 + len(res["hurt"]), (h0, h1, res)
            assert conn.execute("SELECT 1 FROM events WHERE id=?", (res["event_id"],)).fetchone(), res
            again = act(conn, "atk-1", "attack", "I beat him.", target_actor_id=by, details=d_)
            assert again["replayed"] is True
            assert conn.execute("SELECT COUNT(*) FROM harm_incidents").fetchone()[0] == h1
            conn.execute("UPDATE actors SET status='deceased' WHERE id=?", (by,))
            r = po.execute(conn, me, "attack", target_actor_id=by, details={"intent_kind": "beat"}, intent="x")
            assert r["status"] == "refused", r
            conn.execute("UPDATE actors SET status='active' WHERE id=?", (by,))

            # ---- order and trade (Task 5)
            from engine.relationships import relationship_view
            leader = w["crew_leader"]
            conn.execute("UPDATE underworld_personnel SET status='active' WHERE actor_id=?", (leader,))
            conn.execute("UPDATE underworld_personnel SET status='expelled' WHERE actor_id=?", (by,))
            conn.execute("UPDATE actors SET current_location_id=? WHERE id IN (?,?)", (loc, by, leader))
            cash = lambda a: ledger.balance(conn, ("person", a))

            def drives(aid, loyalty, risk, aggression):
                conn.execute("UPDATE actor_drives SET loyalty=?, risk_tolerance=?, aggression=? WHERE actor_id=?", (loyalty, risk, aggression, aid))

            # a stranger is not a subordinate
            r = po.execute(conn, me, "order", target_actor_id=by, details={"do": "demand", "toward": leader, "what": "other"}, intent="x")
            assert r["status"] == "refused" and "subordinate" in r["summary"], r
            drives(leader, 0.95, 0.9, 0.5)
            # an order to demand a debt: the leader acts, the protagonist collects
            civilian_life.create_credit_agreement(conn, principal=8.0, lender_actor_id=me, borrower_actor_id=by, due_day=999999)
            conn.execute("UPDATE resources SET amount=5 WHERE actor_id=? AND resource_type='cash'", (by,))
            m0, l0 = cash(me), cash(leader)
            r = po.execute(conn, me, "order", target_actor_id=leader,
                           details={"do": "demand", "toward": by, "what": "debt", "_call_id": "ord-1"}, intent="Collect what he owes me.")
            assert r["by"] == po._name(conn, leader) and r["obeyed"] == "yes" and "report" in r, r
            assert r["status"] in ("applied", "partial", "refused", "countered"), r
            assert abs(cash(leader) - l0) < 1e-9, "the proceeds belong to the protagonist, not the subordinate"
            if r["status"] in ("applied", "partial"):
                assert cash(me) > m0, r
            else:
                assert abs(cash(me) - m0) < 1e-9, r
            # an order to pay draws on the protagonist's purse, not the subordinate's
            m0, l0 = cash(me), cash(leader)
            r = po.execute(conn, me, "order", target_actor_id=leader,
                           details={"do": "pay", "toward": by, "to": f"person:{by}", "from": "me", "amount": "small"}, intent="Give him this.")
            assert r["status"] == "applied" and r["obeyed"] == "yes", r
            assert abs(m0 - cash(me) - 1.0) < 1e-9 and abs(cash(leader) - l0) < 1e-9, (m0, cash(me), l0, cash(leader))
            # the subordinate cannot reach a purse the protagonist does not control
            r = po.execute(conn, me, "order", target_actor_id=leader,
                           details={"do": "pay", "toward": by, "to": f"person:{by}", "from": f"business:{other_id}", "amount": "small"}, intent="x")
            assert r["status"] == "refused", r
            # not in town
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (far, by))
            r = po.execute(conn, me, "order", target_actor_id=leader, details={"do": "demand", "toward": by, "what": "other"}, intent="x")
            assert r["status"] == "refused" and "not in town" in r["summary"], r
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, by))
            # disloyal and timid: he will not kill for him
            drives(leader, 0.05, 0.1, 0.1)
            h0 = conn.execute("SELECT COUNT(*) FROM harm_incidents").fetchone()[0]
            trust0 = relationship_view(conn, me, leader)["trust"]
            r = po.execute(conn, me, "order", target_actor_id=leader,
                           details={"do": "attack", "toward": by, "intent_kind": "kill", "_call_id": "ord-2"}, intent="Kill him.")
            assert r["obeyed"] == "refused" and r["status"] == "refused" and r["by"] == po._name(conn, leader), r
            assert conn.execute("SELECT COUNT(*) FROM harm_incidents").fetchone()[0] == h0
            assert relationship_view(conn, me, leader)["trust"] < trust0
            # loyal and bold: it is done in his name
            drives(leader, 0.95, 0.9, 0.5)
            r = po.execute(conn, me, "order", target_actor_id=leader,
                           details={"do": "attack", "toward": by, "intent_kind": "beat", "_call_id": "ord-3"}, intent="Beat him.")
            assert r["obeyed"] in ("yes", "reluctantly") and r["status"] == "applied" and r["hurt"], r
            assert conn.execute("SELECT COUNT(*) FROM harm_incidents").fetchone()[0] == h0 + len(r["hurt"])

            # trade: a sale the buyer cannot pay for
            conn.execute("UPDATE resources SET amount=0 WHERE actor_id=? AND resource_type='cash'", (by,))
            conn.execute("DELETE FROM underworld_leader_wealth WHERE actor_id=?", (by,))
            from engine.merchant import add_enterprise_staff
            add_enterprise_staff(conn, biz, me, role="owner", authority=100)
            r = po.execute(conn, me, "trade", target_actor_id=by,
                           details={"deal": "sell", "business": f"business:{biz}", "amount": "fortune"}, intent="Buy me out.")
            assert r["status"] == "refused" and "afford" in r["summary"], r
            assert conn.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?", (biz,)).fetchone()[0] == me
            # buy another's shop; the stall is only his own to sell
            conn.execute("UPDATE resources SET amount=amount+100 WHERE actor_id=? AND resource_type='cash'", (me,))
            m0, b0_ = cash(me), cash(by)
            r = po.execute(conn, me, "trade", target_actor_id=by,
                           details={"deal": "buy", "business": f"business:{rival_shop}", "amount": "fortune"}, intent="Name your price.")
            owner = conn.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?", (rival_shop,)).fetchone()[0]
            if r["status"] == "applied":
                assert owner == me and abs(m0 - cash(me) - 60.0) < 1e-9 and abs(cash(by) - b0_ - 60.0) < 1e-9, r
                assert not re.search(r"\d", r["summary"]), r
            else:
                assert r["status"] in ("refused", "countered") and owner == by and abs(cash(me) - m0) < 1e-9, r
            assert po.execute(conn, me, "trade", target_actor_id=by, details={"deal": "buy", "business": f"business:{biz}", "amount": "small"}, intent="x")["status"] == "refused"
            assert po.execute(conn, me, "trade", target_actor_id=by, details={"deal": "sell", "business": f"business:{other_id}", "amount": "small"}, intent="x")["status"] == "refused"
            # sell for a price the buyer can pay: either way the books agree
            conn.execute("UPDATE resources SET amount=amount+100 WHERE actor_id=? AND resource_type='cash'", (by,))
            m0, b0_ = cash(me), cash(by)
            r = po.execute(conn, me, "trade", target_actor_id=by,
                           details={"deal": "sell", "business": f"business:{biz}", "amount": "small"}, intent="Take the stall.")
            owner = conn.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?", (biz,)).fetchone()[0]
            staff = conn.execute("SELECT 1 FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND role='owner' AND status='active'", (biz, me)).fetchone()
            if r["status"] == "applied":
                assert owner == by and staff is None and abs(cash(me) - m0 - 1.0) < 1e-9 and abs(b0_ - cash(by) - 1.0) < 1e-9, r
            else:
                assert r["status"] in ("refused", "countered") and owner == me and staff is not None, r
    print("player_operations_test passed")


def run_review_fixes():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "ops2.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine import interactions, ledger, player_operations as po
        from engine.merchant import add_enterprise_staff
        from fixtures_protagonist import make_boss

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            w = make_boss(conn)
            me, by, outfit, biz, hh = w["me"], w["bystander"], w["outfit"], w["business"], w["household"]
            day = po._day(conn)
            count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]

            # 2: a dissolved household cannot take on people, and nothing is left behind
            conn.execute("UPDATE households SET status='dissolved' WHERE id=?", (hh,))
            i0, r0 = count("interactions"), count("relationships")
            r = po.execute(conn, me, "hire", target_actor_id=by, details={"into": f"household:{hh}", "role": "retainer", "amount": "modest"}, intent="x")
            assert r["status"] == "refused", r
            assert count("interactions") == i0 and count("relationships") == r0, "refusal left rows behind"
            conn.execute("UPDATE households SET status='active' WHERE id=?", (hh,))

            # 2: a handler that fails half way is rolled back; non-ValueErrors are re-raised after rollback
            def half_done(c, m, t, d, i):
                po.create_interaction(c, m, by, "offer", day, stakes=1, rationale="x", terms={})
                raise ValueError("halfway")
            saved = po._HANDLERS["hire"]
            po._HANDLERS["hire"] = half_done
            r = po.execute(conn, me, "hire", target_actor_id=by, details={}, intent="x")
            assert r["status"] == "refused" and "halfway" in r["summary"] and count("interactions") == i0, r

            def boom(c, m, t, d, i):
                po.create_interaction(c, m, by, "offer", day, stakes=1, rationale="x", terms={})
                raise RuntimeError("boom")
            po._HANDLERS["hire"] = boom
            try:
                po.execute(conn, me, "hire", target_actor_id=by, details={}, intent="x")
                raise AssertionError("expected RuntimeError")
            except RuntimeError:
                pass
            assert count("interactions") == i0
            po._HANDLERS["hire"] = saved

            # 3: loans come from his purse or a house of business only
            cr0 = count("credit_agreements")
            for src in (f"outfit:{outfit}", f"household:{hh}"):
                r = po.execute(conn, me, "lend", target_actor_id=by, details={"from": src, "amount": "small"}, intent="x")
                assert r["status"] == "refused" and "own purse or one of his houses" in r["summary"], r
            assert count("interactions") == i0 and count("credit_agreements") == cr0

            # 5: the other party accepts the protagonist's own offer later, during the simulation
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (w["location"], by))
            terms = {"player_operation": {"op": "lend", "details": {"amount": "small"}}, "incentive": 8}
            iid = interactions.create_interaction(conn, me, by, "offer", day, stakes=1, rationale="A loan, if you will.", terms=terms)
            assert conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()[0] == "pending"
            ledger._credit(conn, ("person", me), 20)
            m0, b0 = ledger.balance(conn, ("person", me)), ledger.balance(conn, ("person", by))
            res = interactions.resolve_interaction(conn, iid, day)
            assert res.response == "accept", res
            row = conn.execute("SELECT * FROM credit_agreements WHERE borrower_actor_id=? AND lender_actor_id=?", (by, me)).fetchone()
            assert row is not None and count("credit_agreements") == cr0 + 1, res.summary
            assert abs(m0 - ledger.balance(conn, ("person", me)) - 1.0) < 1e-9 and abs(ledger.balance(conn, ("person", by)) - b0 - 1.0) < 1e-9
            # the immediate path still settles exactly once
            cr1 = count("credit_agreements")
            conn.execute("UPDATE interactions SET status='expired' WHERE status='pending'")
            r = po.execute(conn, me, "lend", target_actor_id=by, details={"amount": "small", "_call_id": "x"}, intent="Another.")
            assert count("credit_agreements") == cr1 + (1 if r["status"] == "applied" else 0), r

            # 6: obedience calibration
            leader = w["crew_leader"]
            conn.execute("UPDATE actors SET current_location_id=? WHERE id IN (?,?)", (w["location"], leader, by))
            add_enterprise_staff(conn, biz, by, role="clerk", authority=40)
            for aid in (leader, by):
                conn.execute("UPDATE actor_drives SET loyalty=.56, aggression=.44, risk_tolerance=.51 WHERE actor_id=?", (aid,))
                conn.execute("UPDATE relationships SET fear=0 WHERE actor_a_id=? AND actor_b_id=?", (aid, me))
            crew = [po._obedience(conn, me, leader, "attack", by, {"intent_kind": "kill", "_call_id": f"order-{i}"}) for i in range(10)]
            assert sum(x in ("yes", "reluctantly") for x in crew) >= 9, crew
            clerk = [po._obedience(conn, me, by, "attack", leader, {"intent_kind": "kill", "_call_id": f"order-{i}"}) for i in range(10)]
            assert sum(x in ("refused", "reluctantly") for x in clerk) >= 9, clerk

            # 1: rank. As underboss he cannot order or remove the boss above him
            conn.execute("UPDATE underworld_personnel SET role_kind='underboss' WHERE actor_id=?", (me,))
            conn.execute("UPDATE underworld_organizations SET current_leader_actor_id=? WHERE id=?", (leader, outfit))
            conn.execute("UPDATE underworld_personnel SET role_kind='boss' WHERE actor_id=?", (leader,))
            for details in ({"into": f"outfit:{outfit}", "role": "none"}, {"into": f"outfit:{outfit}", "role": "member"}):
                r = po.execute(conn, me, "hire", target_actor_id=leader, details=details, intent="x")
                assert r["status"] == "refused", (details, r)
            got = conn.execute("SELECT status,role_kind FROM underworld_personnel WHERE actor_id=?", (leader,)).fetchone()
            assert (got[0], got[1]) == ("active", "boss"), tuple(got)
            r = po.execute(conn, me, "order", target_actor_id=leader, details={"do": "pay", "to": "me", "amount": "small"}, intent="x")
            assert r["status"] == "refused" and "subordinate" in r["summary"], r
            # as a factor of a business he cannot remove or demote the owner
            conn.execute("UPDATE civilian_enterprises SET owner_actor_id=? WHERE id=?", (leader, biz))
            add_enterprise_staff(conn, biz, leader, role="owner", authority=100)
            add_enterprise_staff(conn, biz, me, role="factor", authority=60)
            for role in ("none", "clerk"):
                r = po.execute(conn, me, "hire", target_actor_id=leader, details={"into": f"business:{biz}", "role": role}, intent="x")
                assert r["status"] == "refused", (role, r)
            assert conn.execute("SELECT authority FROM enterprise_staff WHERE enterprise_id=? AND actor_id=?", (biz, leader)).fetchone()[0] == 100
    print("player_operations review fixes passed")


if __name__ == "__main__":
    run()
    run_review_fixes()
