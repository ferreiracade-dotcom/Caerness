from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, asdict
from typing import Any, Iterable



def _current_day(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()
    return int(row[0]) if row else 0


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _stable_fraction(*parts: object) -> float:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


@dataclass(frozen=True)
class BeliefState:
    actor_id: int
    claim_id: int
    stance: str
    confidence: float
    updated_day: int
    correction_count: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_claim(
    conn: sqlite3.Connection,
    claim_key: str,
    proposition_text: str,
    *,
    subject_kind: str | None = None,
    subject_id: int | None = None,
    authoritative_event_id: int | None = None,
    created_day: int | None = None,
    source_kind: str = "simulation",
) -> int:
    day = _current_day(conn) if created_day is None else int(created_day)
    row = conn.execute("SELECT id FROM information_claims WHERE claim_key=?", (claim_key,)).fetchone()
    if row:
        cid = int(row[0])
        conn.execute(
            """UPDATE information_claims SET proposition_text=COALESCE(NULLIF(?,''),proposition_text),
               authoritative_event_id=COALESCE(authoritative_event_id,?),subject_kind=COALESCE(subject_kind,?),
               subject_id=COALESCE(subject_id,?) WHERE id=?""",
            (proposition_text, authoritative_event_id, subject_kind, subject_id, cid),
        )
        return cid
    cur = conn.execute(
        """INSERT INTO information_claims(
               claim_key,proposition_text,subject_kind,subject_id,authoritative_event_id,created_day,source_kind,status
           ) VALUES (?,?,?,?,?,?,?,'active')""",
        (claim_key, proposition_text, subject_kind, subject_id, authoritative_event_id, day, source_kind),
    )
    return int(cur.lastrowid)


def add_claim_evidence(
    conn: sqlite3.Connection,
    claim_id: int,
    *,
    evidence_kind: str,
    summary: str,
    source_id: int | None = None,
    polarity: str = "supports",
    reliability: float = 0.7,
    salience: float = 0.6,
    domain_key: str | None = None,
    location_id: int | None = None,
    available_from_day: int | None = None,
    source_actor_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    if polarity not in {"supports", "contradicts", "context"}:
        raise ValueError("polarity must be supports, contradicts, or context")
    day = _current_day(conn) if available_from_day is None else int(available_from_day)
    cur = conn.execute(
        """INSERT INTO claim_evidence(
               claim_id,evidence_kind,source_id,source_actor_id,polarity,reliability,salience,domain_key,
               location_id,summary,available_from_day,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            claim_id, evidence_kind, source_id, source_actor_id, polarity, _clamp(reliability),
            _clamp(salience), domain_key, location_id, summary, day,
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


def grant_evidence(
    conn: sqlite3.Connection,
    actor_id: int,
    evidence_id: int,
    *,
    received_day: int | None = None,
    access_kind: str = "observed",
    weight: float = 1.0,
    notes: str = "",
) -> None:
    day = _current_day(conn) if received_day is None else int(received_day)
    conn.execute(
        """INSERT INTO actor_evidence_access(actor_id,evidence_id,received_day,access_kind,weight,notes)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(actor_id,evidence_id) DO UPDATE SET
             received_day=MIN(actor_evidence_access.received_day,excluded.received_day),
             access_kind=excluded.access_kind,weight=MAX(actor_evidence_access.weight,excluded.weight),notes=excluded.notes""",
        (actor_id, evidence_id, day, access_kind, _clamp(weight), notes),
    )


def _compute_belief_from_access(conn: sqlite3.Connection, actor_id: int, claim_id: int) -> tuple[str, float, list[int]]:
    rows = conn.execute(
        """SELECT ce.id,ce.polarity,ce.reliability,aea.weight
           FROM claim_evidence ce JOIN actor_evidence_access aea ON aea.evidence_id=ce.id
           WHERE ce.claim_id=? AND aea.actor_id=? ORDER BY aea.received_day,ce.id""",
        (claim_id, actor_id),
    ).fetchall()
    if not rows:
        return "unaware", 0.0, []
    support = 0.0
    contradict = 0.0
    ids: list[int] = []
    for row in rows:
        ids.append(int(row["id"]))
        strength = _clamp(float(row["reliability"])) * _clamp(float(row["weight"]))
        if row["polarity"] == "supports":
            support += strength
        elif row["polarity"] == "contradicts":
            contradict += strength
    total = support + contradict
    net = support - contradict
    if total <= 0.05:
        return "uncertain", 0.15, ids
    normalized = net / total
    strength_factor = 1.0 - (0.55 ** total)
    confidence = _clamp(abs(normalized) * 0.72 + strength_factor * 0.28, 0.05, 0.98)
    if normalized >= 0.16:
        stance = "accepts"
    elif normalized <= -0.16:
        stance = "rejects"
    else:
        stance = "uncertain"
        confidence = min(confidence, 0.45)
    return stance, round(confidence, 3), ids


def recompute_actor_belief(conn: sqlite3.Connection, actor_id: int, claim_id: int, *, day: int | None = None, reason: str = "evidence_update") -> BeliefState:
    day = _current_day(conn) if day is None else int(day)
    stance, confidence, evidence_ids = _compute_belief_from_access(conn, actor_id, claim_id)
    old = conn.execute("SELECT * FROM actor_beliefs WHERE actor_id=? AND claim_id=?", (actor_id, claim_id)).fetchone()
    old_stance = str(old["stance"]) if old else "unaware"
    old_conf = float(old["confidence"]) if old else 0.0
    first_received = int(old["first_received_day"]) if old else day
    correction_count = int(old["correction_count"]) if old else 0
    changed = old_stance != stance or abs(old_conf - confidence) > 1e-9
    if changed and old and old_stance not in {"unaware", "uncertain"} and stance != old_stance:
        correction_count += 1
    conn.execute(
        """INSERT INTO actor_beliefs(actor_id,claim_id,stance,confidence,first_received_day,updated_day,correction_count,basis_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(actor_id,claim_id) DO UPDATE SET stance=excluded.stance,confidence=excluded.confidence,
             updated_day=excluded.updated_day,correction_count=excluded.correction_count,basis_json=excluded.basis_json""",
        (actor_id, claim_id, stance, confidence, first_received, day, correction_count, json.dumps(evidence_ids)),
    )
    if changed:
        conn.execute(
            """INSERT INTO belief_revisions(actor_id,claim_id,day,old_stance,new_stance,old_confidence,new_confidence,reason,evidence_ids_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (actor_id, claim_id, day, old_stance, stance, old_conf, confidence, reason, json.dumps(evidence_ids)),
        )
    return BeliefState(actor_id, claim_id, stance, confidence, day, correction_count)


def observe_claim(
    conn: sqlite3.Connection,
    actor_id: int,
    claim_id: int,
    evidence_id: int,
    *,
    received_day: int | None = None,
    access_kind: str = "observed",
    weight: float = 1.0,
    reason: str = "evidence_received",
) -> BeliefState:
    grant_evidence(conn, actor_id, evidence_id, received_day=received_day, access_kind=access_kind, weight=weight)
    return recompute_actor_belief(conn, actor_id, claim_id, day=received_day, reason=reason)


def mirror_legacy_knowledge(
    conn: sqlite3.Connection,
    *,
    knowledge_id: int,
    actor_id: int,
    fact_key: str,
    belief_text: str,
    confidence: float,
    learned_day: int,
    truth_event_id: int | None,
    source_kind: str,
    source_id: int | None,
    location_id: int | None,
    notes: str | None,
) -> int:
    """Mirror compatibility `knowledge` writes into the claim/evidence/belief model."""
    claim_key = fact_key
    existing = conn.execute("SELECT id,proposition_text FROM information_claims WHERE claim_key=?", (fact_key,)).fetchone()
    if existing and str(existing["proposition_text"]) != str(belief_text):
        suffix = hashlib.sha256(str(belief_text).encode("utf-8")).hexdigest()[:12]
        claim_key = f"{fact_key}#{suffix}"
    claim_id = ensure_claim(
        conn, claim_key, belief_text, authoritative_event_id=truth_event_id, created_day=learned_day,
        source_kind="legacy_knowledge",
    )
    # One evidence row per legacy knowledge/provenance acquisition; source_id can repeat legitimately.
    evidence_id = add_claim_evidence(
        conn, claim_id, evidence_kind=source_kind, source_id=source_id, summary=belief_text,
        polarity="supports", reliability=confidence, salience=max(0.35, confidence), location_id=location_id,
        available_from_day=learned_day, metadata={"legacy_knowledge_id": knowledge_id, "notes": notes or ""},
    )
    observe_claim(
        conn, actor_id, claim_id, evidence_id, received_day=learned_day,
        access_kind="legacy_knowledge", weight=1.0, reason="legacy_knowledge_mirror",
    )
    return claim_id


def import_existing_knowledge(conn: sqlite3.Connection) -> int:
    made = 0
    rows = conn.execute("SELECT * FROM knowledge ORDER BY id").fetchall()
    for row in rows:
        if conn.execute(
            """SELECT 1 FROM actor_beliefs ab JOIN information_claims c ON c.id=ab.claim_id
               WHERE ab.actor_id=? AND c.claim_key=?""", (int(row["knower_actor_id"]), str(row["fact_key"]))
        ).fetchone():
            continue
        prov = conn.execute("SELECT * FROM knowledge_provenance WHERE knowledge_id=? ORDER BY id LIMIT 1", (int(row["id"]),)).fetchone()
        mirror_legacy_knowledge(
            conn, knowledge_id=int(row["id"]), actor_id=int(row["knower_actor_id"]), fact_key=str(row["fact_key"]),
            belief_text=str(row["belief_text"]), confidence=float(row["confidence"]), learned_day=int(row["learned_day"]),
            truth_event_id=int(row["truth_event_id"]) if row["truth_event_id"] is not None else None,
            source_kind=str(prov["source_kind"]) if prov else "admin",
            source_id=int(prov["source_id"]) if prov and prov["source_id"] is not None else None,
            location_id=int(prov["location_id"]) if prov and prov["location_id"] is not None else None,
            notes=str(prov["notes"] or "") if prov else "Imported from legacy knowledge table.",
        )
        made += 1
    return made


def actor_belief_envelope(conn: sqlite3.Connection, actor_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
    """Actor-safe belief view. Intentionally omits authoritative hidden truth links."""
    rows = conn.execute(
        """SELECT ab.actor_id,ab.claim_id,ab.stance,ab.confidence,ab.first_received_day,ab.updated_day,ab.correction_count,
                  c.claim_key,c.proposition_text,c.subject_kind,c.subject_id
           FROM actor_beliefs ab JOIN information_claims c ON c.id=ab.claim_id
           WHERE ab.actor_id=? ORDER BY ab.updated_day DESC,ab.claim_id DESC LIMIT ?""",
        (actor_id, max(1, int(limit))),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        evidence = conn.execute(
            """SELECT ce.id,ce.evidence_kind,ce.source_actor_id,ce.polarity,ce.reliability,ce.salience,ce.domain_key,
                      ce.location_id,ce.summary,aea.received_day,aea.access_kind,aea.weight
               FROM claim_evidence ce JOIN actor_evidence_access aea ON aea.evidence_id=ce.id
               WHERE ce.claim_id=? AND aea.actor_id=? ORDER BY aea.received_day,ce.id""",
            (int(row["claim_id"]), actor_id),
        ).fetchall()
        item["evidence"] = [dict(e) for e in evidence]
        out.append(item)
    return list(reversed(out))


def build_competence_lens(
    conn: sqlite3.Connection,
    actor_id: int,
    domain_key: str,
    *,
    claim_ids: Iterable[int] | None = None,
    situation: str = "Interpret the evidence available to you.",
    stakes: int = 2,
    uncertainty: float = 0.3,
) -> dict[str, Any]:
    """Turn actor-accessible evidence into a profession-sensitive reading packet.

    Competence changes attention and interpretive depth. It never adds evidence the actor does
    not possess, and the packet never exposes a claim's authoritative_event_id.
    """
    from .expertise import _best_domain_row, prepare_professional_reading

    day = _current_day(conn)
    row = _best_domain_row(conn, actor_id, domain_key)
    score = float(row["score"]) if row else 0.0
    skill = _clamp(score / 100.0)
    params: list[Any] = [actor_id]
    claim_filter = ""
    if claim_ids is not None:
        ids = sorted({int(x) for x in claim_ids})
        if not ids:
            ids = [-1]
        claim_filter = " AND ce.claim_id IN (" + ",".join("?" for _ in ids) + ")"
        params.extend(ids)
    accessible = conn.execute(
        """SELECT ce.id evidence_id,ce.claim_id,ce.evidence_kind,ce.polarity,ce.reliability,ce.salience,
                  ce.domain_key,ce.location_id,ce.summary,aea.received_day,aea.access_kind,aea.weight,
                  c.claim_key,c.proposition_text
           FROM claim_evidence ce
           JOIN actor_evidence_access aea ON aea.evidence_id=ce.id
           JOIN information_claims c ON c.id=ce.claim_id
           WHERE aea.actor_id=?""" + claim_filter + " ORDER BY aea.received_day,ce.id",
        tuple(params),
    ).fetchall()
    noticed: list[dict[str, Any]] = []
    for ev in accessible:
        domain_match = ev["domain_key"] is None or str(ev["domain_key"]) == domain_key
        salience = _clamp(float(ev["salience"]))
        chance = _clamp(0.18 + 0.58 * skill + 0.22 * salience + (0.08 if domain_match else -0.12), 0.05, 0.98)
        if _stable_fraction("competence_lens", actor_id, domain_key, int(ev["evidence_id"]), day) <= chance:
            noticed.append({
                "evidence_id": int(ev["evidence_id"]), "claim_id": int(ev["claim_id"]),
                "claim_key": str(ev["claim_key"]), "claim": str(ev["proposition_text"]),
                "summary": str(ev["summary"]), "polarity": str(ev["polarity"]),
                "reliability": float(ev["reliability"]), "salience": salience,
                "domain_key": ev["domain_key"], "access_kind": str(ev["access_kind"]),
            })
    reading = prepare_professional_reading(
        conn, actor_id, domain_key, situation, evidence=noticed, stakes=stakes, uncertainty=uncertainty,
        source_kind="belief_envelope",
    )
    return {
        "actor_id": actor_id,
        "domain_key": domain_key,
        "accessible_evidence_count": len(accessible),
        "noticed_evidence_count": len(noticed),
        "noticed_evidence": noticed,
        "beliefs": actor_belief_envelope(conn, actor_id),
        "professional_reading": reading,
        "guardrails": {
            "uses_only_actor_accessible_evidence": True,
            "competence_improves_attention_not_omniscience": True,
            "authoritative_truth_links_exposed": False,
        },
    }
