# For review, round 7 (frozen): the Saint Jude grand plan

The documents follow in this order: Claude's reply to round 6, the kit, the grand plan, the owner's intent brief. The plan is frozen; this copy is the record of it.


---

# Reply to Gemini, round 6

All three points are applied, and the plan is frozen until Deploy 1 has been played.

- **The hands-off test (point 1):** in Task 14c. One save per role (council seat, outfit soldier, business owner,
  serving inmate) runs 120 days with no call from him. Every row written with him as the actor must be something that
  befell him, routine upkeep or payroll, or an act recorded as his second's or manager's. The rule is now one of the
  plan's global constraints.
- **The split (point 2):** Deploy 3a is his reach (F-11 to F-14), first after Deploy 2. Deploy 3b is the world
  fixes, trimmed after 3a has been played.
- **His prison group (point 3):** confirmed, `prison.admit` calls `assign_group` for every inmate. For him it now
  becomes an approach, a nomination the GM plays, and he joins only by his own act. This sits in Task 14c with the
  other two guards.

The next round comes after Deploy 1's playtests, with the transcripts.


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
| 6 | 3 points, 3 open answers | All 3: the hands-off test and its rule; Deploy 3 split into 3a (his reach) and 3b; his prison group as an approach, in Task 14c | None. The plan froze after this round |

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
- **The plan is frozen (round 6).** The next round comes after Deploy 1 has been played, with its playtest
  transcripts.
- Round 4: the plan is ready to build from. Further rounds refine Deploys 3 to 6 and don't hold up Task 1. Argue for a cut only with a play situation that needs it.

## Open questions for you this round

None. The plan is frozen until Deploy 1 has been played.


---

# Saint Jude: the grand plan

Written 2026-11-27, at the owner's request. Its round log is in `docs/review/grand-plan-review-kit.md`.

**Frozen after round 6 (2026-11-27, owner's yes).** The plan doesn't change again until Deploy 1 has been played;
then the playtests decide what changes.

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
| Three levels, Deploys 1 and 2 (Tasks 1 to 19) | Planned to revision 5.9, review copy 13; not started |

## Deploy 1 and Deploy 2 (the three-levels plan)

Detailed in `docs/superpowers/plans/2026-11-26-three-levels-build.md` (revision 5.9). In short:
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
| F-14 | His reach into prison, business and the outfit (round 5) | An inmate who files his own appeal, an owner who ends a supplier's contract or closes a failing bar, a soldier who asks for a sit-down: the same background-only gap as P1 | One check and wiring pass, nothing new built. Prison: `prison_review.file_appeal`, `file_parole` and `file_pardon` exist, and no tool calls them, so he files by his own act; he joins or leaves an inside group by his own act (since round 6 the engine doesn't place him; the group approaches him, Task 14c), and write or call out through `prison_channels.open_channel` (visits already work). Business: rent, supply and long projects already reach the engine through the intake's holdings and arrangements; add ending an agreement (`agreement_terms.end_term`) and closing a business. The outfit, for a man who isn't the boss: check that he can ask to join, kick up, step away and ask for a sit-down through the org core's existing offers and choices. The weekly filing of reviews for him is stopped in Deploy 1 (Task 14c) | S to M | Round 5: the code checks |

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
| L-6 | Illness before death | A parent's illness is one of the biggest personal stories, and sudden deaths without illness aren't believable | Shrunk in round 3: deaths are already drawn person by person (`health._natural_mortality_check`). For someone `active` (close to him, or a mover), a natural death that falls due becomes an illness first, with a window before the death, and the Gompertz model is unchanged. People further away can still die suddenly | S | Memory: named mortality |

## Deploy 5: consequences that bite

What makes acts come back. Each item uses machinery that exists and adds a small reader or a few package figures.

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| C-1 | Two sets of books, tax and the "Capone path" (C-2 merged in round 3) | Fronts, skims and audits are central to mob and business stories, and spending he can't explain is how men like him fall | A business holds one optional declared figure for takings beside the real one; a front's or a skim's difference is the gap. A package tax share applies to declared profit. A periodic check compares his visible spending and purchases (rev 5.2) with his declared income, and a wide gap is a tip to `crime_response` or an audit. An audit, an informing bookkeeper or a suspicious partner reads the gap. No accounting system and no tax filing | S to M | BZ2, intake audit row 11 |
| C-3 | The mob on a business's books | A bar paying protection, a loan going bad and a bust-out need real books | Shrunk in round 3: protection already moves as tribute through `org_tension`. It and a street debt become cost lines in Task 18c's business upkeep, protection rising with takings. A missed payment feeds the existing tension and absorption code, which walks toward partner, then bust-out. No separate mob bookkeeping. Same for his business | S | BZ3 |
| C-4 | A bank loan, and the shylock when the bank says no | How a legitimate man ends up owned | A loan request gets an answer (yes, no, terms) weighed from collateral, ties and the owner's standing. A refusal leaves the street lender as the plausible way | S to M | BZ4 |
| C-5 | Strikes | A walkout at his business or his supplier's is a real story beat | A strike is a shock kind (Task 15) on a business with a union presence, weighed from wages and the union's men. The union is an organisation only where the story needs one | S | BZ4 |
| C-6 | Investigators with ambition | A prosecutor making his name on him is one of the best threats in this genre | The prosecutors' and federal offices go in `mover_roles`. `noticing` points them at crimes on record and published items. Their actions are `open_investigation` and `seek_indictment` through the case chain | S | P2, prison §7.1b |
| C-7 | A reporter digging, and a reporter filing | A reporter sniffing around is a threat he can buy, scare or feed; a reporter start needs his stories to land | Each major outlet's lead reporter is in `mover_roles` (round 1), so Tasks 17b and 17c's `noticing` and `weigh` reach him with no second path. His actions are `dig` and `publish`. A reporter protagonist files a story through `act`: an owner or editor with a tie to the subject or an interest in it can spike it, otherwise it runs through `publish_media` and feeds C-10 | S | Information phase 2, round 1 |
| C-8 | Owning a paper or station matters | If he owns the *Chronicle*, a story about him or his friends is his to run, hold or kill | An item about him or his on an outlet he owns becomes a `seat_decision` through the existing `delegation` key | S | Information phase 2 |
| C-9 | Old stories come back | His past is a cost: an old story dug up in an election year | Published items are kept with their subject and day; a rival, reporter or investigator acting on him reads them. Nothing new is stored | S | Information §7.4 |
| C-10 | Public items reach the readers that care | A scandal should move his voters, his lenders and the prosecutor | A published item feeds the existing readers: P1's voter blocs, a lender's answer (C-4), and a case tip (C-6). Each reader is checked in a test. Round 3 checked P1: no war chest, and the vote score has no money term. A donation is a ledger flow to a candidate's campaign purse, and spending from it counts in the race's score as one package-weighted term, for him and background candidates alike (round 1, round 3) | S | Information phase 3 |
| C-11 | The justice system is people | A jury tampered with, a judge bought, a witness scared off | When a case that involves him, someone `active` around him, or a client of his (C-15) reaches trial, the judge, prosecutor and key witnesses are materialized as people (the jurors as a group). An act he or anyone records against them (a bribe, a threat) weighs in the verdict. Every other trial keeps J1's existing path (round 3) | M | Prison §7.1b, J1 gaps |
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

## Round 6 (Gemini, owner's yes 2026-11-27)

Three points, all applied, then the plan froze:
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
