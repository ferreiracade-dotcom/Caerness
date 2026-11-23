"""L1 task 2: ordinary businesses across the neighbourhoods, in the package's mix, with real owners and staff."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.sj_fixture import build_saintjude, connect  # noqa: E402

CFG = json.loads((ROOT / "worlds" / "saintjude" / "neighbourhood.json").read_text(encoding="utf-8"))


def _conn(tmp):
    return connect(build_saintjude(Path(tmp)))


def _expected_total():
    tot = sum(float(d["share"]) for d in CFG["districts"])
    n = 0.0
    for d in CFG["districts"]:
        pop = CFG["residents"]["value"] * d["share"] / tot
        for k, v in CFG["rates_per_1000"].items():
            n += pop / 1000 * v["rate"] * (d.get("mix") or {}).get(k, 1.0) * CFG["named_share"]["value"]
    return n


def test_count_follows_the_package():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        n = c.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE json_extract(metadata_json,'$.opening_business')=1").fetchone()[0]
        exp = _expected_total()
        assert 0.85 * exp <= n <= 1.15 * exp, (n, exp)
        names = [r[0] for r in c.execute("SELECT name FROM civilian_enterprises")]
        assert len(names) == len(set(names))
        c.close()


def test_every_business_is_whole():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        rows = c.execute("SELECT id,owner_actor_id,json_extract(metadata_json,'$.trade') trade FROM civilian_enterprises").fetchall()
        assert rows
        for r in rows:
            eid = r["id"]
            assert c.execute("SELECT 1 FROM actors WHERE id=? AND actor_type='character'", (r["owner_actor_id"],)).fetchone()
            assert c.execute("SELECT 1 FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND role='owner'", (eid, r["owner_actor_id"])).fetchone()
            pk = c.execute("SELECT place_kind,owner_ref FROM place_details WHERE enterprise_id=?", (eid,)).fetchone()
            assert pk and pk["place_kind"] == CFG["profiles"][r["trade"]]["place_kind"], (eid, tuple(pk) if pk else None)
            assert pk["owner_ref"] == f"person:{r['owner_actor_id']}"
            assert c.execute("""SELECT 1 FROM enterprise_business_profiles p JOIN business_archetypes b ON b.id=p.archetype_id
                                WHERE p.enterprise_id=? AND b.archetype_key=?""", (eid, r["trade"])).fetchone(), eid
        c.close()


def test_owners_are_background_people_and_not_outfit_members():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        bad = c.execute("""SELECT e.id FROM civilian_enterprises e JOIN org_seats s ON s.actor_id=e.owner_actor_id AND s.status='active'""").fetchall()
        assert not bad, bad[:5]
        unlinked = c.execute("""SELECT e.id FROM civilian_enterprises e LEFT JOIN background_person_profiles p ON p.actor_id=e.owner_actor_id
                                WHERE p.actor_id IS NULL""").fetchall()
        assert not unlinked, unlinked[:5]   # no actor was created from nothing: every owner is a pre-existing identity
        c.close()


def test_district_mix_and_communities():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        share = {d["location"]: d["share"] for d in CFG["districts"]}

        def per_share(trade, loc):
            n = c.execute("""SELECT COUNT(*) FROM civilian_enterprises e JOIN locations l ON l.id=e.location_id
                             WHERE l.name=? AND json_extract(e.metadata_json,'$.trade')=?""", (loc, trade)).fetchone()[0]
            return n / share[loc]
        assert per_share("bar", "Kerrytown") > 2 * per_share("bar", "The Heights")
        assert per_share("law_office", "Crown Harbor") > 2 * per_share("law_office", "The Eastside")
        black = set(json.loads((ROOT / "worlds" / "saintjude" / "names.json").read_text(encoding="utf-8"))["groups"]["black"]["family"])
        rows = c.execute("""SELECT a.name FROM civilian_enterprises e JOIN actors a ON a.id=e.owner_actor_id JOIN locations l ON l.id=e.location_id
                            WHERE l.name='Dunmore Avenue'""").fetchall()
        assert rows and sum(1 for r in rows if r[0].split()[-1] in black) >= 0.7 * len(rows)
        c.close()


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
