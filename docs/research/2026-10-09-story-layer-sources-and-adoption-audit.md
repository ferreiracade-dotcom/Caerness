# Story layer sources, and an audit of earlier adoptions

**Date:** 2026-10-09
**Checkpoint read:** `master` at `b118590` (schema 108, PERF-01 in progress)
**Purpose:** (1) survey Cicero and similar systems for what Caerness's story layer can borrow; (2) check whether the sources in `EXTERNAL_CODE_ADOPTION_LEDGER_2026-09-17.md` were adopted the way the ledger says.
**Outcome:** design proposals in `docs/superpowers/specs/2026-10-09-story-layer-design.md`. Nothing here changes engine code.

## 0. Why this matters for Caerness

Caerness exists because the earlier Narrative Engine games had to invent the world on the spot: inconsistencies, a small world, and characters and threads that changed only when the player asked. The simulation answers that for the world itself. This review found two places where the old failure mode survives in the layer between the simulation and the player:

1. **NPC speech is still invented at narration time.** `engine/player.py:126-147` gives the narrator present actors as `id, name, actor_type, subtype, status` only ("Deliberately no goals, drives, pressures, resources or hidden relationships here"). The narrator therefore has nothing to ground what an NPC says, wants or promises, so it makes it up.
2. **The world's changes mostly do not reach the player as stories.** `engine/emergence.py:107-131` recognises threads by word overlap, shared place and shared participants, and only ever creates a generic "Developing situation" thread (`emergence.py:168`). There is no notion of a betrayal, a rivalry, a rise or a fall.

## 1. Cicero and similar systems

| Source | What it is | Verdict for Caerness |
|---|---|---|
| **CICERO** (Meta, 2022), [repo](https://github.com/facebookresearch/diplomacy_cicero) | Diplomacy agent. A planner (DiL-piKL) picks intents for itself and predicts others; a dialogue model writes messages conditioned on those intents; messages inconsistent with the plan are filtered. Code MIT except `fairdiplomacy_external` (AGPL); weights CC-BY-NC 4.0. Archived read-only 17 Apr 2025. | **Pattern to adopt, code rejected.** Two ideas carry over: speech is conditioned on the speaker's actual intent, and generated messages are checked against that intent before use. piKL's "regularise toward a typical-human policy" is a cheap idea for DEC-01. The code is Diplomacy-specific, GPU-scale and archived; the weights are non-commercial. |
| **Concordia** (Google DeepMind), [repo](https://github.com/google-deepmind/concordia), [v2 report](https://arxiv.org/pdf/2507.08892) | Generative agent-based modelling library. Agents state intended actions in language; a Game Master entity decides what actually happens. Entity-component design. `pip install gdm-concordia`. | **Reference only.** Its Game Master is the same authority split Caerness already has (model proposes, engine validates, SQLite records), which is a useful confirmation. It needs an LLM call per agent action, which a phone with a 3-4B model and hundreds of actors cannot afford. |
| **Generative Agents / Smallville** (Park et al. 2023), [paper](https://huggingface.co/papers/2304.03442), [genagents repo](https://github.com/joonspk-research/genagents) | Memory stream scored by recency, importance and relevance, plus periodic "reflection" summaries. | **Reference only.** Caerness already has structured `actor_memories` with significance and fading (PERF-01). Prose memories as authority are explicitly rejected by DESIGN §29. |
| **Project Sid / PIANO** (Altera, 2024), [paper](https://arxiv.org/pdf/2411.00114), [repo](https://github.com/altera-al/project-sid) | 10 to 1,000 LLM agents in Minecraft; concurrent modules kept coherent so talk matches action. Preprint; authors call results preliminary. | **Reference only.** Its stated problem (agents' words drifting from their actions) is the same problem SPEECH-01 addresses, at a cost Caerness cannot pay. |
| **Richelieu** (NeurIPS 2024), [paper](https://arxiv.org/pdf/2407.06813) | LLM Diplomacy agent with a social-reasoning module that infers others' intentions, plus self-play memory. | **Reference only.** Supports adding shallow models of others' intentions (see the PsychSim finding below). |
| **Felt** and **Winnow** (Kreminski et al.), [Felt](https://github.com/mkremins/felt), [Winnow](https://github.com/mkremins/winnow), [Winnow paper (AIIDE 2021)](https://ojs.aaai.org/index.php/AIIDE/article/view/18903) | "Story sifting": declarative patterns over an event log that find storyful sequences (example: violation of hospitality). Winnow matches incrementally and partially, so it can see a story while it is still unfolding. Winnow's repository states no license. | **Pattern to adopt (SIFT-01), implement natively.** This is the missing piece behind finding 2 above. Do not copy code: Winnow has no stated license. |
| **James Ryan, *Curating Simulated Storyworlds*** (Talk of the Town, Hennepin, Bad News, Sheldon County), [dissertation](https://escholarship.org/uc/item/1340j5h2) | "Overgenerate and curate": simulate a large world, then mine its history for stories. Talk of the Town centres on what characters know and how knowledge passes, mutates and is lied about. | **Pattern to adopt.** Caerness already overgenerates. It lacks the curation step (SIFT-01) and the mutating-knowledge half (see audit). |
| **Versu** (Evans, Short, Nelson) and **Praxish**, [Versu paper](https://www.cs.uky.edu/~sgware/reading/papers/evans2014versu.pdf), [Praxish (AIIDE)](https://ojs.aaai.org/index.php/AIIDE/article/download/27537/27310) | Social practices: a recurring situation (a dinner, a negotiation, a greeting) offers actions to participants, but each agent still chooses by utility. | **Conditional.** A good model for the speech acts in SPEECH-01 if scene-level conversation grows beyond a handful of acts. Versu itself is unplayable and unreleased; Praxish is a reconstruction. |
| **Comme il Faut / Prom Week**, **Ensemble** (UCSC) | Social-exchange rules with volition scores. No public code found in this review. | **Reference only.** Caerness interactions already cover this ground. |
| Dwarf Fortress legends, Crusader Kings | Large simulated histories surfaced through legends views, chronicles and character-driven schemes. Commercial, no code. | **Design reference.** Both show that a living world is felt through the surfacing layer, not the simulation alone. |
| RimWorld's storyteller | A director that schedules events for drama. | **Rejected.** A director that shapes outcomes for drama breaks DESIGN §27.3 and §29. |

Not verified in this review, so not relied on: DipLLM, the every.to "AI Diplomacy" project.

## 2. Audit of earlier adoptions

Method: licence hygiene first, then for the load-bearing sources, compare what the ledger says against the code. This follows the owner rule "don't trust README/acceptance claims: verify with data".

### 2.1 Licence hygiene: clean

- Python imports across `engine/`, `tools/`, `tests/`, `game/`, `mobile/` are the standard library plus `numpy`. No third-party package from the ledger is a runtime dependency.
- No licence headers, vendored directories or third-party files exist anywhere in git history.
- Copyleft sources the ledger flags (SOCSIM GPL, NegMAS AGPL, SCML GPL-family, OpenFisca AGPL, WOFOST EUPL): no source names and no signature identifiers (`ufun`, `reserved_value`, `SAOMechanism`, OpenFisca `formula_YYYY`, SOCSIM rate files) in the code. The Gompertz-Makeham curve in `engine/health.py` is a public formula, not borrowed code.
- Code that names a source: `background_population.py` (Starsim, MIT), `process_registry.py` (Vivarium, permissive), `information.py` (Neighborly, MIT), `underworld_rebuild.py` comments (Minerva BSD-3, PsychSim, NetworkX). All attributions are comments describing a pattern.

Verdict: nothing was copied that the ledger says should not have been.

### 2.2 Fidelity: where the ledger overstates

| Source and ledger claim | What the code does | Assessment |
|---|---|---|
| **NegMAS**, "PATTERN INCORPORATED AS DESIGN: persistent negotiation/offer/issue/deadline concepts" | `interactions.py` has offers, counters, depth and due days. The recipient decides by one scalar of relationship numbers, drives, incentive, burden and noise against a fixed 1.0 threshold (about lines 370-410). A counter is a fixed adjustment: burden minus 0.25, incentive plus 0.20 (lines 508-512). | **Half adopted.** The protocol shape is there; NegMAS's core is missing. In NegMAS each party has a utility function over outcomes and a reserved value (its walk-away point), and responds by comparing an offer's utility for itself against that floor. Caerness never asks whether the terms serve the recipient's own goals and pressures. Proposed fix: DEAL-01. |
| **PsychSim**, "BELIEF/DEC use subjective information envelopes and shallow models of important others" | Subjective envelopes: yes (`decisions.build_actor_context`). Models of others: not found. `information_claims` are propositions about events (`authoritative_event_id`), not about another actor's goals or likely response. Underworld candidates carry fixed risk constants (for example `risk=.70` for retaliation, `underworld_decisions.py:70`), not a prediction of the target's reaction. | **First half adopted, second half not found.** I could not find any "shallow model of important others". If it exists under another name, the ledger should say where. |
| **Vivarium Core**, "explicit process contracts/ownership/read-write/dependency discipline" | `ProcessSpec` has `reads`, `writes`, `emits` fields (`process_registry.py:51-53`). All 32 registrations leave them empty, and nothing reads them. | **Shape adopted, contract absent.** In Vivarium the declared ports are what a process may touch. Here the declaration is empty and unchecked, so it gives no protection. Low urgency; either fill and test it or drop the claim. |
| **transitions**, "declarative lifecycle/state-machine discipline" | Statuses are limited by SQL `CHECK` lists. No transition tables or guards were found. | **Overstated.** A `CHECK` constrains which states exist, not which moves between them are legal (for example `broken` back to `active`). Low urgency. |
| **SOCSIM**, "competing-risk/eligibility life-course thinking" (conceptual) | Opening history uses annual discrete-time hazards drawn one after another (`opening_family.py:195-218`). Run-time births follow a planned next-child day plus spacing (`household_life.py:798-823`), not a hazard. | **Conceptual only, and acceptable.** Sequential annual draws approximate competing risks well when hazards are small. Worth knowing; not worth changing now. |
| **Talk of the Town**, "consequence propagation, inheritance/continuity, business ≠ building" | Rumours carry a `distortion` scalar that only lowers confidence (`information.py:370-442`). Rumour text is always generated from the true event. Nothing in the engine creates `contradicts` evidence (the only caller is World Bible sex correction, `demographic_sex.py:126`). | **Missed its main lesson.** Talk of the Town is above all about knowledge that mutates, is misremembered and is lied about. In Caerness every rumour is true but uncertain, and the belief system's `contradicts` path is never reached in play. That is the "silently disconnected system" pattern the owner rules warn about. Proposed fix: RUMOUR-02. |

### 2.3 Fidelity: consistent with the ledger (spot checks, not exhaustive)

- **Minerva** (BSD-3, archived 7 Apr 2026; its README says characters "select actions using utility scores" and admits behaviours were unfinished): DEC-01's candidate and utility split matches that pattern.
- **abcEconomics** conservation: non-negative quantity `CHECK`s, dispatch as the conservation boundary (`logistics.py:118`), conserved craft lots (`craft.py:432`). Consistent; not traced end to end.
- **Starsim** People/Arr: stable raw slots and `active_uids` in `background_population.py`. Consistent.
- **Mesa**: inspected and deliberately not adopted, with a measured reason (`process_registry.py:17-24`). Consistent.

Not checked in this pass: Neighborly presence (it has its own comparison report, PRESBACK-01), Brunnfeld, Little Lives, Victoria-Like, the economy, geography and health rows beyond the spot checks above.

## 3. Recommended order

1. **SPEECH-01** (intent-grounded NPC speech): fixes finding 1, which is the most direct return of the old failure mode. It adds narration-time work only, not per-day simulation cost, so it does not compete with PERF-01.
2. **SIFT-01** (story sifting): fixes finding 2. Runs incrementally over new rows; must be budgeted against PERF-01.
3. **RUMOUR-02** (false and garbled knowledge): reconnects the `contradicts` path. Touches rumour spreading, which PERF-01 is optimising now, so it should wait for PERF-01's batching work.
4. **DEAL-01** (terms valued against the recipient's own goals, with a walk-away point): after PERF-01, as a merchant or underworld slice.
5. Ledger corrections for Vivarium and transitions: documentation only, any time.
