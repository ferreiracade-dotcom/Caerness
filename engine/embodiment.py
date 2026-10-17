from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from .simulation import current_day


DEFAULT_EXPRESSION_POLICY = {
    "autonomous_expression_min_confidence": 0.80,
    "ask_below_confidence": 0.70,
    "max_autonomous_stakes": 2,
    "allow_low_stakes_expression": True,
    "major_commitments_require_player": True,
    "avoid_caricature": True,
    "prefer_small_expression_over_irreversible_action": True,
}

MAJOR_COMMITMENTS = {
    "oath",
    "marriage",
    "betrayal",
    "war_declaration",
    "execution",
    "permanent_allegiance",
    "major_confession",
    "life_changing_secret",
    "irreversible_contract",
}


@dataclass(frozen=True)
class AutonomyAssessment:
    actor_id: int
    result: str
    confidence: float
    commitment_risk: str
    reason: str
    expression_kind: str
    stakes: int
    irreversible: bool
    commitment_kind: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def ensure_embodiment_profile(conn: sqlite3.Connection, actor_id: int, *, source_kind: str = "campaign") -> None:
    actor = conn.execute("SELECT actor_type FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not actor:
        raise ValueError(f"Unknown actor #{actor_id}")
    if str(actor["actor_type"]) != "character":
        raise ValueError("Embodiment profiles are for character actors")
    day = current_day(conn)
    conn.execute(
        """INSERT OR IGNORE INTO character_embodiment(
               actor_id,voice_json,temperament_json,values_json,habits_json,social_json,
               relationship_style_json,expression_policy_json,current_state_json,development_json,
               source_kind,updated_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            actor_id,
            _dumps({"register": "natural", "verbosity": "contextual", "directness": "contextual"}),
            _dumps({}),
            _dumps({}),
            _dumps({}),
            _dumps({"formality": "contextual", "social_confidence": "unknown"}),
            _dumps({}),
            _dumps(DEFAULT_EXPRESSION_POLICY),
            _dumps({}),
            _dumps({"behavioral_inertia": True, "change_requires_evidence": True}),
            source_kind,
            day,
        ),
    )


def get_embodiment_profile(conn: sqlite3.Connection, actor_id: int, *, include_recent: int = 8) -> dict[str, Any]:
    ensure_embodiment_profile(conn, actor_id)
    row = conn.execute("SELECT * FROM character_embodiment WHERE actor_id=?", (actor_id,)).fetchone()
    assert row is not None
    actor = conn.execute("SELECT id,name,subtype,status FROM actors WHERE id=?", (actor_id,)).fetchone()
    result = {
        "actor_id": actor_id,
        "actor_name": actor["name"] if actor else None,
        "subtype": actor["subtype"] if actor else None,
        "voice": _loads(row["voice_json"], {}),
        "temperament": _loads(row["temperament_json"], {}),
        "values": _loads(row["values_json"], {}),
        "habits": _loads(row["habits_json"], {}),
        "social": _loads(row["social_json"], {}),
        "relationship_style": _loads(row["relationship_style_json"], {}),
        "expression_policy": _loads(row["expression_policy_json"], dict(DEFAULT_EXPRESSION_POLICY)),
        "current_state": _loads(row["current_state_json"], {}),
        "development": _loads(row["development_json"], {}),
        "source_kind": row["source_kind"],
        "updated_day": int(row["updated_day"]),
        "notes": row["notes"],
    }
    if include_recent > 0:
        recent = conn.execute(
            """SELECT id,day,expression_kind,summary,confidence,autonomy_result,commitment_risk,related_actor_id
               FROM embodiment_expressions WHERE actor_id=? ORDER BY day DESC,id DESC LIMIT ?""",
            (actor_id, include_recent),
        ).fetchall()
        result["recent_expressions"] = [dict(r) for r in reversed(recent)]
    return result


def update_embodiment_profile(
    conn: sqlite3.Connection,
    actor_id: int,
    patch: dict[str, Any],
    *,
    source_kind: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    ensure_embodiment_profile(conn, actor_id, source_kind=source_kind or "campaign")
    row = conn.execute("SELECT * FROM character_embodiment WHERE actor_id=?", (actor_id,)).fetchone()
    assert row is not None
    field_map = {
        "voice": "voice_json",
        "temperament": "temperament_json",
        "values": "values_json",
        "habits": "habits_json",
        "social": "social_json",
        "relationship_style": "relationship_style_json",
        "expression_policy": "expression_policy_json",
        "current_state": "current_state_json",
        "development": "development_json",
    }
    updates: dict[str, str] = {}
    for public, column in field_map.items():
        if public in patch:
            current = _loads(row[column], {})
            incoming = patch[public]
            if not isinstance(incoming, dict):
                raise ValueError(f"{public} must be a JSON object")
            updates[column] = _dumps(_deep_merge(current, incoming))
    if not updates and source_kind is None and notes is None:
        return get_embodiment_profile(conn, actor_id)
    day = current_day(conn)
    sets = [f"{col}=?" for col in updates]
    values: list[Any] = list(updates.values())
    if source_kind is not None:
        if source_kind not in {"campaign", "canon", "crystallization", "admin", "generated"}:
            raise ValueError("invalid source_kind")
        sets.append("source_kind=?")
        values.append(source_kind)
    if notes is not None:
        sets.append("notes=?")
        values.append(notes)
    sets.append("updated_day=?")
    values.append(day)
    values.append(actor_id)
    conn.execute(f"UPDATE character_embodiment SET {', '.join(sets)} WHERE actor_id=?", values)
    return get_embodiment_profile(conn, actor_id)


def stance_band(stance: float) -> str:
    return "warm" if stance >= 35 else "hostile" if stance <= -35 else "mixed_or_neutral"


def trust_band(trust: float) -> str:
    return "high" if trust >= 35 else "low" if trust <= -35 else "uncertain_or_moderate"


def _relationship_context(conn: sqlite3.Connection, actor_id: int, other_ids: list[int] | tuple[int, ...] | set[int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for other_id in other_ids:
        row = conn.execute(
            """SELECT r.*,a.name actor_a,b.name actor_b FROM relationships r
               JOIN actors a ON a.id=r.actor_a_id JOIN actors b ON b.id=r.actor_b_id
               WHERE r.actor_a_id=? AND r.actor_b_id=?
               ORDER BY r.id LIMIT 1""",
            (actor_id, int(other_id)),
        ).fetchone()
        if row:
            item = dict(row)
            # Player-facing/narrator embodiment should use coarse qualitative cues, not raw meters.
            trust = float(row["trust"])
            stance = float(row["stance"])
            item = {
                "other_actor_id": int(other_id),
                "other_name": item["actor_b"],
                "stance_band": stance_band(stance),
                "trust_band": trust_band(trust),
                "has_obligation": abs(float(row["obligation"])) > 0.01,
                "updated_day": int(row["updated_day"]),
            }
            out.append(item)
    return out


def build_embodiment_packet(
    conn: sqlite3.Connection,
    actor_id: int,
    *,
    present_actor_ids: list[int] | tuple[int, ...] | set[int] = (),
    request_text: str = "",
) -> dict[str, Any]:
    profile = get_embodiment_profile(conn, actor_id, include_recent=6)
    return {
        "profile": profile,
        "present_relationship_context": _relationship_context(conn, actor_id, present_actor_ids),
        "current_player_wording": request_text,
        "rendering_rules": [
            "Treat player wording as intent/content/tone unless the player explicitly marks exact dialogue.",
            "Render speech through the protagonist's established voice, culture, status, competence, relationship, and current state.",
            "Do not infer simplicity, bluntness, awkwardness, or eloquence merely from the player's typing style.",
            "The protagonist remains a character between direct commands; small consistent gestures or habitual expression may be inferred.",
            "Do not infer major irreversible commitments, betrayals, oaths, marriage choices, declarations of war, executions, permanent allegiances, or life-changing disclosures.",
            "Prefer small expressive behavior over consequential autonomous decisions.",
            "Established personality creates expectations, not caricature. Context and relationships can produce exceptions.",
            "Do not invent hidden self-knowledge or major internal commitments for the player character.",
        ],
    }


def assess_autonomous_expression(
    conn: sqlite3.Connection,
    actor_id: int,
    *,
    expression_kind: str,
    confidence: float,
    stakes: int = 1,
    irreversible: bool = False,
    commitment_kind: str | None = None,
) -> AutonomyAssessment:
    profile = get_embodiment_profile(conn, actor_id, include_recent=0)
    policy = dict(DEFAULT_EXPRESSION_POLICY)
    policy.update(profile.get("expression_policy") or {})
    confidence = max(0.0, min(1.0, float(confidence)))
    stakes = max(1, min(5, int(stakes)))
    commitment_kind = commitment_kind or None
    major = irreversible or commitment_kind in MAJOR_COMMITMENTS

    if major and bool(policy.get("major_commitments_require_player", True)):
        return AutonomyAssessment(
            actor_id, "block", confidence, "high",
            "Major or irreversible commitment requires explicit player agency.",
            expression_kind, stakes, irreversible, commitment_kind,
        )
    max_stakes = int(policy.get("max_autonomous_stakes", 2))
    allow_threshold = float(policy.get("autonomous_expression_min_confidence", 0.80))
    ask_threshold = float(policy.get("ask_below_confidence", 0.70))
    if stakes > max_stakes:
        return AutonomyAssessment(
            actor_id, "ask", confidence, "medium",
            "The behavior is consequential enough that player confirmation is safer.",
            expression_kind, stakes, irreversible, commitment_kind,
        )
    if confidence >= allow_threshold and bool(policy.get("allow_low_stakes_expression", True)):
        return AutonomyAssessment(
            actor_id, "allow", confidence, "low",
            "Low-stakes expression is strongly supported by the persistent character model.",
            expression_kind, stakes, irreversible, commitment_kind,
        )
    if confidence >= ask_threshold:
        return AutonomyAssessment(
            actor_id, "ask", confidence, "medium",
            "Character fit is plausible but not strong enough for autonomous expression.",
            expression_kind, stakes, irreversible, commitment_kind,
        )
    return AutonomyAssessment(
        actor_id, "block", confidence, "medium",
        "Character fit is too uncertain to infer behavior safely.",
        expression_kind, stakes, irreversible, commitment_kind,
    )


def record_expression(
    conn: sqlite3.Connection,
    actor_id: int,
    summary: str,
    *,
    expression_kind: str = "gesture",
    confidence: float = 0.85,
    stakes: int = 1,
    irreversible: bool = False,
    commitment_kind: str | None = None,
    related_actor_id: int | None = None,
    source_kind: str = "narration",
    source_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assessment = assess_autonomous_expression(
        conn, actor_id, expression_kind=expression_kind, confidence=confidence,
        stakes=stakes, irreversible=irreversible, commitment_kind=commitment_kind,
    )
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO embodiment_expressions(
               actor_id,day,expression_kind,summary,confidence,autonomy_result,commitment_risk,
               related_actor_id,source_kind,source_id,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            actor_id, day, expression_kind, summary, assessment.confidence, assessment.result,
            assessment.commitment_risk, related_actor_id, source_kind, source_id, _dumps(metadata or {}),
        ),
    )
    return {"expression_id": int(cur.lastrowid), "assessment": assessment.as_dict()}


def prepare_speech_mediation(
    conn: sqlite3.Connection,
    actor_id: int,
    raw_input: str,
    *,
    mode: str = "intent",
    audience_actor_id: int | None = None,
    intended_tone: str | None = None,
    social_objective: str | None = None,
    commitment_kind: str | None = None,
) -> dict[str, Any]:
    if mode not in {"intent", "guided", "exact"}:
        raise ValueError("mode must be intent, guided, or exact")
    profile = get_embodiment_profile(conn, actor_id, include_recent=4)
    if audience_actor_id is not None and not conn.execute("SELECT 1 FROM actors WHERE id=?", (audience_actor_id,)).fetchone():
        raise ValueError(f"Unknown audience actor #{audience_actor_id}")
    assessment = assess_autonomous_expression(
        conn, actor_id,
        expression_kind="speech",
        confidence=1.0 if mode == "exact" else 0.9,
        stakes=4 if commitment_kind in MAJOR_COMMITMENTS else 1,
        irreversible=commitment_kind in MAJOR_COMMITMENTS,
        commitment_kind=commitment_kind,
    )
    relation = _relationship_context(conn, actor_id, [audience_actor_id] if audience_actor_id else [])
    mediation = {
        "input_mode": mode,
        "preserve_exact_words": mode == "exact",
        "raw_input": raw_input,
        "intended_tone": intended_tone,
        "social_objective": social_objective,
        "voice": profile.get("voice", {}),
        "temperament": profile.get("temperament", {}),
        "social": profile.get("social", {}),
        "relationship_context": relation,
        "current_state": profile.get("current_state", {}),
        "rules": [
            "Exact mode preserves the player's words verbatim.",
            "Guided mode preserves specifically supplied phrases where practical while rendering the rest in character.",
            "Intent mode treats the player's text as meaning/objective rather than a transcript.",
            "Do not improve away established weaknesses or exaggerate strengths into caricature.",
            "Do not convert a non-committal intent into a major commitment.",
        ],
        "autonomy": assessment.as_dict(),
    }
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO speech_mediations(
               actor_id,day,audience_actor_id,input_mode,raw_input,intended_tone,social_objective,
               commitment_risk,mediation_json,status
           ) VALUES (?,?,?,?,?,?,?,?,?,'prepared')""",
        (
            actor_id, day, audience_actor_id, mode, raw_input, intended_tone, social_objective,
            assessment.commitment_risk, _dumps(mediation),
        ),
    )
    mediation["mediation_id"] = int(cur.lastrowid)
    return mediation


def recent_speech_mediations(conn: sqlite3.Connection, actor_id: int, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM speech_mediations WHERE actor_id=? ORDER BY day DESC,id DESC LIMIT ?",
        (actor_id, limit),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["mediation"] = _loads(item.pop("mediation_json"), {})
        out.append(item)
    return out
