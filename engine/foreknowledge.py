"""What a character could plausibly know, never what the player knows.

Foreknowledge never pays by itself. A bet on a future real fact is judged on what the man behind it could have come across:
his own competence in the field, the competence of the people he employs or commands, and what he has actually heard. The
player profits from foresight only by positioning the character: learning the field, hiring people who know it, reading the
trade, putting money and men where the news is made. NPCs get the same judgement.
"""
from __future__ import annotations

import sqlite3

from . import history


def _field_score(conn: sqlite3.Connection, actor_id: int, words: set[str]) -> float:
    best = 0.0
    for r in conn.execute("SELECT d.domain_key,d.name,c.score,c.specialty FROM actor_competence c JOIN competence_domains d ON d.id=c.domain_id WHERE c.actor_id=?",
                          (int(actor_id),)):
        if words & history._tokens(f"{r['domain_key']} {r['name']} {r['specialty'] or ''}"):
            best = max(best, float(r["score"]) / 100.0)
    return best


def _people(conn: sqlite3.Connection, actor_id: int) -> list[int]:
    """Those he employs or commands: enterprise staff of firms he owns, his household's service people, his subordinates."""
    ids: set[int] = set()
    for r in conn.execute("SELECT s.actor_id FROM enterprise_staff s JOIN civilian_enterprises e ON e.id=s.enterprise_id "
                          "WHERE e.owner_actor_id=? AND s.status='active'", (int(actor_id),)):
        ids.add(int(r[0]))
    for r in conn.execute("SELECT t.actor_id FROM household_service_terms t "
                          "WHERE t.status='active' AND t.household_id IN (SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?)", (int(actor_id),)):
        ids.add(int(r[0]))
    for r in conn.execute("SELECT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active'", (int(actor_id),)):
        ids.add(int(r[0]))
    ids.discard(int(actor_id))
    return sorted(ids)


def character_knows(conn: sqlite3.Connection, actor_id: int, subject_words: str, day: int | None = None) -> dict:
    """{"level": none | hint | informed, "sources": [...]} from competence (his own and his people's) and what he has heard."""
    words = history._tokens(subject_words, conn)
    fig = history.rules(conn).get("foreknowledge") or {}
    informed_at, hint_at = float(fig.get("informed_competence", 0.5)), float(fig.get("hint_competence", 0.2))
    sources: list[str] = []
    best = _field_score(conn, int(actor_id), words)
    if best:
        sources.append(f"his own competence ({best:.2f})")
    for pid in _people(conn, int(actor_id)):
        s = _field_score(conn, pid, words)
        if s:
            sources.append(f"{history._name(conn, pid)} who works for him ({s:.2f})")
            best = max(best, s)
    heard = 0
    for r in conn.execute("SELECT belief_text FROM knowledge WHERE knower_actor_id=?", (int(actor_id),)):
        if words & history._tokens(r["belief_text"]):
            heard += 1
    if heard:
        sources.append(f"{heard} things he has heard")
    level = "informed" if best >= informed_at else "hint" if (best >= hint_at or heard) else "none"
    return {"level": level, "sources": sources}
