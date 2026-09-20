from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.battlefield import (
    add_battle_zone, assign_unit_to_zone, battlefield_view, issue_battle_order,
    local_shock, set_command_link, set_command_profile,
)
from engine.combat import (
    add_battle_side, add_battle_unit, battle_view, create_battle,
    resolve_battle_round, submit_battle_intent,
)
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.expertise import set_actor_competence
from engine.player import set_player
from engine.simulation import seed_demo


def _fresh():
    reset_db(); init_db(); seed_demo(); init_db()


def _actor(conn, name: str):
    return conn.execute("SELECT * FROM actors WHERE name=?", (name,)).fetchone()


def run():
    _fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {"0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0","0.56.0","0.58.0","0.59.0"}
        player = _actor(conn, "[DEMO] Player Wanderer")
        ally = _actor(conn, "[DEMO] River Lantern Escort Company")
        foe = _actor(conn, "[DEMO] North Road Brotherhood")
        set_player(conn, int(player["id"]), "v0.14 test")
        set_actor_competence(conn, int(player["id"]), "command", 76, source_kind="campaign")
        set_actor_competence(conn, int(ally["id"]), "command", 68, source_kind="campaign")
        set_actor_competence(conn, int(foe["id"]), "command", 60, source_kind="campaign")
        set_command_profile(conn, int(player["id"]), planning=82, adaptation=70, delegation=74, presence=65, nerve=72)

        eid = create_battle(conn, "[DEMO] Multi-front Flow", player_actor_id=int(player["id"]), objective="Hold the operational objective")
        a = add_battle_side(conn, eid, "A", controller_actor_id=int(player["id"]), information_quality=72)
        b = add_battle_side(conn, eid, "B", controller_actor_id=int(foe["id"]), information_quality=45)
        north = add_battle_zone(conn, eid, "North Front", importance=70)
        south = add_battle_zone(conn, eid, "South Front", importance=45)
        a1 = add_battle_unit(conn, a, "A North", commander_actor_id=int(ally["id"]), combat_capacity=76)
        a2 = add_battle_unit(conn, a, "A South", combat_capacity=62)
        b1 = add_battle_unit(conn, b, "B North", commander_actor_id=int(foe["id"]), combat_capacity=64)
        b2 = add_battle_unit(conn, b, "B South", combat_capacity=70)
        assign_unit_to_zone(conn, a1, north)
        assign_unit_to_zone(conn, b1, north)
        assign_unit_to_zone(conn, a2, south)
        assign_unit_to_zone(conn, b2, south)
        set_command_link(conn, eid, a, senior_actor_id=int(player["id"]), junior_actor_id=int(ally["id"]), junior_unit_id=a1,
                         communication_quality=90, discretion=75, trust=75)
        order_id = issue_battle_order(conn, eid, a, "hold", issuer_actor_id=int(player["id"]), recipient_actor_id=int(ally["id"]), unit_id=a1,
                                      zone_id=north, objective="Maintain local cohesion")
        assert order_id > 0

        need = resolve_battle_round(conn, eid)
        assert need["needs_player"] is True
        submit_battle_intent(conn, eid, int(player["id"]), "probe", commitment=0.45)
        r1 = resolve_battle_round(conn, eid)
        assert r1["round_index"] == 1
        assert len(r1["battlefield_flow"]["zones"]) == 2
        assert conn.execute("SELECT COUNT(*) FROM battle_zones WHERE engagement_id=?", (eid,)).fetchone()[0] == 2
        # Order reached the subordinate layer without requiring direct player micromanagement.
        row = conn.execute("SELECT autonomy_source FROM battle_unit_actions WHERE engagement_id=? AND unit_id=? AND round_index=1", (eid,a1)).fetchone()
        assert row[0] in {"received_order","commander_judgment","unit_intent"}

        # Reports are not omniscient; side-controller view uses delivered reports rather than raw zone state.
        view1 = battle_view(conn, eid, int(player["id"]))
        assert "battlefield" in view1
        assert view1["guardrails"]["reports_may_be_delayed"] is True
        assert len(view1["battlefield"]["zones"]) == 2

        submit_battle_intent(conn, eid, int(player["id"]), "hold", commitment=0.45)
        r2 = resolve_battle_round(conn, eid)
        assert r2["round_index"] == 2
        reports = conn.execute("SELECT COUNT(*) FROM battle_reports WHERE engagement_id=? AND recipient_actor_id=? AND available_round<=2", (eid,player["id"])).fetchone()[0]
        assert reports >= 1

        # A notable local event remains bounded to one front rather than deciding the whole engagement automatically.
        local_shock(conn, eid, north, a, magnitude=6, summary="A local success briefly lifted nearby confidence.")
        eng = conn.execute("SELECT status FROM combat_engagements WHERE id=?", (eid,)).fetchone()
        assert eng[0] in {"active","resolved"}
        if eng[0] == "active":
            assert conn.execute("SELECT COUNT(*) FROM battle_turning_points WHERE engagement_id=?", (eid,)).fetchone()[0] >= 1

        conn.commit()

    print("v14_test: PASS")


if __name__ == "__main__":
    run()
