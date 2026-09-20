# Caerness Narrative Engine Architecture
## Post-v0.7 Consolidated Design Specification

**Status:** design target after Engine v0.7  
**Relationship to v0.7:** additive. This document does not replace v0.7's authority, persistence, model-gateway, information, competence, agency-handoff, or mobile-runtime rules. It defines the next architectural layer those systems must support.

---

# 0. Governing Premise

> **Caerness is a persistent world simulation with a narrative camera inside it.**

The player character is the focus of the player's experience, not the causal center of the world.

The engine maintains a society with its own chronology, people, institutions, economies, wars, families, professions, cultures, information networks, regional pressures, and accumulated history. The player experiences one life inside that society.

Two tests govern the design:

> **World test:** If the player character vanished from the database for a year, would Caerness still produce a plausible year of history?

> **Game test:** If the wider simulation continued plausibly for a year, would the player's experience still feel like a meaningful life rather than passive observation of a database?

Both answers must remain yes.

The master summary is:

> **Simulate broadly. Resolve selectively. Present personally. Preserve continuity everywhere.**

---

# 1. v0.7 Invariants That Remain Binding

The following are inherited, not reopened.

## 1.1 Camera Principle

> **The player is the story's camera focus, not the world's protagonist or causal center.**

Camera attention never:
- activates a faction;
- weakens an enemy;
- delays a distant event;
- creates unrelated NPC interest;
- reroutes major events toward the protagonist;
- improves outcome probability merely because the player is present.

The protagonist may become historically important by actually becoming important.

## 1.2 Emergent Story Principle

> **Caerness does not generate plots. It generates circumstances, consequences, and continuity from which plots can emerge.**

The engine may recognize a developing thread. Recognition has no authority to force another beat.

## 1.3 Earned Outcome Principle

> **The camera may be lucky about what it gets to see. It is not lucky about what happens next.**

Defeat, loss, imprisonment, injury, decline, missed opportunities, and player-character death remain possible where causality supports them.

Sustained prosperity, stable relationships, repeated success, unusually fortunate lives, and quiet decades are equally legitimate.

## 1.4 Experienced World Principle

> **The World Bible establishes what is true. Play determines what becomes known.**

World truth and character knowledge remain separate.

## 1.5 Character Competence Principle

> **The player controls decisions. The character handles competence.**

The player is not expected to remember, articulate, or technically execute everything their character would naturally know or do.

## 1.6 Agency Handoff Principle

> **A scene ends when fiction changes beat. A player turn ends when meaningful agency becomes useful.**

The engine pauses when continuing would resolve a meaningful unresolved player choice.

## 1.7 Authority Boundary

Models may:
- interpret;
- propose;
- explain;
- narrate.

The engine validates.

Persisted state owns truth.

Narration never retroactively creates a war, relationship change, possession, person, route, agreement, injury, or outcome.

## 1.8 Shared Story Time

Real-world absence does not advance Caerness.

When the protagonist spends six in-world days travelling, six days pass for everyone.

## 1.9 Dormant Never Means Frozen

The existing `ACTIVE`, `STRATEGIC`, and `DORMANT` profiles remain valid computational actor tiers.

They are not protagonist-relevance labels.

---

# 2. Core Philosophy

## 2.1 Protagonist-Agnostic Causality

> **Anything the player can accomplish through ordinary world systems must also be achievable by simulated actors through those same systems.**

The player has no private causal privilege.

NPCs can:
- become great masters;
- conquer territory;
- lose kingdoms;
- found institutions;
- create great works;
- build fortunes;
- ruin fortunes;
- produce famous children or disciples;
- establish dynasties;
- die obscurely.

The world must remain capable of surprising the player because other lives are genuinely occurring.

## 2.2 Protagonist-Centered Attention

> **Causality is protagonist-agnostic; attention is protagonist-centered.**

The world does not bend toward the player, but presentation does.

The engine preferentially surfaces developments relevant to:
- current goals;
- relationships;
- profession;
- location;
- obligations;
- threats;
- opportunities;
- identity;
- social position.

Player goals affect visibility and search, not underlying probability.

## 2.3 No Emotional Ledger

> **Do not manufacture adversity to compensate for success. Do not manufacture success to compensate for adversity.**

Good and bad outcomes may cluster.

Loss is permitted, not preferred.

Success is permitted, not suspicious.

## 2.4 Success Changes Reach

> **Success increases reach. Increased reach exposes the character to larger opportunities, responsibilities, rivals, institutions, and conflicts. It does not create an adversity debt.**

A famous Sixth attracts strategic attention because a Sixth matters.

A rich merchant receives larger proposals because wealth creates reach.

A great architect receives royal commissions because reputation creates demand.

This is consequence, not rubber-banding.

## 2.5 Loss Changes the Story

> **Failure of the current objective is not failure of the narrative.**

A defeated king may become:
- captive;
- exile;
- client ruler;
- claimant;
- dispossessed noble.

A bankrupt merchant may become:
- salaried factor;
- debtor;
- partner in a smaller venture.

A wounded warrior may become:
- instructor;
- commander;
- administrator.

The campaign can continue in a changed life.

---

# 3. Persistent Agent Architecture

## 3.1 Characters Accumulate Lives, Not States

Important actors need persistent models containing, as appropriate:
- identity;
- age and origin;
- family;
- culture;
- class/status;
- profession;
- institutions;
- competence;
- temperament;
- values;
- habits;
- goals;
- loyalties;
- fears;
- relationships;
- wealth/resources;
- health;
- reputation;
- knowledge;
- obligations;
- major memories;
- unresolved pressures;
- current emotional state.

A character is not "merchant, age 52." They are someone who became a merchant, passed through institutions, knew people, survived events, and accumulated habits.

## 3.2 Traits Are Tendencies

"Rude," "brave," "cruel," "devout," "patient," or "loyal" are not scripts.

Traits change:
- probability;
- interpretation;
- expression;
- preferred behavior.

They do not mechanically dictate every action.

## 3.3 Persistent but Developmental

The protagonist and important NPCs are allowed to change.

Development should arise from:
- repeated behavior;
- sustained relationships;
- major experiences;
- profession;
- age;
- deliberate choices;
- long-term pressure.

Do not force a predetermined arc.

## 3.4 Reputation Is Separate From Personhood

Different groups may hold different views.

A person can simultaneously be:
- hero to soldiers;
- brute to courtiers;
- monster to enemies;
- beloved parent;
- admired collector.

There is no single universal reputation number.

---

# 4. Protagonist Embodiment and Autonomous Behavior

## 4.1 Player Intent vs Character Execution

> **The player supplies intention and judgment; the character supplies embodied expertise.**

This applies to:
- martial combat;
- generalship;
- trade;
- medicine;
- architecture;
- court etiquette;
- administration;
- scholarship;
- craft;
- speech.

## 4.2 Speech Mediation

Player wording is not automatically literal character speech.

Unless explicitly marked exact, player dialogue input should be interpreted as:
- intended meaning;
- desired content;
- emotional direction;
- social objective;
- rough tone.

Actual speech is rendered through:
- personality;
- education;
- culture;
- status;
- relationship;
- social skill;
- current emotion;
- context.

> **Do not infer bluntness merely because the player typed bluntly.**
>
> **Do not infer eloquence merely because the player typed eloquently.**

Possible informal modes:
- **intent mode:** "Tell him I will support him if..."
- **guided dialogue:** "Say something like..."
- **exact dialogue:** "I say exactly..."

## 4.3 Expression vs Commitment

The engine may infer low-stakes, high-confidence protagonist expression:
- gestures;
- habitual profanity;
- a familiar greeting;
- mild irritation;
- characteristic humor;
- body language.

It should be cautious about autonomous commitment:
- oath;
- marriage;
- betrayal;
- declaration of war;
- execution of an important captive;
- permanent allegiance;
- major confession.

> **The engine has broad freedom over expression and narrow freedom over irreversible commitment.**

## 4.4 Player Character Death

The player character can die.

Soft plot armour may modestly prefer continuation only inside genuinely uncertain outcome space.

Strong causality overrides it.

A personal campaign may end at death.

A generational campaign may move the camera to:
- child;
- heir;
- disciple;
- sibling;
- another appropriate successor.

The dead protagonist then becomes a historical person inside the world.

---

# 5. Competence, Careers, and Training

## 5.1 Domain-Specific Competence

Stage, wealth, title, and age do not grant universal expertise.

Separate competence domains may include:
- martial execution;
- command;
- political judgment;
- administration;
- commerce;
- medicine;
- craft;
- social perception;
- scholarship;
- regional familiarity;
- institutional knowledge.

A Sixth may be politically naive.

A Closed-Core chancellor may be a brilliant administrator.

## 5.2 Character Knowledge vs Advice

The player-facing decision layer should distinguish:
- **character knowledge** — what competence lets the protagonist understand;
- **reports** — what others actually communicate;
- **advisor judgment** — opinions of named advisors;
- **player decision** — final choice.

The player may always ask:

> **What does my character think the sensible options are?**

The engine should provide plausible options, not a hidden "correct answer."

## 5.3 Expertise Warns, It Does Not Override

If a player gives an expert character a poor deliberate order, the engine should surface the character's professional warning.

The player may still insist.

> **Expertise informs and intelligently executes the player's intentions; it does not silently replace deliberate decisions.**

## 5.4 Careers Are Trajectories

People should move through plausible professional stages.

Examples:
- blacksmith apprentice → journeyman → independent smith → workshop master;
- merchant apprentice → factor → partner → principal;
- martial disciple → practitioner → instructor → master;
- student → junior scholar → established academic;
- junior officer → captain → commander → senior authority.

Starting situations can begin at any of these points.

## 5.5 Starting Difficulty Is Circumstance Difficulty

There is no simulation Easy/Hard setting that alters causality.

There may be:
- easy cultivation start;
- difficult political start;
- wealthy household;
- roadside nobody;
- secure prince;
- disputed heir;
- peaceful decade;
- invasion year.

The simulation remains the same.

---

# 6. Perception, Uncertainty, and Information

## 6.1 Distinct Information Layers

The engine distinguishes:
- objective reality;
- direct observation;
- reports;
- inference;
- rumor;
- deception;
- unknowns.

A character never sees SQLite.

## 6.2 Confidence

Claims can carry internal confidence based on:
- firsthand observation;
- source reliability;
- corroboration;
- professional expertise;
- known bias;
- elapsed time.

Visible percentages are unnecessary.

Player-facing prose may instead say:
- credible;
- uncertain;
- independently corroborated;
- likely exaggerated;
- unresolved.

## 6.3 Expertise Improves Interpretation

The same evidence can mean different things to different characters.

A merchant sees liquidity trouble where a novice sees late shipments.

A general recognizes a dangerous deployment pattern.

A collector notices suspicious restoration.

Expertise improves inference, not hidden truth access.

## 6.4 Deception Must Have a Cause

The engine does not lie merely to create a twist.

Deception requires an actor or institution trying to mislead for a reason.

## 6.5 Truth, Belief, Public Story, and Record Are Separate

The engine should distinguish:
- what happened;
- what an actor believes;
- what a community believes;
- what documents claim.

Historical disagreement is possible without database inconsistency.

---

# 7. Emotion, Stress, and Morale

## 7.1 Emotional State

Behavior emerges from:

**baseline temperament + current emotion + accumulated stress + immediate context + self-control/experience**

Emotion modifies pressure and interpretation.

It does not automatically control behavior.

## 7.2 Stress

Long-term stress may affect:
- patience;
- attention;
- risk appetite;
- social tolerance;
- decision quality.

Support, routine, wealth, faith, friendship, and experience may mitigate it.

## 7.3 Group Morale

Armies, workshops, households, institutions, crews, and cities may develop morale/cohesion factors such as:
- confidence in leadership;
- fatigue;
- trust;
- pay;
- supplies;
- recent losses;
- expected success;
- shared identity.

Avoid one simplistic global morale bar where a richer model is warranted.

---

# 8. Households, Families, and Domestic Life

## 8.1 Household as Institution

A household may include:
- family;
- servants;
- retainers;
- apprentices;
- guards;
- tutors;
- guests;
- clerks;
- dependents.

Household scale varies enormously.

## 8.2 Domestic Labor Exists Without Micromanagement

Food, clothing, childcare, repairs, cleaning, animals, hosting, and accounts are real processes.

They are usually lightly simulated.

## 8.3 Long-Term Staff Can Matter

A steward, nurse, clerk, or household retainer may become a decades-long relationship.

## 8.4 Children Have Developmental Environments

Children grow up inside:
- courts;
- workshops;
- military households;
- merchant houses;
- universities;
- religious institutions;
- martial lineages.

They do not become fully formed NPCs at adulthood.

## 8.5 Domestic Peace Is Allowed

Stable marriages, friendships, families, and households may remain stable for decades.

The engine does not generate betrayal because stability seems narratively insufficient.

---

# 9. Religion and Lived Belief

Religion is represented through:
- worship;
- prayer;
- holy days;
- pilgrimage;
- burial;
- marriage rites;
- charity;
- sacred music;
- sacred art;
- vows;
- education;
- moral expectations;
- institutions.

Belief intensity and practice vary by person.

Religion can shape:
- calendar;
- reputation;
- moral interpretation;
- oaths;
- patronage;
- architecture;
- charity;
- public life.

Sacred objects are not necessarily treated as ordinary commodities.

---

# 10. Health, Aging, Injury, and Recovery

Health is more than combat HP.

The simulation may include:
- ordinary illness;
- chronic disease;
- injury;
- occupational wear;
- old injuries;
- disability;
- convalescence;
- aging.

Recovery takes time.

Different competencies age differently.

Disability can change a career without ending relevance.

Ordinary medicine, cultivation medicine, and Vein-Mending remain distinct layers.

> **Health changes capacity and life trajectory rather than merely toggling characters between combat-ready and dead.**

---

# 11. Ecology, Seasons, and Environment

The natural world creates recurring conditions rather than random catastrophe.

Relevant systems may include:
- seasons;
- harvest;
- roads;
- rivers;
- passes;
- shipping conditions;
- drought;
- flood;
- wildfire;
- agriculture;
- mining;
- forestry;
- current ecology.

Current geography remains its own system:
- density;
- stability;
- replenishment;
- breadth;
- concentration.

Natural disasters should be rare enough to remain historically significant.

Human activity may alter landscapes over decades.

---

# 12. Economy, Production, Labor, and Prices

The engine does not need perfect economics.

It does need coherent dependencies.

## 12.1 Production Chains

Examples:

textiles:
fiber → processing → spinning → weaving → dyeing → tailoring → sale;

metal:
mining → transport → refining → smithing → sale/use;

construction:
land → design → materials → transport → skilled labor → building;

Vein-Root:
growing → harvest → transport → refinement → use.

## 12.2 Labor

The world contains:
- ordinary labor;
- skilled labor;
- apprentices;
- journeymen;
- masters;
- clerks;
- sailors;
- miners;
- farmers;
- administrators.

> **Material shortages can often be solved through trade. Expertise shortages take generations.**

## 12.3 Prices

Prices should vary by:
- region;
- supply;
- demand;
- transport;
- risk;
- tax;
- season;
- market scale.

Merchant competence should turn complex causes into actionable interpretation rather than unexplained number changes.

## 12.4 Credit and Debt

Large commerce may use:
- partnerships;
- loans;
- collateral;
- guarantees;
- letters/accounts;
- pooled risk.

Debt is a tool as well as a vulnerability.

## 12.5 State Finance

States need plausible income and costs.

War, roads, courts, armies, patronage, and institutions consume resources.

Money does not spawn from political importance.

---

# 13. Arts, Culture, Fashion, and Material Civilization

Culture is a major simulation system, not decoration.

It includes:
- music;
- painting;
- sculpture;
- architecture;
- textiles;
- fashion;
- books;
- manuscripts;
- jewelry;
- furniture;
- decorative metalwork;
- instruments;
- performance;
- gardens;
- monuments;
- public works;
- master weapons.

## 13.1 Historical Depth

Not all famous creators are alive.

The world contains:
- remembered masters;
- old canon figures;
- vanished workshops;
- old styles;
- revivals;
- disputed attributions;
- inherited collections;
- famous buildings;
- lost techniques.

> **The current generation adds to an existing cultural tradition rather than creating culture from nothing.**

## 13.2 Cultural Professions

Important professions may include:
- architect;
- painter;
- sculptor;
- musician;
- composer;
- weaver;
- tailor;
- dyer;
- jeweler;
- smith;
- bookbinder;
- copyist;
- restorer;
- dealer;
- auctioneer;
- appraiser;
- librarian.

Famous individuals rest on real professional ecosystems.

## 13.3 Textiles and Fashion

Textiles connect:
- agriculture;
- trade;
- dye;
- weaving;
- tailoring;
- military supply;
- luxury;
- status;
- regional identity.

Fashion propagates socially and changes over time.

## 13.4 Architecture

Buildings can be long-term expressions of:
- wealth;
- piety;
- civic ambition;
- dynasty;
- taste;
- legitimacy.

A building persists after the commissioner dies.

## 13.5 Provenance

Significant objects may track:
- creator;
- date;
- commissioner;
- owners;
- sale;
- inheritance;
- war capture;
- restoration;
- attribution;
- current location.

Important objects can have biographies.

## 13.6 Culture and Underworld

Cultural goods create shadow economies:
- theft;
- fencing;
- forgery;
- illicit antiquities;
- fake provenance;
- counterfeit textiles;
- corrupt auctions;
- stolen estate material;
- looted collections.

The underworld is specialized, not one universal thieves' guild.

## 13.7 Cultural Prestige Is Not Martial Power

> **Human excellence is not monopolized by martial power.**

A Fifth is not automatically a better architect, musician, administrator, merchant, or sculptor.

---

# 14. Institutions, Networks, Patronage, and Law

Institutions include:
- courts;
- guilds;
- merchant houses;
- universities;
- military bodies;
- workshops;
- schools;
- religious institutions;
- auction houses;
- criminal networks.

Institutions have:
- history;
- procedures;
- internal actors;
- culture;
- memory;
- succession;
- resources;
- reputation.

Patronage may support:
- education;
- appointments;
- commissions;
- workshops;
- research;
- artists;
- apprenticeships.

Financial debt and social obligation are distinct.

Law may vary by:
- crown;
- locality;
- guild;
- religion;
- military jurisdiction;
- commercial custom.

Contracts, enforcement, and legal access should matter without becoming paperwork simulators.

---

# 15. War and Battle Architecture

A major battle is not one contest.

The simulation must model a changing system of:
- objectives;
- commands;
- formations;
- terrain;
- morale;
- information;
- reserves;
- fatigue;
- logistics;
- cultivator deployment;
- subordinate initiative;
- local crises;
- changing objectives.

> **Do not force every major battle toward protagonist centrality.**

Personal combat may alter local conditions, sometimes decisively, but strategic victory emerges from the whole battlefield.

## 15.1 Rank Changes Experience

A junior fighter sees a local slice.

A unit commander receives orders and limited reports.

A general receives broader but incomplete synthesis.

A ruler/campaign commander deals with mobilization, appointments, supply, and fronts.

A Sixth who is not a general remains a strategic martial asset, not automatically a commander.

## 15.2 NPC Commanders Use the Same Model

NPCs should receive:
- information appropriate to their position;
- professional interpretation appropriate to competence;
- goals;
- risk preferences;
- doctrine;
- subordinate quality.

No player-only tactical physics.

---

# 16. Duel Architecture

The player should not be required to write realistic weapon technique.

The engine handles technical exchange.

The player controls high-level choices such as:
- objective;
- risk posture;
- resource posture;
- strategic approach;
- whether to reveal an art;
- whether to disengage;
- whether to protect/capture rather than finish.

Character perception deepens with competence and Stage.

Advancement should feel partly like **seeing more of the fight**, not only increasing numbers.

The duel loop is conceptually:

> **perception → player intention → character execution → changed state → new perception**

---

# 17. Narrative Presentation

## 17.1 Presentation Is Not Simulation

The engine may know much more than the player sees.

A scene should contain what the protagonist can reasonably:
- witness;
- know;
- remember;
- infer;
- access.

## 17.2 Solve Boredom With Life

> **Solve boredom by revealing opportunity, relationship, work, culture, ambition, and change — not by manufacturing catastrophe.**

Positive milestones have equal narrative eligibility:
- first major commission;
- promotion;
- successful project;
- marriage;
- child beginning a career;
- recognition;
- artistic discovery;
- peaceful prosperity.

## 17.3 Simulation Depth Should Improve Scenes

> **Simulation depth should create better scenes, not heavier exposition.**

Do not dump every system state into prose.

Let the machinery surface only when relevant.

---

# 18. Resolution Architecture

This extends v0.7's actor tiers with a broader world-resolution model.

The conceptual levels are:

## 18.1 Scene

Moment-to-moment simulation.

Used for:
- conversation;
- duel;
- negotiation;
- auction;
- medical treatment;
- battle decision;
- important ceremony;
- critical domestic interaction.

## 18.2 Active

Detailed persistent state and ongoing agency without constant narration.

Examples:
- close family;
- current rival;
- active commander;
- workshop;
- major venture;
- war directly affecting current life.

## 18.3 Tracked

Persistent entity with meaningful compressed development.

Examples:
- old master elsewhere;
- regional Fifth;
- recurring merchant;
- famous auction house;
- building commissioned by the player.

## 18.4 Structural

Most civilization.

Represented through:
- institutions;
- cohorts;
- demographics;
- regional metrics;
- aggregate economy;
- state processes;
- population distributions.

## 18.5 Latent

Implied by established world structure but not yet individually instantiated.

> **Latent does not mean newly created. It means previously undescribed.**

These conceptual levels may map onto or extend the existing `ACTIVE / STRATEGIC / DORMANT` implementation rather than replacing it mechanically.

---

# 19. Historical Crystallization

A person first encountered at fifty must not have a blank first fifty years.

The engine reconstructs biography from already-established constraints:
- age;
- birthplace;
- class;
- profession;
- regional history;
- wars;
- institutions;
- cohort;
- economy;
- cultural conditions;
- career pathway.

Historical crystallization is:

> **retroactive detail generation constrained by pre-existing history.**

Once generated, it becomes campaign truth.

## 19.1 Progressive Crystallization

Do not generate a full biography merely because a person says hello.

Crystallize only what current interaction requires.

If that person later becomes important, deepen their history.

## 19.2 Anti-Convenience Firewall

> **Newly crystallized history should primarily explain the entity that already exists, not conveniently solve the protagonist's current problem.**

Do not repeatedly generate:
- secret old friendships with exactly the needed person;
- perfectly useful prior jobs;
- convenient family connections;
- hidden knowledge tailored to the current scene.

Past generation should be identity-facing, not plot-facing.

---

# 20. Anchors and Connective Tissue

## 20.1 Historical Anchors

Facts that materially constrain future continuity should be persisted.

Examples:
- birth;
- parents;
- marriage;
- children;
- teacher;
- major institution;
- office;
- important battle;
- severe injury;
- major property;
- allegiance;
- Stage attainment;
- masterwork;
- death.

## 20.2 Connective Tissue

Routine periods may remain compressed:
- ordinary work;
- minor travel;
- routine acquaintances;
- unremarkable seasons.

> **Persist consequences. Compress routine.**

---

# 21. Continuity Cores

Persistent entity types require compact continuity records suited to their nature.

## 21.1 Person Core

May include:
- identity;
- origin;
- family;
- residence;
- profession;
- affiliation;
- competence;
- temperament;
- important relationships;
- health;
- wealth;
- goals;
- reputation;
- anchors;
- unresolved obligations.

## 21.2 Institution Core

May include:
- founding;
- purpose;
- leadership;
- internal structure;
- resources;
- culture;
- rivals;
- historical turning points;
- current trajectory.

## 21.3 Place Core

May include:
- population;
- economy;
- institutions;
- social composition;
- notable families;
- infrastructure;
- cultural reputation;
- current conditions.

## 21.4 Object Core

For significant objects:
- maker;
- date;
- provenance;
- condition;
- restoration;
- current owner/location;
- cultural reputation.

Most ordinary objects do not need persistence.

---

# 22. Immutable World Ledger

Consequential events require an append-only historical ledger.

A ledger event should know, as appropriate:
- date;
- place;
- involved entities;
- objective outcome;
- changed state;
- privacy/publicity;
- provenance;
- major consequences.

Narration is not history.

Regenerated prose never rerolls ledger truth.

---

# 23. Reality, Belief, Record, and Memory

At minimum the engine conceptually separates:
- objective ledger truth;
- actor beliefs;
- public narratives;
- documentary records;
- personal memories.

A later chronicler may be wrong while the engine remains consistent.

---

# 24. Promotion and Demotion of Resolution

Resolution may increase because:
- the protagonist meets an entity;
- an entity becomes powerful;
- an active crisis requires detail;
- a relationship forms;
- an institution enters the protagonist's life;
- a work becomes culturally significant.

Resolution may decrease when immediate relevance falls.

> **Resolution may change. Continuity may not.**

Demoted entities continue to live at coarser cadence.

---

# 25. Simulation Cadence

Different systems should update at causally appropriate frequencies.

Conceptually:

**scene/continuous**
- combat;
- conversation;
- immediate negotiation.

**daily-ish**
- movement;
- acute illness;
- active operations.

**weekly/monthly**
- commerce;
- training;
- household management;
- political maneuvering;
- projects.

**seasonal**
- harvest;
- campaigning;
- trade patterns;
- construction;
- migration.

**annual**
- aging;
- births;
- career shifts;
- institutional changes;
- long-term wealth.

**multi-year**
- demographic drift;
- urban growth;
- artistic movements;
- technology diffusion;
- deep institutional change.

> **Simulation frequency should match causal frequency.**

---

# 26. Causal Queues and Open Threads

The engine should track processes already in motion rather than repeatedly asking "what happens next?"

Examples:
- building completion;
- maturing loan;
- approaching apprenticeship;
- military mobilization;
- declining ruler health;
- artwork nearing completion;
- unresolved succession.

Open threads are unresolved causal situations, not scripted quests.

They may:
- resolve;
- expire;
- cool into background;
- become more serious.

Persistent obligations should not disappear merely because scenes moved on.

---

# 27. Attention Filtering

Many things may happen while only a few deserve foreground presentation.

Rank developments by:
- personal relevance;
- consequence;
- urgency;
- novelty;
- goal relevance;
- relationship strength;
- professional relevance;
- historical significance.

Possible presentation levels:
- full scene;
- short interaction;
- report/letter;
- summary;
- background-only.

> **Attention weighting changes visibility, never probability.**

---

# 28. Cohorts as Historical Compression

Cohorts can preserve shared generation-level experience without individual simulation.

Examples:
- Ravenfield class of a certain period;
- veterans of one war;
- university cohort;
- workshop generation;
- merchant apprentices during a boom;
- artistic school.

When an individual later crystallizes, cohort history supplies plausible constraints.

Population structure creates priors, not destiny.

---

# 29. Institutions and Geography as Compression Nodes

Institutions can carry:
- pipelines;
- norms;
- staff structure;
- cohorts;
- resources;
- reputations.

Places can carry:
- demographics;
- economy;
- institutions;
- cultural expectations;
- current pressures.

These structures allow later generation of people who feel historically embedded rather than randomly spawned.

---

# 30. Latent Works and Cultural Production

Historical creators need not have every surviving work pre-instantiated.

A famous dead painter, smith, architect, composer, or textile workshop may have a latent body of work.

New works may crystallize later if consistent with:
- known output scale;
- historical period;
- oeuvre/style;
- provenance;
- geography;
- survival;
- prior catalogues.

> **Latent cultural production follows the same rule as latent people: undescribed is not nonexistent.**

---

# 31. Time Skips

A time skip is compressed simulation, not age addition.

Procedure:

1. capture protagonist intention;
2. identify obligations and delegated authority;
3. advance world processes;
4. advance protagonist career, health, wealth, family, and relationships;
5. resolve major interruptions;
6. persist new anchors;
7. present a compressed bridge;
8. resume at an appropriate agency point.

> **Compression ends where consequential player choice begins.**

Delegated matters may continue without interruption if the player explicitly delegated them.

---

# 32. Delegation and Scale

As a character's reach grows, delegation should grow with it.

A powerful character should not receive exponential micromanagement.

Examples:
- merchant principal → factors/managers;
- ruler → ministers;
- general → subordinate officers;
- master smith → foremen/senior apprentices;
- Sixth → household staff, disciples, envoys.

> **Greater importance should produce higher-level decisions, not administrative spam.**

NPC subordinates should act competently within delegated authority according to their own competence and incentives.

---

# 33. Causal Attribution

The engine should preserve who or what caused important outcomes.

Potential causal owners:
- player decision;
- protagonist automatic competence;
- protagonist autonomous expression;
- delegated subordinate;
- NPC decision;
- institution;
- environment;
- random uncertainty.

Do not later blame the player for a subordinate's mistake unless the player's own decisions materially caused it.

Historical reputation may still assign blame incorrectly; objective causality should not.

---

# 34. Randomness and Fixity

> **Unobserved does not mean unfixed once causally resolved.**

If something has already been resolved offscreen, later observation cannot reroll it.

Conversely:

> **Resolve a detail when something causally depends on it. Once resolved, persist it.**

Unneeded latent detail may remain undecided until first causal relevance.

---

# 35. Contradiction Hierarchy

New generated facts must respect, in descending priority:

1. hard setting canon / current World Bible;
2. explicitly established campaign facts;
3. World Ledger events;
4. entity continuity cores;
5. persisted anchors;
6. records and public narratives;
7. generated connective tissue;
8. disposable descriptive flavor.

Lower layers never silently overwrite higher layers.

If conflict appears:
- regenerate;
- reinterpret;
- mark disputed knowledge;
- or stop for explicit design resolution.

---

# 36. Setting Canon vs Campaign History

Setting canon defines the world framework.

Campaign-generated history defines what occurred in one playthrough.

Campaign history must obey setting canon.

It does not automatically rewrite universal setting canon.

This preserves replayability.

---

# 37. Aggregate-First, Individual-Second Simulation

Large systems should generally resolve at the highest level that preserves causal truth.

For war:
- armies;
- formations;
- logistics;
- command;
- morale;
- objectives;

then descend to individuals where agency can matter.

For economy:
- production;
- supply/demand;
- transport;
- labor;

then descend to particular merchants where agency matters.

For institutions:
- leadership;
- resources;
- cohorts;
- culture;

then descend to individuals.

Important individuals may then bubble upward and change macro outcomes.

Simulation must flow both directions.

---

# 38. Historical Compression and Snapshots

Long campaigns require periodic state compression.

Preserve:
- major wars;
- rulers;
- dynastic transitions;
- economic changes;
- cultural movements;
- important people;
- institutional reforms;
- disasters;
- major inventions;
- personally important history.

> **History should be dense around change and sparse around stability.**

Periodic state snapshots should preserve:
- borders;
- rulers;
- wars;
- major institutions;
- protagonist state;
- family;
- assets;
- relationships;
- obligations;
- key developments.

Old detailed scenes may be archived into minimum sufficient causal memory.

---

# 39. Minimum Sufficient Causal Memory

Compression should preserve the facts necessary to explain later behavior.

Bad:
> "Had dispute with Mercer."

Better:
> "Mercer withheld payment on the Northwater shipment; arbitration recovered half. Persistent financial distrust remains."

The goal is neither exhaustive memory nor shallow summary.

It is:

> **minimum sufficient causal memory.**

Domain-specific compression is preferable to generic biography compression.

---

# 40. Invariants Firewall

The resolver must enforce setting and engine invariants.

Examples:
- Stage is not command rank;
- Stage is not universal competence;
- cultivation cannot simply be given;
- Closed Core is not illness;
- the Churn is not all martial society;
- a Sixth cannot be everywhere;
- wealth does not automatically grant noble status;
- provenance persists;
- player importance does not grant causal privilege;
- success does not create adversity debt.

---

# 41. Worldbuilding Uncertainty vs In-World Uncertainty

The engine must distinguish:

**design unresolved:** the creators have not decided;

from:

**world unknown:** the answer exists but characters do not know it.

The simulation must not silently settle open worldbuilding questions as universal canon.

A campaign-specific answer may be generated when needed if it does not conflict with hard canon, but should remain campaign history unless explicitly promoted into setting canon.

---

# 42. Positive Milestone Eligibility

Narrative attention must not be danger-biased.

Scene-worthy events can include:
- achievement;
- affection;
- recognition;
- successful creation;
- maturation;
- prosperity;
- discovery;
- reunion;
- peaceful succession;
- completion of a building;
- apprentice becoming master;
- child entering a profession.

Quiet life is not content failure.

---

# 43. Anti-Convenience and Anti-Destiny Rules

## 43.1 Do Not Invent Significance

Persistence does not promise future relevance.

The cobbler met once does not need to become king.

The painting mentioned at dinner does not need a hidden secret.

## 43.2 Importance Emerges

NPC importance should arise from:
- talent;
- opportunity;
- institutions;
- decisions;
- relationships;
- luck;
- history.

Do not secretly mark random children as destined for later plot importance.

Potential is not destiny.

---

# 44. Runtime Conceptual Loop

The post-v0.7 simulation loop should conceptually become:

1. read authoritative state;
2. identify due processes by cadence;
3. resolve actor/system interactions;
4. apply authoritative consequences;
5. write consequential events to history;
6. update continuity cores and obligations;
7. promote/demote resolution where warranted;
8. crystallize latent details only where causally needed;
9. validate new facts against canon and continuity;
10. propagate information;
11. rank player-relevant developments;
12. choose scene/report/summary/background presentation;
13. render through protagonist knowledge, competence, personality, culture, and current state;
14. stop at meaningful agency boundaries.

The model remains outside the authority boundary.

---

# 45. Stress-Test Findings Incorporated

Three conceptual tests were used:

## 45.1 Historical Freak

Confirmed:
- success must enlarge social/causal reach;
- it must not generate compensatory tragedy;
- high status requires stronger delegation/filtering;
- reputation should be socially and geographically uneven.

## 45.2 Windmere Merchant Apprentice

Confirmed:
- noncombat lives need real progression;
- expertise must explain underlying economic complexity;
- positive milestones must receive narrative attention;
- late-career progression should shift toward delegation, legacy, succession, and patronage.

## 45.3 Fifty-Year-Old Newly Met Professional

Confirmed:
- old NPCs need pre-existing lives;
- progressive historical crystallization is viable;
- crystallization requires anti-convenience constraints;
- cohort and institutional history are valuable compression structures.

---

# 46. Core Rules Summary

The strongest post-v0.7 rules are:

> **Simulate broadly. Resolve selectively. Present personally. Preserve continuity everywhere.**

> **Causality is protagonist-agnostic; attention is protagonist-centered.**

> **The player supplies intention and judgment; the character supplies embodied expertise.**

> **Characters accumulate lives, not merely states.**

> **Low resolution is not nonexistence.**

> **Latent does not mean newly created. It means previously undescribed.**

> **Resolve a detail when something causally depends on it. Once resolved, persist it.**

> **Persist consequences. Compress routine.**

> **Resolution may change. Continuity may not.**

> **Historical crystallization must explain existing identity rather than conveniently serve the current scene.**

> **Attention weighting changes visibility, never probability.**

> **Success increases reach, not adversity debt.**

> **Loss changes the story; it does not inherently end it.**

> **Narrative preference operates inside uncertainty, never against causality.**

> **History is current state with memory.**

> **Power gives leverage, not control.**

> **Solve boredom with life, not manufactured disaster.**

> **Positive milestones are as narratively valid as danger and loss.**

> **Simulation depth should create better scenes, not heavier exposition.**

> **Greater importance should produce higher-level decisions, not administrative spam.**

> **Minimum sufficient causal memory is preferable to both exhaustive memory and shallow summaries.**

---

# 47. Relationship to Engine v0.7

The existing v0.7 implementation already provides important foundations this design should build on rather than replace:

- canonical retrieval;
- SQLite world truth;
- state/history/knowledge/camera separation;
- `ACTIVE / STRATEGIC / DORMANT` actor resolution;
- dormant actors continuing off-camera;
- world/regional processes;
- shared story time;
- route-based information propagation;
- player-safe scene packets;
- action interpretation before mutation;
- narration after authoritative resolution;
- persistent intentions and obligations;
- contextual competence cues;
- emergent actor memories and thread evidence;
- `none / open / hard` agency handoffs;
- local/external model routing;
- transactional save integrity;
- spoiler separation;
- developer observability.

The architecture above should therefore be implemented as an **extension of v0.7's authority model**, not as a parallel narrative system.

The clean development principle is:

> **v0.7 owns authority and runtime safety; the post-v0.7 architecture supplies the deeper world, character, resolution, historical, economic, cultural, battle, and presentation systems that authority will govern.**

---

# 48. Next Implementation Targets

After this specification, the next design/implementation passes should be:

1. **Schema extension**
   - continuity cores;
   - historical anchors;
   - objective ledger/public narrative separation;
   - cohorts;
   - career stages;
   - institutions as compression nodes;
   - resolution promotion/demotion metadata.

2. **Historical crystallization service**
   - constrained biography generation;
   - anti-convenience validation;
   - campaign-canon persistence.

3. **Character embodiment service**
   - speech mediation;
   - persistent protagonist model;
   - autonomous-expression confidence;
   - commitment firewall.

4. **Competence interpretation**
   - domain profiles;
   - professional readings;
   - advisor separation;
   - actionable interpretation.

5. **Time-skip resolver**
   - intentions;
   - obligations;
   - world advancement;
   - interruption thresholds;
   - compressed historical bridge.

6. **Battle and duel resolvers**
   - rank-sensitive information;
   - formation/unit state;
   - subordinate agency;
   - high-level player intent;
   - character execution.

7. **Civilian simulation**
   - careers;
   - households;
   - economy;
   - textiles;
   - culture;
   - architecture;
   - auctions;
   - provenance;
   - underworld overlap.

8. **Long-run simulation tests**
   - 20-year;
   - 40-year;
   - 100+ year;
   - protagonist death/camera succession;
   - political-map divergence;
   - quiet-life campaign;
   - extreme-success campaign;
   - institutional succession;
   - historical crystallization consistency.

---

# 49. Final Design Statement

Caerness should not feel like a story-generator disguising itself as a world simulation, nor like a world simulator that forgot it was meant to be played.

The intended balance is:

> **Simulate the world strongly enough that the protagonist is not its cause. Simulate the protagonist deeply enough that the world still feels like their life.**

That is the post-v0.7 target.
