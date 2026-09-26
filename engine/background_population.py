from __future__ import annotations

"""POPBACK-01 bounded background identity partitions.

Authority model
---------------
SCALE-01 owns the 52m population denominator through disjoint regional buckets.
``background_population_sources`` is an exact operational decomposition of those buckets:
59 named-settlement sources plus residual rural/structural-urban sources.  The source rows
sum to the SCALE-01 world population and do not create additional people.

A background partition is a bounded, persistent identity sample from exactly one disjoint
source.  It exists only to give ordinary people stable identity before they become important.
The partition's sample_size is NEVER added to source or world population totals.

Implementation pattern
----------------------
The compact state borrows the useful part of Starsim's People/Arr architecture: stable raw
slots plus a smaller active-UID view.  Caerness owns the resolution and persistence semantics.
SQLite stores source/partition metadata, audit links and the serialized checkpoint; NumPy owns
the high-volume in-memory state.
"""

import hashlib
import io
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

import numpy as np

_CODEC = "caerness_numpy_npz_v1"
_U64_MASK = (1 << 64) - 1

# Working demographic calibration inherited from the existing campaign bootstrap.  Applying
# it to POPBACK sources is explicitly a simulation assumption, not setting canon.
_AGE_BANDS: tuple[tuple[str, float, int, int], ...] = (
    ("0_4", .12, 0, 5 * 365 - 1),
    ("5_12", .18, 5 * 365, 13 * 365 - 1),
    ("13_17", .10, 13 * 365, 18 * 365 - 1),
    ("18_39", .31, 18 * 365, 40 * 365 - 1),
    ("40_59", .20, 40 * 365, 60 * 365 - 1),
    ("60_plus", .09, 60 * 365, 85 * 365),
)


def _j(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, ensure_ascii=False)


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _splitmix64(x: np.ndarray) -> np.ndarray:
    z = x.astype(np.uint64, copy=False) + np.uint64(0x9E3779B97F4A7C15)
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return z ^ (z >> np.uint64(31))


def _draw(uid: np.ndarray, step_index: int, stream: int, seed: int) -> np.ndarray:
    salt1 = (step_index * 0xD1B54A32D192ED03) & _U64_MASK
    salt2 = (stream * 0x94D049BB133111EB) & _U64_MASK
    x = uid.astype(np.uint64, copy=False) ^ np.uint64(seed & _U64_MASK) ^ np.uint64(salt1) ^ np.uint64(salt2)
    z = _splitmix64(x)
    return ((z >> np.uint64(11)).astype(np.float64)) * (1.0 / (1 << 53))


def _mortality_probability(age_days: np.ndarray) -> np.ndarray:
    from .health import FIRST_YEAR_MORTALITY, DEFAULT_COHORT_MORTALITY as C
    age = age_days / 365.2425
    # Childhood follows the world's premodern demography (DEMO-04), exactly as named children do.
    annual = np.where(
        age < 1, FIRST_YEAR_MORTALITY,
        np.where(age < 5, C['0_4'],
        np.where(age < 13, C['5_12'],
        np.where(age < 15, C['13_17'],
        np.where(age < 50, 0.0018,
        np.where(age < 65, 0.009,
        np.where(age < 75, 0.03, 0.085)))))),
    )
    return annual / 12.0


@dataclass
class PartitionState:
    uid: np.ndarray
    age_days: np.ndarray
    alive: np.ndarray
    demographic_sex: np.ndarray
    exposure_score: np.ndarray
    active_uids: np.ndarray

    @property
    def sample_size(self) -> int:
        return int(self.uid.size)

    @property
    def state_bytes(self) -> int:
        return int(sum(getattr(self, name).nbytes for name in self.__dataclass_fields__))

    def snapshot(self, local_uid: int) -> dict[str, Any]:
        slot = int(local_uid) - 1
        if slot < 0 or slot >= self.sample_size or int(self.uid[slot]) != int(local_uid):
            raise KeyError(f"Unknown local background uid {local_uid}")
        return {
            "local_uid": int(self.uid[slot]),
            "age_days": int(self.age_days[slot]),
            "alive": bool(self.alive[slot]),
            "demographic_sex": "female" if int(self.demographic_sex[slot]) == 1 else "male",
            "exposure_score": float(self.exposure_score[slot]),
        }


def _encode(state: PartitionState) -> tuple[bytes, str]:
    buf = io.BytesIO()
    np.savez(
        buf,
        uid=state.uid,
        age_days=state.age_days,
        alive=state.alive,
        demographic_sex=state.demographic_sex,
        exposure_score=state.exposure_score,
        active_uids=state.active_uids,
    )
    raw = buf.getvalue()
    return raw, hashlib.sha256(raw).hexdigest()


def _decode(raw: bytes, expected_sha256: str | None = None) -> PartitionState:
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and digest != str(expected_sha256):
        raise ValueError("Background population partition checksum mismatch")
    with np.load(io.BytesIO(raw), allow_pickle=False) as z:
        return PartitionState(**{name: z[name] for name in PartitionState.__dataclass_fields__})


def _age_cohorts_exist(conn: sqlite3.Connection, source_id: int) -> bool:
    try:
        return bool(conn.execute("SELECT 1 FROM background_population_age_cohorts WHERE source_id=? LIMIT 1", (source_id,)).fetchone())
    except sqlite3.OperationalError:
        return False


def _upsert_population_source(conn: sqlite3.Connection, *, source_key: str, source_kind: str, bucket_key: str,
                              location_id: int | None, opening_population: int, urban: int,
                              metadata: dict[str, Any]) -> int:
    row = conn.execute("SELECT id,population_estimate FROM background_population_sources WHERE source_key=?", (source_key,)).fetchone()
    if row is None:
        cur = conn.execute(
            """INSERT INTO background_population_sources(
                 source_key,source_kind,bucket_key,location_id,population_estimate,urban,calibration_status,metadata_json,baseline_population_estimate)
               VALUES (?,?,?,?,?,?,'CAMPAIGN_CALIBRATION',?,?)""",
            (source_key, source_kind, bucket_key, location_id, int(opening_population), int(urban), _j(metadata), int(opening_population)),
        )
        return int(cur.lastrowid)
    sid = int(row['id'])
    live = _age_cohorts_exist(conn, sid)
    # Once POPLIFE has live state, ordinary re-activation must never reset history to the
    # opening calibration. Baseline may be refreshed only as metadata; current population remains causal.
    if live:
        conn.execute(
            """UPDATE background_population_sources SET source_kind=?,bucket_key=?,location_id=?,urban=?,
                 calibration_status='CAMPAIGN_CALIBRATION',metadata_json=?,
                 baseline_population_estimate=COALESCE(baseline_population_estimate,?) WHERE id=?""",
            (source_kind, bucket_key, location_id, int(urban), _j(metadata), int(opening_population), sid),
        )
    else:
        conn.execute(
            """UPDATE background_population_sources SET source_kind=?,bucket_key=?,location_id=?,population_estimate=?,urban=?,
                 calibration_status='CAMPAIGN_CALIBRATION',metadata_json=?,baseline_population_estimate=? WHERE id=?""",
            (source_kind, bucket_key, location_id, int(opening_population), int(urban), _j(metadata), int(opening_population), sid),
        )
    return sid


def activate_population_sources(conn: sqlite3.Connection) -> dict[str, int]:
    """Decompose SCALE-01 into disjoint source pools whose opening total is exactly 52m."""
    for r in conn.execute(
        """SELECT s.location_id,s.bucket_key,s.population_estimate,l.name
           FROM settlement_scale_profiles s JOIN locations l ON l.id=s.location_id ORDER BY s.location_id"""
    ).fetchall():
        _upsert_population_source(
            conn, source_key=f"settlement:{int(r['location_id'])}", source_kind='settlement',
            bucket_key=str(r['bucket_key']), location_id=int(r['location_id']), opening_population=int(r['population_estimate']), urban=1,
            metadata={'authority': 'SCALE01_DERIVED_DISJOINT_SOURCE', 'name': str(r['name'])},
        )

    for b in conn.execute("SELECT * FROM population_scale_buckets ORDER BY bucket_key").fetchall():
        key = str(b['bucket_key'])
        named_urban = int(conn.execute(
            "SELECT COALESCE(SUM(population_estimate),0) FROM settlement_scale_profiles WHERE bucket_key=? AND named_urban=1", (key,),
        ).fetchone()[0])
        structural_urban = int(b['urban_population']) - named_urban
        if structural_urban < 0:
            raise ValueError(f"Named settlement population exceeds SCALE-01 urban population for {key}")
        if structural_urban:
            _upsert_population_source(
                conn, source_key=f'structural_urban:{key}', source_kind='structural_urban', bucket_key=key,
                location_id=None, opening_population=structural_urban, urban=1,
                metadata={'authority': 'SCALE01_DERIVED_DISJOINT_SOURCE', 'exact_location_unresolved': True},
            )
        _upsert_population_source(
            conn, source_key=f'rural:{key}', source_kind='rural_residual', bucket_key=key,
            location_id=None, opening_population=int(b['rural_population']), urban=0,
            metadata={'authority': 'SCALE01_DERIVED_DISJOINT_SOURCE', 'exact_local_distribution_unresolved': True},
        )

    valid_keys = {str(r[0]) for r in conn.execute("SELECT 'settlement:'||location_id FROM settlement_scale_profiles")}
    valid_keys |= {f"rural:{str(r['bucket_key'])}" for r in conn.execute("SELECT bucket_key FROM population_scale_buckets")}
    for r in conn.execute("SELECT bucket_key,urban_population FROM population_scale_buckets"):
        named = int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM settlement_scale_profiles WHERE bucket_key=?", (r['bucket_key'],)).fetchone()[0])
        if int(r['urban_population']) > named:
            valid_keys.add(f"structural_urban:{str(r['bucket_key'])}")
    for r in conn.execute("SELECT id,source_key FROM background_population_sources").fetchall():
        if str(r['source_key']) not in valid_keys:
            if not conn.execute("SELECT 1 FROM background_population_partitions WHERE source_id=?", (int(r['id']),)).fetchone() and not _age_cohorts_exist(conn, int(r['id'])):
                conn.execute("DELETE FROM background_population_sources WHERE id=?", (int(r['id']),))

    baseline_total = int(conn.execute("SELECT COALESCE(SUM(baseline_population_estimate),0) FROM background_population_sources").fetchone()[0])
    scale_total = int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM population_scale_buckets").fetchone()[0])
    if baseline_total != scale_total:
        raise ValueError(f"POPBACK opening decomposition {baseline_total} != SCALE-01 total {scale_total}")
    return {
        'background_population_sources': int(conn.execute("SELECT COUNT(*) FROM background_population_sources").fetchone()[0]),
        'background_population_source_total': int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM background_population_sources").fetchone()[0]),
        'background_population_baseline_total': baseline_total,
    }


def activate_population_life_course(conn: sqlite3.Connection) -> dict[str, int]:
    """Seed six live age bands per disjoint source without creating person rows."""
    from .health import DEFAULT_COHORT_MORTALITY
    day = _day(conn)
    created = dynamics = 0
    for src in conn.execute("SELECT * FROM background_population_sources ORDER BY id").fetchall():
        sid = int(src['id'])
        if not conn.execute("SELECT 1 FROM background_population_age_cohorts WHERE source_id=? LIMIT 1", (sid,)).fetchone():
            total = float(src['population_estimate'])
            allocated = 0.0
            for idx, (band, share, _lo, _hi) in enumerate(_AGE_BANDS):
                # Float populations are intentional aggregate expected counts; final band takes residual exactly.
                pop = total - allocated if idx == len(_AGE_BANDS) - 1 else total * float(share)
                allocated += pop
                conn.execute(
                    """INSERT INTO background_population_age_cohorts(
                         source_id,age_band,population,baseline_population,annual_mortality_rate,last_review_day,metadata_json)
                       VALUES (?,?,?,?,?,?,?)""",
                    (sid, band, pop, pop, float(DEFAULT_COHORT_MORTALITY[band]), day,
                     _j({'authority': 'POPLIFE01_CAMPAIGN_CALIBRATION', 'age_distribution': 'campaign_assumption_v1'})),
                )
                created += 1
        conn.execute(
            """INSERT INTO background_population_dynamics(source_id,annual_birth_rate,health_modifier,last_review_day,status,metadata_json)
               VALUES (?,0.027,1,?,'active',?) ON CONFLICT(source_id) DO NOTHING""",
            (sid, day, _j({'authority': 'POPLIFE01_CAMPAIGN_CALIBRATION', 'birth_rate_basis': 'DEMO04_gross_birth_rate_27_per_thousand'})),
        )
        dynamics += 1
    # Reconcile exact source totals to their seeded live cohorts.
    _reconcile_source_populations(conn)
    return {'population_age_cohorts': created, 'population_dynamics_sources': dynamics}


def _reconcile_source_populations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """UPDATE background_population_sources SET population_estimate=(
             SELECT COALESCE(SUM(c.population),0) FROM background_population_age_cohorts c
             WHERE c.source_id=background_population_sources.id)
           WHERE EXISTS(SELECT 1 FROM background_population_age_cohorts c2 WHERE c2.source_id=background_population_sources.id)"""
    )


def _advance_source_one_year(conn: sqlite3.Connection, source_id: int, step_day: int) -> tuple[float, float, float, float]:
    dyn = conn.execute("SELECT * FROM background_population_dynamics WHERE source_id=?", (source_id,)).fetchone()
    rows = {str(r['age_band']): r for r in conn.execute(
        "SELECT * FROM background_population_age_cohorts WHERE source_id=?", (source_id,)
    ).fetchall()}
    if not dyn or len(rows) != len(_AGE_BANDS):
        return (0.0, 0.0, 0.0, 0.0)
    opening = sum(float(r['population']) for r in rows.values())
    modifier = max(0.0, float(dyn['health_modifier']))
    survivors: dict[str, float] = {}
    deaths = 0.0
    for band, _, _, _ in _AGE_BANDS:
        pop = float(rows[band]['population'])
        rate = max(0.0, min(1.0, float(rows[band]['annual_mortality_rate']) * modifier))
        dead = pop * rate
        survivors[band] = max(0.0, pop - dead)
        deaths += dead

    widths = {'0_4': 5.0, '5_12': 8.0, '13_17': 5.0, '18_39': 22.0, '40_59': 20.0}
    nxt = {'0_4': '5_12', '5_12': '13_17', '13_17': '18_39', '18_39': '40_59', '40_59': '60_plus'}
    closing = {band: survivors[band] for band, *_ in _AGE_BANDS}
    for band, width in widths.items():
        aged = survivors[band] / width
        closing[band] -= aged
        closing[nxt[band]] += aged
    births = opening * max(0.0, min(1.0, float(dyn['annual_birth_rate'])))
    from .health import FIRST_YEAR_MORTALITY
    infant_deaths = births * FIRST_YEAR_MORTALITY
    deaths += infant_deaths
    closing['0_4'] += births - infant_deaths
    for band in closing:
        conn.execute(
            "UPDATE background_population_age_cohorts SET population=?,last_review_day=? WHERE source_id=? AND age_band=?",
            (max(0.0, closing[band]), int(step_day), source_id, band),
        )
    new_total = sum(closing.values())
    conn.execute("UPDATE background_population_sources SET population_estimate=? WHERE id=?", (int(round(new_total)), source_id))
    conn.execute("UPDATE background_population_dynamics SET last_review_day=? WHERE source_id=?", (int(step_day), source_id))
    conn.execute(
        """INSERT OR REPLACE INTO background_population_yearly_balances(
             source_id,period_day,opening_population,births,deaths,movement_net,closing_population,metadata_json)
           VALUES (?,?,?,?,?,0,?,?)""",
        (source_id, int(step_day), opening, births, deaths, new_total,
         _j({'method': 'aggregate_age_band_life_course', 'no_quota_rebalancing': True, 'infant_deaths_share_of_gross_births': 0.10, 'calibration': 'DEMO-04'})),
    )
    return opening, births, deaths, new_total


def process_due_population_life_course(conn: sqlite3.Connection, day: int) -> dict[str, int | float]:
    """Advance every due source in one-year causal increments; never rebalance to SCALE-01."""
    sources = conn.execute(
        "SELECT source_id,last_review_day FROM background_population_dynamics WHERE status='active' AND last_review_day+365<=? ORDER BY source_id",
        (int(day),),
    ).fetchall()
    reviewed = periods = 0
    births = deaths = 0.0
    for r in sources:
        sid = int(r['source_id'])
        last = int(r['last_review_day'])
        did = False
        while last + 365 <= int(day):
            last += 365
            _opening, b, d, _closing = _advance_source_one_year(conn, sid, last)
            births += b; deaths += d; periods += 1; did = True
        if did:
            reviewed += 1
    _reconcile_source_populations(conn)
    return {'sources_reviewed': reviewed, 'source_year_periods': periods, 'births': round(births, 6), 'deaths': round(deaths, 6)}


def next_population_life_course_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row = conn.execute(
        "SELECT MIN(last_review_day+365) FROM background_population_dynamics WHERE status='active' AND last_review_day+365>? AND last_review_day+365<=?",
        (int(after_day), int(end_day)),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def transfer_population(conn: sqlite3.Connection, from_source_id: int, to_source_id: int, population: float, *,
                        reason: str, day: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    """Explicit migration/displacement: conserve people while moving age structure proportionally."""
    if from_source_id == to_source_id or population <= 0:
        raise ValueError('population transfer requires distinct sources and positive population')
    if day is None:
        day = _day(conn)
    origin = conn.execute("SELECT population_estimate FROM background_population_sources WHERE id=?", (from_source_id,)).fetchone()
    dest = conn.execute("SELECT population_estimate FROM background_population_sources WHERE id=?", (to_source_id,)).fetchone()
    if not origin or not dest:
        raise ValueError('unknown population source')
    rows = conn.execute("SELECT age_band,population FROM background_population_age_cohorts WHERE source_id=?", (from_source_id,)).fetchall()
    if len(rows) != len(_AGE_BANDS):
        raise ValueError('origin lacks live POPLIFE age cohorts')
    total = sum(float(r['population']) for r in rows)
    amount = float(population)
    if amount > total + 1e-9:
        raise ValueError('population transfer exceeds origin population')
    for r in rows:
        band = str(r['age_band']); source_pop = float(r['population'])
        moved = amount * (source_pop / total) if total > 0 else 0.0
        conn.execute("UPDATE background_population_age_cohorts SET population=MAX(0,population-?) WHERE source_id=? AND age_band=?",
                     (moved, from_source_id, band))
        conn.execute("UPDATE background_population_age_cohorts SET population=population+? WHERE source_id=? AND age_band=?",
                     (moved, to_source_id, band))
    _reconcile_source_populations(conn)
    cur = conn.execute(
        "INSERT INTO background_population_movements(day,from_source_id,to_source_id,population,reason,metadata_json) VALUES (?,?,?,?,?,?)",
        (int(day), from_source_id, to_source_id, amount, reason, _j(metadata)),
    )
    return int(cur.lastrowid)


def current_bucket_population(conn: sqlite3.Connection, bucket_key: str) -> int:
    row = conn.execute("SELECT SUM(population_estimate) FROM background_population_sources WHERE bucket_key=?", (bucket_key,)).fetchone()
    if row and row[0] is not None:
        return int(row[0])
    fallback = conn.execute("SELECT population_estimate FROM population_scale_buckets WHERE bucket_key=?", (bucket_key,)).fetchone()
    return int(fallback[0]) if fallback else 0


def current_world_population(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT SUM(population_estimate) FROM background_population_sources").fetchone()
    if row and row[0] is not None:
        return int(row[0])
    return int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM population_scale_buckets").fetchone()[0])

def _sample_age_days(rng: np.random.Generator, n: int) -> np.ndarray:
    shares = np.array([b[1] for b in _AGE_BANDS], dtype=np.float64)
    bands = rng.choice(len(_AGE_BANDS), size=n, p=shares / shares.sum())
    ages = np.empty(n, dtype=np.int32)
    for idx, (_, _, low, high) in enumerate(_AGE_BANDS):
        mask = bands == idx
        if mask.any():
            ages[mask] = rng.integers(low, high + 1, size=int(mask.sum()), dtype=np.int32)
    return ages


def create_partition(
    conn: sqlite3.Connection,
    source_id: int,
    *,
    sample_size: int,
    partition_key: str | None = None,
    seed: int | None = None,
    cadence_days: int = 30,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Create one bounded stable-identity reservoir for a disjoint SCALE-01 source."""
    source = conn.execute("SELECT * FROM background_population_sources WHERE id=?", (source_id,)).fetchone()
    if not source:
        raise ValueError("Unknown background population source")
    population = int(source['population_estimate'])
    if sample_size <= 0 or sample_size > population:
        raise ValueError("sample_size must be positive and no greater than source population")
    existing = conn.execute("SELECT id FROM background_population_partitions WHERE source_id=?", (source_id,)).fetchone()
    if existing:
        raise ValueError("A source may have only one active identity reservoir; resize/reuse it rather than duplicating identities")
    day = _day(conn)
    if seed is None:
        world_seed = conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()
        seed = int(world_seed[0] if world_seed and world_seed[0] is not None else 1) * 1000003 + int(source_id) * 7919
    if partition_key is None:
        partition_key = f"source:{source_id}:identity-reservoir"

    rng = np.random.default_rng(seed & _U64_MASK)
    uid = np.arange(1, sample_size + 1, dtype=np.int64)
    state = PartitionState(
        uid=uid,
        age_days=_sample_age_days(rng, sample_size),
        alive=np.ones(sample_size, dtype=np.bool_),
        demographic_sex=rng.integers(0, 2, size=sample_size, dtype=np.uint8),
        exposure_score=np.zeros(sample_size, dtype=np.float32),
        # active_uids are stable raw slots, matching the source-aligned Starsim pattern.
        active_uids=np.arange(sample_size, dtype=np.int64),
    )
    raw, sha = _encode(state)
    cur = conn.execute(
        """INSERT INTO background_population_partitions(
             partition_key,source_id,sample_size,source_population_at_seed,state_codec,state_blob,state_sha256,
             seed,last_step_day,next_step_day,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,'active',?)""",
        (partition_key, source_id, sample_size, population, _CODEC, sqlite3.Binary(raw), sha, int(seed), day, day + cadence_days,
         _j({
             "authority": "identity_sample_only",
             "population_total_owner": "SCALE01/population_scale_buckets",
             "source_decomposition": "background_population_sources",
             "age_distribution": "campaign_assumption_v1_12_18_10_31_20_09",
             "sex_initialization": "parity_assumption_v1",
             **(metadata or {}),
         })),
    )
    return int(cur.lastrowid)


def load_partition(conn: sqlite3.Connection, partition_id: int) -> tuple[sqlite3.Row, PartitionState]:
    row = conn.execute("SELECT * FROM background_population_partitions WHERE id=?", (partition_id,)).fetchone()
    if not row:
        raise ValueError("Unknown background population partition")
    if str(row['state_codec']) != _CODEC:
        raise ValueError(f"Unsupported background state codec {row['state_codec']!r}")
    return row, _decode(bytes(row['state_blob']), str(row['state_sha256']))


def save_partition(conn: sqlite3.Connection, partition_id: int, state: PartitionState, *, last_step_day: int, next_step_day: int) -> None:
    raw, sha = _encode(state)
    conn.execute(
        """UPDATE background_population_partitions
           SET state_blob=?,state_sha256=?,sample_size=?,last_step_day=?,next_step_day=? WHERE id=?""",
        (sqlite3.Binary(raw), sha, state.sample_size, int(last_step_day), int(next_step_day), partition_id),
    )


def step_partition_month(conn: sqlite3.Connection, partition_id: int, *, day: int | None = None) -> dict[str, int]:
    """Advance identity continuity only; population totals remain under aggregate authority."""
    row, state = load_partition(conn, partition_id)
    if str(row['status']) != 'active':
        return {"partition_id": partition_id, "aged": 0, "deaths": 0}
    if day is None:
        day = _day(conn)
    if day < int(row['next_step_day']):
        return {"partition_id": partition_id, "aged": 0, "deaths": 0}

    slots = state.active_uids
    uid = state.uid[slots]
    ages = state.age_days[slots].copy()
    ages += 30
    alive = state.alive[slots].copy()
    step_index = max(0, int(day) // 30)
    deaths = alive & (_draw(uid, step_index, 1, int(row['seed'])) < _mortality_probability(ages))
    alive[deaths] = False
    state.age_days[slots] = ages
    state.alive[slots] = alive
    state.active_uids = slots[alive]

    # A sampled death is the resolved identity manifestation of aggregate mortality; it does not
    # subtract a second person from SCALE-01. Population dynamics remain an aggregate owner task.
    for local_uid in state.uid[slots[deaths]].tolist():
        conn.execute(
            """INSERT INTO background_population_identity_links(
                 partition_id,local_uid,status,first_link_day,last_update_day,snapshot_json,metadata_json)
               VALUES (?,?,'dead',?,?,?,?)
               ON CONFLICT(partition_id,local_uid) DO UPDATE SET status='dead',last_update_day=excluded.last_update_day,
                 snapshot_json=excluded.snapshot_json,metadata_json=excluded.metadata_json""",
            (partition_id, int(local_uid), int(day), int(day), _j(state.snapshot(int(local_uid))),
             _j({"source": "popback_monthly_step", "population_delta": 0, "reason": "identity-resolution manifestation only"})),
        )

    save_partition(conn, partition_id, state, last_step_day=int(day), next_step_day=int(day) + 30)
    return {"partition_id": partition_id, "aged": int(slots.size), "deaths": int(deaths.sum())}


def apply_exposure(
    conn: sqlite3.Connection,
    partition_id: int,
    local_uid: int,
    *,
    domain: str,
    delta: float,
    reason: str,
    source_kind: str | None = None,
    source_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> float:
    """Accumulate cross-domain causal salience on one pre-existing ordinary identity."""
    row, state = load_partition(conn, partition_id)
    snap = state.snapshot(local_uid)
    if not snap['alive']:
        raise ValueError("Cannot expose a dead background identity")
    slot = int(local_uid) - 1
    state.exposure_score[slot] = np.float32(max(0.0, min(1.0, float(state.exposure_score[slot]) + float(delta))))
    day = _day(conn)
    save_partition(conn, partition_id, state, last_step_day=int(row['last_step_day']), next_step_day=int(row['next_step_day']))
    conn.execute(
        """INSERT INTO background_population_exposures(day,partition_id,local_uid,domain,delta,reason,source_kind,source_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (day, partition_id, local_uid, domain, float(delta), reason, source_kind, source_id, _j(metadata)),
    )
    return float(state.exposure_score[slot])


def promote_identity_to_latent(
    conn: sqlite3.Connection,
    partition_id: int,
    local_uid: int,
    *,
    archetype: str | None = None,
    reason: str,
) -> int:
    """Promote the same sampled identity into the existing latent-person ladder."""
    existing = conn.execute(
        "SELECT latent_entity_id FROM background_population_identity_links WHERE partition_id=? AND local_uid=? AND latent_entity_id IS NOT NULL",
        (partition_id, local_uid),
    ).fetchone()
    if existing:
        return int(existing[0])
    part, state = load_partition(conn, partition_id)
    snap = state.snapshot(local_uid)
    if not snap['alive']:
        raise ValueError("Cannot promote a dead background identity")
    source = conn.execute("SELECT * FROM background_population_sources WHERE id=?", (int(part['source_id']),)).fetchone()
    if not source:
        raise ValueError("Background source disappeared")
    day = _day(conn)
    age_years = max(0, int(snap['age_days'] // 365))
    from .continuity import create_latent_entity
    latent_id = create_latent_entity(
        conn,
        'person',
        archetype or f"ordinary_{source['source_kind']}",
        location_id=int(source['location_id']) if source['location_id'] is not None else None,
        cohort_id=None,
        count_estimate=1,
        constraints={
            'age': age_years,
            'birth_day': day - int(snap['age_days']),
            'demographic_sex': snap['demographic_sex'],
            'background_partition_id': partition_id,
            'background_local_uid': local_uid,
            'background_source_id': int(source['id']),
        },
        historical_context={
            'background_identity_snapshot': snap,
            'background_source_id': int(source['id']),
            'background_source_key': str(source['source_key']),
            'background_source_kind': str(source['source_kind']),
            'population_bucket_key': str(source['bucket_key']),
            'promotion_reason': reason,
            'identity_existed_before_promotion': True,
        },
        day=day,
        notes='Promoted from POPBACK-01 identity reservoir; SCALE-01 remains population-total authority.',
    )
    conn.execute(
        """INSERT INTO background_population_identity_links(
             partition_id,local_uid,status,latent_entity_id,first_link_day,last_update_day,snapshot_json,metadata_json)
           VALUES (?,?,'latent',?,?,?,?,?)
           ON CONFLICT(partition_id,local_uid) DO UPDATE SET status='latent',latent_entity_id=excluded.latent_entity_id,
             last_update_day=excluded.last_update_day,snapshot_json=excluded.snapshot_json,metadata_json=excluded.metadata_json""",
        (partition_id, local_uid, latent_id, day, day, _j(snap), _j({'reason': reason})),
    )
    return latent_id


def partition_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT COUNT(*) n,COALESCE(SUM(sample_size),0) sampled FROM background_population_partitions WHERE status='active'"
    ).fetchone()
    source = conn.execute("SELECT COUNT(*) n,COALESCE(SUM(population_estimate),0) p FROM background_population_sources").fetchone()
    return {
        'population_sources': int(source['n']),
        'source_population_total': int(source['p']),
        'active_partitions': int(rows['n']),
        'sampled_identities': int(rows['sampled']),
        'linked_latent': int(conn.execute("SELECT COUNT(*) FROM background_population_identity_links WHERE latent_entity_id IS NOT NULL").fetchone()[0]),
        'linked_actors': int(conn.execute("SELECT COUNT(*) FROM background_population_identity_links WHERE actor_id IS NOT NULL").fetchone()[0]),
        'authority_rule': 'SCALE-01 owns totals; POPBACK sources decompose them; partitions preserve bounded identity only',
    }
