"""ROUTES-01 — the World Bible's connective geography as a travel graph.

"The geography is intentionally connective rather than zoned."  The seed imported only the eleven routes
that carry explicit canon travel times, leaving 121 of 133 places (including Crownhold and every outer
kingdom) unreachable, so trade, travel, news, tournaments, smuggling and war silently could not reach
most of the world.  This module adds the rest of the canon network, once, as opening geography:

* the seed's 34 prose-adjacency road edges and the World Bible's Hearth skeleton (Crownlands–Aldergate–
  Cairnholt corridor, South Road, western roads through Stonecross, Eastern Road, Fellmarch roads, and the
  Longwater as a river route);
* each outer kingdom's internal roads from its canon centres (hub = where canon says roads converge);
* the canon frontier corridors between states, and the named sea lanes.

``base_days`` is ordinary caravan travel.  Canon travel times are used where given; elsewhere days are
estimated at the same scale as canon's Hearth table (Cairnholt → Toll's Reach is 12–16 days).  Every route
records its basis and a certainty: ``canon_route`` (canon names the link), ``canon_corridor`` (canon names
the corridor; days estimated), or ``working_placement`` (canon names the place but not its exact link).
"""
from __future__ import annotations

import sqlite3
from typing import Any

AUTHORITY = "ROUTES01_CANON_NETWORK"

# (seed key a, seed key b, kind, ordinary days, certainty, basis)
CANON_ROUTES: tuple[tuple[str, str, str, float, str, str], ...] = (
    # --- Hearth circuits and prose adjacency (seed geography_graph road edges) ---------------------
    ("highford", "stillwater", "road", 2.0, "canon_route", "Cairnholt Circuit: Highford → Stillwater → Cairnholt → Bell Hollow"),
    ("stillwater", "cairnholt", "road", 1.5, "canon_route", "Cairnholt Circuit"),
    ("cairnholt", "bell-hollow", "road", 1.5, "canon_route", "Cairnholt Circuit"),
    ("waymeet", "renlow-estates", "road", 1.25, "canon_route", "South Road Circuit: Cairnholt → Waymeet → Renlow → Amber Court (Waymeet→Amber Court 2–3 days)"),
    ("renlow-estates", "amber-court", "road", 1.25, "canon_route", "South Road Circuit"),
    ("amber-court", "redford", "road", 4.0, "canon_route", "South Road: Waymeet and Amber Court toward Redford and Toll's Reach"),
    ("redford", "tolls-reach", "road", 5.0, "canon_route", "South Road Circuit: Redford → southern towns → Toll's Reach"),
    ("cairnholt", "rivermoor", "river", 3.0, "canon_route", "The Longwater runs through Cairnholt ... down toward Rivermoor"),
    ("rivermoor", "seven-bridges", "river", 4.0, "canon_route", "River Circuit: Cairnholt / Rivermoor → ferry country → Seven Bridges → Blackfen → Toll's Reach"),
    ("seven-bridges", "blackfen", "river", 3.0, "canon_route", "River Circuit"),
    ("blackfen", "tolls-reach", "river", 4.0, "canon_route", "River Circuit; the lower Longwater links Blackfen and Toll's Reach"),
    ("nine-ferries-country", "rivermoor", "river", 2.0, "canon_route", "the lower Longwater links Rivermoor, Nine Ferries country, Blackfen"),
    # Ferry country spreads along the river between Rivermoor and Seven Bridges; its link to Blackfen is not a
    # shortcut past the canon order (Rivermoor → ferry country → Seven Bridges → Blackfen → Toll's Reach).
    ("nine-ferries-country", "blackfen", "river", 4.0, "canon_route", "the lower Longwater links Rivermoor, Nine Ferries country, Blackfen"),
    ("redford", "kastel-sphere", "road", 2.0, "canon_route", "Fellmarch Circuit: Redford → Kastel sphere → Mirehold / Brackwater"),
    ("kastel-sphere", "northern-fellmarch", "road", 2.0, "canon_route", "Fellmarch roads (seed prose adjacency)"),
    ("northern-fellmarch", "mirehold", "road", 2.0, "canon_route", "Fellmarch roads linking Redford, Mirehold, Undertow-heavy towns"),
    ("mirehold", "reedmark-blackwood-country", "road", 2.5, "canon_route", "Fellmarch Circuit: ... deeper Reedmark / Blackwood country"),
    ("mirehold", "brackwater-springs", "road", 1.0, "canon_route", "Fellmarch Circuit: Mirehold / Brackwater"),
    ("stonepool", "kastel-sphere", "road", 1.5, "canon_route", "seed prose adjacency"),
    ("cairnholt", "eastwatch", "road", 3.5, "canon_route", "the Eastern Road crosses through Eastwatch and Lysmere (Cairnholt → Lysmere 5–7 days)"),
    ("eastwatch", "lysmere", "road", 2.5, "canon_route", "Eastern Circuit: Cairnholt → Eastwatch → Lysmere"),
    ("lysmere", "eastern-hearth-towns", "road", 2.0, "canon_route", "Eastern Circuit: Lysmere → eastern towns"),
    ("eastern-hearth-towns", "grand-coven-complex", "road", 4.0, "canon_route", "Cairnholt → Grand Coven 10–14 days via the Eastern Road"),
    ("eastern-hearth-towns", "hollow-adjacent-eastern-hosts", "road", 2.0, "canon_route", "Eastern Circuit: ... occasional Hollow-adjacent hosts"),
    ("cairnholt", "stonecross", "road", 4.0, "canon_route", "routes west climb toward Stonecross, Aldenmoor and the Spine (Cairnholt → Aldenmoor 5–7 days)"),
    ("stonecross", "aldenmoor", "road", 2.0, "canon_route", "Spine Circuit: Stonecross → Aldenmoor → White Laurel foothills"),
    ("aldenmoor", "white-laurel-foothills", "road", 2.0, "canon_route", "Spine Circuit"),
    ("white-laurel-foothills", "long-stair", "trail", 2.0, "canon_route", "Spine Circuit: ... Long Stair towns"),
    ("long-stair", "long-stair-towns", "trail", 1.0, "canon_route", "Spine Circuit"),
    ("long-stair-towns", "silent-peak-outer-approach", "trail", 3.0, "canon_route", "seed prose adjacency (Cairnholt → Silent Peak outer approach 8–12 days + mountain)"),
    ("silent-peak-outer-approach", "silent-peak", "trail", 2.0, "canon_route", "ascent and local terrain remain decisive"),
    ("long-stair-towns", "seasonal-mountain-gatherings", "trail", 1.5, "canon_route", "Spine Circuit: ... seasonal mountain gatherings"),
    ("waymeet", "wrenfield-seat-district", "road", 1.0, "canon_route", "seed prose adjacency"),
    ("waymeet", "southern-road-belt", "road", 4.0, "canon_route", "southern routes pass Waymeet ... before reaching Toll's Reach"),
    ("southern-road-belt", "tolls-reach", "road", 6.0, "canon_route", "seed prose adjacency (Cairnholt → Toll's Reach 12–16 days)"),
    ("ashgrave-margin", "greywatch", "road", 2.0, "canon_route", "seed prose adjacency; Greywatch (Ashgrave)"),
    # --- Crownlands ------------------------------------------------------------------------------------
    ("crownhold", "aldergate", "road", 3.0, "canon_corridor", "Crownlands–Aldergate–Cairnholt corridor; Aldergate the inland hinge of the capital sphere"),
    # Canon places Highford both on the capital's northern edge (Crownlands) and on the Cairnholt Circuit
    # (Hearth, 3.5 days from Cairnholt).  The circuit is kept; this link is long enough that the capital is
    # not closer to Cairnholt via Highford than via the Aldergate corridor.
    ("crownhold", "highford", "road", 4.0, "canon_corridor", "Highford stands on the northern edge where the capital roads open onto the plains"),
    ("crownhold", "mapleford", "road", 2.0, "canon_corridor", "Mapleford: old administrative city on a principal river approach"),
    ("crownhold", "everborn-quay", "road", 1.5, "canon_corridor", "Everborn Quay, the working lake port of the capital"),
    ("aldergate", "everborn-quay", "road", 1.0, "canon_corridor", "Aldergate sits near Lake Everborn as the hinge of lake traffic"),
    ("crownhold", "white-granary", "road", 1.0, "canon_corridor", "White Granary, the capital's state-storage complex"),
    ("aldergate", "cairnholt", "river", 6.0, "canon_route", "The Longwater runs from the Crownlands and Aldergate sphere through Cairnholt"),
    # Talonkeep is a Frontier Command on "the armed Thornward corridor"; the provisional continental map draws it
    # in the east toward Thornward.
    ("eastwatch", "talonkeep", "road", 3.0, "working_placement", "Frontier Commands (Eastwatch, Talonkeep) hold the imperial marches, especially the armed Thornward corridor; continental map places it east"),
    # --- Hearth places canon names without an exact link ------------------------------------------------
    ("cairnholt", "corr-seat-district", "road", 1.5, "working_placement", "Central Hearth estate district"),
    # Canon names these Hearth settlements without placing them; the provisional continental map draws them in the
    # east (Oakridge and Verenwood toward Thornward, Britterwatch above Ashgrave).
    ("eastwatch", "oakridge", "road", 2.5, "working_placement", "Hearth settlement; continental map places it east near the Eastern Hearth"),
    ("eastwatch", "verenwood", "road", 3.0, "working_placement", "Hearth settlement; continental map places it east toward Thornward"),
    ("greywatch", "britterwatch", "road", 2.5, "working_placement", "Hearth settlement; continental map places it above Ashgrave"),
    ("cairnholt", "deepwell", "road", 2.5, "working_placement", "Hearthlands cultivation site, exact placement open"),
    ("cairnholt", "redroot-vale", "road", 3.0, "working_placement", "Hearthlands cultivation region, exact placement open"),
    ("cairnholt", "clearwell", "road", 2.0, "working_placement", "Hearthlands commercial cultivation site"),
    ("cairnholt", "founders-cut", "road", 2.5, "working_placement", "Hearthlands historic martial site"),
    ("waymeet", "greywatch", "road", 3.0, "working_placement", "Ashgrave occupies the south-central country off the south/central road system"),
    ("greywatch", "ashgrave-wells", "road", 1.0, "working_placement", "Ashgrave cultivation site"),
    ("white-laurel-foothills", "white-laurel-heights", "trail", 1.5, "working_placement", "White Laurel's highland ascent"),
    ("long-stair", "stonewake", "trail", 1.5, "working_placement", "Spine cultivation caverns"),
    # Stonegate Pass crosses the northern Spine.  Canon: the Spineward Provinces "hold the passes ... of the Spine's
    # eastern slopes"; "Stonegate and Spine routes move mountain stock" (a trade crossing; canon lists no
    # Greywood–Empire war frontier because the Spine is the barrier).  The provisional continental map puts it south
    # of Raven Pass, level with eastern Greywood; canon ties Mistral Keep to Raven Pass, so its Greywood end is Oakspire.
    ("stonecross", "stonegate-pass", "pass", 3.0, "canon_corridor", "Stonegate and Spine routes move mountain stock; routes west climb through Stonecross into the Spine"),
    ("stonegate-pass", "oakspire", "pass", 4.0, "working_placement", "far side of Stonegate: eastern Greywood (provisional continental map; canon ties Mistral Keep to Raven Pass instead)"),
    # --- Frontier corridors between states --------------------------------------------------------------
    ("highford", "ravenfield", "road", 10.0, "canon_corridor", "The Northern Plains lie between the Crownlands and Dunmoor; Ravenfield is Dunmoor's broad heartland"),
    ("stoneford", "westbrook", "road", 1.5, "canon_corridor", "Westbrook–Stoneford river country: reliable crossings and easy army routes"),
    ("northwatch", "raven-pass", "pass", 2.0, "canon_corridor", "terrain rises toward Raven Pass, anchored by Dunmoor's Northwatch"),
    ("raven-pass", "mistral-keep", "pass", 2.0, "canon_corridor", "... and Greywood's Mistral Keep"),
    ("caelshore", "stormwatch", "road", 6.0, "working_placement", "Greywood–Windmere: wooded and coastal south (endpoints working)"),
    ("tolls-reach", "saltmere", "sea", 3.0, "canon_route", "Toll's Reach → Saltmere: 4–7 days by road; often ship"),
    ("saltmere", "southbay", "sea", 6.0, "canon_corridor", "Windmere–Sunreach: Saltmere–Southbay trade"),
    ("redford", "kingsway-pass", "pass", 6.0, "canon_corridor", "southern routes pass Redford and the Fellmarch before turning toward the outer states"),
    ("tolls-reach", "kingsway-pass", "pass", 4.0, "working_placement", "Toll's Reach, a major physical gateway; the provisional continental map draws Kingsway Pass beside it"),
    ("kingsway-pass", "brightspine", "pass", 4.0, "canon_corridor", "Kingsway Pass through the southern Spine; Brightspine at the southern mountain approaches"),
    ("dunbriar", "highcairn", "road", 4.0, "canon_corridor", "Thornward–Stormhollow broken southern ridges; Highcairn controls the Thornward road"),
    ("sableton", "brightspine", "road", 5.0, "working_placement", "Sunreach–Stormhollow: one direct corridor, Sableton access (Sunreach endpoint working)"),
    # --- Dunmoor ----------------------------------------------------------------------------------------
    ("ravenfield", "northmarch", "road", 3.0, "working_placement", "Ravenfield and Northmarch on the Dunmoor side of the Greywood frontier"),
    ("ravenfield", "stoneford", "road", 3.0, "working_placement", "Stoneford: river tolls and iron country feeding the crown's armour economy"),
    ("ravenfield", "northwatch", "road", 4.0, "working_placement", "Northwatch and the northern military estates"),
    # --- Greywood ---------------------------------------------------------------------------------------
    ("eldenfell", "westbrook", "road", 3.0, "working_placement", "a town has owed levy to Eldenfell for four hundred years"),
    ("eldenfell", "oakspire", "road", 2.0, "working_placement", "Greywood working settlement"),
    ("eldenfell", "mistral-keep", "road", 4.0, "working_placement", "Greywood's frontier anchor"),
    ("eldenfell", "caelshore", "road", 3.0, "working_placement", "Greywood coast"),
    ("caelshore", "mornlight-isles", "sea", 1.0, "working_placement", "the Mornlight Isles off Greywood's shore"),
    # --- Windmere ---------------------------------------------------------------------------------------
    ("saltmere", "stormwatch", "sea", 3.0, "working_placement", "Windmere's chartered ports"),
    ("saltmere", "silvercove", "road", 3.0, "working_placement", "Windmere's chartered ports"),
    # --- Sunreach ---------------------------------------------------------------------------------------
    ("brightspine", "brightspine-foothills", "road", 1.0, "canon_corridor", "Brightspine, southern mountain-and-foothill country"),
    ("brightspine-foothills", "sunreach", "river", 3.0, "canon_corridor", "the Aster descends from the Brightspine foothills through the central Confederacy"),
    ("sunreach", "goldmarsh", "river", 3.0, "canon_corridor", "... to the low wetlands around Goldmarsh"),
    ("highsun", "sunreach", "road", 3.0, "working_placement", "Highsun in the northern uplands above the central river country"),
    ("sunreach", "southbay", "road", 3.0, "working_placement", "Southbay on the southern coast"),
    ("southbay", "tidefall", "road", 2.0, "working_placement", "Southbay and Tidefall on the southern coast"),
    ("goldmarsh", "southbay", "road", 3.0, "working_placement", "lower river country to the coast"),
    ("southbay", "starfall-isles", "sea", 2.0, "canon_corridor", "Southbay faces the Sunward Sea and Starfall routes"),
    # --- Thornward (Brackenfell: "where the kingdom can reach itself from") --------------------------------
    ("westgate", "brackenfell", "road", 3.0, "canon_corridor", "Brackenfell at the junction of the western roads"),
    ("westgate", "harrowden", "road", 2.0, "working_placement", "Harrowden, a western agricultural valley"),
    ("harrowden", "brackenfell", "road", 2.0, "canon_corridor", "the western roads meet at Brackenfell"),
    ("brackenfell", "alderwall", "road", 2.0, "canon_corridor", "Alderwall controls the main northern road"),
    ("brackenfell", "mossford", "road", 2.0, "working_placement", "Mossford, river and timber city deeper inside the realm"),
    ("brackenfell", "dunbriar", "road", 3.0, "canon_corridor", "the southern route toward Dunbriar and the rough south"),
    ("brackenfell", "stoneheath", "road", 2.0, "canon_corridor", "the interior passes; Stoneheath upland mining town"),
    ("brackenfell", "fenmere", "road", 3.0, "working_placement", "Fenmere, low wet eastern river country"),
    # --- Stormhollow (Stormhollow city: "most important roads converge") -----------------------------------
    ("stormhollow", "highcairn", "road", 3.0, "canon_corridor", "Highcairn, northern fortress town controlling the Thornward road"),
    ("stormhollow", "redcairn", "road", 3.0, "canon_corridor", "Redcairn commands the northern valleys"),
    ("stormhollow", "ironspike", "road", 3.0, "canon_corridor", "Ironspike, the great mountain city"),
    ("stormhollow", "sableton", "road", 4.0, "canon_corridor", "Sableton in the lower south, the kingdom's commercial outlet"),
    ("stormhollow", "ashbarrow", "road", 3.0, "canon_corridor", "Ashbarrow, eastern uplands"),
    ("stormhollow", "greyfen", "road", 2.0, "canon_corridor", "Greyfen, western grain valley"),
    ("stormhollow", "stonewash", "road", 2.0, "canon_corridor", "Stonewash, where mountain rivers converge"),
)

_KIND_PROFILE = {  # reliability, seasonal sensitivity
    "road": (80.0, 1.0), "river": (78.0, 1.2), "sea": (72.0, 1.4), "pass": (65.0, 1.6), "trail": (70.0, 1.3),
}
_DISTRICT_PARENT_DAYS = 1.0


def _loc(conn: sqlite3.Connection, key: str) -> int | None:
    r = conn.execute("SELECT entity_id FROM source_identity_map WHERE entity_kind='location' AND source_key=?", (f"place:{key}",)).fetchone()
    return int(r[0]) if r else None


def _has_route(conn: sqlite3.Connection, a: int, b: int, kind: str) -> bool:
    return conn.execute(
        """SELECT 1 FROM travel_routes WHERE route_kind=? AND ((from_location_id=? AND to_location_id=?)
           OR (from_location_id=? AND to_location_id=?)) LIMIT 1""", (kind, a, b, b, a)).fetchone() is not None


def ensure_canon_route_network(conn: sqlite3.Connection) -> dict[str, Any]:
    """Add the canon network (idempotent) and connect city districts to their city."""
    from .ecology import add_route
    added, missing = 0, []
    for ka, kb, kind, days, certainty, basis in CANON_ROUTES:
        a, b = _loc(conn, ka), _loc(conn, kb)
        if a is None or b is None:
            missing.append(ka if a is None else kb)
            continue
        if _has_route(conn, a, b, kind):
            continue
        rel, seasonal = _KIND_PROFILE[kind]
        if certainty == "working_placement":
            rel -= 5.0
        add_route(conn, a, b, route_kind=kind, base_days=days, reliability=rel, seasonal_sensitivity=seasonal,
                  metadata={"authority": AUTHORITY, "certainty": certainty, "basis": basis, "days_basis": "ordinary caravan travel"})
        added += 1
    # Districts, quays and waystones are part of their city: one short hop.
    districts = 0
    for lid, parent in conn.execute(
            """SELECT l.id,l.parent_location_id FROM locations l JOIN locations p ON p.id=l.parent_location_id
               WHERE p.kind IN ('settlement','medical city/node','scholarly/appraisal node','road-river city','lake port')
               ORDER BY l.id""").fetchall():
        if not _has_route(conn, int(lid), int(parent), "road"):
            add_route(conn, int(parent), int(lid), route_kind="road", base_days=_DISTRICT_PARENT_DAYS, reliability=95.0,
                      seasonal_sensitivity=0.2, metadata={"authority": AUTHORITY, "certainty": "canon_route", "basis": "district of its city"})
            districts += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('routes01_network_version','1')")
    return {"routes01_added": added, "routes01_district_links": districts, "routes01_missing_places": sorted(set(missing))}


def unreachable_places(conn: sqlite3.Connection, hub_name: str = "Cairnholt") -> list[str]:
    """Travel destinations (not seas, ranges or macro-regions) with no route to the hub."""
    import collections
    adj = collections.defaultdict(set)
    for a, b in conn.execute("SELECT from_location_id,to_location_id FROM travel_routes WHERE status IN ('open','restricted')"):
        adj[int(a)].add(int(b)); adj[int(b)].add(int(a))
    hub = conn.execute("SELECT id FROM locations WHERE name=?", (hub_name,)).fetchone()
    seen, stack = set(), [int(hub[0])] if hub else []
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x); stack.extend(adj[x])
    skip = {"sea", "lake", "mountain range", "region", "cultural-geographic region", "river", "frontier region"}
    return sorted(str(r[1]) for r in conn.execute("SELECT id,name,kind FROM locations") if int(r[0]) not in seen and str(r[2]) not in skip)
