# Caerness v0.31 prose-geography completion audit

## Decision

The v1.1 structured seed was not a closed universe of places. The authoritative schema requires the engine to derive the geographic graph from accepted World Bible prose, import named places as persistent anchors, and preserve uncertainty without requiring coordinates. v0.31 therefore separates **identity certainty** from **placement certainty** and leaves coordinates open unless canon later supplies them.

## Result

The current seed increases from **101 to 133 place records**. Existing stable IDs are preserved where a v1.1 row already represented the same canonical referent. One duplicate `Northern Fellmarch` row that existed only to satisfy a route endpoint is removed and the route is re-linked to the retained identity.

The pass corrects three classes of defect:

1. **Missing canonical referents** — named, causally useful places/sites in MASTER FINAL now receive persistent identities, including White Laurel Heights, Brackwater Springs, Clearwell, Founder’s Cut, The Red Yard and Oldstone Hall, plus load-bearing geographic structures and city subplaces used by government, commerce, culture or travel.
2. **Collapsed/shortened display names** — existing IDs for Deepwell, Stonewake and Long Stair are retained but their canonical display names become `Deepwell Basin`, `Stonewake Caverns`, and `The Long Stair`.
3. **False precision / duplicate geography** — the seed records only supported containment. A place can be canonically real while its exact position remains `UNRESOLVED_WITHIN_REGION` or `WORKING_RELATIVE`; no coordinates, nearest-town relation or travel time are invented to make the graph look complete.

## Geography certainty fields

Every place now carries:

- `identity_certainty` — whether the referent itself is established, working, or an aggregate/relative node;
- `placement_certainty` — how strongly its location within the accepted containment graph is established;
- `coordinate_status` — currently `OPEN_NOT_REQUIRED` for the prose-derived graph;
- `source_anchor` — the World Bible basis for the identity/placement.

These fields intentionally allow a site such as Clearwell to exist and hold access/ecology state while its exact map position remains unresolved.

## Object-type discipline

A named geographic referent is not automatically flattened into a generic town. Cultivation grounds can be locations plus ecology/cultivation-site state; route systems such as The Long Stair remain route-like geographic entities; city districts and compounds are subplaces; historical traces can exist as notable sites without being treated as active cultivation grounds.

## Authority boundary

This pass does **not** settle the still-open detailed cartography, add coordinates, revive the obsolete visual map, or infer sovereignty from Churn influence. The prose graph remains authoritative until a replacement visual map is later drawn from it.
