# For review, round 16: the Saint Jude grand plan, revision 6.12

The documents follow in this order: Claude's note on this round, the kit, the grand plan, the owner's intent brief, the code audit, and the changed task. Review continues until you have nothing left to raise.


---

# To Gemini, round 16 (revision 6.12: your round 15 point)

The owner took your point, with one change and one addition. The plan stays open, not frozen.

- **The owner's seat first.** Agreed, though it matters less than you expected: in the opening none of Saint Jude's
  544 businesses is owned by a seated man. It counts once a captain buys a bar or the GM founds a capo's restaurant,
  and it costs one line.
- **Left out:** the Deploy 2 protection link. The plan has no `exposure_links` kind for protection (only
  `competitor`), so nothing is invented for it.
- **Added:** 270 of the 544 businesses share a location with a racket, mostly at neighbourhood or district level, so
  several outfits can run at one place. The one that answers is the one whose rackets take the most there each week.

The order is: the outfit its owner sits in, then the biggest weekly racket take at its location, then none.


---

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
| 11 | 2 Task 14 bugs; nothing else to raise | Both as revision 6.5: each conduct fact surfaces once; `note(kind="answer")` for seat matters | None. Gemini was satisfied with the plan as it stood |
| 12 | 7 points on the audit revisions | All 7 as revision 6.9: prefixed answer references; one outfit purse; Task 14d0 split out; `where` places the unrouted; three switch names; `unmodelled` without `owner_notice`; old-layer reads at the start | Point 3 (three fallback rules, one per caller) became one rule in `routines.where`; point 4's optional switch was dropped instead of checked further |
| 13 | 3 points; nothing else once applied | All 3 as revision 6.10: institutions meet one evening a week; `decision:` for offers and his own due decisions, `seat:` for his business; the rest of the old-layer reads, with a catch-all SQL watch | Point 1 got one rule in `routines.where`, not a district match in the scan; `offer:` was renamed `decision:` instead of adding a fourth prefix |
| 14 | 2 points | Both as revision 6.11: his own decisions answerable in Deploy 1; all of `player_operations.py` on the org core, every outfit action under the SQL watch | Point 2 was wider than raised: about twenty helpers, including the outfit behind a business |
| 15 | 1 point | As revision 6.12: the owner's seat first, then the biggest weekly racket take at the location, then none | The Deploy 2 protection link was left out (no such `exposure_links` kind in the plan); the tie rule was added |
| 16 | (this round: revision 6.12) | | |

## Settled decisions (don't reopen without new evidence)

- The engine and GM split (three-levels revision 4) and story first (revision 5) are binding.
- Deploys 1 and 2 are the three-levels plan, reviewed in seventeen rounds. Raise a point about them only if a
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

Revision 6.12 applied your round 15 point, with one addition. The plan stays open, not frozen. The full text of Task
14d0 is at the end of this copy.

1. Anything else, or nothing left to raise.


---

# Saint Jude: the grand plan

Written 2026-11-27, at the owner's request. Its round log is in `docs/review/grand-plan-review-kit.md`.

**Reviewed until Gemini has nothing left to raise (owner, 2026-11-27).** Each round's points are checked against the
code, put to the owner, and applied on his yes. Deploy 1's playtests then add their own evidence.

## What this is

Saint Jude has eight approved designs, written between 2026-11-19 and 2026-11-26, and several streams already
built. This plan takes everything in them that is not yet built and puts it through the binding principle
(`AGENTS.md` §0):

> The objective is not to build the most sophisticated simulation of a fictional city. It is to create the best
> possible environment in which to play a believable character-led story.

The test for every item: does it make the story more believable, more reactive, more interesting to play, or more
coherent over time? If a simpler mechanism gets the same result, the simpler one is used. Priorities, in order:
the playing experience, a world that reacts, persistence and continuity, then the machinery.

Each item is in one of three groups:
- **Kept:** in the plan, in its simplest form, with a stable ID.
- **Already covered:** built already, or done by the three-levels plan (Deploys 1 and 2).
- **Cut:** fails the test, or the GM does it better with what exists. Cutting an unbuilt item deletes no code.

IDs never change and are never reused. A cut item keeps its ID, so a reviewer can argue for it.

## The split that decides most verdicts

The three-levels design (revision 4) split the work:
- **The engine** holds facts, memory, numbers and causes, and vetoes named contradictions.
- **The GM** (Claude) writes the prose and invents.
- **Near him,** the engine nominates, the GM realizes, and the engine ratifies.

The older designs were written before this split. They often ask the engine to simulate what the GM can now play
from facts: a newsroom's meetings, a campaign's door-knocking, a prison yard. The question for each of those items
is: **would forgetting it break the story?** If yes, the engine records it. If no, the GM plays it.

## Where everything stands

| Stream | State |
|---|---|
| Org core, mob tasks, law (B1 to B16) | Built |
| Information 1a (bearing, room read, push, ledger) and 1b (claims, audiences, the personal circle) | Built |
| Prison J1 (case chain, facilities, inside groups, channels, parole, appeal, pardon) | Built |
| Business BZ1 (shared drivers, ventures, property, agreements) | Built |
| Politics P1 (the city at middle depth: offices, races, votes, tenders, appointments, fraud) | Built |
| One intake (I-1), real history (R1), the lived opening (L1) | Built |
| Playtest fixes P2, GM correction and price book G1, bodies B1 | Built |
| S1 tiered background | Tasks 1 to 3 built; Tasks 4 to 7 open (see O-6) |
| Three levels, Deploys 1 and 2 (Tasks 1 to 19) | Planned to revision 6.0 (every grand-plan round included); not started |

## Deploy 1 and Deploy 2 (the three-levels plan)

Detailed in `docs/superpowers/plans/2026-11-26-three-levels-build.md` (revision 6.0, which already carries every
change this plan's rounds made to Deploys 1 and 2). In short:
- **Deploy 1 (Tasks 1 to 14d):** scenes with a record, undo, the GM fault checker, consequence facts, one news gate,
  a brief of facts, nominations, conduct, starts at any scale (play anyone, including a held seat), big business
  owners as movers, the outlets as businesses, cutaways (former F-10, round 2), the unheld-thread check (former
  F-6, round 3), the engine no longer casting his council vote, filing his appeals or placing him in a prison group
  (rounds 5 and 6), and a hands-off test that nothing else acts for him (round 6). It proves the GM and the engine work together.
- **Deploy 2 (Tasks 15 to 19):** shocks through channels, pressure and opportunity, offscreen weighing and
  decisions, noticing, ambition actions, officials who seek payments and rig counts (former F-4, round 3), the
  ten-step chain, business state, his death or long sentence. It proves the world moves.

Nothing below starts before Deploy 2 has been played. Each later deploy gets its own detailed task plan, written
when it is next, from what play showed. Planning it in detail now would plan against a game that does not exist yet.

## Deploy 3a: his reach (split in round 6)

What he can do with systems that already exist, wired to `act` with nothing new built. First after Deploy 2, so
every start is fully playable soonest.

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| F-11 | His reach into the city's politics (round 3, widened in round 4, split in round 5) | A lawyer who runs for mayor, a hauler who bids on a city contract, an alderman who brings a measure: all are day-one moves, and P1 was built for background people only | One pass that wires what exists to `act`, with nothing new built. Round 4's code check found every P1 piece present and none reachable by him: `races.file` (file in an open race; the office's eligibility and filing window are its vetoes), `civic_votes.add_bid` (his business bids on an open tender), `civic_votes.open_item` (when seated, he brings a measure), `pre_vote_deal` (it records only a pledge agreed in a scene; the GM plays the haggling), `appointments.put_forward` and accepting an appointment (the background `fill` already leaves him out), and `races.commit_fraud` (he rigs if he chooses). `civic_graft.weigh` refuses him as a payer, so his bribes stay a plain `pay` that the official answers as a person. Endorsements already exist as `field_holdings` `delivery`, recorded only when a head's decision or a scene backs him. Campaign money goes in C-10. His own council vote is fixed in Deploy 1 (Task 14c, round 5) | S to M | Rounds 3 to 5: the code checks |
| F-13 | His own work as an employee (split from F-11 in round 5) | A driver who becomes dispatcher, quits for a rival firm, or gets a raise is an everyday story, and it must land on his post, his pay and his routine | As an owner he can already hire, dismiss, promote and reassign (`player_operations`). Check that as an employee he can quit, take a job elsewhere, and that a raise or promotion his boss gives him lands on his post and wage; wire any missing piece the same way, with nothing new built | S | Round 4: the code check |
| F-12 | Owning part of a business, and paying over time (round 4) | A dock worker buys a quarter of his boss's trucking firm, two friends open a shop, the mob takes a silent piece of a bar, a retiring owner sells for a down payment: these are the usual ways men come to own things | `enterprise_partners` already holds `ownership_share`, but almost nothing reads it, and `trade` moves a whole business for cash. Add: `trade` can sell a share, written to `enterprise_partners`; it can close on a down payment with the rest held as a debt to the seller, on the existing obligations; and Task 18c's profit is paid to the owners by share. C-3's silent piece and W-7's stake use the same rows. Round 5: partial repayment already works (`make_credit_payment` through `pay`); add changing a debt's terms (amount or due day) once a scene has agreed it, and settling a debt for a share. The majority or managing owner runs the business; a minority share pays its cut and gives the GM leverage to play. No shareholder voting | S | Round 4: the code check |
| F-14 | His reach into prison, business and the outfit (round 5) | An inmate who files his own appeal, an owner who ends a supplier's contract or closes a failing bar, a soldier who asks for a sit-down: the same background-only gap as P1 | One check and wiring pass, nothing new built. Prison: `prison_review.file_appeal`, `file_parole` and `file_pardon` exist, and no tool calls them, so he files by his own act; he joins or leaves an inside group by his own act (since round 6 the engine doesn't place him; the group approaches him, Task 14c), and write or call out through `prison_channels.open_channel` (visits already work). Business: rent, supply and long projects already reach the engine through the intake's holdings and arrangements; add ending an agreement (`agreement_terms.end_term`) and closing a business. The outfit, for a man who isn't the boss: check that he can ask to join, kick up, step away and ask for a sit-down through the org core's existing offers and choices. The weekly filing of reviews for him is stopped in Deploy 1 (Task 14c). Revision 6.8: the boss's side (his outfit's purse, hiring, promoting, dismissing, truces) was found pointing at the old Caerness tables, empty in Saint Jude, and is fixed in Deploy 1 Task 14d0 (revision 6.9); F-14 keeps the non-boss side | S to M | Round 5: the code checks |

## Deploy 3b: finish what is built

Small fixes to systems that exist, where a gap breaks coherence or leaves a system half-connected. Mostly one task
each. Trimmed after Deploy 3a has been played.

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| F-1 | A man who dies before admission stays "serving" | A dead man still serving is a coherence bug the GM will trip on | The case chain closes the sentence on death | S | J1 gaps |
| F-2 | The opening's held man has no sentence row | No parole or appeal for him, so his story stops | The opening gives a held man a sentence row from his term | S | J1 gaps |
| F-3 | Inside groups are almost all mob men | A prison of only made men isn't believable; street and neighbourhood groups make the inside a world | Tune who goes in and how groups form; a check in the one-year run | S | J1 gaps |
| F-5 | Deterrence is read only by the answering choice | A man who let a slight go should be probed by rivals; that's story | Outfit choices read the deterrence value that I1b already computes | S | I1b gaps |
| F-7 | Visits leave no mark | Visiting a man inside is seen and talked about | A visit writes a claim through the existing `claims.record` | S | J1 gaps |
| F-8 | Faith acts in Saint Jude | The owner is weighing faith in the story; a parish has to be reachable | Verify that a tithe, a vow, a priest's counsel and the parish as an organisation reach the engine; fix the gaps found. What a priest hears in confession is held sealed: `conduct.lies` and `news_gate.spread` never carry it (round 1) | S to M | Intake audit row 15 |

## Deploy 4: the three levels completed (design steps 6 to 8)

Moved ahead of the consequences in round 1: fights, illness and lasting obligations show up in the first months of
almost every start.

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| L-1 | Fights | A fight has to be believable, or every violent scene is the GM's guess | Narrowed in round 2 to physical fights: weighed from the fighters' bodies and injuries (B1), their known skill and the situation (numbers, weapons, surprise), with the outcome and injuries recorded. B1's held-fight patch is the input. Races, games and other contests stay the GM's to play. Round 4: a fight that could kill the protagonist goes through Task 18d's rule, where both are plausible the GM leans toward his living | M | Design step 6, B1 patch |
| L-2 | Plans carried out by someone's men can go wrong | A capo's plan botched by his men is a story; perfect execution isn't believable | Simplified in round 1: when `fire_due` carries out an offscreen action through a subordinate, one check against his loyalty and competence can make it leak (a `spread` row) or fail (a `failed` decision with a plain cause). Near him, the GM plays it from nominations | S | Design step 7 |
| L-3 | A small man rising | The nobody who becomes someone is a classic story, and it must happen to NPCs too | Shrunk in round 2: one prominence rule in `levels.refresh`, read from what is already held: wealth at or above the package's line, or wide claims standing (I1b) without a seat, makes someone `notable`. A one-year run must show at least one person with no tie to him rising | S | Design step 8 |
| L-4 | Obligations through life changes | A debt or a promise shouldn't vanish because a man moves, marries or goes inside | Obligations follow the person through moves, custody and death (passing to heirs where the package says so) | S | Design step 8 |
| L-6 | Illness before death | A parent's illness is one of the biggest personal stories, and sudden deaths without illness aren't believable | Shrunk in round 3: deaths are already drawn person by person (`health._natural_mortality_check`). For someone `active` (close to him, or a mover), a natural death that falls due becomes an illness first, with a window before the death, and the Gompertz model is unchanged. People further away can still die suddenly. Revision 6.3: for someone `near` him the illness comes as a nomination; for a distant mover it applies directly, since a mayor's or a boss's illness is succession drama | S | Memory: named mortality |
| L-9 | A look back over his history (restored in revision 6.0) | A story over five to twenty years needs its past: why a grudge started, when a deal was struck. A fresh GM session in year four has to find it without the brief growing | The existing `lookup` tool gains a history query over closed scenes' stamps and `causal_chains`, by person or subject, returning dated one-line items. Nothing new is stored. It was deferred to steps 6 to 8 by the three-levels plan and left out when this plan was compiled | S | Three-levels rev 5.1, Gemini rev 6.0 |

## Deploy 5: consequences that bite

What makes acts come back. Each item uses machinery that exists and adds a small reader or a few package figures.

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| C-1 | Two sets of books, tax and the "Capone path" (C-2 merged in round 3) | Fronts, skims and audits are central to mob and business stories, and spending he can't explain is how men like him fall | A business holds one optional declared figure for takings beside the real one; a front's or a skim's difference is the gap. A package tax share applies to declared profit. A periodic check compares his visible spending and purchases (rev 5.2) with money he can explain: declared income plus his starting wealth, recorded loans (C-4) and recorded sales of assets or shares (F-12) (revision 6.3), and a wide gap is a tip to `crime_response` or an audit. An audit, an informing bookkeeper or a suspicious partner reads the gap. No accounting system and no tax filing | S to M | BZ2, intake audit row 11 |
| C-3 | The mob on a business's books | A bar paying protection, a loan going bad and a bust-out need real books | Shrunk in round 3: protection already moves as tribute through `org_tension`. It and a street debt become cost lines in Task 18c's business upkeep, protection rising with takings. A missed payment feeds the existing tension and absorption code, which walks toward partner, then bust-out. No separate mob bookkeeping. Same for his business | S | BZ3 |
| C-4 | A bank loan, and the shylock when the bank says no | How a legitimate man ends up owned | A loan request gets an answer (yes, no, terms) weighed from collateral, ties and the owner's standing. A refusal leaves the street lender as the plausible way | S to M | BZ4 |
| C-5 | Strikes | A walkout at his business or his supplier's is a real story beat | A strike is a shock kind (Task 15) on a business with a union presence, weighed from wages and the union's men. The union is an organisation only where the story needs one | S | BZ4 |
| C-6 | Investigators with ambition | A prosecutor making his name on him is one of the best threats in this genre | The prosecutors' and federal offices go in `mover_roles`. `noticing` points them at crimes on record and published items. Their actions are `open_investigation` and `seek_indictment` through the case chain Revision 6.0, men who flip: `org_informing` already turns a man in custody or facing a case, but he gives up only the man he answers to in his organisation, and not from what he knows. Widen the existing turning to anyone in custody who holds a true `knowledge` row of who ordered his crime (Task 10b's rows), weighed by the same loyalty against the sentence he faces. What he gives the prosecutor comes from that row, and he becomes a C-11 witness. The protagonist is under the same rules | S | P2, prison §7.1b |
| C-7 | A reporter digging, and a reporter filing | A reporter sniffing around is a threat he can buy, scare or feed; a reporter start needs his stories to land | Each major outlet's lead reporter is in `mover_roles` (round 1), so Tasks 17b and 17c's `noticing` and `weigh` reach him with no second path. His actions are `dig` and `publish`. A reporter protagonist files a story through `act`: an owner or editor with a tie to the subject or an interest in it can spike it, otherwise it runs through `publish_media` and feeds C-10 | S | Information phase 2, round 1 |
| C-8 | Owning a paper or station matters | If he owns the *Chronicle*, a story about him or his friends is his to run, hold or kill | An item about him or his on an outlet he owns becomes a `seat_decision` through the existing `delegation` key | S | Information phase 2 |
| C-9 | Old stories come back | His past is a cost: an old story dug up in an election year | Published items are kept with their subject and day; a rival, reporter or investigator acting on him reads them. Nothing new is stored | S | Information §7.4 |
| C-10 | Public items reach the readers that care | A scandal should move his voters, his lenders and the prosecutor | A published item feeds the existing readers: P1's voter blocs, a lender's answer (C-4), and a case tip (C-6). Each reader is checked in a test. Round 3 checked P1: no war chest, and the vote score has no money term. A donation is a ledger flow to a candidate's campaign purse, and spending from it counts in the race's score as one package-weighted term, for him and background candidates alike (round 1, round 3) | S | Information phase 3 |
| C-11 | The justice system is people | A jury tampered with, a judge bought, a witness scared off | When a case that involves him, someone `near` him (revision 6.3), or a client of his (C-15) reaches trial, the judge, prosecutor and key witnesses are materialized as people (the jurors as a group). An act he or anyone records against them (a bribe, a threat) weighs in the verdict. Every other trial keeps J1's existing path (round 3) | M | Prison §7.1b, J1 gaps |
| C-12 | A new name | Cooperating and going into protection is a fully playable path (owner) | An alias on the same actor, with the knowledge firewall hiding the link from those who wouldn't know it | S to M | Prison 8b, intake row 12 |
| C-13 | Civil matters: divorce, suits, bankruptcy | A divorce is one of the biggest personal stories, and bankruptcy ends many business stories | Shrunk in round 3: a civil filing records the parties, the kind, the amount or terms and its status. It settles through what exists: `money`, `trade`, obligations, `household_unions` for a divorce, and business closure for a bankruptcy. C-11's judge comes in only if the dispute reaches trial | S | Intake audit row 10 |
| C-14 | Prison changes a man | An old friend who comes out changed is a story; so is he | On release after a long term, temperament (`actor_drives`) moves from what happened inside, by package figures. Contacts made inside are kept as ties | S | Prison §7.4 |
| C-15 | Counsel on a case | A lawyer start needs real clients; a defendant's lawyer is a person, not a fee | Shrunk in round 2: a case names its counsel (`counsel_actor_id`). Case updates and plea or settlement offers reach the counsel (and him, if he is the counsel) as `waiting_on_you` matters. Counsel can agree a plea or settlement the client accepted, which binds the case. C-11 weighs the counsel's claims standing (I1b). No skill score; the GM plays the courtroom | S | Round 1 |
| C-16 | Licences and inspections | A bar's liquor licence, a builder's permit and a health raid are everyday stakes for bar owners, builders and aldermen | P1 already decides licences and zoning variances as votes. Add: a business holds its licences as standing facts. An official speeding or holding a licence or zoning decision moves the existing `civic_items.vote_day`, or the due day of a venture approval (BZ1); there is no new queue. A failed inspection or a raid is a shock kind that fines the business or closes it until it is put right. Round 5: a licence does not pass to an heir or a buyer by itself; he applies, through the same vote | S | Round 1, round 2 |
| C-17 | Sites (split from C-16 in round 2) | A stadium, a casino or a housing block starts with land, and the fight over it is the story | Shrunk in round 3: a site is a `buildings` row of kind `other`, marked as a site in its metadata with its zoning, so it is owned and changes hands through `places.transfer_place` like any building. City-owned parcels are rows owned by the city. Building on it is a BZ1 venture whose approval stage is P1's zoning or land-use vote. No new table and no schema change | S | Round 2b, round 3 |

## Deploy 6: the wider world

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| W-1 | Atlantic City | After 1978, Atlantic City is where Saint Jude men and money go, for mob and business campaigns alike | One region as package data: its holders, the casino vote and opening dates, its law agency. A move there goes through lazy places, `act`, `author` and outfit tension | M | BZ6 |
| W-3 | Prices move by year | Gas lines in 1979 and inflation are part of the era's feel | Dated price changes in the price book, read by `money` | S | R1 deferred |
| W-4 | Rigged tenders | The Concrete Club is a canon fixture and a business-campaign obstacle | Shrunk in round 2: the Club's members and their arrangement are canon package data. On P1's tender item, an outside bid gets the members' answer through what exists: a shock (stopped trucks, a supplier's refusal), a threat, or a refused bond. The GM plays the rest | S | BZ3, business §6.7 |
| W-7 | Real firms he can act on (restored from X-9 and X-10 by the owner) | He must be able to invest in a real firm, buy into it, change its course, compete with it, poach its people, or found something that replaces it before it exists | The real firms that matter (giants touching Saint Jude, and the emerging ones such as Microsoft, Apple, FedEx and Nike) are package data: founding date, founders, real state by year. A firm becomes a business row when play touches it, with its real state on that day, as places do. Its real path is the default until his act gives a cause (R1's divergence check). Founders answer as their record makes plausible: Gates in 1975 doesn't sell to a stranger. A rival he founds first is a recorded fact; when the real firm's founding date comes, R1's divergence check reads it as a possible cause and the GM rules (round 3: no national competition model; the GM plays the pushback). Round 2: a holding in a real firm (former W-2) is valued from its dated real path unless the run diverged it, so buying Apple in 1977 pays if nothing changed Apple. How founders and boards react is the GM's to play within the R1 real-figures rules; there are no special vetoes. The foreknowledge rule stays | S to M | BZ5, owner 2026-11-27 |
| W-6 | The campaign starts | Event organiser, developer, newspaper, casino, trucking and boxing are the business design's checks | Add them as starts in `tools/start_check.py` (Task 14d). The boxing start first verifies that owning a fighter and fixing a fight reach the engine (former F-9, moved here in round 1) | S | BZ7 |

## Running alongside

| ID | Item | Why it passes | Simplest form | Size |
|---|---|---|---|---|
| O-1 | Phone cards | Play happens on the phone; the cards are the playing experience | Fix theme and height in the real cards (only the probe rendered) | S |
| O-2 | Speed on the VM | No long waits (owner rule) | Measure 30 days and one year on the VM after each deploy; fix the cadence, not the people | S |
| O-3 | Save size | About 24 to 25 MB a year against a 15 MB target; it matters only if it breaks the VM | Measure after Deploy 2; act only if the disk or speed suffers | S |
| O-4 | AGENTS.md §2 is stale | The next agent reads it first | Update the current-state section | S |
| O-5 | Remote hosting check | The address must point at the VM | Verify the duckdns record | S |
| O-6 | S1 Tasks 4 to 7 | Fast skips are the playing experience | Owner's call to the lead (2026-11-27): wait. Measure skip speed after Deploy 1 and decide then. The untracked S1 files belong to another session and stay untouched | ? |
| O-7 | The player's sex at creation | Settled | Owner (2026-11-27): male unless the concept says otherwise | S |
| O-8 | The connector rename | Cosmetic | When convenient | S |
| O-9 | World words out of `engine/` (code audit, revision 6.6) | Packages are data only; a second world would trip on Saint Jude facts held in the engine | When each file is next touched, move to package data: `underworld.py`'s closed set of organisation types and its "gang-to-Mafia-family" refusal; `temperament.py`'s branch on `mafia_family`; `veto.py`'s list of public-office words; `ledger._LEADER`'s Caerness titles (lord, abbot, abbess, prior, patriarch, steward, warden) and `free_operation`'s Caerness keywords (siege, smith, granary, sect, tithe, guild, "sail to", "march to") (revision 6.7); the year in `civic_field`'s and `civic_patronage`'s keys (`holdings_1975`, `patronage_1975` become `holdings_opening`, `patronage_opening`). No task of its own | S |

## Already covered

| ID | Item | Covered by |
|---|---|---|
| A-1 | Seat standing from claims | I1b (`standing_pull`) |
| A-2 | Papers, radio and TV as institutions with owners | Rev 5.8 (outlets as businesses) and 5.9 (`publish_media`) |
| A-3 | A planted or false story | `holds_true=0` travels as false (Task 10a) |
| A-4 | The press as a business seat | Rev 5.8 business movers, plus C-8 |
| A-5 | The city at C (P3): the people around a political protagonist | `levels` makes them active; Task 14d's political start; `office_threat` |
| A-6 | Business C widening (BZ7) | `levels.refresh` and materializing around him |
| A-7 | Prison C depth (phase 4) | The GM plays inside from facts. Task 18d keeps him alive in the story after a long sentence |
| A-8 | Prison ways out: parole, appeal, pardon, good time | J1 |
| A-9 | Technology of the year | R1 (`tech_level`, the enabler check) |
| A-10 | Real holders and dated events above the city (most of P2) | R1 history entries and dated rules |
| A-11 | Places outside the city | The intake's lazy places (I-1, BZ1.8) |
| A-12 | Settled commitments become things | The intake (I-1) |
| A-13 | Marriage and courtship in play | P2.29, G1 |
| A-14 | A reporter start | Task 14d starts at any scale, plus C-7 |
| A-15 | The family carrying his reputation | I1b's personal circle |
| A-16 | Trades with real margins (former W-5) | Moved into Deploy 2's Task 18c in round 1: `trades.json` is data that Task 18c's business state reads |
| A-17 | Cutaways (former F-10, restored by the owner) | Moved into Deploy 1 in round 2, so Task 11 doesn't remove them only for Deploy 3 to build them again: Tasks 11 (a `cutaways` field on skip and close results), 7 (`gm_check` reports one used as his knowledge) and 12 (a rulebook line) |
| A-18 | A holding in a real firm pays as history did (former W-2) | Merged into W-7 in round 2: a holding is one of the things he does with a real firm |
| A-19 | Threads that nothing in the engine holds (former F-6) | Moved into Deploy 1's Task 7 in round 3, so the first playtests catch forgotten threads |
| A-20 | Officials who seek payments and rig counts (former F-4) | Moved into Deploy 2's Tasks 17a and 17b in round 3, so Deploy 2's politicians aren't clean |
| A-21 | Tax and the "Capone path" (former C-2) | Merged into C-1 in round 3 |

## Cut

| ID | Item | Why |
|---|---|---|
| X-1 | Cutaways | **Restored by the owner (2026-11-27) as F-10**, built in Deploy 1 since round 2 (A-17) |
| X-2 | A lookup view of the delivery ledger | Knowledge rows with a path (Task 10a) answer "what has he heard" |
| X-3 | A weekly NPC display pass (spending sprees) | Bearing already reads a man's money and goods when he is in a scene; a weekly pass adds nothing the player sees |
| X-4 | The story pipeline (assignment, editing, deadlines, space) | The GM plays the newsroom; the engine needs only what was published (C-7 to C-10) |
| X-5 | Libel, subpoenas, shield laws, gag orders | Rare in play; the GM can raise them, and C-13 holds a suit if one is brought |
| X-6 | The newsroom in close detail | Covered by the GM and C-7 |
| X-7 | A `company` org kind with shapes and seat ladders | A business row with an owner, key staff as ties, and C-1's books carry the story; the org core handles the few big firms that need seats |
| X-8 | Markets per sector and neighbourhood as a separate model | Task 18c's demand drivers and W-5's margins do it |
| X-9 | Giants running monthly agendas | **Restored by the owner (2026-11-27) as W-7**, in the lazy form: a firm runs once play touches it |
| X-10 | Emerging firms as simulated actors | **Restored by the owner (2026-11-27) as W-7** |
| X-11 | Regulation Q and the rate weather | Not felt in a character story beyond what W-3 covers |
| X-12 | Union locals simulated everywhere | C-5 makes a union an organisation only where the story needs one |
| X-13 | Every region beyond Atlantic City | Lazy places plus the GM; W-1 proves the pattern |
| X-14 | The state and nation at C (P4) | Lazy materialization and the GM; real holders from R1 |
| X-15 | Coarse state and national elections as simulated races | R1's real results stand unless the run names a cause |
| X-16 | Security reclass and transfers between prisons | Rare; the GM can author one |
| X-17 | The parole board's arrangements reach | Folded into C-11's people |
| X-18 | Money hidden abroad as its own shape | Lazy places plus held things |
| X-19 | Credentials (bar, broker, pilot) as a system | Recorded as facts on the person; the veto refuses a named contradiction |
| X-20 | Ties context (`tie_contexts`) | Unread so far; it comes back only with a reader that needs it |
| X-21 | `standing.infer` | Waits for a play case that needs it |
| X-22 | Groups with their own rates (former L-7) | Round 1: the background already marries and works by canon rates; it returns only if a run shows visibly broken demographics |
| X-23 | Others weighing in (former L-8) | Round 1: near him the GM plays it from who is present; far from him nobody sees it, and it would rebuild the scoring revision 5 cut |
| X-24 | Careful demotion (former L-5) | Round 2: Task 3's `refresh` already keeps anyone held by a live obligation or concern at `notable` or above. Task 3 now tests a former mover who still holds a concern |

## After Saint Jude (separate designs, not in this plan)

- Saint Jude in later eras (the owner wants several eras).
- A sports campaign (football), and business campaigns elsewhere.
- A medieval world on the same core.
- Caerness renovated after the three games.

## Revision 6.12 (Gemini round 15)

One point, taken with an addition. When he leans on a shop, the outfit that answers is the one its owner sits in,
then the one whose rackets take the most there each week, then none. No shop in the opening is owned by a seated man,
but one can be later. The protection link Gemini suggested for Deploy 2 was left out: the plan has no such link.

## Revision 6.11 (Gemini round 14)

Two points, both taken. His own stated decisions reach "waiting on you" in Deploy 1, so they can be answered there
too; the handler for offers to him stays in Deploy 2. The outfit task covers every helper in his tools that read
the old outfit tables (crews, rank, protection, "who is behind this business"), and its watched test runs every
outfit action.

## Revision 6.10 (Gemini round 13)

Gemini raised three points and the owner took all three, keeping the plan open for review rather than frozen. Clubs,
supper clubs, diners and parishes meet one evening a week and their members are there, so background courtship goes
on (revision 6.9's home-and-work rule would have stopped it). Offers to him and his own due decisions share one
answer reference, `decision:`, and his shop's work turned away is a seat decision. The outfit task now covers every
old-layer read left (his attacks, his people, a new outfit the GM founds) and fails its test on any statement that
names an old outfit table.

## Revision 6.9 (Gemini round 12)

Gemini checked revisions 6.6 to 6.8 and raised seven points; Claude checked each against the code and the owner took
all seven. His answers name what they answer (`life:`, `seat:`, `offer:`), so a seat decision and a life matter
can't be mistaken for each other. His outfit's money is the boss's own purse, shown once and never paid to itself.
Moving his outfit onto the org core is its own task (14d0), and it also closes a veto hole: in Saint Jude a claim to
lead an outfit whose head is alive was not refused. Someone with no routine is placed from his household and work.
Three missing switch names were added, a 0.2-second optional switch was dropped, and a creative scheme the engine
can't model no longer makes the GM announce a disagreement.

## Revision 6.8 (the code audit's third pass)

Looking for systems that do the same job twice found one that breaks play: Saint Jude's outfits run on the org core,
but every outfit path in his tools (the outfit's purse, hiring, promoting, dismissing, truces, heat, "his outfit")
reads the old Caerness tables, which are empty in Saint Jude. A boss couldn't pay out of his outfit or take a man on.
Task 14d now points those paths at the org core and tests it on the boss start. Three deliberate overlaps were looked
at and kept (how closely someone is simulated, what people think of him, where marriages come from).

## Revision 6.7 (the code audit's second pass)

The first pass ran the city with no protagonist, so the tools the GM calls never ran. The second pass read them and
found four things, all in the three-levels plan now:
- His answer to a matter already had a tool (`act` answer); revision 6.5 had added a second. Seat matters now go
  through the existing one.
- `act` gave sums as scale words ("a modest sum"), so the GM had to invent figures. Task 11: dollars in the result.
- An action nothing models was refused. Task 12: it comes back `unmodelled`, with the way to record it.
- Task 11 deleted `outings.approach`, but `act(outing)` still led there. Task 11 now changes `act` too.
- Caerness titles and keywords in `ledger` and `free_operation` join O-9.

## Revision 6.6 (the owner's code audit, 2026-11-27)

The owner asked for the code that doesn't fit story first, or is more complicated than the story needs. A profiled
120-day Saint Jude run (`docs/review/saint-jude-code-audit.md`) found five things the plans didn't cover:
- Two systems answered "where is this person": the old presence habits and the new routines. Task 3b moves the
  callers that place named people onto routines; Saint Jude stores no new presence habits.
- Every Saint Jude baby got a Caerness cultivation Core. Task 2b guards the birth path; Task 3's migration removes
  the rows; the leak scan checks the table.
- The psychology process ran in Saint Jude, writing scores nothing reads. Task 2b switches it off (no longer optional).
- The death check logged every person every month, unread. Task 2b keeps a row only for a death.
- Saint Jude words and closed lists inside `engine/`. O-9, when each file is next touched.

Looked at and kept: the ten numbers on each relationship (much reads them, and the player meets only how people
treat him), the outfit motive scoring (the working level-2 layer), `temptations` and `settle_circle`. No hard caps
were found in the code that runs for Saint Jude.

## Revision 6.5 (Gemini round 11)

Two Deploy 1 bugs in Task 14, both applied:
- A fact behind a personal matter (a wrong, a broken promise, a lie, news of another woman) surfaces once. Before,
  a confrontation already played could be nominated again every week.
- The GM gets a tool path to give his answer to a seat matter (`note(kind="answer")`; revision 6.7 uses the
  existing `act` answer instead).

Gemini then said it has nothing left to raise: the next real bugs will show once Deploy 1 runs and is played.

## Revision 6.4 (Gemini round 10)

Six slips in the three-levels plan's own text, none architectural: `lapsed` added to the nominations status; an
opportunity tied to its cash episode so it isn't reopened; the cutaway check covers wider cutaways; missing files
named in Tasks 11, 14c and 17b; Task 17b replaces Task 14a's stated-decision clean-up; Task 11's test uses a second
call id. Gemini's drift check found every earlier round landed cleanly.

## Revision 6.3 (Gemini round 9, owner's yes 2026-11-27)

Six points, all applied:
- Life draws run for everyone, the active included; near him they become nominations. The plan's overview and an
  older design line said otherwise, and are corrected.
- Overdue seat matters lapse; nothing is done in his name.
- Restlessness only for wage earners; money strain reads what a man can draw on.
- C-11 uses `near`, not `active`. C-1 compares spending with money he can explain.
- Wider cutaways: shown once, a floor for quiet weeks, not checked as scene people.
- L-6: illness near him is a nomination; a distant mover's applies directly.

## Revision 6.2 (Gemini, owner's yes 2026-11-27)

Five traps in Deploys 1 and 2, all applied in the three-levels plan:
- `near` excluded distant movers, so they move the city on their own instead of waiting as his nominations.
- His answer to a seat matter goes back to the code that asked; unanswered, nothing is decided for him.
- A skipped day counts as time with whoever his routine puts him with, so skips don't breed neglect.
- Casual extras are recorded like authored people, so undo reverts them cleanly.
- The start test asserts his personal life moves over 120 days, and only reports the 30-day count.

## Revision 6.0 (Gemini, owner's yes 2026-11-27)

Five points, all applied:
- L-9 restored: a look back over his history, lost when this plan was compiled.
- Task 4: scenes have a part of the day, so presence is judged right for two scenes on one day.
- The three-levels plan is labelled revision 6.0, with a list of every grand-plan change by task. The task text
  already carried them.
- C-6: a man in custody who knows who ordered his crime can flip and give him up.
- Task 11: a cutaway is a reaction to what he did, never a plan aimed at him. The code already works this way.
- Owner, the same day (revision 6.1): cutaways are wider than his circle. Anyone reacting to what is public or
  visible about him counts: strangers seeing him arrive with security, people watching him on the news, talk of his
  sentence or his wealth. They come from the spread and media items about him, the few most significant per skip.

## Round 6 (Gemini, owner's yes 2026-11-27)

Three points, all applied:
- A hands-off test in Task 14c: every role runs 90 to 120 days with no call from him, and nothing is written in his
  name except what befell him, upkeep and payroll, or his second's acts. The rule is a global constraint.
- Deploy 3 split: 3a his reach (F-11 to F-14), 3b the world fixes.
- His prison group: the engine no longer places him; the group approaches him as a nomination (Task 14c).

## Round 5 (Gemini, owner's yes 2026-11-27)

Six points, all applied:
- His council vote moved into Deploy 1's Task 14c, with a second place the check found: the prison's weekly review
  filed appeals and pardons for him by chance.
- F-11 is politics only; `pre_vote_deal` records a pledge agreed in a scene. His work as an employee is F-13.
- F-14: one pass for his reach into prison (filing himself, his inside group, letters and calls), business (ending
  an agreement, closing a business) and the outfit as a man who isn't the boss.
- F-12 adds changing a debt's terms and settling a debt for a share, with control left to the majority owner.
- C-16: a licence doesn't pass to an heir by itself.
- Leaking a rumour outside a scene needs nothing new: the GM plays a short scene and stamps what was told.

## Round 4 (Gemini, owner's yes 2026-11-27)

Four points, all applied:
- F-11 widened into one pass that wires all of P1 to `act` (races, tenders, measures, deals before a vote,
  appointments, fraud), plus his own work as an employee. The check found a seated protagonist's vote cast from his
  lean, now his own matter.
- F-12, owning part of a business and paying over time, on the existing `enterprise_partners` rows.
- L-1: a fight that could kill him goes through Task 18d's rule.
- Gemini's answer: the plan is ready to build from; nothing in Deploys 3 to 6 holds up Task 1. The build starts on
  the owner's go.

## Round 3 (Gemini, owner's yes 2026-11-27)

Ten points, all applied:
- Running for office (F-11): the code check found that `races.file` exists but no tool calls it, so he couldn't
  run. Campaign money joins C-10.
- C-2 merged into C-1, one lean item.
- Illness before death (L-6), civil matters (C-13), sites (C-17) and the mob on the books (C-3) shrunk to S.
- The thread check (F-6) moved into Deploy 1's Task 7, officials' payments and fraud (F-4) into Deploy 2's Tasks
  17a and 17b.
- People at trial (C-11) only for cases that touch him, his circle or his clients.
- Real firms (W-7) strictly lazy, with the owner's path kept: a firm he founds first is a fact R1's divergence
  check reads.

## Round 2 (Gemini, owner's yes 2026-11-27)

Eight points, all applied:
- Cutaways (F-10) moved into Deploy 1, since Task 11 would otherwise remove them and Deploy 3 build them again. They
  show only on `advance` and close results, for a significant happening that touches him, never in a mid-scene brief.
- Careful demotion (L-5) cut as X-24: Task 3 already holds people tied by an obligation or a concern.
- W-2 merged into W-7.
- Counsel (C-15), licences (C-16), rigged tenders (W-4) and a small man rising (L-3) shrunk to small forms that reuse
  what exists. Sites split from C-16 as C-17.
- Contests (L-1) narrowed to physical fights.
- Gemini's answers: nothing in Deploy 4 depends on Deploy 5; L-5 was its first cut.

## Round 2b: can the player surprise the game? (Gemini, owner's yes 2026-11-27)

Tested on an ambition nothing models: a pro basketball team and its stadium. No new deploy. Four small changes
went into the three-levels plan and one into this plan:
- Task 18c: `trades.json` gives default costs, never a closed list; an unmatched trade keeps the GM's figures.
- Task 11: his open ventures show in `you` while unfinished (BZ1 ventures already have stages, budget, partners
  and approvals).
- Task 15: a good-news shock, `demand_up`.
- Task 12: never refuse an ambition for lack of a model, never make it cheap, and ground the obstacles in the era.
- Task 14d: a test that a counterpart outside the city survives refresh, routines and a skip.
- C-16: sites (empty land, city lots) can be owned or claimed, gated by zoning.

## The owner's answers (2026-11-27)

- **S1 (O-6):** the lead's pick: wait, measure after Deploy 1.
- **His sex (O-7):** male unless stated otherwise.
- **Mob items:** stay where they are.
- **Cuts:** cutaways (F-10) and real firms (W-7) restored; the other cuts stand.


---

# Saint Jude: owner intent brief for the personal-level plan

For the code agent. Judge the personal-level plan against this, not against the plan's own goals. Dominic Basile is one illustrative playthrough, not the target. The target is any start in any sphere (business, underworld, politics, or a mix). Do not build Dominic-specific logic.

## The division of labour (do not blur it)

The engine exists because the GM (a Claude agent) was bad at persistent memory, arithmetic, and keeping things plausible instead of giving the player what he asked for. The GM is good at prose, storytelling and inventing hooks.

- **Engine:** state, memory, numbers, time, causes, and the plausibility bounds. It is the authority on what is true.
- **GM:** prose, scenes, voice, and inventing events, people and hooks. It is meant to act as a real game master and take initiative. It must work inside what the engine says is true, and what it invents should be recorded so it persists.

Where this brief says "the game should do X", the agent decides which side does it. Keep the engine's share to what needs memory, arithmetic or enforcement. Do not build tables where a fact plus the GM's judgement is enough. Example: a rough bar is rough because dockworkers drink there. The engine holds who frequents a place and the district's character, and the GM judges what follows. No per-venue fight odds.

## Owner decisions on how the two sides work together

1. **GM inventions become canon.** When the GM invents a person, place, event or fact and the engine accepts it as plausible, it is recorded and is as real as anything the game started with. Canon is per save only and does not carry to other saves. This means the engine needs a way to accept or reject a GM invention and to store what it accepts.
2. **Engine wins, but the owner is told.** If the GM and the engine disagree, the engine's version stands by default. The GM must tell the owner what the disagreement is, and the owner can rule for either side. A ruling for the GM's version is recorded as a correction to the engine.
3. **Every start has a real personal circle.** Whatever the start (family, employees, business associates, close staff, a household), the people around the protagonist are real people in the engine with their own histories and lives, not scenery generated when the player looks.
4. **No veto on plausible events.** If something is plausible and realistic it can happen, however inconvenient, unwelcome or hectic for the protagonist. Stories cannot always go well. The owner chooses how Dominic responds, but does not choose whether a plausible event occurs.

## Owner decisions on how the world behaves (any story)

1. **Real stakes.** The protagonist can be badly hurt, jailed or killed by plausible events (hence the prison work). Tie-break: if both survival and death are plausible, he survives. If death is the only plausible outcome, he dies. After a death, the successor is chosen with the GM afterwards.
2. **Fog and rumour.** The player knows only what someone in his position would learn through channels. Rumours can be wrong or distorted. The true state lives in the engine.
3. **Opponents are active, not only reactive.** Rivals, the mob and the police plan, adapt to his rise and pursue their own aims. Envy, underestimation and human mistakes are part of it.
4. **Reputation is per person and per group,** built from what each actually saw or heard, and it changes how they treat him.
5. **Life goes on.** People, including his parents, brothers and circle, age, marry, have children, fall ill, move away and die at realistic rates.
6. **His influence scales.** If he rises, the city visibly changes around him. While he is small, it carries on without him.
7. **Consequences linger.** Injuries, police attention, debts, grudges and a bad name persist until something actually resolves them. Nothing quietly resets.

## The test every event must pass

Plausible prior history. Invention is welcome. An event with no cause in state (relationships, wants, money, reputation, place, period) is not. The reverse also holds: an absence needs a cause. A mob that notices a useful man and then ignores him for months is as implausible as one that invents a grudge.

## The problem in one paragraph

The city simulation is rich and the protagonist's own life is thin, with nothing in between to carry city events to him. In the first playthrough the mob struck a deal, sent one car, and vanished for months while his business grew. Almost every customer paid late. Nights out with four young men produced nothing until the owner asked about women, and then the first woman was perfect. Nothing was heard of the mob doing anything else. The GM moralised.

## What the finished game must do

1. **The world acts without the player.** Families, gangs, officials and businesses pursue their own aims with reasons: gaining, losing, feuding, killing, making examples, being squeezed. A player could stay on the Hill and never touch the mob, and the mob would still be moving. If he enters later he enters something already in motion. News reaches him only through channels that would plausibly carry it, at plausible delay, or not at all.
2. **Powerful people notice and want things, for reasons.** How the mob learns of a person is itself causal (who saw, who talked). They may know he does good work without knowing his income. Follow-up is the default. Silence needs a cause. Backstory must hold together: a father untouched for thirty years needs a reason, settled at setup.
3. **Business is an ordinary mix.** Customers vary in payment, price, haggling, referrals. Things break. Booms follow good work and reputation, slumps follow neglect or rivals. Capacity matters: a boom in a one-bay shop should push him toward real decisions (premises, hiring, turning work away, marketing). When nothing arrives, there is a discoverable reason.
4. **People around him have their own lives.** Brothers, friends, a girlfriend and parents move without the player. Opening state is plausible: four fit young tradesmen are not all single with nothing going on. People can refuse, leave, lie or compete, with persistent consequences, when plausible.
5. **Ordinary life produces things unprompted.** A night out contains people and incidents without the player asking: most forgettable, some one-offs, some recurring, few marriage material, trouble depending on who he is and where he goes. The first woman, customer or fight is not special by default.
6. **Time skips.** He keeps living in his own competence and routine during a skip, and it is applied. A skip is interrupted for something serious or needing his decision, and not otherwise. Quiet is allowed to be quiet.
7. **No moralising.** Period behaviour is shown plainly (under-age and heavy drinking, speeding, small crimes, bigotry as the characters' own, death as part of the underworld). The protagonist is not steered to the moral high ground and the people around him are not all honest. Characters are gray. This is a GM-side instruction and belongs in the connector or skill.

## How to check

Keep it light. For each of the seven points give: which plan task covers it, whether it is covered, partial or missing, and the test or measured run that shows it. Do not write long prose. Then answer four questions:

- What carries a city event to the protagonist, and what decides it does not?
- What makes the mob follow up with someone it has noticed?
- What stops the first woman, customer or fight from being special?
- Does anything here assume Dominic or a business start, and what happens in a political start?

Flag anything in the plan that serves a different goal (speed, the city sim) and whether it conflicts. Re-read Gemini's review with this brief and say which of its findings bear on these goals.


---

# Saint Jude code audit against story first (2026-11-27)

**The question (owner):** what in the Saint Jude or engine code it touches doesn't fit the new philosophy, and what is
more complicated than it needs to be to deliver the story?

**The rules used:** AGENTS.md §0 (story first; the simplest mechanism wins) and revision 5 of the three-levels design:
- no psychology simulation;
- recording stays light;
- the engine never chooses for him;
- packages are data only;
- no caps.

**Method:**
- I ran 120 days of Saint Jude from the packaged opening, on a copy, under a profiler.
- I recorded which engine modules ran, what each table gained, and whether anything reads what was written.
- I left out what the grand plan, the three-levels plan or the nearby-code review (`three-levels-adjacent-verdicts.md`)
  already deals with.

**The run:** 121 engine modules ran, 109 tables grew, and the run made 211 events, all births, unions, comings of age,
deaths and successions.

## Already dealt with by the plans (not repeated here)

- The old personal choices and the belief mirror. The mirror is the four 13,143-row tables `knowledge`,
  `knowledge_provenance`, `actor_evidence_access` and `actor_beliefs`. Both go in Task 2b.
- `resolution_controller`'s second level ladder (Task 3).
- Event-to-rumour broadcast and the side doors into his news (Task 10).
- `outings`' `you_may` list of moves (Task 11).
- Background rolls that ignore protection (Task 14).
- `org_happenings` choosing for him (Task 2b).
- The agency leaks in civic, prison and business code (Task 14c).

## New findings

### 1. Two systems answer "where is this person?" (the biggest)

- `presence.py` keeps probabilistic presence habits for everyone:
  - 12,469 new rows in 120 days;
  - the single costliest module, about 11% of the engine's own time.
- Task 3b adds `routines.where` as the answer, but nothing moves `presence.py`'s callers onto it. They are:
  - `company.py` (who is with him in a scene);
  - `household_life` (courtship meetings);
  - `authoring` (housemates);
  - `information` (rumour exposure; that part goes off with Task 10);
  - plus `player`, `turns`, `decisions` and `model_gateway`.
- The nearby-code review said `outings.crowd` was presence's last caller. That is wrong.
- **Risk:** after Deploy 1, the scene's company and the presence check could disagree about where a man is.
- **Proposal:**
  - Task 3b moves `company.py`, `household_life` and `authoring` onto `routines.where`.
  - Saint Jude stops writing presence habits.
  - The module stays for Caerness.

### 2. Saint Jude babies get a Caerness cultivation "Core" (a bug)

- `household_life` calls `cultivation.assign_birth_core` for every birth with no check of the package.
- All 56 babies born in the run got a `Closed-Core` row with Caerness metadata (`HEREDITARY_BIRTH_CORE`).
- The other two paths that write cultivation profiles already check `system_enabled(conn, "cultivation")`.
- `tools/leak_scan.py` doesn't look at this table.
- **Proposal:**
  - Guard the call: one line.
  - Delete the rows on existing Saint Jude saves in a migration.
  - Add the table to the leak scan.

### 3. The psychology process runs in Saint Jude

- It writes grief and trauma scores (for example "grief 60, intensity 29.4" after a death).
- Nothing reads them except a coverage count used in tests.
- Revision 5 says plainly: no psychology simulation.
- Task 2b lists `psychology` among the Caerness processes to switch off, but as optional tidying and "on empty tables".
  It isn't empty.
- **Proposal:** make that switch required, not optional.

### 4. Records nobody reads

| Table | Rows in 120 days | Read by |
|---|---|---|
| `mortality_audit` (one row per person per monthly death check, about 8,500 a year) | 2,824 | nothing |
| `information_links` | 580 | nothing |
| `resolution_transitions` | 84 | nothing |
| `actor_context_cache` | 111 | nothing |

- Recording should stay light.
- **Proposal:** Saint Jude stops writing these:
  - `mortality_audit` keeps a row only for a death, or only under a debug switch;
  - the other three go off with the systems that write them.

### 5. Saint Jude words and closed lists inside `engine/` (small)

- `underworld.py`:
  - a closed set of organisation types;
  - a hard-coded rule refusing "gang-to-Mafia-family" promotion.
- `temperament.py` branches on `organization_type == "mafia_family"`.
- `veto.py` holds a list of public-office words (mayor, alderman, councilman and so on).
- `civic_field` and `civic_patronage` read package keys named `holdings_1975` and `patronage_1975`.
- Each is small, but all are world facts living in the engine, not in the package.
- **Proposal:** move them to package data when that code is next touched. No dedicated task.

### 6. Looked at, no change proposed

- **Relationships:**
  - Each bond holds ten numbers: affection, trust, resentment, fear, respect, loyalty and others.
  - Every change also writes a history row: 4,718 in 120 days.
  - That is closer to modelling inner states than revision 5 likes.
  - But `life_matters`, the outfit choices and the brief all read those numbers, and the player meets the result only
    as how people treat him.
  - Replacing them would be a large change for little that he would notice. Keep.
- **Outfit motives:**
  - `org_motives` and `outfit_motives` score motives from real state: 1.5 million calls in 120 days.
  - This is the working level-2 layer the design keeps, and it already follows temperament and cost. Keep.
- **`temptations` and `settle_circle`:** kept by the earlier review, and still right.
- **No hard caps found** in the code that runs for Saint Jude. The package's prison capacities and term limits are real
  facts about the buildings and the law.

## Second pass: the code that runs during play (2026-11-27)

The first pass profiled the city's own clock, with no protagonist and no scenes, so the tools the GM calls never ran.
This pass read those paths: `act`, its dispatch (`connector/acting.py`), `free_operation`, `player_operations` and
`outings`, checked against story first and the engine/GM split. Four findings.

### 7. His answer to a matter already has a tool, and revision 6.5 added a second one

- `act(action_type="answer", details={"matter", "answer", "how"})` already exists. It answers anything in
  `waiting_on_you` through `life_matters.answer`: "yes", "no", or "settled" with a free-text `how`.
- Task 14c makes a seat decision a `waiting_on_you` matter.
- Revision 6.5 then added `note(kind="answer")` as a separate path for those matters, without knowing this tool
  existed.
- **Proposal:**
  - Drop `note(kind="answer")`.
  - `act(answer)` hands a `seat_decision` matter to `nominations.realize` with `{"choice": how or answer}`.
  - Every other matter goes to `life_matters.answer` as now.
  - That leaves one tool, with the player's own words in `how`.

### 8. `act` hides sums behind scale words

- `player_operations` returns money only as scale words. Its header says "Amounts leave this module only as scale
  words".
- So `act(pay)` returns `"amount": "modest"`, and its summary says "hands over a modest sum".
- Yet the Saint Jude rulebook says every sum the GM states must agree with `scene` or `lookup`. The contract says tool
  results give facts and numbers in fields, not engine prose. The `money` tool does give dollars.
- The GM is left to invent the figure, which is exactly how sums drift.
- Task 11 fixes this for `views.py` only.
- **Proposal:**
  - Task 11 also covers `act`'s results: the dollar figure as a number in `amount` (and in `short_of`).
  - The scale word may stay beside it. The summary sentence becomes plain facts.

### 9. Free actions are matched against a fixed keyword list, and anything else is refused

- `free_operation` sorts an intent into one of 15 kinds by English keyword: travel, duel, battle, message, treat,
  train, craft, project, attack, trade, demand, lend, hire, pay, order.
- Many of the keywords are Caerness words: siege, smith, granary, sect, tithe, guild, "sail to", "march to".
- An intent that matches none is refused with "That is not something the engine can carry out yet". Its reason kind
  tells the GM to rephrase and retry.
- So a con, a forged document, a newspaper smear or a rigged fight gets pushed into the wrong kind (a "pay", an
  "order"), or played with nothing recorded.
- That cuts against Task 12's rule: never refuse an ambition because nothing models it.
- **Proposal:**
  - An unmatched intent comes back as `status: "unmodelled"`, not a refusal.
  - The result names the record path the rulebook already gives (a scene stamp with `known_to`, `money` for any sum,
    `author` for anyone new), so it is played and recorded, never turned away.
  - The keyword list stays; the GM's `kind` hint already overrides it.
  - Its Caerness words join O-9.

### 10. Task 11 deletes `outings.approach`, but `act` still calls it

- Task 11 deletes the happenings draw, `you_may` and `approach` from `outings`. That is right: approach is a fixed
  four-move romance roll with points for each move.
- But `act(outing)` with a target, and the `act` tool's own description ("details.move talk|dance|number|leave
  together"), still lead there.
- **Proposal:** Task 11's files add `connector/acting.py` (an outing with a target becomes an ordinary scene with
  that person) and the `act` description in `connector/server.py`.

### Smaller, joining O-9

- `ledger._LEADER`, the pattern that decides who may draw on a holder's purse, matches Caerness titles (lord, abbot,
  abbess, prior, patriarch, steward, warden).
- It belongs in package data with the other world words.

## Third pass: systems that do the same job twice (2026-11-27)

This pass looked for places where two systems hold the same fact or do the same job.

### 11. Saint Jude outfits live in one organisation layer, and his tools use the other

- The engine has two organisation layers:
  - the old Caerness one: `underworld_organizations`, `underworld_personnel` and about 40 `underworld_*` tables,
    worked by `underworld.py` and `underworld_rebuild.py`;
  - the org core (`org_profiles`, `org_seats`, `org_units`, `org_money` and the `org_*` modules), which runs Saint
    Jude's outfits.
- In Saint Jude the old tables are empty after 120 days (0 organisations, 0 personnel).
- But every outfit path in the tools he uses still reads and writes the old layer:
  - `ledger`'s `outfit:<id>` purse reads `underworld_organizations.treasury`. Checked on a Saint Jude save,
    `outfit:20` (the Eastside Combine) is refused as "unknown outfit 20".
  - In `player_operations`:
    - hiring into an outfit (`create_personnel`);
    - promoting, retiring and expelling;
    - "his outfit" (`_my_outfit`);
    - truces and alliances (`change_relation`);
    - heat (`add_heat`);
    - the men behind an attack.
  - In the connector:
    - `store`'s and `authoring`'s outfit ids;
    - `views`' list of who is in the life.
- **What it means in play:** a Saint Jude boss can't pay out of his outfit's treasury through `money` or `act`. He
  can't hire a man into it, promote one, or make a truce through `act`. Each comes back refused, or does nothing.
  That is a silent disconnection.
- It is also complexity: two layers for one thing.
- **Deploy 1 is affected.** Task 14d proves "play anyone, including a boss", but these paths are not in its test.
- **Proposal:**
  - Point those paths at the org core when the package runs it (`systems.outfits`):
    - an outfit purse is the org core's treasury;
    - hiring, promoting and dismissing go through `org_seats`;
    - truces and alliances go through `org_tension`;
    - heat goes through `org_heat`.
  - The old layer stays for Caerness.
  - Task 14d's boss start gets a test: he pays a man from the treasury, takes one on, and agrees a truce, each landing
    in the org core.
- This overlaps grand plan F-14 (his reach into the outfit, Deploy 3a). F-14 assumed these paths worked and only
  checked the non-boss side.

### Overlaps that are deliberate, no change proposed

- **How closely someone is simulated.** After Deploy 1, two settings remain:
  - `actors.sim_resolution`, from `levels`: how much he matters to the story;
  - `simulation_profiles`, used by `tiers.py`: how often his upkeep runs.
  - The contract keeps them apart on purpose; 14 modules read the second.
  - The old `entity_resolution` (5,934 rows) stays frozen in Saint Jude once its process is off. That is harmless.
- **What people think of him.** Three records each answer a different question:
  - the ten numbers on each relationship: how one person feels about another;
  - `claims` and `impressions`: what is said of him, and how a crowd sees him;
  - `standing`: words worked out from those two.
  - Merging them would be a large change before anyone has played.
- **Marriages:** these come from two places, but for different people. `household_life`'s courtship pairs named
  people; `opening_family` marries a named person into the unnamed population. Not a duplicate.
- **The money-flow recorder** lives in `underworld_rebuild` (`_record_economic_flow`), though every Saint Jude
  payment uses it. Misplaced, but harmless. It can move to `ledger` when either file is next touched (O-9's list).

### Still not covered by any pass

- **The opening builder** (`tools/build_opening.py`, `opening_family`): it runs once. "Canon null means unknown"
  already governs it.
- **Caerness's own code:** left alone until Caerness is renovated, by the owner's rule.
- **Whether the engine still acts for him during a run:** the first pass had no protagonist. Task 14c's hands-off test
  is the check for that.

## What it would cost

- **Findings 1 to 4:** small changes that fit the Deploy 1 tasks that already touch these files (Tasks 2b and 3b).
- **Finding 5:** later, when that code is next touched.
- **Finding 6:** nothing.
- Nothing is deleted; each change is a Saint Jude switch or a guard, as revision 5 requires.


---

# Task 14d0 of the three-levels plan (revision 6.12, full text)

### Task 14d0: His outfit through the org core (Deploy 1, built before Task 14d)

Revision 6.9 split this out of Task 14d (Gemini round 12): it is a different subsystem from a start in a held seat,
and Task 14d's boss start needs it working first.

**Files:**
- Revision 6.8 (code audit finding 11). Saint Jude's outfits run on the org core
  (`org_profiles`, `org_seats`, `org_units`, `org_money`); the old layer (`underworld_organizations`,
  `underworld_personnel`) is empty there. Yet every outfit path in his tools reads the old layer: checked on a
  Saint Jude save, `outfit:20` (the Eastside Combine) is refused as "unknown outfit 20". When the package runs the
  org core (`systems.outfits`), these paths use it; the old layer stays for Caerness:
  - Modify: `engine/ledger.py` (an `outfit:<id>` holder is an `org_profiles` organisation. Its purse is the one the
    org core already pays from, `org_money.purse_ref`: the living head's purse. `_check_exists`, `balance`,
    `_debit` and `can_draw` follow it, so a boss pays out of the outfit's money as the org core does);
  - Modify: `engine/player_operations.py`:
    - hiring into an outfit seats the man through `orgs.seat` at the role named, under the boss or the unit
      leader named;
    - promoting, retiring and expelling change his `org_seats` row the way the org core's own vacancies do;
    - `_my_outfit` reads his seat (`orgs.seats_of`);
    - a truce or alliance lowers the pair's `org_tension` and is recorded with the org core's deal records;
    - heat goes to `org_heat.add`;
    - the men behind an attack are his outfit's seated men;
  - Modify: `connector/store.py`, `connector/authoring.py` and `connector/views.py` (an outfit id is an `org_profiles`
    organisation; "who is in the life" reads `org_seats`);
  - the money-flow recorder `underworld_rebuild._record_economic_flow` stays where it is (O-9 moves it later).
- Revision 6.9, one purse (Gemini round 12):
  - `engine/ledger.py`: `institution:<id>` of an org-core organisation reaches the same purse as `outfit:<id>`
    (today it reaches an empty purse of the organisation's own). A payment whose two ends are the same purse is
    refused in plain words ("that is already his money"). `can_draw` lets only the head draw on it; his second does
    not (the old layer let an underboss draw).
  - `connector/views.py`: for an org-core outfit, the money view says the outfit's money is his purse and shows it
    once, not as a second figure. Anything that adds up his means (`brief.full`'s money, Task 16's `cash_strain`)
    counts that purse once.
- Revision 6.9, the start-time reads (the round 12 check of the old layer):
  - Modify: `engine/veto.py` (`held_by_other` finds an org-core outfit's holder with `orgs.head_of`. Today it finds
    the outfit only as an institution and looks for a "head" membership, which none has, so a claim to lead the
    Eastside Combine during play is not refused. The world measures count org-core outfits and their seated men,
    not the empty `underworld_organizations`);
  - Modify: `engine/new_character.py` (an outfit start's colleagues come from his outfit's `org_seats`, nearest
    roles first, as now from `underworld_personnel`);
  - left as they are: the opening's district facts from `underworld_zones` give nothing in Saint Jude, where the
    rackets are citywide shares (`org_holdings`); no wrong fact is written. `connector/money.py`,
    `connector/correct.py` and the business table were checked and are clean.
- Revision 6.10 (Gemini round 13), the rest of the old-layer reads:
  - Modify: `engine/free_operation.py` (`resolve_ref` finds an outfit by name among org-core organisations. An attack
    on an outfit takes the rival's head from `orgs.head_of`, its strength from its seated men, and its losses as
    seats vacated, not from `member_count_estimate`);
  - Modify: `engine/authoring.py` (`_his_person` reads his outfit's seats. Founding an organisation in a package
    with `systems.outfits` writes an org-core one: `org_profiles`, its first unit and the leader's seat through
    `orgs.seat`, the kind from the package's org kinds. The outfit counts used for scale read org-core outfits);
  - Modify: `engine/intake.py` (`_ENTITY_KEYS`: an `outfit_id` is an org-core organisation);
  - `ledger`: a payment from an outfit with no living head (`purse_ref` is None) is refused in plain words ("the
    outfit has no living head to pay from");
  - unchanged: the outfit's own spending. The org core pays purse to purse and never calls `can_draw`, so the
    head-only rule doesn't stop his second's routine running;
  - catch-all: the test watches the SQL (`conn.set_trace_callback`) through the boss's calls and fails on any
    statement naming `underworld_organizations`, `underworld_personnel` or `underworld_crews`.
- Revision 6.11 (Gemini round 14), all of `engine/player_operations.py`: about twenty helpers read the old outfit
  tables, not only those listed above. Every one reads the org core in a package with `systems.outfits`:
  - his place and rank (`_outfit_row`, `_outranks`, `_is_my_person`, `_serves_in`, `_holder_label`) from his seat;
  - crews (`_hire_many`, `_backer_list`) are the org core's units (`org_units`), and sizes are seated men, not
    `member_count_estimate` or `size_estimate`;
  - promoting (`_reassign`), retiring (`_leave_holdings`) and expelling (`_dismiss`) change `org_seats`;
  - who protects a victim (`_protectors`) is his outfit's seated men;
  - the outfit behind a person (`_org_behind`) is the one he sits in. Revision 6.12, the outfit behind a business,
    in order: the outfit its owner sits in (`orgs.seats_of`; none in the opening, but a captain who buys a bar or
    a capo's restaurant the GM founds counts); then the outfit whose active rackets at its location
    (`org_lines.location_id`, mostly a neighbourhood or district) take the most each week, since a shop there is
    on its turf; then none. Saint Jude keeps no per-shop protection, and none is an honest answer, not an
    invented one;
  - the trace an act leaves (`_leave_trace`) goes to `org_heat` and `org_tension`, as heat and truces above.
- Test: `tests/outfit_org_core_test.py`

**Interfaces:**
- Produces: in a package with `systems.outfits`, `outfit:<id>` and `institution:<id>` of an org-core organisation
  are one ledger holder, its living head's purse (`org_money.purse_ref`); `veto.held_by_other` reads `orgs.head_of`.
  Task 14d's boss start and Task 16's `cash_strain` rely on both.

- [ ] **Step 1: Write the failing test:**
```python
# revision 6.8: the boss runs his outfit through the org core
outfit = org_named(conn, "The Eastside Combine"); boss = head_of(conn, outfit)
make_protagonist(conn, boss)               # revision 6.10: seated directly; Task 14d's starts come later
seen = watch_sql(conn)                     # revision 6.10: every statement from here on
before = org_money_rows(boss); r = server.act("b1", "pay", "he pays Sal for the job", target_actor_id=sal,
                                           details={"amount": 500, "from": f"outfit:{outfit}"})
assert r["status"] == "applied" and r["amount"] == 500                     # not "unknown outfit"
server.act("b2", "hire", "he takes Nicky on as a soldier", target_actor_id=nicky, details={"into": f"outfit:{outfit}", "role": "soldier"})
assert seat_role(boss, nicky, outfit) == "soldier"                            # an org_seats row, not underworld_personnel
t0 = tension(boss, outfit, rival); server.act("b3", "demand", "he offers the Greco crew a truce", target_actor_id=greco_head)
assert tension(boss, outfit, rival) < t0 or waiting_on_you_has(server, "truce")   # agreed, or their answer is pending
assert count(boss, "underworld_personnel") == 0 and count(boss, "underworld_organizations") == 0
# revision 6.9: one purse
assert server.money("m1", "pay", f"outfit:{outfit}", "me", 100)["status"] == "refused"   # his own money
assert ledger.balance(conn, ("institution", outfit)) == ledger.balance(conn, ("person", boss))
assert not ledger.can_draw(conn, his_second(conn, outfit), ("outfit", outfit))
assert means_listed(server, boss).count(ledger.balance(conn, ("person", boss))) == 1          # shown once
# revision 6.9: the start-time reads
with pytest.raises(veto.Contradiction): veto.held_by_other(conn, "The Eastside Combine", "boss")   # its head is alive
assert set(colleagues_seeded(conn, associate_start)) <= seated_men(conn, his_outfit_id(associate_start))
# revision 6.10: the rest of the old layer
server.act("b4", "attack", "he hits the Greco crew's card game", details={"targets": ["Greco crew"]})
server.author("b5", "organisation", {"name": "the Dock Street crew", "leader_actor_id": nicky})
assert org_named(conn, "the Dock Street crew") and seat_role(boss, nicky, org_named(conn, "the Dock Street crew"))
server.lookup("b6", "the Eastside Combine")
# revision 6.11: every outfit action under the watch
server.act("b8", "order", "he makes Nicky a capo", target_actor_id=nicky, details={"role": "capo"})
assert seat_role(boss, nicky, outfit) == "capo"
server.act("b9", "order", "he retires old Sal", target_actor_id=sal, details={"retire": True})
server.act("b10", "order", "he throws Joey out", target_actor_id=joey, details={"expel": True})
assert seat_status(joey, outfit) == "expelled" and seat_status(sal, outfit) == "retired"
server.act("b11", "demand", "he leans on the Kowalski bakery", details={"targets": ["business:kowalski"]})
# revision 6.12: whose shop it is
give_business(conn, rival_capo, bar); assert org_behind_business(conn, bar) == rival   # the owner's seat first
assert org_behind_business(conn, shop_where_two_run) == top_weekly_take_there(conn, shop_where_two_run)
assert org_behind_business(conn, shop_off_every_turf) is None
server.act("b12", "attack", "he has Greco's runner roughed up", target_actor_id=greco_runner)
assert not [s for s in seen if re.search(r"underworld_(organizations|personnel|crews)", s)]
with pytest.raises(ValueError, match="no living head"): ledger.transfer(conn, ("outfit", headless), ("person", sal), 10)
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus the tests of every modified module, commit.
