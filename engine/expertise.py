from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from .simulation import current_day


DEFAULT_DOMAINS: dict[str, dict[str, Any]] = {
    "martial": {"name": "Martial practice", "description": "Personal martial execution, training, technique, and cultivation-aware combat reading."},
    "command": {"name": "Command", "description": "Military command, unit employment, logistics, reports, morale, and battlefield judgment."},
    "politics": {"name": "Politics", "description": "Court politics, institutions, factions, leverage, protocol, and political risk."},
    "administration": {"name": "Administration", "description": "Institutional management, delegation, procedure, finance, staffing, and execution capacity."},
    "commerce": {"name": "Commerce", "description": "Trade, credit, pricing, contracts, markets, logistics, and commercial risk."},
    "medicine": {"name": "Medicine", "description": "Ordinary medicine, diagnosis, treatment, recovery, and clinical judgment."},
    "vein_mending": {"name": "Vein-Mending", "description": "Cultivation-aware medicine involving the Vessel, Channels, Core, and serious cultivation injury."},
    "craft": {"name": "Craft", "description": "Professional making, workshop practice, materials, quality, production, and apprenticeship."},
    "architecture": {"name": "Architecture", "description": "Building design, construction, materials, site judgment, project constraints, and patronage."},
    "scholarship": {"name": "Scholarship", "description": "Research, texts, evidence, archives, argument, teaching, and academic institutions."},
    "social": {"name": "Social judgment", "description": "Etiquette, interpersonal reading, negotiation context, status signals, and conversational judgment."},
    "law": {"name": "Law", "description": "Legal procedure, contracts, jurisdiction, claims, inheritance, and institutional enforcement."},
    "art_culture": {"name": "Art and culture", "description": "Art, provenance, style, collecting, patronage, cultural reputation, and attribution."},
    "regional": {"name": "Regional knowledge", "description": "Local geography, institutions, customs, routes, people, and regional conditions."},
}


@dataclass(frozen=True)
class CompetenceBand:
    key: str
    label: str
    description: str
    interpretation_depth: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def competence_band(score: float) -> CompetenceBand:
    s = max(0.0, min(100.0, float(score)))
    if s < 15:
        return CompetenceBand("untrained", "Untrained", "Recognizes only obvious features and should rely heavily on others.", "surface")
    if s < 35:
        return CompetenceBand("novice", "Novice", "Has real introductory knowledge but limited judgment outside familiar situations.", "basic")
    if s < 55:
        return CompetenceBand("competent", "Competent", "Can perform ordinary professional work and identify common risks and options.", "professional")
    if s < 75:
        return CompetenceBand("experienced", "Experienced", "Reads non-obvious patterns, weighs tradeoffs, and notices important omissions.", "deep")
    if s < 90:
        return CompetenceBand("expert", "Expert", "Has highly developed judgment, broad pattern recognition, and strong specialty knowledge.", "expert")
    return CompetenceBand("master", "Master", "Possesses exceptional professional judgment within the limits of available evidence and their actual specialties.", "master")


def seed_competence_domains(conn: sqlite3.Connection) -> None:
    for key, meta in DEFAULT_DOMAINS.items():
        conn.execute(
            """INSERT OR IGNORE INTO competence_domains(domain_key,name,description,default_visibility)
               VALUES (?,?,?,'private')""",
            (key, meta["name"], meta["description"]),
        )


def set_actor_competence(
    conn: sqlite3.Connection,
    actor_id: int,
    domain_key: str,
    score: float,
    *,
    specialty: str | None = None,
    experience: dict[str, Any] | None = None,
    training: dict[str, Any] | None = None,
    confidence_modifier: float = 0.0,
    source_kind: str = "campaign",
    notes: str = "",
) -> int:
    seed_competence_domains(conn)
    domain = conn.execute("SELECT id FROM competence_domains WHERE domain_key=?", (domain_key,)).fetchone()
    if not domain:
        raise ValueError(f"Unknown competence domain: {domain_key}")
    day = current_day(conn)
    score = max(0.0, min(100.0, float(score)))
    confidence_modifier = max(-0.5, min(0.5, float(confidence_modifier)))
    conn.execute(
        """INSERT INTO actor_competence(
               actor_id,domain_id,score,specialty,experience_json,training_json,confidence_modifier,source_kind,updated_day,notes
           ) VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(actor_id,domain_id,specialty_key) DO UPDATE SET
               score=excluded.score,experience_json=excluded.experience_json,training_json=excluded.training_json,
               confidence_modifier=excluded.confidence_modifier,source_kind=excluded.source_kind,updated_day=excluded.updated_day,notes=excluded.notes""",
        (
            actor_id, int(domain["id"]), score, specialty,
            json.dumps(experience or {}, ensure_ascii=False), json.dumps(training or {}, ensure_ascii=False),
            confidence_modifier, source_kind, day, notes,
        ),
    )
    row = conn.execute(
        """SELECT ac.id FROM actor_competence ac
           JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=? AND ac.specialty_key=COALESCE(?, '')""",
        (actor_id, domain_key, specialty),
    ).fetchone()
    return int(row["id"])


def actor_competence_profile(conn: sqlite3.Connection, actor_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT ac.*,d.domain_key,d.name domain_name,d.description domain_description
           FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? ORDER BY ac.score DESC,d.domain_key,ac.specialty_key""",
        (actor_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["band"] = competence_band(float(row["score"])).as_dict()
        for key in ("experience_json", "training_json"):
            try:
                item[key.removesuffix("_json")] = json.loads(item[key] or "{}")
            except json.JSONDecodeError:
                item[key.removesuffix("_json")] = {}
            item.pop(key, None)
        out.append(item)
    return out


def _best_domain_row(conn: sqlite3.Connection, actor_id: int, domain_key: str, specialty: str | None = None) -> sqlite3.Row | None:
    if specialty:
        row = conn.execute(
            """SELECT ac.*,d.domain_key,d.name domain_name,d.description domain_description
               FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
               WHERE ac.actor_id=? AND d.domain_key=? AND ac.specialty_key=COALESCE(?, '')
               ORDER BY ac.score DESC LIMIT 1""",
            (actor_id, domain_key, specialty),
        ).fetchone()
        if row:
            return row
    return conn.execute(
        """SELECT ac.*,d.domain_key,d.name domain_name,d.description domain_description
           FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=?
           ORDER BY CASE WHEN ac.specialty IS NULL THEN 0 ELSE 1 END,ac.score DESC LIMIT 1""",
        (actor_id, domain_key),
    ).fetchone()


def _base_reading_confidence(score: float, evidence_quality: float, uncertainty: float, modifier: float) -> float:
    skill = max(0.0, min(1.0, float(score) / 100.0))
    evidence_quality = max(0.0, min(1.0, evidence_quality))
    uncertainty = max(0.0, min(1.0, uncertainty))
    # Skill improves inference but cannot erase missing evidence.
    confidence = 0.15 + 0.45 * skill + 0.35 * evidence_quality - 0.35 * uncertainty + modifier
    return round(max(0.05, min(0.95, confidence)), 3)


def prepare_professional_reading(
    conn: sqlite3.Connection,
    actor_id: int,
    domain_key: str,
    situation: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
    specialty: str | None = None,
    stakes: int = 2,
    uncertainty: float = 0.3,
    source_kind: str = "scene",
    source_id: int | None = None,
) -> dict[str, Any]:
    """Create an auditable, player-safe professional-reading packet.

    This does not invent hidden facts. It states how deeply the character may interpret
    accessible evidence and provides a contract for a model or deterministic adapter.
    """
    seed_competence_domains(conn)
    day = current_day(conn)
    row = _best_domain_row(conn, actor_id, domain_key, specialty)
    score = float(row["score"]) if row else 0.0
    modifier = float(row["confidence_modifier"]) if row else 0.0
    band = competence_band(score)
    ev = list(evidence or [])
    qualities = [float(x.get("reliability", x.get("confidence", 0.6))) for x in ev if isinstance(x, dict)]
    evidence_quality = sum(qualities) / len(qualities) if qualities else 0.45
    confidence = _base_reading_confidence(score, evidence_quality, uncertainty, modifier)

    cur = conn.execute(
        """INSERT INTO professional_readings(
               actor_id,domain_key,specialty,situation_text,evidence_json,stakes,uncertainty,
               competence_score,competence_band,reading_confidence,status,source_kind,source_id,created_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?,'prepared',?,?,?)""",
        (
            actor_id, domain_key, specialty, situation, json.dumps(ev, ensure_ascii=False),
            max(1, min(5, int(stakes))), max(0.0, min(1.0, float(uncertainty))), score,
            band.key, confidence, source_kind, source_id, day,
        ),
    )
    reading_id = int(cur.lastrowid)
    return {
        "reading_id": reading_id,
        "actor_id": actor_id,
        "domain": domain_key,
        "specialty": specialty,
        "situation": situation,
        "competence": {"score": score, "band": band.as_dict()},
        "reading_confidence": confidence,
        "evidence": ev,
        "stakes": max(1, min(5, int(stakes))),
        "uncertainty": max(0.0, min(1.0, float(uncertainty))),
        "interpretation_contract": {
            "depth": band.interpretation_depth,
            "may_interpret_accessible_evidence": True,
            "may_invent_hidden_facts": False,
            "may_override_player_choice": False,
            "must_distinguish_observation_from_inference": True,
            "must_surface_material_unknowns": True,
            "should_offer_actionable_options": band.key not in {"untrained"},
            "should_express_uncertainty": True,
        },
    }


def record_professional_reading(
    conn: sqlite3.Connection,
    reading_id: int,
    *,
    summary: str,
    observations: list[str] | None = None,
    inferences: list[str] | None = None,
    warnings: list[str] | None = None,
    unknowns: list[str] | None = None,
    options: list[dict[str, Any]] | None = None,
    confidence: float | None = None,
    provider: str = "rules",
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM professional_readings WHERE id=?", (reading_id,)).fetchone()
    if not row:
        raise ValueError(f"No professional reading #{reading_id}")
    if row["status"] not in {"prepared", "resolved"}:
        raise ValueError(f"Professional reading #{reading_id} cannot be resolved from status {row['status']}")
    bounded_conf = float(row["reading_confidence"])
    if confidence is not None:
        # A generated reading cannot assert more confidence than the competence/evidence packet permits.
        bounded_conf = min(bounded_conf, max(0.0, min(1.0, float(confidence))))
    result = {
        "summary": summary,
        "observations": list(observations or []),
        "inferences": list(inferences or []),
        "warnings": list(warnings or []),
        "unknowns": list(unknowns or []),
        "options": list(options or []),
        "confidence": round(bounded_conf, 3),
        "provider": provider,
    }
    conn.execute(
        """UPDATE professional_readings SET status='resolved',result_json=?,resolved_day=?,provider=? WHERE id=?""",
        (json.dumps(result, ensure_ascii=False), current_day(conn), provider, reading_id),
    )
    return {"reading_id": reading_id, **result}


def professional_reading(conn: sqlite3.Connection, reading_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM professional_readings WHERE id=?", (reading_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    for key in ("evidence_json", "result_json"):
        try:
            out[key.removesuffix("_json")] = json.loads(out[key] or ("[]" if key == "evidence_json" else "{}"))
        except json.JSONDecodeError:
            out[key.removesuffix("_json")] = [] if key == "evidence_json" else {}
        out.pop(key, None)
    return out


def add_advisor_judgment(
    conn: sqlite3.Connection,
    recipient_actor_id: int,
    advisor_actor_id: int,
    domain_key: str,
    situation_key: str,
    judgment: str,
    *,
    confidence: float = 0.6,
    communicated: bool = True,
    evidence: list[dict[str, Any]] | None = None,
    assumptions: list[str] | None = None,
    bias_note: str | None = None,
    source_kind: str = "conversation",
    source_id: int | None = None,
) -> int:
    seed_competence_domains(conn)
    if not conn.execute("SELECT 1 FROM actors WHERE id=?", (advisor_actor_id,)).fetchone():
        raise ValueError("Advisor actor does not exist")
    if not conn.execute("SELECT 1 FROM actors WHERE id=?", (recipient_actor_id,)).fetchone():
        raise ValueError("Recipient actor does not exist")
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO advisor_judgments(
               recipient_actor_id,advisor_actor_id,domain_key,situation_key,judgment_text,confidence,
               evidence_json,assumptions_json,bias_note,communicated,source_kind,source_id,created_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            recipient_actor_id, advisor_actor_id, domain_key, situation_key, judgment,
            max(0.0, min(1.0, float(confidence))), json.dumps(evidence or [], ensure_ascii=False),
            json.dumps(assumptions or [], ensure_ascii=False), bias_note, 1 if communicated else 0,
            source_kind, source_id, day,
        ),
    )
    return int(cur.lastrowid)


def advisor_judgments(
    conn: sqlite3.Connection,
    recipient_actor_id: int,
    *,
    situation_key: str | None = None,
    domain_key: str | None = None,
    communicated_only: bool = True,
    limit: int = 12,
) -> list[dict[str, Any]]:
    clauses = ["aj.recipient_actor_id=?"]
    params: list[Any] = [recipient_actor_id]
    if situation_key is not None:
        clauses.append("aj.situation_key=?")
        params.append(situation_key)
    if domain_key is not None:
        clauses.append("aj.domain_key=?")
        params.append(domain_key)
    if communicated_only:
        clauses.append("aj.communicated=1")
    params.append(limit)
    rows = conn.execute(
        f"""SELECT aj.*,a.name advisor_name FROM advisor_judgments aj
            JOIN actors a ON a.id=aj.advisor_actor_id
            WHERE {' AND '.join(clauses)} ORDER BY aj.created_day DESC,aj.id DESC LIMIT ?""",
        params,
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        for key in ("evidence_json", "assumptions_json"):
            try:
                item[key.removesuffix("_json")] = json.loads(item[key] or "[]")
            except json.JSONDecodeError:
                item[key.removesuffix("_json")] = []
            item.pop(key, None)
        out.append(item)
    return out


_KEYWORDS: dict[str, tuple[str, ...]] = {
    "commerce": ("trade", "merchant", "price", "buy", "sell", "market", "credit", "loan", "contract", "shipment", "profit"),
    "command": ("army", "battle", "troop", "unit", "command", "officer", "campaign", "siege", "reserve", "formation"),
    "politics": ("court", "king", "queen", "lord", "duke", "alliance", "claim", "succession", "minister", "faction", "politic"),
    "medicine": ("ill", "injury", "patient", "doctor", "physician", "medicine", "fever", "recover", "health"),
    "vein_mending": ("core", "channel", "vessel", "rupture", "mender", "vein-mender", "cultivation injury"),
    "architecture": ("building", "architect", "house", "hall", "bridge", "construction", "stone", "timber", "design"),
    "craft": ("smith", "workshop", "forge", "craft", "weave", "tailor", "material", "make", "commission"),
    "art_culture": ("painting", "sculpture", "artist", "auction", "provenance", "collection", "attribution", "fashion", "music"),
    "scholarship": ("book", "archive", "scholar", "university", "text", "research", "manuscript", "history"),
    "law": ("law", "legal", "inherit", "court case", "claim", "contract", "property", "jurisdiction"),
    "social": ("persuade", "negotiate", "conversation", "insult", "etiquette", "dinner", "speech", "social"),
    "martial": ("duel", "fight", "martial", "technique", "training", "cultivation", "weapon"),
}


def infer_relevant_domains(request_text: str, profile: list[dict[str, Any]], limit: int = 3) -> list[str]:
    text = (request_text or "").lower()
    scores: dict[str, float] = {}
    for domain, words in _KEYWORDS.items():
        hit = sum(1 for w in words if w in text)
        if hit:
            scores[domain] = float(hit) * 10.0
    by_domain: dict[str, float] = {}
    for item in profile:
        d = str(item["domain_key"])
        by_domain[d] = max(by_domain.get(d, 0.0), float(item["score"]))
    for d in list(scores):
        scores[d] += by_domain.get(d, 0.0) / 20.0
    return [d for d, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def build_scene_competence_packet(conn: sqlite3.Connection, actor_id: int, request_text: str = "") -> dict[str, Any]:
    profile = actor_competence_profile(conn, actor_id)
    relevant = infer_relevant_domains(request_text, profile)
    compact = []
    for domain in relevant:
        row = _best_domain_row(conn, actor_id, domain)
        if row:
            band = competence_band(float(row["score"]))
            compact.append({
                "domain": domain,
                "score": float(row["score"]),
                "band": band.key,
                "label": band.label,
                "interpretation_depth": band.interpretation_depth,
                "specialty": row["specialty"],
            })
        else:
            compact.append({"domain": domain, "score": 0.0, "band": "untrained", "label": "Untrained", "interpretation_depth": "surface", "specialty": None})
    return {
        "relevant_domains": compact,
        "all_domains": profile,
        "rules": [
            "Character expertise may interpret accessible evidence but may not reveal hidden world state.",
            "Separate direct observation, reports, professional inference, advisor judgment, and player choice.",
            "Higher competence deepens interpretation; it never makes the character omniscient.",
            "Surface material uncertainty and missing evidence rather than inventing certainty.",
            "Offer actionable professional options when the character has enough competence to frame them.",
            "Do not silently override a deliberate player decision merely because the character is expert.",
        ],
    }


def decision_context(
    conn: sqlite3.Connection,
    actor_id: int,
    domain_key: str,
    situation_key: str,
    *,
    reading_id: int | None = None,
) -> dict[str, Any]:
    reading = professional_reading(conn, reading_id) if reading_id is not None else None
    return {
        "character_professional_reading": reading,
        "advisor_judgments": advisor_judgments(
            conn, actor_id, situation_key=situation_key, domain_key=domain_key, communicated_only=True
        ),
        "separation_rule": "Character knowledge, reports, advisor judgment, and player decision are distinct layers.",
    }
