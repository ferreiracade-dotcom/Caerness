from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any, Callable

from .business import commercial_context, configure_enterprise_business
from .civilian import create_enterprise


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _seed(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _location(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _institution(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _ensure_book_enterprise(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    location_id: int,
    institution_actor_id: int | None,
) -> int:
    row = conn.execute(
        "SELECT id FROM civilian_enterprises WHERE json_extract(metadata_json,'$.activation_key')=? LIMIT 1",
        (key,),
    ).fetchone()
    if row:
        eid = int(row[0])
    else:
        eid = create_enterprise(
            conn,
            name,
            "service",
            institution_actor_id=institution_actor_id,
            location_id=location_id,
            capital=55,
            cash=30,
            debt=0,
            reputation=55,
            admin_quality=58,
            labor_capacity=45,
            risk_tolerance=58,
            metadata={
                "activation_key": key,
                "authority": "CAMPAIGN_CALIBRATION",
                "resolution": "AGGREGATE_BOOKMAKING_FOOTPRINT",
                "does_not_mean": "one literal named bookmaker or monopoly over local wagering",
            },
        )
    configure_enterprise_business(
        conn,
        eid,
        "gambling_house",
        quality=58,
        price_position=50,
        capacity=58,
        clientele_fit=65,
        service_reliability=75,
        regulatory_pressure=30,
        cadence_days=30,
        metadata={"authority": "CAMPAIGN_CALIBRATION", "activation_key": key},
    )
    return eid


def _ensure_latent_pool(conn: sqlite3.Connection, market_key: str, location_id: int, pool_size: int, day: int) -> int:
    row = conn.execute(
        "SELECT id FROM latent_entities WHERE latent_kind='prizefighter_pool' AND json_extract(constraints_json,'$.market_key')=? AND status IN ('latent','partially_crystallized') ORDER BY id LIMIT 1",
        (market_key,),
    ).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        """INSERT INTO latent_entities(
               latent_kind,archetype,location_id,count_estimate,constraints_json,historical_context_json,status,created_day,updated_day,notes
           ) VALUES ('prizefighter_pool','closed_core_professional_prizefighters',?,?,?,?,'latent',?,?,?)""",
        (
            location_id,
            pool_size,
            json.dumps(
                {
                    "market_key": market_key,
                    "core_state": "Closed-Core",
                    "age_range": [18, 45],
                    "career_domain": "prizefighting",
                    "named_identity_policy": "remain structural until durable causal significance requires promotion",
                },
                sort_keys=True,
            ),
            json.dumps(
                {
                    "authority": "WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION",
                    "meaning": "low-resolution professional population, not a named roster",
                },
                sort_keys=True,
            ),
            day,
            day,
            "Structural Closed-Core prizefighter pool. No individual biography exists merely because cards run.",
        ),
    )
    return int(cur.lastrowid)


def activate_spectacle_substrate(conn: sqlite3.Connection) -> dict[str, int]:
    """Activate ordinary betting/prizefighting without implying that vice is automatically criminal.

    Red Board entries are aggregate local commercial footprints of the canon network; independent
    books are deliberately included so the Board never becomes a universal monopoly. Prize halls are
    structural local markets populated by latent Closed-Core professionals, not invented named adults.
    """
    day = _day(conn)
    red = _institution(conn, "Red Board")
    book_specs = [
        ("red-board-cairnholt", "Red Board — Cairnholt aggregate books", "Cairnholt", red, "network_branch", "licensed", 84, 78, 0.07),
        ("red-board-toll", "Red Board — Toll’s Reach aggregate books", "Toll’s Reach", red, "network_branch", "mixed", 74, 80, 0.09),
        ("independent-cairnholt-books", "Independent Cairnholt books — aggregate market", "Cairnholt", None, "independent_market", "tolerated", 78, 62, 0.08),
        ("independent-waymeet-books", "Independent Waymeet books — aggregate market", "Waymeet", None, "independent_market", "tolerated", 76, 58, 0.08),
        ("independent-aldergate-books", "Independent Aldergate books — aggregate market", "Aldergate", None, "independent_market", "licensed", 82, 70, 0.07),
    ]
    books_created = 0
    for key, name, loc_name, inst, kind, legal, rel, info, margin in book_specs:
        lid = _location(conn, loc_name)
        if lid is None:
            continue
        ekey = f"v036-book-{key}"
        eid = _ensure_book_enterprise(conn, ekey, name, lid, inst)
        existed = conn.execute("SELECT 1 FROM spectacle_books WHERE book_key=?", (key,)).fetchone()
        conn.execute(
            """INSERT INTO spectacle_books(book_key,name,institution_actor_id,enterprise_id,location_id,book_kind,legal_profile,reliability,information_quality,margin_rate,status,metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,'active',?)
               ON CONFLICT(book_key) DO UPDATE SET enterprise_id=excluded.enterprise_id,location_id=excluded.location_id,
                   institution_actor_id=excluded.institution_actor_id,reliability=excluded.reliability,information_quality=excluded.information_quality,
                   margin_rate=excluded.margin_rate,status='active'""",
            (
                key,
                name,
                inst,
                eid,
                lid,
                kind,
                legal,
                rel,
                info,
                margin,
                json.dumps(
                    {
                        "authority": "CAMPAIGN_CALIBRATION",
                        "canon_basis": "Red Board/ordinary legal and gray books exist; local branch census is intentionally aggregate",
                        "not_crime_by_default": True,
                    },
                    sort_keys=True,
                ),
            ),
        )
        if not existed:
            books_created += 1

    market_specs = [
        ("cairnholt-prize-halls", "Cairnholt licensed prize-hall market", "Cairnholt", "licensed", 30, 24, 18),
        ("toll-prize-halls", "Toll’s Reach tolerated prize-hall market", "Toll’s Reach", "tolerated", 28, 28, 14),
        ("aldergate-prize-halls", "Aldergate licensed prize-hall market", "Aldergate", "licensed", 35, 20, 22),
    ]
    prize_markets_created = 0
    latent_pools_created = 0
    for key, name, loc_name, legality, cadence, pool_size, offset in market_specs:
        lid = _location(conn, loc_name)
        if lid is None:
            continue
        existing_pool = conn.execute(
            "SELECT id FROM latent_entities WHERE latent_kind='prizefighter_pool' AND json_extract(constraints_json,'$.market_key')=? LIMIT 1",
            (key,),
        ).fetchone()
        pool = _ensure_latent_pool(conn, key, lid, pool_size, day)
        if not existing_pool:
            latent_pools_created += 1
        existed = conn.execute("SELECT 1 FROM prizefight_markets WHERE market_key=?", (key,)).fetchone()
        conn.execute(
            """INSERT INTO prizefight_markets(
                   market_key,name,location_id,market_kind,legality,coercion_profile,cadence_days,next_card_day,latent_pool_id,pool_size,public_form,injury_load,status,metadata_json
               ) VALUES (?,?,?,'prize_hall',?,'voluntary',?,?,?,?,50,5,'active',?)
               ON CONFLICT(market_key) DO UPDATE SET location_id=excluded.location_id,latent_pool_id=excluded.latent_pool_id,
                   pool_size=excluded.pool_size,status='active'""",
            (
                key,
                name,
                lid,
                legality,
                cadence,
                day + offset,
                pool,
                pool_size,
                json.dumps(
                    {
                        "authority": "CAMPAIGN_CALIBRATION",
                        "canon_basis": "professional Closed-Core prize halls with referees, purses and medical supervision",
                        "coercive_pit_logic": False,
                        "structural_population": True,
                    },
                    sort_keys=True,
                ),
            ),
        )
        if not existed:
            prize_markets_created += 1
    return {
        "spectacle_books": int(conn.execute("SELECT COUNT(*) FROM spectacle_books WHERE status='active'").fetchone()[0]),
        "spectacle_books_created": books_created,
        "prizefight_markets": int(conn.execute("SELECT COUNT(*) FROM prizefight_markets WHERE status='active'").fetchone()[0]),
        "prizefight_markets_created": prize_markets_created,
        "prizefighter_latent_pools_created": latent_pools_created,
    }


def _public_rating(conn: sqlite3.Connection, actor_id: int) -> float:
    rows = conn.execute(
        "SELECT value FROM social_reputation WHERE subject_kind='actor' AND subject_id=? AND domain IN ('martial_spectacle','tournament','martial_public')",
        (actor_id,),
    ).fetchall()
    rep = sum(float(r[0]) for r in rows) / len(rows) if rows else 50.0
    wins = int(conn.execute("SELECT COUNT(*) FROM tournament_bouts WHERE status='resolved' AND winner_actor_id=?", (actor_id,)).fetchone()[0])
    losses = int(
        conn.execute(
            "SELECT COUNT(*) FROM tournament_bouts WHERE status='resolved' AND winner_actor_id IS NOT NULL AND (actor_a_id=? OR actor_b_id=?) AND winner_actor_id<>?",
            (actor_id, actor_id, actor_id),
        ).fetchone()[0]
    )
    return _clamp(rep + wins * 3.5 - losses * 1.5, 10, 90)


def _market_prob_from_public(a: float, b: float, *, noise: float = 0.0) -> float:
    x = (float(a) - float(b)) / 14.0 + float(noise)
    p = 1.0 / (1.0 + math.exp(-x))
    return _clamp(p, 0.08, 0.92)


def _odds(prob_a: float, margin: float) -> tuple[float, float]:
    # Overround is the bookmaker margin; odds encode market belief, not engine truth.
    over = 1.0 + max(0.0, float(margin))
    implied_a = _clamp(prob_a * over, 0.03, 0.97)
    implied_b = _clamp((1.0 - prob_a) * over, 0.03, 0.97)
    return round(max(1.01, 1.0 / implied_a), 3), round(max(1.01, 1.0 / implied_b), 3)


def _handle_for(conn: sqlite3.Connection, location_id: int, source_kind: str, book_id: int, source_id: int) -> tuple[float, float]:
    ctx = commercial_context(conn, location_id)
    base = 8.0 + ctx["foot_traffic"] * 0.12 + ctx["event_activity"] * 0.18 + ctx["disposable_income"] * 0.08
    if source_kind == "tournament_bout":
        base *= 1.35
    rng = random.Random(_seed(conn) + book_id * 10007 + source_id * 97 + (17 if source_kind == "tournament_bout" else 41))
    return round(max(4.0, base * rng.uniform(0.75, 1.25)), 2), rng.uniform(-0.08, 0.08)


def _open_market(
    conn: sqlite3.Connection,
    book: sqlite3.Row,
    *,
    source_kind: str,
    source_id: int,
    location_id: int,
    opened_day: int,
    close_day: int,
    outcome_a_key: str,
    outcome_b_key: str,
    public_a: float,
    public_b: float,
) -> int:
    key = f"{book['book_key']}:{source_kind}:{source_id}"
    row = conn.execute("SELECT id FROM betting_markets WHERE market_key=?", (key,)).fetchone()
    if row:
        return int(row[0])
    noise_scale = max(0.0, (100.0 - float(book["information_quality"])) / 100.0 * 0.35)
    rng = random.Random(_seed(conn) + int(book["id"]) * 7919 + source_id * 131)
    p = _market_prob_from_public(public_a, public_b, noise=rng.uniform(-noise_scale, noise_scale))
    odds_a, odds_b = _odds(p, float(book["margin_rate"]))
    handle, bet_noise = _handle_for(conn, location_id, source_kind, int(book["id"]), source_id)
    stake_share_a = _clamp(p + bet_noise, 0.12, 0.88)
    cur = conn.execute(
        """INSERT INTO betting_markets(
               market_key,book_id,source_kind,source_id,location_id,opened_day,close_day,status,outcome_a_key,outcome_b_key,
               public_probability_a,decimal_odds_a,decimal_odds_b,handle,stake_share_a,metadata_json
           ) VALUES (?,?,?,?,?,?,?,'open',?,?,?,?,?,?,?,?)""",
        (
            key,
            int(book["id"]),
            source_kind,
            source_id,
            location_id,
            opened_day,
            max(opened_day, close_day),
            outcome_a_key,
            outcome_b_key,
            p,
            odds_a,
            odds_b,
            handle,
            stake_share_a,
            json.dumps(
                {
                    "authority": "ENGINE_DERIVED",
                    "odds_basis": "public reputation/form plus book-specific information noise; hidden combat capability is not read",
                    "aggregate_bettors": True,
                    "credit_betting": False,
                },
                sort_keys=True,
            ),
        ),
    )
    return int(cur.lastrowid)


def _discover_tournament_books(conn: sqlite3.Connection, day: int) -> int:
    created = 0
    bouts = conn.execute(
        """SELECT tb.*,te.location_id FROM tournament_bouts tb
           JOIN tournament_events te ON te.id=tb.event_id
           WHERE tb.status IN ('scheduled','active') AND tb.winner_actor_id IS NULL"""
    ).fetchall()
    for bout in bouts:
        lid = int(bout["location_id"])
        books = conn.execute("SELECT * FROM spectacle_books WHERE location_id=? AND status='active' ORDER BY id", (lid,)).fetchall()
        if not books:
            continue
        a, b = int(bout["actor_a_id"]), int(bout["actor_b_id"])
        pa, pb = _public_rating(conn, a), _public_rating(conn, b)
        for book in books:
            key = f"{book['book_key']}:tournament_bout:{int(bout['id'])}"
            if conn.execute("SELECT 1 FROM betting_markets WHERE market_key=?", (key,)).fetchone():
                continue
            _open_market(
                conn,
                book,
                source_kind="tournament_bout",
                source_id=int(bout["id"]),
                location_id=lid,
                opened_day=day,
                close_day=int(bout["scheduled_day"]),
                outcome_a_key=f"actor:{a}",
                outcome_b_key=f"actor:{b}",
                public_a=pa,
                public_b=pb,
            )
            created += 1
    return created


def _schedule_prize_card(conn: sqlite3.Connection, market: sqlite3.Row, day: int) -> tuple[int, int]:
    rng = random.Random(_seed(conn) + int(market["id"]) * 1009 + day * 31)
    ctx = commercial_context(conn, int(market["location_id"]))
    attendance = _clamp(35 + ctx["foot_traffic"] * 0.3 + ctx["event_activity"] * 0.25 + rng.uniform(-8, 8), 20, 95)
    bouts = max(3, min(7, int(round(3 + attendance / 30))))
    purse = round(8 + attendance * 0.32 + rng.uniform(0, 8), 2)
    base = float(market["public_form"])
    incumbent = int(market["champion_streak"]) > 0
    public_a = _clamp(base + (6 if incumbent else 0) + rng.uniform(-7, 7), 20, 85)
    public_b = _clamp(base + rng.uniform(-8, 8), 20, 85)
    # True form is separate from public form, so the market can be wrong without reading hidden named capability.
    true_a = _clamp(public_a + rng.uniform(-12, 12) - float(market["injury_load"]) * 0.05, 15, 90)
    true_b = _clamp(public_b + rng.uniform(-12, 12) - float(market["injury_load"]) * 0.04, 15, 90)
    resolve_day = day + 3
    cur = conn.execute(
        """INSERT OR IGNORE INTO prizefight_cards(market_id,scheduled_day,status,bout_count,attendance_index,gross_purse,metadata_json)
           VALUES (?,?,'scheduled',?,?,?,?)""",
        (
            int(market["id"]),
            resolve_day,
            bouts,
            attendance,
            purse,
            json.dumps(
                {
                    "authority": "ENGINE_DERIVED",
                    "incumbent_champion_present": incumbent,
                    "main_event_public_form_a": public_a,
                    "main_event_public_form_b": public_b,
                    "main_event_true_form_a": true_a,
                    "main_event_true_form_b": true_b,
                    "structural_fighters": True,
                },
                sort_keys=True,
            ),
        ),
    )
    card_id = int(cur.lastrowid or conn.execute("SELECT id FROM prizefight_cards WHERE market_id=? AND scheduled_day=?", (market["id"], resolve_day)).fetchone()[0])
    books = conn.execute("SELECT * FROM spectacle_books WHERE location_id=? AND status='active' ORDER BY id", (market["location_id"],)).fetchall()
    opened = 0
    for book in books:
        key = f"{book['book_key']}:prizefight_card:{card_id}"
        if conn.execute("SELECT 1 FROM betting_markets WHERE market_key=?", (key,)).fetchone():
            continue
        _open_market(
            conn,
            book,
            source_kind="prizefight_card",
            source_id=card_id,
            location_id=int(market["location_id"]),
            opened_day=day,
            close_day=resolve_day,
            outcome_a_key="structural:incumbent_or_side_a",
            outcome_b_key="structural:challenger_or_side_b",
            public_a=public_a,
            public_b=public_b,
        )
        opened += 1
    conn.execute("UPDATE prizefight_markets SET next_card_day=? WHERE id=?", (day + int(market["cadence_days"]), market["id"]))
    return card_id, opened


def _maybe_promote_champion(conn: sqlite3.Connection, market: sqlite3.Row, day: int, profile: dict[str, Any]) -> int | None:
    streak = int(profile.get("streak") or 0)
    if streak < 4:
        return None
    existing = profile.get("latent_entity_id")
    if existing and conn.execute("SELECT 1 FROM latent_entities WHERE id=?", (int(existing),)).fetchone():
        return int(existing)
    cur = conn.execute(
        """INSERT INTO latent_entities(
               latent_kind,archetype,location_id,count_estimate,constraints_json,historical_context_json,status,created_day,updated_day,notes
           ) VALUES ('person','closed_core_prizefighter_champion',?,1,?,?,'latent',?,?,?)""",
        (
            int(market["location_id"]),
            json.dumps(
                {
                    "age_range": [20, 40],
                    "core_state": "Closed-Core",
                    "career_domain": "prizefighting",
                    "market_id": int(market["id"]),
                    "identity_status": "unnamed latent individual; crystallize only when causally required",
                },
                sort_keys=True,
            ),
            json.dumps(
                {
                    "emerged_from_structural_prizefighting": True,
                    "champion_streak": streak,
                    "cards_through_day": day,
                    "public_form": profile.get("public_form"),
                    "source_market": market["market_key"],
                },
                sort_keys=True,
            ),
            day,
            day,
            "Promoted from aggregate prizefighter pool after durable repeated success; still unnamed and low-resolution.",
        ),
    )
    return int(cur.lastrowid)


def _resolve_prize_card(conn: sqlite3.Connection, card: sqlite3.Row, day: int) -> dict[str, int]:
    market = conn.execute("SELECT * FROM prizefight_markets WHERE id=?", (card["market_id"],)).fetchone()
    meta = _loads(card["metadata_json"], {})
    rng = random.Random(_seed(conn) + int(card["id"]) * 1543 + day * 43)
    count = int(card["bout_count"])
    main_winner = "A"
    avg_injury = 0.0
    for idx in range(1, count + 1):
        if idx == count:
            pa, pb = float(meta["main_event_public_form_a"]), float(meta["main_event_public_form_b"])
            ta, tb = float(meta["main_event_true_form_a"]), float(meta["main_event_true_form_b"])
        else:
            base = float(market["public_form"])
            pa, pb = _clamp(base + rng.uniform(-12, 12), 15, 88), _clamp(base + rng.uniform(-12, 12), 15, 88)
            ta, tb = _clamp(pa + rng.uniform(-13, 13), 10, 92), _clamp(pb + rng.uniform(-13, 13), 10, 92)
        p = _market_prob_from_public(ta, tb, noise=rng.uniform(-0.45, 0.45))
        winner = "A" if rng.random() < p else "B"
        closeness = 1.0 - min(1.0, abs(ta - tb) / 45.0)
        inj_a = _clamp(rng.uniform(1, 9) + closeness * rng.uniform(0, 8) + (4 if winner == "B" else 0), 0, 35)
        inj_b = _clamp(rng.uniform(1, 9) + closeness * rng.uniform(0, 8) + (4 if winner == "A" else 0), 0, 35)
        avg_injury += inj_a + inj_b
        conn.execute(
            "INSERT INTO prizefight_bouts(card_id,bout_index,public_form_a,public_form_b,true_form_a,true_form_b,winner_side,injury_a,injury_b,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                card["id"], idx, pa, pb, ta, tb, winner, inj_a, inj_b,
                json.dumps({"structural_fighters": True, "no_current_or_aura": True, "medical_supervision": True}, sort_keys=True),
            ),
        )
        if idx == count:
            main_winner = winner
    avg_injury = avg_injury / max(1, count * 2)
    old_profile = _loads(market["champion_profile_json"], {})
    incumbent = bool(meta.get("incumbent_champion_present"))
    if incumbent and main_winner == "A":
        streak = int(market["champion_streak"]) + 1
        profile = dict(old_profile)
    else:
        streak = 1
        profile = {}
    winning_public = float(meta["main_event_public_form_a"] if main_winner == "A" else meta["main_event_public_form_b"])
    profile.update({"streak": streak, "public_form": round(winning_public, 2), "last_win_day": day, "last_card_id": int(card["id"])})
    # Losing a previously promoted champion does not erase that person's historical latent identity,
    # but the new incumbent begins as aggregate again.
    if not (incumbent and main_winner == "A"):
        profile.pop("latent_entity_id", None)
    latent_id = _maybe_promote_champion(conn, market, day, profile)
    if latent_id:
        profile["latent_entity_id"] = latent_id
    new_form = _clamp(float(market["public_form"]) * 0.88 + winning_public * 0.12, 20, 85)
    new_injury = _clamp(float(market["injury_load"]) * 0.82 + avg_injury * 0.55, 0, 70)
    card_meta = dict(meta)
    card_meta["main_event_winner_side"] = main_winner
    card_meta["champion_streak_after"] = streak
    if latent_id:
        card_meta["promoted_latent_champion_id"] = latent_id
    conn.execute(
        "UPDATE prizefight_cards SET status='resolved',resolved_day=?,metadata_json=? WHERE id=?",
        (day, json.dumps(card_meta, sort_keys=True), card["id"]),
    )
    conn.execute(
        "UPDATE prizefight_markets SET public_form=?,injury_load=?,champion_streak=?,champion_profile_json=? WHERE id=?",
        (new_form, new_injury, streak, json.dumps(profile, sort_keys=True), market["id"]),
    )
    return {"cards_resolved": 1, "prizefight_bouts_resolved": count, "latent_champions_promoted": 1 if latent_id and not old_profile.get("latent_entity_id") else 0}


def _winner_key(conn: sqlite3.Connection, market: sqlite3.Row) -> str | None:
    if market["source_kind"] == "tournament_bout":
        row = conn.execute("SELECT status,winner_actor_id FROM tournament_bouts WHERE id=?", (market["source_id"],)).fetchone()
        if not row or row["status"] != "resolved" or row["winner_actor_id"] is None:
            return None
        return f"actor:{int(row['winner_actor_id'])}"
    row = conn.execute("SELECT status,metadata_json FROM prizefight_cards WHERE id=?", (market["source_id"],)).fetchone()
    if not row or row["status"] != "resolved":
        return None
    side = _loads(row["metadata_json"], {}).get("main_event_winner_side")
    if side == "A":
        return str(market["outcome_a_key"])
    if side == "B":
        return str(market["outcome_b_key"])
    return None


def _settle_market(conn: sqlite3.Connection, market: sqlite3.Row, day: int) -> bool:
    winner = _winner_key(conn, market)
    if winner is None:
        return False
    handle = float(market["handle"])
    share_a = float(market["stake_share_a"])
    if winner == str(market["outcome_a_key"]):
        payout = handle * share_a * float(market["decimal_odds_a"])
    else:
        payout = handle * (1.0 - share_a) * float(market["decimal_odds_b"])
    payout = round(max(0.0, payout), 2)
    result = round(handle - payout, 2)
    conn.execute(
        "UPDATE betting_markets SET status='settled',settled_day=?,payout=?,book_result=? WHERE id=?",
        (day, payout, result, market["id"]),
    )
    book = conn.execute("SELECT * FROM spectacle_books WHERE id=?", (market["book_id"],)).fetchone()
    if book and book["enterprise_id"] is not None:
        eid = int(book["enterprise_id"])
        conn.execute("UPDATE civilian_enterprises SET cash=cash+?,updated_day=? WHERE id=?", (result, day, eid))
        if result >= 0:
            conn.execute(
                "INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,source_kind,source_id) VALUES (?,?,'revenue',?,?,?,?)",
                (eid, day, result, "Aggregate settled wagering result", "betting_market", market["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,source_kind,source_id) VALUES (?,?,'loss',?,?,?,?)",
                (eid, day, abs(result), "Aggregate settled wagering loss", "betting_market", market["id"]),
            )
    return True


def next_spectacle_due_day(conn: sqlite3.Connection, after_day: int, until_day: int) -> int | None:
    vals: list[int] = []
    queries = [
        ("SELECT MIN(next_card_day) FROM prizefight_markets WHERE status='active' AND next_card_day>? AND next_card_day<=?", (after_day, until_day)),
        ("SELECT MIN(scheduled_day) FROM prizefight_cards WHERE status='scheduled' AND scheduled_day>? AND scheduled_day<=?", (after_day, until_day)),
    ]
    for q, args in queries:
        r = conn.execute(q, args).fetchone()[0]
        if r is not None:
            vals.append(int(r))
    # Open tournament markets do not need an independent high-frequency poll: tournament checkpoints
    # drive their source state and this process runs immediately after the tournament resolver.
    return min(vals) if vals else None


def process_due_spectacle(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    out = {
        "prizefight_markets_due": 0,
        "cards_scheduled": 0,
        "cards_resolved": 0,
        "prizefight_bouts_resolved": 0,
        "betting_markets_opened": 0,
        "betting_markets_settled": 0,
        "latent_champions_promoted": 0,
    }
    # First open any real tracked tournament books that have a currently bettable bout.
    out["betting_markets_opened"] += _discover_tournament_books(conn, day)
    for market in conn.execute("SELECT * FROM prizefight_markets WHERE status='active' AND next_card_day<=? ORDER BY id", (day,)).fetchall():
        out["prizefight_markets_due"] += 1
        card_id, opened = _schedule_prize_card(conn, market, int(market["next_card_day"]))
        out["cards_scheduled"] += 1
        out["betting_markets_opened"] += opened
        if event_logger:
            event_logger(
                day=day,
                event_type="prizefight_card_scheduled",
                title=str(market["name"]),
                summary=f"A structural professional Closed-Core fight card was scheduled at {market['name']}; fighters remain latent unless durable significance promotes one.",
                severity=1,
                location_id=int(market["location_id"]),
            )
    for card in conn.execute("SELECT * FROM prizefight_cards WHERE status='scheduled' AND scheduled_day<=? ORDER BY id", (day,)).fetchall():
        r = _resolve_prize_card(conn, card, day)
        for k, v in r.items():
            out[k] += v
        if event_logger:
            market = conn.execute("SELECT * FROM prizefight_markets WHERE id=?", (card["market_id"],)).fetchone()
            event_logger(
                day=day,
                event_type="prizefight_card",
                title=str(market["name"]),
                summary=f"A professional Closed-Core fight card resolved with {int(card['bout_count'])} structural bouts under local prize-hall rules.",
                severity=1,
                location_id=int(market["location_id"]),
            )
    # Settle only after the underlying contest actually resolves. Aggregate bettors are outside the
    # named-person balance sheet, so only the book's net result enters tracked enterprise cash.
    for bm in conn.execute("SELECT * FROM betting_markets WHERE status='open' ORDER BY id").fetchall():
        if _settle_market(conn, bm, day):
            out["betting_markets_settled"] += 1
    return out
