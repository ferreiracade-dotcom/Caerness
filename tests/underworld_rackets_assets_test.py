"""Persistent underworld rackets/assets — acceptance tests.

Covers the racket/front work done after ARCH-01: racket kinds with real distinct
numbers instead of being pure labels, zone-aware kind selection (universal baseline
everywhere, warehouse-flavored kinds boosted in warehouse/commercial/caravan zones,
not exclusive to any one city), a fixed racket_kind->activity mapping, secrecy actually
protecting a racket from raids, and fronts finally being seizable (the schema already
allowed a 'seized' status; nothing used it before this).
"""
from __future__ import annotations
import os, sys, tempfile, random
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.underworld import create_underworld_organization
from engine.underworld_rebuild import (
    RACKET_PROFILES, UNIVERSAL_RACKET_KINDS, WAREHOUSE_FLAVORED_RACKET_KINDS, TERRITORIAL_ACTIVITIES,
    racket_kind_options, create_racket_site, create_zone, set_zone_controller, create_front,
    seize_front, grant_operating_permission, attempt_local_activity, _review_heat, ensure_heat_profile,
)


def bootstrap():
    path = Path(tempfile.gettempdir()) / f'caerness_racket_assets_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH'] = str(path)
    os.environ['CAERNESS_TEST_MODE'] = '1'
    reset_db(force=True, backup=False); init_db()
    c = connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def run():
    assert ENGINE_VERSION == '0.60.0' and SCHEMA_VERSION >= 59
    c = bootstrap()
    alder = int(c.execute("select id from locations where name='Aldergate'").fetchone()[0])
    org = create_underworld_organization(c, 'test-racket-org', 'gang', name='Test Racket Gang', primary_location_id=alder, member_count_estimate=30, command_depth=1)

    # --- every registered kind maps to a real, recognized territorial activity, not a
    # guess based on whether the name happens to contain "gambl" or "book".
    for kind, profile in RACKET_PROFILES.items():
        assert profile["activity"] in TERRITORIAL_ACTIVITIES, (kind, profile["activity"])
    assert "courtesan house leverage" in RACKET_PROFILES
    assert RACKET_PROFILES["courtesan house leverage"]["activity"] == "local_extortion"
    assert "brothel protection" in RACKET_PROFILES
    assert RACKET_PROFILES["brothel protection"]["activity"] == "brothel_protection"

    # --- universal kinds are available with no zone at all (no city to flavor against).
    pool_no_zone = set(racket_kind_options(c, None, random.Random(1), count=200))
    assert pool_no_zone >= set(UNIVERSAL_RACKET_KINDS)

    # --- zone-aware selection: a warehouse zone should draw warehouse-flavored kinds far
    # more often than a residential zone does, without making them exclusive to it.
    warehouse_zone = create_zone(c, alder, 'test-warehouse-zone', 'Test Warehouse Zone', zone_kind='warehouse')
    residential_zone = create_zone(c, alder, 'test-residential-zone', 'Test Residential Zone', zone_kind='residential')
    warehouse_picks = racket_kind_options(c, warehouse_zone, random.Random(2), count=500)
    residential_picks = racket_kind_options(c, residential_zone, random.Random(3), count=500)
    warehouse_flavor_rate_in_warehouse = sum(1 for k in warehouse_picks if k in WAREHOUSE_FLAVORED_RACKET_KINDS) / len(warehouse_picks)
    warehouse_flavor_rate_in_residential = sum(1 for k in residential_picks if k in WAREHOUSE_FLAVORED_RACKET_KINDS) / len(residential_picks)
    assert warehouse_flavor_rate_in_warehouse > warehouse_flavor_rate_in_residential * 1.5, (warehouse_flavor_rate_in_warehouse, warehouse_flavor_rate_in_residential)
    assert any(k in UNIVERSAL_RACKET_KINDS for k in residential_picks), "universal kinds must still appear in a non-warehouse zone"

    # --- the fixed activity mapping actually changes what gets authorized. Under the old
    # substring guess, "high-risk debt" fell into the generic "collections" bucket; it now
    # correctly requires local_debt_enforcement, so a guest authorized only for collections
    # must NOT be allowed to run a high-risk-debt racket in someone else's zone.
    set_zone_controller(c, warehouse_zone, org)
    rival = create_underworld_organization(c, 'test-racket-rival', 'gang', name='Test Racket Rival', primary_location_id=alder, member_count_estimate=20, command_depth=1)
    grant_operating_permission(c, warehouse_zone, org, rival, 'collections', tribute_rate=.1)
    assert attempt_local_activity(c, warehouse_zone, rival, 'collections')['authorized'] is True
    assert attempt_local_activity(c, warehouse_zone, rival, 'local_debt_enforcement')['authorized'] is False

    # --- secrecy now actually protects a racket. Two rackets, identical in every way
    # except secrecy, raided many times: the high-secrecy one must be suppressed far less.
    def raid_survival_rate(secrecy_a: float, secrecy_b: float, trials: int = 20) -> tuple[float, float]:
        suppressed_a = suppressed_b = 0
        for i in range(trials):
            cc = bootstrap()
            aid = int(cc.execute("select id from locations where name='Aldergate'").fetchone()[0])
            o = create_underworld_organization(cc, f'test-secrecy-org-{i}', 'gang', name='Test Secrecy Gang', primary_location_id=aid, member_count_estimate=30, command_depth=1)
            zid = create_zone(cc, aid, f'test-secrecy-zone-{i}', f'Test Secrecy Zone {i}')
            set_zone_controller(cc, zid, o)
            ra = create_racket_site(cc, o, 'protection collections', zone_id=zid, gross_income_per_30=5, secrecy=secrecy_a)
            rb = create_racket_site(cc, o, 'unlicensed bookmaking', zone_id=zid, gross_income_per_30=5, secrecy=secrecy_b)
            # force the raid roll to land by driving heat past the racket_raid threshold directly.
            ensure_heat_profile(cc, o)
            cc.execute("UPDATE underworld_heat SET investigative_heat=40,public_heat=25,violence_heat=25,corruption_cover=0 WHERE organization_id=?", (o,))
            _review_heat(cc, o, random.Random(1000 + i))
            status_a = cc.execute("SELECT status FROM underworld_racket_sites WHERE id=?", (ra,)).fetchone()[0]
            status_b = cc.execute("SELECT status FROM underworld_racket_sites WHERE id=?", (rb,)).fetchone()[0]
            suppressed_a += status_a == 'suppressed'
            suppressed_b += status_b == 'suppressed'
            cc.commit(); cc.close()
        return suppressed_a / trials, suppressed_b / trials

    rate_high_secrecy, rate_low_secrecy = raid_survival_rate(90, 10, trials=20)
    assert rate_low_secrecy > rate_high_secrecy * 2, (rate_high_secrecy, rate_low_secrecy)

    # --- fronts can now actually be seized (the schema always allowed 'seized'; nothing
    # used it). Direct call first, then confirm the enforcement path can reach a front too.
    c2 = bootstrap()
    aid2 = int(c2.execute("select id from locations where name='Aldergate'").fetchone()[0])
    o2 = create_underworld_organization(c2, 'test-front-org', 'gang', name='Test Front Gang', primary_location_id=aid2, member_count_estimate=20, command_depth=1)
    z2 = create_zone(c2, aid2, 'test-front-zone', 'Test Front Zone')
    set_zone_controller(c2, z2, o2)
    eid = create_front(c2, o2, 'Test Cover Shop', 'service', zone_id=z2, archetype='general_store')
    link_id = int(c2.execute("SELECT id FROM underworld_business_links WHERE enterprise_id=? AND status='active'", (eid,)).fetchone()[0])
    front_depth_before = float(c2.execute("SELECT front_depth FROM underworld_organizations WHERE id=?", (o2,)).fetchone()[0])
    assert front_depth_before > 0
    seized = seize_front(c2, link_id, reason="test")
    assert seized is True
    assert c2.execute("SELECT status FROM underworld_business_links WHERE id=?", (link_id,)).fetchone()[0] == 'seized'
    assert c2.execute("SELECT status FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()[0] == 'closed'
    front_depth_after = float(c2.execute("SELECT front_depth FROM underworld_organizations WHERE id=?", (o2,)).fetchone()[0])
    assert front_depth_after < front_depth_before
    assert seize_front(c2, link_id, reason="test") is False, "seizing an already-seized front must not report success"
    ev = c2.execute("SELECT * FROM events WHERE event_type='underworld_front_seized' ORDER BY id DESC LIMIT 1").fetchone()
    assert ev is None  # no event_logger was passed to this direct call; the authoritative row still exists regardless
    assert c2.execute("SELECT 1 FROM underworld_business_links WHERE id=?", (link_id,)).fetchone()  # authoritative record persists

    # --- enforcement can now hit a front, not only rackets: give an org one very exposed
    # front (low admin_quality) and no rackets, force the raid roll, confirm it lands.
    c3 = bootstrap()
    aid3 = int(c3.execute("select id from locations where name='Aldergate'").fetchone()[0])
    o3 = create_underworld_organization(c3, 'test-front-raid-org', 'gang', name='Test Front Raid Gang', primary_location_id=aid3, member_count_estimate=20, command_depth=1)
    z3 = create_zone(c3, aid3, 'test-front-raid-zone', 'Test Front Raid Zone')
    set_zone_controller(c3, z3, o3)
    eid3 = create_front(c3, o3, 'Test Exposed Shop', 'service', zone_id=z3, archetype='general_store')
    link_id3 = int(c3.execute("SELECT id FROM underworld_business_links WHERE enterprise_id=? AND status='active'", (eid3,)).fetchone()[0])
    c3.execute("UPDATE civilian_enterprises SET admin_quality=5 WHERE id=?", (eid3,))
    fired = False
    for i in range(12):
        ensure_heat_profile(c3, o3)
        c3.execute("UPDATE underworld_heat SET investigative_heat=40,public_heat=25,violence_heat=25,corruption_cover=0 WHERE organization_id=?", (o3,))
        _review_heat(c3, o3, random.Random(2000 + i))
        status = c3.execute("SELECT status FROM underworld_business_links WHERE id=?", (link_id3,)).fetchone()[0]
        if status == 'seized':
            fired = True
            break
    assert fired, "enforcement never reached the only available target (a front) across 12 trials"

    print('underworld rackets/assets tests: PASS')


if __name__ == '__main__':
    run()
