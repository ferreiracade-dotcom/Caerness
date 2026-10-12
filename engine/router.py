from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from .local_model import estimate_tokens, runtime_config
from .simulation import current_day


@dataclass(frozen=True)
class RouteAssessment:
    task_type: str
    reasoning_score: float
    narrative_score: float
    context_tokens_estimate: int
    hardware_score: float
    recommendation: str
    reasons: tuple[str, ...]
    external_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, float(v)))


def _scene_features(payload: dict[str, Any]) -> dict[str, float]:
    # Accept either a scene packet, narration payload, or wrapper.
    scene = payload.get("scene_after") or payload.get("scene") or payload.get("narration_envelope", {}).get("scene_after") or (payload.get("context",{}).get("scene") if payload.get("protocol")=="world_plan_v1" else None) or payload
    present = scene.get("present_actors") or []
    pending = scene.get("pending_player_interactions") or []
    events = scene.get("known_events") or []
    rumours = scene.get("known_rumours") or []
    cues = scene.get("attention_cues") or []
    max_stakes = max([float(i.get("stakes") or 0) for i in pending] or [0.0])
    max_event = max([float(e.get("severity") or 0) for e in events[-6:]] or [0.0])
    cue_salience = max([float(c.get("salience") or 0) for c in cues] or [0.0])
    return {
        "present": len(present),
        "pending": len(pending),
        "max_stakes": max_stakes,
        "max_event": max_event,
        "rumours": len(rumours),
        "cue_salience": cue_salience,
    }


def _decision_features(payload: dict[str, Any]) -> dict[str, float]:
    ctx = payload.get("actor_context") or payload
    goals = ctx.get("goals") or []
    pressures = ctx.get("pressures") or []
    relationships = ctx.get("relationships") or []
    constraints = ctx.get("constraints") or []
    knowledge = ctx.get("knowledge") or []
    max_pressure_ratio = 0.0
    for p in pressures:
        threshold = float(p.get("threshold") or 1.0)
        max_pressure_ratio = max(max_pressure_ratio, float(p.get("intensity") or 0.0) / max(0.1, threshold))
    conflicting = 0
    if len(goals) >= 2:
        priorities = sorted([int(g.get("priority") or 0) for g in goals if g.get("status", "active") == "active"], reverse=True)
        if len(priorities) >= 2 and priorities[1] >= 50:
            conflicting = 1
    return {
        "goals": len(goals),
        "pressures": len(pressures),
        "relationships": len(relationships),
        "constraints": len(constraints),
        "knowledge": len(knowledge),
        "pressure_ratio": max_pressure_ratio,
        "conflicting_goals": conflicting,
    }


def assess_model_task(
    conn: sqlite3.Connection,
    task_type: str,
    payload: dict[str, Any],
    *,
    target_kind: str | None = None,
    target_id: int | None = None,
    persist: bool = True,
) -> RouteAssessment:
    if task_type not in {"action_interpretation", "npc_decision", "narration"}:
        raise ValueError("Unsupported route task type")
    cfg = runtime_config(conn)
    tokens = estimate_tokens(payload)
    normal_limit = int(cfg["local_max_context_tokens"])
    heavy_limit = int(cfg["local_heavy_context_tokens"])

    reasons: list[str] = []
    reasoning = 10.0
    narrative = 5.0

    if task_type in {"narration", "action_interpretation"}:
        f = _scene_features(payload)
        reasoning += min(35, f["present"] * 5.5)
        reasoning += min(20, f["pending"] * 6 + f["max_stakes"] * 2)
        reasoning += min(12, f["cue_salience"] * 2.5)
        if f["present"] >= 4:
            reasons.append(f"{int(f['present'])} significant/present actors increase scene-state complexity")
        if f["pending"]:
            reasons.append("unresolved social or contractual interactions are active")
        if task_type == "narration":
            narrative += min(32, f["present"] * 6)
            narrative += min(18, f["max_event"] * 3.5)
            narrative += min(12, f["rumours"] * 1.5)
            if f["max_event"] >= 4:
                reasons.append("recent high-severity consequences make this narratively important")
        else:
            raw = str(payload.get("raw_player_input") or payload.get("request") or "")
            if len(raw) > 240:
                reasoning += 12
                reasons.append("player intent is unusually compound")
            if any(w in raw.lower() for w in ("bargain", "negotiate", "deceive", "threaten", "convince", "promise", "betray")):
                reasoning += 14
                reasons.append("player intent contains consequential social interpretation")
    else:
        f = _decision_features(payload)
        reasoning += min(24, f["goals"] * 4)
        reasoning += min(20, f["pressures"] * 4)
        reasoning += min(20, f["relationships"] * 2.5)
        reasoning += min(10, f["constraints"] * 2)
        reasoning += min(10, f["knowledge"] * 0.7)
        reasoning += min(18, f["pressure_ratio"] * 12)
        reasoning += 10 * f["conflicting_goals"]
        if f["relationships"] >= 5:
            reasons.append("decision spans a dense relationship network")
        if f["pressure_ratio"] >= 0.8:
            reasons.append("actor is under near-threshold pressure")
        if f["conflicting_goals"]:
            reasons.append("multiple high-priority goals compete")

    # Context/memory burden on a 12 GB phone is a separate axis from reasoning quality.
    if tokens <= normal_limit:
        hardware = 10 + 30 * (tokens / max(1, normal_limit))
    elif tokens <= heavy_limit:
        hardware = 45 + 35 * ((tokens - normal_limit) / max(1, heavy_limit - normal_limit))
        reasons.append("context is above the comfortable local profile")
    else:
        hardware = min(100, 82 + 18 * ((tokens - heavy_limit) / max(1, heavy_limit)))
        reasons.append("context exceeds the configured heavy local-context ceiling")

    reasoning = _clamp(reasoning)
    narrative = _clamp(narrative)
    hardware = _clamp(hardware)

    sensitivity = str(cfg["referral_sensitivity"])
    quality_threshold = {"rare": 88, "balanced": 72, "quality_first": 58}[sensitivity]
    strong_threshold = {"rare": 96, "balanced": 88, "quality_first": 80}[sensitivity]
    quality_signal = max(reasoning if int(cfg["referral_for_reasoning"]) else 0, narrative if int(cfg["referral_for_quality"]) else 0)
    hardware_signal = hardware if int(cfg["referral_for_hardware"]) else 0
    signal = max(quality_signal, hardware_signal)

    external_reason: str | None = None
    if signal >= strong_threshold or tokens > int(heavy_limit * 1.25):
        recommendation = "external_strongly_recommended"
    elif signal >= quality_threshold or tokens > heavy_limit:
        recommendation = "external_recommended"
    elif tokens > normal_limit or hardware >= 55:
        recommendation = "local_heavy"
    elif task_type == "npc_decision" and reasoning < 32:
        recommendation = "rules"
    else:
        recommendation = "local"

    if recommendation.startswith("external"):
        if hardware_signal >= quality_signal and hardware_signal >= quality_threshold:
            external_reason = "hardware"
        elif reasoning >= narrative and int(cfg["referral_for_reasoning"]):
            external_reason = "reasoning"
        else:
            external_reason = "quality"
        if external_reason == "hardware":
            reasons.append("external AI would reduce phone memory/thermal load")
        elif external_reason == "reasoning":
            reasons.append("a stronger model is likely to improve consequential reasoning")
        else:
            reasons.append("a stronger model is likely to improve scene quality")

    if not reasons:
        reasons.append("task fits the configured phone-local profile")

    assessment = RouteAssessment(
        task_type=task_type,
        reasoning_score=round(reasoning, 1),
        narrative_score=round(narrative, 1),
        context_tokens_estimate=tokens,
        hardware_score=round(hardware, 1),
        recommendation=recommendation,
        reasons=tuple(dict.fromkeys(reasons)),
        external_reason=external_reason,
    )
    if persist:
        conn.execute(
            """INSERT INTO model_route_assessments(
                   day,task_type,target_kind,target_id,reasoning_score,narrative_score,
                   context_tokens_estimate,hardware_score,recommendation,reasons_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                current_day(conn), task_type, target_kind, target_id,
                assessment.reasoning_score, assessment.narrative_score,
                assessment.context_tokens_estimate, assessment.hardware_score,
                assessment.recommendation, json.dumps(list(assessment.reasons), ensure_ascii=False),
            ),
        )
    return assessment


def route_label(assessment: RouteAssessment) -> str:
    labels = {
        "rules": "Rules engine is sufficient",
        "local": "Local model",
        "local_heavy": "Local model — heavy",
        "external_recommended": "ChatGPT/Claude recommended",
        "external_strongly_recommended": "ChatGPT/Claude strongly recommended",
    }
    return labels[assessment.recommendation]
