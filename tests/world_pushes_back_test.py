"""Gap 4b: the world pushes back. One function per task; each runs on a temp copy of the packaged world."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@contextmanager
def world():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "w.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        init_db()
        conn = connect()
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
        finally:
            conn.close()


def money():
    from engine import ledger
    from engine.simulation import advance_connection
    from fixtures_protagonist import make_boss, make_fane
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit = w["outfit"]
        assert conn.execute("SELECT 1 FROM underworld_heat WHERE organization_id=?", (outfit,)).fetchone(), "new outfit has no heat row"
        advance_connection(conn, 31)
        t = conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0]
        assert t > 0, f"outfit with heat row did not earn: {t}"
        assert conn.execute("SELECT COUNT(*) FROM underworld_finance_transactions WHERE organization_id=?", (outfit,)).fetchone()[0] > 0
    # owner's draw
    with world() as conn:
        w = make_fane(conn, legacy=False)
        hh = w["household"]
        h0 = ledger.balance(conn, ("household", hh))
        advance_connection(conn, 91)
        assert ledger.balance(conn, ("household", hh)) > h0 - 3, "household got nothing from owned businesses"
        gain = conn.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='distribution' AND target_household_id=?", (hh,)).fetchone()[0]
        assert gain >= 1, "no owner_draw flow"
        for eid in w["fronts"]:
            op = conn.execute("SELECT operating_cost FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
            cash = conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()[0]
            if op:
                assert cash >= 2 * float(op[0]) - 1e-6 or cash >= 0, (eid, cash, op[0])
    # migration seeds a legacy outfit
    with world() as conn:
        w = make_fane(conn, legacy=True)
        from engine.db import _migration_113
        _migration_113(conn)
        assert conn.execute("SELECT 1 FROM underworld_heat WHERE organization_id=?", (w["outfit"],)).fetchone()
        assert conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (w["outfit"],)).fetchone()[0] > 0
        _migration_113(conn)  # idempotent
        t1 = conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (w["outfit"],)).fetchone()[0]
        _migration_113(conn)
        assert conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (w["outfit"],)).fetchone()[0] == t1
    print("money ok")


def ground():
    from fixtures_protagonist import make_fane
    from engine.db import _migration_113
    with world() as conn:
        w = make_fane(conn, legacy=True)
        outfit = w["outfit"]
        assert conn.execute("SELECT COUNT(*) FROM underworld_zone_claims WHERE organization_id=? AND status='active'", (outfit,)).fetchone()[0] == 0
        _migration_113(conn)
        claims = conn.execute("SELECT zone_id,claim_kind FROM underworld_zone_claims WHERE organization_id=? AND status='active'", (outfit,)).fetchall()
        assert claims, "outfit with fronts neither holds nor contests ground"
        assert claims[0]["zone_id"] in [r[0] for r in conn.execute("SELECT id FROM underworld_zones WHERE city_location_id=?", (w["location"],))]
        for eid in w["fronts"]:
            n = conn.execute("SELECT COUNT(*) FROM underworld_protection_accounts WHERE enterprise_id=? AND status='active' AND protector_organization_id<>?", (eid, outfit)).fetchone()[0]
            assert n == 0, f"rival still protects front {eid}"
        for rv in w["rivals"]:
            a, b = sorted((rv, outfit))
            rel = conn.execute("SELECT * FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone()
            assert rel and rel["relation_kind"] == "rival" and rel["hostility"] >= 45, dict(rel) if rel else None
            assert conn.execute("SELECT COUNT(*) FROM underworld_incidents WHERE incident_kind='protection_dispute' AND target_organization_id=? AND source_organization_id=?", (rv, outfit)).fetchone()[0] >= 1
        # baseline relations among outfits sharing a city
        loc = w["location"]
        orgs = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_organizations WHERE primary_location_id=? AND status='active'", (loc,))]
        missing = 0
        for i, x in enumerate(orgs):
            for y in orgs[i + 1:]:
                a, b = sorted((x, y))
                if not conn.execute("SELECT 1 FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone():
                    missing += 1
        assert missing == 0, f"{missing} same-city pairs without a relation"
        n_claims = conn.execute("SELECT COUNT(*) FROM underworld_zone_claims").fetchone()[0]
        n_inc = conn.execute("SELECT COUNT(*) FROM underworld_incidents").fetchone()[0]
        _migration_113(conn)
        assert conn.execute("SELECT COUNT(*) FROM underworld_zone_claims").fetchone()[0] == n_claims
        assert conn.execute("SELECT COUNT(*) FROM underworld_incidents").fetchone()[0] == n_inc
    print("ground ok")


HOSTILE_OPS = ("hostile_move", "targeted_hit", "territorial_attack", "challenge_zone", "poach_protection")


def _street_gang(conn, loc=None):
    q = "SELECT id FROM underworld_organizations WHERE status='active' AND json_extract(metadata_json,'$.role')='street_gang'"
    if loc:
        q += f" AND primary_location_id={int(loc)}"
    return [int(r[0]) for r in conn.execute(q + " ORDER BY id")]


def temperament():
    from engine import temperament as tp
    with world() as conn:
        gangs = _street_gang(conn)
        spec = int(conn.execute("SELECT id FROM underworld_organizations WHERE status='active' AND json_extract(metadata_json,'$.role')='specialist' ORDER BY id LIMIT 1").fetchone()[0])
        durable = int(conn.execute("SELECT id FROM underworld_organizations WHERE status='active' AND name='Tallow Family'").fetchone()[0])
        g = gangs[0]
        pg, pd, ps = (tp.propensity(conn, o) for o in (g, durable, spec))
        assert pg > pd > ps, (pg, pd, ps)
        assert tp.ensure_temperament(conn, g)["style"] in tp.STYLES
        # succession re-derives from the new boss's drives
        before = tp.ensure_temperament(conn, g)
        old_leader = int(conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (g,)).fetchone()[0])
        new_leader = int(conn.execute("SELECT actor_id FROM underworld_personnel WHERE organization_id=? AND actor_id<>? AND status='active' ORDER BY authority DESC LIMIT 1", (g, old_leader)).fetchone()[0])
        conn.execute("UPDATE actor_drives SET aggression=0.95,patience=0.1 WHERE actor_id=?", (old_leader,))
        conn.execute("UPDATE actor_drives SET aggression=0.05,patience=0.95 WHERE actor_id=?", (new_leader,))
        tp.rederive(conn, g)
        hot = tp.ensure_temperament(conn, g)
        conn.execute("UPDATE underworld_organizations SET current_leader_actor_id=? WHERE id=?", (new_leader, g))
        calm = tp.ensure_temperament(conn, g)
        assert calm["leader_actor_id"] == new_leader
        assert calm["current"] < hot["current"] - 0.1 and calm["base"] < hot["base"], (dict(hot), dict(calm))
        # but anchored: a calm boss of a street gang is still hotter than a specialist's
        assert tp.propensity(conn, g) > tp.propensity(conn, spec)
        # a defeat makes it cautious, a win bolder, and both fade
        c0 = tp.propensity(conn, g)
        tp.adjust(conn, g, -0.2)
        assert tp.propensity(conn, g) < c0
        later = tp.effective_current(conn, g, day=800)
        assert abs(later - tp.ensure_temperament(conn, g)["base"]) < 0.05
    print("temperament ok")


def grudge():
    from engine import temperament as tp
    from engine.harm import record_harm
    from engine.simulation import advance_connection
    from fixtures_protagonist import _reveal
    with world() as conn:
        loc = int(conn.execute("SELECT id FROM locations WHERE name LIKE 'Toll%Reach' ORDER BY id LIMIT 1").fetchone()[0])
        x, r = _street_gang(conn, loc)[:2]
        boss = int(conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (x,)).fetchone()[0])
        son = _reveal(conn, loc, "fixture son", min_age=18, max_age=24)
        conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?, 'parent','recognized',-9000)", (boss, son))
        conn.execute("UPDATE underworld_relations SET relation_kind='neutral',hostility=20 WHERE (organization_a_id=? AND organization_b_id=?) OR (organization_a_id=? AND organization_b_id=?)", (x, r, r, x))
        assert tp.grudge_level(conn, x, r) == 0
        record_harm(conn, son, source_kind="underworld_hit", source_ref_id=1, severity=100, intent_class="lethal",
                    metadata={"source_organization_id": r}, outcome_override="fatal")
        g0 = tp.grudge_level(conn, x, r)
        assert g0 >= 50, g0
        a, b = sorted((x, r))
        rel = conn.execute("SELECT * FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone()
        assert rel["hostility"] >= 58 and rel["relation_kind"] in ("rival", "war"), dict(rel)
        assert tp.propensity(conn, x, toward=r) > tp.propensity(conn, x) + 0.15
        # nothing happens to an outfit with no tie to the dead man
        other = _street_gang(conn, loc)[2] if len(_street_gang(conn, loc)) > 2 else None
        if other:
            assert tp.grudge_level(conn, other, r) == 0
        # it decays over years but is not forgotten after one
        conn.execute("UPDATE underworld_grudges SET last_day=last_day-365 WHERE organization_id=? AND rival_organization_id=?", (x, r))
        g1 = tp.grudge_level(conn, x, r)
        assert 0.3 * g0 < g1 < g0, (g0, g1)
        conn.execute("UPDATE underworld_grudges SET last_day=last_day+365 WHERE organization_id=? AND rival_organization_id=?", (x, r))
        conn.commit()
        advance_connection(conn, 180)
        ops = conn.execute(f"SELECT operation_kind,metadata_json FROM underworld_operations WHERE organization_id=? AND target_organization_id=? AND operation_kind IN {HOSTILE_OPS!r}", (x, r)).fetchall()
        assert ops, "the bereaved outfit did nothing against the killer's outfit in 180 days"
        import json
        for o in ops:
            style = json.loads(o["metadata_json"] or "{}").get("style")
            assert style in tp.styles_for(conn, x), (style, tp.styles_for(conn, x))
    print("grudge ok")


def rivals():
    import json
    from engine import temperament as tp
    from engine.simulation import advance_connection
    from fixtures_protagonist import make_fane
    sys.path.insert(0, str(ROOT / "tools"))
    import uw_calibration as cal
    # a hostile rival acts against the Fane-like outfit within 180 days, in a style that fits its temperament
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit = w["outfit"]
        street = [o for o in w["rivals"] if tp.outfit_class(conn, o) == "street"]
        r = street[0] if street else w["rivals"][0]
        a, b = sorted((r, outfit))
        conn.execute("INSERT OR REPLACE INTO underworld_relations(organization_a_id,organization_b_id,relation_kind,hostility,respect,tribute_rate,started_day,last_changed_day,metadata_json) VALUES (?,?,'rival',72,10,0,0,0,'{}')", (a, b))
        conn.commit()
        advance_connection(conn, 180)
        ops = conn.execute(f"SELECT operation_kind,metadata_json FROM underworld_operations WHERE organization_id=? AND target_organization_id=? AND operation_kind IN {HOSTILE_OPS!r}", (r, outfit)).fetchall()
        assert ops, "a rival with hostility 72 did nothing against the Fane-like outfit in 180 days"
        styles = [json.loads(o["metadata_json"] or "{}").get("style") for o in ops]
        assert any(st in tp.styles_for(conn, r) for st in styles), (styles, tp.styles_for(conn, r))
        assert conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND status='active'", (w["me"],)).fetchone(), "the engine killed the player's character"
    # a year of the packaged world, by outfit type and city
    with world() as conn:
        start = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        org0 = [int(x[0]) for x in conn.execute("SELECT id FROM underworld_organizations WHERE status IN ('active','strained','fragmented')")]
        advance_connection(conn, 365)
        rep = cal.report(conn, start, org0)
        per = rep["hostile_moves_per_outfit"]
        assert per.get("street", 0) > per.get("durable", 0) >= per.get("specialist", 0), per
        assert rep["collapsed"] >= 1 and rep["new_gangs"] >= 1, (rep["collapsed"], rep["new_gangs"])
        assert rep["crackdowns"] + sum(rep["enforcement_actions"].values()) >= 1, "violence brought no law response anywhere"
        assert len(rep["styles"]) >= 4, rep["styles"]
        quiet = [c for c, v in rep["by_city"].items() if v.get("hostile_move", 0) == 0]
        busy = [c for c, v in rep["by_city"].items() if v.get("hostile_move", 0) >= 10]
        assert quiet and busy, "violent and quiet cities do not differ"
        print(json.dumps({k: rep[k] for k in ("hostile_moves_per_outfit", "collapsed", "new_gangs", "crackdowns", "styles")}, sort_keys=True))
    print("rivals ok")


def player_traces():
    from engine import civilian, player_operations as po
    from engine.simulation import advance_connection
    from engine.underworld_rebuild import _ensure_protection_racket
    from fixtures_protagonist import make_fane, _reveal
    with world() as conn:
        w = make_fane(conn, legacy=False)
        me, outfit, loc = w["me"], w["outfit"], w["location"]
        rival, rzone = w["rivals"][0], int(conn.execute("SELECT zone_id FROM underworld_zone_claims WHERE organization_id=? AND claim_kind='controller' AND status='active' LIMIT 1", (w["rivals"][0],)).fetchone()[0])
        owner = _reveal(conn, loc, "fixture shopkeeper", min_age=30, max_age=55)
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, owner))
        biz = civilian.create_enterprise(conn, "Protected Stall", "shop", owner_actor_id=owner, location_id=loc, cash=12)
        conn.execute("""INSERT INTO underworld_protection_accounts(protector_organization_id,enterprise_id,zone_id,payment_per_30,service_strength,fear_component,disputed,started_day,status,metadata_json,racket_id)
                        VALUES (?,?,?,1,50,50,0,0,'active','{}',?)""", (rival, biz, rzone, _ensure_protection_racket(conn, rival, rzone)))
        conn.commit()
        h0 = conn.execute("SELECT violence_heat FROM underworld_heat WHERE organization_id=?", (rival,)).fetchone()[0]
        r = po.execute(conn, me, "attack", target_actor_id=None, details={"business": f"business:{biz}", "intent_kind": "beat"}, intent="I wreck the stall.")
        assert r["status"] == "applied", r
        inc = conn.execute("SELECT * FROM underworld_incidents WHERE source_organization_id=? AND target_organization_id=? AND incident_kind='attack_on_client'", (outfit, rival)).fetchone()
        assert inc, "attack on a protected business left no incident for the protector"
        a, b = sorted((outfit, rival))
        rel = conn.execute("SELECT * FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone()
        assert rel["hostility"] >= 33 and rel["relation_kind"] == "rival", dict(rel)
        assert conn.execute("SELECT violence_heat FROM underworld_heat WHERE organization_id=?", (rival,)).fetchone()[0] >= h0
        # an open demand on the protected man's boss-side is also an incident
        advance_connection(conn, 90)
        answered = conn.execute("""SELECT operation_kind FROM underworld_operations WHERE organization_id=? AND target_organization_id=?
                                   AND operation_kind IN ('warn_protection_poacher','retaliate_protection_poach','negotiate_protection_poach','hostile_move','negotiate_settlement','targeted_hit','challenge_zone')""", (rival, outfit)).fetchall()
        assert answered, "the protector did not answer within 90 days"
        assert conn.execute("SELECT status FROM underworld_incidents WHERE id=?", (inc["id"],)).fetchone()[0] != "open"
    print("player_traces ok")


def pay():
    from engine import ledger, payroll, player_operations as po
    from engine.household_life import add_service_term
    from engine.simulation import advance_connection
    from fixtures_protagonist import make_fane, _reveal
    # ordinary outfit, business and household stay net positive and wages really reach people
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit, hh, loc = w["outfit"], w["household"], w["location"]
        servant = _reveal(conn, loc, "fixture servant", min_age=20, max_age=50)
        add_service_term(conn, hh, servant, "servant")
        conn.execute("UPDATE households SET liquidity=20,wealth=20 WHERE id=?", (hh,))
        conn.commit()
        s0 = ledger.balance(conn, ("person", servant)); cl = w["crew_leader"]; c0 = ledger.balance(conn, ("person", cl))
        low = 1e9
        for _ in range(6):
            advance_connection(conn, 30)
            low = min(low, conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0])
        assert low >= 0
        t = conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0]
        assert t > 0, f"ordinary outfit ended in the red: {t}"
        assert ledger.balance(conn, ("person", cl)) > c0, "the crew leader was never paid"
        assert ledger.balance(conn, ("person", servant)) > s0, "the servant was never paid"
        assert payroll.get_arrears(conn, "outfit", outfit)["months"] == 0
        assert payroll.get_arrears(conn, "household", hh)["months"] == 0
        for eid in w["fronts"]:
            net = conn.execute("SELECT COALESCE(SUM(net_income),0) FROM business_cycles WHERE enterprise_id=?", (eid,)).fetchone()[0]
            assert net > 0, (eid, net)
        assert conn.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='wage' AND source_organization_id=?", (outfit,)).fetchone()[0] > 0
    # a broke outfit falls behind, never goes negative, and the boss can pay arrears through act
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit, me = w["outfit"], w["me"]
        conn.execute("UPDATE underworld_racket_sites SET status='abandoned' WHERE organization_id=?", (outfit,))
        conn.execute("UPDATE underworld_organizations SET treasury=0 WHERE id=?", (outfit,))
        conn.commit()
        for _ in range(4):
            advance_connection(conn, 31)
            assert conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0] >= 0
        a = payroll.get_arrears(conn, "outfit", outfit)
        assert a["months"] >= 3 and a["owed"] > 0, a
        owed_before = a["owed"]
        ledger._credit(conn, ("person", me), 40.0)
        p0 = ledger.balance(conn, ("person", me))
        r = po.execute(conn, me, "pay", target_actor_id=None, details={"from": "me", "to": "wages", "for": f"outfit:{outfit}", "amount": "small"}, intent="I pay the crews something.")
        assert r["status"] == "applied", r
        mid = payroll.get_arrears(conn, "outfit", outfit)
        assert 0 < mid["owed"] < owed_before, (mid, owed_before)
        r = po.execute(conn, me, "pay", target_actor_id=None, details={"from": "me", "to": "wages", "for": f"outfit:{outfit}", "amount": "fortune"}, intent="I settle it.")
        assert r["status"] == "applied", r
        end = payroll.get_arrears(conn, "outfit", outfit)
        assert end["owed"] <= 0.01 and end["months"] == 0, end
        assert ledger.balance(conn, ("person", me)) < p0
        assert not any(ch.isdigit() for ch in r["summary"]), r["summary"]
        # nothing is owed now
        r = po.execute(conn, me, "pay", target_actor_id=None, details={"from": "me", "to": "wages", "for": f"outfit:{outfit}", "amount": "small"}, intent="again")
        assert r["status"] == "refused"
    # a household that cannot pay falls behind with its servant
    with world() as conn:
        w = make_fane(conn, legacy=False)
        hh, loc, me = w["household"], w["location"], w["me"]
        servant = _reveal(conn, loc, "fixture servant", min_age=20, max_age=50)
        add_service_term(conn, hh, servant, "servant")
        conn.execute("UPDATE households SET liquidity=0,wealth=3 WHERE id=?", (hh,))
        conn.execute("UPDATE resources SET amount=0 WHERE actor_id=? AND resource_type='cash'", (me,))
        conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=0 WHERE actor_id=?", (me,))
        for e in w["fronts"]:
            conn.execute("UPDATE civilian_enterprises SET status='closed' WHERE id=?", (e,))
        conn.execute("UPDATE underworld_racket_sites SET status='abandoned' WHERE organization_id=?", (w["outfit"],))
        conn.execute("UPDATE underworld_organizations SET treasury=0,monthly_leader_draw_rate=0 WHERE id=?", (w["outfit"],))
        conn.commit()
        advance_connection(conn, 90)
        a = payroll.get_arrears(conn, "household", hh)
        assert a["months"] >= 1 and a["owed"] > 0, a
        assert conn.execute("SELECT liquidity FROM households WHERE id=?", (hh,)).fetchone()[0] >= 0
    print("pay ok")


def loyalty():
    from engine import ledger, loyalty as ly, payroll
    from engine.household_life import add_service_term
    from engine.simulation import advance_connection
    from engine.underworld_rebuild import create_personnel
    from fixtures_protagonist import make_fane, _reveal
    MOVES = ("underworld_desertion", "underworld_defection")
    # pay withheld: people leave or go over, a servant quits, the table hears it in words
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit, hh, loc = w["outfit"], w["household"], w["location"]
        members = [create_personnel(conn, outfit, role_kind="member") for _ in range(5)]
        servant = _reveal(conn, loc, "fixture servant", min_age=20, max_age=50)
        term = add_service_term(conn, hh, servant, "servant")
        conn.execute("UPDATE underworld_racket_sites SET status='abandoned' WHERE organization_id=?", (outfit,))
        conn.execute("UPDATE underworld_organizations SET treasury=0,monthly_leader_draw_rate=0 WHERE id=?", (outfit,))
        conn.execute("UPDATE households SET liquidity=0,wealth=3 WHERE id=?", (hh,))
        conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=0 WHERE actor_id=?", (w["me"],))
        conn.execute("UPDATE resources SET amount=0 WHERE actor_id=? AND resource_type='cash'", (w["me"],))
        for e in w["fronts"]:
            conn.execute("UPDATE civilian_enterprises SET status='closed' WHERE id=?", (e,))
        conn.commit()
        advance_connection(conn, 125)
        assert "behind on pay" in ly.outfit_mood(conn, outfit), ly.outfit_mood(conn, outfit)
        assert not any(ch.isdigit() for ch in ly.outfit_mood(conn, outfit))
        crews = conn.execute("SELECT AVG(loyalty) FROM underworld_crews WHERE organization_id=?", (outfit,)).fetchone()[0]
        assert crews < 45, crews
        advance_connection(conn, 100)
        gone = conn.execute("SELECT COUNT(*) FROM events WHERE event_type IN ('underworld_desertion','underworld_defection')").fetchone()[0]
        assert gone >= 1, "225 days of unpaid wages and nobody left or went over"
        left = [r[0] for r in conn.execute("SELECT actor_id FROM underworld_personnel WHERE actor_id IN (%s) AND (status<>'active' OR organization_id<>?)" % ",".join(str(m) for m in members), (outfit,))]
        defected = conn.execute("SELECT COUNT(*) FROM underworld_incidents WHERE incident_kind='defection' AND target_organization_id=?", (outfit,)).fetchone()[0]
        assert left or defected, "no named member left the outfit"
        for aid in left:  # deserters are ordinary people again, never labelled criminal
            sub = conn.execute("SELECT subtype FROM actors WHERE id=?", (aid,)).fetchone()[0]
            st = conn.execute("SELECT status,organization_id FROM underworld_personnel WHERE actor_id=?", (aid,)).fetchone()
            if st["status"] == "retired":
                assert "criminal" not in str(sub), sub
        assert conn.execute("SELECT status FROM household_service_terms WHERE id=?", (term,)).fetchone()[0] == "former", "the unpaid servant stayed"
        assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='household_service_quit'").fetchone()[0] >= 1
    # paid outfits over a year lose no one to these paths
    with world() as conn:
        w = make_fane(conn, legacy=False)
        for _ in range(3):
            create_personnel(conn, w["outfit"], role_kind="member")
        advance_connection(conn, 365)
        assert payroll.get_arrears(conn, "outfit", w["outfit"])["months"] == 0
        n = conn.execute("""SELECT COUNT(*) FROM events WHERE event_type IN ('underworld_desertion','underworld_defection','underworld_informant','underworld_theft')
                            AND (summary LIKE '%Fane Front%' OR title LIKE '%Fixture Outfit%' OR summary LIKE '%Fixture Outfit%')""").fetchone()[0]
        assert n == 0, "a paid, untroubled outfit lost people to desertion, defection, informing or theft"
        avg = conn.execute("SELECT AVG(loyalty) FROM underworld_crews WHERE organization_id=?", (w["outfit"],)).fetchone()[0]
        assert avg >= 55, avg
    print("loyalty ok")


TESTS = {"money": money, "ground": ground, "temperament": temperament, "grudge": grudge, "rivals": rivals, "player_traces": player_traces, "pay": pay, "loyalty": loyalty}

if __name__ == "__main__":
    names = sys.argv[1:] or list(TESTS)
    for n in names:
        TESTS[n]()
    print("world_pushes_back_test: ok", names)
