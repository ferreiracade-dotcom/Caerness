# Caerness v0.15 — Tactical Grammar and Vein Battlefield Divergence

## Purpose

v0.14 established the multi-front command structure. v0.15 adds variation without turning battles into scripted puzzles or reproducing particular scenes from another work.

The design rule is:

> **Learn tactical grammar, not tactical scripts.**

Tactics are abstract reasoning families. They describe what kind of battlefield problem a commander is trying to create or solve, not the real-world geometry or weapon procedure used to do it.

## Tactical families

The engine recognizes ten broad families:

- **Pressure** — spend flexibility to create stronger local initiative.
- **Fixing** — keep an opposing element occupied so it has less freedom elsewhere.
- **Misdirection** — trade effort and certainty for a chance to distort the opponent's reading of priorities.
- **Isolation** — make one local problem harder to support.
- **Depth** — accept less immediate pressure in exchange for resilience and time.
- **Reserve play** — preserve flexible strength for later rather than commit it now.
- **Mobility** — change where strength matters, with coordination costs.
- **Attrition** — favor endurance and resource pressure over immediate decision.
- **Disruption** — attack coordination, information, or command clarity at an abstract level.
- **Exploitation** — enlarge an opening that already exists; without one it can become overreach.

None is a universal counter or winning move. Their value depends on state, commander doctrine, information, resources, fronts, subordinates, and the opponent's decisions.

## Commander doctrine

Commanders can carry persistent preferences across those families. Doctrine is a tendency, not a script.

A cautious commander may favor depth and reserve play. An aggressive commander may favor pressure and exploitation. Another may prefer disruption or misdirection. Context can still pull a commander away from their baseline.

This gives battles stylistic variation without assigning one faction a permanent rock-paper-scissors identity.

## Opportunity cost

Tactical choices should alter the structure of the problem rather than simply add a battle score.

A local push can spend reserve. A resilient posture can concede initiative. Mobility can strain coordination. Exploitation is powerful only if an opening already exists. Preserving reserves sacrifices current leverage.

> **Power gives leverage, not control.**

## Why Caerness is not simply Kingdom with renamed armies

The Vein changes battlefield logic.

Cultivators are not generic morale bonuses. They are finite strategic resources whose importance depends on:

- Stage;
- current reserve;
- readiness;
- battlefield role;
- where they are committed;
- local current density, stability, and replenishment;
- whether their presence is tied to command, a critical position, or a replaceable task.

The engine therefore separates raw martial importance from command competence.

> **Stage is not command competence.**

A Fifth can be a decisive battlefield asset and a poor general. A veteran lower-stage commander can make better operational decisions.

## Current geography

Battle zones can carry abstract current ecology values:

- density;
- stability;
- replenishment.

These affect how efficiently committed Vein assets can sustain themselves. Rich current does not grant a higher Stage or substitute for capability. Thin current does not make cultivation disappear. Geography changes sustainability and opportunity cost.

## Cultivator concentration

A side may distribute important cultivators across several fronts or concentrate them at one. The simulation does not encode a single correct answer.

Concentration can create a major local advantage while leaving other fronts without the same answer. Distribution creates resilience but may fail to create decisive local superiority.

This is handled as abstract allocation and opportunity cost, not real-world formation instruction.

## Personal combat and battle consequence

v0.14's strict local-only heroic shock was too restrictive for Caerness.

The corrected principle is:

> **Personal combat changes the battlefield through the strategic value of the people, positions, resources, and command structures involved. A duel may be trivial, locally important, operationally decisive, or in exceptional circumstances strategically decisive—but never merely because it was a duel.**

The consequence model therefore considers:

- the defeated person's Stage;
- importance of the front;
- command significance;
- replacement depth;
- the side's existing morale/cohesion fragility.

A strategically important Fifth or Sixth falling at the critical point of an already fragile plan can trigger a collapse. The same Sixth falling far from the principal decision, with good replacement and a stable army, may have only local or operational effect.

This gives Caerness:

> **Heroic consequence without heroic determinism.**

## Implementation boundary

The system remains deliberately abstract. It does not attempt to teach real-world battlefield tactics, weapon handling, formations, or violence. It stores causal categories useful for fantasy simulation and narrative resolution.
