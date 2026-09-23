from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.combat import (
    add_battle_side, add_battle_unit, battle_view, create_battle, create_duel, duel_view,
    resolve_battle_round, resolve_duel_exchange, submit_battle_intent, submit_duel_intent,
)
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.expertise import set_actor_competence
from engine.player import set_player
from engine.simulation import seed_demo


def _fresh():
    reset_db()
    init_db()
    seed_demo()
    init_db()


def _actor(conn, name: str):
    return conn.execute("SELECT * FROM actors WHERE name=?", (name,)).fetchone()


def _new_character(conn, name: str) -> int:
    loc = conn.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()
    cur = conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,is_demo) VALUES (?,'character','test combatant',?,?,'active',1)",
        (name, loc[0], loc[0]),
    )
    return int(cur.lastrowid)


def run():
    # Version/schema migration and player agency at a strategic command boundary.
    _fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {"0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0","0.56.0","0.58.0","0.59.0","0.60.0"}
        assert conn.execute("SELECT value FROM engine_meta WHERE key='engine_version'").fetchone()[0] in {"0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0", "0.58.0","0.59.0","0.60.0"}
        player = _actor(conn, "[DEMO] Player Wanderer")
        escort = _actor(conn, "[DEMO] River Lantern Escort Company")
        brotherhood = _actor(conn, "[DEMO] North Road Brotherhood")
        set_player(conn, int(player["id"]), "Combat Test")
        set_actor_competence(conn, int(player["id"]), "command", 72, source_kind="campaign")
        set_actor_competence(conn, int(escort["id"]), "command", 58, source_kind="campaign")
        set_actor_competence(conn, int(brotherhood["id"]), "command", 55, source_kind="campaign")

        eid = create_battle(conn, "[DEMO] Crossroads Contest", player_actor_id=int(player["id"]), objective="Control the crossroads")
        a = add_battle_side(conn, eid, "Lantern Side", controller_actor_id=int(player["id"]), posture="balanced", information_quality=70)
        b = add_battle_side(conn, eid, "Brotherhood Side", controller_actor_id=int(brotherhood["id"]), posture="assertive", information_quality=45)
        add_battle_unit(conn, a, "Lantern Main", commander_actor_id=int(escort["id"]), unit_role="line")
        add_battle_unit(conn, a, "Lantern Reserve", unit_role="reserve")
        add_battle_unit(conn, b, "Brotherhood Main", commander_actor_id=int(brotherhood["id"]), unit_role="line")
        add_battle_unit(conn, b, "Brotherhood Reserve", unit_role="reserve")

        needs = resolve_battle_round(conn, eid)
        assert needs["needs_player"] is True and needs["role"] == "side_controller"
        assert conn.execute("SELECT COUNT(*) FROM battle_rounds WHERE engagement_id=?", (eid,)).fetchone()[0] == 0

        submit_battle_intent(conn, eid, int(player["id"]), "probe", risk_level="balanced", commitment=0.5)
        result = resolve_battle_round(conn, eid)
        assert result["round_index"] == 1
        assert len(result["sides"]) == 2
        assert conn.execute("SELECT COUNT(*) FROM battle_unit_actions WHERE engagement_id=? AND round_index=1", (eid,)).fetchone()[0] == 4
        # Subordinate reserve behavior is derived rather than requiring player micromanagement.
        reserve_action = conn.execute(
            """SELECT a.action_key,a.autonomy_source FROM battle_unit_actions a
               JOIN battle_units u ON u.id=a.unit_id WHERE a.engagement_id=? AND u.name='Lantern Reserve'""",
            (eid,),
        ).fetchone()
        assert reserve_action["action_key"] == "hold"
        assert reserve_action["autonomy_source"] in {"side_intent","commander_judgment"}

        view = battle_view(conn, eid, int(player["id"]))
        assert view["viewer"]["role"] == "side_controller"
        own = next(x for x in view["sides"] if x["name"] == "Lantern Side")
        enemy = next(x for x in view["sides"] if x["name"] == "Brotherhood Side")
        assert len(own["units"]) == 2
        # Enemy view never exposes raw hidden numeric state.
        assert "logistics" not in enemy and "reserve" not in enemy
        assert view["guardrails"]["hidden_enemy_state_withheld"] is True
        conn.commit()

    # Unit-command player gets a local decision boundary rather than strategic omniscience.
    _fresh()
    with connect() as conn:
        player = _actor(conn, "[DEMO] Player Wanderer")
        escort = _actor(conn, "[DEMO] River Lantern Escort Company")
        brotherhood = _actor(conn, "[DEMO] North Road Brotherhood")
        set_actor_competence(conn, int(player["id"]), "command", 62, source_kind="campaign")
        eid = create_battle(conn, "[DEMO] Local Command Test", player_actor_id=int(player["id"]))
        a = add_battle_side(conn, eid, "A", controller_actor_id=int(escort["id"]))
        b = add_battle_side(conn, eid, "B", controller_actor_id=int(brotherhood["id"]))
        uid = add_battle_unit(conn, a, "Player Unit", commander_actor_id=int(player["id"]))
        add_battle_unit(conn, a, "Other A", commander_actor_id=int(escort["id"]))
        add_battle_unit(conn, b, "Other B", commander_actor_id=int(brotherhood["id"]))
        needs = resolve_battle_round(conn, eid)
        assert needs["needs_player"] and needs["role"] == "unit_commander" and needs["unit_id"] == uid
        submit_battle_intent(conn, eid, int(player["id"]), "hold")
        result = resolve_battle_round(conn, eid)
        assert result["round_index"] == 1
        view = battle_view(conn, eid, int(player["id"]))
        assert view["viewer"]["information_depth"] == "local"
        own_side = next(x for x in view["sides"] if x["name"] == "A")
        assert len(own_side["units"]) == 1 and own_side["units"][0]["name"] == "Player Unit"
        conn.commit()

    # Duel resolution asks for player intent, uses martial competence, and stays abstract/non-graphic.
    _fresh()
    with connect() as conn:
        player = _actor(conn, "[DEMO] Player Wanderer")
        rival_id = _new_character(conn, "[DEMO] Practice Rival")
        set_actor_competence(conn, int(player["id"]), "martial", 70, source_kind="campaign")
        set_actor_competence(conn, rival_id, "martial", 64, source_kind="campaign")
        eid = create_duel(conn, "[DEMO] Formal Practice Duel", int(player["id"]), rival_id, player_actor_id=int(player["id"]), objective="Test each other's measure")
        needs = resolve_duel_exchange(conn, eid)
        assert needs["needs_player"] and needs["role"] == "duelist"
        submit_duel_intent(conn, eid, int(player["id"]), "measure", risk_level="balanced", reserve_commitment=0.2)
        result = resolve_duel_exchange(conn, eid)
        assert result["round_index"] == 1
        assert "HARM-01" in result["note"]  # final injury/death consequences are projected by HARM-01
        assert len(result["combatants"]) == 2
        view = duel_view(conn, eid, int(player["id"]))
        opponent = next(x for x in view["combatants"] if x["actor_id"] == rival_id)
        assert "apparent_readiness" in opponent
        assert "readiness" not in opponent
        assert view["guardrails"]["technical_exchange_hidden"] is True
        conn.commit()

    # Fully NPC duel can advance with no player camera actor at all.
    _fresh()
    with connect() as conn:
        a = _new_character(conn, "[DEMO] NPC Duelist A")
        b = _new_character(conn, "[DEMO] NPC Duelist B")
        set_actor_competence(conn, a, "martial", 55, source_kind="campaign")
        set_actor_competence(conn, b, "martial", 55, source_kind="campaign")
        eid = create_duel(conn, "[DEMO] Off-camera Duel", a, b)
        result = resolve_duel_exchange(conn, eid)
        assert result["round_index"] == 1 and "needs_player" not in result
        assert conn.execute("SELECT COUNT(*) FROM duel_intents WHERE engagement_id=?", (eid,)).fetchone()[0] == 2
        conn.commit()

    print("v13_test: PASS")


if __name__ == "__main__":
    run()
