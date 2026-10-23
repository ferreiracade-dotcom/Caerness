"""Lock the Caerness connector surface: rulebook/creation bytes, date format, lore on the packaged opening.

Regenerate the fixture only on purpose: python tests/world_pkg_caerness_connector_test.py --write-fixture
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "caerness_connector_surface.json"


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def surface() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CAERNESS_CAMPAIGN_DIR"] = tmp
        from connector.campaign import connect_campaign, open_campaign
        from connector.lore import lore
        from connector.session import load_creation, load_rulebook
        from connector.views import compact_scene
        from engine.civil_calendar import format_sv_date

        open_campaign("wp1")
        from engine.player import set_player

        with connect_campaign() as conn:
            row = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()
            set_player(conn, int(row["id"]))
            conn.commit()
            scene = compact_scene(conn)
            passages = lore(conn, "Cairnholt")["passages"]
        assert passages, "lore('Cairnholt') returned no passage"
        assert scene["date"] == "1 First Month, 624 SV" == format_sv_date(0), scene["date"]
        return {"rulebook_sha256": _h(load_rulebook()), "creation_sha256": _h(load_creation()),
                "day0_date_format": format_sv_date(0), "scene_date_day0": scene["date"],
                "lore_cairnholt_has_passage": True}


def run():
    got = surface()
    if "--write-fixture" in sys.argv:
        FIXTURE.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("wrote", FIXTURE)
        return
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    exp = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert got == exp, f"connector surface changed:\n got {got}\n exp {exp}"
    print("world_pkg_caerness_connector_test passed")


if __name__ == "__main__":
    run()
