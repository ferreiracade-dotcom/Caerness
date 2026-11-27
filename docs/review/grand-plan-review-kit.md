# Review kit: the Saint Jude grand plan

This kit is the same every round, except for the round log and the open questions at the end. Read it first.

## Who does what

- **The owner** decides. Nothing you propose is applied without his yes.
- **Claude** (the lead) keeps the plan, checks every claim against the code before acting on it, and writes a reply
  to each round saying what was applied, what was refused, and why.
- **You** review. You cannot see the code. Say when a point rests on an assumption about the code, and Claude will
  check it.

## What you get each round

1. This kit.
2. The grand plan (`docs/superpowers/plans/2026-11-27-saint-jude-grand-plan.md`), the current version.
3. Claude's reply to your last round (from round 2).
4. The owner's intent brief.

Anything else you want, ask for by path in a `REQUEST` line: a design, the detailed three-levels plan (the latest
review copy is 13), a report, or a piece of code. It comes in the next round.

## How to judge

Use one test, the owner's binding principle:

> The objective is not to build the most sophisticated simulation of a fictional city. It is to create the best
> possible environment in which to play a believable character-led story.

Does it make the story more believable, more reactive, more interesting to play, or more coherent over time? If a
simpler mechanism gets the same result, the simpler one wins. "It makes the simulation more complete" is never a
reason.

Two more rules from the owner:
- **Engine and GM.** The engine holds facts, numbers and causes and vetoes named contradictions. The GM (Claude)
  writes and invents. Ask of anything: would forgetting it break the story? If not, the GM plays it.
- **No caps, menus or ladders.** Real-world rates are targets that get reported, never limits in code.

## Useful kinds of help

- A **kept** item that fails the test, or has a simpler form.
- A **cut** item that should come back, with the play situation that needs it.
- A **missing** item: something a player would plausibly do, or expect the world to do, that nothing in Deploys 1
  to 6 holds.
- **Order:** an item placed too late for what play needs, or too early for what it depends on.
- **A draft:** when Claude asks, the detailed task text for one item, in the three-levels plan's style.

Less useful: a point about an item already settled in the round log, unless you have new evidence. Wording
and style.

## Reply format

Number your points, most important first, at most ten. Each one:

```
POINT n: <item ID, or NEW>
VERDICT: keep | simplify | cut | restore | add | move | question
WHY: <the play situation, judged by the test>
EVIDENCE: <a quote and where it comes from, or "assumption about the code">
CHANGE: <what to write in the plan, in a line or two>
```

A new item gets a NEW point. Claude gives it the next free ID in its group (F, C, L, W, O, X).
End with any `REQUEST` lines.

## Round log

| Round | Your points | Applied | Refused, and why |
|---|---|---|---|
| 1 | 10 points, 3 open questions | All 10: Deploy 4 and 5 swapped (fights, illness, obligations first); L-7, L-8 cut; reporters as movers and filing (C-7); counsel on cases (C-15); licences and inspections (C-16); margins into Task 18c; L-2 simplified; boxing into W-6; sealed confession (F-8); war-chest check (C-10) | Margins went into Deploy 2's Task 18c rather than Deploy 3; licences reduced to holding and inspections, since P1 already votes on them; witness protection kept in place (owner: cooperation is fully playable) |
| 2b | The surprise test (basketball team and stadium): 6 points | All six, as small changes: open trades, ventures in `you`, `demand_up`, sites in C-16, an outside-counterpart test, a rulebook line | None. Staged projects already exist as BZ1 ventures, so only their visibility was added |
| 2 | 8 points, 3 open answers | All 8: cutaways moved into Deploy 1 (A-17); L-5 cut (X-24); W-2 merged into W-7 (A-18); C-15, C-16, W-4 and L-3 shrunk; sites split as C-17; L-1 narrowed to fights | None. Two additions of Claude's: cutaways show only on skip and close results, never mid-scene; Task 3 tests a former mover who still holds a concern |
| 3 | 10 points, 3 open answers | All 10: running for office (F-11, the filing code was never called); C-2 merged into C-1; L-6, C-13, C-17 and C-3 shrunk to S; F-6 into Task 7; F-4 into Tasks 17a and 17b; C-11 only for cases near him; W-7 strictly lazy | None. Claude's changes: F-11 sits in Deploy 3 as a fix to what is built, with campaign money in C-10; a site is a `buildings` row of kind `other`, since no land table exists; the owner's replace-before-it-exists path in W-7 is kept as a fact R1 reads |
| 4 | 4 points, 3 open answers | All 4: F-11 widened to all of P1 plus his own work; F-12 shares and paying over time; L-1 routes his possible death through Task 18d | None. The check found more than assumed: every P1 piece is unreachable by him, and his council vote was cast from his lean, now his own matter |
| 5 | 6 points, 3 open answers | All 6: his vote fix into Task 14c; F-11 split (F-13 his work); F-14 prison, business and outfit reach; F-12 debt terms and debt for a share, no shareholder voting; C-16 licence on inheritance | None. The check found a second place acting for him: the prison's weekly review filed his appeals and pardons; BZ1 was mostly reachable already through the intake |
| 6 | 3 points, 3 open answers | All 3: the hands-off test and its rule; Deploy 3 split into 3a (his reach) and 3b; his prison group as an approach, in Task 14c | None |
| 6.0 | 5 points | All 5: L-9 history lookup restored; a scene's part of the day (Task 4); the three-levels plan labelled 6.0; men who flip (C-6); cutaways never show plans (Task 11) | None. The three-levels task text already carried rounds 1 to 6, so only its label changed; cutaways were already reactions only |
| 6.1 | Owner | Cutaways include anyone reacting to what is public or visible about him | |
| 6.2 | 5 traps in Deploys 1 and 2 | All 5: `near` without distant movers; answering a seat matter; no neglect from ordinary skips; casual extras undo cleanly; the start test over 120 days | None. All five confirmed against the plan text |
| 9 | 6 points, 5 requests | All 6 as revision 6.3: life draws for everyone; overdue seat matters lapse; restlessness and strain scoped; C-11 `near`; C-1 explainable money; cutaway guards; L-6 note | None. Point 1 was a real conflict between the plan's overview and Task 14a |
| 10 | 6 points, drift check | All 6 as revision 6.4, slips in the plan's own text | None |
| 11 | 2 Task 14 bugs; nothing else to raise | Both as revision 6.5: each conduct fact surfaces once; `note(kind="answer")` for seat matters | None. Review ends here: Gemini is satisfied |

## Settled decisions (don't reopen without new evidence)

- The engine and GM split (three-levels revision 4) and story first (revision 5) are binding.
- Deploys 1 and 2 are the three-levels plan, reviewed in thirteen rounds. Raise a point about them only if a
  grand-plan item collides with them.
- The protagonist is always a new character, under the same rules as everyone, with one exception: where both are
  plausible, the GM leans toward his living.
- Real people appear only within their public record.
- His death or a long sentence (Task 18d) is firm in Deploy 2.
- A start in a held seat replaces the holder.
- The owner went through the cuts (2026-11-27): cutaways (F-10) and real firms (W-7) came back; the other cuts
  stand.
- Cutaways are built in Deploy 1 (round 2) and appear only on skip and close results.
- Round 3 left Deploy 3 as F-1 to F-3, F-5, F-7, F-8 and F-11; rounds 4 and 5 added F-12 to F-14; round 6 split
  them into Deploy 3a (F-11 to F-14) and 3b.
- **Review continues until you have nothing left to raise** (owner, 2026-11-27). Say so plainly when that is the
  case; that is the signal the owner waits for.
- Round 4: the plan is ready to build from. Further rounds refine Deploys 3 to 6 and don't hold up Task 1. Argue for a cut only with a play situation that needs it.

## Open questions for you this round

1. The corrected text of Tasks 7, 11, 14, 16 and 17b is at the end again. Do the six fixes read right?
2. Are you satisfied? If you have nothing left to raise, say so plainly.
