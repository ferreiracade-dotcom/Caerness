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
| F-14 | His reach into prison, business and the outfit (round 5) | An inmate who files his own appeal, an owner who ends a supplier's contract or closes a failing bar, a soldier who asks for a sit-down: the same background-only gap as P1 | One check and wiring pass, nothing new built. Prison: `prison_review.file_appeal`, `file_parole` and `file_pardon` exist, and no tool calls them, so he files by his own act; he joins or leaves an inside group by his own act (since round 6 the engine doesn't place him; the group approaches him, Task 14c), and write or call out through `prison_channels.open_channel` (visits already work). Business: rent, supply and long projects already reach the engine through the intake's holdings and arrangements; add ending an agreement (`agreement_terms.end_term`) and closing a business. The outfit, for a man who isn't the boss: check that he can ask to join, kick up, step away and ask for a sit-down through the org core's existing offers and choices. The weekly filing of reviews for him is stopped in Deploy 1 (Task 14c). Revision 6.8: the boss's side (his outfit's purse, hiring, promoting, dismissing, truces) was found pointing at the old Caerness tables, empty in Saint Jude, and is fixed in Deploy 1 Task 14d; F-14 keeps the non-boss side | S to M | Round 5: the code checks |

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
