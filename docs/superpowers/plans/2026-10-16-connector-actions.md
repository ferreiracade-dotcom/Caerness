# Connector Actions (gap 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The protagonist can pay, hire, lend, demand, attack, buy or sell, and give orders through `act`; the engine checks feasibility, decides contested outcomes from its own models, and records the consequences in its real tables.

**Architecture:** A money layer (`engine/ledger.py`) gives one transfer primitive across purses, treasuries, business cash and household liquidity. `engine/player_operations.py` holds seven general operations that wrap existing engine code. `connector/acting.py` routes the new action types to them inside `run_once`. Outcomes are tiered by what is at stake (owner baseline: "The world decides attempts and outcomes"; "degree of simulation follows the significance of the consequence"):
- **Tier 1, only the protagonist's own will** (moving own money, reassigning own staff): validate and record, no roll.
- **Tier 2, someone else's will or strength** (a payment demanded, a job offered, a loan, a sale, a fight): the engine decides with its existing models (`interactions._social_response` drives and relationships, `interactions._capacity`, `harm.record_harm`, `civilian_life` credit).
- The GM narrates how it happens and invents everything the engine is silent on; it never narrates an outcome the engine did not return.

**Tech Stack:** Python 3.13, SQLite; tests are plain `python tests/<name>.py` scripts.

**Spec:** `docs/superpowers/specs/2026-10-16-claude-connector-design.md` (§5 `act`, §6, §7 tiers). Owner baseline: `D:\Theology\Caerness_Agreed_Narrative_Design_Baseline_2026-10-16.md` line 12. Engine survey of reusable functions is summarised in the task Interfaces below.

## Global Constraints

- General parameters only (spec §5): who, what, with what, toward whom, under what terms; no per-activity verbs beyond the seven action types below.
- Every `act` call is idempotent through `store.run_once` (call_id).
- No engine figure in what the GM is told to show: results carry amounts as scale words (`ledger.scale_word`), never numbers. Holdings may keep numbers for the GM (rulebook already forbids printing them).
- Nobody is manufactured: hires, debtors and victims are existing actors; `resolve_background_person` stays the only way to reveal new people.
- Money never goes negative; an operation that cannot be paid is refused, or partial when the payer is someone else (a debtor pays what they have).
- Only the protagonist's own holdings and people he commands can be drawn on: own purse; businesses he owns or where he is staff with authority >= 60 (`merchant.authorized_enterprises`); an outfit where he is `boss` or `underboss` (`underworld_personnel`); his household where he is head.
- Contested actions require the target in the same location as the actor who carries them out (`actors.current_location_id`), except `pay`.
- Never write `data/caerness.db`; tests copy it.

## Review Focus

1. Paying or lending more than the source holds, from a holder the protagonist does not control, or to a dead/absent target: refused with a reason, nothing written.
2. A debtor ordered to pay more than they have: pays what they have, the rest stays owed, result says "partial".
3. Two attackers named twice, a companion who is not present, or the target already dead: refused, no harm rows.
4. An `order` to someone who is not the protagonist's subordinate, or who is in another town: refused.
5. Retrying any operation with the same call_id: one set of money rows, one harm row, one interaction.

---

### Task 1: Money layer

**Files:** Create `engine/ledger.py`; Test `tests/ledger_test.py`.

**Interfaces (Produces):**
- `Holder = tuple[str, int]` with kind in `("person", "business", "outfit", "household")`.
- `parse_holder(ref: str, me: int) -> Holder`: `"me"` → `("person", me)`; `"person:12"`, `"business:3"`, `"outfit:12"`, `"household:7"`; anything else `ValueError("holder must be me, person:<id>, business:<id>, outfit:<id> or household:<id>")`; unknown id `ValueError(f"unknown {kind} {id}")`.
- `balance(conn, h: Holder) -> float`: person → `underworld_leader_wealth.liquid_wealth` if a row exists, else `resources.amount` where `resource_type='cash'` (0 if none); business → `civilian_enterprises.cash`; outfit → `underworld_organizations.treasury`; household → `households.liquidity`.
- `transfer(conn, src: Holder, dst: Holder, amount: float, *, flow_kind: str, purpose: str, allow_partial: bool = False) -> float`: returns the amount moved; `ValueError("not enough money")` when `amount > balance(src)` and not partial; partial moves `min(amount, balance)`; household credit also raises `wealth`; person credit creates the `resources` cash row if missing; writes one `economic_flows` row through `underworld_rebuild._record_economic_flow` (flow_kind must be in its CHECK list; use `other` for purchases and loans).
- `SCALES = {"token": 0.2, "small": 1.0, "modest": 3.0, "substantial": 8.0, "large": 20.0, "fortune": 60.0}` (engine units; calibrated to racket costs 1.2-3.5 and fronts 6-14). `amount_of(word: str) -> float` (`ValueError` listing `SCALES` keys). `scale_word(x: float) -> str`: nearest key by log distance; `"nothing"` for `x < 0.05`.
- `can_draw(conn, me: int, h: Holder) -> bool` per the Global Constraints authority rule.

- [ ] **Step 1: Failing test** `tests/ledger_test.py` (copy packaged DB, `init_db`): create an enterprise with `civilian.create_enterprise(... owner_actor_id=me, cash=10)`; assert `transfer(conn, ("business",e), ("person",me), 4, flow_kind="other", purpose="t") == 4`, business cash 6, person balance +4, one new `economic_flows` row; `transfer(... 100 ...)` raises "not enough money" and writes nothing; `allow_partial=True` moves exactly 6; `scale_word(8) == "substantial"`, `scale_word(0.01) == "nothing"`; `parse_holder("outfit:999999", me)` raises "unknown outfit"; `can_draw` true for own business, false for a business owned by someone else.
- [ ] **Step 2: Run** `python tests/ledger_test.py` → FAIL (ModuleNotFoundError).
- [ ] **Step 3: Implement** `engine/ledger.py` as specified.
- [ ] **Step 4: Run** → `ledger_test passed`.
- [ ] **Step 5: Commit** `feat(engine): ledger moves money between purses, treasuries, businesses and households`.

### Task 2: Operations module with pay and hire, wired into `act`

**Files:** Create `engine/player_operations.py`; Modify `connector/acting.py`, `connector/server.py` (`act` signature/docstring); Create `tests/fixtures_protagonist.py`; Test `tests/player_operations_test.py`, `tests/connector_act_test.py`.

**Interfaces:**
- Consumes Task 1.
- Produces: `OPERATIONS = ("pay", "hire", "lend", "demand", "attack", "trade", "order")`; `execute(conn, actor_id: int, op: str, *, target_actor_id: int | None, details: dict, intent: str) -> dict` returning `{"status": "applied"|"refused"|"partial", "summary": str, ...}`; never raises for player mistakes (refusals are results); writes one `events` row per applied/partial operation (`event_type='player_operation'`, visibility local) so news and memory see it.
- `tests/fixtures_protagonist.py`: `make_boss(conn) -> dict` builds, in a copied packaged world, a protagonist in Toll's Reach with an outfit (`create_underworld_organization` + `create_personnel(role_kind="boss", actor_id=me)`, treasury 10), a business he owns (cash 10), a household he heads, one crew with a leader (`create_crew`), and returns `{"me","outfit","business","household","crew","crew_leader","bystander"}` (`bystander` = a living adult character in the same location who is none of the above).
- Connector: `ACT_TYPES` gains the seven operations; `act(..., details: dict | None = None)`; for an operation type `act` validates `intent`, then calls `player_operations.execute(conn, me, action_type, target_actor_id=..., details=details or {}, intent=intent)` inside `run_once`, with `elapsed_days` 0. Server docstring (keep short): `"Attempt a consequential action; narrate only what returns. Types: observe, speak, investigate, respond, travel, pay, hire, lend, demand, attack, trade, order. details: from/to ('me','business:<id>','outfit:<id>','household:<id>','person:<id>'), amount (token|small|modest|substantial|large|fortune), role, what, with (ids), crew, intent_kind, deal, business, do."`
- `pay` (tier 1): details `to` (holder ref), `amount`, `from` (default `"me"`), `purpose`. Refused unless `can_draw(from)`; `flow_kind` `wage` when `purpose` says wage else `other`.
- `hire`: target = person; details `into` (`business:<id>` | `outfit:<id>` | `household:<id>`), `role`, optional `amount` (wage offered per month, scale word). Already the protagonist's staff/personnel → tier 1 reassignment. Otherwise tier 2: `interactions.create_interaction(me, target, "offer", day, stakes=2, terms={"incentive": min(2.0, amount/1.5), "operation": "hire"})` then `resolve_interaction` at once; on `accept` → `merchant.add_enterprise_staff` / `underworld_rebuild.create_personnel(actor_id=target, role_kind=role or "member")` / `household_life.add_service_term`; on refusal → `status "refused"`, summary says they turned it down.

- [ ] **Step 1: Failing tests.** `player_operations_test.py`: `pay` 'substantial' from `business:<b>` to `me` applied, balances move by 8, result summary contains "substantial" and no digits; `pay` from someone else's business refused; `hire` the crew leader into the business is tier 1 applied; `hire` the bystander into the outfit with `amount="modest"` returns accept or refused, and on accept an `underworld_personnel` row exists, on refusal none; no new actors are created by any call. `connector_act_test.py` (extend the existing one): `act(conn, "op-1", "pay", "I pay Varen", details={...})` applied; same call_id again → `replayed`, money moved once.
- [ ] **Step 2: Run both** → FAIL.
- [ ] **Step 3: Implement** module, fixture, connector routing and server signature.
- [ ] **Step 4: Run** `player_operations_test`, `connector_act_test`, `connector_server_test`, `connector_http_test` → all pass (update tool-size assertion only if it fails, keeping it <= 7000).
- [ ] **Step 5: Commit** `feat: act pays and hires through the engine ledger and interaction model`.

### Task 3: Lend and demand (collecting, pressure, extortion)

**Files:** Modify `engine/player_operations.py`, `engine/interactions.py:353-395` (`_social_response`); Test `tests/player_operations_test.py`, `tests/interactions_coercion_test.py`.

**Interfaces:**
- `_social_response` reads `terms["coercion"]` (0-3, default 0) and, for `demand`/`threat` only, adds `0.45 * coercion` to the score. Nothing else changes for existing callers (they never set it).
- `coercion(conn, proposer: int, backers: list[int], recipient: int) -> float` in `player_operations`: `sum(_capacity(p) for p in [proposer]+backers) / max(0.5, _capacity(recipient) + protection)` mapped to 0-3 by `min(3, max(0, 1.5 * log2(ratio) + 1))`, where `protection` is the summed `_capacity` of the recipient's household members present and, if the recipient is in an outfit, that outfit's `violence_capacity / 25`.
- `lend` (tier 2): target = borrower; details `amount`, `from` (default `"me"`), `rate` (`low` 0.02 | `usual` 0.05 | `steep` 0.12 per 30 days), `due_days` (default 90). Borrower answers an `offer` (incentive 1.0 + need: 1.0 if their balance < amount else 0); accept → `ledger.transfer(from → person:target)` and `civilian_life.create_credit_agreement(principal=..., lender_actor_id=me or lender_enterprise_id, borrower_actor_id=target, interest_rate_per_30=rate, due_day=day+due_days)`.
- `demand` (tier 2): target = person; details `what` in (`payment`, `debt`, `stop`, `information`, `other`), `amount` (for payment/debt), `with` (list of actor ids present with the protagonist) or `crew` (`crew:<id>`, counts as leader + `min(size_estimate, 8)` men of capacity 1.0), `open` (bool: open threat → `threat`, else `demand`). Creates the interaction with `terms={"coercion": coercion(...), "what": what}` and resolves at once. On `comply`: `payment` → `ledger.transfer(person:target → me, allow_partial=True)`; `debt` → `civilian_life.make_credit_payment` on the target's open agreements with the protagonist or his businesses (oldest first) using what the target can pay (`ledger.transfer` partial), status `partial` if anything stays owed; others record the concession only. On refusal or when the target resists: status `refused`, summary from the interaction result; if `open` and the protagonist is in an outfit, `underworld_rebuild.add_heat(conn, outfit, public=2, violence=0)`.

- [ ] **Step 1: Failing tests.** `interactions_coercion_test.py`: for 200 seeded demand interactions between two fixed actors, compliance rate with `coercion=3` is higher than with `coercion=0` by at least 0.25; with no `coercion` key the score equals the old formula (compare one interaction's resolution before and after on a copy). `player_operations_test.py`: lend 'modest' to the bystander → on accept a `credit_agreements` row with borrower = bystander and money moved; demand `what="debt"` with the crew backing → comply or refused, and on comply the agreement's outstanding falls by what the bystander could pay (status `partial` when the bystander's balance is below what is owed); demand toward someone in another location → refused "not here"; crew of another outfit → refused.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `interactions_coercion_test`, `player_operations_test`, `v25_test` (social interactions regression) → pass.
- [ ] **Step 5: Commit** `feat: act lends and makes demands; the force behind a threat weighs on the answer`.

### Task 4: Attack

**Files:** Modify `engine/player_operations.py`; Test `tests/player_operations_test.py`.

**Interfaces:** `attack` (tier 2): target = person present; details `with`/`crew` as in demand, `intent_kind` in (`drive_off`, `beat`, `kill`). Sides: attackers = protagonist + backers; defenders = target + protection people present (same rule as `coercion`). `ratio = sum(_capacity(attackers)) / max(0.01, sum(_capacity(defenders)))`, `roll = ratio * rng.uniform(0.75, 1.25)` with `rng = random.Random(f"attack:{world_seed}:{call_id}")` (deterministic per call). `roll > 1.35` → attackers win: `harm.record_harm(target, source_kind="player_operation", source_ref_id=<event id>, severity={"drive_off": 15, "beat": 45, "kill": 90}[intent_kind], intent_class="hostile")`. `roll < 0.75` → defenders win: `record_harm` on one attacker (protagonist only if alone, else the weakest backer) with severity 35. Otherwise both sides take severity 20 on one member each. Relationships via `relationships.adjust_relationship_pair` as in `interactions._resolve_attack`; outfit heat `add_heat(violence=4, public=3)` (`kill`: violence 10, investigative 6). Result: `{"status": "applied", "outcome": "won"|"lost"|"stalemate", "hurt": [{"name", "how": harm outcome}], "summary"}`; `execute` passes `call_id` through `details["_call_id"]` set by the connector.

- [ ] **Step 1: Failing tests:** attack the bystander with the crew backing, `intent_kind="beat"` → one `harm_incidents` row per hurt person and an event; repeating with the same call_id via `connector.acting.act` adds no harm rows; target in another town → refused; target dead → refused; a backer listed twice → refused "listed twice".
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `player_operations_test`, `connector_act_test` → pass.
- [ ] **Step 5: Commit** `feat: act attacks; the engine decides who is hurt from capacity, harm is recorded`.

### Task 5: Trade a business, and orders through subordinates

**Files:** Modify `engine/player_operations.py`; Test `tests/player_operations_test.py`.

**Interfaces:**
- `trade`: details `deal` in (`buy`, `sell`), `business` (`business:<id>`), `amount` (price, scale word), `from`/`to` holder for payment (default `"me"`). `buy`: counterparty = the business owner (`owner_actor_id`); `offer` with `incentive = 2 * (price - value) / max(1, value)` clamped to [-2, 2] where `value = capital + cash - debt`; accept → `ledger.transfer(payer → person:owner)` and `UPDATE civilian_enterprises SET owner_actor_id=me`. `sell`: target = buyer (present), same valuation from the buyer's side (`incentive = 2 * (value - price) / max(1, value)`), buyer must be able to pay (refused "cannot afford" otherwise); accept → transfer and ownership to buyer, and the protagonist's `enterprise_staff` owner row removed.
- `order`: target = the subordinate who carries it out; details `do` in (`pay`, `demand`, `attack`, `lend`, `hire`) plus that operation's details and `toward` (actor id for the operation's target). Valid subordinates: active `underworld_personnel` of an outfit the protagonist bosses, or `enterprise_staff` of a business he owns. The subordinate must be in the same town as `toward` (else refused "not in town"). Runs `execute(conn, subordinate, do, target_actor_id=toward, details=...)` with the subordinate as actor but drawing money only from holders the protagonist can draw on; result wrapped as `{"status", "report": <inner summary>, "by": <subordinate name>, ...}`.

- [ ] **Step 1: Failing tests:** sell the fixture business to the bystander at `amount="fortune"` → refused "cannot afford" unless the bystander can pay (set bystander cash with `ledger.transfer` from a seeded holder first, then accept or refused); buy a business owned by another actor at `"fortune"` → accept likelihood shown by one deterministic case; `order` the crew leader to `demand` a debt from the bystander → result has `by` = crew leader's name; `order` the bystander (not a subordinate) → refused.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `player_operations_test`, `connector_act_test` → pass.
- [ ] **Step 5: Commit** `feat: act trades businesses and gives orders through subordinates`.

### Task 6: Rulebook, scene means, deploy

**Files:** Modify `connector/rulebook.md` + spec Appendix A, `connector/session.py` (`HOW_TO_PLAY` line 2), `connector/views.py` (`_holdings`); Test `tests/connector_resume_test.py`, `tests/connector_views_test.py`.

- `_holdings` adds `"means"`: `{"purse": scale_word, "outfit_treasury": scale_word, "business_cash": {name: scale_word}}` so the GM can judge what Ansel can afford without numbers.
- `HOW_TO_PLAY` line 2: `"2. Consequential intentions go through act first (pay, hire, lend, demand, attack, trade, order, or the scene actions); then write the scene, dialogue and detail around what it returns."`
- Rulebook, **The world** section, add after the `act` bullet: `- Choose the approach yourself from the character and the scene: who goes, how many men, what is offered or threatened, how much. The engine decides whether it works; you decide how it plays out. A refusal, a partial payment or a lost fight is the story, not a mistake to smooth over. Things nobody else could resist (moving the protagonist's own money, reassigning his own people) simply happen.`
- [ ] **Step 1: Failing tests:** resume test asserts the new rulebook sentence "The engine decides whether it works"; views test asserts `holdings["means"]["purse"]` is a scale word and `json.dumps(holdings["means"])` has no digits.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `connector_resume_test`, `connector_views_test`, `connector_server_test`, `connector_http_test`, `player_operations_test`, `ledger_test` → pass.
- [ ] **Step 5: Commit** `docs(connector): rulebook and scene for consequential actions`.
- [ ] **Step 6: Deploy** (owner must allow push/SSH): push `feat/claude-connector`, then `update.sh` on the server; owner phone playtest: Ansel collects from a debtor through Varen's crew, pays a man, and gets into a fight.

Out of scope: goods trading (merchant contracts), protection rackets on zones (Toll's Reach has no zones until gap 4), multi-day orders (orders resolve now), property other than businesses, tier-3 GM-decided outcomes beyond `note`.
