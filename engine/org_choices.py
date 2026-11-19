"""What a seated man can choose (sphere-free): the decision provider `org`, the registry of choices and agenda actions.

A sphere registers, per organisation kind, the choices its men have: `register_choice(org_kind, choice, candidate_fn,
execute_fn)`. The provider offers a seated man only the choices registered for the kinds of his seats that the package
also declares in orgs.json `kinds` (a choice registered for a kind the package does not declare is never offered), and
a man with seats in two organisations gets each one's choices. A choice is considered only on the days his weekly
roll (`org_motives.should_choose`) says so; open agenda items due today are offered through `AGENDA_ACTIONS`.

`candidate_fn(conn, actor_id, org_actor_id, day) -> list[offer]` and agenda actions `fn(conn, actor_id, agenda_row, day)
-> list[offer]` return offers, dicts with `kind` (the action's name; default the choice), `utility`, `rationale`,
`payload`, and optionally `target_actor_id`, `risk`, `cost`. `execute_fn(conn, actor_id, kind, payload, day) -> dict`
(with a `summary`) carries one out; `register_executor` adds executors for kinds a choice offers beyond its own name.
The routine "carry on" is not an offer here: the baseline `hold` candidate of the decision runtime stands for it, and a
quiet man whose roll does not fire is not reviewed at all.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from . import org_motives
from .decision_runtime import DecisionCandidate, register_provider
from .orgs import is_living, kind_rules, register_reason_check, seats_of

CandidateFn = Callable[[sqlite3.Connection, int, int, int], list[dict]]
ExecuteFn = Callable[[sqlite3.Connection, int, str, dict, int], dict]
AgendaFn = Callable[[sqlite3.Connection, int, sqlite3.Row, int], list[dict]]

_CHOICES: dict[str, dict[str, CandidateFn]] = {}  # org kind -> choice -> candidate fn
_EXECUTORS: dict[str, ExecuteFn] = {}
AGENDA_ACTIONS: dict[str, AgendaFn] = {}  # agenda kind -> candidate fn; a kind with no entry (history) needs no action


def register_choice(org_kind: str, choice: str, candidate_fn: CandidateFn, execute_fn: ExecuteFn) -> None:
    _CHOICES.setdefault(str(org_kind), {})[str(choice)] = candidate_fn
    _EXECUTORS[str(choice)] = execute_fn


def register_executor(kind: str, execute_fn: ExecuteFn) -> None:
    _EXECUTORS[str(kind)] = execute_fn


def register_agenda_action(kind: str, fn: AgendaFn) -> None:
    AGENDA_ACTIONS[str(kind)] = fn


def clear_choices() -> None:
    """For tests: forget every registered choice, executor and agenda action."""
    _CHOICES.clear()
    _EXECUTORS.clear()
    AGENDA_ACTIONS.clear()


def _declared_seats(conn: sqlite3.Connection, actor_id: int) -> list[tuple[int, str]]:
    """(organisation id, kind) of each active seat whose kind the package declares in orgs.json."""
    out = []
    for s in seats_of(conn, actor_id):
        if s["status"] != "active":
            continue
        org = int(s["org_actor_id"])
        if not kind_rules(conn, org):
            continue
        out.append((org, str(conn.execute("SELECT org_kind FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()[0])))
    return out


def _reason(conn: sqlite3.Connection, actor_id: int, day: int) -> bool:
    """A reason to leave the quiet routine: one of his organisations' choices passes today's weekly roll."""
    if not _CHOICES:
        return False
    for org, kind in _declared_seats(conn, actor_id):
        for choice, fn in _CHOICES.get(kind, {}).items():
            if org_motives.should_choose(conn, actor_id, day, choice) and fn(conn, int(actor_id), org, int(day)):
                return True  # the roll passed and there is something he could actually do
    return False


register_reason_check(_reason)


def _candidate(provider_key: str, org: int, offer: dict, choice: str, extra_key: str = "") -> DecisionCandidate:
    kind = str(offer.get("kind") or choice)
    target = offer.get("target_actor_id")
    return DecisionCandidate(
        key=f"org:{kind}:{org}:{target or 0}:{extra_key}:{json.dumps(offer.get('payload') or {}, sort_keys=True, default=str)}",
        provider_key=provider_key, action_kind=kind, utility=float(offer["utility"]), rationale=str(offer.get("rationale") or kind),
        execution_kind="org_action", target_actor_id=None if target is None else int(target), payload=dict(offer.get("payload") or {}),
        information_basis={"kind": "own_organisation_state", "org_actor_id": org}, tags=("org", choice),
        estimated_cost=float(offer.get("cost") or 0.0), risk=float(offer.get("risk") or 0.0),
    )


def org_provider(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    """Candidates for a seated man; [] for anyone else."""
    if not is_living(conn, actor_id):
        return []
    seats = _declared_seats(conn, actor_id)
    if not seats:
        return []
    out: list[DecisionCandidate] = []
    for org, kind in seats:
        for choice, fn in sorted(_CHOICES.get(kind, {}).items()):
            if not org_motives.should_choose(conn, actor_id, day, choice):
                continue
            for offer in fn(conn, int(actor_id), org, int(day)):
                out.append(_candidate("org", org, offer, choice))
    if AGENDA_ACTIONS:
        for item in conn.execute("SELECT * FROM org_agenda WHERE actor_id=? AND status='open' AND due_day<=? ORDER BY id",
                                 (int(actor_id), int(day))).fetchall():
            fn = AGENDA_ACTIONS.get(str(item["kind"]))
            if fn is None:
                continue
            for offer in fn(conn, int(actor_id), item, int(day)):
                payload = dict(offer.get("payload") or {})
                payload.setdefault("agenda_id", int(item["id"]))
                offer = {**offer, "payload": payload}
                out.append(_candidate("org", seats[0][0], offer, str(item["kind"]), f"agenda{int(item['id'])}"))
    return out


register_provider("org", org_provider)


def execute(conn: sqlite3.Connection, actor_id: int, kind: str, payload: dict, day: int) -> dict:
    """Carry out a chosen action by its registered executor. Returns {"summary": ...}."""
    fn = _EXECUTORS.get(str(kind))
    if fn is None:
        return {"summary": f"Nothing is registered to carry out {kind}.", "blocked": True}
    return fn(conn, int(actor_id), str(kind), dict(payload or {}), int(day))
