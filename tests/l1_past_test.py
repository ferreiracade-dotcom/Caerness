"""L1 task 3: the outfits and their men start with a past that is consistent with canon and balances."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.sj_fixture import build_saintjude, connect  # noqa: E402

PAST = json.loads((ROOT / "worlds" / "saintjude" / "outfits.json").read_text(encoding="utf-8"))["opening_past"]


def _conn(tmp):
    return connect(build_saintjude(Path(tmp)))


def test_canon_events_are_dated_in_their_year():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        for ev in PAST["canon_events"]:
            rows = c.execute("""SELECT i.day,i.kind,i.status,a.name FROM org_incidents i JOIN org_seats s ON s.actor_id=i.offender_actor_id
                                JOIN actors a ON a.id=s.org_actor_id WHERE json_extract(i.metadata_json,'$.history')=?""", (ev["text"],)).fetchall()
            assert len(rows) == 1, (ev["text"], rows)
            day, kind, status, org = rows[0]
            assert kind == ev["kind"] and status == "done" and org == ev["offender_org"], tuple(rows[0])
            want = (date(ev["year"], 7, 1) - date(1975, 1, 1)).days
            assert day == want, (day, want)
        c.close()


def test_incidents_are_history_and_whole():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        rows = c.execute("""SELECT i.id,i.day,i.offender_actor_id o,i.victim_actor_id v,i.matters,i.status,i.raised_to_org_actor_id FROM org_incidents i""").fetchall()
        assert len(rows) > 100
        for r in rows:
            assert r["day"] < 0 and r["matters"] == 0 and r["status"] == "done" and r["raised_to_org_actor_id"] is None, tuple(r)
            for who in (r["o"], r["v"]):
                if who is None:
                    continue
                bd = c.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (who,)).fetchone()[0]
                assert (r["day"] - bd) / 365.0 >= 16.0, (tuple(r), who)
            if r["v"] is not None:   # the victim remembers it: a relationship toward the offender exists
                assert c.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (r["v"], r["o"])).fetchone(), tuple(r)
        c.close()


def test_debts_balance_and_follow_canon():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        names = {r[0]: r[1] for r in c.execute("SELECT id,name FROM actors WHERE actor_type='institution'")}
        got = {(names[r["creditor_org"]], names[r["debtor_org"]]) for r in c.execute("SELECT * FROM org_debts")}
        assert got == {(p["creditor"], p["debtor"]) for p in PAST["debts"]["pairs"]}, got
        for r in c.execute("SELECT * FROM org_debts"):
            assert 0 <= r["paid"] <= r["amount"] and r["since_day"] < 0 and r["status"] == "open"
        # history is not a transfer: nothing was paid or moved at the opening
        assert c.execute("SELECT COUNT(*) FROM org_money").fetchone()[0] == 0
        c.close()


def test_heat_follows_the_incidents_and_obligations_follow_the_ladder():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        orgs_with = {r[0] for r in c.execute("""SELECT s.org_actor_id FROM org_incidents i JOIN org_seats s ON s.actor_id=i.offender_actor_id""")}
        heated = {r[0] for r in c.execute("SELECT org_actor_id FROM org_heat WHERE public_heat>=0 AND violence_heat>=0")}
        assert heated and heated <= orgs_with | heated
        for r in c.execute("SELECT * FROM org_heat"):
            assert r["updated_day"] < 0 and r["violence_heat"] > 0
        for r in c.execute("SELECT * FROM obligations WHERE source_kind='opening_past'"):
            assert r["status"] == "active" and r["due_day"] is None and r["counterparty_actor_id"] is not None
            assert c.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND superior_actor_id=?", (r["actor_id"], r["counterparty_actor_id"])).fetchone()
        assert c.execute("SELECT COUNT(*) FROM obligations WHERE source_kind='opening_past'").fetchone()[0] > 20
        c.close()


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
