"""SCENE-01 step 1: every scene packet carries the reading lenses and the culture briefs it needs, and the
narrator's canon search never returns the simulation registry, the open-questions ledger or canon-status rules."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.canon import DEFAULT_CANON, index_canon, search_canon
from engine.db import connect, init_db, reset_db
from engine.player import build_scene_packet, render_scene_brief, set_player
from engine.scene_brief import (
    NARRATOR_EXCLUDED_PARTS, actor_culture, brief_staleness, build_scene_brief, load_briefs, location_culture,
    narrator_may_receive,
)
from engine.simulation import seed_demo


def run():
    reset_db()
    init_db()
    seed_demo()
    init_db()
    index_canon(DEFAULT_CANON)

    with connect() as conn:
        # Culture of a place: the Hearth by membership (parent chain or named Hearth city), otherwise the owner.
        hearth = int(conn.execute("SELECT id FROM locations WHERE name='Hearthlands'").fetchone()[0])
        inn = int(conn.execute("INSERT INTO locations(name,kind,parent_location_id) VALUES ('[SCENE] Hearth inn','inn',?)",
                               (hearth,)).lastrowid)
        dun = int(conn.execute("INSERT INTO locations(name,kind,political_owner) VALUES ('[SCENE] Dunmoor manor','manor','Dunmoor')").lastrowid)
        sea = int(conn.execute("INSERT INTO locations(name,kind) VALUES ('[SCENE] Open sea','sea')").lastrowid)
        cairn = conn.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()
        assert location_culture(conn, inn) == "hearth"
        assert location_culture(conn, dun) == "dunmoor"
        assert location_culture(conn, sea) is None
        assert location_culture(conn, None) is None
        if cairn:
            assert location_culture(conn, int(cairn[0])) == "hearth"

        # A Dunmoor knight drinking in a Hearth inn brings Dunmoor's brief along; locals add nothing new.
        knight = int(conn.execute("INSERT INTO actors(name,actor_type,home_location_id,current_location_id) "
                                  "VALUES ('[SCENE] Dunmoor knight','character',?,?)", (dun, inn)).lastrowid)
        local = int(conn.execute("INSERT INTO actors(name,actor_type,home_location_id,current_location_id) "
                                 "VALUES ('[SCENE] Innkeeper','character',?,?)", (inn, inn)).lastrowid)
        assert actor_culture(conn, knight) == "dunmoor"
        brief = build_scene_brief(conn, inn, [knight, local])
        lenses = brief["reading_lenses"]["text"]
        assert "Recognition precedes introduction" in lenses and "Same bows, different room" in lenses
        assert [c["culture"] for c in brief["cultures"]] == ["hearth", "dunmoor"]
        assert brief["cultures"][0]["applies"] == "this place"
        assert "seat of its dead" in brief["cultures"][0]["text"]
        # The lenses never depend on the place: even the open sea carries them.
        assert build_scene_brief(conn, sea, [])["reading_lenses"]["text"] == lenses
        assert build_scene_brief(conn, sea, [])["cultures"] == []

        # Narrator search excludes engine-only and open Parts; the filter is real, not vacuous.
        query = "Simulation anchor summary living Sixth Stage census registry open questions banked passes"
        unfiltered = search_canon(query, limit=12, conn=conn)
        assert any(not narrator_may_receive(c.heading_path) for c in unfiltered), [c.heading_path for c in unfiltered]
        filtered = search_canon(query, limit=12, conn=conn, exclude_prefixes=NARRATOR_EXCLUDED_PARTS)
        assert filtered and all(narrator_may_receive(c.heading_path) for c in filtered), [c.heading_path for c in filtered]

        # Every brief's World Bible sources are unchanged since the brief was written.
        assert brief_staleness(conn) == [], brief_staleness(conn)
        for key, culture in load_briefs()["cultures"].items():
            assert culture["text"] and culture["sources"], key

        # The full scene packet carries the brief and obeys the exclusion.
        player = conn.execute("SELECT id FROM actors WHERE name='[DEMO] Player Wanderer'").fetchone()
        set_player(conn, int(player["id"]), "Scene Brief Test")
        packet = build_scene_packet(conn, "I walk into the inn and greet the clan head")
        assert packet["scene_brief"]["reading_lenses"]["text"] == lenses
        assert all(narrator_may_receive(c["heading"]) for c in packet["canon"]), [c["heading"] for c in packet["canon"]]
        assert any("scene_brief" in rule for rule in packet["narrator_rules"])
        if packet["scene_brief"]["cultures"]:
            assert "Culture briefs:" in render_scene_brief(packet)

    print("SCENE-01 scene brief test passed")


if __name__ == "__main__":
    run()
