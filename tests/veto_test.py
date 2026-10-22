"""The veto: every check passes a plausible case and refuses a clashing one naming the clash; nothing is refused for being unlisted."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def refuses(fn, needle, *a, **k):
    from engine.veto import Contradiction
    try:
        fn(*a, **k)
    except Contradiction as e:
        assert needle.lower() in str(e).lower(), (needle, str(e))
        return
    raise AssertionError(f"not refused (wanted {needle!r})")


def run():
    from new_character_test import open_copy
    from engine import veto as v
    from engine.person_ecology import FIRST_FEMALE, FIRST_MALE

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = open_copy(tmp)
        toll = v.find_location(c, "Toll's Reach")
        assert toll is not None and v.find_location(c, "Nowhereville") is None
        # unknown words map without error; the fallback is the commonest domain
        assert v.categorise("lamp-lighter") in {"artisan", "labor"} and v.categorise("zxqv wibble") == "labor"
        assert v.categorise("cadet of House Halloway") == "soldier" and v.categorise("anything", "clerk") == "clerk"

        canon = c.execute("SELECT a.name FROM actors a JOIN source_identity_map m ON m.entity_id=a.id AND m.entity_kind='actor' "
                          "WHERE a.actor_type='character' LIMIT 1").fetchone()[0]
        refuses(v.canon_figure, "canon figure", c, canon)
        v.canon_figure(c, "Tam Underhill")
        v.canon_figure(c, "Brother Tam")  # a single name is fine
        refuses(v.name_taken, "already in use", c, canon)
        refuses(v.name_sex, "names follow sex", FIRST_FEMALE[0] + " Rook", "male")
        assert v.name_sex(FIRST_MALE[0] + " Rook", None) == "male" and v.name_sex("Brother", "male") is None
        refuses(v.same_sex_union, "same-sex", "male", "male")
        v.same_sex_union("male", "female")
        # Stage plausibility
        refuses(v.stage_plausible, "unheard", 25, "merchant", "Third")
        v.stage_plausible(55, "merchant", "Third")          # a retired master
        v.stage_plausible(45, "criminal", "Third")
        v.stage_plausible(22, "soldier", "Breach")  # no fixed age caps on a Stage: canon's Blake Merrin was a Sixth at 34
        v.stage_plausible(30, "soldier", "Fifth")
        refuses(v.stage_plausible, "forty Sixths", 80, "soldier", "Sixth")
        v.stage_plausible(30, "merchant", "Temper")
        v.stage_plausible(30, "merchant", "a quiet sort of talent")  # free text claims no Stage
        # held by another
        refuses(v.held_by_other, "already has its leader", c, "Stone Boars", "boss")
        refuses(v.held_by_other, "already has its head", c, "House Halloway", "head of the house")
        assert v.held_by_other(c, "House Halloway", "cadet")["kind"] == "institution"  # an ordinary place is fine
        refuses(v.held_by_other, "no body called", c, "House Nonesuch", "cadet")
        assert v.held_by_other(c, "House Nonesuch", "head", new=True) is None
        # named kin
        dead = c.execute("SELECT a.name FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id WHERE p.life_status<>'living' LIMIT 1").fetchone()[0]
        refuses(v.kin_alive, "dead", c, dead, "father", 45)
        assert v.kin_alive(c, "An Unnamed Cousin", "cousin", 45) is None
        # world scale: nothing fixed, everything from the place
        sc = v.place_scale(c, toll)
        assert sc["population"] == 110000 and sc["outfit_members"] > 100 and sc["enterprises"] >= 8
        small = int(c.execute("SELECT s.location_id FROM background_population_sources s JOIN underworld_organizations u ON u.primary_location_id=s.location_id "
                              "GROUP BY s.location_id ORDER BY SUM(u.member_count_estimate) LIMIT 1").fetchone()[0])
        assert v.place_scale(c, small)["outfit_members"] < sc["outfit_members"] / 5
        adj, down = v.holdings_in_proportion(c, small, [{"kind": "outfit", "name": "The Rooks", "members": 25}])
        assert adj[0]["members"] < 25 and down and "men" in down[0]["why"], (adj, down)
        adj, down = v.holdings_in_proportion(c, toll, [{"kind": "gang", "name": "The Rooks", "members": 25}])
        assert adj[0]["members"] == 25 and not down
        adj, down = v.holdings_in_proportion(c, small, [{"kind": "tavern", "name": "A", "amount": "fortune"}])
        assert adj[0]["amount"] < 60 and down and "the town" in down[0]["why"]
        adj, down = v.holdings_in_proportion(c, toll, [{"kind": "tavern", "name": "A", "amount": "substantial"}])
        assert not down and adj[0]["amount"] == 8.0
        adj, down = v.holdings_in_proportion(c, toll, [{"kind": "tavern", "name": "A", "amount": "fortune"}])
        assert down, "a fortune larger than the town"
        # a district counts by its parent city
        dist = c.execute("SELECT id FROM locations WHERE kind IN ('city district','port district','commercial district') AND parent_location_id IS NOT NULL LIMIT 1").fetchone()
        assert dist is not None and v.settlement_of(c, int(dist[0])) is not None and v.place_scale(c, int(dist[0]))["population"] > 0
        # the whole proposal
        base = {"age": 40, "place": "Toll's Reach", "work": "lamp-lighter", "draw": 0}
        assert v.check_proposal(c, base)["category"] in {"artisan", "labor"}
        refuses(v.check_proposal, "no place called", c, {**base, "place": "Nowhereville"})
        refuses(v.check_proposal, "canon figure", c, {**base, "name": canon})
        refuses(v.check_proposal, "same-sex", c, {**base, "sex": "male", "family": {"spouse": "a husband"}})
        refuses(v.check_proposal, "unheard", c, {**base, "age": 25, "work": "merchant", "stage": "Third"})
        refuses(v.check_proposal, "dead", c, {**base, "family": {"parents": [{"name": dead}]}})
        refuses(v.check_proposal, "no spouse", c, {**base, "age": 12, "family": {"spouse": "a wife"}})
        # only the spouse word decides: a widower and a daughter in the same breath are not a second spouse
        v.check_proposal(c, {**base, "sex": "female", "family": {"spouse": "a husband, a widower with a daughter"}})
        v.check_proposal(c, {**base, "sex": "male", "family": {"spouse": "a wife who is a widow's daughter"}})
        refuses(v.check_proposal, "same-sex", c, {**base, "sex": "female", "family": {"spouse": "a wife"}})
        # zero is a valid answer: where the town can bear nothing more, the holding is dropped and said so
        adj, down = v.holdings_in_proportion(c, toll, [{"kind": "tavern", "name": "B", "amount": "modest"}], prior_wealth=1e6)
        assert adj == [] and down and down[0]["got"] == "nothing", (adj, down)
        v.check_proposal(c, {**base, "affiliation": {"name": "House Halloway", "role": "cadet"}})
        c.close()
    print("veto_test: ok")


if __name__ == "__main__":
    run()
