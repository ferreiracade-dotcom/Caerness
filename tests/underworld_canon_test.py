from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    from engine.underworld_canon import (CANON_NETWORKS, CANON_OUTFITS, FIGHTING, HEARTH_CITIES, REGION_DEFAULTS,
                                         SETTLEMENT_CHARACTER)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "canon.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        conn = sqlite3.connect(db)
        actors = {r[0] for r in conn.execute("SELECT name FROM actors WHERE actor_type='institution'")}
        places = {r[0] for r in conn.execute("SELECT name FROM locations")}
        for name, o in list(CANON_OUTFITS.items()) + list(CANON_NETWORKS.items()):
            assert name in actors, name
            assert o["locator"].startswith("["), name
        for name, o in CANON_OUTFITS.items():
            assert o["location"] in places and o["fronts"] and o["activities"], name
        for name, n in CANON_NETWORKS.items():
            for place, strength in n["presence"]:
                assert place in places and strength in ("strong", "present", "thin"), (name, place)
        assert set(HEARTH_CITIES) <= places
        for name, c in SETTLEMENT_CHARACTER.items():
            assert name in places and c["locator"].startswith("[") and 0.3 <= c["density"] <= 2.5, name
            assert sum(c["kinds"].values()) > 0 and isinstance(c["districts"], list), name
        for name, c in REGION_DEFAULTS.items():
            assert c["locator"].startswith("[") and sum(c["kinds"].values()) > 0, name
        owners = {r[0] for r in conn.execute("SELECT DISTINCT political_owner FROM locations WHERE kind='settlement'")}
        assert owners <= set(REGION_DEFAULTS), owners - set(REGION_DEFAULTS)
        for place, specs in FIGHTING.items():
            assert place in places, place
            for s in specs:
                assert s["locator"].startswith("[") and s["legality"] in ("licensed", "tolerated", "unlicensed", "criminal")
                assert s.get("kind", "prize_hall") in ("prize_hall", "back_room", "pit", "private_club")
                assert s["coercion"] in ("voluntary", "coercive") and s.get("location", place) in places
                assert s.get("venue") is None or s["venue"] in places, s
        assert {"Tallow Family", "Greyhook Wharf Company", "Saltwake Combine"} == set(CANON_OUTFITS)
        conn.close()
    print("underworld_canon_test passed")


if __name__ == "__main__":
    run()
