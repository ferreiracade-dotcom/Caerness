from __future__ import annotations

import json
import math
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def add_enterprise_staff(conn: sqlite3.Connection, enterprise_id: int, actor_id: int, *, role: str = "factor",
                         authority: float = 60, specialty: str = "trade", metadata: dict[str, Any] | None = None) -> None:
    conn.execute(
        """INSERT INTO enterprise_staff(enterprise_id,actor_id,role,authority,specialty,status,joined_day,metadata_json)
           VALUES (?,?,?,?,?,'active',?,?)
           ON CONFLICT(enterprise_id,actor_id) DO UPDATE SET role=excluded.role,authority=excluded.authority,
             specialty=excluded.specialty,status='active',metadata_json=excluded.metadata_json""",
        (enterprise_id, actor_id, role, max(0, min(100, float(authority))), specialty, _day(conn),
         json.dumps(metadata or {}, sort_keys=True)),
    )


def authorized_enterprises(conn: sqlite3.Connection, actor_id: int, *, minimum_authority: float = 40) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT DISTINCT e.* FROM civilian_enterprises e
           LEFT JOIN enterprise_staff s ON s.enterprise_id=e.id AND s.actor_id=? AND s.status='active'
           WHERE e.status IN ('active','strained','insolvent')
             AND (e.owner_actor_id=? OR (s.actor_id IS NOT NULL AND s.authority>=?))
           ORDER BY e.id""",
        (actor_id, actor_id, float(minimum_authority)),
    ).fetchall()


def record_market_observation(conn: sqlite3.Connection, enterprise_id: int, location_id: int, good_id: int, *,
                              observer_actor_id: int | None = None, observed_day: int | None = None,
                              received_day: int | None = None, source_kind: str = "market_report",
                              source_actor_id: int | None = None, reliability: float = .85,
                              price: float | None = None, supply: float | None = None, demand: float | None = None,
                              metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    observed_day = day if observed_day is None else int(observed_day)
    received_day = day if received_day is None else int(received_day)
    m = conn.execute(
        "SELECT current_price,supply,demand FROM market_conditions WHERE location_id=? AND good_id=?",
        (location_id, good_id),
    ).fetchone()
    if not m:
        raise ValueError("market condition does not exist")
    cur = conn.execute(
        """INSERT INTO merchant_market_observations(
               enterprise_id,observer_actor_id,location_id,good_id,observed_day,received_day,
               observed_price,observed_supply,observed_demand,source_kind,source_actor_id,reliability,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (enterprise_id, observer_actor_id, location_id, good_id, observed_day, received_day,
         float(m["current_price"] if price is None else price), float(m["supply"] if supply is None else supply),
         float(m["demand"] if demand is None else demand), source_kind, source_actor_id,
         max(0, min(1, float(reliability))), json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def commission_market_report(conn: sqlite3.Connection, enterprise_id: int, actor_id: int,
                             location_id: int, good_id: int) -> int:
    ent = conn.execute("SELECT location_id FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone()
    if not ent:
        raise ValueError("unknown enterprise")
    day = _day(conn)
    lag = 0
    if ent["location_id"] is not None and int(ent["location_id"]) != int(location_id):
        from .ecology import find_route_path, evaluate_route_leg
        current = int(ent["location_id"])
        path = find_route_path(conn, current, int(location_id), day=day)
        if not path:
            raise ValueError("market cannot be reached for report")
        for rid in path:
            ev = evaluate_route_leg(conn, int(rid), current, day=day)
            lag += max(1, int(math.ceil(float(ev["days"]))))
            current = int(ev["target"])
    return record_market_observation(
        conn, enterprise_id, location_id, good_id, observer_actor_id=actor_id, observed_day=day,
        received_day=day + lag, source_kind="commissioned_report", reliability=.82,
        metadata={"transmission_lag_days": lag},
    )


def latest_market_observation(conn: sqlite3.Connection, enterprise_id: int, location_id: int, good_id: int,
                              day: int | None = None) -> sqlite3.Row | None:
    day = _day(conn) if day is None else int(day)
    return conn.execute(
        """SELECT * FROM merchant_market_observations
           WHERE enterprise_id=? AND location_id=? AND good_id=? AND received_day<=?
           ORDER BY observed_day DESC,received_day DESC,id DESC LIMIT 1""",
        (enterprise_id, location_id, good_id, day),
    ).fetchone()


def create_trade_offer(conn: sqlite3.Connection, seller_enterprise_id: int, stock_id: int,
                       quantity: float, unit_price: float, *, expires_day: int | None = None,
                       metadata: dict[str, Any] | None = None) -> int:
    st = conn.execute(
        "SELECT * FROM commercial_stock WHERE id=? AND enterprise_id=?", (stock_id, seller_enterprise_id)
    ).fetchone()
    if not st:
        raise ValueError("seller does not own stock lot")
    quantity = float(quantity)
    if quantity <= 0 or quantity > float(st["quantity"]) + 1e-9:
        raise ValueError("invalid offer quantity")
    if unit_price <= 0:
        raise ValueError("unit price must be positive")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO merchant_trade_offers(
               seller_enterprise_id,stock_id,location_id,good_id,quantity_available,unit_price,
               published_day,expires_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,'open',?)""",
        (seller_enterprise_id, stock_id, int(st["location_id"]), int(st["good_id"]), quantity,
         float(unit_price), day, expires_day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def observe_trade_offer(conn: sqlite3.Connection, enterprise_id: int, actor_id: int, offer_id: int, *,
                        received_day: int | None = None) -> None:
    off = conn.execute("SELECT id FROM merchant_trade_offers WHERE id=? AND status='open'", (offer_id,)).fetchone()
    if not off:
        raise ValueError("offer unavailable")
    day = _day(conn)
    received = day if received_day is None else int(received_day)
    conn.execute(
        """INSERT INTO merchant_offer_awareness(enterprise_id,actor_id,offer_id,observed_day,received_day)
           VALUES (?,?,?,?,?)
           ON CONFLICT(enterprise_id,offer_id) DO UPDATE SET actor_id=excluded.actor_id,
             observed_day=excluded.observed_day,received_day=excluded.received_day""",
        (enterprise_id, actor_id, offer_id, day, received),
    )


def create_trade_contract(conn: sqlite3.Connection, buyer_enterprise_id: int, offer_id: int, quantity: float, *,
                          settlement_kind: str = "cash_on_delivery", due_day: int | None = None,
                          metadata: dict[str, Any] | None = None) -> int:
    off = conn.execute("SELECT * FROM merchant_trade_offers WHERE id=? AND status='open'", (offer_id,)).fetchone()
    if not off:
        raise ValueError("offer unavailable")
    quantity = float(quantity)
    if quantity <= 0 or quantity > float(off["quantity_available"]) + 1e-9:
        raise ValueError("quantity exceeds offer")
    buyer = conn.execute(
        "SELECT * FROM civilian_enterprises WHERE id=? AND status IN ('active','strained')", (buyer_enterprise_id,)
    ).fetchone()
    seller = conn.execute(
        "SELECT * FROM civilian_enterprises WHERE id=? AND status IN ('active','strained')",
        (int(off["seller_enterprise_id"]),),
    ).fetchone()
    if not buyer or not seller or buyer["location_id"] is None:
        raise ValueError("counterparty unavailable")
    amount = quantity * float(off["unit_price"])
    if settlement_kind == "cash_on_delivery" and float(buyer["cash"]) + 1e-9 < amount:
        raise ValueError("buyer lacks cash")
    if settlement_kind not in {"cash_on_delivery", "seller_credit"}:
        raise ValueError("unsupported settlement kind")
    day = _day(conn)
    due = day + 30 if due_day is None else int(due_day)
    cur = conn.execute(
        """INSERT INTO merchant_trade_contracts(
               offer_id,buyer_enterprise_id,seller_enterprise_id,good_id,quantity,unit_price,
               origin_location_id,destination_location_id,settlement_kind,agreed_day,due_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'accepted',?)""",
        (offer_id, buyer_enterprise_id, int(off["seller_enterprise_id"]), int(off["good_id"]), quantity,
         float(off["unit_price"]), int(off["location_id"]), int(buyer["location_id"]), settlement_kind,
         day, due, json.dumps(metadata or {}, sort_keys=True)),
    )
    cid = int(cur.lastrowid)
    remaining = float(off["quantity_available"]) - quantity
    conn.execute(
        "UPDATE merchant_trade_offers SET quantity_available=?,status=? WHERE id=?",
        (max(0, remaining), "filled" if remaining <= 1e-9 else "open", offer_id),
    )
    return cid



def _settle_contract(conn: sqlite3.Connection, contract: sqlite3.Row, day: int) -> bool:
    if str(contract['status']) in {'fulfilled','cancelled','breached'}:
        return False
    amount = float(contract['quantity']) * float(contract['unit_price'])
    buyer = int(contract['buyer_enterprise_id']); seller = int(contract['seller_enterprise_id'])
    if str(contract['settlement_kind']) == 'cash_on_delivery':
        b = conn.execute('SELECT cash FROM civilian_enterprises WHERE id=?',(buyer,)).fetchone()
        if not b or float(b['cash']) + 1e-9 < amount:
            conn.execute("UPDATE merchant_trade_contracts SET status='breached',delivered_quantity=quantity WHERE id=?", (int(contract['id']),))
            return False
        conn.execute('UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?',(amount,day,buyer))
        conn.execute('UPDATE civilian_enterprises SET cash=cash+?,updated_day=? WHERE id=?',(amount,day,seller))
        conn.execute("""INSERT INTO commercial_cash_transfers(day,from_enterprise_id,to_enterprise_id,amount,transfer_kind,trade_contract_id,metadata_json)
                        VALUES (?,?,?,?,'trade_settlement',?,'{}')""",(day,buyer,seller,amount,int(contract['id'])))
        conn.execute("""INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,related_good_id,source_kind,source_id)
                        VALUES (?,?,?,?,?,?,'merchant_contract',?)""",(seller,day,'revenue',amount,'Trade-contract sale',int(contract['good_id']),int(contract['id'])))
        conn.execute("""INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,related_good_id,source_kind,source_id)
                        VALUES (?,?,?,?,?,?,'merchant_contract',?)""",(buyer,day,'purchase',amount,'Trade-contract purchase',int(contract['good_id']),int(contract['id'])))
        paid=amount
    else:
        conn.execute("""INSERT INTO credit_agreements(lender_enterprise_id,borrower_enterprise_id,principal,outstanding,interest_rate_per_30,
                        opened_day,due_day,status,risk,last_review_day,metadata_json)
                        VALUES (?,?,?,?,0.03,?,?,'current',30,?,?)""",
                     (seller,buyer,amount,amount,day,int(contract['due_day']),day,json.dumps({'merchant01_contract_id':int(contract['id'])},sort_keys=True)))
        conn.execute('UPDATE civilian_enterprises SET debt=debt+?,updated_day=? WHERE id=?',(amount,day,buyer))
        paid=0.0
    conn.execute("""UPDATE merchant_trade_contracts SET delivered_quantity=quantity,amount_paid=?,status='fulfilled',fulfilled_day=? WHERE id=?""",
                 (paid,day,int(contract['id'])))
    return True

def dispatch_trade_contract(conn: sqlite3.Connection, contract_id: int, *,
                            carrier_enterprise_id: int | None = None) -> int | None:
    contract = conn.execute(
        "SELECT * FROM merchant_trade_contracts WHERE id=? AND status='accepted'", (contract_id,)
    ).fetchone()
    if not contract:
        raise ValueError("contract is not dispatchable")
    off = conn.execute("SELECT * FROM merchant_trade_offers WHERE id=?", (int(contract["offer_id"]),)).fetchone()
    if not off:
        raise ValueError("contract offer missing")
    if int(contract["origin_location_id"]) == int(contract["destination_location_id"]):
        stock = conn.execute("SELECT * FROM commercial_stock WHERE id=? AND enterprise_id=?",
                             (int(off["stock_id"]), int(contract["seller_enterprise_id"]))).fetchone()
        qty=float(contract["quantity"])
        if not stock or float(stock["quantity"]) + 1e-9 < qty:
            raise ValueError("insufficient seller stock for local delivery")
        day=_day(conn)
        conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?",(qty,day,int(stock["id"])))
        conn.execute("""INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
                        VALUES (?,?,?,?,?,?) ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
                        quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
                     (int(contract["buyer_enterprise_id"]),int(contract["destination_location_id"]),int(contract["good_id"]),qty,day,
                      json.dumps({"authority":"ENGINE_DERIVED","source":"local_trade_contract","contract_id":int(contract_id)},sort_keys=True)))
        conn.execute("UPDATE merchant_trade_contracts SET shipped_quantity=quantity,delivered_quantity=quantity WHERE id=?",(contract_id,))
        fresh=conn.execute("SELECT * FROM merchant_trade_contracts WHERE id=?",(contract_id,)).fetchone()
        _settle_contract(conn,fresh,day)
        return None
    from .logistics import arrange_stock_shipment
    sid = arrange_stock_shipment(
        conn, int(contract["seller_enterprise_id"]), int(off["stock_id"]), float(contract["quantity"]),
        int(contract["destination_location_id"]), recipient_enterprise_id=int(contract["buyer_enterprise_id"]),
        trade_contract_id=contract_id, carrier_enterprise_id=carrier_enterprise_id,
    )
    conn.execute(
        "UPDATE merchant_trade_contracts SET shipped_quantity=quantity,status='in_transit',shipment_id=? WHERE id=?",
        (sid, contract_id),
    )
    return sid


def settle_delivered_shipment(conn: sqlite3.Connection, shipment: sqlite3.Row, day: int) -> None:
    cid = shipment["trade_contract_id"] if "trade_contract_id" in shipment.keys() else None
    if cid is None:
        return
    contract = conn.execute("SELECT * FROM merchant_trade_contracts WHERE id=?", (int(cid),)).fetchone()
    if not contract:
        return
    _settle_contract(conn, contract, day)


def add_production_input_option(conn: sqlite3.Connection, production_site_id: int, input_good_id: int, *,
                                units_per_output: float = 1.0, substitution_group: str = "primary",
                                preference_weight: float = 1.0, initial_share: float = .5) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT INTO production_input_options(
               production_site_id,input_good_id,units_per_output,substitution_group,preference_weight,
               current_share,last_review_day,next_review_day
           ) VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(production_site_id,input_good_id) DO UPDATE SET units_per_output=excluded.units_per_output,
             substitution_group=excluded.substitution_group,preference_weight=excluded.preference_weight""",
        (production_site_id, input_good_id, float(units_per_output), substitution_group,
         float(preference_weight), max(0, min(1, float(initial_share))), day, day + 30),
    )
    return int(conn.execute(
        "SELECT id FROM production_input_options WHERE production_site_id=? AND input_good_id=?",
        (production_site_id, input_good_id),
    ).fetchone()[0])


def resolve_input_substitution(conn: sqlite3.Connection, production_site_id: int, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    site = conn.execute(
        """SELECT ps.*,e.location_id FROM production_sites ps
           JOIN civilian_enterprises e ON e.id=ps.enterprise_id WHERE ps.id=? AND ps.active=1""",
        (production_site_id,),
    ).fetchone()
    if not site or site["location_id"] is None:
        return {"changed": False}
    options = conn.execute(
        """SELECT o.*,mc.current_price FROM production_input_options o
           JOIN market_conditions mc ON mc.good_id=o.input_good_id AND mc.location_id=?
           WHERE o.production_site_id=? AND o.active=1 ORDER BY o.substitution_group,o.id""",
        (int(site["location_id"]), production_site_id),
    ).fetchall()
    if not options:
        return {"changed": False}
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in options:
        groups.setdefault(str(row["substitution_group"]), []).append(row)
    changes: list[dict[str, float | int]] = []
    total_output = float(site["capacity_per_30"])
    for rows in groups.values():
        weights = [
            max(.0001, float(r["preference_weight"])) /
            max(.01, float(r["current_price"]) * float(r["units_per_output"])) for r in rows
        ]
        denom = sum(weights) or 1.0
        for r, weight in zip(rows, weights):
            new_share = weight / denom
            old_share = float(r["current_share"])
            new_qty = total_output * float(r["units_per_output"]) * new_share
            old_qty = total_output * float(r["units_per_output"]) * old_share
            delta = new_qty - old_qty
            conn.execute(
                "UPDATE production_input_options SET current_share=?,last_review_day=?,next_review_day=? WHERE id=?",
                (new_share, day, day + 30, int(r["id"])),
            )
            mc = conn.execute(
                "SELECT demand FROM market_conditions WHERE location_id=? AND good_id=?",
                (int(site["location_id"]), int(r["input_good_id"])),
            ).fetchone()
            if mc:
                conn.execute(
                    "UPDATE market_conditions SET demand=? WHERE location_id=? AND good_id=?",
                    (max(0, float(mc["demand"]) + delta * 1.5), int(site["location_id"]), int(r["input_good_id"])),
                )
            changes.append({"good_id": int(r["input_good_id"]), "old_share": old_share,
                            "new_share": new_share, "demand_delta": delta})
    return {"changed": True, "production_site_id": production_site_id, "changes": changes}


def apply_supply_shock(conn: sqlite3.Connection, location_id: int, good_id: int, quantity: float, *,
                       source: str = "scenario") -> dict[str, float]:
    from .civilian import _price
    market = conn.execute(
        "SELECT * FROM market_conditions WHERE location_id=? AND good_id=?", (location_id, good_id)
    ).fetchone()
    if not market:
        raise ValueError("market condition does not exist")
    before = float(market["current_price"])
    supply = max(0, float(market["supply"]) + float(quantity))
    base = float(conn.execute("SELECT base_price FROM market_goods WHERE id=?", (good_id,)).fetchone()[0])
    price = _price(base, supply, float(market["demand"]), float(market["transport_pressure"]),
                   float(market["risk_pressure"]), float(market["tax_pressure"]))
    meta = json.loads(market["metadata_json"] or "{}")
    meta["last_supply_shock_source"] = source
    conn.execute(
        "UPDATE market_conditions SET supply=?,current_price=?,metadata_json=? WHERE location_id=? AND good_id=?",
        (supply, price, json.dumps(meta, sort_keys=True), location_id, good_id),
    )
    return {"supply_before": float(market["supply"]), "supply_after": supply,
            "price_before": before, "price_after": price}



def _merchant_cycle_due(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM engine_meta WHERE key='merchant_next_market_cycle_day'").fetchone()
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _route_information_lag(conn: sqlite3.Connection, origin: int, destination: int, day: int, *, route_snapshot=None) -> int | None:
    if int(origin) == int(destination):
        return 0
    if route_snapshot is not None:
        from .ecology import route_information_lag_snapshot
        return route_information_lag_snapshot(route_snapshot, int(origin), int(destination))
    from .ecology import find_route_path, evaluate_route_leg
    path = find_route_path(conn, int(origin), int(destination), day=day)
    if not path:
        return None
    current = int(origin); lag = 0
    for rid in path:
        ev = evaluate_route_leg(conn, int(rid), current, day=day)
        lag += max(1, int(math.ceil(float(ev['days']))))
        current = int(ev['target'])
    return lag


def _ordinary_market_cycle(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Low-resolution public-market routine for ordinary enterprises/factors.

    This is deliberately not omniscient strategic trading. It only (a) exposes owned physical
    stock as local public offers, (b) records the local market book for authorized factors, and
    (c) lets public offers travel to other authorized factors with route-derived information lag.
    Rich choices still belong to DEC-01 actors after the information reaches them.
    """
    conn.execute("UPDATE merchant_trade_offers SET status='expired' WHERE status='open' AND expires_day IS NOT NULL AND expires_day<?", (day,))
    offers_created = observations = awareness = 0

    # Ordinary public listing of a bounded share of actually owned physical stock.
    stocks = conn.execute(
        """SELECT s.*,e.status AS enterprise_status FROM commercial_stock s
           JOIN civilian_enterprises e ON e.id=s.enterprise_id
           WHERE s.quantity>0.75 AND e.status IN ('active','strained') ORDER BY s.id"""
    ).fetchall()
    for st in stocks:
        if conn.execute("SELECT 1 FROM merchant_trade_offers WHERE stock_id=? AND status='open'", (int(st['id']),)).fetchone():
            continue
        market = conn.execute("SELECT current_price FROM market_conditions WHERE location_id=? AND good_id=?",
                              (int(st['location_id']), int(st['good_id']))).fetchone()
        if not market:
            continue
        qty = min(10.0, max(0.5, float(st['quantity']) * .4))
        create_trade_offer(
            conn, int(st['enterprise_id']), int(st['id']), qty, max(.01, float(market['current_price']) * 1.02),
            expires_day=day + 60,
            metadata={'authority':'ENGINE_DERIVED','source':'ordinary_public_market_cycle','low_resolution_listing':True},
        )
        offers_created += 1

    staff = conn.execute(
        """SELECT s.enterprise_id,s.actor_id,e.location_id FROM enterprise_staff s
           JOIN civilian_enterprises e ON e.id=s.enterprise_id
           WHERE s.status='active' AND s.authority>=40 AND e.status IN ('active','strained') AND e.location_id IS NOT NULL
           ORDER BY s.enterprise_id,s.actor_id"""
    ).fetchall()
    offers = conn.execute(
        """SELECT o.* FROM merchant_trade_offers o
           WHERE o.status='open' AND (o.expires_day IS NULL OR o.expires_day>=?) ORDER BY o.id""", (day,)
    ).fetchall()
    # ROUTE-01: one authoritative read-only graph snapshot per market cycle.  This keeps
    # route/environment truth in SQL while avoiding thousands of repeated path queries.
    from .ecology import build_route_path_snapshot
    route_snapshot = build_route_path_snapshot(conn, day=day) if staff and offers else None
    for sf in staff:
        eid=int(sf['enterprise_id']); aid=int(sf['actor_id']); loc=int(sf['location_id'])
        # A factor physically based at a market can know its ordinary public price/supply book.
        for mc in conn.execute("SELECT good_id FROM market_conditions WHERE location_id=? ORDER BY good_id", (loc,)).fetchall():
            gid=int(mc['good_id'])
            last=conn.execute(
                """SELECT observed_day FROM merchant_market_observations
                   WHERE enterprise_id=? AND location_id=? AND good_id=? AND source_kind='ordinary_local_market_book'
                   ORDER BY observed_day DESC,id DESC LIMIT 1""", (eid,loc,gid)).fetchone()
            if last and day-int(last[0]) < 25:
                continue
            record_market_observation(
                conn,eid,loc,gid,observer_actor_id=aid,observed_day=day,received_day=day,
                source_kind='ordinary_local_market_book',reliability=.9,
                metadata={'authority':'ENGINE_DERIVED','low_resolution_public_market':True},
            )
            observations += 1
        # Public offers are not telepathy: remote awareness arrives after route-derived delay.
        for off in offers:
            if int(off['seller_enterprise_id']) == eid:
                continue
            if conn.execute("SELECT 1 FROM merchant_offer_awareness WHERE enterprise_id=? AND offer_id=?", (eid,int(off['id']))).fetchone():
                continue
            lag=_route_information_lag(conn,int(off['location_id']),loc,day,route_snapshot=route_snapshot)
            if lag is None:
                continue
            observe_trade_offer(conn,eid,aid,int(off['id']),received_day=day+lag)
            awareness += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('merchant_next_market_cycle_day',?)", (str(day+30),))
    return {'offers_created':offers_created,'observations':observations,'offer_awareness':awareness}

def next_merchant_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    candidates: list[int] = []
    from .aggregate_trade import next_aggregate_trade_due_day
    from .world_package import system_enabled
    aggregate_due = next_aggregate_trade_due_day(conn, after_day, end_day) if system_enabled(conn, "caerness_trade") else None
    if aggregate_due is not None:
        candidates.append(int(aggregate_due))
    cycle = _merchant_cycle_due(conn)
    if cycle is not None and after_day < cycle <= end_day:
        candidates.append(cycle)
    r = conn.execute(
        "SELECT MIN(next_review_day) FROM production_input_options WHERE active=1 AND next_review_day>? AND next_review_day<=?",
        (after_day, end_day),
    ).fetchone()
    if r and r[0] is not None:
        candidates.append(int(r[0]))
    r = conn.execute(
        "SELECT MIN(due_day) FROM merchant_trade_contracts WHERE status IN ('accepted','in_transit') AND due_day>? AND due_day<=?",
        (after_day, end_day),
    ).fetchone()
    if r and r[0] is not None:
        candidates.append(int(r[0]))
    return min(candidates) if candidates else None


def process_due_merchant(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str, int | float]:
    from .aggregate_trade import process_due_aggregate_trade
    from .world_package import system_enabled
    aggregate_result = process_due_aggregate_trade(conn, day, event_logger=event_logger) if system_enabled(conn, "caerness_trade") else {}
    cycle_result = {'offers_created':0,'observations':0,'offer_awareness':0}
    cycle = _merchant_cycle_due(conn)
    if cycle is not None and cycle <= day:
        cycle_result = _ordinary_market_cycle(conn, day)
    rows = conn.execute(
        "SELECT DISTINCT production_site_id FROM production_input_options WHERE active=1 AND next_review_day<=? ORDER BY production_site_id",
        (day,),
    ).fetchall()
    changed = 0
    for row in rows:
        if resolve_input_substitution(conn, int(row[0]), day).get("changed"):
            changed += 1
    overdue = conn.execute(
        "SELECT id FROM merchant_trade_contracts WHERE status IN ('accepted','in_transit') AND due_day<?",
        (day,),
    ).fetchall()
    for row in overdue:
        conn.execute(
            "UPDATE merchant_trade_contracts SET status='breached' WHERE id=? AND delivered_quantity<quantity",
            (int(row[0]),),
        )
    return {"substitution_reviews": len(rows), "changed": changed, "overdue_contracts": len(overdue), **aggregate_result, **cycle_result}


def _commerce_competence(conn: sqlite3.Connection, actor_id: int) -> float:
    row = conn.execute(
        """SELECT MAX(ac.score) FROM actor_competence ac
           JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key='commerce'""",
        (actor_id,),
    ).fetchone()
    return max(0.0, min(100.0, float(row[0] or 0.0)))


def merchant_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int,
                                 envelope: dict[str, Any]):
    from .decision_runtime import DecisionCandidate
    out: list[DecisionCandidate] = []
    commerce_skill = _commerce_competence(conn, actor_id)
    for ent in authorized_enterprises(conn, actor_id):
        eid = int(ent["id"])
        cash = float(ent["cash"])
        awareness = conn.execute(
            """SELECT a.enterprise_id,a.actor_id,a.offer_id,a.observed_day,a.received_day AS awareness_received,o.*
               FROM merchant_offer_awareness a JOIN merchant_trade_offers o ON o.id=a.offer_id
               WHERE a.enterprise_id=? AND a.received_day<=? AND o.status='open'
                 AND (o.expires_day IS NULL OR o.expires_day>=?)
               ORDER BY a.received_day DESC,o.id LIMIT 6""",
            (eid, day, day),
        ).fetchall()
        for offer in awareness:
            if int(offer["seller_enterprise_id"]) == eid:
                continue
            quantity = min(float(offer["quantity_available"]), max(1.0, cash / max(.01, float(offer["unit_price"])) * .35))
            cost = quantity * float(offer["unit_price"])
            if quantity <= 0 or cost > cash + 1e-9:
                continue
            observed = latest_market_observation(conn, eid, int(offer["location_id"]), int(offer["good_id"]), day)
            ref_price = float(observed["observed_price"]) if observed else float(offer["unit_price"])
            discount = max(-1.5, min(2.0, (ref_price - float(offer["unit_price"])) / max(.01, ref_price) * 4))
            reading_bonus = min(.6, commerce_skill / 200.0) if observed else 0.0
            out.append(DecisionCandidate(
                key=f"merchant:accept_offer:{eid}:{int(offer['offer_id'])}", provider_key="merchant",
                action_kind="accept_trade_offer", utility=4.2 + discount + reading_bonus,
                rationale=f"Accept the specific observed offer #{int(offer['offer_id'])} for {quantity:.2f} units.",
                execution_kind="merchant_action",
                payload={"enterprise_id": eid, "offer_id": int(offer["offer_id"]), "quantity": quantity,
                         "settlement_kind": "cash_on_delivery"},
                information_basis={"enterprise_id": eid, "offer_awareness_received_day": int(offer["awareness_received"]),
                                   "market_observation_id": int(observed["id"]) if observed else None,
                                   "commerce_competence": commerce_skill},
                tags=("merchant", "specific_offer", "bounded_information"), estimated_cost=cost,
                risk=max(.06, .16 - commerce_skill / 1200.0),
            ))
        stocks = conn.execute(
            "SELECT * FROM commercial_stock WHERE enterprise_id=? AND quantity>0.5 ORDER BY quantity DESC,id LIMIT 4",
            (eid,),
        ).fetchall()
        for stock in stocks:
            remote = conn.execute(
                """SELECT * FROM merchant_market_observations
                   WHERE enterprise_id=? AND good_id=? AND location_id<>? AND received_day<=?
                   ORDER BY observed_price DESC,observed_day DESC LIMIT 1""",
                (eid, int(stock["good_id"]), int(stock["location_id"]), day),
            ).fetchone()
            if not remote:
                continue
            local = latest_market_observation(conn, eid, int(stock["location_id"]), int(stock["good_id"]), day)
            if not local:
                continue
            local_price = float(local["observed_price"])
            minimum_premium = max(1.04, 1.14 - commerce_skill / 1000.0)
            if float(remote["observed_price"]) <= local_price * minimum_premium:
                continue
            quantity = min(float(stock["quantity"]) * .4, 10.0)
            out.append(DecisionCandidate(
                key=f"merchant:move_stock:{eid}:{int(stock['id'])}:{int(remote['location_id'])}", provider_key="merchant",
                action_kind="move_stock_to_market",
                utility=3.8 + min(2.0, (float(remote["observed_price"]) / local_price - 1) * 5),
                rationale="Move owned stock toward a specifically observed higher-price market.",
                execution_kind="merchant_action",
                payload={"enterprise_id": eid, "stock_id": int(stock["id"]), "quantity": quantity,
                         "destination_location_id": int(remote["location_id"])},
                information_basis={"remote_market_observation_id": int(remote["id"]),
                                   "local_market_observation_id": int(local["id"]),
                                   "commerce_competence": commerce_skill,
                                   "minimum_price_premium": round(minimum_premium, 4)},
                tags=("merchant", "stock", "shipment"), risk=max(.08, .22 - commerce_skill / 800.0),
            ))
        stale_after_days = max(20, int(round(45 - commerce_skill * .25)))
        stale = conn.execute(
            """SELECT * FROM merchant_market_observations
               WHERE enterprise_id=? AND received_day<=? AND (? - observed_day)>=?
               ORDER BY observed_day ASC LIMIT 1""",
            (eid, day, day, stale_after_days),
        ).fetchone()
        if stale:
            out.append(DecisionCandidate(
                key=f"merchant:refresh_report:{eid}:{int(stale['location_id'])}:{int(stale['good_id'])}",
                provider_key="merchant", action_kind="refresh_market_report", utility=4.0,
                rationale="Commission a fresh report because the enterprise record is stale.",
                execution_kind="merchant_action",
                payload={"enterprise_id": eid, "location_id": int(stale["location_id"]), "good_id": int(stale["good_id"])},
                information_basis={"stale_observation_id": int(stale["id"]),
                                   "commerce_competence": commerce_skill,
                                   "stale_after_days": stale_after_days},
                tags=("merchant", "information", "stale_record"), risk=.03,
            ))
    return out


def execute_merchant_action(conn: sqlite3.Connection, actor_id: int, action_kind: str,
                            payload: dict[str, Any], day: int) -> dict[str, Any]:
    eid = int(payload.get("enterprise_id") or 0)
    if eid not in {int(e["id"]) for e in authorized_enterprises(conn, actor_id)}:
        return {"summary": "Merchant action blocked: actor lacks enterprise authority.", "blocked": True}
    try:
        if action_kind == "accept_trade_offer":
            conn.execute("SAVEPOINT merchant_accept_offer")
            try:
                cid = create_trade_contract(
                    conn, eid, int(payload["offer_id"]), float(payload["quantity"]),
                    settlement_kind=str(payload.get("settlement_kind") or "cash_on_delivery"),
                )
                sid = dispatch_trade_contract(conn, cid)
                conn.execute("RELEASE SAVEPOINT merchant_accept_offer")
            except Exception:
                conn.execute("ROLLBACK TO SAVEPOINT merchant_accept_offer")
                conn.execute("RELEASE SAVEPOINT merchant_accept_offer")
                raise
            if sid is None:
                status=conn.execute("SELECT status FROM merchant_trade_contracts WHERE id=?",(cid,)).fetchone()
                return {"summary": f"Accepted observed local trade offer; contract #{cid} resolved as {status[0] if status else 'unknown'}.",
                        "contract_id": cid, "shipment_id": None}
            return {"summary": f"Accepted observed trade offer and dispatched contract #{cid} as shipment #{sid}.",
                    "contract_id": cid, "shipment_id": sid}
        if action_kind == "move_stock_to_market":
            from .logistics import arrange_stock_shipment
            sid = arrange_stock_shipment(
                conn, eid, int(payload["stock_id"]), float(payload["quantity"]), int(payload["destination_location_id"])
            )
            return {"summary": f"Dispatched owned stock as shipment #{sid}.", "shipment_id": sid}
        if action_kind == "refresh_market_report":
            oid = commission_market_report(conn, eid, actor_id, int(payload["location_id"]), int(payload["good_id"]))
            row = conn.execute("SELECT received_day FROM merchant_market_observations WHERE id=?", (oid,)).fetchone()
            return {"summary": f"Commissioned market report #{oid}; it becomes usable on day {int(row[0])}.",
                    "observation_id": oid}
        return {"summary": f"Merchant action blocked: unsupported action {action_kind}.", "blocked": True}
    except Exception as exc:
        return {"summary": f"Merchant action blocked: {exc}", "blocked": True}
