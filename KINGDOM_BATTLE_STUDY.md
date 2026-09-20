# Kingdom Structural Study — Transfer Notes for Caerness v0.14

## Scope

This study extracts **narrative and simulation structure** from *Kingdom* rather than reproducing its characters, battles, named maneuvers, formations, or scene choreography. It is not intended as a real-world warfare guide. The useful question for Caerness is:

> How can a large battle remain readable, character-driven, uncertain, and causally coherent while many commanders and units act at once?

## 1. A battle needs multiple simultaneous centers of agency

A battle should not collapse into `Player vs Enemy Commander`.

The useful structure is layered:

- overall command has an objective and incomplete picture;
- subordinate commanders receive intent rather than perfect puppeteering;
- local fronts develop their own pressures;
- individual actors can matter greatly without becoming the entire battle.

**Caerness transfer:** v0.14 introduces battle zones, command links, delayed orders, and subordinate interpretation.

## 2. Readability comes from fronts, not one army-wide score

The biggest weakness in v0.13 was that whole sides were compared largely as aggregate strength. That made a battle mechanically legible but dramatically flat: one side could be doing well everywhere at once because one global average said so.

Large war fiction works better when the audience can answer:

- Where is pressure building?
- Which part is stable?
- Which part is becoming dangerous?
- What does high command know about those changes?

**Caerness transfer:** units are assigned to persistent battle zones. Each zone develops its own pressure, initiative, and local turning points.

## 3. Command is not direct control

The important distinction is between:

- **objective** — what a superior wants accomplished;
- **order** — what reaches a subordinate;
- **execution** — what that subordinate actually does in changing circumstances.

A subordinate should sometimes carry out an order exactly, sometimes adapt it within delegated authority, and sometimes fail through limited competence or changed circumstances.

**Caerness transfer:** command links now track communication quality, discretion, and trust. Orders have an issued round and an effective round. Competent subordinates can make bounded adaptations when local conditions have materially changed.

## 4. Information delay creates genuine command uncertainty

A commander should not receive the database state of every front in real time.

Reports should be:

- delayed;
- partial;
- confidence-weighted;
- dependent on information quality and command organization.

The important simulation effect is that a commander may make a reasonable decision using information that was accurate when observed but is already aging.

**Caerness transfer:** v0.14 adds persistent battle reports with observed and available rounds. The strategic battle view reads delivered reports rather than exposing raw enemy state.

## 5. Great commanders should feel different without becoming stat packages

Large-scale war fiction often makes generalship memorable because commanders solve the same problem differently. Caerness should not reduce this to one `command = 92` number.

A command profile now separates broad tendencies such as:

- planning;
- adaptation;
- presence;
- delegation;
- nerve.

These are not personality scripts or guaranteed bonuses. They provide additional context for how command systems function.

## 6. Morale matters through local context and social confidence

Morale should not be a supernatural comeback meter.

It should react to:

- confidence in leadership;
- fatigue;
- cohesion;
- nearby success or failure;
- the apparent state of the local front;
- whether people believe the wider plan still makes sense.

**Caerness transfer:** local battle events may create bounded morale shocks in one zone. They do not automatically decide the entire engagement.

## 7. Personal combat belongs inside the battle, not above it

A duel or extraordinary individual action may matter because of where and when it happens. Its significance should propagate through nearby morale, command, or objective state only when there is a causal bridge.

A famous individual defeating someone important does **not** automatically mean every formation on the battlefield instantly collapses.

**Caerness transfer:** v0.14 formalizes bounded local shock hooks. Future duel integration should feed through these rather than directly setting a battle winner.

## 8. Turning points should be consequences of accumulated state

A good turning point feels surprising in the moment but understandable afterward.

The engine should therefore detect turning points when existing conditions cross meaningful thresholds, rather than schedule dramatic beats because pacing demands one.

**Caerness transfer:** zone pressure crossings create persisted turning-point records. The emergence layer may later recognize them narratively, but cannot manufacture them.

## 9. Battle phases should emerge

Avoid rigid sequences such as:

`opening -> boss reveal -> second phase -> final duel`.

A battle can have an opening, development, crisis, withdrawal, or aftermath, but these should follow the actual state of the fronts and command system.

**Caerness transfer:** v0.14 recalculates battle phase from elapsed rounds and the number of fronts in serious crisis.

## 10. The camera can move across scales while knowledge remains role-bound

The appeal of large-scale battle fiction comes partly from moving between:

- command perspective;
- local unit perspective;
- individual perspective;
- political/campaign consequences.

Caerness can do the same without giving the player omniscience.

The **simulation** may track every active front. The **player view** remains limited by the protagonist's role and available reports.

## 11. Rank should change the kind of game

A junior commander should make local decisions.

A senior commander should make broader decisions and rely increasingly on other people.

Promotion should therefore create:

- greater causal reach;
- wider but less immediate information;
- more reliance on subordinates;
- higher-level decisions;

not simply more units to micromanage.

This directly supports the wider Caerness rule:

> **Greater importance should produce higher-level decisions, not administrative spam.**

## 12. The battle must remember what happened

Battle outcomes should persist beyond the battle through:

- reputation;
- promotions;
- losses;
- relationships;
- institutional memory;
- strategic consequences;
- later historical interpretation.

v0.14 only establishes the battle-flow substrate. The later campaign and health layers will carry these consequences farther.

---

# v0.14 design conclusion

The central correction to v0.13 is:

> **A battle is not one contest with many units inside it. It is a network of local contests, command relationships, delayed information, and accumulating pressures whose interaction produces the strategic result.**

And the corresponding player rule is:

> **The protagonist can become decisive without the battlefield becoming protagonist-shaped.**
