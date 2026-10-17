from __future__ import annotations

"""What the World Bible (Part Twenty-Two) says about the underworld, as data.

Every entry carries `locator`, the paragraph refs in docs/superpowers/notes/2026-10-17-underworld-canon.md.
Canon fixes character, names and activities; it gives no sizes, so `density`/`street` and the kind weights are
working calibration derived from that character (source: procedural_calibration_from_canon_character).
Canon leadership of every outfit below is open: never name a boss here.
"""

CALIBRATION_SOURCE = "procedural_calibration_from_canon_character"

# Durable outfits: hold fronts and bottlenecks, never districts (notes section 1, [1738]). Key = institution actor name.
CANON_OUTFITS = {
    "Tallow Family": {
        "location": "Aldergate", "organization_type": "criminal_dynasty", "locator": "[1740]-[1743] [4359] [5910]",
        "fronts": ["warehousing", "cheap lodging", "wagon repair", "animal yards", "freight handling", "small lending"],
        "activities": ["cargo substitution", "stolen goods", "protection", "high-risk debt", "illegal gambling",
                       "warehouse-record manipulation"],
        "violence": "controlled", "members": (50, 80),
    },
    "Greyhook Wharf Company": {
        "location": "Toll’s Reach", "organization_type": "criminal_enterprise", "locator": "[1744]-[1746] [4362] [5913]",
        "fronts": ["dock work", "salvage", "small boats", "warehousing"],
        "activities": ["smuggling through paperwork", "stolen goods", "forged cargo", "fencing"],
        "violence": "contingency", "members": (40, 70),
    },
    "Saltwake Combine": {
        "location": "Saltmere", "organization_type": "syndicate", "locator": "[1807] [4368] [5922]",
        "fronts": ["ship factors", "warehouse interests", "brokerage", "financing"],
        "activities": ["false manifests", "customs evasion", "insurance fraud", "elixir redistribution"],
        "violence": "contingency", "members": (30, 60), "principals": "several",
    },
}

# Networks: no seat, no territory, no head. presence = (place, strength); strength is strong, present or thin.
CANON_NETWORKS = {
    "Painted Veil": {"locator": "[1726]-[1729] [1763] [1318]", "presence": [("Cairnholt", "strong")],
                     "presence_rule": "hearth_cities"},
    "The Hush": {"locator": "[1730]-[1732] [1765]", "presence": [], "presence_rule": "min_population:20000"},
    "Red Board": {"locator": "[1656]-[1660] [4365] [5916]",
                  "presence": [("Cairnholt", "present"), ("Toll’s Reach", "present"), ("Waymeet", "thin"),
                               ("Aldergate", "thin")]},
    "Cormorants": {"locator": "[1735] [1788]",
                   "presence": [("Toll’s Reach", "present"), ("Saltmere", "present"), ("Southbay", "thin"),
                                ("Tidefall", "thin")]},
    # Reckoning (owner ruling 2026-10-17): canon gives no base and its relationships are obscured [4107], but Seth Carrick is
    # one of the Hearth's Sixths [2242]-[2245] and Waymeet is the Hearth's Long Road crossroads where people repeatedly meet
    # [606] [841]: a secret killing institution whose members pass as travellers and whose clients come from everywhere fits
    # there, with thinner reach in Cairnholt and Crownhold [1730]. Mallow: secret cells [1751]; it stays unplaced.
    "The Reckoning": {"locator": "[1734] [4107] [1730] [2242]-[2245] [606] [841]",
                      "presence": [("Waymeet", "strong"), ("Cairnholt", "present"), ("Crownhold", "thin")]},
    "Mallow Coven": {"locator": "[1751]-[1765] [3527]", "presence": [], "presence_rule": "unplaced"},
}

HEARTH_CITIES = ("Cairnholt", "Crownhold", "Aldergate", "Toll’s Reach", "Waymeet", "Lysmere", "Aldenmoor")

KINDS = ("fencing", "smuggling", "lending", "gaming", "prizefighting", "vice", "brokerage", "labour_debt",
         "horse_theft", "fraud")


def _w(**kw):
    return {k: kw.get(k, 0) for k in KINDS}


# density: multiplier on underworld size; street: weight of territorial street gangs; kinds: specialist weights;
# districts: canon-flavoured zone names (real locations where they exist).
SETTLEMENT_CHARACTER = {
    "Toll’s Reach": {"density": 1.9, "street": 1.0, "locator": "[1786]-[1788] [1323]-[1324] [946] [1748]",
                     "kinds": _w(fencing=3, smuggling=4, lending=2, gaming=3, prizefighting=3, vice=3, fraud=1,
                                 brokerage=1),
                     "districts": ["River Quays", "Sea Quays", "Warehouse District", "Greyhook Dock"]},
    "Aldergate": {"density": 1.1, "street": 0.35, "locator": "[1789]-[1791] [1327] [946] [1748]",
                  "kinds": _w(fraud=4, lending=3, fencing=2, gaming=2, smuggling=1, prizefighting=1, brokerage=1),
                  "districts": ["Caravan Quarter", "Exchange Quarter", "Warehouse Row"]},
    "Saltmere": {"density": 2.0, "street": 0.8, "locator": "[1805]-[1809] [946] [1830]",
                 "kinds": _w(smuggling=4, fraud=4, fencing=3, gaming=2, vice=2, prizefighting=3, brokerage=2,
                             lending=1),
                 "districts": ["Sea Quays", "Harbour Warehouses"]},
    "Cairnholt": {"density": 1.1, "street": 0.05, "locator": "[1783]-[1785] [1750] [1304] [1658]",
                  "kinds": _w(brokerage=4, gaming=4, fencing=1, vice=2, fraud=1, lending=1, prizefighting=1),
                  "districts": ["Lantern District"]},
    "Crownhold": {"density": 1.2, "street": 0.1, "locator": "[1798]-[1799] [1750]",
                  "kinds": _w(brokerage=4, fraud=4, vice=2, gaming=2, fencing=1), "districts": []},
    "Waymeet": {"density": 0.8, "street": 0.5, "transient": True, "locator": "[1792]-[1794]",
                "kinds": _w(gaming=4, vice=3, prizefighting=3, lending=1), "districts": ["Contract Row"]},
    "Lysmere": {"density": 0.6, "street": 0.1, "locator": "[1797]",
                "kinds": _w(fraud=3, vice=2, gaming=2, brokerage=1), "districts": []},
    "Aldenmoor": {"density": 0.5, "street": 0.05, "locator": "[1795]-[1796] [1748]",
                  "kinds": _w(fencing=4, fraud=3, brokerage=2), "districts": []},
    "Ravenfield": {"density": 1.2, "street": 0.6, "locator": "[1801]-[1804]",
                   "kinds": _w(prizefighting=4, horse_theft=3, gaming=3, vice=3, fencing=1, lending=1), "districts": []},
    "Stormhollow": {"density": 1.1, "street": 0.5, "locator": "[1822]-[1825]",
                    "kinds": _w(labour_debt=4, lending=3, fraud=2, fencing=1, vice=2, prizefighting=1), "districts": []},
    "Brackenfell": {"density": 0.9, "street": 0.4, "locator": "[1818]-[1821]",
                    "kinds": _w(gaming=2, smuggling=2, fencing=2, vice=2, brokerage=1), "districts": []},
}

# Defaults by political owner or region name (settlements carry political_owner, some a parent region).
REGION_DEFAULTS = {
    "Dunmoor": {"density": 0.8, "street": 0.5, "locator": "[1801]-[1804]",
                "kinds": _w(horse_theft=3, fencing=2, gaming=2, smuggling=1, vice=2, prizefighting=1)},
    "Greywood": {"density": 0.8, "street": 0.2, "locator": "[1810]-[1813]",
                 "kinds": _w(vice=4, lending=2, gaming=2, fencing=1, labour_debt=1)},
    "Sunreach Confederacy": {"density": 0.9, "street": 0.1, "locator": "[1814]-[1817]",
                             "kinds": _w(fraud=4, brokerage=2, smuggling=2, gaming=2, lending=1)},
    "Thornward": {"density": 0.7, "street": 0.5, "locator": "[1818]-[1821]",
                  "kinds": _w(gaming=2, fencing=2, smuggling=1, vice=2, prizefighting=1, lending=1)},
    "Windmere": {"density": 1.0, "street": 0.5, "locator": "[1805]-[1809]",
                 "kinds": _w(smuggling=3, fraud=2, fencing=2, gaming=2, vice=2)},
    "Stormhollow": {"density": 0.9, "street": 0.4, "locator": "[1822]-[1825]",
                    "kinds": _w(labour_debt=4, lending=2, fraud=1, vice=2, fencing=1)},
    "Crownlands": {"density": 0.9, "street": 0.3, "locator": "[1800]",
                   "kinds": _w(fraud=3, fencing=2, smuggling=2, brokerage=1)},
    "Great River Provinces": {"density": 0.9, "street": 0.3, "locator": "[1800]",
                              "kinds": _w(smuggling=3, fraud=2, fencing=2)},
    "North Coast": {"density": 0.9, "street": 0.3, "locator": "[1800]",
                    "kinds": _w(smuggling=4, fraud=2, vice=1, fencing=1)},
    "Spineward Provinces": {"density": 0.8, "street": 0.3, "locator": "[1800] [946]",
                            "kinds": _w(smuggling=3, fencing=2, fraud=1)},
    "Eastern Provinces": {"density": 0.8, "street": 0.3, "locator": "[1800]",
                          "kinds": _w(smuggling=2, fraud=2, fencing=1, gaming=1)},
    "Underheaven Empire": {"density": 0.9, "street": 0.3, "locator": "[1800] [1826]-[1828]",
                           "kinds": _w(fencing=2, fraud=2, gaming=2, lending=1, smuggling=1, vice=1)},
}

# Fighting by place (notes section 1 [1662]-[1693], section 3). legality (prizefight_markets values): licensed, tolerated, unlicensed or criminal; kind: prize_hall, back_room, pit or private_club.
# `venue` is an existing location the market sits at; without one the market sits at the settlement.
FIGHTING = {
    "Toll’s Reach": [
        {"key": "toll-red-yard", "name": "The Red Yard challenge ground", "venue": "The Red Yard", "legality": "licensed",
         "coercion": "voluntary", "pool": 18, "cadence": 21, "locator": "[415]-[417] [1787]"},
        {"key": "toll-dockside-rings", "name": "Toll’s Reach dockside rings", "kind": "back_room", "venue": "River Quays", "legality": "tolerated",
         "coercion": "voluntary", "pool": 16, "cadence": 14, "locator": "[1787]"},
        {"key": "toll-red-board-warehouse-ring", "name": "Red Board warehouse ring", "kind": "pit", "legality": "criminal",
         "coercion": "coercive", "pool": 12, "cadence": 18, "locator": "[1656]-[1660] [1685] [4365]",
         "network": "Red Board"},
    ],
    "Ravenfield": [{"key": "ravenfield-fight-halls", "name": "Ravenfield Closed-Core fight halls", "legality": "tolerated",
                    "coercion": "voluntary", "pool": 26, "cadence": 21, "locator": "[1804]"}],
    "Saltmere": [{"key": "saltmere-prestige-halls", "name": "Saltmere prestige prize halls", "legality": "licensed",
                  "coercion": "voluntary", "pool": 30, "cadence": 25, "locator": "[1808]"}],
    "Waymeet": [{"key": "waymeet-open-prizefighting", "name": "Waymeet open prizefighting", "legality": "tolerated",
                 "coercion": "voluntary", "pool": 18, "cadence": 12, "locator": "[1792]-[1794]"}],
    "Aldergate": [{"key": "aldergate-private-clubs", "name": "Aldergate private fighting clubs", "kind": "private_club", "legality": "criminal",
                   "coercion": "voluntary", "pool": 10, "cadence": 30, "locator": "[1789]-[1791]"}],
    "Stormhollow": [{"key": "stormhollow-debt-pits", "name": "Stormhollow debt pits", "kind": "pit", "legality": "criminal",
                     "coercion": "coercive", "pool": 14, "cadence": 20, "locator": "[1823]-[1825]"}],
    "Brackenfell": [{"key": "thornward-seasonal-promoters", "name": "Thornward seasonal fight promoters",
                     "legality": "tolerated", "coercion": "voluntary", "pool": 12, "cadence": 40,
                     "locator": "[1818]-[1821]"}],
}
