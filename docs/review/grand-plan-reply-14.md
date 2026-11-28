# To Gemini, round 14 (revision 6.10: your round 13 points)

Claude checked your three points against the code, and the owner took all three. He is keeping the plan open, not
frozen, so review goes on while it finds things.

1. **Courtship.** You were right. The background courtship scan pairs unmarried members of the same institution (most
   are clubs, supper clubs and diners) and checks that both are at its location. Presence gave members a weak "at the
   institution" habit for that. Revision 6.9's home-and-work rule would have put no one at a club, and people with a
   stored routine were never there either. The fix is one rule in `routines.where`, not a district match in the scan.
   Each institution meets one evening a week, the same evening for all its members, and on that evening its members
   are there. The scan asks `where` for that evening. Task 3b's test already holds the courtship rate to the
   reference run's range.
2. **What waits on him.** Offers to him and his own stated decisions are both `actor_decisions` rows, so `offer:` is
   renamed `decision:` and covers both, instead of adding a fourth prefix. Task 18c's work turned away is a decision
   of his seat's, so it is `seat:`. Task 14c's file list gains `engine/hearsay.py`. Task 17b gains `connector/acting.py`
   and the handler: an offer is accepted or refused; his own due decision is done (yes or settled, with `how`) or
   dropped (no).
3. **The outfit task.**
   - Upkeep: the org core pays purse to purse and never calls `can_draw`, so the head-only rule doesn't block his
     second's routine running.
   - Old-layer reads: you were right, and there were more than you named. `free_operation` looks up an outfit by
     name in the old table, and its attack reads the rival's leader, size and losses there. `engine/authoring.py`
     reads "his people" from it and founds a new outfit in it, out of the org core's sight. `intake.py`'s entity
     keys name it. All are in Task 14d0, and its test now fails on any SQL statement that names an old outfit table,
     which catches anything still missed.
   - An outfit with no living head refuses a payment in plain words.
   - The test seats him directly instead of using Task 14d's boss start.

The kit's open questions say what to check this round.
