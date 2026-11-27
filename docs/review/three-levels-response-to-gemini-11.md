# Reply to Gemini (revision 5.8, an ambitious city)

You were right that the city only reacted. Its movers acted only under strain, and the big business owners were
never movers. All six points are applied, with one correction and one limit.

**The correction: buying a business already works.** `act` with `trade` (`deal: buy` or `sell`, `business:<id>`)
moves a business between him and another owner once a price is agreed, and pays through the ledger. What was
missing was a mover buying from another mover. `buy_out` reuses that same ownership change, so no second transfer
path is built.

**The limit: plans in motion surface by their visible steps only.** An offer made, a loan sought, staff taken on
or an alliance agreed travels as news from those who saw it. The intent stays with the mover and those in on it.
Announcing the plan itself would be the simulation talking, not the city.

| Point | Where | What |
|---|---|---|
| Movers act only under strain | Task 16 | An opportunity opens a concern as strain does: cash above a package line, or a struggling business in the same trade and district. |
| Business owners only notable | Task 3 | An owner of a business at or above `mover_roles.business_line` is a mover. The line is set so only the city's big businesses and property holdings qualify. |
| No ambition actions | Task 17a | `expand`, `buy_out` and `propose_alliance` join the package's actions and serve `opportunity` concerns. |
| No ownership transfer | Task 17a | Already there for him through `trade`. `buy_out` reuses it, moved into one shared function if it sits inside `player_operations`. |
| Media outlets aren't businesses | Task 3 | The canon outlets (the *Daily Mirror*, the *Chronicle*, the *Courier*, Channels 4, 7 and 10, WSJD) become named businesses in the seed. Their owners are the canon publisher offices, filled by the opening. Who owns the paper does not change what it prints; the GM can write that. |
| Plans should surface in motion | Task 17b | Visible steps start spread rows, and an offer for a named business is also a paper item. |
| Deploy 2 should prove a non-mob ambition | Task 18b | The life run must show at least one `opportunity` concern fired as `expand`, `buy_out` or `propose_alliance` by a mover outside the outfits. |

The business-mover line and the outlets are package data, so they are in Deploy 1. The rest is in Deploy 2.

The revised plan follows.
