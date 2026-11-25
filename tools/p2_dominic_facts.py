"""Write a save's agreed facts into it: cash, wages, standing payments, shares, past jobs, standing rules, and the clean-up
of records the playthrough logged wrongly: a marriage the player never made, people recorded with the wrong work or place,
things nobody holds, sheets cut short, and epithet or numbered names. The facts are data (tools/saves/dominic.json): correct
a figure there; bump "version" to apply a corrected file to a save that already took an earlier one.

    python tools/p2_dominic_facts.py <save.db>                              dry run on a throwaway copy
    python tools/p2_dominic_facts.py <save.db> --apply --backup <new.db>    back the save up, then write

Stop the connector first. A person who cannot be told apart is reported and what depends on them is skipped; name them with
--person "Name=actor id". A second apply changes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FACTS = ROOT / "tools" / "saves" / "dominic.json"


class Stop(Exception):
    pass


class Writer:
    def __init__(self, conn, facts: dict, overrides: dict[str, int]):
        from engine import world_calendar
        from engine.world_package import current_package

        self.conn, self.facts, self.overrides = conn, facts, overrides
        self.pkg, self.calendar = current_package(conn), world_calendar
        self.day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        self.call = f"tool:{facts['version']}"
        self.report: list[str] = []
        row = conn.execute("SELECT a.id,a.name FROM player_state p JOIN actors a ON a.id=p.player_actor_id WHERE p.id=1").fetchone()
        want = facts["protagonist"].split()
        if not row or row["name"].split()[0] != want[0] or row["name"].split()[-1] != want[-1]:
            raise Stop(f"this save's protagonist is {row['name'] if row else 'not set'}, not {facts['protagonist']}")
        self.me, self.names = int(row["id"]), {facts["protagonist"]: int(row["id"])}
        self.business = self._business()

    def say(self, text: str) -> None:
        self.report.append(text)

    def date(self, text: str) -> int:
        return int(self.calendar.day_for_date(self.pkg, text))

    def _business(self) -> int:
        r = self.conn.execute("SELECT id FROM civilian_enterprises WHERE name=? AND status!='closed'", (self.facts["business"],)).fetchall()
        if len(r) != 1:
            r = self.conn.execute("SELECT enterprise_id AS id FROM enterprise_staff WHERE actor_id=? AND status='active'",
                                  (self.me,)).fetchall()
        if len(r) != 1:
            raise Stop(f"cannot tell which business is {self.facts['business']}")
        return int(r[0]["id"])

    def person(self, name: str) -> int | None:
        """Exact name, else the one person of that first (and last) name he is tied to, works with or the GM made."""
        if name in self.names:
            return self.names[name]
        if name in self.overrides:
            found = [self.overrides[name]]
        else:
            c, me = self.conn, self.me
            close = {int(r[0]) for r in c.execute(
                """SELECT actor_b_id FROM relationships WHERE actor_a_id=? UNION SELECT actor_a_id FROM relationships WHERE actor_b_id=?
                   UNION SELECT actor_id FROM enterprise_staff WHERE enterprise_id=? AND status='active'
                   UNION SELECT entity_id FROM authored_entities WHERE entity_table='actors'""", (me, me, self.business))}
            rows = c.execute("SELECT id,name FROM actors WHERE actor_type='character' AND status='active' AND (name=? OR name LIKE ?)",
                             (name, name.split()[0] + " %")).fetchall()
            last = name.split()[-1] if " " in name else None
            rows = [r for r in rows if last is None or r["name"].split()[-1] == last]
            exact = [int(r["id"]) for r in rows if r["name"] == name]
            found = exact if len(exact) == 1 else [int(r["id"]) for r in rows if int(r["id"]) in close]
            if len(found) > 1:  # family and workmates before acquaintances
                near = {int(r[0]) for r in c.execute(
                    """SELECT actor_id FROM enterprise_staff WHERE enterprise_id=? AND status='active'
                       UNION SELECT related_actor_id FROM kinship WHERE actor_id=?""", (self.business, me))}
                found = [i for i in found if i in near] or found
        if len(found) != 1:
            self.say(f"MISSING: {name}: " + ("nobody he knows by that name" if not found else f"several people ({found})"))
            return None
        self.names[name] = found[0]
        return found[0]

    def ref(self, who: str) -> str | None:
        if who == "business":
            return f"business:{self.business}"
        i = self.person(who)
        return None if i is None else f"person:{i}"

    # ---- people ----

    def names_straight(self) -> None:
        from engine import name_repair

        changed = name_repair.repair_names(self.conn)
        if changed:
            self.say(f"names repaired: {len(changed)}, e.g. " + "; ".join(f"{a} -> {b}" for a, b in list(changed.items())[:3]))

    def unmarry(self) -> None:
        """A marriage the engine made offstage is taken back: ties, home, feelings and the news of it."""
        from engine import civilian, corrections

        c, me = self.conn, self.me
        for m in self.facts.get("unmarry", []):
            found = c.execute(
                """SELECT a.id,a.name,u.started_day FROM household_unions u
                   JOIN actors a ON a.id=CASE WHEN u.actor_a_id=? THEN u.actor_b_id ELSE u.actor_a_id END
                   WHERE (u.actor_a_id=? OR u.actor_b_id=?) AND a.name=?""", (me, me, me, m["spouse"])).fetchall()
            if not found:
                self.say(f"MISSING: no marriage to {m['spouse']} on the record")
                continue
            her, name, day = int(found[0]["id"]), found[0]["name"], int(found[0]["started_day"])
            pair = (me, her, her, me)
            words = next((r[0] for r in c.execute("SELECT text FROM error_reports WHERE status='open' ORDER BY id DESC")
                          if name.split()[0] in r[0]), m["player_said"])
            reverse = [{"table": "relationships", "action": "delete", "where": {"actor_a_id": r[0], "actor_b_id": r[1]}}
                       for r in c.execute("""SELECT actor_a_id,actor_b_id FROM relationships WHERE started_day=? AND
                           ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))""", (day, *pair)).fetchall()]
            news = [int(r[0]) for r in c.execute(
                """SELECT DISTINCT e.id FROM events e JOIN event_targets t ON t.event_id=e.id WHERE e.event_type='life:union' AND e.day=?
                   AND ((e.source_actor_id=? AND t.actor_id=?) OR (e.source_actor_id=? AND t.actor_id=?))""", (day, *pair)).fetchall()]
            corrections.apply(c, "undo_event", words, {"actors": [me, her], "day": day, "reverse": reverse}, self.call)
            for event in news:
                corrections.apply(c, "undo_event", words, {"event_id": event}, self.call)
            c.execute("""UPDATE actor_life_profiles SET metadata_json=json_patch(COALESCE(metadata_json,'{}'),
                         '{"marital_status":"single","marital_status_basis":null,"spouse_actor_id":null}') WHERE actor_id IN (?,?)""", (me, her))
            home = c.execute("SELECT household_id FROM household_members WHERE actor_id=? AND status='active'", (her,)).fetchone()
            if home is None:
                at = c.execute("SELECT current_location_id FROM actors WHERE id=?", (her,)).fetchone()[0]
                home = (civilian.create_household(c, f"{name}'s household", head_actor_id=her, location_id=at),)
            c.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (home[0], her))
            self.say(f"marriage taken back: {name}, {self.calendar.format_date(self.pkg, day)}; {len(reverse)} tie rows removed, "
                     f"{len(news)} news entries voided, they have their own household")

    def people(self) -> None:
        """Work and place as the story had them, and no held thing for a person."""
        from engine import corrections

        c = self.conn
        for p in self.facts.get("people", []):
            who = self.person(p["person"])
            if who is None:
                continue
            want = {k: v for k, v in p.items() if k != "person"}
            if want:
                try:
                    corrections.apply(c, "person", self.facts["player_said"], {"person": who, **want}, self.call)
                    self.say(f"corrected: {p['person']}: " + ", ".join(f"{k} {v}" for k, v in want.items()))
                except corrections.Refused as e:
                    self.say(f"unchanged: {p['person']}: {e}")
            for r in c.execute("SELECT id,name FROM held_things WHERE status!='ended' AND (owner_actor_id=? OR name=?)",
                               (who, p["person"])).fetchall():
                c.execute("UPDATE held_things SET status='ended',ended_reason='not something anyone holds',end_day=?,updated_day=? WHERE id=?",
                          (self.day, self.day, r["id"]))
                self.say(f"no longer held: {r['name']} (held thing {r['id']})")

    def sheets(self) -> None:
        """A sheet cut short when it was saved is put back whole from the call that saved it."""
        latest: dict[str, str] = {}
        for r in self.conn.execute("SELECT request_json FROM connector_calls WHERE tool='note' ORDER BY rowid"):
            asked = json.loads(r[0])
            if asked.get("kind") == "sheet":
                latest[asked.get("field")] = " ".join(str(asked.get("text") or "").split())
        for field, whole in latest.items():
            row = self.conn.execute("SELECT text FROM character_sheet WHERE field=?", (field,)).fetchone()
            if row and len(row[0]) < len(whole) and whole.startswith(row[0].rstrip("…").rstrip()):
                self.conn.execute("UPDATE character_sheet SET text=? WHERE field=?", (whole, field))
                self.say(f"sheet restored whole: {field}: {whole}")

    # ---- money ----

    def money(self) -> None:
        from engine import agreement_terms, business_data, design, money_records

        me, shop = f"person:{self.me}", f"business:{self.business}"
        for ref, key, label in ((me, "cash", "his cash"), (shop, "till", "the shop's till")):
            was = money_records.cash(self.conn, ref)
            money_records.set_cash(self.conn, ref, self.facts[key]["amount"])
            self.say(f"{label}: {money_records.fmt(self.conn, was)} -> {money_records.fmt(self.conn, self.facts[key]['amount'])}")
        first = next(d for d in range(self.day + 1, self.day + 8)
                     if self.calendar.format_date(self.pkg, d).startswith(self.facts["payday"]))
        for w in self.facts["wages"]:
            worker = self.ref(w["worker"])
            if worker:
                money_records.set_wage(self.conn, worker, shop, w["weekly"], first, self.day)
                self.say(f"wage: {money_records.name_of(self.conn, worker)} {money_records.fmt(self.conn, w['weekly'])} a week from the "
                         f"shop, first on {self.calendar.format_date(self.pkg, first)}")
        for kind in ("board", "living"):
            f = self.facts[kind]
            if f["weekly"] <= 0:
                continue
            to = me if kind == "living" else self.ref(f["to"])
            if not to:
                continue
            agreement_terms.add_term(
                self.conn, ref_kind=kind, ref_id=None, debtor_ref=me, creditor_ref=to, amount_usd=f["weekly"], first_due_day=first,
                every_days=7, grace_days=int(design.figure(self.conn, "money_wage_grace_days", 28)),
                breach_word=business_data.default(self.conn, "breach_word"), purpose=f["what"], day=self.day)
            self.say(f"{kind}: {money_records.fmt(self.conn, f['weekly'])} a week, {f['what']}")

    def shares(self) -> None:
        from engine import money_records

        shop, me = f"business:{self.business}", f"person:{self.me}"
        for s in self.facts["shares"]:
            to = shop if s["to"] == "business" else self.ref(s["to"])
            if not to:
                continue
            self.conn.execute("UPDATE share_rules SET status='ended' WHERE recipient_ref=? AND source_ref=? AND applies=? AND status='active'",
                              (to, me, s["applies"]))
            self.conn.execute("""INSERT INTO share_rules(recipient_ref,source_ref,basis,share,applies,note,created_day)
                                 VALUES (?,?,'profit',?,?,?,?)""", (to, me, s["share"], s["applies"], s["note"], self.day))
            self.say(f"share: {s['share'] * 100:g}% of profit, {s['applies']}, to {money_records.name_of(self.conn, to)}")

    def deals(self) -> None:
        from engine import money_records

        me = f"person:{self.me}"
        for d in self.facts["deals"]:
            customer = self.ref(d["customer"])
            if not customer:
                self.say(f"SKIPPED job: {d['job']}")
                continue
            referrer = self.person(d["referrer"]) if d.get("referrer") else None
            status = d.get("status", "open")
            deal = money_records.add_deal(
                self.conn, customer=customer, provider=me, job=d["job"], quote=d["quote"], parts=d.get("parts", 0), referrer=referrer,
                note=d.get("note", ""), status=status, day=self.date(d["created"]))
            for on, amount in d.get("payments", []):  # history: the cash figure above already includes it, so nothing moves
                self.conn.execute("INSERT INTO deal_payments(deal_id,day,amount_usd,source) VALUES (?,?,?,'recorded')",
                                  (deal, self.date(on), amount))
            if d.get("payments"):
                left = money_records.owing(self.conn, money_records.deal_row(self.conn, deal))
                status = "paid" if left < 0.005 else "open"
                self.conn.execute("UPDATE deals SET status=?,next_try_day=NULL,updated_day=? WHERE id=?",
                                  (status, self.date(d["payments"][-1][0]), deal))
            for c in d.get("collateral", []):
                self.conn.execute("INSERT INTO deal_collateral(deal_id,what,status,day) VALUES (?,?,?,?)",
                                  (deal, c["what"], c["status"], self.date(c["day"])))
            for s in d.get("shares", []):
                to = self.ref(s["to"])
                if not to:
                    continue
                rule = self.conn.execute("SELECT id FROM share_rules WHERE recipient_ref=? AND source_ref=? AND status='active' ORDER BY id DESC",
                                         (to, me)).fetchone()
                self.conn.execute("INSERT INTO share_payments(rule_id,deal_id,day,amount_usd) VALUES (?,?,?,?)",
                                  (rule[0] if rule else None, deal, self.date(s["day"]), s["amount"]))
            self.say(f"job: {d['job']}, {money_records.name_of(self.conn, customer)}, {money_records.fmt(self.conn, d['quote'])}, {status}")

    # ---- the record ----

    def rules(self) -> None:
        from connector import store

        have = {r[0] for r in self.conn.execute("SELECT text FROM standing_rules WHERE status='active'")}
        added = 0
        for text in self.facts["rules"]:
            if " ".join(text.split()) not in have:
                store.record(self.conn, "rule", text, self.call)
                added += 1
        self.say(f"standing rules added: {added}")

    def clean(self) -> None:
        from engine import intake

        c = self.conn
        for v in self.facts["void"]:
            rows = c.execute("""SELECT e.id,e.day,e.title,e.summary FROM events e JOIN knowledge k ON k.truth_event_id=e.id AND k.knower_actor_id=?
                                WHERE e.event_type=? AND e.day BETWEEN ? AND ? AND e.title NOT LIKE '[never happened]%' GROUP BY e.id""",
                             (self.me, v["event_type"], self.date(v["from"]), self.date(v["to"]))).fetchall()
            for r in rows:
                c.execute("DELETE FROM knowledge WHERE knower_actor_id=? AND truth_event_id=?", (self.me, r["id"]))
                c.execute("UPDATE events SET title=?,summary=? WHERE id=?",
                          (f"[never happened] {r['title']}", f"[never happened: {v['reason']}] {r['summary']}", r["id"]))
                self.say(f"voided: {self.calendar.format_date(self.pkg, r['day'])}: {r['summary']}")
        for r in c.execute("SELECT id,text FROM error_reports WHERE status='open'").fetchall():
            if any(w.lower() in r["text"].lower() for w in self.facts["settle_errors"]):
                c.execute("UPDATE error_reports SET status='fixed' WHERE id=?", (r["id"],))
                self.say(f"correction settled: {r['text'][:120]}")
        for r in c.execute("""SELECT id,name,kind_text,shape,call_id,consequences_json FROM held_things
                              WHERE owner_actor_id=? AND status!='ended'""", (self.me,)).fetchall():
            errand = str(r["call_id"] or "").startswith("settle:") and not intake.founds(
                c, " ".join([r["name"], r["kind_text"], *map(str, json.loads(r["consequences_json"] or "[]"))]))
            if r["shape"] in ("person", "rumour") or errand:
                c.execute("UPDATE held_things SET status='ended',ended_reason='not something he holds',end_day=?,updated_day=? WHERE id=?",
                          (self.day, self.day, r["id"]))
                self.say(f"no longer held: {r['name']}")

    def run(self) -> dict:
        for step in (self.names_straight, self.unmarry, self.people, self.sheets, self.money, self.shares, self.deals, self.rules,
                     self.clean):
            step()
        return {"summary": "The agreed facts were written into the save.", "report": self.report}


def _write(save: Path, facts: dict, overrides: dict[str, int]) -> tuple[list[str], bool]:
    """The report, and whether this call wrote it (False: it was already there)."""
    previous = os.environ.get("CAERNESS_DB_PATH")
    os.environ["CAERNESS_DB_PATH"] = str(save)
    try:
        from connector import store
        from engine.db import connect, init_db

        init_db()
        with connect() as conn:
            store.ensure_connector_schema(conn)
            out = store.run_once(conn, f"tool:{facts['version']}", "save_facts", {"version": facts["version"]},
                                 lambda: Writer(conn, facts, overrides).run())
        return out["report"], not out.get("replayed")
    finally:
        if previous is None:
            os.environ.pop("CAERNESS_DB_PATH", None)
        else:
            os.environ["CAERNESS_DB_PATH"] = previous


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", type=Path)
    ap.add_argument("--facts", type=Path, default=FACTS)
    ap.add_argument("--person", action="append", default=[], metavar="NAME=ID")
    a = ap.parse_args(argv)
    save = a.save.resolve()
    if not save.is_file():
        print(f"no save at {save}")
        return 2
    if a.apply and (a.backup is None or a.backup.exists()):
        print("--apply needs --backup <a file that does not exist yet>")
        return 2
    facts = json.loads(a.facts.read_text(encoding="utf-8"))
    overrides = {n.strip(): int(i) for n, _, i in (p.partition("=") for p in a.person)}
    from connector.backup import copy_consistent

    scratch = None
    try:
        if a.apply:
            copy_consistent(save, a.backup)
            target = save
            print(f"backup: {a.backup}")
        else:
            scratch = Path(tempfile.mkdtemp(prefix="save-facts-"))
            target = scratch / save.name
            copy_consistent(save, target)
            print("DRY RUN on a copy; the save is not changed.")
        report, wrote = _write(target, facts, overrides)
    except Stop as e:
        print(f"stopped, nothing written: {e}")
        return 1
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
    if not wrote:
        print("Already applied: nothing changed. What was written then:")
    for line in report:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
