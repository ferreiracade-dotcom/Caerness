# Caerness Engine v0.30.0 — Current-Canon Economic Substrate Handoff

## Status
Regression-clean checkpoint. Ten-year gate remains closed.

## Added in v0.30.0
- Sparse current-canon aggregate material economy layered over the v0.29 conservation-safe logistics owner.
- Eight abstract goods/price indices and 49 market conditions across explicit commercial hubs. Numeric supply, demand, prices and capacities are tagged `CAMPAIGN_CALIBRATION`; they are not canon currency or census claims.
- Market presence is kept separate from manufacture: distribution hubs can trade goods without receiving fake local production sites.
- Five production sites only where MASTER FINAL explicitly supports making/refining/assembling: Still Hand provisioning, House Dovell naval supply, Lysmere medical supply, Stonecross metalwork and Redroot Vale Root production.
- Explicit Bible seats repair three structured-seed omissions without arbitrary defaults: Counting House -> Aldergate; Still Hand -> Toll's Reach; Brass Lantern House -> Toll's Reach.
- Five aggregate infrastructure footprints for explicitly described warehouse/caravan/medical/port infrastructure. These are tagged aggregate and are not literal building counts.
- Four Brass Lantern Grand Sales placed on relative campaign days 90/180/270/360 because the Bible explicitly says four major annual sales. Exact in-world calendar dating remains open and no lots/objects are invented.
- No specific credit agreement, borrower, debt, ownership share or household budget was invented.

## Verification
- Full cumulative test suite passes through v0.30.0, including the historical 20/40/120-year stress tests.
- `v30_test.py` verifies calibration metadata, market-vs-production separation, explicit seat repair, no invented credit, aggregate infrastructure marking, activation idempotency and non-negative production resolution.
- Clean current-canon unattended year reaches day 365 with 10 active enterprises, 49 markets, 5 production sites, 5 aggregate infrastructure footprints and all 8 explicit households intact.
- Four autonomous freight shipments were dispatched through the v0.29 domain-action/logistics path: two arrived within the year and two remained legitimately in transit at day 365.
- Brass Lantern's four campaign-relative Grand Sales all resolved; because no lots were canon-supported, zero lots were fabricated.
- Ten-year gate failures fell from 29 at v0.29 to 25 after the v0.30 ordinary year.

## Current limit
The next high-leverage work is to populate runnable-but-empty current-canon systems before implementing specialized missing mechanics. Priority targets: current ecology/cultivation sites, manuals/knowledge custody, religion/observance, culture/news/information channels and continental polity/process state. After those are active, the remaining failures will be dominated by real mechanism gaps (cultivation Realization, Hollow succession, tournament/combat autonomy, gambling/prizefighting, organized-crime lifecycle and policing) rather than empty tables.
