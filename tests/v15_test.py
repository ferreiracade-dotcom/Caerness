from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.battlefield import add_battle_zone, assign_unit_to_zone
from engine.battle_tactics import (
    add_vein_asset, apply_personal_combat_consequence, set_battle_doctrine,
    set_zone_current, submit_tactical_choice,
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
        assert ENGINE_VERSION in {"0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0","0.56.0","0.58.0","0.59.0","0.60.0"}
        player = _actor(conn, "[DEMO] Player Wanderer")
        ally = _actor(conn, "[DEMO] River Lantern Escort Company")
        foe = _actor(conn, "[DEMO] North Road Brotherhood")
        set_player(conn, int(player["id"]), "v0.15 test")
        set_actor_competence(conn, int(player["id"]), "command", 78, source_kind="campaign")
        set_actor_competence(conn, int(foe["id"]), "command", 65, source_kind="campaign")
        set_battle_doctrine(conn, int(player["id"]), pressure=80, exploitation=75, reserve_play=35, depth=30)
        set_battle_doctrine(conn, int(foe["id"]), depth=78, attrition=72, disruption=65)

        eid = create_battle(conn, "[DEMO] Vein Tactical Grammar", player_actor_id=int(player["id"]), objective="Contest the campaign objective")
        a = add_battle_side(conn, eid, "A", controller_actor_id=int(player["id"]), information_quality=70)
        b = add_battle_side(conn, eid, "B", controller_actor_id=int(foe["id"]), information_quality=58)
        gate = add_battle_zone(conn, eid, "Gate Front", importance=92)
        flats = add_battle_zone(conn, eid, "Outer Flats", importance=24)
        set_zone_current(conn, gate, density=82, stability=88, replenishment=78)
        set_zone_current(conn, flats, density=28, stability=48, replenishment=35)

        a1 = add_battle_unit(conn, a, "A Gate", commander_actor_id=int(ally["id"]), combat_capacity=72)
        b1 = add_battle_unit(conn, b, "B Gate", commander_actor_id=int(foe["id"]), combat_capacity=72)
        a2 = add_battle_unit(conn, a, "A Flats", combat_capacity=60)
        b2 = add_battle_unit(conn, b, "B Flats", combat_capacity=60)
        for uid,zid in ((a1,gate),(b1,gate),(a2,flats),(b2,flats)):
            assign_unit_to_zone(conn, uid, zid)

        a_fifth = add_vein_asset(conn, eid, a, "Fifth", actor_id=int(player["id"]), zone_id=gate,
                                 battlefield_role="anchor", commitment=0.65,
                                 metadata={"command_role":"side_controller","replacement_depth":0.8})
        b_fifth = add_vein_asset(conn, eid, b, "Fifth", actor_id=int(foe["id"]), zone_id=gate,
                                 battlefield_role="anchor", commitment=0.62,
                                 metadata={"command_role":"critical_command","replacement_depth":0.4})
        # A Sixth in a low-value area should not automatically become strategically decisive merely by existing there.
        low_asset = add_vein_asset(conn, eid, a, "Sixth", zone_id=flats, battlefield_role="support", commitment=0.25,
                                   metadata={"replacement_depth":1.0})

        need = resolve_battle_round(conn, eid)
        assert need["needs_player"] is True
        submit_battle_intent(conn, eid, int(player["id"]), "press", commitment=0.55)
        submit_tactical_choice(conn, eid, a, "pressure", actor_id=int(player["id"]), focus_zone_id=gate, commitment=0.65)
        r1 = resolve_battle_round(conn, eid)
        assert r1["round_index"] == 1
        assert "tactical_layer" in r1
        assert len(r1["tactical_layer"]["choices"]) == 2
        assert conn.execute("SELECT COUNT(*) FROM battle_tactical_effects WHERE engagement_id=? AND round_index=1", (eid,)).fetchone()[0] == 2
        # Vein exertion has a cost and is geographically conditioned rather than a free power bonus.
        post = conn.execute("SELECT reserve FROM battle_vein_assets WHERE id=?", (a_fifth,)).fetchone()
        assert float(post[0]) < 100

        view = battle_view(conn, eid, int(player["id"]))
        assert "tactics" in view
        assert view["guardrails"]["personal_combat_consequence_is_contextual"] is True
        assert any(x["stage"] == "Fifth" for x in view["tactics"]["own_vein_assets"])

        # Context, not duel-status alone, determines scale. A strategically important Fifth falling at a major point
        # can trigger a cascade if the side is already fragile.
        conn.execute("UPDATE battle_sides SET morale=22,cohesion=21,status='withdrawing' WHERE id=?", (b,))
        major = apply_personal_combat_consequence(conn, eid, gate, winner_asset_id=a_fifth, loser_asset_id=b_fifth,
                                                   summary="A major personal confrontation removed a critical battlefield figure.")
        assert major["scale"] == "strategic"
        assert major["cascade"] is True
        assert conn.execute("SELECT status FROM battle_sides WHERE id=?", (b,)).fetchone()[0] == "broken"

        # The same famous Stage at an unimportant location with strong replacement context need not decide the battle.
        c = add_battle_side(conn, eid, "C", information_quality=50)
        c_asset = add_vein_asset(conn, eid, c, "Sixth", zone_id=flats, battlefield_role="support", commitment=0.2,
                                 metadata={"replacement_depth":1.0})
        minor_context = apply_personal_combat_consequence(conn, eid, flats, winner_asset_id=low_asset, loser_asset_id=c_asset,
                                                           summary="A famous fighter was removed far from the principal decision point.")
        assert minor_context["scale"] in {"local","operational"}
        assert minor_context["cascade"] is False

        conn.commit()

    print("v15_test: PASS")


if __name__ == "__main__":
    run()
