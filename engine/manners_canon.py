"""Room manners per culture, paraphrased from the World Bible (locators are paragraph numbers [N]).

Canon gives no universal bow angles or Stage ladder ([511], [512]); these lines are the grammar of the
room, for the GM to render, not rules for the engine to compute.
"""
from __future__ import annotations

import sqlite3

MANNERS: dict[str, str] = {
    'hearth': (
        'Formal by default; a bow is grammar, not a Stage calculator. Hospitality before business. Titles keep distance. Fear tightens formality.'),
    'churn': (
        "Master and disciple, seniority and lineage rule; a master's word outlasts a pupil's Stage. Tax and magistrates still apply. Refusing a challenge is no cowardice."),
    'empire': (
        'The most formal society beyond the Hearth: office and examination outrank blood, rank sets distance and address. Satire at sovereignty is a legal risk.'),
    'court': (
        'Court is a graded approach: distance is rank, audience is bodily (prostration, eyes lowered until addressed). Nobody stands north of the throne. Office outweighs blood.'),
    'dunmoor': (
        'Landed, confident, martial. Feasts, oaths and land frame talk. An oath-breaker or one who abandons his dead loses standing without losing a Stage.'),
    'greywood': (
        'Institutional and precedent-minded: church and guild courtesy, charity, public moral language. Marriage and fidelity carry heavy pressure.'),
    'windmere': (
        'Fluid, cosmopolitan, bargaining. Foreigners welcome; credit and access outweigh birth. A bargain is sacred; little shocks anyone.'),
    'sunreach': (
        'Civic pride and rivalry; every city differs. Visible self-made wealth, guild standing and public works count. Oaths before the Common Flame.'),
    'thornward': (
        'Practical and frontier: self-sufficient, muster and Warden duty. Nobles are officeholders in a defence system; the officer who holds a line is prized.'),
    'stormhollow': (
        'Highland, strong local lordship, worker towns. The hill-fighter and the lord who holds a pass are prized. Keepers of Names settle lineage disputes.'),
    'undertow': (
        'Rougher, less uniform. Personal hierarchy and sworn loyalty, no common code: surety, truce, a neutral host, a mediator. Violence costs because of relationships.'),
    'road': (
        "Looser: reputation circuits, no membership. A Waystone's peace is local and rests on reputation. A fighter answers only the fights meant to be answered."),
    'default': (
        'Formality follows power: distance and address are keyed to office, birth or martial standing, and a breach reads loudly. Elders and hosts are deferred to.'),
}

LOCATORS: dict[str, tuple[str, ...]] = {
    "hearth": ("[510]", "[511]", "[512]", "[513]", "[514]-[516]"),
    "churn": ("[473]-[479]", "[482]-[485]", "[556]-[558]", "[613]", "[854]"),
    "empire": ("[1046]-[1052]", "[1116]", "[1125]", "[1875]"),
    "court": ("[1046]-[1049]", "[1122]", "[1125]"),
    "dunmoor": ("[1135]-[1149]", "[1024]-[1041]", "[1040]", "[1597]"),
    "greywood": ("[1172]-[1176]", "[1173]", "[1450]", "[1601]"),
    "windmere": ("[1152]-[1167]", "[1083]-[1088]", "[1087]"),
    "sunreach": ("[1188]-[1209]", "[1206]", "[1603]"),
    "thornward": ("[1211]-[1222]", "[1220]", "[1605]"),
    "stormhollow": ("[1225]-[1236]", "[1233]", "[1100]", "[1607]"),
    "undertow": ("[599]", "[615]", "[752]-[788]", "[756]"),
    "road": ("[606]-[607]", "[836]-[848]", "[854]"),
    "default": ("[24]", "[488]-[516]"),
}

_NEUTRAL = "Formality follows power: distance and address are keyed to office, birth or standing, and a breach reads loudly. Elders and hosts are deferred to."

_BY_POLITY = {"Dunmoor": "dunmoor", "Greywood": "greywood", "Windmere": "windmere", "Sunreach Confederacy": "sunreach",
              "Thornward": "thornward", "Stormhollow": "stormhollow"}


def culture_key(conn: sqlite3.Connection, place_id: int | None, *, churn: bool = False) -> str:
    """The culture of a place (a key of MANNERS). `churn` picks the Churn culture inside the Hearth."""
    from .cultivation import location_in_hearth
    from .standing import _chain, polity_of

    if place_id is None:
        return "default"
    chain = _chain(conn, place_id)
    if not chain:
        return "default"
    names = {str(r["name"]) for r in chain}
    if any("Waystone" in n for n in names):
        return "road"
    if "Crownhold" in names:
        return "court"
    if "Fellmarch" in names:
        return "undertow"
    if location_in_hearth(conn, place_id):
        return "churn" if churn else "hearth"
    polity = polity_of(conn, place_id)
    if polity == "Underheaven Empire":
        return "empire"
    return _BY_POLITY.get(str(polity), "default")


def manners_for(conn: sqlite3.Connection, place_id: int | None, *, churn: bool = False) -> str:
    """The one line of room manners for a place. `churn` picks the Churn line inside the Hearth.

    A world package supplies its own phrases (data "manners": place kind -> phrase, with a "default");
    a package without cultivation and without phrases gets a neutral line. Only Caerness uses MANNERS."""
    import json
    from .world_package import package_for

    pkg = package_for(conn)
    path = pkg.data.get("manners")
    if path is not None:
        table = json.loads(path.read_text(encoding="utf-8"))
        kind = None
        if place_id is not None:
            row = conn.execute("SELECT kind FROM locations WHERE id=?", (int(place_id),)).fetchone()
            kind = row[0] if row else None
        return str(table.get(kind) or table.get("default") or _NEUTRAL)
    if not pkg.systems.get("cultivation"):
        return _NEUTRAL
    return MANNERS[culture_key(conn, place_id, churn=churn)]
