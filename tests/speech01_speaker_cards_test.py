"""SPEECH-01 step 1: the narrator receives speaker cards drawn from state (standing, demeanour, history,
open dealings, temperament, mannerisms) instead of names only. Mannerisms are resolved on first look,
recorded, and identical in every later scene; the same world seed always resolves them the same way."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import connect, init_db, reset_db
from engine.player import build_scene_packet, set_player
from engine.speaker_cards import SPEAKER_RULE, build_speaker_cards, likely_speakers, seeded_drives, temperament


def _world(conn):
    loc = int(conn.execute("INSERT INTO locations(name,kind) VALUES ('[SPEECH] Ferry inn','inn')").lastrowid)
    house = int(conn.execute("INSERT INTO actors(name,actor_type,subtype,current_location_id) "
                             "VALUES ('[SPEECH] House Vey','institution','clan',?)", (loc,)).lastrowid)
    mk = lambda name, sub: int(conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id) VALUES (?,?,?,?,?)",
        (name, "character", sub, loc, loc)).lastrowid)
    player, steward, keeper, stranger = (mk("[SPEECH] Ren", "wanderer"), mk("[SPEECH] Mother Vey", "clan elder"),
                                         mk("[SPEECH] Tam Oarsby", "innkeeper"), mk("[SPEECH] Quiet Drinker", "porter"))
    conn.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,role_text) VALUES (?,?,?)",
                 (house, steward, "Senior elder."))
    conn.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,role_text) VALUES (?,?,?)",
                 (house, player, "Sworn retainer."))
    # Mother Vey knows Ren well and resents them; they hold an active debt and she has a pending demand.
    conn.execute("""INSERT INTO relationships(actor_a_id,actor_b_id,stance,familiarity,trust,resentment,updated_day)
                    VALUES (?,?,-10,70,10,55,0)""", (steward, player))
    conn.execute("INSERT INTO agreements(agreement_type,actor_a_id,actor_b_id,created_day,terms_json) VALUES ('debt',?,?,0,?)",
                 (steward, player, json.dumps({"purpose": "forty silver for the ferry license"})))
    conn.execute("""INSERT INTO interactions(created_day,proposer_actor_id,recipient_actor_id,interaction_type,terms_json,response_due_day)
                    VALUES (0,?,?,'demand',?,10)""", (steward, player, json.dumps({"purpose": "repay the license money"})))
    conn.execute("""INSERT INTO relationship_history(day,source_actor_id,target_actor_id,source_kind,summary)
                    VALUES (0,?,?,'interaction','Mother Vey lent Ren the license money against her better judgement')""",
                 (steward, player))
    conn.execute("INSERT INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) "
                 "VALUES (?,0.2,0.3,0.9,0.85,0.5,0.5)", (steward,))
    conn.execute("UPDATE world_state SET current_day=0 WHERE id=1")
    return loc, player, steward, keeper, stranger


def run():
    reset_db()
    init_db()
    with connect() as conn:
        loc, player, steward, keeper, stranger = _world(conn)
        set_player(conn, player, "Speaker Card Test")

        present = [dict(r) for r in conn.execute(
            "SELECT id,name,actor_type,subtype FROM actors WHERE current_location_id=? AND id<>?", (loc, player))]
        # Dealings and history rank first; the innkeeper's work is to talk to strangers; the porter is silent.
        order = likely_speakers(conn, player, present, "")
        assert order[:2] == [steward, keeper], order
        assert stranger not in order
        # Naming someone in the request brings them forward.
        assert likely_speakers(conn, player, present, "I ask Tam about a room")[0] == keeper
        # Titles and ordinary words in names do not count as being addressed.
        assert likely_speakers(conn, player, present, "I write to my mother")[0] == steward
        assert keeper not in likely_speakers(conn, player, present, "I ask the porter about a room")[:1]

        # The packet carries speakers (whoever presence puts in the room), the rule, and the player's standing.
        packet = build_scene_packet(conn, "I sit down across from Mother Vey")
        assert isinstance(packet["speakers"], list)
        assert packet["player"]["visible_standing"] == ["Sworn retainer ([SPEECH] House Vey)"]
        assert SPEAKER_RULE in packet["narrator_rules"]

        cards = {c["name"]: c for c in build_speaker_cards(conn, player, present, "I sit down across from Mother Vey", 0)}
        vey = cards["[SPEECH] Mother Vey"]
        assert vey["visible_standing"] == ["Senior elder ([SPEECH] House Vey)"]
        assert vey["toward_followed_character"] == {"familiarity": "knows them well",
                                                    "demeanour": "hostile or resentful, within whatever courtesy the setting demands"}
        assert any("forty silver" in d for d in vey["open_dealings"]) and any("pending demand" in d for d in vey["open_dealings"])
        assert vey["shared_history"] and "license money" in vey["shared_history"][0]
        assert vey["temperament"]["basis"] == "actor_drives"
        assert "unhurried; lets silences run" in vey["temperament"]["cues"]
        assert len(vey["mannerisms"]) >= 2 and vey["speech"]

        # Private seed judgements never reach the narrator as a role; public positions do.
        from engine.speaker_cards import public_role
        assert public_role("Generational anomaly") is None and public_role("Strong mature Third") is None
        assert public_role("Current leader; formidable apex practitioner.") == "Current leader"
        assert public_role("Highly respected independent duelist.") == "Independent duelist"
        conn.execute("UPDATE actors SET subtype='Generational anomaly' WHERE id=?", (stranger,))
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, stranger))
        for a in build_scene_packet(conn, "I look around")["present_actors"]:
            assert "anomaly" not in str(a.get("subtype") or "").lower(), a

        # People without drives get a stable seeded preview, flagged as such.
        tam = cards["[SPEECH] Tam Oarsby"]
        assert tam["temperament"]["basis"] == "seeded_preview"
        assert seeded_drives(conn, keeper) == seeded_drives(conn, keeper)
        assert temperament(conn, keeper) == tam["temperament"]

        # Resolved on first look, recorded, and unchanged in a later scene on a later day.
        row = conn.execute("SELECT habits_json,development_json FROM character_embodiment WHERE actor_id=?", (steward,)).fetchone()
        assert json.loads(row["habits_json"])["mannerisms"] == vey["mannerisms"]
        assert json.loads(row["development_json"])["revealed"]["mannerisms"]["basis"] == "resolved_on_reveal"
        conn.execute("UPDATE world_state SET current_day=40 WHERE id=1")
        later = {c["name"]: c for c in build_speaker_cards(conn, player, present, "I greet Mother Vey", 40)}
        assert later["[SPEECH] Mother Vey"]["mannerisms"] == vey["mannerisms"]
        assert later["[SPEECH] Mother Vey"]["speech"] == vey["speech"]
        first = (vey["mannerisms"], vey["speech"], tam["mannerisms"])

    # Same world seed, fresh database: the same people resolve to the same mannerisms.
    reset_db()
    init_db()
    with connect() as conn:
        loc, player, steward, keeper, stranger = _world(conn)
        present = [dict(r) for r in conn.execute(
            "SELECT id,name,actor_type,subtype FROM actors WHERE current_location_id=? AND id<>?", (loc, player))]
        cards = {c["name"]: c for c in build_speaker_cards(conn, player, present, "I sit down across from Mother Vey", 0)}
        again = (cards["[SPEECH] Mother Vey"]["mannerisms"], cards["[SPEECH] Mother Vey"]["speech"],
                 cards["[SPEECH] Tam Oarsby"]["mannerisms"])
        assert again == first, (again, first)

    print("SPEECH-01 speaker card test passed")


if __name__ == "__main__":
    run()
