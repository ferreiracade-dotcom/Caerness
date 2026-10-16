from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CAERNESS_CAMPAIGN_DIR"] = tmp
        from connector.campaign import connect_campaign, open_campaign
        from connector.lore import lore

        open_campaign("lore")  # loads the World Bible into the campaign when it is missing
        with connect_campaign() as conn:
            assert conn.execute("SELECT COUNT(*) FROM canon_chunks").fetchone()[0] > 0
            r = lore(conn, "cultivation stages Temper Breach Sixth")
            assert r["passages"], r
            text = " ".join(p["text"] for p in r["passages"])
            assert "Temper" in text and all(p["section"] for p in r["passages"]), r
            assert len(json.dumps(r, ensure_ascii=False)) <= 6000
            empty = lore(conn, "zzqqxx")
            assert empty["passages"] == [] and empty["hint"]
            assert lore(conn, "   ")["passages"] == []
    print("connector_lore_test passed")


if __name__ == "__main__":
    run()
