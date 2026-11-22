"""Patronage and favours (politics P1).

An office's patronage is a stake like any other: the holder of the stake holds the office's jobs, and jobs are `org_lines`
described as the package's job kind and tagged with the office. When the office changes hands, the stake moves with the new
holder's own choice (his organisation, else himself) and the lines move with it, so the old holder's organisation loses its
jobs and, through `electorate.delivery`, its hold on the voters. A favour is a ledger entry the receiver owes the giver.
Pay is the city budget's, not an organisation's take, so these lines carry no weekly take.
"""
from __future__ import annotations

import json
import random

from . import civic_field, civic_seams, offices, orgs
from .design import figure
from .world_package import package_for, politics_rules


def _rules(conn) -> dict:
    return politics_rules(package_for(conn))


def _tag(office_key: str) -> str:
    return f"[{office_key}]"


def _kind(conn) -> str:
    return str(_rules(conn).get("patronage_line_kind") or "a public job")


def lines_of(conn, office_key: str) -> list:
    return conn.execute("SELECT * FROM org_lines WHERE status='active' AND description LIKE ? ORDER BY id", (f"%{_tag(office_key)}%",)).fetchall()


def _holder(conn, office_key: str):
    return civic_field.holder_of(conn, "patronage", office_key)


def _place(conn, holder: tuple[str, int] | None, n: int) -> tuple[int | None, int | None]:
    """(unit_id, holder_actor_id) for the n-th line of a holder: an organisation's units in turn, a person himself."""
    if holder is None:
        return None, None
    kind, hid = holder
    if kind == "actor":
        return None, hid
    units = [int(r[0]) for r in conn.execute("SELECT id FROM org_units WHERE org_actor_id=? ORDER BY id", (hid,))]
    if units:
        return units[n % len(units)], None
    return None, orgs.head_of(conn, hid)  # an organisation with no units holds its jobs through its head


def _add_line(conn, office_key: str, holder, n: int, day: int, who: int | None = None) -> int:
    unit, person = _place(conn, holder, n)
    text = f"{_kind(conn)} {_tag(office_key)}" + (" (given)" if who is not None else "")
    return int(conn.execute("INSERT INTO org_lines(unit_id,holder_actor_id,description,weekly_take,status,started_day) VALUES (?,?,?,0,'active',?)",
                            (unit, who if who is not None else person, text, int(day))).lastrowid)


def seed_patronage(conn, day: int) -> int:
    """The opening's jobs: each patronage office's share of the city's job total, held with its patronage stake."""
    total = float(figure(conn, "patronage_jobs_total", 0.0))
    made = 0
    for key, share in ((_rules(conn).get("patronage_1975") or {}).get("offices") or {}).items():
        if lines_of(conn, key):
            continue
        h = _holder(conn, key)
        for i in range(int(round(total * float(share)))):
            _add_line(conn, key, h, i, day)
            made += 1
    return made


def follow(conn, office_key: str, new_holder: int, *, day: int, cause: str = "new_holder") -> int:
    """The office changed hands: its patronage stake goes to the new holder's choice (the organisation he sits in, else himself)
    and the office's jobs go with it. Returns the lines moved."""
    old = conn.execute("SELECT id,holder_kind,holder_id FROM field_holdings WHERE stake_kind='patronage' AND stake_ref=? AND ended_day IS NULL "
                       "ORDER BY strength DESC,id LIMIT 1", (office_key,)).fetchone()
    seat = conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active' AND org_actor_id IN "
                        "(SELECT DISTINCT holder_id FROM field_holdings WHERE holder_kind='org') ORDER BY id LIMIT 1", (int(new_holder),)).fetchone()
    to = ("org", int(seat[0])) if seat else ("actor", int(new_holder))
    if old is None:
        civic_field._open(conn, to[0], to[1], "patronage", office_key, 1.0, day, cause, None)
    elif (old["holder_kind"], int(old["holder_id"])) != to:
        civic_field.transfer(conn, int(old["id"]), to[0], to[1], day=day, cause_kind=cause)
    else:
        return 0
    moved = 0
    for i, ln in enumerate(lines_of(conn, office_key)):
        unit, person = _place(conn, to, i)
        # a line a person was handed stays his; the rest sit with the new holder
        if "(given)" in ln["description"]:
            continue  # a job handed to a person stays his
        conn.execute("UPDATE org_lines SET unit_id=?,holder_actor_id=? WHERE id=?", (unit, person, int(ln["id"])))
        moved += 1
    return moved


def hand_out(conn, office_key: str, to_actor: int, *, day: int, why: str) -> int:
    """The office-holder gives a person a job: one more line, held by him, and a favour he owes the giver."""
    giver = offices.holder(conn, office_key)
    if giver is None:
        raise ValueError(f"{office_key} has no holder to give a job")
    line = _add_line(conn, office_key, _holder(conn, office_key), len(lines_of(conn, office_key)), day, who=int(to_actor))
    favour(conn, int(giver), int(to_actor), f"a job: {why}", day=day)
    return line


def cut(conn, office_key: str, share: float, *, day: int, cause: str) -> int:
    """End a share of the office's jobs (chosen by the day's seed, the same lines for the same seed). Returns the lines ended."""
    rows = lines_of(conn, office_key)
    k = min(len(rows), max(0, int(round(len(rows) * float(share)))))
    pick = random.Random(f"cut:{office_key}:{int(day)}").sample([int(r["id"]) for r in rows], k)
    for i in pick:
        conn.execute("UPDATE org_lines SET status='ended',ended_day=? WHERE id=?", (int(day), i))
    return k


def favour(conn, giver: int, receiver: int, what: str, *, day: int) -> int:
    """A ledger entry of kind `favour`: the receiver owes the giver."""
    return civic_seams.ledger_entry(conn, int(receiver), int(giver), kind="favour", terms={"what": what, "breach_word": "grudge"}, due_day=None, day=int(day))


def owed(conn, a: int, b: int) -> float:
    """The net favours: what `b` owes `a` less what `a` owes `b`."""
    def n(debtor, creditor):
        return conn.execute("SELECT COUNT(*) FROM agreement_terms WHERE status='active' AND ref_kind='favour' AND debtor_ref=? AND creditor_ref=?",
                            (f"person:{int(debtor)}", f"person:{int(creditor)}")).fetchone()[0]
    return float(n(b, a) - n(a, b))
