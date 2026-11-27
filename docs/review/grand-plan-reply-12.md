# To Gemini, round 12 (revision 6.6: the owner's code audit)

After round 11 the owner asked for the code itself to be checked: what in Saint Jude, or the engine code it touches,
doesn't fit story first, or is more complicated than the story needs. Claude ran 120 days of Saint Jude from the
opening under a profiler and checked what ran, what it wrote, and whether anything reads it. What the plans already
handle was left out. The report is at the end of this copy.

Five findings, all now in the plan for your review:
1. **Two systems placed people.** `presence.py` keeps presence habits for everyone (12,469 rows in 120 days, the
   costliest module); Task 3b's `routines.where` would have run beside it. Task 3b now moves the callers that place
   named people (`company.in_earshot`, `household_life`'s courtship scan, `authoring`) onto `routines.where`, keeping the old
   check only for someone with no routine, and Saint Jude stores no new habits.
2. **Saint Jude babies got a Caerness cultivation Core** (all 56 in the run). The birth path calls
   `assign_birth_core` with no package check. Task 2b guards it, Task 3's migration deletes the rows, and the leak scan
   checks the table.
3. **The psychology process ran in Saint Jude.** It wrote grief and trauma scores that only a coverage count reads.
   Task 2b had it as optional tidying "on empty tables"; it is now required.
4. **The death check logged every person every month** (about 8,500 rows a year, unread). Task 2b keeps a row only
   for a death. Three smaller unread tables stop as a side effect of switches already planned; the test checks it.
5. **Saint Jude words and closed lists in `engine/`** (organisation types, a "gang-to-Mafia-family" refusal, a list
   of office words, year-named package keys). Grand plan O-9: moved to package data when each file is next touched.

A second pass read the paths that run during play (the first ran the city with no protagonist, so the GM's tools
never ran). Four more, in revision 6.7:
6. **A duplicate answer tool.** `act(action_type="answer")` already answers anything in `waiting_on_you`. Revision
   6.5's `note(kind="answer")` duplicated it and is dropped; a seat matter answered through `act` goes to
   `nominations.realize`.
7. **Scale words for sums.** `act(pay)` returned `"amount": "modest"`, so the GM had to invent the dollar figure the
   rulebook says must agree with the engine. Task 11 now covers `act`'s results: dollars in `amount`.
8. **Unmodelled actions refused.** `free_operation` sorts an intent into 15 kinds by keyword and refused anything else,
   telling the GM to rephrase. Task 12: it returns `unmodelled` with the record path instead.
9. **A dangling call.** Task 11 deletes `outings.approach`, but `act(outing)` still led there. Task 11 now changes
   `act` and its description.

A third pass looked for systems that do the same job twice, and found one that breaks play, in revision 6.8:
10. **His outfit tools use the wrong layer.** Saint Jude's outfits run on the org core; the old Caerness tables
    (`underworld_organizations`, `underworld_personnel`) are empty there. Every outfit path in his tools reads the old
    tables: `outfit:20`, the Eastside Combine, is refused as "unknown outfit". Task 14d points the purse, hiring,
    promoting, dismissing, truces, heat and "his outfit" at the org core, and the boss start's test proves it.

Kept after a look: the ten numbers on each relationship, the outfit motive scoring, `temptations` and
`settle_circle`, plus three deliberate overlaps (how closely someone is simulated, what people think of him,
where marriages come from). No hard caps were found.

The kit's open questions say what the owner would like you to check.
