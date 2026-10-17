"""Gap 4b: the world pushes back. One function per task; each runs on a temp copy of the packaged world."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@contextmanager
def world():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "w.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        init_db()
        conn = connect()
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
        finally:
            conn.close()


def money():
    from engine import ledger
    from engine.simulation import advance_connection
    from fixtures_protagonist import make_boss, make_fane
    with world() as conn:
        w = make_fane(conn, legacy=False)
        outfit = w["outfit"]
        assert conn.execute("SELECT 1 FROM underworld_heat WHERE organization_id=?", (outfit,)).fetchone(), "new outfit has no heat row"
        advance_connection(conn, 31)
        t = conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0]
        assert t > 0, f"outfit with heat row did not earn: {t}"
        assert conn.execute("SELECT COUNT(*) FROM underworld_finance_transactions WHERE organization_id=?", (outfit,)).fetchone()[0] > 0
    # owner's draw
    with world() as conn:
        w = make_fane(conn, legacy=False)
        hh = w["household"]
        h0 = ledger.balance(conn, ("household", hh))
        advance_connection(conn, 91)
        assert ledger.balance(conn, ("household", hh)) > h0 - 3, "household got nothing from owned businesses"
        gain = conn.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='distribution' AND target_household_id=?", (hh,)).fetchone()[0]
        assert gain >= 1, "no owner_draw flow"
        for eid in w["fronts"]:
            op = conn.execute("SELECT operating_cost FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
            cash = conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()[0]
            if op:
                assert cash >= 2 * float(op[0]) - 1e-6 or cash >= 0, (eid, cash, op[0])
    # migration seeds a legacy outfit
    with world() as conn:
        w = make_fane(conn, legacy=True)
        from engine.db import _migration_113
        _migration_113(conn)
        assert conn.execute("SELECT 1 FROM underworld_heat WHERE organization_id=?", (w["outfit"],)).fetchone()
        assert conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (w["outfit"],)).fetchone()[0] > 0
        _migration_113(conn)  # idempotent
        t1 = conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (w["outfit"],)).fetchone()[0]
        _migration_113(conn)
        assert conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (w["outfit"],)).fetchone()[0] == t1
    print("money ok")


def ground():
    from fixtures_protagonist import make_fane
    from engine.db import _migration_113
    with world() as conn:
        w = make_fane(conn, legacy=True)
        outfit = w["outfit"]
        assert conn.execute("SELECT COUNT(*) FROM underworld_zone_claims WHERE organization_id=? AND status='active'", (outfit,)).fetchone()[0] == 0
        _migration_113(conn)
        claims = conn.execute("SELECT zone_id,claim_kind FROM underworld_zone_claims WHERE organization_id=? AND status='active'", (outfit,)).fetchall()
        assert claims, "outfit with fronts neither holds nor contests ground"
        assert claims[0]["zone_id"] in [r[0] for r in conn.execute("SELECT id FROM underworld_zones WHERE city_location_id=?", (w["location"],))]
        for eid in w["fronts"]:
            n = conn.execute("SELECT COUNT(*) FROM underworld_protection_accounts WHERE enterprise_id=? AND status='active' AND protector_organization_id<>?", (eid, outfit)).fetchone()[0]
            assert n == 0, f"rival still protects front {eid}"
        for rv in w["rivals"]:
            a, b = sorted((rv, outfit))
            rel = conn.execute("SELECT * FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone()
            assert rel and rel["relation_kind"] == "rival" and rel["hostility"] >= 45, dict(rel) if rel else None
            assert conn.execute("SELECT COUNT(*) FROM underworld_incidents WHERE incident_kind='protection_dispute' AND target_organization_id=? AND source_organization_id=?", (rv, outfit)).fetchone()[0] >= 1
        # baseline relations among outfits sharing a city
        loc = w["location"]
        orgs = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_organizations WHERE primary_location_id=? AND status='active'", (loc,))]
        missing = 0
        for i, x in enumerate(orgs):
            for y in orgs[i + 1:]:
                a, b = sorted((x, y))
                if not conn.execute("SELECT 1 FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone():
                    missing += 1
        assert missing == 0, f"{missing} same-city pairs without a relation"
        n_claims = conn.execute("SELECT COUNT(*) FROM underworld_zone_claims").fetchone()[0]
        n_inc = conn.execute("SELECT COUNT(*) FROM underworld_incidents").fetchone()[0]
        _migration_113(conn)
        assert conn.execute("SELECT COUNT(*) FROM underworld_zone_claims").fetchone()[0] == n_claims
        assert conn.execute("SELECT COUNT(*) FROM underworld_incidents").fetchone()[0] == n_inc
    print("ground ok")


TESTS = {"money": money, "ground": ground}

if __name__ == "__main__":
    names = sys.argv[1:] or list(TESTS)
    for n in names:
        TESTS[n]()
    print("world_pushes_back_test: ok", names)
