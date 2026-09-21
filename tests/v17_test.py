from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.civilian import create_cultural_object, create_enterprise, create_household, create_project
from engine.civilian_life import (
    create_credit_agreement, create_professional_membership, ensure_style_movement,
    set_enterprise_partner, set_inheritance_claim, set_style_adoption, set_succession_plan,
)
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.simulation import advance_connection, seed_demo


def _fresh():
    reset_db(); init_db(); seed_demo(); init_db()


def _actor(conn, name):
    return conn.execute('SELECT * FROM actors WHERE name=?', (name,)).fetchone()


def run():
    _fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {'0.17.0','0.18.0','0.19.0','0.19.1','0.20.0','0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
        merchant = _actor(conn, '[DEMO] House of Seven Ledgers')
        player = _actor(conn, '[DEMO] Player Wanderer')
        cairn = int(conn.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0])

        # Add a second plausible household claimant / professional member.
        cur = conn.execute("INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,is_demo) VALUES (?,?,?,?,?,'active',1)",
                           ('[DEMO] Civilian Heir', 'character', 'merchant_heir', cairn, cairn))
        heir = int(cur.lastrowid)

        hh = create_household(conn, '[DEMO] Deep Civilian Household', head_actor_id=int(merchant['id']),
                              location_id=cairn, wealth=240, liquidity=45, staff_capacity=55, hospitality=40)
        conn.execute("INSERT INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status) VALUES (?,?,?,?,?,?, 'active')",
                     (hh, heir, 'heir', 45, 25, 0))
        set_succession_plan(conn, hh, designated_heir_actor_id=heir, succession_method='designated', certainty=90, dispute_pressure=20)
        set_inheritance_claim(conn, hh, heir, priority=90, legitimacy=85, support=70, status='active')
        set_inheritance_claim(conn, hh, int(player['id']), priority=25, legitimacy=30, support=10)

        # Architecture is not just a completed project: it crystallizes into a persistent building.
        proj = create_project(conn, '[DEMO] Indigo Counting Hall', 'architecture', patron_actor_id=int(merchant['id']),
                              creator_actor_id=int(player['id']), location_id=cairn, target_day=45,
                              quality_potential=80, funding=85, material_access=78, skilled_labor=82,
                              metadata={'building_kind':'hall','household_id':hh,'style_key':'indigo_court',
                                        'capacity':72,'prestige':76,'utility':88,'maintenance_burden':14})

        # Fashion / textile styles propagate as local social adoption, not as universal world switches.
        style = ensure_style_movement(conn, 'indigo_court', 'Indigo Court', 'dress', origin_location_id=cairn,
                                      prestige=80, novelty=72, accessibility=60, durability=70, status='current')
        set_style_adoption(conn, style, cairn, adoption=12, elite_support=85, craft_capacity=78, resistance=12)

        # Enterprise credit and partnership are authoritative balances/governance, not flavor text.
        lender = create_enterprise(conn, '[DEMO] Quiet Ledger Bank', 'service', owner_actor_id=int(merchant['id']),
                                   location_id=cairn, capital=400, cash=300, admin_quality=80)
        borrower = create_enterprise(conn, '[DEMO] Indigo Works', 'workshop', owner_actor_id=heir, household_id=hh,
                                     location_id=cairn, capital=80, cash=10, debt=0, admin_quality=65)
        set_enterprise_partner(conn, borrower, heir, ownership_share=60, governance_weight=70, capital_committed=50, role='managing_partner')
        set_enterprise_partner(conn, borrower, int(player['id']), ownership_share=40, governance_weight=30, capital_committed=30)
        credit = create_credit_agreement(conn, principal=60, lender_enterprise_id=lender, borrower_enterprise_id=borrower,
                                         interest_rate_per_30=0.02, due_day=60, risk=45)

        # Institutional professional life accrues seniority/eligibility without granting an office automatically.
        member = create_professional_membership(conn, heir, int(merchant['id']), 'commerce', role='junior_factor',
                                                standing=72, influence=20, dues_per_30=1)

        # Personal property should transfer through household succession.
        heirloom = create_cultural_object(conn, '[DEMO] Family Ledger', 'book', owner_actor_id=int(merchant['id']),
                                          location_id=cairn, quality=70, market_value=40, significance='personal')
        conn.commit()

        adoption_before = float(conn.execute('SELECT adoption FROM style_adoption WHERE style_id=? AND location_id=?', (style,cairn)).fetchone()[0])
        borrower_before = conn.execute('SELECT cash,debt FROM civilian_enterprises WHERE id=?', (borrower,)).fetchone()
        assert float(borrower_before['cash']) == 70 and float(borrower_before['debt']) == 60

        # 400 days proves recurring systems work through shared story time.
        advance_connection(conn, 400)
        conn.commit()

        building = conn.execute('SELECT * FROM buildings WHERE project_id=?', (proj,)).fetchone()
        assert building is not None and building['building_kind'] == 'hall'
        assert int(building['updated_day']) == 400 and float(building['condition']) > 0

        adoption = float(conn.execute('SELECT adoption FROM style_adoption WHERE style_id=? AND location_id=?', (style,cairn)).fetchone()[0])
        assert adoption > adoption_before

        loan = conn.execute('SELECT * FROM credit_agreements WHERE id=?', (credit,)).fetchone()
        assert float(loan['outstanding']) > 60
        assert loan['status'] == 'defaulted'
        borrower_after = conn.execute('SELECT debt,status FROM civilian_enterprises WHERE id=?', (borrower,)).fetchone()
        assert float(borrower_after['debt']) > 60 and borrower_after['status'] in ('strained','insolvent')

        membership = conn.execute('SELECT * FROM professional_memberships WHERE id=?', (member,)).fetchone()
        assert int(membership['seniority_days']) >= 365
        assert membership['eligibility_state'] == 'eligible_for_review'
        assert membership['role'] == 'junior_factor'  # eligibility is not an auto-promotion.
        assert conn.execute('SELECT COUNT(*) FROM professional_reviews WHERE membership_id=?', (member,)).fetchone()[0] >= 1

        partners = conn.execute('SELECT SUM(ownership_share),SUM(governance_weight) FROM enterprise_partners WHERE enterprise_id=? AND status="active"', (borrower,)).fetchone()
        assert round(float(partners[0]), 5) == 100 and round(float(partners[1]), 5) == 100

        # Succession is automatically triggered only when the old head is actually marked dead/deceased.
        conn.execute("UPDATE actors SET status='deceased' WHERE id=?", (merchant['id'],))
        conn.commit()
        advance_connection(conn, 1)
        conn.commit()
        h = conn.execute('SELECT * FROM households WHERE id=?', (hh,)).fetchone()
        assert int(h['head_actor_id']) == heir
        se = conn.execute('SELECT * FROM succession_events WHERE household_id=? ORDER BY id DESC LIMIT 1', (hh,)).fetchone()
        assert se is not None and int(se['new_head_actor_id']) == heir and se['resolution_kind'] == 'designated'
        obj = conn.execute('SELECT * FROM cultural_objects WHERE id=?', (heirloom,)).fetchone()
        assert int(obj['current_owner_actor_id']) == heir
        assert conn.execute("SELECT COUNT(*) FROM object_provenance WHERE object_id=? AND provenance_kind='inherited'", (heirloom,)).fetchone()[0] == 1

        summary = __import__('engine.civilian', fromlist=['civilian_summary']).civilian_summary(conn)
        assert summary['buildings'] >= 1 and summary['styles'] >= 1 and summary['open_credit'] >= 1
        assert summary['enterprise_partners'] >= 2 and summary['professional_memberships'] >= 1

    print('v17_test: PASS')


if __name__ == '__main__':
    run()
