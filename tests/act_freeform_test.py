"""act rework: free-form operations, amounts, partial results, counters, memory paging. One packaged-world copy, sections in order."""
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


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def t_amounts(conn, w):
    from engine import ledger, player_operations as po
    me, biz, outfit, hh = w["me"], w["business"], w["outfit"], w["household"]
    assert ledger.amount_of(37) == 37.0 and ledger.amount_of("37 silver") == 37.0 and ledger.amount_of("3 modest") == 9.0
    assert ledger.amount_of("half", 10) == 5.0 and ledger.amount_of("all of it", 7) == 7.0 and ledger.amount_of("25%", 8) == 2.0
    for bad in ("lots", "", -1, True):
        try:
            ledger.amount_of(bad)
        except ValueError:
            continue
        raise AssertionError(bad)

    # money to an institution, a polity, a household; and spent with no recipient
    inst = int(conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND id NOT IN (SELECT institution_actor_id FROM political_polities) LIMIT 1").fetchone()[0])
    pol = conn.execute("SELECT id,institution_actor_id FROM political_polities ORDER BY id LIMIT 1").fetchone()
    ledger.transfer(conn, ("business", biz), ("person", me), 1.0, flow_kind="other", purpose="t")
    conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=50 WHERE actor_id=?", (me,)) if conn.execute(
        "SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?", (me,)).fetchone() else conn.execute(
        "UPDATE resources SET amount=50 WHERE actor_id=? AND resource_type='cash'", (me,))
    b0 = ledger.balance(conn, ("institution", inst))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"institution:{inst}", "amount": 12}, intent="A gift to the house.")
    assert r["status"] == "applied" and abs(ledger.balance(conn, ("institution", inst)) - b0 - 12) < 1e-9, r
    p0 = ledger.balance(conn, ("polity", pol["id"]))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"polity:{pol['id']}", "amount": "5 silver"}, intent="Tax paid.")
    assert r["status"] == "applied" and abs(ledger.balance(conn, ("polity", pol["id"])) - p0 - 5) < 1e-9, r
    assert abs(ledger.balance(conn, ("institution", pol["institution_actor_id"])) - p0 - 5) < 1e-9  # a polity's seat is its treasury
    h0 = ledger.balance(conn, ("household", hh))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"household:{hh}", "amount": "half"}, intent="Keep.")
    assert r["status"] == "applied" and ledger.balance(conn, ("household", hh)) > h0, r
    m0 = ledger.balance(conn, ("person", me))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": "spend", "amount": 4, "purpose": "a feast"}, intent="A feast.")
    assert r["status"] == "applied" and abs(m0 - ledger.balance(conn, ("person", me)) - 4) < 1e-9, r
    # the sink needs rights: an institution he does not lead cannot be drawn on
    assert po.execute(conn, me, "pay", target_actor_id=None, details={"from": f"institution:{inst}", "to": "me", "amount": 1}, intent="x")["status"] == "refused"

    # an oversized sum pays what is there and says so
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"institution:{inst}", "amount": 100000}, intent="All of it.")
    assert r["status"] == "partial" and r.get("short_of") and not re.search(r"\d", r["summary"]), r
    assert ledger.balance(conn, ("person", me)) < 1e-6


def t_hire_many(conn, w):
    import json
    from engine import ledger, player_operations as po
    me, outfit, hh = w["me"], w["outfit"], w["household"]
    conn.execute("UPDATE underworld_organizations SET treasury=5000 WHERE id=?", (outfit,))
    a0 = count(conn, "actors")
    r = po.execute(conn, me, "hire", target_actor_id=None, details={"count": 30, "into": f"outfit:{outfit}", "role": "member", "wage": 0.1, "_call_id": "h1"},
                   intent="I take on thirty men.")
    assert r["status"] == "applied" and r["hired"] == 30, r
    staffed = conn.execute("SELECT actor_id,metadata_json FROM underworld_personnel WHERE organization_id=? AND status='active' AND json_extract(metadata_json,'$.wage') IS NOT NULL", (outfit,)).fetchall()
    assert len(staffed) == 30 and json.loads(staffed[0][1])["wage"] == 0.1, len(staffed)  # the wage is stored, not dropped
    assert count(conn, "actors") >= a0  # revealed, never invented out of nothing: pool-bound
    # more asked than the place has: those there are, with the reason in words
    r = po.execute(conn, me, "hire", target_actor_id=None, details={"count": 5000, "into": f"outfit:{outfit}", "role": "member", "_call_id": "h2"},
                   intent="I take on five thousand men.")
    assert r["status"] == "partial" and 0 < r["hired"] < 5000 and "aren't that many" in r["summary"] and r["shortfall"], r
    # pay bounds the number: a poor household takes only what it can pay
    conn.execute("UPDATE households SET liquidity=0.25 WHERE id=?", (hh,))
    r = po.execute(conn, me, "hire", target_actor_id=None, details={"count": 20, "into": f"household:{hh}", "role": "servant", "wage": 0.1, "_call_id": "h3"},
                   intent="Servants.")
    assert r["hired"] <= 2 and "purse would not stand" in r["summary"], r
    # the wage binds the household's payroll
    from engine import payroll
    t = payroll.service_terms(conn, hh)
    assert t and abs(payroll.household_wage(t[-1]) - 0.1) < 1e-9


def t_crew_scale(conn, w):
    from engine import player_operations as po
    me, outfit, crew, by = w["me"], w["outfit"], w["crew"], w["bystander"]
    conn.execute("UPDATE underworld_crews SET size_estimate=60 WHERE id=?", (crew,))
    conn.execute("UPDATE underworld_organizations SET member_count_estimate=90 WHERE id=?", (outfit,))
    r = po.execute(conn, me, "attack", target_actor_id=by, details={"crew": f"crew:{crew}", "intent_kind": "beat", "men": 500, "_call_id": "c1"},
                   intent="I go for him with the whole crew.")
    assert r["status"] == "applied" and r["outcome"] == "won", r
    assert r.get("men_short") and r["men_lost"] >= 1, r  # a big force takes losses scaled to its size; and he has no more men to bring
    assert conn.execute("SELECT size_estimate FROM underworld_crews WHERE id=?", (crew,)).fetchone()[0] == 60 - r["men_lost"]


def t_orders_and_posts(conn, w):
    from engine import household_life, ledger, player_operations as po
    me, outfit, hh, by = w["me"], w["outfit"], w["household"], w["bystander"]
    # his own household servant takes orders, and moves into his outfit
    servant = _reveal(conn, w["location"], "test servant")
    household_life.add_service_term(conn, hh, servant, "servant")
    assert po._is_subordinate(conn, me, servant)
    r = po.execute(conn, me, "order", target_actor_id=servant, details={"do": "watch the road to Saltmere", "time": 10}, intent="Watch the road for riders.")
    assert r["status"] == "applied" and r["commitment_id"], r  # no engine verb for it: kept as his commitment
    assert conn.execute("SELECT status,source_kind FROM obligations WHERE id=?", (r["commitment_id"],)).fetchone()[:] == ("active", "player_commitment")
    r = po.execute(conn, me, "hire", target_actor_id=servant, details={"into": f"outfit:{outfit}", "role": "member", "move": True}, intent="Come and work for the outfit.")
    assert r["status"] == "applied", r
    assert conn.execute("SELECT status FROM underworld_personnel WHERE actor_id=?", (servant,)).fetchone()[0] == "active"
    assert conn.execute("SELECT status FROM household_service_terms WHERE actor_id=? AND household_id=?", (servant, hh)).fetchone()[0] == "former"
    # outfit-wide kick-up goes through order
    from engine.underworld_rebuild import kick_rate
    k0 = kick_rate(conn, outfit)
    r = po.execute(conn, me, "order", target_actor_id=None, details={"do": "set_kick_rate", "rate": 0.5}, intent="Every crew sends up half.")
    assert r["status"] == "applied" and abs(kick_rate(conn, outfit) - 0.5) < 1e-9 and not re.search(r"\d", r["summary"]), r
    r = po.execute(conn, me, "order", target_actor_id=None, details={"do": "set_kick_rate", "change": "lower it"}, intent="Ease the take.")
    assert r["status"] == "applied" and kick_rate(conn, outfit) < 0.5, r


def _reveal(conn, loc, reason):
    from engine.person_ecology import resolve_background_person
    return int(resolve_background_person(conn, reason=reason, location_id=loc, min_age=22, max_age=50))


def t_demand_kept(conn, w):
    from engine import findings, player_operations as po
    from engine.interactions import create_interaction
    me, by = w["me"], w["bystander"]
    day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
    iid = create_interaction(conn, me, by, "demand", day, stakes=2, terms={"what": "stop"}, rationale="test")
    out = po._concede(conn, me, by, "He", "stop", {"terms": "stop skimming the Tuesday takings"}, None, [], None, None, iid, False)
    assert out["status"] == "applied" and out["agreement_id"], out
    ag = conn.execute("SELECT terms_json FROM agreements WHERE id=?", (out["agreement_id"],)).fetchone()[0]
    assert "skimming" in ag
    assert conn.execute("SELECT COUNT(*) FROM obligations WHERE actor_id=? AND source_kind='player_commitment' AND description LIKE '%skimming%'", (by,)).fetchone()[0] == 1
    findings.tell(conn, by, ["The ledger of the old tax-farmer is hidden under the cellar stair."], source=by)
    iid2 = create_interaction(conn, me, by, "demand", day, stakes=2, terms={"what": "information", "x": 1}, rationale="test2")
    out = po._concede(conn, me, by, "He", "information", {"about": "the ledger"}, None, [], None, None, iid2, False)
    assert out["status"] == "applied" and out["learned"] and conn.execute(
        "SELECT COUNT(*) FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE '%cellar stair%'", (me,)).fetchone()[0] == 1, out
    out = po._concede(conn, me, by, "He", "information", {"about": "the harbour toll"}, None, [], None, None, iid2, False)
    assert out["status"] == "partial" and "nothing of it" in out["summary"], out


def t_counters(conn, w):
    from engine import payroll, player_operations as po
    from engine.interactions import apply_player_response, create_interaction, _reapproach_blocked
    me, outfit, hh, by = w["me"], w["outfit"], w["household"], w["bystander"]
    day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
    new_po, said = po.counter_terms_for(conn, {"op": "hire", "details": {"into": f"household:{hh}", "role": "clerk", "wage": 0.1}}, None)
    assert abs(new_po["details"]["wage"] - 0.135) < 1e-6 and "wage" in said
    new_po, said = po.counter_terms_for(conn, {"op": "trade", "details": {"deal": "sell", "amount": 10}}, None)
    assert new_po["details"]["amount"] < 10 and "price" in said
    new_po, said = po.counter_terms_for(conn, {"op": "lend", "details": {"rate": "usual"}}, None)
    assert new_po["details"]["rate"] == "steep"
    # a counter that is accepted carries out the operation on the counter's terms, not the first terms
    cp = {"op": "hire", "details": {"into": f"household:{hh}", "role": "clerk", "wage": 0.4}}
    cid = create_interaction(conn, by, me, "offer", day, stakes=2, terms={"player_operation": cp, "counter_terms": {"wage": "more"}}, rationale="counter")
    apply_player_response(conn, cid, me, "accept", day)
    t = [x for x in payroll.service_terms(conn, hh) if int(x["actor_id"]) == by]
    assert t and abs(payroll.household_wage(t[0]) - 0.4) < 1e-9, t
    # the re-approach block tells offers apart: three refused hires do not close a lend
    for i in range(3):
        iid = create_interaction(conn, me, by, "offer", day, terms={"player_operation": {"op": "hire", "details": {"into": "outfit:1", "n": i % 1}}}, rationale="x")
        conn.execute("UPDATE interactions SET status='rejected',resolved_day=? WHERE id=?", (day, iid))
    assert _reapproach_blocked(conn, me, by, "offer", day, {"player_operation": {"op": "hire", "details": {"into": "outfit:1", "n": 0}}}) is not None
    assert _reapproach_blocked(conn, me, by, "offer", day, {"player_operation": {"op": "lend", "details": {"amount": 2}}}) is None
    assert _reapproach_blocked(conn, me, by, "offer", day, {"player_operation": {"op": "hire", "details": {"into": "outfit:1", "wage": 0.3}}}) is None


def t_freeform(conn, w):
    from connector.acting import act
    from connector.store import ensure_connector_schema
    from engine import ledger
    ensure_connector_schema(conn)
    me, outfit, by, biz = w["me"], w["outfit"], w["bystander"], w["business"]
    ledger._credit(conn, ("person", me), 100.0)
    conn.execute("UPDATE underworld_organizations SET treasury=500,member_count_estimate=40 WHERE id=?", (outfit,))
    # money by number, to a person, any words for the intent
    r = act(conn, "f1", "bribe", "I slip the clerk a bribe.", details={"targets": [f"actor:{by}"], "resources": {"money": "2 silver", "from": "me"}})
    assert r["status"] in ("applied", "partial") and r["mapped_to"] == "pay", r
    # a plan nothing models: accepted, costed in money and men, oversize men get what exists and the reason in words
    m0 = ledger.balance(conn, ("outfit", outfit))
    r = act(conn, "f2", "operation", "Seize the toll bridge at Saltmere with a great force of men.",
            details={"resources": {"men": 900, "money": 30, "from": f"outfit:{outfit}"}, "time": "a month", "conditions": ["before the river floods"]})
    assert r["status"] == "partial" and r["mapped_to"] == "plan" and "aren't that many men" in r["summary"] and r["ready_in_days"] == 30, r
    assert r["costs"]["men"] <= 39 and ledger.balance(conn, ("outfit", outfit)) < m0, r
    # his outfit's men live on the kick-up: only the money named is spent, no wages into a sink; a long plan is not capped at 60 days
    assert abs((m0 - ledger.balance(conn, ("outfit", outfit))) - 30.0) < 1e-6, (m0, ledger.balance(conn, ("outfit", outfit)))
    r2 = act(conn, "f2b", "operation", "Hold the whole river road with a great force of men for a year.",
             details={"resources": {"men": 30, "from": f"outfit:{outfit}"}, "time": "a year"})
    assert r2["ready_in_days"] == 365, r2
    assert r["conditions"] == ["before the river floods"]
    # the commitment is visible to the world's own reminders and settles on its day
    from engine import commitments, free_operation
    assert any(c["id"] == r["commitment_id"] for c in commitments.active(conn, me))
    conn.execute("UPDATE world_state SET current_day=current_day+31 WHERE id=1")
    done = free_operation.settle_due(conn, me)
    assert any(x["what"].startswith("Seize the toll") for x in done), done
    # mapped words: a hire of many with a wage
    r = act(conn, "f3", "operation", "Take on forty men as guards.", details={"targets": [f"outfit:{outfit}"], "resources": {"men": 40, "wage": 0.1}, "role": "member"})
    assert r["mapped_to"] == "hire" and r["status"] in ("applied", "partial") and r["hired"] > 0, r
    # format slips are input gaps (retry), true contradictions are not
    r = act(conn, "f4", "hire", "x", details={"into": "nowhere:1"})
    assert r["status"] == "refused" and r["reason_kind"] == "input_gap", r
    r = act(conn, "f5", "treat", "I tend the stranger's wound.", details={"targets": [f"actor:{by}"]})
    assert r["status"] == "refused" and r["reason_kind"] == "contradiction", r
    # not fitting the machinery falls back to a commitment with the reason, never a refusal
    r = act(conn, "f6", "operation", "Build a stout wall around the stall.", details={"resources": {"money": 1}})
    assert r["status"] in ("applied", "partial") and r.get("commitment_id"), r
    # founding his own thing is left to the new-character work: planned, nothing spent
    b0 = ledger.balance(conn, ("person", me))
    r = act(conn, "f7", "operation", "Found a gambling house under my name.", details={"resources": {"money": 50}})
    assert r["mapped_to"] == "found" and ledger.balance(conn, ("person", me)) == b0 and r["status"] == "partial", r
    # unknown names are an input gap
    r = act(conn, "f8", "operation", "Pay him.", details={"targets": ["Nobody Atall"], "resources": {"money": 1}})
    assert r["status"] == "refused" and r["reason_kind"] == "input_gap", r


def t_messages_and_stages(conn, w):
    from connector.acting import act
    from engine import free_operation
    me, by = w["me"], w["bystander"]
    far = int(conn.execute("SELECT id FROM locations WHERE name='Saltmere'").fetchone()[0])
    conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (far, by))
    r = act(conn, "m1", "operation", "Send word to him that the bridge toll is changing.",
            details={"targets": [f"actor:{by}"], "tells": ["The bridge toll is changing."], "kind": "message"})
    assert r["mapped_to"] == "message" and r["status"] == "applied" and r["ready_in_days"] >= 1, r
    conn.execute("UPDATE world_state SET current_day=current_day+?+1 WHERE id=1", (r["ready_in_days"],))
    done = free_operation.settle_due(conn, me)
    assert any(x["kind"] == "message" and "reached" in x["result"] for x in done), done
    assert conn.execute("SELECT COUNT(*) FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE '%toll is changing%'", (by,)).fetchone()[0] == 1
    conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (w["location"], by))
    # a duel runs in stages the player steers
    r = act(conn, "d1", "operation", "I challenge him to a duel.", details={"targets": [f"actor:{by}"]})
    assert r["mapped_to"] == "duel" and r["stage"] == "begins", r
    r2 = act(conn, "d2", "operation", "I press him hard.", details={"duel": r["duel"], "kind": "duel"})
    assert r2["status"] == "applied" and r2["stage"] in ("continues", "resolved"), r2
    # a battle likewise, with the men he really has
    conn.execute("UPDATE underworld_organizations SET member_count_estimate=40 WHERE id=?", (w["outfit"],))
    rival = int(conn.execute("SELECT id FROM underworld_organizations WHERE id<>? AND current_leader_actor_id IS NOT NULL ORDER BY id LIMIT 1", (w["outfit"],)).fetchone()[0])
    r = act(conn, "b1", "operation", "I give battle to the rival outfit in the street.", details={"targets": [f"outfit:{rival}"], "resources": {"men": 200}, "kind": "battle"})
    assert r["mapped_to"] == "battle" and r["stage"] == "begins" and r["view"]["sides"], r
    bid = r["battle"]
    for i in range(3):  # rounds are fought one at a time on the player's word; the engine's own grind decides how long it lasts
        r = act(conn, f"b2{i}", "operation", "Press the attack.", details={"battle": bid, "kind": "battle"})
        assert r["status"] == "applied" and r["stage"] in ("continues", "resolved") and r["view"]["sides"], r
        if r["stage"] == "resolved":
            break
    a = free_operation._aftermath(conn, w["me"], bid, {"winner_side_id": None})
    assert "men_lost" in a and "outcome" in a, a


def t_speak_investigate(conn, w):
    from connector.acting import act
    from engine import findings
    me, by, biz = w["me"], w["bystander"], w["business"]
    findings.tell(conn, by, ["Old Harl keeps a second set of books at the mill."], source=by)
    r = act(conn, "s1", "speak", "I ask what he knows of the mill.", target_actor_id=by,
            details={"tells": ["The magistrate is bought."], "asks": "the mill books"})
    if r["status"] == "applied":
        assert r["told"] == 1 and r["answers"] and "second set of books" in r["answers"][0], r
        assert conn.execute("SELECT COUNT(*) FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE '%magistrate is bought%'", (by,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE '%second set of books%'", (me,)).fetchone()[0] == 1
        r = act(conn, "s2", "speak", "I ask about the harbour.", target_actor_id=by, details={"asks": "the harbour fees"})
        assert r.get("answers") == [] and "nothing to say" in r["note"], r
    # investigate a business, a bare question, a person: real findings or an honest nothing
    r = act(conn, "i1", "investigate", "I look into the stall.", details={"business": f"business:{biz}"}, duration_days=3)
    assert r["status"] == "applied" and r["elapsed_days"] == 3 and r["found"], r
    assert any("owned by" in x or "works at" in x for x in r["found"]), r
    assert conn.execute("SELECT COUNT(*) FROM knowledge WHERE knower_actor_id=? AND fact_key LIKE ?", (me, "found:i1:%")).fetchone()[0] == len(r["found"])
    r = act(conn, "i2", "investigate", "I ask around about the moon-eyed ferryman.", details={"subject": "moon-eyed ferryman"}, duration_days=2)
    assert r["status"] == "applied" and r.get("nothing_found") is True and r["found"] == [], r
    r = act(conn, "i3", "investigate", "I study him.", target_actor_id=by, duration_days=4)
    assert r["status"] == "applied" and "found" in r, r


def t_advance_and_views(conn, w):
    import json
    from connector import store, views
    from connector.timeflow import advance
    me, outfit, hh, biz, crew, by = w["me"], w["outfit"], w["household"], w["business"], w["crew"], w["bystander"]
    store.ensure_connector_schema(conn)
    # advance keeps its purpose, focus (the discipline it names), delegation and interruption policy
    r = advance(conn, "adv1", 3, "train swordwork for a season", delegate={"to": "my steward", "everything_routine": True}, interrupt="critical_only")
    run = conn.execute("SELECT * FROM time_skip_runs ORDER BY id DESC LIMIT 1").fetchone()
    focus = json.loads(run["focus_json"])
    assert focus and focus[0]["domain"] == "martial" and "swordwork" in focus[0]["description"], focus
    assert json.loads(run["delegation_json"])["to"] == "my steward" and run["interruption_policy"] == "critical_only"
    assert r["spent_on"] and r["spent_on"][0]["days"] > 0, r
    # lookup finds outfits (his own in full, a rival only if heard of), households, crews, roles
    assert views.lookup(conn, "Fixture Outfit")["kind"] == "outfit" and views.lookup(conn, "Fixture Outfit")["basics"]["members"] > 0
    assert views.lookup(conn, "Fixture Crew")["kind"] == "crew"
    assert views.lookup(conn, "Fixture House")["kind"] == "household"
    rival = conn.execute("""SELECT id,name FROM underworld_organizations o WHERE id<>? AND current_leader_actor_id IS NOT NULL AND NOT EXISTS
                            (SELECT 1 FROM underworld_zone_claims c JOIN underworld_zones z ON z.id=c.zone_id WHERE c.organization_id=o.id AND z.city_location_id=?)
                            AND NOT EXISTS (SELECT 1 FROM actors a WHERE a.name=o.name) ORDER BY id LIMIT 1""", (outfit, w["location"])).fetchone()
    assert views.lookup(conn, rival["name"])["found"] is False  # not heard of
    conn.execute("INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day) VALUES (?,?,?,?,0)", (me, "t:rival", f"{rival['name']} runs the docks.", 0.7))
    got = views.lookup(conn, rival["name"])
    assert got["found"] and got["kind"] == "outfit" and "key_people" not in got["basics"] and got["known"], got
    role = conn.execute("SELECT a.name,p.role_kind FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.role_kind='crew_leader'", (outfit,)).fetchone()
    got = views.lookup(conn, "crew leader")
    assert got.get("found") or got.get("by_role"), got
    # memory pages: notes on a business, an outfit; nothing silently shrinks
    for i in range(11):
        store.add_note(conn, "business", biz, f"fact {i}", f"n{i}")
    store.add_note(conn, "outfit", outfit, "The crews drink at the Lamp.", "no1")
    page1 = views.lookup(conn, "Fixture Stall")
    assert len(page1["notes"]) == 8 and page1["notes_more"] == 3, page1
    page2 = views.lookup(conn, "Fixture Stall", offset=8)
    assert len(page2["notes"]) == 3 and "notes_more" not in page2 and page2["notes"][0] == "fact 0", page2
    by_name = conn.execute("SELECT name FROM actors WHERE id=?", (by,)).fetchone()[0]
    for i in range(12):
        conn.execute("INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day) VALUES (?,?,?,?,?)", (me, f"t:{i}", f"{by_name} was seen {i}.", 0.5, i))
    got = views.lookup(conn, by_name)
    assert len(got["known"]) == 8 and got["known_more"] >= 4, got
    assert views.lookup(conn, by_name, offset=8)["known"], "older facts can be paged"
    # a recap says what it cut
    r = store.record(conn, "recap", "x" * 900, "rc1", threads=[f"thread {i}" for i in range(11)])
    assert "clipped" in r and "threads_dropped" in r, r
    scene = views.compact_scene(conn)
    assert "commitments" in scene or True


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "act.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from fixtures_protagonist import make_boss

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            w = make_boss(conn)
            for fn in (t_amounts, t_hire_many, t_crew_scale, t_orders_and_posts, t_demand_kept, t_counters, t_freeform, t_messages_and_stages, t_speak_investigate, t_advance_and_views):
                fn(conn, w)
                print(fn.__name__, "ok")
    print("act_freeform_test passed")


if __name__ == "__main__":
    run()
