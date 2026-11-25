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
        assert "error" not in server.note(cid(), "The careful man entry is void; ask again later", "error")
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

        extra = {}
        for name, sex in (("Lucia Fernandes", "female"), ("Paul Ricci", "male"), ("Tullio Bruni", "male")):
            out = server.author(cid(), "person", {"name": name, "sex": sex, "age": 24, "place": "South Hill", "from_elsewhere": True})
            assert out.get("actor_id"), out
            extra[name] = out["actor_id"]
        her, paul = extra["Lucia Fernandes"], extra["Paul Ricci"]
        sheet = " ".join(f"week {i} he put money by" for i in range(30))
        server.note(cid(), sheet, "sheet", field="money")
        with connect() as conn:  # as the playtest left it: a marriage drawn offstage, a person held as a thing, a sheet cut short
            from engine.interactions import _log_event
            from engine.opening_family import _form_revealed_union

            conn.execute("DELETE FROM household_members WHERE actor_id=?", (her,))
            wed = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0] + 180
            conn.execute("UPDATE world_state SET current_day=?", (wed,))
            _form_revealed_union(conn, me, her, married_day=wed, day=wed, family_plan={}, basis="run_time_marriage")
            news = _log_event(conn, wed, "life:union", "Marriage", "Dominic Basile married Lucia Fernandes.", 1, me, (her,))
            conn.execute("UPDATE world_state SET current_day=?", (wed + 19,))
            conn.execute("INSERT INTO held_things(name,shape,owner_actor_id,start_day,call_id,created_day,updated_day) "
                         "VALUES ('Owner of a busy restaurant','enterprise',?,?,'a9',?,?)", (paul, wed, wed, wed))
            conn.execute("UPDATE character_sheet SET text=substr(text,1,299)||'\u2026' WHERE field='money'")
            conn.commit()
        server.note(cid(), "Dominic never married Lucia Fernandes; that did not happen", "error")

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
        assert after[0] == 2512, after
        assert tool.main([str(save), "--apply", "--backup", str(Path(tmp) / "again.db")]) == 0
        assert state() == after, ("a second apply wrote", after, state())

        with connect() as conn:
            deals = {r["job"]: (r["status"], r["quote"], money_records.paid_on(conn, r["id"]))
                     for r in conn.execute("SELECT * FROM deals")}
            assert sorted(v[1] for v in deals.values() if v[0] == "paid" and v[1] == v[2]) == [85, 120, 350, 350, 900, 900, 900], deals
            assert sorted(v[1] for v in deals.values() if v[0] == "declined") == [350, 900, 1900], deals
            assert conn.execute("SELECT status FROM deal_collateral").fetchone()[0] == "returned"
            assert conn.execute("SELECT SUM(amount_usd) FROM share_payments").fetchone()[0] == 16
            assert conn.execute("SELECT COUNT(*) FROM share_rules WHERE status='active'").fetchone()[0] == 4
            assert not conn.execute("SELECT 1 FROM knowledge WHERE truth_event_id=?", (ev,)).fetchone()
            assert conn.execute("SELECT title FROM events WHERE id=?", (ev,)).fetchone()[0].startswith("[never happened]")
            assert not conn.execute("SELECT 1 FROM error_reports WHERE status='open'").fetchone()
            for table in ("household_unions", "relationships"):
                assert not conn.execute(f"SELECT 1 FROM {table} WHERE (actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)",
                                        (me, her, her, me)).fetchone(), table
            assert not conn.execute("SELECT 1 FROM kinship_links WHERE kin_kind='spouse' AND actor_a_id IN (?,?)", (me, her)).fetchone()
            homes = [[r[0] for r in conn.execute("SELECT household_id FROM household_members WHERE actor_id=? AND status='active'", (i,))]
                     for i in (me, her)]
            assert len(homes[1]) == 1 and homes[1][0] not in homes[0], homes
            assert conn.execute("SELECT title FROM events WHERE id=?", (news,)).fetchone()[0].startswith("[never happened]")
            assert not conn.execute("SELECT 1 FROM held_things WHERE owner_actor_id=? AND status!='ended'", (paul,)).fetchone()
            there = conn.execute("SELECT l.name,a.subtype FROM actors a JOIN locations l ON l.id=a.current_location_id WHERE a.id=?",
                                 (paul,)).fetchone()
            assert there[0] == "The Eastside" and "restaurant" in there[1], tuple(there)
            assert conn.execute("SELECT text FROM character_sheet WHERE field='money'").fetchone()[0] == sheet
            assert not conn.execute("SELECT 1 FROM held_things WHERE owner_actor_id=? AND status!='ended' AND call_id IN ('a1','settle:9')",
                                    (me,)).fetchone()
        rules = server.resume_current()["story"]["standing_rules"]
        assert any("half pay" in r for r in rules) and not any(r.endswith("…") for r in rules), rules

        for _ in range(4):
            out = server.advance(cid(), 7, "work at the garage", from_day=server.scene()["day"])
            assert "error" not in out, out
        with connect() as conn:
            # four paydays at the agreed wage
            assert money_records.cash(conn, f"person:{me}") == 2512 + 4 * 55, money_records.cash(conn, f"person:{me}")
            short = conn.execute("SELECT creditor_ref,owed_usd FROM agreement_terms WHERE ref_kind='wage' AND (owed_usd>0 OR status!='active')").fetchall()
            assert not short, [tuple(r) for r in short]
            paid = conn.execute("SELECT SUM(amount) FROM economic_flows WHERE flow_kind='wage' AND source_enterprise_id IS NOT NULL AND day>?",
                                (day,)).fetchone()[0]
            assert paid >= 4 * 455, paid
    print("PASS p2_dominic_facts_test")


if __name__ == "__main__":
    main()
