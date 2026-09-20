# Caerness Engine v0.21 — Religion & Cultural Institutions

## Authority boundary

v0.21 makes religion and cultural institutions persistent simulation state without turning unresolved setting detail into canon.

The engine seeds only three currently named religious traditions as vocabulary: **Hearth Rites**, **the Vigil**, and the **Small True Faith**. It does **not** seed adherents, clergy, feast dates, sacred sites, local institutions, or exact ritual forms. The Small True Faith remains explicitly marked `signoff_pending`, reflecting the current World Bible rather than silently locking its unfinished historical furniture.

The governing rule is:

> Religion is lived social reality through practice, institution, belief, calendar, art, morality, memory, and obligation—not a faction label.

## Religious state

The engine now persists:

- religious traditions and their canon status;
- actor affiliations and participation without forcing one universal exclusive alignment;
- religious institutions with treasury, ritual capacity, charity commitment, authority, and reputation;
- religious offices with standing and seniority, but no automatic promotion;
- campaign-defined observances and recurring ritual calendars;
- actual observance instances and attendance;
- actor, household, or institutional religious obligations;
- sacred sites tied to locations/buildings/institutions;
- domain-specific religious reliability reputation;
- funded patronage from households or enterprises.

Hearth Rites can therefore remain household-centred without requiring a priesthood. The Vigil can support organized institutions. Other local or campaign-defined traditions can use the same substrate.

## Cultural institutions

Cultural institutions are now distinct from businesses. An archive, theatre, performance company, memorial foundation, artistic society, or similar institution can persist as an institutional actor with:

- cultural domain;
- local presence;
- prestige;
- resources;
- public reach;
- continuity;
- recurring or one-off programs.

Programs create actual historical instances and public events. Where a program is deliberately linked to a style movement, it can exert a small bounded influence on local style adoption. Cultural institutions still require resources and can become strained or dissolve.

## Patronage

Patronage is not decorative prose. Household or enterprise funds actually leave the sponsor and enter the supported religious or cultural institution. Insufficient funds do not create money or permit invisible overdraft; the patronage relationship becomes strained.

## Calendar rule

The World Bible explicitly says the Hearth does not need an encyclopedic fixed festival calendar and that exact feast days can be created when stories require them. v0.21 therefore seeds **zero observances**. Dates become campaign history only when explicitly created.

## Player-facing information

Scene packets now include:

- `religious_context`: the protagonist's active affiliations, relevant obligations, visible local religious institutions, and scheduled local observances;
- `cultural_context`: visible local cultural institutions and upcoming programs.

The narrator is explicitly prohibited from inferring private belief from faction, ancestry, office, or public observance.

## Simulation integration

Religious and cultural deadlines participate directly in the authoritative world clock. Observances, obligations, patronage, institutional reviews, and cultural programs create their own due checkpoints alongside NPC reviews, information propagation, civilian systems, health, and other world processes.

Routine observances can happen completely off-camera. The protagonist is not required for them to exist.
