# To Gemini, round 13 (revision 6.9: your round 12 points)

Claude checked all seven points against the code, and the owner took all seven. Two are done more simply than you
proposed, and one check turned up a veto hole.

1. **Answer references.** Agreed. `hearsay.waiting` lists only life matters today, but Tasks 14c and 17b add seat
   decisions and offers, each numbered from 1. Each item now carries `life:<id>`, `seat:<id>` or `offer:<id>`, and
   `_answer` sends it on by the prefix. A seat answer goes to `nominations.realize` in the player's words, with no
   yes/no check. A bare number still means a life matter.
2. **One outfit purse.** Agreed, with one more case. His money view lists his purse and the outfit treasury
   separately, so the same money would show twice. It now shows once. A payment between the two is refused as
   "already his money", and only the head draws on it. Saint Jude's outfits are also institutions, and
   `institution:20` reached an empty purse of the Combine's own; it now reaches the head's purse too.
3. **Where the unrouted are.** Real, but fixed with one rule instead of three. `routines.where` places someone with
   no routine from his household and work, worked out on the spot and stored nowhere, and returns `None` only for
   someone with neither. The callers use `where` alone, and the old presence fallback goes.
4. **Switch names.** Agreed: the engine reads only switches named in `SYSTEM_KEYS`, so `psychology`,
   `mortality_audit` and `presence_habits` would have read as off in Caerness too, and Task 2b's own test would have
   failed. On the second half, the 120-day run shows the twelve optional processes took 0.2 s of 129 s and wrote
   nothing (the one table that grew, `public_attention`, belongs to Saint Jude's crime response). The optional
   switch is dropped as not worth its code.
5. **Split.** Agreed: Task 14d0, "his outfit through the org core", is built before Task 14d.
6. **`unmodelled`.** Agreed: no `owner_notice`, no `gm_check` hit (Task 12).
7. **Other old-layer reads.** Claude ran the check:
   - `veto.held_by_other` finds a Saint Jude outfit only as an institution and looks for a "head" membership, which
     none has. So during play a claim to lead the Eastside Combine is not refused. It now reads `orgs.head_of`
     (Task 14d0).
   - An outfit start's colleagues come from the empty `underworld_personnel`; they now come from `org_seats`.
   - The veto's world measures count zero outfits; they now count org-core outfits.
   - Left alone: the opening's district facts from the empty zones table write nothing wrong. Clean:
     `connector/money.py`, `connector/correct.py`, the business table, and the cultivation code (behind its switch).
     Scale words appear only in a world without a currency.

The kit's open questions say what to check this round.
