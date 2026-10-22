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
                                   AND operation_kind IN ('warn_protection_poacher','retaliate_protection_poach','negotiate_protection_poach','warn_aggressor','retaliate_aggression','negotiate_aggression','hostile_move','negotiate_settlement','targeted_hit','challenge_zone')""", (rival, outfit)).fetchall()
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
        from engine.underworld_rebuild import create_personnel
        s0 = ledger.balance(conn, ("person", servant)); cl = create_personnel(conn, outfit, role_kind="accountant"); c0 = ledger.balance(conn, ("person", cl))
        low = 1e9
        for _ in range(6):
            advance_connection(conn, 30)
            low = min(low, conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0])
        assert low >= 0
        t = conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0]
        assert t > 0, f"ordinary outfit ended in the red: {t}"
        assert ledger.balance(conn, ("person", cl)) > c0, "the keeper of accounts was never paid"
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
        from engine.underworld_rebuild import create_personnel
        for _ in range(3):
            create_personnel(conn, outfit, role_kind="enforcer")
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
        r = po.execute(conn, me, "pay", target_actor_id=None, details={"from": "me", "to": "wages", "for": f"outfit:{outfit}", "amount": "token"}, intent="I pay the retainers something.")
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
        members = [create_personnel(conn, outfit, role_kind="enforcer") for _ in range(5)]
        terms = []
        for i in range(8):  # one draw proves nothing: a household of servants shows the rate
            terms.append(add_service_term(conn, hh, _reveal(conn, loc, f"fixture servant {i}", min_age=20, max_age=50), "servant"))
        conn.commit()
        advance_connection(conn, 31)  # one good month: the crews learn what their rackets give them
        crews0 = conn.execute("SELECT AVG(loyalty) FROM underworld_crews WHERE organization_id=?", (outfit,)).fetchone()[0]
        conn.execute("UPDATE underworld_racket_sites SET status='abandoned' WHERE organization_id=?", (outfit,))
        conn.execute("UPDATE underworld_organizations SET treasury=0,monthly_leader_draw_rate=0 WHERE id=?", (outfit,))
        conn.execute("UPDATE households SET liquidity=0,wealth=40 WHERE id=?", (hh,))
        conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=0 WHERE actor_id=?", (w["me"],))
        conn.execute("UPDATE resources SET amount=0 WHERE actor_id=? AND resource_type='cash'", (w["me"],))
        for e in w["fronts"]:
            conn.execute("UPDATE civilian_enterprises SET status='closed' WHERE id=?", (e,))
        conn.commit()
        advance_connection(conn, 125)
        assert "behind on pay" in ly.outfit_mood(conn, outfit), ly.outfit_mood(conn, outfit)
        assert not any(ch.isdigit() for ch in ly.outfit_mood(conn, outfit))
        crews = conn.execute("SELECT AVG(loyalty) FROM underworld_crews WHERE organization_id=?", (outfit,)).fetchone()[0]
        assert crews < crews0 - 8, ("crews whose rackets were lost grew less loyal", crews0, crews)
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
        gone_n = conn.execute("SELECT COUNT(*) FROM household_service_terms WHERE id IN (%s) AND status='former'" % ",".join(map(str, terms))).fetchone()[0]
        print("unpaid servants who left:", gone_n, "of", len(terms))
        assert 3 <= gone_n, ("unpaid servants mostly stayed", gone_n)
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
        assert n <= 2, ("a paid outfit lost more than background turnover to desertion, defection, informing or theft", n)
        avg = conn.execute("SELECT AVG(loyalty) FROM underworld_crews WHERE organization_id=?", (w["outfit"],)).fetchone()[0]
        assert avg >= 55, avg
    print("loyalty ok")


# ---------------------------------------------------------------------------------------------------------------
# Fix pass (review 2026-10-17): findings C1, C2, I1-I8, M1-M5
# ---------------------------------------------------------------------------------------------------------------

def fix_payroll():
    """I4 business wages are not charged twice; I5 household arrears are not forgiven between closings; M1 no digits."""
    from engine import payroll, ledger
    from engine.household_life import add_service_term
    from fixtures_protagonist import make_fane, _reveal
    with world() as conn:
        w = make_fane(conn, legacy=False)
        eid = w["fronts"][0]
        conn.execute("UPDATE civilian_enterprises SET cash=10,debt=5 WHERE id=?", (eid,))
        payroll.set_arrears(conn, "business", eid, 2, 2.0)
        payroll.run_business_payroll(conn, eid, 1.0, 0.0)
        cash, debt = conn.execute("SELECT cash,debt FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()
        spent = 10 - cash
        assert spent > 0.01, spent
        assert abs((5 - debt) - spent) < 1e-6, ("catch-up wages paid from cash must discharge the capitalised debt", cash, debt)
        # paying the staff's arrears by order discharges it too
        conn.execute("UPDATE civilian_enterprises SET cash=10,debt=5 WHERE id=?", (eid,))
        payroll.set_arrears(conn, "business", eid, 2, 2.0)
        ledger._credit(conn, ("person", w["me"]), 50.0)
        paid = payroll.pay_arrears(conn, "business", eid, ("person", w["me"]), 1.5)
        assert paid > 0
        assert abs(conn.execute("SELECT debt FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()[0] - (5 - paid)) < 1e-6
    with world() as conn:
        w = make_fane(conn, legacy=False)
        hh, loc = w["household"], w["location"]
        servant = _reveal(conn, loc, "fixture servant", min_age=20, max_age=50)
        add_service_term(conn, hh, servant, "servant")
        conn.execute("UPDATE households SET liquidity=0,wealth=0 WHERE id=?", (hh,))
        conn.execute("UPDATE resources SET amount=0 WHERE actor_id=? AND resource_type='cash'", (w["me"],))
        conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=0 WHERE actor_id=?", (w["me"],))
        for d in range(9):  # the books close every ten days for three months
            h = conn.execute("SELECT * FROM households WHERE id=?", (hh,)).fetchone()
            payroll.run_household_payroll(conn, h, 10, 10 * (d + 1))
        a = payroll.get_arrears(conn, "household", hh)
        assert a["months"] >= 2, ("unpaid for ninety days must read as two or more months", a)
    for n in (1, 2, 3, 4, 7, 12):
        assert not any(ch.isdigit() for ch in payroll.arrears_words(n)), payroll.arrears_words(n)
    print("fix_payroll ok")


def fix_loyalty_paths():
    """I6 only a boss's own mistreatment counts; I7 a defector stops leading his crew; M3 desertion is a flow, defection is an incident
    the victim can answer, a rival is a plausible one and never the player's outfit."""
    from engine import loyalty as ly
    from engine.harm import record_harm
    from engine.underworld_decisions import underworld_decision_candidates
    from engine.underworld_rebuild import create_personnel
    from fixtures_protagonist import make_fane, _reveal
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit, rival, loc = w["outfit"], w["rivals"][0], w["location"]
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        theirs = create_personnel(conn, rival, role_kind="member")
        mine = create_personnel(conn, outfit, role_kind="member")
        record_harm(conn, theirs, source_kind="player_operation", source_ref_id=11, severity=40, intent_class="hostile", metadata={})
        assert ly.mistreated_count(conn, rival, day) == 0, "the player beating a rival's man is not that rival's mistreatment of its own"
        record_harm(conn, mine, source_kind="player_operation", source_ref_id=12, severity=40, intent_class="hostile", metadata={})
        assert ly.mistreated_count(conn, outfit, day) >= 1, "the boss's own blow on his own man is mistreatment"
        other = create_personnel(conn, outfit, role_kind="member")
        n0 = ly.mistreated_count(conn, outfit, day)
        record_harm(conn, other, source_kind="underworld_beating", source_ref_id=13, severity=40, intent_class="hostile",
                    metadata={"source_organization_id": rival})
        assert ly.mistreated_count(conn, outfit, day) == n0, "a rival's beating is not the head's mistreatment"
        # servants: only the player's own household head counts
        servant = _reveal(conn, loc, "fixture servant", min_age=20, max_age=50)
        record_harm(conn, servant, source_kind="player_operation", source_ref_id=14, severity=40, intent_class="hostile", metadata={})
        other_hh = int(conn.execute("SELECT id FROM households WHERE id<>? AND status='active' ORDER BY id LIMIT 1", (w["household"],)).fetchone()[0])
        assert ly.household_mistreated(conn, other_hh, servant, day) == 0
        assert ly.household_mistreated(conn, w["household"], servant, day) >= 1
        # I7
        crew_leader, crew = w["crew_leader"], w["crew"]
        assert conn.execute("SELECT leader_actor_id FROM underworld_crews WHERE id=?", (crew,)).fetchone()[0] == crew_leader
        ly.defect(conn, crew_leader, outfit, rival, day)
        assert conn.execute("SELECT leader_actor_id FROM underworld_crews WHERE id=?", (crew,)).fetchone()[0] != crew_leader, "the defector still leads his old crew"
        # M3 desertion is a membership flow
        deserter = create_personnel(conn, outfit, role_kind="member")
        f0 = conn.execute("SELECT COUNT(*) FROM underworld_membership_flows WHERE organization_id=? AND flow_kind='desistance'", (outfit,)).fetchone()[0]
        ly.desert(conn, deserter, outfit, day, loc)
        assert conn.execute("SELECT COUNT(*) FROM underworld_membership_flows WHERE organization_id=? AND flow_kind='desistance'", (outfit,)).fetchone()[0] == f0 + 1
        # rival choice: never an ally, never the player's outfit
        others = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_organizations WHERE primary_location_id=? AND status='active' AND id<>?", (loc, rival))]
        for o in others:
            a, b = sorted((o, rival))
            conn.execute("""INSERT INTO underworld_relations(organization_a_id,organization_b_id,relation_kind,hostility,respect,tribute_rate,started_day,last_changed_day,metadata_json)
                            VALUES (?,?,'ally',0,50,0,0,0,'{}') ON CONFLICT(organization_a_id,organization_b_id) DO UPDATE SET relation_kind='ally',hostility=0""", (a, b))
        pick = ly._rival_in_city(conn, rival, loc)
        assert pick is None, ("only allies in town: no rival to go over to", pick)
        a, b = sorted((outfit, rival))
        conn.execute("UPDATE underworld_relations SET relation_kind='neutral' WHERE organization_a_id=? AND organization_b_id=?", (a, b))
        assert ly._rival_in_city(conn, rival, loc) != outfit, "a defector went to the player's outfit without his order"
        # DEC-01 sees a defection as an incident it can answer
        r_leader = int(conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (rival,)).fetchone()[0])
        conn.execute("""INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
                        VALUES (?,NULL,?,?,'defection',45,'open','{}')""", (day, others[0], rival))
        conn.commit()
        cands = underworld_decision_candidates(conn, r_leader, "STRATEGIC", day, {"drives": {}})
        assert any(c.payload.get("source_organization_id") == others[0] and c.action_kind != "seek_truce" for c in cands), [c.action_kind for c in cands]
    print("fix_loyalty_paths ok")


def fix_words():
    """M4: answers to wider incidents are not called poaching."""
    from engine.underworld_decisions import underworld_decision_candidates
    from fixtures_protagonist import make_fane
    with world() as conn:
        w = make_fane(conn, legacy=False)
        target, source = w["rivals"][0], w["rivals"][1]
        t_leader = int(conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (target,)).fetchone()[0])
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        for kind in ("attack_on_member", "attack_on_client", "extortion_attempt", "territorial_challenge"):
            conn.execute("""INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
                            VALUES (?,NULL,?,?,?,50,'open','{}')""", (day, source, target, kind))
        conn.commit()
        cands = [c for c in underworld_decision_candidates(conn, t_leader, "STRATEGIC", day, {"drives": {}}) if c.payload.get("incident_id")]
        assert cands, "no answer to the wider incidents"
        for c in cands:
            assert "poach" not in c.action_kind and "poach" not in c.rationale.lower() and "poach" not in c.key, (c.action_kind, c.rationale)
        conn.execute("DELETE FROM underworld_incidents WHERE incident_kind<>'protection_poach'")
        conn.execute("""INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
                        VALUES (?,NULL,?,?,'protection_poach',50,'open','{}')""", (day, source, target))
        conn.commit()
        assert any("poach" in c.rationale.lower() for c in underworld_decision_candidates(conn, t_leader, "STRATEGIC", day, {"drives": {}}) if c.payload.get("incident_id"))
    print("fix_words ok")


def fix_bonds():
    """C2 (owner ruling): loyalty is bonds first and pay second. Kin, sworn, disciple and retainer families, years of service,
    shared fights and the regional culture make a bond; bonds damp the effect of arrears; grievances move bonded people;
    the hazard is smooth, and betrayal costs standing."""
    from engine import loyalty as ly
    from engine.harm import record_harm
    from engine.underworld_canon import HEARTH_CITIES
    from engine.underworld_rebuild import create_personnel
    from fixtures_protagonist import make_fane
    # the shape of the hazard
    hire, sworn = ly.leave_hazard(0.10, 3.0, 0.0), ly.leave_hazard(0.85, 3.0, 0.0)
    assert hire > 8 * sworn and hire > 0.1, (hire, sworn)
    assert ly.leave_hazard(0.85, 0.0, 0.0) < 0.002
    prev = ly.leave_hazard(0.3, 0.0, 0.0)
    for i in range(1, 60):  # smooth: monotone with months unpaid, no threshold jump
        h = ly.leave_hazard(0.3, i / 10.0, 0.0)
        assert h >= prev and h - prev < 0.03, (i, h, prev)
        prev = h
    prev = ly.leave_hazard(0.7, 0.0, 0.0)
    for i in range(1, 41):
        h = ly.leave_hazard(0.7, 0.0, i / 40.0)
        assert h >= prev and h - prev < 0.03, (i, h, prev)
        prev = h
    assert ly.leave_hazard(0.8, 0.0, 0.55) > 0.08, "a humiliated, bonded man is a real risk even when paid"
    assert ly.leave_hazard(0.8, 0.0, 0.55) > 8 * ly.leave_hazard(0.8, 0.0, 0.0)
    with world() as conn:
        # regional culture
        def city(owner):
            r = conn.execute("""SELECT l.id FROM underworld_organizations o JOIN locations l ON l.id=o.primary_location_id
                                WHERE o.status='active' AND l.political_owner=? ORDER BY l.id LIMIT 1""", (owner,)).fetchone()
            return int(r[0])
        hearth = int(conn.execute("SELECT id FROM locations WHERE name=?", (sorted(HEARTH_CITIES)[0],)).fetchone()[0])
        c_h, c_d, c_w, c_s = (ly.culture_bond(conn, x) for x in (hearth, city("Dunmoor"), city("Windmere"), city("Sunreach Confederacy")))
        assert c_h > c_w + 0.2 and c_d > c_w + 0.2 and c_h > c_s and c_d > c_s, (c_h, c_d, c_w, c_s)
        # the same months unpaid cost a Windmere outfit more men than a Hearth or Dunmoor one
        assert ly.leave_hazard(c_w, 3.0, 0.0) > 1.5 * ly.leave_hazard(c_h, 3.0, 0.0)
        assert ly.leave_hazard(c_w, 3.0, 0.0) > 1.5 * ly.leave_hazard(c_d, 3.0, 0.0)
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit, rival, me = w["outfit"], w["rivals"][0], w["me"]
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        kin = create_personnel(conn, outfit, role_kind="member", membership_status="member")
        conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?, 'parent','recognized',-9000)", (me, kin))
        sw = create_personnel(conn, outfit, role_kind="member", membership_status="sworn_member")
        hired = create_personnel(conn, outfit, role_kind="member", membership_status="employee")
        ctx = ly.outfit_context(conn, outfit, day)
        rows = {a: conn.execute("SELECT * FROM underworld_personnel WHERE actor_id=?", (a,)).fetchone() for a in (kin, sw, hired)}
        b_k, b_s, b_h = (ly.bond_strength(conn, ctx, rows[a], day) for a in (kin, sw, hired))
        assert b_k > b_h + 0.1 and b_s > b_h + 0.1 and (b_k + b_s) / 2 > b_h + 0.2, (b_k, b_s, b_h)
        assert 0.0 <= b_h and b_k <= 1.0
        # grievances: cruelty from the head, a dead comrade nobody avenged, defeats
        g0 = ly.grievance(conn, outfit, day)
        record_harm(conn, sw, source_kind="player_operation", source_ref_id=21, severity=40, intent_class="hostile", metadata={})
        dead = create_personnel(conn, outfit, role_kind="member")
        record_harm(conn, dead, source_kind="underworld_hit", source_ref_id=22, severity=100, intent_class="lethal",
                    metadata={"source_organization_id": rival}, outcome_override="fatal")
        g1 = ly.grievance(conn, outfit, day)
        assert g1["cruelty"] > g0["cruelty"] and g1["unavenged"] > 0 and g1["total"] > g0["total"] + 0.3, (g0, g1)
        assert ly.leave_hazard(b_s, 0.0, g1["total"]) > 5 * ly.leave_hazard(b_s, 0.0, g0["total"])
        # avenging the dead eases it
        conn.execute("""INSERT INTO underworld_operations(organization_id,day,operation_kind,target_organization_id,result,success,metadata_json)
                        VALUES (?,?, 'hostile_move',?,'won',1,'{}')""", (outfit, day, rival))
        assert ly.grievance(conn, outfit, day)["unavenged"] < g1["unavenged"]
        # betrayal costs standing: the old head resents him, the outfit taking him in does not trust him
        from engine.relationships import ensure_relationship
        ly.defect(conn, sw, outfit, rival, day)
        new_head = int(conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (rival,)).fetchone()[0])
        rel = conn.execute("SELECT trust,resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (new_head, sw)).fetchone()
        base = conn.execute("SELECT trust FROM relationships WHERE id=?", (ensure_relationship(conn, new_head, kin, day),)).fetchone()
        assert rel is not None and rel["trust"] < base["trust"], (dict(rel) if rel else None, dict(base))
        old = conn.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (me, sw)).fetchone()
        assert old is not None and old["resentment"] > 15, dict(old) if old else None
    print("fix_bonds ok")


def fix_bond_flows():
    """C2: stipended people unpaid for months: hirelings leave and sworn kin mostly stay; with nothing wrong and pay on time a bonded man never goes over."""
    from engine import loyalty as ly
    from engine.underworld_rebuild import create_personnel
    from fixtures_protagonist import make_fane
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit, me = w["outfit"], w["me"]
        sworn = [create_personnel(conn, outfit, role_kind="enforcer", membership_status="sworn_member") for _ in range(10)]
        hired = [create_personnel(conn, outfit, role_kind="enforcer", membership_status="employee") for _ in range(10)]
        for a in sworn[:5]:
            conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?, 'sibling','recognized',-9000)", (me, a))
        conn.commit()
        day0 = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        for m in range(1, 13):  # a year with every wage paid and nothing wrong
            ly.outfit_morale(conn, outfit, 0, day0 + 30 * m)
        gone = lambda grp: sum(1 for a in grp if conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (a, outfit)).fetchone() is None)
        assert gone(sworn) <= 1, "bonded men left a paid, untroubled outfit"
        assert conn.execute("SELECT COUNT(*) FROM underworld_incidents WHERE incident_kind='defection' AND target_organization_id=?", (outfit,)).fetchone()[0] <= 1
        for m in range(13, 21):  # then eight months with no pay
            ly.outfit_morale(conn, outfit, 2 + (m - 13) // 2, day0 + 30 * m)
        g_h, g_s = gone(hired), gone(sworn)
        assert g_h >= 4 and g_h > g_s + 2, ("unpaid, hirelings must leave far more than bonded men", g_h, g_s)
    print("fix_bond_flows ok")


def _two_crew_outfit(conn, w):
    """Three crews of the fixture outfit, each working one racket and each with three named earners."""
    from engine.underworld_rebuild import _insert_economic_interest, create_crew, create_personnel
    outfit = w["outfit"]
    rackets = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_racket_sites WHERE organization_id=? AND status='active' ORDER BY id", (outfit,))]
    assert len(rackets) >= 3, rackets
    crews = [w["crew"], create_crew(conn, outfit, "Second Crew", size_estimate=6), create_crew(conn, outfit, "Third Crew", size_estimate=6)]
    conn.execute("UPDATE economic_interests SET status='ended' WHERE interest_kind='operator' AND target_racket_id IN (%s)" % ",".join(str(r) for r in rackets))
    for c, r in zip(crews, rackets):
        _insert_economic_interest(conn, interest_kind="operator", holder_crew_id=c, target_racket_id=r, metadata={})
        for _ in range(3):
            create_personnel(conn, outfit, role_kind="member", crew_id=c)
    conn.commit()
    return crews, rackets


def fix_earners():
    """Owner ruling (mafia pay): rank and file earn from the rackets they work and kick a part up; a suppressed racket costs that
    crew, not the others; a raised kick-up raises the treasury and lowers earner loyalty, damped by bonds; only stipended
    people (accountant, house enforcers, retainers) fall into arrears, and only from an empty treasury."""
    from engine import loyalty as ly, payroll
    from engine.simulation import advance_connection
    from engine.underworld_rebuild import create_personnel, kick_rate, monthly_net_estimate, set_kick_rate, set_racket_status
    from fixtures_protagonist import make_fane
    # a racket suppressed hurts only the crew that works it
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit = w["outfit"]
        crews, rackets = _two_crew_outfit(conn, w)
        day0 = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        ly.outfit_morale(conn, outfit, 0, day0)
        base = payroll.crew_earnings(conn, outfit)
        assert all(base[c] > 0 for c in crews), base
        loy0 = {c: conn.execute("SELECT loyalty FROM underworld_crews WHERE id=?", (c,)).fetchone()[0] for c in crews}
        set_racket_status(conn, rackets[0], "suppressed")
        for m in range(1, 7):
            ly.outfit_morale(conn, outfit, 0, day0 + 30 * m)
        now = payroll.crew_earnings(conn, outfit)
        assert now[crews[0]] < 0.3 * base[crews[0]], (now, base)
        assert abs(now[crews[1]] - base[crews[1]]) < 1e-6 and abs(now[crews[2]] - base[crews[2]]) < 1e-6
        loy = {c: conn.execute("SELECT loyalty FROM underworld_crews WHERE id=?", (c,)).fetchone()[0] for c in crews}
        assert loy[crews[0]] < loy[crews[1]] - 8 and loy[crews[0]] < loy0[crews[0]] - 8, (loy0, loy)
        assert loy[crews[1]] > loy0[crews[1]] - 3 and loy[crews[2]] > loy0[crews[2]] - 3, (loy0, loy)
    # raising the kick-up
    results = {}
    for label, rate in (("control", None), ("raised", 0.66)):
        with world() as conn:
            w = make_fane(conn, legacy=False)
            outfit = w["outfit"]
            crews, rackets = _two_crew_outfit(conn, w)
            day0 = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            ly.outfit_morale(conn, outfit, 0, day0)
            k0 = kick_rate(conn, outfit)
            net0 = monthly_net_estimate(conn, outfit)
            if rate is not None:
                set_kick_rate(conn, outfit, rate)
                assert kick_rate(conn, outfit) == rate
            for m in range(1, 7):
                ly.outfit_morale(conn, outfit, 0, day0 + 30 * m)
            avg = conn.execute("SELECT AVG(loyalty) FROM underworld_crews WHERE organization_id=? AND status='active'", (outfit,)).fetchone()[0]
            results[label] = (monthly_net_estimate(conn, outfit), avg, k0, net0)
    assert results["raised"][0] > results["control"][0] * 1.1, results
    assert results["raised"][1] < results["control"][1] - 4, results
    assert ly.leave_hazard(0.85, 0.0, 0.0, share_drop=0.4) < 0.25 * ly.leave_hazard(0.1, 0.0, 0.0, share_drop=0.4)
    # stipended people fall into arrears from an empty treasury; earners never do
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit = w["outfit"]
        acc = create_personnel(conn, outfit, role_kind="accountant")
        guard = create_personnel(conn, outfit, role_kind="enforcer")
        earners = [create_personnel(conn, outfit, role_kind="member") for _ in range(3)] + [w["crew_leader"]]
        roster = {a for a, _ in payroll.outfit_roster(conn, outfit)}
        assert roster == {acc, guard}, ("only people who earn nothing directly are on the stipend", roster)
        conn.execute("UPDATE underworld_racket_sites SET status='abandoned' WHERE organization_id=?", (outfit,))
        conn.execute("UPDATE underworld_organizations SET treasury=0,monthly_leader_draw_rate=0 WHERE id=?", (outfit,))
        for e in w["fronts"]:
            conn.execute("UPDATE civilian_enterprises SET status='closed' WHERE id=?", (e,))
        conn.commit()
        for _ in range(4):
            advance_connection(conn, 31)
            assert conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0] >= 0
        a = payroll.get_arrears(conn, "outfit", outfit)
        assert a["months"] >= 2 and a["owed"] > 0, a
        n = conn.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='wage' AND source_organization_id=? AND target_actor_id IN (%s)" % ",".join(str(e) for e in earners), (outfit,)).fetchone()[0]
        assert n == 0, "an earner was paid a wage from the treasury"
    print("fix_earners ok")


def fix_bands():
    """C1: hits resolve in outcome bands that lean toward survival; death only when the odds are overwhelming."""
    import random
    from engine import underworld_aggression as ag
    def share(p, lethal, n=1500):
        rng = random.Random(7)
        c = {"failed": 0, "wounded": 0, "maimed": 0, "killed": 0}
        for _ in range(n):
            c[ag.hit_band(p, rng, lethal)] += 1
        return {k: v / n for k, v in c.items()}
    mid = share(0.65, True)
    assert all(mid[k] > 0.02 for k in mid), mid
    assert mid["killed"] < 0.5 * (1 - mid["failed"]), ("most blows that land are not killings", mid)
    assert share(0.3, True)["killed"] < 0.05, share(0.3, True)
    assert share(0.9, True)["killed"] > 2 * mid["killed"]
    assert share(0.9, False)["killed"] < share(0.9, True)["killed"] * 0.3, "a beating is not a killing"
    assert share(0.9, True)["failed"] < share(0.3, True)["failed"]
    print("fix_bands ok")


def fix_player_target():
    """C1: the player is a valid target like anyone else. An attempt on him is a pending incident for the GM to play, never
    resolved off-screen in `advance`; his outfit defends itself and answers in kind but opens nothing without his order; his
    gang can fall apart."""
    import random
    from engine import underworld_aggression as ag
    from engine.interactions import apply_player_response
    from engine.underworld_decisions import execute_underworld_action, underworld_decision_candidates
    from engine.underworld_rebuild import _targeted_hit
    from fixtures_protagonist import make_fane
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit, rival, me = w["outfit"], w["rivals"][0], w["me"]
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        hit_it = None
        for i in range(60):
            _targeted_hit(conn, rival, random.Random(1000 + i), target=outfit)
            hit_it = conn.execute("SELECT * FROM interactions WHERE recipient_actor_id=? AND interaction_type='attack' AND status='pending' ORDER BY id DESC LIMIT 1", (me,)).fetchone()
            if hit_it:
                break
        assert hit_it, "sixty hits on the outfit never reached its boss: the player is immune"
        assert conn.execute("SELECT status FROM actors WHERE id=?", (me,)).fetchone()[0] == "active"
        assert conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE actor_id=? AND source_kind LIKE 'underworld_%'", (me,)).fetchone()[0] == 0, "an attempt on the protagonist resolved off-screen"
        import json
        terms = json.loads(hit_it["terms_json"])
        assert terms.get("underworld_attempt") and terms.get("source_organization_id") == rival and "purpose" in terms
        assert not any(ch.isdigit() for ch in str(terms["purpose"])), terms["purpose"]
        ev = conn.execute("SELECT 1 FROM event_targets t JOIN events e ON e.id=t.event_id WHERE t.actor_id=? AND e.severity>=3 AND e.event_type='underworld_attempt'", (me,)).fetchone()
        assert ev, "the attempt left no event aimed at the protagonist"
        # played out by the GM: yields, flees or fights, all through the same bands
        iid = int(hit_it["id"])
        r = apply_player_response(conn, iid, me, "reject", day)
        assert conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()[0] == "resolved", r
        assert r.summary and not any(ch.isdigit() for ch in r.summary), r.summary
        # his outfit answers an incident in kind but opens no talks and no hostile initiative of its own
        conn.execute("""INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
                        VALUES (?,NULL,?,?,'attack_on_member',55,'open','{"style":"beating"}')""", (day, rival, outfit))
        conn.commit()
        cands = underworld_decision_candidates(conn, me, "STRATEGIC", day, {"drives": {}})
        kinds = {c.action_kind for c in cands}
        assert "retaliate_aggression" in kinds and "warn_aggressor" in kinds, kinds
        assert not (kinds & {"negotiate_aggression", "negotiate_settlement", "seek_truce", "challenge_zone", "occupy_vacant_turf", "poach_protection", "targeted_hit"}), kinds
        c = next(c for c in cands if c.action_kind == "retaliate_aggression")
        res = execute_underworld_action(conn, me, "retaliate_aggression", c.payload, day)
        assert not res.get("blocked"), res
        assert conn.execute("SELECT 1 FROM underworld_operations WHERE organization_id=? AND operation_kind='retaliate_aggression'", (outfit,)).fetchone()
        # unplayed attempts lapse without harm
        iid2 = ag.pending_attempt(conn, me, rival, 0.8, style="hired_killing", lethal=True, day=day)
        assert iid2
        ag.expire_attempts(conn, day + 90)
        assert conn.execute("SELECT status FROM interactions WHERE id=?", (iid2,)).fetchone()[0] == "expired"
        assert conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE actor_id=? AND source_kind LIKE 'underworld_%'", (me,)).fetchone()[0] <= 1
    # his gang can fall apart like anyone's
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit, me = w["outfit"], w["me"]
        conn.execute("UPDATE underworld_organizations SET metadata_json=json_set(COALESCE(metadata_json,'{}'),'$.role','street_gang'),treasury=0 WHERE id=?", (outfit,))
        conn.execute("UPDATE underworld_membership_profiles SET core_members=1,active_members=2 WHERE organization_id=?", (outfit,))
        conn.execute("UPDATE underworld_zone_claims SET status='lost' WHERE organization_id=?", (outfit,))
        conn.commit()
        fell = False
        for d in range(1, 120):
            ag.street_gang_churn(conn, 1000 + 31 * d)
            if conn.execute("SELECT status FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0] == "destroyed":
                fell = True
                break
        assert fell, "the player's weak street gang can never collapse"
        assert conn.execute("SELECT status FROM actors WHERE id=?", (me,)).fetchone()[0] == "active"
    print("fix_player_target ok")


def fix_style_rolls():
    """I2: a beating, smashed premises, seized goods, an abduction or a public example succeed or fail by the strength of the two
    sides, and a failed one costs the attacker men."""
    import random
    from engine import underworld_aggression as ag
    from fixtures_protagonist import make_fane
    with world() as conn:
        w = make_fane(conn, legacy=False)
        a, t = w["outfit"], w["rivals"][0]
        zone = int(conn.execute("SELECT zone_id FROM underworld_zone_claims WHERE organization_id=? AND claim_kind='controller' AND status='active' LIMIT 1", (t,)).fetchone()[0])
        conn.execute("UPDATE underworld_personnel SET status='retired' WHERE actor_id=?", (w["me"],))  # keep the player out of the arithmetic
        conn.commit()

        from engine import temperament as tp
        real = tp.fighting_strength
        strength = {a: 5.0, t: 40.0}
        tp.fighting_strength = lambda c, oid: strength.get(oid, real(c, oid))

        def rate(style, attacker_strength, n=40):
            strength[a] = attacker_strength
            wins = 0
            for i in range(n):
                conn.execute("SAVEPOINT s")
                res = ag.STYLE_FUNCS[style](conn, a, t, zone, random.Random(50 + i))
                wins += 1 if res["win"] else 0
                conn.execute("ROLLBACK TO s"); conn.execute("RELEASE s")
            return wins / n
        try:
            for style in ("beating", "smashed_premises", "seized_goods", "abduction", "public_example"):
                weak, strong = rate(style, 4.0), rate(style, 160.0)
                assert strong - weak > 0.35 and weak < 0.5 and strong > 0.8, (style, weak, strong)
            strength[a] = 4.0
        finally:
            pass
        # a failed move costs the attacker men
        conn.execute("UPDATE underworld_organizations SET violence_capacity=5 WHERE id=?", (a,))
        from engine.underworld import ensure_underworld_membership_profile
        ensure_underworld_membership_profile(conn, a, core_members=4, active_members=12)
        lost = 0
        for i in range(40):
            f0 = conn.execute("SELECT COUNT(*) FROM underworld_membership_flows WHERE organization_id=? AND flow_kind='death_or_incapacitation'", (a,)).fetchone()[0]
            r = ag.hostile_move(conn, a, t, zone, random.Random(900 + i), style="beating", file_contest=False)
            if not r["won"]:
                lost += conn.execute("SELECT COUNT(*) FROM underworld_membership_flows WHERE organization_id=? AND flow_kind='death_or_incapacitation'", (a,)).fetchone()[0] - f0
        assert lost >= 3, "failed moves cost the attacker nothing"
        tp.fighting_strength = real
    print("fix_style_rolls ok")


def fix_grudges():
    """I3: a killing of a crew leader or an ordinary member is remembered too; it is simply smaller than a boss's loss."""
    from engine import temperament as tp
    from engine.harm import record_harm
    from engine.underworld_rebuild import create_personnel
    from fixtures_protagonist import make_fane
    with world() as conn:
        w = make_fane(conn, legacy=False)
        a, r1, r2 = w["outfit"], w["rivals"][0], w["rivals"][1]
        member = create_personnel(conn, a, role_kind="member")
        record_harm(conn, member, source_kind="underworld_beating", source_ref_id=31, severity=100, intent_class="lethal", metadata={"source_organization_id": r1}, outcome_override="fatal")
        g_member = tp.grudge_level(conn, a, r1)
        assert g_member > 0, "a killed member left no grudge"
        record_harm(conn, w["crew_leader"], source_kind="underworld_hit", source_ref_id=32, severity=100, intent_class="lethal", metadata={"source_organization_id": r2}, outcome_override="fatal")
        g_lead = tp.grudge_level(conn, a, r2)
        assert g_lead > g_member * 1.5, (g_lead, g_member)
        assert g_lead < 60, g_lead  # smaller than the loss of a boss or a boss's kin
    print("fix_grudges ok")


def fix_fronts():
    """I8: a front gets a real business and its profit reaches the outfit; the packaged world has no front without a business and no
    opening city business without a person owner."""
    from engine.simulation import advance_connection
    from engine.underworld_rebuild import create_front
    from fixtures_protagonist import make_fane
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit = w["outfit"]
        eid = create_front(conn, outfit, "Fixture Yard", "service", zone_id=None, capital=30, cash=24)
        p = conn.execute("SELECT a.archetype_key FROM enterprise_business_profiles p JOIN business_archetypes a ON a.id=p.archetype_id WHERE p.enterprise_id=?", (eid,)).fetchone()
        assert p is not None and p[0] != "general_store", "the front never became a business"
        conn.commit()
        advance_connection(conn, 120)
        n = conn.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='distribution' AND source_enterprise_id=? AND target_organization_id=?", (eid, outfit)).fetchone()[0]
        assert n >= 1, "the front's profit never reached the outfit"
    with world() as conn:
        bare = conn.execute("""SELECT COUNT(*) FROM civilian_enterprises e WHERE e.metadata_json LIKE '%underworld_front%' AND e.status<>'closed'
                               AND NOT EXISTS (SELECT 1 FROM enterprise_business_profiles p WHERE p.enterprise_id=e.id)""").fetchone()[0]
        assert bare == 0, f"{bare} fronts have no business"
        ownerless = conn.execute("""SELECT COUNT(*) FROM civilian_enterprises e JOIN enterprise_business_profiles p ON p.enterprise_id=e.id
                                    WHERE e.metadata_json LIKE '%procedural_city_business%' AND e.owner_actor_id IS NULL AND e.institution_actor_id IS NULL""").fetchone()[0]
        assert ownerless == 0, f"{ownerless} opening city businesses have no owner"
    print("fix_fronts ok")


def _orgs_by_class(conn):
    from engine import temperament as tp
    out = {}
    for r in conn.execute("SELECT id FROM underworld_organizations WHERE status='active' ORDER BY id"):
        oid = int(r[0])
        out.setdefault(tp.outfit_class(conn, oid), []).append(oid)
    return out


def fix_coercion():
    """I1: outfits that live on coercive rackets hurt their debtors, house workers and shopkeepers, at a rate set by temperament."""
    import random
    from engine import underworld_aggression as ag
    from engine.underworld_rebuild import create_racket_site
    with world() as conn:
        by = _orgs_by_class(conn)
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        gang, spec = by["street"][0], by["specialist"][0]
        for o in (gang, spec):
            conn.execute("UPDATE underworld_racket_sites SET status='abandoned' WHERE organization_id=?", (o,))
            create_racket_site(conn, o, "high-risk debt", zone_id=None, gross_income_per_30=6)
        conn.commit()
        rate = {}
        for label, o in (("gang", gang), ("spec", spec)):
            n = 0
            for i in range(300):
                n += ag.coercion_turn(conn, o, random.Random(i), day)
            rate[label] = n
        assert rate["gang"] >= 8, rate
        assert rate["gang"] > 2 * rate["spec"], ("a street gang squeezes its debtors harder than a lender does", rate)
        harmed = conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE source_kind='underworld_coercion'").fetchone()[0]
        assert harmed >= 8, harmed
        v = conn.execute("SELECT actor_id FROM harm_incidents WHERE source_kind='underworld_coercion' LIMIT 1").fetchone()[0]
        assert conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=?", (v,)).fetchone() is None, "the victim is an ordinary person of the city"
        assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='underworld_coercion'").fetchone()[0] >= 8
    print("fix_coercion ok")


def fix_predation_and_hiring():
    """I1: gangs prey on specialists; wronged specialists buy violence; a hit may follow a high grudge under a nominal peace."""
    import random
    from engine import temperament as tp, underworld_aggression as ag
    from engine.underworld_rebuild import ensure_relation
    with world() as conn:
        by = _orgs_by_class(conn)
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        # a gang and a specialist of the same city
        for gang in by["street"]:
            loc = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?", (gang,)).fetchone()[0]
            spec = conn.execute("""SELECT id FROM underworld_organizations WHERE primary_location_id=? AND status='active' AND json_extract(metadata_json,'$.role')='specialist'
                                   ORDER BY id LIMIT 1""", (loc,)).fetchone()
            if spec:
                spec = int(spec[0]); break
        else:
            raise AssertionError("no gang shares a city with a specialist")
        conn.execute("UPDATE underworld_organizations SET treasury=20 WHERE id=?", (spec,))
        boss = int(conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (gang,)).fetchone()[0])
        cands = ag.aggression_candidates(conn, boss, gang, {"aggression": .8, "patience": .2, "ambition": .8, "pragmatism": .4}, day, 0.0, 0.0, 5.0)
        sq = [c for c in cands if c.action_kind == "squeeze_specialist" and c.payload["target_organization_id"] == spec]
        assert sq, "a gang does not see the specialist next door as prey"
        res = ag.execute_aggression(conn, boss, gang, "squeeze_specialist", sq[0].payload, day)
        assert not res.get("blocked") and res.get("operation_id"), res
        op = conn.execute("SELECT metadata_json FROM underworld_operations WHERE id=?", (res["operation_id"],)).fetchone()[0]
        import json
        assert json.loads(op)["style"] in ("seized_goods", "intimidation", "beating"), op
        # the specialist answers by buying it
        styles = set()
        for i in range(30):
            conn.execute("SAVEPOINT s")
            conn.execute("UPDATE underworld_organizations SET treasury=30 WHERE id=?", (spec,))
            r = ag.retaliate(conn, spec, gang, 0, random.Random(i))
            if r.get("style"):
                styles.add(r["style"])
            conn.execute("ROLLBACK TO s"); conn.execute("RELEASE s")
        assert styles and styles <= {"hired_beating", "hired_killing", "intimidation", "seized_goods", "smashed_premises"}, styles
        assert "beating" not in styles and "assault" not in styles, "a specialist sent its own men"
        # a hit under a nominal peace when the grudge is deep
        a, b = by["street"][0], by["street"][1]
        x, y = sorted((a, b))
        conn.execute("""INSERT INTO underworld_relations(organization_a_id,organization_b_id,relation_kind,hostility,respect,tribute_rate,started_day,last_changed_day,metadata_json)
                        VALUES (?,?,'hostile_peace',96,10,0,0,0,'{}') ON CONFLICT(organization_a_id,organization_b_id) DO UPDATE SET relation_kind='hostile_peace',hostility=96""", (x, y))
        loc = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?", (a,)).fetchone()[0]
        conn.execute("UPDATE underworld_organizations SET primary_location_id=? WHERE id=?", (loc, b))
        boss_a = int(conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (a,)).fetchone()[0])
        drv = {"aggression": .8, "patience": .2, "ambition": .6, "pragmatism": .4}
        none = [c for c in ag.aggression_candidates(conn, boss_a, a, drv, day, 0.0, 0.0, 5.0) if c.action_kind == "targeted_hit" and c.payload["target_organization_id"] == b]
        assert not none, "a hit with no grudge under a nominal peace"
        tp.add_grudge(conn, a, b, 60.0, "kin_killed", None)
        conn.execute("UPDATE underworld_relations SET relation_kind='hostile_peace',hostility=96 WHERE organization_a_id=? AND organization_b_id=?", (x, y))
        hit = [c for c in ag.aggression_candidates(conn, boss_a, a, drv, day, 0.0, 0.0, 5.0) if c.action_kind == "targeted_hit" and c.payload["target_organization_id"] == b]
        assert hit, "a deep grudge never reaches a hit under hostile_peace"
    print("fix_predation_and_hiring ok")


def fix_named_people():
    """I1/migration 114: every outfit has people to hurt, promote and lose, in numbers that follow its size; command follows the sex rule;
    loyalty starts dispersed; the report is there."""
    import json
    from engine import temperament as tp
    with world() as conn:
        rep = json.loads(conn.execute("SELECT value FROM engine_meta WHERE key='schema114_report'").fetchone()[0])
        for k in ("front_profiles_backfilled", "city_business_owners_given", "named_people_seeded", "loyalty_dispersed"):
            assert k in rep, rep
        tiny = bare = 0
        for r in conn.execute("SELECT o.id, COALESCE(m.core_members,0)+COALESCE(m.active_members,0) fullm FROM underworld_organizations o LEFT JOIN underworld_membership_profiles m ON m.organization_id=o.id WHERE o.status='active'"):
            n = conn.execute("SELECT COUNT(*) FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind<>'boss'", (r[0],)).fetchone()[0]
            if r["fullm"] >= 6 and n < 1:
                bare += 1
            if n == 0:
                tiny += 1
        assert bare == 0, f"{bare} outfits of six or more still have no named people but their boss"
        roles = {r[0]: r[1] for r in conn.execute("SELECT role_kind,COUNT(*) FROM underworld_personnel WHERE status='active' GROUP BY 1")}
        for k in ("lieutenant", "enforcer", "accountant"):
            assert roles.get(k, 0) >= 20, roles
        assert sum(roles.values()) >= 200, roles
        # the sex rule for command: mostly men, never all
        sx = conn.execute("""SELECT lp.demographic_sex,COUNT(*) FROM underworld_personnel p JOIN actor_life_profiles lp ON lp.actor_id=p.actor_id
                             WHERE p.status='active' AND p.role_kind IN ('lieutenant','underboss') GROUP BY 1""").fetchall()
        tot = sum(r[1] for r in sx); male = sum(r[1] for r in sx if r[0] == "male")
        assert tot >= 40 and 0.6 <= male / tot <= 0.97, (tot, male)
        # occupation follows Stage among the people drawn: a Breach or Fifth is never an ordinary tradesman
        bad = conn.execute("""SELECT COUNT(*) FROM underworld_personnel p JOIN cultivation_profiles cp ON cp.actor_id=p.actor_id
                              JOIN background_person_profiles b ON b.actor_id=p.actor_id
                              WHERE p.status='active' AND cp.current_stage IN ('Breach','Fifth','Sixth') AND b.occupation_domain IN ('labor','merchant','artisan','hospitality','farming')""").fetchone()[0]
        assert bad == 0, bad
        # loyalty is dispersed, not sixty everywhere
        v = [r[0] for r in conn.execute("SELECT loyalty FROM underworld_crews WHERE status='active'")]
        mean = sum(v) / len(v)
        sd = (sum((x - mean) ** 2 for x in v) / len(v)) ** .5
        assert sd > 4, sd
        assert len({round(x) for x in v}) > 15
        pl = [json.loads(r[0]).get("loyalty") for r in conn.execute("SELECT metadata_json FROM underworld_personnel WHERE status='active' AND role_kind<>'boss'")]
        pl = [x for x in pl if x is not None]
        assert len(pl) > 200 and len({round(x) for x in pl}) > 30
        # high-bond cultures start higher
        hearth = conn.execute("""SELECT AVG(c.loyalty) FROM underworld_crews c JOIN underworld_organizations o ON o.id=c.organization_id JOIN locations l ON l.id=o.primary_location_id
                                 WHERE l.political_owner='Dunmoor'""").fetchone()[0]
        windmere = conn.execute("""SELECT AVG(c.loyalty) FROM underworld_crews c JOIN underworld_organizations o ON o.id=c.organization_id JOIN locations l ON l.id=o.primary_location_id
                                   WHERE l.political_owner='Windmere'""").fetchone()[0]
        assert hearth > windmere + 4, (hearth, windmere)
    print("fix_named_people ok")


TESTS = {"money": money, "ground": ground, "temperament": temperament, "grudge": grudge, "rivals": rivals, "player_traces": player_traces, "pay": pay, "loyalty": loyalty, "fix_payroll": fix_payroll, "fix_loyalty_paths": fix_loyalty_paths, "fix_words": fix_words, "fix_bonds": fix_bonds, "fix_bond_flows": fix_bond_flows, "fix_earners": fix_earners, "fix_bands": fix_bands, "fix_player_target": fix_player_target, "fix_style_rolls": fix_style_rolls, "fix_grudges": fix_grudges, "fix_fronts": fix_fronts, "fix_coercion": fix_coercion, "fix_predation_and_hiring": fix_predation_and_hiring, "fix_named_people": fix_named_people}

if __name__ == "__main__":
    names = sys.argv[1:] or list(TESTS)
    for n in names:
        TESTS[n]()
    print("world_pushes_back_test: ok", names)
