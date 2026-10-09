"""SPEECH-01 step 1: speaker cards, so the narrator voices people from the state instead of inventing them.

Before this, present people reached the narrator as name, type and status only (engine/player.py
_present_actors), so whatever an NPC said, wanted or promised was made up at narration time.

A card carries, for each person likely to speak: what they visibly are (role, office, institution), how they
stand toward the followed character (familiarity, demeanour, shared history), the open dealings between them
(the only commitments they may voice), and how they come across: temperament as portrayal cues and a few
mannerisms and speech habits.

Temperament comes from the person's drives (actor_drives) when they have them. Otherwise it is drawn once from
a stable seeded preview, bell-shaped around the middle, and the card says so: the decision engine still treats
such people as average (decisions._drive_row) until opening resolution writes their drives, which should use
the same draw (see seeded_drives). Mannerisms and speech habits are texture: resolved on first look (DESIGN
§15.1) from pools fitting the person's role and age, recorded in character_embodiment, and never redrawn.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any, Iterable

DRIVES = ("aggression", "risk_tolerance", "patience", "loyalty", "ambition", "pragmatism")

# Portrayal cues for clearly high or low drives; shown through behaviour, never stated as traits.
_CUES = {
    "aggression": ("slow to anger; steps around confrontation", "quick to take offence; meets a challenge head-on"),
    "risk_tolerance": ("cautious; wants guarantees before committing", "bold; at ease with danger"),
    "patience": ("impatient; interrupts and pushes to the point", "unhurried; lets silences run"),
    "loyalty": ("treats allegiances as transactions", "speaks of their people and obligations first"),
    "ambition": ("content with their station", "measures people by what they can offer; restless to rise"),
    "pragmatism": ("argues from what is proper", "practical; deals in what works"),
}

# Role classes, recognised from role words. Order matters: the first match wins.
_ROLE_WORDS = (
    ("underworld", ("boss", "enforcer", "smuggl", "fence", "gang", "racket", "thief", "assassin", "crime", "lender")),
    ("official", ("governor", "magistrate", "clerk", "official", "officer", "steward", "administrat", "minister",
                  "envoy", "tax", "court")),
    ("merchant", ("merchant", "trader", "factor", "shop", "broker", "banker", "dealer", "caravan", "innkeeper",
                  "proprietor")),
    ("learned", ("priest", "scholar", "archiv", "physician", "healer", "doctor", "scribe", "teacher", "tutor",
                 "monk", "abbot", "apothecar")),
    ("martial", ("sword", "spear", "disciple", "master", "elder", "guard", "duel", "fighter", "soldier", "captain",
                 "general", "warlord", "mercenar", "head", "heir", "knight", "warden", "martial", "practitioner")),
    ("labour", ("farmer", "harvest", "porter", "dock", "labour", "labor", "servant", "groom", "smith", "miner",
                "boatman", "carter")),
)

# Mannerism and speech pools: texture only, plausible anywhere on the continent, specific by role.
_MANNERISMS = {
    "general": ("rubs a thumb along the edge of whatever they hold", "tilts the head slightly when listening",
                "keeps their hands folded and still", "glances at the door when someone enters",
                "pauses before answering, as if weighing the question", "straightens their clothing when uneasy",
                "taps two fingers on the table while thinking", "holds eye contact a moment longer than most",
                "laughs quietly, mostly through the nose", "stands with their weight on one leg"),
    "martial": ("rests a hand near the weapon without touching it", "stands square, feet set as if on a training floor",
                "notes where everyone in the room is before sitting", "breathes slow and even, even when angry",
                "flexes the fingers of one hand, as if testing them", "keeps their back to a wall when they can"),
    "merchant": ("weighs coins or goods absently in the palm", "notices fabric, fittings and wear on others' clothes",
                 "smiles quickly and stops just as quickly", "names prices without hesitation",
                 "keeps a small tally on their fingers", "leans in when a number is mentioned"),
    "official": ("speaks with the cadence of someone used to being written down", "squares papers that are already square",
                 "uses titles exactly and expects the same", "lets an inferior finish before replying",
                 "folds hands inside the sleeves", "looks past people toward whoever outranks them"),
    "underworld": ("watches hands rather than faces", "speaks low enough that others must lean in",
                   "never sits with the door behind them", "smiles without it reaching the eyes",
                   "turns a ring or coin over the knuckles", "lets silences do the threatening"),
    "learned": ("cleans ink or herbs from under the nails without noticing", "quotes or half-quotes when making a point",
                "examines things closely before touching them", "corrects small errors almost apologetically",
                "keeps their place in a conversation with a raised finger", "speaks more slowly when it matters"),
    "labour": ("works a callus on the palm with a thumb", "shifts as if unused to standing idle",
               "wipes hands on their clothes before taking anything", "speaks plainly and briefly",
               "eyes the weather through the nearest opening", "stretches the back of the neck"),
}
_SPEECH = {
    "general": ("plain and direct", "measured, choosing words with care", "warm and talkative",
                "dry, with understatement", "brisk, finishing other people's sentences", "formal, sparing with names"),
    "martial": ("clipped, used to giving or taking orders", "quiet and exact", "blunt, impatient with flourish"),
    "merchant": ("friendly patter that circles back to terms", "precise about quantities and dates"),
    "official": ("formal, full titles every time", "careful, never committing in the first answer"),
    "underworld": ("soft-spoken, every word deliberate", "easy and familiar, until it is not"),
    "learned": ("precise, fond of qualification", "gentle, explanatory"),
    "labour": ("plain, local idiom", "few words, mostly practical"),
}
_ELDER_MANNERISMS = ("moves without hurry and expects others to wait", "addresses younger people by their family's name")
_YOUTH_MANNERISMS = ("fidgets when made to wait", "glances to elders before speaking")


def _fraction(*parts: object) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _world_seed(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def seeded_drives(conn: sqlite3.Connection, actor_id: int) -> dict[str, float]:
    """A stable, bell-shaped draw per drive (mean of three uniforms). Opening resolution should use this same
    draw when it writes actor_drives for people who have none, so portrayal and decisions agree."""
    seed = _world_seed(conn)
    return {d: round(sum(_fraction("drives", seed, int(actor_id), d, i) for i in range(3)) / 3.0, 3) for d in DRIVES}


def temperament(conn: sqlite3.Connection, actor_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    if row:
        drives, basis = {d: float(row[d]) for d in DRIVES}, "actor_drives"
    else:
        drives, basis = seeded_drives(conn, actor_id), "seeded_preview"
    cues = [(_CUES[d][1] if v >= 0.68 else _CUES[d][0]) for d, v in drives.items() if v >= 0.68 or v <= 0.32]
    return {"cues": cues or ["even-tempered; nothing in excess"], "basis": basis}


# Seed role texts mix public positions ("Sect Head", "Senior spear master", "independent duelist") with the
# seed's own judgements of a person ("Generational anomaly", "Good fundamentals", "Strong mature Third").
# Judgements and Stage labels are not something anyone wears or is called, so the narrator never gets them.
_JUDGEMENT = {"anomaly", "freak", "prodigy", "prodigious", "promising", "promise", "high-promise", "talent", "talented",
              "strong", "stronger", "strongest", "formidable", "exceptional", "excellent", "good", "solid", "steady",
              "above-average", "very", "highly", "major", "accelerating", "developing", "development", "fundamentals",
              "hype", "respected", "regarded", "technically", "clear", "extreme", "broad", "deep", "deepest",
              "greatest", "generational", "apex", "mature", "prospect", "unusual", "without", "famous", "living",
              "acknowledged", "historical", "most", "best", "gifted", "elite", "outstanding", "remarkable", "known"}
_STAGES = ("first", "temper", "third", "breach", "fifth", "sixth")
_ROLE_NOUNS = {"head", "leader", "elder", "master", "instructor", "teacher", "disciple", "student", "recruit",
               "retainer", "member", "heir", "champion", "captain", "commander", "admiral", "queen", "king", "emperor",
               "empress", "lord", "inheritor", "mediator", "traveller", "wanderer", "warlord", "duelist", "hermit",
               "figure", "practitioner", "guard", "soldier", "officer", "governor", "magistrate", "steward", "merchant",
               "trader", "innkeeper", "physician", "healer", "priest", "scholar", "smith", "farmer", "boatman",
               "porter", "servant", "clerk", "envoy", "minister", "general", "knight", "warden", "relative", "junior",
               "roader", "witness", "representative", "recruiter", "lady", "prince", "princess", "chancellor"}


def public_role(text: str | None) -> str | None:
    """What a person is publicly, from a seed role text: the first clause that names a position or profession,
    with judgements and Stage labels removed. None when the text is only a judgement."""
    for clause in str(text or "").split(";"):
        kept = []
        for word in clause.strip().rstrip(".").split():
            w = word.lower().strip(",.()")
            if w in _JUDGEMENT or w.startswith(_STAGES) and (w in _STAGES or "-" in w):
                continue
            kept.append(word)
        if any(w.lower().strip(",.()").rstrip("s") in _ROLE_NOUNS for w in kept):
            out = " ".join(kept).strip(" ,")
            return out[:1].upper() + out[1:] if out else None
    return None


def _role_text(conn: sqlite3.Connection, actor_id: int, subtype: str | None) -> tuple[str, list[str]]:
    roles = [dict(r) for r in conn.execute(
        """SELECT m.role_text, a.name institution FROM institution_memberships m
           JOIN actors a ON a.id=m.institution_actor_id
           WHERE m.member_actor_id=? AND m.status='active' ORDER BY m.id""", (int(actor_id),))]
    standing = [f"{public_role(r['role_text'])} ({r['institution']})" if public_role(r["role_text"])
                else f"member of {r['institution']}" for r in roles]
    words = " ".join([str(subtype or "")] + [str(r["role_text"] or "") for r in roles]).lower()
    return words, standing


def role_class(words: str, *, has_stage: bool) -> str:
    for cls, keys in _ROLE_WORDS:
        if any(k in words for k in keys):
            return cls
    return "martial" if has_stage else "general"


def _age(conn: sqlite3.Connection, actor_id: int, day: int) -> tuple[int | None, str | None, str | None]:
    row = conn.execute("SELECT birth_day,demographic_sex,life_stage FROM actor_life_profiles WHERE actor_id=?",
                       (int(actor_id),)).fetchone()
    if not row:
        return None, None, None
    age = int((day - int(row["birth_day"])) / 365.25) if row["birth_day"] is not None else None
    return age, row["demographic_sex"], row["life_stage"]


def _stage(conn: sqlite3.Connection, actor_id: int) -> str | None:
    try:
        row = conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?", (int(actor_id),)).fetchone()
    except sqlite3.OperationalError:
        return None
    return str(row["current_stage"]) if row and row["current_stage"] else None


def mannerisms(conn: sqlite3.Connection, actor_id: int, cls: str, life_stage: str | None, day: int) -> dict[str, Any]:
    """Resolved on first look, then remembered: drawn once, recorded in character_embodiment, never redrawn."""
    from .embodiment import ensure_embodiment_profile
    ensure_embodiment_profile(conn, int(actor_id), source_kind="generated")
    row = conn.execute("SELECT habits_json,voice_json,development_json FROM character_embodiment WHERE actor_id=?",
                       (int(actor_id),)).fetchone()
    habits, voice, development = _loads(row["habits_json"]), _loads(row["voice_json"]), _loads(row["development_json"])
    if habits.get("mannerisms") and voice.get("speech"):
        return {"mannerisms": habits["mannerisms"], "speech": voice["speech"], "first_seen_day": (
            development.get("revealed", {}).get("mannerisms", {}).get("day"))}
    seed = _world_seed(conn)
    pick = lambda pool, *k: pool[int(_fraction("manner", seed, int(actor_id), *k) * len(pool)) % len(pool)]
    own = _MANNERISMS.get(cls, ())
    chosen = [pick(own, "role")] if own else []
    general = [m for m in _MANNERISMS["general"] if m not in chosen]
    chosen.append(pick(general, "general"))
    if life_stage == "elder":
        chosen.append(pick(_ELDER_MANNERISMS, "age"))
    elif life_stage in ("youth", "child"):
        chosen.append(pick(_YOUTH_MANNERISMS, "age"))
    speech = pick(_SPEECH.get(cls, ()) + _SPEECH["general"], "speech")
    habits["mannerisms"] = chosen
    voice["speech"] = speech
    development.setdefault("revealed", {})["mannerisms"] = {"day": day, "basis": "resolved_on_reveal",
                                                            "role_class": cls}
    conn.execute("UPDATE character_embodiment SET habits_json=?,voice_json=?,development_json=?,updated_day=? "
                 "WHERE actor_id=?", (json.dumps(habits, ensure_ascii=False, sort_keys=True),
                                      json.dumps(voice, ensure_ascii=False, sort_keys=True),
                                      json.dumps(development, ensure_ascii=False, sort_keys=True), day, int(actor_id)))
    return {"mannerisms": chosen, "speech": speech, "first_seen_day": day}


def _bands(rel: sqlite3.Row | None) -> tuple[str, str]:
    if rel is None:
        return "has not met them", "a stranger's ordinary civility"
    fam = float(rel["familiarity"])
    familiarity = ("knows them by sight or name" if fam < 25 else "acquainted" if fam < 60 else "knows them well")
    v = {k: float(rel[k]) for k in ("stance", "trust", "affection", "respect", "fear", "resentment")}
    if v["fear"] >= 40:
        demeanour = "afraid of them; formal and careful"
    elif v["resentment"] >= 40 or v["stance"] <= -40:
        demeanour = "hostile or resentful, within whatever courtesy the setting demands"
    elif v["trust"] <= -30:
        demeanour = "distrustful"
    elif v["affection"] >= 40 or v["stance"] >= 40:
        demeanour = "warm"
    elif v["respect"] >= 40:
        demeanour = "respectful"
    else:
        demeanour = "civil"
    return familiarity, demeanour


def _dealings(conn: sqlite3.Connection, a: int, b: int) -> list[str]:
    out = []
    for r in conn.execute("""SELECT agreement_type,terms_json,created_day FROM agreements WHERE status='active'
                             AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))
                             ORDER BY created_day DESC,id DESC LIMIT 4""", (a, b, b, a)):
        purpose = _loads(r["terms_json"]).get("purpose")
        out.append(f"active {r['agreement_type']} agreement since day {r['created_day']}" + (f": {purpose}" if purpose else ""))
    for r in conn.execute("""SELECT interaction_type,terms_json,proposer_actor_id,response_due_day FROM interactions
                             WHERE status='pending' AND ((proposer_actor_id=? AND recipient_actor_id=?)
                             OR (proposer_actor_id=? AND recipient_actor_id=?)) ORDER BY id DESC LIMIT 4""", (a, b, b, a)):
        purpose = _loads(r["terms_json"]).get("purpose")
        who = "they proposed" if int(r["proposer_actor_id"]) == a else "the followed character proposed"
        due = f", answer due day {r['response_due_day']}" if r["response_due_day"] is not None else ""
        out.append(f"pending {r['interaction_type']} ({who}{due})" + (f": {purpose}" if purpose else ""))
    return out


def _history(conn: sqlite3.Connection, a: int, b: int) -> list[str]:
    rows = conn.execute("""SELECT day,summary FROM relationship_history
                           WHERE (source_actor_id=? AND target_actor_id=?) OR (source_actor_id=? AND target_actor_id=?)
                           ORDER BY day DESC,id DESC LIMIT 3""", (a, b, b, a)).fetchall()
    return [f"day {r['day']}: {r['summary']}" for r in reversed(rows)]


# Words in names that are titles or ordinary words, not a way of addressing that particular person.
_NAME_NOISE = {"the", "and", "for", "from", "with", "old", "young", "lady", "lord", "sir", "dame", "mother", "father",
               "brother", "sister", "elder", "master", "head", "house", "clan", "sect", "son", "daughter", "demo"}


def likely_speakers(conn: sqlite3.Connection, player_id: int, present: Iterable[dict[str, Any]], request_text: str = "",
                    *, limit: int = 3) -> list[int]:
    """Who is likely to talk in this scene: people named in the request, people with open dealings or
    history with the followed character, and people whose work is to address strangers."""
    words = set(re.findall(r"[a-z][a-z'-]*", (request_text or "").lower()))
    scored = []
    for p in present:
        if p.get("actor_type") != "character":
            continue
        aid, score = int(p["id"]), 0.0
        # Being addressed by any part of their name outranks everything else (dealings plus history score ~10).
        if words & {t for t in re.findall(r"[a-z][a-z'-]*", str(p["name"]).lower()) if len(t) >= 3 and t not in _NAME_NOISE}:
            score += 20
        if _dealings(conn, aid, player_id):
            score += 4
        rel = conn.execute("SELECT familiarity FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (aid, player_id)).fetchone()
        if rel:
            score += 1 + float(rel["familiarity"]) / 25.0
        sub = str(p.get("subtype") or "").lower()
        if any(k in sub for k in ("innkeeper", "guard", "clerk", "merchant", "steward", "official", "trader", "servant")):
            score += 1
        if score > 0:
            scored.append((-score, aid))
    return [aid for _, aid in sorted(scored)[:limit]]


def speaker_card(conn: sqlite3.Connection, player_id: int, actor_id: int, day: int) -> dict[str, Any]:
    actor = conn.execute("SELECT name,subtype FROM actors WHERE id=?", (int(actor_id),)).fetchone()
    words, standing = _role_text(conn, actor_id, actor["subtype"])
    stage = _stage(conn, actor_id)
    cls = role_class(words, has_stage=bool(stage))
    age, sex, life_stage = _age(conn, actor_id, day)
    rel = conn.execute("SELECT * FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(actor_id), int(player_id))).fetchone()
    familiarity, demeanour = _bands(rel)
    manner = mannerisms(conn, actor_id, cls, life_stage, day)
    return {
        "name": actor["name"],
        "pronoun": {"female": "she", "male": "he"}.get(str(sex), "they"),
        "age": age,
        "role": public_role(actor["subtype"]),
        "visible_standing": standing,
        "toward_followed_character": {"familiarity": familiarity, "demeanour": demeanour},
        "shared_history": _history(conn, actor_id, player_id),
        "open_dealings": _dealings(conn, actor_id, player_id),
        "temperament": temperament(conn, actor_id),
        "mannerisms": manner["mannerisms"],
        "speech": manner["speech"],
    }


def build_speaker_cards(conn: sqlite3.Connection, player_id: int, present: list[dict[str, Any]], request_text: str,
                        day: int, *, limit: int = 3) -> list[dict[str, Any]]:
    return [speaker_card(conn, player_id, aid, day) for aid in likely_speakers(conn, player_id, present, request_text, limit=limit)]


SPEAKER_RULE = ("Voice the people in speakers from their cards: keep each one's mannerisms and speech consistent, show "
                "temperament through behaviour and words (never state it as a trait), let demeanour and familiarity "
                "shape how they treat the followed character, and let them refer only to the shared_history and "
                "open_dealings listed. They may not promise, agree, threaten or offer anything beyond open_dealings; "
                "new commitments come from the engine, not from prose.")
