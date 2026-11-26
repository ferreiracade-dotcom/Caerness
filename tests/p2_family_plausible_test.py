"""A family drawn for a new character is one that could exist: neither parent a child at any birth, and no two of its children
carrying names that read as one (Domenic beside Dominic)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.opening_family import draw_origin_family  # noqa: E402
from engine.stated_family import unsaid_ages  # noqa: E402
from tests.sj_fixture import build_saintjude  # noqa: E402


def check_ages() -> None:
    import random
    for n in range(4000):
        age = 18 + n % 30
        fam = draw_origin_family(f"t{n}", age=age, sex="male")
        kids = [age] + [s["age_now"] for s in fam["siblings"]]
        assert fam["father"]["age_now"] - max(kids) >= 18, (n, age, fam)
        assert fam["mother"]["age_now"] - max(kids) >= 16, (n, age, fam)
    for n in range(4000):
        rng = random.Random(n)
        parents = {"mother": {"age": None, "alive": True}, "father": {"age": None, "alive": True}}
        sibs = [{"age": None, "older": n % 2 == 0, "younger": False}]
        unsaid_ages(rng, 24, parents, sibs)
        kids = [24] + [s["age"] for s in sibs]
        assert parents["father"]["age"] - max(kids) >= 18, (n, parents, sibs)
        assert parents["mother"]["age"] - max(kids) >= 16, (n, parents, sibs)


def check_names() -> None:
    from engine.new_character import too_alike
    for a, b in (("Dominic", "Domenic"), ("Dominic", "Dominick"), ("Anna", "Ann"), ("Joseph", "Josephine"), ("Maria", "Marie"),
                 ("Joseph", "Joseph")):
        assert too_alike(a, b), (a, b)
    for a, b in (("Dominic", "Donald"), ("Joseph", "John"), ("Maria", "Martha"), ("Anna", "Angela"), ("Frank", "Francis")):
        assert not too_alike(a, b), (a, b)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("families", package="saintjude")
        seen = 0
        for n, surname in enumerate(("Basile", "Greco", "Moretti", "Kowalski", "Walsh", "Washington") * 5):
            made = server.author(f"p{n}", "protagonist", {
                "name": f"Dominic {surname}", "sex": "male", "age": 22 + n % 7, "place": "South Hill", "work": "mechanic",
                "family": {"parents": {"father": "alive", "mother": "alive"}, "siblings": "three brothers and two sisters"}})
            assert made["status"] == "draft", made
            names = ["Dominic"] + [a["value"].split(", ")[1].split()[0] if a["field"] in ("father", "mother") else a["value"].split()[0]
                                   for a in made["as_stated"] + made["filled"]
                                   if a["field"] in ("father", "mother") and a["value"].startswith("alive, ")
                                   or a["field"].startswith("sibling ") and ", " in a["value"] and not a["value"].endswith("dead")]
            seen += len(names) - 1
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    assert not too_alike(a, b), (surname, names)
        assert seen > 60, seen


if __name__ == "__main__":
    check_ages()
    check_names()
    print("PASS p2_family_plausible_test")
