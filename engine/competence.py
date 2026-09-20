from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from .simulation import SimEvent, current_day, log_event


@dataclass(frozen=True)
class CompetenceOutcome:
    intention_id: int
    outcome: str
    summary: str
    event_id: int | None = None
    cue_id: int | None = None
    possession_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def add_possession(
    conn: sqlite3.Connection,
    holder_actor_id: int,
    name: str,
    *,
    item_type: str = "item",
    quantity: float = 1,
    legal_owner_actor_id: int | None = None,
    notes: str = "",
) -> int:
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO possessions(holder_actor_id,legal_owner_actor_id,name,item_type,quantity,status,acquired_day,notes)
           VALUES (?,?,?,?,?,'held',?,?)""",
        (holder_actor_id, legal_owner_actor_id, name, item_type, quantity, day, notes),
    )
    return int(cur.lastrowid)


def add_intention(
    conn: sqlite3.Connection,
    actor_id: int,
    description: str,
    *,
    intention_kind: str = "follow_through",
    target_actor_id: int | None = None,
    target_location_id: int | None = None,
    possession_id: int | None = None,
    due_day: int | None = None,
    trigger_kind: str = "manual",
    auto_policy: str = "routine",
    source_kind: str | None = None,
    source_id: int | None = None,
    condition: dict[str, Any] | None = None,
    notes: str = "",
) -> int:
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO character_intentions(
               actor_id,intention_kind,description,target_actor_id,target_location_id,possession_id,due_day,
               trigger_kind,auto_policy,status,source_kind,source_id,condition_json,created_day,updated_day,notes
           ) VALUES (?,?,?,?,?,?,?,?,?,'active',?,?,?,?,?,?)""",
        (
            actor_id, intention_kind, description, target_actor_id, target_location_id, possession_id, due_day,
            trigger_kind, auto_policy, source_kind, source_id,
            json.dumps(condition or {}, ensure_ascii=False), day, day, notes,
        ),
    )
    return int(cur.lastrowid)


def add_obligation(
    conn: sqlite3.Connection,
    actor_id: int,
    description: str,
    *,
    counterparty_actor_id: int | None = None,
    due_day: int | None = None,
    target_actor_id: int | None = None,
    target_location_id: int | None = None,
    importance: int = 2,
    intention_id: int | None = None,
    source_kind: str | None = None,
    source_id: int | None = None,
    notes: str = "",
) -> int:
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO obligations(
               actor_id,counterparty_actor_id,description,due_day,target_actor_id,target_location_id,
               importance,status,intention_id,source_kind,source_id,created_day,updated_day,notes
           ) VALUES (?,?,?,?,?,?,?,'active',?,?,?,?,?,?)""",
        (
            actor_id, counterparty_actor_id, description, due_day, target_actor_id, target_location_id,
            max(1, min(5, int(importance))), intention_id, source_kind, source_id, day, day, notes,
        ),
    )
    return int(cur.lastrowid)


def suspend_intention(conn: sqlite3.Connection, intention_id: int, note: str = "") -> None:
    day = current_day(conn)
    conn.execute(
        "UPDATE character_intentions SET status='suspended',updated_day=?,notes=CASE WHEN ?='' THEN notes ELSE ? END WHERE id=?",
        (day, note, note, intention_id),
    )


def resume_intention(conn: sqlite3.Connection, intention_id: int) -> None:
    day = current_day(conn)
    conn.execute("UPDATE character_intentions SET status='active',updated_day=? WHERE id=?", (day, intention_id))


def _cue(
    conn: sqlite3.Connection,
    actor_id: int,
    cue_type: str,
    text: str,
    *,
    salience: int = 2,
    related_kind: str | None = None,
    related_id: int | None = None,
) -> int:
    day = current_day(conn)
    if related_kind and related_id is not None:
        existing = conn.execute(
            """SELECT id,status,text,day FROM attention_cues
               WHERE actor_id=? AND related_kind=? AND related_id=? AND status IN ('pending','shown')
               ORDER BY id DESC LIMIT 1""",
            (actor_id, related_kind, related_id),
        ).fetchone()
        if existing:
            if existing["status"] == "pending":
                return int(existing["id"])
            if existing["status"] == "shown" and str(existing["text"]) == text:
                return int(existing["id"])
    cur = conn.execute(
        """INSERT INTO attention_cues(actor_id,day,cue_type,text,salience,related_kind,related_id)
           VALUES (?,?,?,?,?,?,?)""",
        (actor_id, day, cue_type, text, max(1, min(5, int(salience))), related_kind, related_id),
    )
    return int(cur.lastrowid)


def _relationship_changed_meaningfully(conn: sqlite3.Connection, actor_id: int, target_actor_id: int | None, created_day: int) -> bool:
    if target_actor_id is None:
        return False
    row = conn.execute(
        """SELECT stance,trust,updated_day FROM relationships
           WHERE actor_a_id=? AND actor_b_id=?
           ORDER BY id LIMIT 1""",
        (actor_id, target_actor_id),
    ).fetchone()
    if not row:
        return False
    if int(row["updated_day"]) <= int(created_day):
        return False
    return float(row["stance"]) <= -25 or float(row["trust"]) <= -35


def _trigger_met(
    row: sqlite3.Row,
    *,
    day: int,
    current_location_id: int | None,
    present_actor_ids: set[int],
    trigger: str | None,
) -> bool:
    kind = str(row["trigger_kind"])
    if kind == "manual":
        return False
    if kind == "due_day":
        return row["due_day"] is not None and day >= int(row["due_day"])
    if kind == "actor_present":
        return row["target_actor_id"] is not None and int(row["target_actor_id"]) in present_actor_ids
    if kind == "location_present":
        return row["target_location_id"] is not None and current_location_id == int(row["target_location_id"])
    if kind == "on_arrival":
        return trigger == "on_arrival" and (row["target_location_id"] is None or current_location_id == int(row["target_location_id"]))
    if kind == "on_departure":
        return trigger == "on_departure"
    return False


def _fulfill_delivery(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> CompetenceOutcome:
    actor_id = int(row["actor_id"])
    target_id = int(row["target_actor_id"])
    possession_id = int(row["possession_id"])
    poss = conn.execute("SELECT * FROM possessions WHERE id=?", (possession_id,)).fetchone()
    target = conn.execute("SELECT name FROM actors WHERE id=?", (target_id,)).fetchone()
    if not poss or poss["status"] != "held" or poss["holder_actor_id"] != actor_id:
        conn.execute("UPDATE character_intentions SET status='failed',updated_day=? WHERE id=?", (day, row["id"]))
        cue_id = _cue(
            conn, actor_id, "warning",
            f"You intended to {row['description']}, but the required item is no longer in your possession.",
            salience=4, related_kind="intention", related_id=int(row["id"]),
        )
        return CompetenceOutcome(int(row["id"]), "failed", "Required possession unavailable.", cue_id=cue_id, possession_id=possession_id)

    conn.execute(
        "UPDATE possessions SET holder_actor_id=?,status='held' WHERE id=?",
        (target_id, possession_id),
    )
    conn.execute(
        "UPDATE character_intentions SET status='fulfilled',fulfilled_day=?,updated_day=? WHERE id=?",
        (day, day, row["id"]),
    )
    conn.execute(
        "UPDATE obligations SET status='fulfilled',updated_day=? WHERE intention_id=? AND status='active'",
        (day, row["id"]),
    )
    target_name = str(target[0]) if target else "the intended recipient"
    summary = f"You automatically follow through on your established intention and give {poss['name']} to {target_name}."
    event_id = log_event(conn, SimEvent(
        day=day,
        event_type="competence:routine_fulfillment",
        title="Routine intention fulfilled",
        summary=summary,
        severity=1,
        source_actor_id=actor_id,
        target_actor_ids=(target_id,),
        visibility="private",
        rumorability=0.0,
    ))
    cue_id = _cue(
        conn, actor_id, "automatic", summary,
        salience=2, related_kind="intention", related_id=int(row["id"]),
    )
    return CompetenceOutcome(int(row["id"]), "fulfilled", summary, event_id=event_id, cue_id=cue_id, possession_id=possession_id)


def _fulfill_generic(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> CompetenceOutcome:
    actor_id = int(row["actor_id"])
    conn.execute(
        "UPDATE character_intentions SET status='fulfilled',fulfilled_day=?,updated_day=? WHERE id=?",
        (day, day, row["id"]),
    )
    conn.execute("UPDATE obligations SET status='fulfilled',updated_day=? WHERE intention_id=? AND status='active'", (day, row["id"]))
    summary = f"You automatically follow through on your established intention: {row['description']}"
    cue_id = _cue(conn, actor_id, "automatic", summary, salience=2, related_kind="intention", related_id=int(row["id"]))
    return CompetenceOutcome(int(row["id"]), "fulfilled", summary, cue_id=cue_id)


def process_competence(
    conn: sqlite3.Connection,
    actor_id: int,
    *,
    current_location_id: int | None = None,
    present_actor_ids: set[int] | None = None,
    trigger: str | None = None,
    reminder_window_days: int = 3,
) -> list[CompetenceOutcome]:
    """Apply routine follow-through while handing meaningful forks back to the player.

    This layer is deliberately conservative: it only auto-performs an intention whose
    trigger is met and whose auto policy says routine/ask_if_changed. If circumstances
    changed in a way the engine can recognize, it creates a decision cue instead.
    """
    day = current_day(conn)
    present_actor_ids = set(present_actor_ids or set())
    outcomes: list[CompetenceOutcome] = []

    # Proactive reminders for obligations: journals are references, not memory substitutes.
    for ob in conn.execute(
        """SELECT * FROM obligations WHERE actor_id=? AND status='active' AND due_day IS NOT NULL
           ORDER BY due_day,id""",
        (actor_id,),
    ).fetchall():
        days_left = int(ob["due_day"]) - day
        if 0 <= days_left <= reminder_window_days:
            when = "today" if days_left == 0 else ("tomorrow" if days_left == 1 else f"in {days_left} days")
            _cue(
                conn, actor_id, "reminder", f"{ob['description']} is due {when}.",
                salience=max(2, int(ob["importance"])), related_kind="obligation", related_id=int(ob["id"]),
            )
        elif days_left < 0:
            _cue(
                conn, actor_id, "warning", f"An obligation is overdue: {ob['description']}",
                salience=max(3, int(ob["importance"])), related_kind="obligation", related_id=int(ob["id"]),
            )

    rows = conn.execute(
        """SELECT * FROM character_intentions WHERE actor_id=? AND status='active' ORDER BY id""",
        (actor_id,),
    ).fetchall()
    for row in rows:
        if not _trigger_met(row, day=day, current_location_id=current_location_id, present_actor_ids=present_actor_ids, trigger=trigger):
            # Location/recipient salience can still generate a reminder before exact fulfillment.
            if row["target_location_id"] is not None and current_location_id == int(row["target_location_id"]) and row["target_actor_id"] is not None and int(row["target_actor_id"]) not in present_actor_ids:
                target = conn.execute("SELECT name FROM actors WHERE id=?", (row["target_actor_id"],)).fetchone()
                if target:
                    _cue(
                        conn, actor_id, "reminder",
                        f"You remember your intention to {row['description']}; {target[0]} is associated with this place but is not presently here.",
                        salience=2, related_kind="intention", related_id=int(row["id"]),
                    )
            continue

        policy = str(row["auto_policy"])
        if policy in {"manual", "remind"}:
            cue_id = _cue(
                conn, actor_id, "decision", f"You remember: {row['description']}",
                salience=3, related_kind="intention", related_id=int(row["id"]),
            )
            outcomes.append(CompetenceOutcome(int(row["id"]), "needs_player", str(row["description"]), cue_id=cue_id, possession_id=row["possession_id"]))
            continue

        changed = _relationship_changed_meaningfully(conn, actor_id, row["target_actor_id"], int(row["created_day"]))
        if policy == "ask_if_changed" and changed:
            conn.execute("UPDATE character_intentions SET status='blocked',updated_day=? WHERE id=?", (day, row["id"]))
            cue_id = _cue(
                conn, actor_id, "decision",
                f"You had intended to {row['description']}, but circumstances with the other person have changed enough that doing so is now a meaningful choice.",
                salience=4, related_kind="intention", related_id=int(row["id"]),
            )
            outcomes.append(CompetenceOutcome(int(row["id"]), "needs_player", str(row["description"]), cue_id=cue_id, possession_id=row["possession_id"]))
            continue

        if row["intention_kind"] == "deliver_possession" and row["target_actor_id"] is not None and row["possession_id"] is not None:
            outcomes.append(_fulfill_delivery(conn, row, day))
        else:
            outcomes.append(_fulfill_generic(conn, row, day))

    return outcomes


def pending_attention(conn: sqlite3.Connection, actor_id: int, *, mark_shown: bool = False, limit: int = 12) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT * FROM attention_cues WHERE actor_id=? AND status='pending'
           ORDER BY salience DESC,day,id LIMIT ?""",
        (actor_id, limit),
    ).fetchall()
    items = [dict(r) for r in rows]
    if mark_shown and items:
        conn.executemany("UPDATE attention_cues SET status='shown' WHERE id=?", [(i["id"],) for i in items])
    return items


def active_matters(conn: sqlite3.Connection, actor_id: int) -> dict[str, list[dict[str, Any]]]:
    intentions = [dict(r) for r in conn.execute(
        """SELECT ci.*,a.name target_actor_name,l.name target_location_name,p.name possession_name
           FROM character_intentions ci
           LEFT JOIN actors a ON a.id=ci.target_actor_id
           LEFT JOIN locations l ON l.id=ci.target_location_id
           LEFT JOIN possessions p ON p.id=ci.possession_id
           WHERE ci.actor_id=? AND ci.status IN ('active','blocked','suspended')
           ORDER BY CASE WHEN ci.due_day IS NULL THEN 1 ELSE 0 END,ci.due_day,ci.id""",
        (actor_id,),
    ).fetchall()]
    obligations = [dict(r) for r in conn.execute(
        """SELECT o.*,a.name counterparty_name,t.name target_actor_name,l.name target_location_name
           FROM obligations o LEFT JOIN actors a ON a.id=o.counterparty_actor_id
           LEFT JOIN actors t ON t.id=o.target_actor_id LEFT JOIN locations l ON l.id=o.target_location_id
           WHERE o.actor_id=? AND o.status='active'
           ORDER BY CASE WHEN o.due_day IS NULL THEN 1 ELSE 0 END,o.due_day,o.importance DESC,o.id""",
        (actor_id,),
    ).fetchall()]
    return {"intentions": intentions, "obligations": obligations}
