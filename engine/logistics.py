from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Callable

from .ecology import find_route_path, evaluate_route_leg


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _begin_next_leg(conn: sqlite3.Connection, shipment_id: int, day: int) -> bool:
    sh = conn.execute("SELECT * FROM commercial_shipments WHERE id=?", (shipment_id,)).fetchone()
    if not sh or str(sh["status"]) not in {"in_transit", "stalled"}:
        return False
    current = int(sh["current_location_id"])
    destination = int(sh["destination_location_id"])
    if current == destination:
        _deliver(conn, sh, day)
        return True
    path = find_route_path(conn, current, destination, day=day)
    if not path:
        conn.execute(
            "UPDATE commercial_shipments SET status='stalled',current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
            (day + 3, shipment_id),
        )
        return False
    route_id = int(path[0])
    ev = evaluate_route_leg(conn, route_id, current, day=day)
    if not bool(ev["usable"]):
        conn.execute(
            "UPDATE commercial_shipments SET status='stalled',current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
            (day + 3, shipment_id),
        )
        return False
    due = day + max(1, int(math.ceil(float(ev["days"]))))
    meta = json.loads(sh["metadata_json"] or "{}")
    meta["segment_target_location_id"] = int(ev["target"])
    meta["planned_path"] = [int(x) for x in path]
    meta["segment_hazard_pressure"] = float(ev["hazard"])
    conn.execute(
        """UPDATE commercial_shipments SET status='in_transit',current_route_id=?,segment_due_day=?,next_review_day=?,metadata_json=?
           WHERE id=?""",
        (route_id, due, due, json.dumps(meta, sort_keys=True), shipment_id),
    )
    return True


def _deliver(conn: sqlite3.Connection, shipment: sqlite3.Row, day: int) -> None:
    if str(shipment["status"]) == "delivered":
        return
    meta = json.loads(shipment["metadata_json"] or "{}")
    procurement_id = meta.get("seek_procurement_contract_id")
    if procurement_id is not None:
        contract = conn.execute("SELECT * FROM seek_procurement_contracts WHERE id=?", (int(procurement_id),)).fetchone()
        conn.execute(
            """UPDATE commercial_shipments SET status='delivered',current_location_id=destination_location_id,
               current_route_id=NULL,segment_due_day=NULL,next_review_day=?,arrived_day=? WHERE id=?""",
            (day, day, int(shipment["id"])),
        )
        if contract and str(contract["status"]) != "fulfilled":
            total = float(contract["quantity"]) * float(contract["unit_price"])
            conn.execute("UPDATE civilian_enterprises SET cash=cash+?,reputation=MIN(100,reputation+?),updated_day=? WHERE id=?",
                         (total, min(2.5,float(contract["quantity"])*.08), day, int(contract["seller_enterprise_id"])))
            conn.execute("UPDATE seek_procurement_contracts SET status='fulfilled',fulfilled_day=? WHERE id=?", (day, int(procurement_id)))
            good = conn.execute("SELECT good_key FROM market_goods WHERE id=?", (int(contract["good_id"]),)).fetchone()
            if contract["buyer_polity_id"] is not None and good and str(good[0]) == "horses_remounts":
                quality=float(contract["agreed_quality"]); qty=float(contract["quantity"]); bump=min(8.0,qty*.22*(.65+quality/100.0*.5))
                conn.execute("UPDATE military_logistics_profiles SET transport_capacity=MIN(100,transport_capacity+?),readiness=MIN(100,readiness+?),next_review_day=MIN(next_review_day,?) WHERE polity_id=?",
                             (bump,bump*.35,day+1,int(contract["buyer_polity_id"])))
                conn.execute("UPDATE political_polities SET treasury_pressure=MIN(100,treasury_pressure+?) WHERE id=?",
                             (min(5.0,total/450.0),int(contract["buyer_polity_id"])))
            if contract["intent_id"] is not None:
                try:
                    from .seeking import mark_intent_fulfilled
                    mark_intent_fulfilled(conn,int(contract["intent_id"]),detail={"kind":"procurement","contract_id":int(procurement_id),"shipment_id":int(shipment["id"])})
                except (ImportError,sqlite3.OperationalError):
                    pass
        return
    conn.execute(
        """INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
             quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
        (
            int(shipment["recipient_enterprise_id"] if "recipient_enterprise_id" in shipment.keys() and shipment["recipient_enterprise_id"] is not None else shipment["enterprise_id"]), int(shipment["destination_location_id"]), int(shipment["good_id"]),
            float(shipment["quantity"]), day,
            json.dumps({"authority":"ENGINE_DERIVED", "source_shipment_id":int(shipment["id"])}, sort_keys=True),
        ),
    )
    conn.execute(
        """UPDATE commercial_shipments SET status='delivered',current_location_id=destination_location_id,
           current_route_id=NULL,segment_due_day=NULL,next_review_day=?,arrived_day=? WHERE id=?""",
        (day, day, int(shipment["id"])),
    )
    try:
        from .merchant import settle_delivered_shipment
        delivered = conn.execute("SELECT * FROM commercial_shipments WHERE id=?", (int(shipment["id"]),)).fetchone()
        settle_delivered_shipment(conn, delivered, day)
    except (ImportError, sqlite3.OperationalError):
        pass


def arrange_shipment(
    conn: sqlite3.Connection,
    enterprise_id: int,
    source_production_site_id: int,
    quantity: float,
    destination_location_id: int,
    *,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Dispatch owned cargo from real production inventory into a persistent in-transit record.

    Dispatch is the conservation boundary: source inventory is reduced in the same transaction
    that creates the shipment. Delivery later moves that same quantity into commercial_stock.
    """
    quantity = float(quantity)
    if quantity <= 0:
        raise ValueError("shipment quantity must be positive")
    e = conn.execute("SELECT * FROM civilian_enterprises WHERE id=? AND status IN ('active','strained')", (enterprise_id,)).fetchone()
    if not e:
        raise ValueError("enterprise is not active for shipment")
    site = conn.execute("SELECT * FROM production_sites WHERE id=? AND active=1", (source_production_site_id,)).fetchone()
    if not site or int(site["enterprise_id"]) != int(enterprise_id):
        raise ValueError("production site does not belong to enterprise")
    if float(site["inventory"]) + 1e-9 < quantity:
        raise ValueError("insufficient source inventory")
    if e["location_id"] is None:
        raise ValueError("enterprise has no origin location")
    origin = int(e["location_id"])
    destination = int(destination_location_id)
    if destination == origin:
        raise ValueError("shipment destination must differ from origin")
    if not conn.execute("SELECT 1 FROM locations WHERE id=?", (destination,)).fetchone():
        raise ValueError("unknown shipment destination")
    day = _day(conn)
    if not find_route_path(conn, origin, destination, day=day):
        raise ValueError("no traversable route to shipment destination")

    conn.execute("UPDATE production_sites SET inventory=inventory-? WHERE id=?", (quantity, source_production_site_id))
    payload = {"authority":"ENGINE_DERIVED", "cargo_custody":"shipment", **(metadata or {})}
    cur = conn.execute(
        """INSERT INTO commercial_shipments(
               enterprise_id,source_production_site_id,good_id,quantity,origin_location_id,destination_location_id,
               current_location_id,next_review_day,status,started_day,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,'in_transit',?,?)""",
        (enterprise_id, source_production_site_id, int(site["good_id"]), quantity, origin, destination,
         origin, day, day, json.dumps(payload, sort_keys=True)),
    )
    sid = int(cur.lastrowid)
    _begin_next_leg(conn, sid, day)
    return sid



def arrange_stock_shipment(conn: sqlite3.Connection, enterprise_id: int, source_stock_id: int, quantity: float,
                           destination_location_id: int, *, recipient_enterprise_id: int | None = None,
                           trade_contract_id: int | None = None, carrier_enterprise_id: int | None = None,
                           freight_cost: float = 0.0, metadata: dict[str, Any] | None = None) -> int:
    quantity = float(quantity)
    if quantity <= 0:
        raise ValueError("shipment quantity must be positive")
    stock = conn.execute("SELECT * FROM commercial_stock WHERE id=? AND enterprise_id=?", (source_stock_id, enterprise_id)).fetchone()
    if not stock or float(stock["quantity"]) + 1e-9 < quantity:
        raise ValueError("insufficient owned commercial stock")
    origin = int(stock["location_id"]); destination = int(destination_location_id); day = _day(conn)
    if origin == destination:
        raise ValueError("shipment destination must differ from origin")
    if not find_route_path(conn, origin, destination, day=day):
        raise ValueError("no traversable route to shipment destination")
    conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?", (quantity, day, source_stock_id))
    cur = conn.execute(
        """INSERT INTO commercial_shipments(
               enterprise_id,source_stock_id,recipient_enterprise_id,trade_contract_id,carrier_enterprise_id,freight_cost,
               good_id,quantity,origin_location_id,destination_location_id,current_location_id,next_review_day,status,started_day,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'in_transit',?,?)""",
        (enterprise_id, source_stock_id, recipient_enterprise_id, trade_contract_id, carrier_enterprise_id,
         max(0.0, float(freight_cost)), int(stock["good_id"]), quantity, origin, destination, origin, day, day,
         json.dumps({"authority":"ENGINE_DERIVED", "cargo_custody":"shipment", **(metadata or {})}, sort_keys=True)),
    )
    sid = int(cur.lastrowid)
    _begin_next_leg(conn, sid, day)
    return sid

def cancel_shipment(conn: sqlite3.Connection, shipment_id: int, *, return_to_source: bool = False) -> None:
    sh = conn.execute("SELECT * FROM commercial_shipments WHERE id=?", (shipment_id,)).fetchone()
    if not sh:
        raise ValueError("unknown shipment")
    if str(sh["status"]) in {"delivered", "cancelled", "lost"}:
        return
    # Cargo may only return to production inventory while physically still at origin.
    if return_to_source:
        has_source = sh["source_production_site_id"] is not None or ("source_stock_id" in sh.keys() and sh["source_stock_id"] is not None)
        if int(sh["current_location_id"]) != int(sh["origin_location_id"]) or not has_source:
            raise ValueError("cargo can only be returned to source before leaving origin")
        if sh["source_production_site_id"] is not None:
            conn.execute("UPDATE production_sites SET inventory=inventory+? WHERE id=?", (float(sh["quantity"]), int(sh["source_production_site_id"])))
        elif "source_stock_id" in sh.keys() and sh["source_stock_id"] is not None:
            conn.execute("UPDATE commercial_stock SET quantity=quantity+?,updated_day=? WHERE id=?", (float(sh["quantity"]), _day(conn), int(sh["source_stock_id"])))
    conn.execute(
        "UPDATE commercial_shipments SET status='cancelled',current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
        (_day(conn), shipment_id),
    )


def next_logistics_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row = conn.execute(
        """SELECT MIN(next_review_day) FROM commercial_shipments
           WHERE status IN ('in_transit','stalled') AND next_review_day>? AND next_review_day<=?""",
        (after_day, end_day),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _process_shipment(conn: sqlite3.Connection, sh: sqlite3.Row, day: int, event_logger: Callable[..., int] | None = None) -> bool:
    status = str(sh["status"])
    if status == "stalled":
        return _begin_next_leg(conn, int(sh["id"]), day)
    due = sh["segment_due_day"]
    if due is None or int(due) > day:
        return False
    meta = json.loads(sh["metadata_json"] or "{}")
    target = meta.get("segment_target_location_id")
    if target is None:
        conn.execute("UPDATE commercial_shipments SET status='stalled',next_review_day=? WHERE id=?", (day + 3, int(sh["id"])))
        return False
    conn.execute("UPDATE commercial_shipments SET current_location_id=? WHERE id=?", (int(target), int(sh["id"])))
    refreshed = conn.execute("SELECT * FROM commercial_shipments WHERE id=?", (int(sh["id"]),)).fetchone()
    if int(target) == int(sh["destination_location_id"]):
        _deliver(conn, refreshed, day)
        if event_logger:
            ent = conn.execute("SELECT name FROM civilian_enterprises WHERE id=?", (int(sh["enterprise_id"]),)).fetchone()
            good = conn.execute("SELECT name FROM market_goods WHERE id=?", (int(sh["good_id"]),)).fetchone()
            event_logger(day=day, event_type="commerce:shipment_arrived", title="Commercial shipment arrived",
                         summary=f"{ent[0] if ent else 'An enterprise'} delivered {float(sh['quantity']):g} units of {good[0] if good else 'goods'}.",
                         severity=1, source_actor_id=None, target_actor_ids=(), location_id=int(sh["destination_location_id"]))
        return True
    return _begin_next_leg(conn, int(sh["id"]), day)


def process_due_logistics(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    rows = conn.execute(
        """SELECT * FROM commercial_shipments WHERE status IN ('in_transit','stalled') AND next_review_day<=?
           ORDER BY next_review_day,id""", (day,)
    ).fetchall()
    changed = 0
    for sh in rows:
        if _process_shipment(conn, sh, day, event_logger=event_logger):
            changed += 1
    return {"due": len(rows), "changed": changed}


def logistics_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "in_transit": int(conn.execute("SELECT COUNT(*) FROM commercial_shipments WHERE status IN ('in_transit','stalled')").fetchone()[0]),
        "delivered": int(conn.execute("SELECT COUNT(*) FROM commercial_shipments WHERE status='delivered'").fetchone()[0]),
        "stock_quantity": float(conn.execute("SELECT COALESCE(SUM(quantity),0) FROM commercial_stock").fetchone()[0]),
        "cargo_quantity": float(conn.execute("SELECT COALESCE(SUM(quantity),0) FROM commercial_shipments WHERE status IN ('in_transit','stalled')").fetchone()[0]),
    }
