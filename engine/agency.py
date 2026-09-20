from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from .simulation import current_day


@dataclass(frozen=True)
class AgencyAssessment:
    handoff_type: str  # none|open|hard
    reason: str
    richness_score: float
    can_auto_continue: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _new_ids(before: list[dict[str, Any]], after: list[dict[str, Any]], key: str = "id") -> set[int]:
    old = {int(x[key]) for x in before if x.get(key) is not None}
    return {int(x[key]) for x in after if x.get(key) is not None} - old


def assess_handoff(
    pre_scene: dict[str, Any],
    post_scene: dict[str, Any],
    action_result: dict[str, Any],
) -> AgencyAssessment:
    """Determine whether the prose should naturally pause for player agency.

    This is not a 'does an NPC ask the player something?' test. Open handoffs exist for
    agency-rich situations where the player may reasonably want to choose a direction even
    though continuing the established plan would also be plausible.
    """
    cues = post_scene.get("attention_cues") or []
    decision_cues = [c for c in cues if c.get("cue_type") in {"decision", "warning"} and int(c.get("salience") or 0) >= 3]
    pending = post_scene.get("pending_player_interactions") or []
    new_pending = _new_ids(pre_scene.get("pending_player_interactions") or [], pending)

    if action_result.get("status") in {"needs_interpretation", "invalid", "failed"}:
        return AgencyAssessment("hard", "The player's intended action cannot proceed without clarification or a new choice.", 100.0, False)
    if decision_cues:
        return AgencyAssessment("hard", "Established competence reached a meaningful fork that the engine must not choose for the player.", 96.0, False)
    if new_pending:
        return AgencyAssessment("hard", "A new unresolved interaction materially requires the player's response.", 92.0, False)

    score = 0.0
    reasons: list[str] = []
    action_type = str(action_result.get("action_type") or "")
    before_loc = (pre_scene.get("location") or {}).get("id")
    after_loc = (post_scene.get("location") or {}).get("id")
    if before_loc != after_loc and after_loc is not None:
        score += 48
        reasons.append("arrival in a new place")
    if action_type in {"observe", "speak", "investigate"}:
        score += 24
        reasons.append("the player deliberately opened an exploratory/social situation")
    present = post_scene.get("present_actors") or []
    if present:
        score += min(28, 6 + len(present) * 4)
        reasons.append("other people are presently available to engage with")
    new_events = _new_ids(pre_scene.get("known_events") or [], post_scene.get("known_events") or [])
    if new_events:
        score += min(28, 8 + len(new_events) * 5)
        reasons.append("new consequences have become known")
    new_rumours = _new_ids(pre_scene.get("known_rumours") or [], post_scene.get("known_rumours") or [])
    if new_rumours:
        score += min(16, 4 + len(new_rumours) * 3)
        reasons.append("new information creates optional avenues of interest")
    if cues:
        score += min(18, max(int(c.get("salience") or 0) for c in cues) * 3)
        reasons.append("something is naturally salient to the character")
    if action_type == "travel":
        score += 18
        reasons.append("arrival is a natural opportunity to choose what matters next")

    score = min(100.0, score)
    if score >= 40:
        return AgencyAssessment("open", "; ".join(reasons) or "The situation is open enough for meaningful player initiative.", score, True)

    return AgencyAssessment(
        "none",
        "No unresolved meaningful choice or sufficiently rich intervention opportunity has appeared yet.",
        score,
        True,
    )


def build_segment_outline(action_result: dict[str, Any], pre_scene: dict[str, Any], post_scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe multiple fictional beats that may be narrated in one player-facing section.

    The outline lets a phone-local model make several smaller generations later without
    exposing those technical boundaries as repeated 'continue' prompts.
    """
    kind = str(action_result.get("action_type") or "scene")
    duration = int(action_result.get("duration_days") or 0)
    segments: list[dict[str, Any]] = []
    if kind == "travel" and duration > 0:
        segments.append({"kind": "travel", "beat": "departure and settling into the journey", "weight": 0.2})
        if duration > 1:
            segments.append({"kind": "travel", "beat": "the journey's ordinary passage, notable consequences, and lived texture", "weight": 0.5})
        segments.append({"kind": "arrival", "beat": "arrival and the immediate state of the destination", "weight": 0.3})
    elif kind == "wait" and duration > 0:
        segments.append({"kind": "downtime", "beat": "ordinary passage of time and character routine", "weight": 0.45})
        if duration > 1:
            segments.append({"kind": "aftermath", "beat": "only consequences or information that actually became accessible", "weight": 0.35})
        segments.append({"kind": "scene", "beat": "the present moment after the elapsed time", "weight": 0.2})
    elif kind == "speak":
        segments.append({"kind": "conversation", "beat": "the resolved social exchange, grounded in persisted outcomes", "weight": 0.75})
        segments.append({"kind": "aftermath", "beat": "the immediate social atmosphere after the exchange", "weight": 0.25})
    else:
        segments.append({"kind": "scene", "beat": "the resolved action and the living situation around it", "weight": 1.0})
    return segments


def persist_checkpoint(
    conn: sqlite3.Connection,
    turn_id: int,
    assessment: AgencyAssessment,
    *,
    segment_id: int | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO agency_checkpoints(turn_id,segment_id,day,checkpoint_type,reason,richness_score,can_auto_continue)
           VALUES (?,?,?,?,?,?,?)""",
        (
            turn_id, segment_id, current_day(conn), assessment.handoff_type, assessment.reason,
            assessment.richness_score, 1 if assessment.can_auto_continue else 0,
        ),
    )
    return int(cur.lastrowid)


def request_interrupt(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE runtime_flags SET value='1',updated_at=CURRENT_TIMESTAMP WHERE key='interrupt_requested'")


def consume_interrupt(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM runtime_flags WHERE key='interrupt_requested'").fetchone()
    if not row or str(row[0]) != "1":
        return False
    conn.execute("UPDATE runtime_flags SET value='0',updated_at=CURRENT_TIMESTAMP WHERE key='interrupt_requested'")
    return True
