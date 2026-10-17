"""Room manners per culture, paraphrased from the World Bible (locators are paragraph numbers [N]).

Canon gives no universal bow angles or Stage ladder ([511], [512]); these lines are the grammar of the
room, for the GM to render, not rules for the engine to compute.
"""
from __future__ import annotations

import sqlite3

MANNERS: dict[str, str] = {
    "hearth": ("Formal by default. A bow is grammar, not a Stage calculator: depth, timing and who begins it say the relationship. "
               "Hospitality comes before business. Titles keep distance and over-familiar address insults. Fear tightens formality; "
               "who stays informal reveals old ties."),
    "churn": ("Among the Churned, master and disciple, seniority and lineage protocol rule, and a master's word outlasts a pupil's Stage. "
              "Martial affairs are the Churn's own, but tax and magistrates still apply. Challenges want notice and witnesses; "
              "refusing one is not cowardice."),
    "empire": ("Beyond the Hearth the Empire is the most formal society: office and examination outrank blood, and rank sets distance "
               "and address. Satire at sovereignty is a legal risk. Hearth Rites are kept in private."),
    "court": ("Court is a graded approach: distance is rank, audience is bodily (prostration, eyes lowered until addressed, set forms "
              "of speech). No one stands north of the throne; screen and veil mark access. Office outweighs blood."),
    "dunmoor": ("Landed, confident, martial. Feasts, oaths and land frame talk, and birth matters. A man who breaks an oath or "
                "abandons his dead loses standing without losing a Stage. Witnesses are pressed to attend the rites."),
    "greywood": ("Institutional and precedent-minded: church and guild courtesy, charity, public moral language. 'By what lawful "
                 "authority' is the question asked. Marriage and fidelity carry heavy pressure; vice hides behind respectable fronts."),
    "windmere": ("Fluid, cosmopolitan, bargaining. Foreigners are welcome, credit and access count for more than birth, and the noble "
                 "and merchant lines blur. A bargain is sacred; oaths are sworn under the Turn. Little shocks anyone."),
    "sunreach": ("Civic pride and rivalry, and every city differs. Visible self-made wealth, guild standing and public works count. "
                 "Oaths are taken before the Common Flame, which sits badly with Witnesses."),
    "thornward": ("Practical and frontier: self-sufficient, muster and Warden duty, news by the military roads. Nobles are officeholders "
                  "in a defence system, and the officer who holds a line is prized. The old gods are honoured."),
    "stormhollow": ("Highland, with strong local lordship and worker towns. The hill-fighter and the lord who holds a pass are prized. "
                    "The Keeping of Names honours ancestors, and Keepers settle lineage disputes. Debt can bind industrial workers."),
    "undertow": ("Rougher and less uniform. Personal hierarchy and sworn loyalty, no common code: surety, truce, a neutral host and a "
                 "mediator are the old tools. Violence costs because of relationships."),
    "road": ("Looser: reputation circuits, no membership, personal synthesis. A Waystone's peace is local and rests on reputation, "
             "not rule. A fighter answers only the fights meant to be answered."),
    "default": ("Formality follows power: conduct, distance, address and precedence are keyed to office, birth or martial standing, "
                "and a breach reads loudly. Elders and hosts are deferred to; strangers are read by how they carry themselves."),
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

_BY_POLITY = {"Dunmoor": "dunmoor", "Greywood": "greywood", "Windmere": "windmere", "Sunreach Confederacy": "sunreach",
              "Thornward": "thornward", "Stormhollow": "stormhollow"}


def manners_for(conn: sqlite3.Connection, place_id: int | None, *, churn: bool = False) -> str:
    """The one line of room manners for a place. `churn` picks the Churn line inside the Hearth."""
    from .cultivation import location_in_hearth
    from .standing import _chain, polity_of

    if place_id is None:
        return MANNERS["default"]
    chain = _chain(conn, place_id)
    if not chain:
        return MANNERS["default"]
    names = {str(r["name"]) for r in chain}
    if any("Waystone" in n for n in names):
        return MANNERS["road"]
    if "Crownhold" in names:
        return MANNERS["court"]
    if "Fellmarch" in names:
        return MANNERS["undertow"]
    if location_in_hearth(conn, place_id):
        return MANNERS["churn" if churn else "hearth"]
    polity = polity_of(conn, place_id)
    if polity == "Underheaven Empire":
        return MANNERS["empire"]
    return MANNERS[_BY_POLITY.get(str(polity), "default")]
