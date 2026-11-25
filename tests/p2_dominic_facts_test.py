"""P2: the one-off tool that writes the owner's agreed facts into the Dominic save: dry run changes nothing, apply needs a
backup, a second apply changes nothing, and the agreed wages are then paid through skips."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {
    "name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
    "family": {"parents": [{"as": "father", "alive": True, "name": "Louis"}, {"as": "mother", "alive": True, "name": "Josephine"}],
               "siblings": [{"sex": "male", "age": 21, "name": "Vincent"}, {"sex": "male", "age": 18, "name": "Anthony"}]},
    "family_business": {"name": "Basile & Sons Auto Repair", "type": "garage", "owner": "father", "works": ["self", "siblings"]},
    "people": [{"name": "Frank Amato", "relation": "best friend", "since": "since boyhood", "age": 24},
               {"name": "Gennaro Pace", "relation": "older mechanic at the garage", "work": "mechanic", "works": True},
               {"name": "Stanley Wojcik", "relation": "mechanic at the garage", "work": "mechanic", "works": True}],
    "accept": True}
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"d{_n[0]:03d}"


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        import p2_dominic_facts as tool
        from connector import campaign, server
        from engine import money_records
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("dominic", package="saintjude")
        made = server.author(cid(), "protagonist", PROTAGONIST)
        assert made["status"] == "created", made
        me = made["actor_id"]
        for name, sex in (("Samuel Harris", "male"), ("Rocco Ferraro", "male"), ("Gerald Orsini", "male")):
            out = server.author(cid(), "person", {"name": name, "sex": sex, "age": 23, "place": "South Hill", "from_elsewhere": True})
            assert out.get("actor_id") or "already in use" in out["reason"], out  # the city may have one of that name
        save = Path(os.environ["CAERNESS_DB_PATH"])
        server.note(cid(), "error", "The careful man entry is void; ask again later")
        with connect() as conn:
            day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            ev = conn.execute("INSERT INTO events(day,event_type,title,summary) VALUES (42,'interaction:demand:rejected',"
                              "'Demand refused','Samuel Harris refused the demand.')").lastrowid
            conn.execute("INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,truth_event_id,learned_day) "
                         "VALUES (?,?,'Samuel Harris refused the demand.',?,42)", (me, f"event:{ev}", ev))
            for held, shape, call in (("Gennaro Pace", "person", "a1"), ("have a word with the foreman", "enterprise", "settle:9")):
                conn.execute("INSERT INTO held_things(name,shape,owner_actor_id,start_day,call_id,created_day,updated_day,"
                             "consequences_json) VALUES (?,?,?,?,?,?,?,?)",
                             (held, shape, me, day, call, day, day, json.dumps([held])))
            conn.commit()

        def state() -> tuple:
            with connect() as conn:
                return (money_records.cash(conn, f"person:{me}"),
                        conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0],
                        conn.execute("SELECT COUNT(*) FROM agreement_terms WHERE status='active'").fetchone()[0],
                        conn.execute("SELECT COUNT(*) FROM standing_rules").fetchone()[0])

        before = state()
        assert tool.main([str(save)]) == 0
        assert state() == before, ("a dry run wrote", before, state())
        assert tool.main([str(save), "--apply"]) != 0 and state() == before, "applied without a backup"
        backup = Path(tmp) / "dominic-before.db"
        assert tool.main([str(save), "--apply", "--backup", str(backup)]) == 0
        assert backup.exists() and os.environ["CAERNESS_DB_PATH"] == str(save)
        after = state()
        assert after[0] == 1249, after
        assert tool.main([str(save), "--apply", "--backup", str(Path(tmp) / "again.db")]) == 0
        assert state() == after, ("a second apply wrote", after, state())

        with connect() as conn:
            deals = {r["job"]: (r["status"], r["quote"], money_records.paid_on(conn, r["id"]))
                     for r in conn.execute("SELECT * FROM deals")}
            assert sorted(v for v in deals.values() if v[0] == "paid") == [("paid", 85, 85), ("paid", 120, 120), ("paid", 350, 350)], deals
            assert sorted(v[1] for v in deals.values() if v[0] == "declined") == [350, 900, 1900], deals
            assert conn.execute("SELECT status FROM deal_collateral").fetchone()[0] == "returned"
            assert conn.execute("SELECT SUM(amount_usd) FROM share_payments").fetchone()[0] == 16
            assert conn.execute("SELECT COUNT(*) FROM share_rules WHERE status='active'").fetchone()[0] == 4
            assert not conn.execute("SELECT 1 FROM knowledge WHERE truth_event_id=?", (ev,)).fetchone()
            assert conn.execute("SELECT title FROM events WHERE id=?", (ev,)).fetchone()[0].startswith("[never happened]")
            assert not conn.execute("SELECT 1 FROM error_reports WHERE status='open'").fetchone()
            assert not conn.execute("SELECT 1 FROM held_things WHERE owner_actor_id=? AND status!='ended' AND call_id IN ('a1','settle:9')",
                                    (me,)).fetchone()
        rules = server.resume_current()["story"]["standing_rules"]
        assert any("half pay" in r for r in rules) and not any(r.endswith("…") for r in rules), rules

        for _ in range(4):
            out = server.advance(cid(), 7, "work at the garage", from_day=server.scene()["day"])
            assert "error" not in out, out
        with connect() as conn:
            # four paydays: $125 in, $30 board and $40 of his own spending out
            assert money_records.cash(conn, f"person:{me}") == 1249 + 4 * (125 - 30 - 40), money_records.cash(conn, f"person:{me}")
            short = conn.execute("SELECT creditor_ref,owed_usd FROM agreement_terms WHERE ref_kind='wage' AND (owed_usd>0 OR status!='active')").fetchall()
            assert not short, [tuple(r) for r in short]
            paid = conn.execute("SELECT SUM(amount) FROM economic_flows WHERE flow_kind='wage' AND source_enterprise_id IS NOT NULL AND day>?",
                                (day,)).fetchone()[0]
            assert paid >= 4 * 525, paid
    print("PASS p2_dominic_facts_test")


if __name__ == "__main__":
    main()
