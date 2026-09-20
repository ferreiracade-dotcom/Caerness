"""ARCH-02 — authoritative registry cutover and caller-boundary invariance.

Acceptance law:
    advance(N) == advance(a)+advance(b)+... whenever the chunks sum to N.

The public API boundary is not a world event.  This test protects the two defects found
while hardening ARCH-01 for production:
- terminal catch-up used to resolve ordinary domains at arbitrary caller end-days;
- resolution lookahead used to mutate latent review dates using the caller's horizon.
"""
from __future__ import annotations
import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.simulation import advance_connection
from engine.resolution_controller import next_resolution_due_day


COMPARE_TABLES = (
    "world_state", "events", "event_information", "event_targets",
    "knowledge", "knowledge_provenance", "actor_beliefs",
    "enterprise_accounts", "aggregate_trade_balances", "aggregate_trade_flows",
    "rumours", "rumour_locations", "rumour_transmissions", "rumour_exposures",
    "background_population_sources", "background_population_age_cohorts",
    "simulation_profiles", "actors", "actor_presence_profiles",
    "civilian_enterprises", "relationships", "information_links", "travel_plans",
    "tournament_events", "underworld_organizations", "agreements",
    "latent_entities", "latent_resolution_profiles", "entity_resolution", "resolution_reviews",
)
VOLATILE_COLUMNS = {"created_at", "updated_at", "timestamp", "recorded_at"}


def _bootstrap(name: str):
    path = Path(tempfile.gettempdir()) / name
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_TEST_MODE"] = "1"
    reset_db(force=True, backup=False)
    init_db()
    conn = connect()
    import_current_seed(conn)
    activate_existing_loops(conn)
    conn.commit()
    return conn


def _hash_table(conn: sqlite3.Connection, table: str) -> tuple[int, str] | None:
    info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    if not info:
        return None
    cols = [r[1] for r in info if str(r[1]).lower() not in VOLATILE_COLUMNS]
    pks = [r[1] for r in info if int(r[5] or 0) > 0]
    order = pks or cols
    sql = (
        "SELECT " + ",".join(f'"{c}"' for c in cols) +
        f' FROM "{table}" ORDER BY ' + ",".join(f'"{c}"' for c in order)
    )
    digest = hashlib.sha256()
    count = 0
    for row in conn.execute(sql):
        digest.update(repr(tuple(row)).encode("utf-8"))
        digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def run() -> dict:
    assert ENGINE_VERSION == "0.60.0" and SCHEMA_VERSION >= 74

    # Due-date lookahead is observational, never a hidden mutation.  Different caller
    # horizons may change whether a due day is visible, but not persisted review state.
    probe = _bootstrap("caerness_arch02_due_purity.db")
    before = [tuple(r) for r in probe.execute(
        "SELECT * FROM latent_resolution_profiles ORDER BY latent_entity_id"
    ).fetchall()]
    next_resolution_due_day(probe, 0, 30)
    middle = [tuple(r) for r in probe.execute(
        "SELECT * FROM latent_resolution_profiles ORDER BY latent_entity_id"
    ).fetchall()]
    next_resolution_due_day(probe, 0, 365)
    after = [tuple(r) for r in probe.execute(
        "SELECT * FROM latent_resolution_profiles ORDER BY latent_entity_id"
    ).fetchall()]
    assert before == middle == after, "resolution lookahead mutated latent review state"
    probe.close()

    # Normal-regression depth: enough time for trade, civilian, information, life-stage,
    # shipment and repeated rumour propagation checkpoints without making every test run
    # pay the full one-year cost.
    one = _bootstrap("caerness_arch02_one_90.db")
    advance_connection(one, 90)
    one.commit()

    segmented = _bootstrap("caerness_arch02_segmented_90.db")
    for days in (30, 30, 30):
        advance_connection(segmented, days)
        segmented.commit()

    diffs = []
    for table in COMPARE_TABLES:
        left = _hash_table(one, table)
        right = _hash_table(segmented, table)
        if left != right:
            diffs.append((table, left, right))
    assert not diffs, f"caller-boundary invariance failed: {diffs[:8]}"

    assert one.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert segmented.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not one.execute("PRAGMA foreign_key_check").fetchall()
    assert not segmented.execute("PRAGMA foreign_key_check").fetchall()

    result = {
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "days": 90,
        "tables_compared": len(COMPARE_TABLES),
        "events": int(one.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
        "knowledge": int(one.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]),
        "rumours": int(one.execute("SELECT COUNT(*) FROM rumours").fetchone()[0]),
        "trade_periods": int(one.execute("SELECT COUNT(DISTINCT period_day) FROM aggregate_trade_balances").fetchone()[0]),
        "status": "PASS",
    }
    one.close(); segmented.close()
    print("ARCH-02 scheduler chunk invariance: PASS")
    print(result)
    return result


if __name__ == "__main__":
    run()
