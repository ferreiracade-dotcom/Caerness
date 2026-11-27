# For review, round 1: the Saint Jude grand plan

You have reviewed the three-levels plan through thirteen copies. That plan is now Deploys 1 and 2 of a larger one.
The owner asked Claude to take every other Saint Jude design (news and reputation, prison, business, politics, real
history, and the three-levels design's later steps), judge each unbuilt part by the story-first test, cut what the
new plan makes unnecessary, and put the rest into one plan. That is the grand plan below.

From now on the review runs in rounds. The kit explains how. The documents follow in this order: the kit, the
grand plan, the owner's intent brief.


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
| 1 | (this round) | | |

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
  stand. Argue for a cut only with a play situation that needs it.

## Open questions for you this round

1. Is anything a player would plausibly do in Saint Jude missing from Deploys 3 to 6? Think of the starts:
   mechanic, made man, bar owner, alderman, businessman, reporter, lawyer, priest.
2. Is the order of Deploys 3 to 6 right for the playing experience? Deploy 5 (fights, illness, a small man rising)
   could arguably come before Deploy 4.
3. Which three items carry the most story for their cost, and which three the least?


---

# Saint Jude: the grand plan

Written 2026-11-27, at the owner's request. Living document: it changes after every review round. Its round log is
in `docs/review/grand-plan-review-kit.md`.

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
  owners as movers, the outlets as businesses. It proves the GM and the engine work together.
- **Deploy 2 (Tasks 15 to 19):** shocks through channels, pressure and opportunity, offscreen weighing and
  decisions, noticing, ambition actions, the ten-step chain, business state, his death or long sentence. It proves
  the world moves.

Nothing below starts before Deploy 2 has been played. Each later deploy gets its own detailed task plan, written
when it is next, from what play showed. Planning it in detail now would plan against a game that does not exist yet.

## Deploy 3: finish what is built

Small fixes to systems that exist, where a gap breaks coherence or leaves a system half-connected. Mostly one task each.

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| F-1 | A man who dies before admission stays "serving" | A dead man still serving is a coherence bug the GM will trip on | The case chain closes the sentence on death | S | J1 gaps |
| F-2 | The opening's held man has no sentence row | No parole or appeal for him, so his story stops | The opening gives a held man a sentence row from his term | S | J1 gaps |
| F-3 | Inside groups are almost all mob men | A prison of only made men isn't believable; street and neighbourhood groups make the inside a world | Tune who goes in and how groups form; a check in the one-year run | S | J1 gaps |
| F-4 | No official starts a payment or a fraud on his own | A city where only the player corrupts anyone isn't believable | Office holders get `seek_payment` and `rig_count` in the package's `actions`, served by `office_threat` and `cash_strain` | S | P1 report |
| F-5 | Deterrence is read only by the answering choice | A man who let a slight go should be probed by rivals; that's story | Outfit choices read the deterrence value that I1b already computes | S | I1b gaps |
| F-6 | Threads that nothing in the engine holds | The GM's thread is forgotten unless something holds it | Fold the intake design's tripwire into Task 7's `gm_check`: a recap thread with nothing held behind it is a reported fault | S | Intake §7.5 |
| F-7 | Visits leave no mark | Visiting a man inside is seen and talked about | A visit writes a claim through the existing `claims.record` | S | J1 gaps |
| F-8 | Faith acts in Saint Jude | The owner is weighing faith in the story; a parish has to be reachable | Verify that a tithe, a vow, a priest's counsel and the parish as an organisation reach the engine; fix the gaps found | S to M | Intake audit row 15 |
| F-10 | Cutaways (restored from X-1 by the owner) | The owner wants to see the wave his acts make: the editor's meeting, a rival's men talking, his kids taunted at school | For a significant happening that touches him, the brief carries a few `outside_his_knowledge` items (who reacted, where, how), which I1a already produces. The GM writes them as cutaways, marked, and the character can act only on what reaches him. `gm_check` (Task 7) reports a cutaway used as his knowledge. This changes the three-levels plan's Task 11, which had dropped them | S | I1a, owner 2026-11-27 |
| F-9 | Boxing reachability | A boxing start is one of the business design's campaign checks | Verify that owning a fighter and fixing a fight reach the engine; fix the gaps found | S | Intake audit row 16 |

## Deploy 4: consequences that bite

What makes acts come back. Each item uses machinery that exists and adds a small reader or a few package figures.

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| C-1 | Two sets of books | Fronts, skims and audits are central to mob and business stories, and need a real gap to find | A business holds a declared and a real figure for takings. A front's or a skim's difference is the gap. An audit, an informing bookkeeper or a suspicious partner reads the gap | M | BZ2 |
| C-2 | Tax and the "Capone path" | Spending he can't explain is how men like him fall; it ties to visible spending (rev 5.2) | Tax on declared income as package data. When visible spending runs well above declared income, the gap is a tip that can open a case through `crime_response` | M | Intake audit row 11 |
| C-3 | The mob on a business's books | A bar paying protection, a loan going bad and a bust-out need real books | The existing arrangement kinds become lines on the business's books: protection as a cost that rises with takings, a street loan as a debt. Default walks toward partner, then bust-out, through the existing tension and absorption code. Same for his business | M | BZ3 |
| C-4 | A bank loan, and the shylock when the bank says no | How a legitimate man ends up owned | A loan request gets an answer (yes, no, terms) weighed from collateral, ties and the owner's standing. A refusal leaves the street lender as the plausible way | S to M | BZ4 |
| C-5 | Strikes | A walkout at his business or his supplier's is a real story beat | A strike is a shock kind (Task 15) on a business with a union presence, weighed from wages and the union's men. The union is an organisation only where the story needs one | S | BZ4 |
| C-6 | Investigators with ambition | A prosecutor making his name on him is one of the best threats in this genre | The prosecutors' and federal offices go in `mover_roles`. `noticing` points them at crimes on record and published items. Their actions are `open_investigation` and `seek_indictment` through the case chain | S | P2, prison §7.1b |
| C-7 | A reporter digging | A reporter sniffing around is a threat he can buy, scare or feed | A reporter at an outlet is a notable whom `noticing` points at public facts about movers and him. The actions are `dig` and `publish` through `publish_media`. A reporter start is covered by Task 14d | S | Information phase 2 |
| C-8 | Owning a paper or station matters | If he owns the *Chronicle*, a story about him or his friends is his to run, hold or kill | An item about him or his on an outlet he owns becomes a `seat_decision` through the existing `delegation` key | S | Information phase 2 |
| C-9 | Old stories come back | His past is a cost: an old story dug up in an election year | Published items are kept with their subject and day; a rival, reporter or investigator acting on him reads them. Nothing new is stored | S | Information §7.4 |
| C-10 | Public items reach the readers that care | A scandal should move his voters, his lenders and the prosecutor | A published item feeds the existing readers: P1's voter blocs, a lender's answer (C-4), and a case tip (C-6). Each reader is checked in a test | S | Information phase 3 |
| C-11 | The justice system is people | A jury tampered with, a judge bought, a witness scared off | When a case reaches trial, the judge, prosecutor and key witnesses are materialized as people (the jurors as a group). An act he or anyone records against them (a bribe, a threat) weighs in the verdict | M | Prison §7.1b, J1 gaps |
| C-12 | A new name | Cooperating and going into protection is a fully playable path (owner) | An alias on the same actor, with the knowledge firewall hiding the link from those who wouldn't know it | S to M | Prison 8b, intake row 12 |
| C-13 | Civil matters: divorce, suits, bankruptcy | A divorce is one of the biggest personal stories, and bankruptcy ends many business stories | A civil case on the same chain as a criminal one, with money and orders as outcomes. Divorce goes through `household_unions` | M | Intake audit row 10 |
| C-14 | Prison changes a man | An old friend who comes out changed is a story; so is he | On release after a long term, temperament (`actor_drives`) moves from what happened inside, by package figures. Contacts made inside are kept as ties | S | Prison §7.4 |

## Deploy 5: the three levels completed (design steps 6 to 8)

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| L-1 | Contests: fights, races and the like | A fight has to be believable, or every violent scene is the GM's guess | A contest is weighed from the people's bodies (B1), skills and situation, with the outcome recorded. B1's held-fight patch is the input | M | Design step 6, B1 patch |
| L-2 | Movers' plans through organisations, with execution that can go wrong | A capo's plan botched by his men is a story; perfect execution isn't believable | A fired decision that goes through his men carries a chance of a botch, a leak or a delay from the men's competence and loyalty | M | Design step 7 |
| L-3 | A small man rising | The nobody who becomes someone is a classic story, and it must happen to NPCs too | `levels.refresh` promotes someone who has shown significance (money, seats, ties, deeds on record) without a tie to him | S to M | Design step 8 |
| L-4 | Obligations through life changes | A debt or a promise shouldn't vanish because a man moves, marries or goes inside | Obligations follow the person through moves, custody and death (passing to heirs where the package says so) | S | Design step 8 |
| L-5 | Careful demotion | People drifting out of his life should fade, not vanish | `refresh` lowers someone only when no tie, obligation or concern holds them | S | Design step 8 |
| L-6 | Illness before death | A parent's illness is one of the biggest personal stories, and sudden deaths without illness aren't believable | Illness onset as a health event some time before most natural deaths, with the existing Gompertz model unchanged | M | Memory: named mortality |
| L-7 | Groups with their own rates | Parish, union and neighbourhood ways of living make the background believable (who marries, who works where) | Several group memberships per person and per-domain rates, only where a rate is canon-grounded | M | Design step 6 |
| L-8 | Others weighing in | A wife against the deal, a brother pushing for revenge | In `weigh`, the active people closest to the decider add weight for or against an action. No mood | S to M | Design step 6 |

## Deploy 6: the wider world

| ID | Item | Why it passes | Simplest form | Size | Source |
|---|---|---|---|---|---|
| W-1 | Atlantic City | After 1978, Atlantic City is where Saint Jude men and money go, for mob and business campaigns alike | One region as package data: its holders, the casino vote and opening dates, its law agency. A move there goes through lazy places, `act`, `author` and outfit tension | M | BZ6 |
| W-2 | A holding in a real firm pays as history did | Buying Apple in 1977 must pay if the run hasn't changed Apple's path | A holding in a real firm is valued from its dated real path (R1), unless the run diverged it. The foreknowledge rule stays | S | R1 deferred, BZ5 |
| W-3 | Prices move by year | Gas lines in 1979 and inflation are part of the era's feel | Dated price changes in the price book, read by `money` | S | R1 deferred |
| W-4 | Rigged tenders | The Concrete Club is a canon fixture and a business-campaign obstacle | The rigging is an arrangement between bidders and with the board, on P1's tender item; an outside bidder gets the canon answer (stopped trucks, a refused bond) through existing acts | M | BZ3, business §6.7 |
| W-5 | Trades with real margins | His bar leaves him 10 to 20%, a garment shop 3 to 8%: a business story needs real stakes | The bible's cost structures as package data (`trades.json`), read by the business state of Task 18c | S | BZ2 |
| W-7 | Real firms he can act on (restored from X-9 and X-10 by the owner) | He must be able to invest in a real firm, buy into it, change its course, compete with it, poach its people, or found something that replaces it before it exists | The real firms that matter (giants touching Saint Jude, and the emerging ones such as Microsoft, Apple, FedEx and Nike) are package data: founding date, founders, real state by year. A firm becomes a business row when play touches it, with its real state on that day, as places do. Its real path is the default until his act gives a cause (R1's divergence check). Founders answer as their record makes plausible: Gates in 1975 doesn't sell to a stranger. A rival he founds first is weighed against the real one's founding through the same check. The foreknowledge rule stays | M | BZ5, owner 2026-11-27 |
| W-6 | The campaign starts | Event organiser, developer, newspaper, casino, trucking and boxing are the business design's checks | Add them as starts in `tools/start_check.py` (Task 14d) | S | BZ7 |

## Running alongside

| ID | Item | Why it passes | Simplest form | Size |
|---|---|---|---|---|
| O-1 | Phone cards | Play happens on the phone; the cards are the playing experience | Fix theme and height in the real cards (only the probe rendered) | S |
| O-2 | Speed on the VM | No long waits (owner rule) | Measure 30 days and one year on the VM after each deploy; fix the cadence, not the people | S |
| O-3 | Save size | About 24 to 25 MB a year against a 15 MB target; it matters only if it breaks the VM | Measure after Deploy 2; act only if the disk or speed suffers | S |
| O-4 | AGENTS.md §2 is stale | The next agent reads it first | Update the current-state section | S |
| O-5 | Remote hosting check | The address must point at the VM | Verify the duckdns record | S |
| O-6 | S1 Tasks 4 to 7 | Fast skips are the playing experience, but `levels` (Task 3) now owns cadence in Saint Jude | Owner question Q1 | ? |
| O-7 | The player's sex at creation | The resolution order is settled for everyone else | Owner question Q2 | S |
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

## Cut

| ID | Item | Why |
|---|---|---|
| X-1 | Cutaways | **Restored by the owner (2026-11-27) as F-10** |
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

## After Saint Jude (separate designs, not in this plan)

- Saint Jude in later eras (the owner wants several eras).
- A sports campaign (football), and business campaigns elsewhere.
- A medieval world on the same core.
- Caerness renovated after the three games.

## Questions for the owner

- **Q1 (O-6).** S1's coarser clock and Task 3's `levels` both decide how often background people are simulated.
  Should S1 Tasks 4 to 7 go ahead, or wait until Deploy 1 shows whether skips are fast enough? Recommended: wait,
  and measure skips after Deploy 1. The untracked S1 files belong to another session and stay untouched.
- **Q2 (O-7).** How is the protagonist's sex decided when the concept doesn't say? Recommended: the concept and the
  name decide. If both are silent, the GM picks what fits the concept and states it in the creation scene, so it can
  be corrected.
- **Q3.** You are rethinking mob play. The mob-specific items (C-3, W-4, part of W-1) are kept but placed after the
  general ones in their deploys. Is that right?


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

