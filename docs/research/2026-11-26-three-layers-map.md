# World, personal life, and the link: what the engine does today (2026-11-26)

Read-only map made after the second Dominic playtest. The owner's question was whether the fixes have been treating
symptoms rather than root causes. Mostly they have. This note says where, from the code.

## 1. The world layer
`engine/simulation.py` registers about 40 domain processes: economy, outfits, law, politics, war, religion, health,
information and so on. It is deep and has been checked over runs of many years. No playtest fault came from here.

## 2. The personal layer (the people around the protagonist)
Most of it is `engine/life_matters.py`. Every living adult gets a yearly *rate* per kind of matter (money, romance,
quarrel, illness, rivalry, work, police, fling, scuffle). The rate comes from a few personal numbers (`_rates`, ~l.942):
cash, temper (`actor_drives.aggression`), highest resentment, age, trade, criminal familiarity.

**The pattern is roll first, explain after.** Take a quarrel (`_open_quarrel`, ~l.589):
1. a base yearly rate, scaled by temper and resentment, says *that* he quarrels;
2. the partner is drawn by tie weight from his ties;
3. the *topic* is drawn from a package word list (`quarrel_topics`), loosely filtered ("of_age", "debt");
4. the quarrel then *creates* the resentment (+8/-4).

So the grievance does not cause the quarrel. The quarrel is rolled, and a grievance-shaped sentence is attached to it.
Every playtest fault of this kind follows the same steps: the mother's "insult at a bar" quarrel, the Aurelio "words over
a girl", the marriage out of nowhere, and the mother's paid job (P2.32 patched only the job case). A brawl added to B1 the
same way would be one more such generator.

What is missing:
- **Standing state that drives behaviour.** The engine has no record of what a person currently wants from another,
  owes them, holds against them or fears for. There are relationship scalars (trust, resentment, familiarity) and one
  `actor_drives` row, but no *concerns* with an object and a reason.
- **Ties that follow play.** Relationships change only through `relationships.record_relationship_effect` (called from
  interactions, life_matters, outings and org agency). A `note kind=scene` with `present` (`connector/store.py`
  `_scene_note`) touches no tie. So the Morettis' dinners left Aurelio at "knows of".
- **One way contests resolve.** Fights (`combat.py`), bargains, quarrels and courtships each resolve in their own code.
  There is no shared "two people's states meet under these stakes" model.

## 3. The link between the layers
### World → personal: almost absent
Life-matter rates read only personal numbers. Outfit attention, a docks slowdown, a rival's rise, prices: none of these
becomes a personal concern for a named person. That's why the club's interest in Carla never turned into Aurelio's fear
by itself: the GM had to supply it, and the engine instead rolled a generic quarrel.

### Personal → world: partial
The protagonist's deals, money and authored acts reach enterprises, outfits and the law through specific hooks
(money_records, org agency, crime response). There is no general way a person's acts become their standing with groups.

### What reaches the protagonist: four separate feeds, four rule sets
`connector/timeflow.py advance` assembles the GM's report from:
| feed | module | rule for reaching him |
|---|---|---|
| `noticed` | raw `knowledge` rows (from `information.py` location rumours) | none: the last 8 rows learned in the window |
| hearsay (`material`, `waiting`, stops) | `hearsay.py` | a real carrier among close ties; stake = the tie |
| `texture` | `texture.py` | significance score (base + public + severity + circle closeness + violent) plus a "bringer" |
| `money`, `chances`, `history_due` | money_records, temptations, history | each its own |

`hearsay.py` already does what R1 wanted (a path and a stake). The others bypass it. The stale Mario Basso item is the
`noticed` kind. Gerald "bringing in more" is the texture/circle kind: `texture.circle` puts a customer with an open deal
or a work matter at closeness 0.6, the same as a workmate, so it counts as near.

## What this means for the design
The fixes in the queue (R1 news gate, R2 caused events, fights, ties from scenes, generated-people plausibility) are
all parts of two missing things:

1. **A personal layer made of concerns**: standing, specific states of one named person toward another or toward
   something (owes, wants, resents-because, fears-for, courts, rivals), each with its origin. Behaviour (quarrels, loans,
   offers, courtship steps, fights) is *chosen* from a person's live concerns, and outcomes change concerns and ties.
   One contest model resolves any confrontation from both sides' states and the stakes.
2. **A link made of translations**:
   - world events become concerns for the specific people they touch (outfit attention on Carla → Aurelio fears-for Carla);
   - persons' acts become standing with groups;
   - knowledge reaches the protagonist through a single gate that carries path and stake. Everything outward (scene,
     lookup, advance, resume) reads from that gate.

Whatever is rolled with no concern behind it either goes away or becomes the *origin* of a concern (a chance meeting on a
night out; an illness). It never becomes an outcome with a made-up reason.
