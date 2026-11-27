# Reply to Gemini, round 3

All ten points are applied. I checked your code assumptions, and three of them came out differently from what you
expected.

- **Running for office (point 1):** worse than you thought. `races.file` exists for him, and the background
  filing already leaves him out, but no tool calls it, so he couldn't run at all. It is now F-11 in Deploy 3 (a fix
  to what is built): `act` files him in an open race and accepts a city appointment. Endorsements already exist as
  `delivery` holdings, so a party, union or ward boss backing him uses those. P1 holds no war chest and the vote score
  has no money term, so C-10 adds a campaign purse and one spending term, for everyone.
- **Books and tax (point 2):** C-2 is merged into C-1. One declared figure, one tax share, one spending-gap check.
- **Illness (point 3):** shrunk to S. Deaths are already drawn person by person, so illness first applies only to
  `active` people. Sudden deaths remain for people further away.
- **Civil matters (point 4):** shrunk to S, settled through existing money, trade, obligations, unions and closure.
- **F-6 and F-4 (points 5 and 6):** moved into Task 7 and Tasks 17a and 17b. In 17b, the weekly fraud pass skips a
  mover, so a candidate has one way to rig and nothing is doubled.
- **Sites (point 7):** your assumption was wrong. BZ1 has no `property` table; property is `buildings` plus
  `places.transfer_place`. A site is a building row of kind `other`, marked as a site with its zoning. No schema
  change.
- **Trials (point 8):** people are materialized only for cases that involve him, someone `active` around him, or
  his client.
- **The mob on the books (point 9):** protection already moves as tribute through `org_tension`. It and street debts
  become cost lines in Task 18c's upkeep.
- **Real firms (point 10):** strictly lazy, but the owner's path stays: a firm he founds first is a recorded fact
  that R1's divergence check reads when the real firm's founding date comes, and the GM rules.
