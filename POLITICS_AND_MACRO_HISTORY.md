# v0.23 — Politics, State Transformation & Macro-History

v0.23 makes political geography authoritative campaign state rather than a label on locations.

The system distinguishes:

- polity institutions from ordinary institutions;
- rulers from the polity itself;
- dynasties from offices;
- territorial control from territorial claims;
- diplomatic relations from hierarchy links;
- succession claims from automatic inheritance;
- structural political processes from scripted plot events;
- current borders from append-only political history.

## Core invariant

> **States persist through institutions and territory, not through plot protection. Borders, rulers, hierarchies, and even states themselves may change through ordinary campaign causality.**

## Political polities

A polity is backed by an institution actor and carries campaign-state fields for legitimacy, stability, administrative capacity, military capacity, treasury pressure, succession method, ruler, ruling dynasty, status, and review cadence.

No polity is seeded automatically by the engine. The World Bible remains the source for setting-level political facts; campaign state only becomes concrete when configured or crystallized.

## Rulers, dynasties, and succession

Rulers are character actors. Dynasties are persistent lineages with members and prestige. Succession claims persist separately with legitimacy, support, and priority.

When a ruler is no longer living, shared world-time review opens a real succession vacancy. Established claims may resolve a clear routine succession; close claims leave a persisted succession crisis rather than choosing arbitrarily.

Elapsed time does not manufacture heirs, dynasties, or claimants.

## Territory

`territorial_control` gives each crystallized location at most one authoritative controller. Control can be direct, vassal, occupied, disputed, or chartered.

A transfer updates both the political control table and the compatibility `locations.political_owner` field. Every transfer writes an append-only political-history entry.

Dissolving a territorial polity is illegal unless its controlled locations are first transferred or a successor polity is supplied. This prevents orphan territory.

## Claims and political pressure

Territorial claims have legitimacy, support, pressure, review cadence, and a campaign-configured resolution policy. Claims do not change borders merely because they exist.

If a claim accumulates enough pressure, the configured campaign policy may:

- leave it as a pressed dispute;
- recognize it without changing control; or
- transfer control.

The engine therefore supports actual long-run political divergence while keeping the cause explicit and auditable.

## Political hierarchy and interstate relations

Inter-polity relations persist stance, trust, tension, and a coarse relation kind.

Separate hierarchy links support vassalage, protectorates, federations, personal unions, and tributary relationships. Hierarchical cycles are rejected so a state cannot become its own indirect overlord.

## Structural political processes

Campaign-configured political processes can change legitimacy, stability, treasury pressure, territorial integration, or structural pressure through story time. Thresholds may create disputes, claims, or fragmentation state without requiring the player to be present.

These processes are intentionally abstract. They model political causality, not tactical methods of violence.

## Macro-history ledger

All meaningful political transitions write to `political_history`: ruler changes, succession crises, territorial transfers, hierarchy creation/end, dissolution, and other state transformations. The current political map can therefore diverge dramatically while remaining historically traceable.

## Camera boundary

Scene packets receive bounded political context. Narration may reflect established political state but cannot preserve old borders for convenience or invent political change in prose.

## Deliberately deferred

v0.23 does not attempt to model every tax office, law code, parliament, court, or military campaign. Detailed territorial war execution remains owned by existing combat/world systems. Political institutions own status, legitimacy, succession, relationships, claims, hierarchy, and the macro consequences of resolved events.
