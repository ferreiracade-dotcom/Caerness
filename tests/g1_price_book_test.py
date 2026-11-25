"""G1: the price book. `lookup prices <thing>` answers from the package's sourced figures with the buyer's pay beside them,
every kind of thing a person might buy is covered, later years scale, and a scene shows prices only when a purchase is in
play."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"}}, "accept": True}
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"p{_n[0]:03d}"


def dollars(text: str) -> float:
    return float(text.split()[0].lstrip("$").replace(",", ""))


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        for name in ("CAERNESS_BACKUP_DIR", "CAERNESS_WORLDS_DIR", "CAERNESS_SHELVED_WORLDS"):
            os.environ.pop(name, None)
        from connector import campaign, server
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("g1", package="saintjude")
        server.author(cid(), "protagonist", PROTAGONIST)
        with connect() as conn:
            shop = conn.execute("SELECT id FROM civilian_enterprises WHERE status='active' ORDER BY id LIMIT 1").fetchone()[0]
        assert not server.money(cid(), "wage", {"worker": "me", "business": f"business:{shop}", "weekly": 143}).get("error")

        # every item says where its figure comes from
        book = json.loads((ROOT / "worlds/saintjude/prices.json").read_text(encoding="utf-8"))
        keys = [i["key"] for i in book["items"]]
        assert len(keys) == len(set(keys)), "an item key is used twice"
        for item in book["items"]:
            if item.get("ref"):
                continue
            assert item.get("source") and (item.get("mark") == "Design proposal") == (item["source"] == "unsourced"), item
            assert item.get("mark") in ("Design proposal", "Sourced"), item
            assert item["mark"] != "Sourced" or item.get("url"), item
            assert item["price"] > 0 and item["low"] <= item["price"] <= item["high"], item

        got = server.lookup("prices good suit")
        assert got["found"] and got["year"] == 1975 and got["weekly_pay"] == "$143", got
        suit = got["prices"][0]
        assert "suit" in suit["item"].lower() and suit["price"] == "$143" and suit["weeks_pay"] == 1.0, suit
        assert suit["basis"] == "Sourced" and "New York" in suit["source"], suit

        for term in ("room", "one-bedroom", "house rent", "buy a house", "used car", "new car", "suit", "jacket", "shoes", "dinner",
                     "beers", "a dance", "night out", "ring", "furniture", "tools", "shop equipment", "lease a storefront",
                     "buy a small shop building", "electricity", "insurance", "television", "phone line", "gift"):
            out = server.lookup(f"prices {term}")
            assert out.get("found") and out["prices"], (term, out)
        used = server.lookup("prices used car")["prices"]
        assert len(used) >= 3 and all("used" in p["item"].lower() for p in used[:3]), used
        new = server.lookup("prices new car")["prices"]
        assert "new" in new[0]["item"].lower(), new

        # rents point at the package's own table, so there is one figure for each
        rents = server.lookup("prices two bedroom rent")["prices"]
        walk = [p for p in rents if p["price"] == "$140 a month"]
        assert walk and walk[0]["range"] == "$100 to $190", rents

        listing = server.lookup("prices")
        assert not listing["found"] and len(listing["groups"]) >= 10, listing
        assert not server.lookup("prices zeppelin")["found"]
        assert server.lookup("Dominic Basile")["found"]  # ordinary lookups are as before

        # a scene shows prices only when buying is in the air
        assert "prices" not in (server.scene().get("market") or {})
        server.note(cid(), "Dominic brushes the sawdust off his suit and says nothing about it.", kind="scene")
        assert "prices" not in (server.scene().get("market") or {})
        server.note(cid(), "Rain on the window. Dominic stops at Feld's and wonders what that suit costs. A bus goes by.", kind="scene")
        shown = server.scene()["market"]["prices"]
        assert shown and all("suit" in p["item"].lower() for p in shown) and len(shown) <= 5, shown
        assert server.resume()["scene"]["market"]["prices"], "resume carries the scene's prices"

        # later years, later prices
        with connect() as conn:
            conn.execute("UPDATE world_state SET current_day=current_day+365*5+2")
            conn.commit()
        later = server.lookup("prices good suit")
        assert later["year"] == 1980 and dollars(later["prices"][0]["price"]) == round(143 * 1.532), later
    print("PASS g1_price_book_test")


if __name__ == "__main__":
    main()
