# v0.21 Adversarial Edge-Case Audit

**Audited release:** v0.21.0  
**Scope:** Religion & Cultural Institutions

The v0.21 audit was run before treating the release as the new baseline. It tests behavior rather than merely checking that schema tables or functions exist.

## Edge cases tested and hardened

### 1. No silent calendar canonization

Fresh initialization seeds religious tradition vocabulary but **zero feast days or observances**. This prevents the engine from silently deciding the exact seasonal calendar, ceremonies, foods, songs, or feast dates that the World Bible deliberately leaves open.

### 2. Sign-off-sensitive theology remains flagged

The Small True Faith is persisted as `signoff_pending`. The engine does not generate Christian analogue furniture, a universal clergy structure, or faction membership from it.

### 3. Religion is not faction alignment

Religious affiliation has no Churn-faction or moral-alignment field. A person can simultaneously participate in Hearth Rites and the Vigil where campaign state supports that social overlap. Faction does not automatically determine religion.

### 4. Affiliation updates are idempotent without deleting history

Updating an active affiliation changes that row rather than duplicating it. Ending an affiliation preserves the former relationship and its dates. A later renewed affiliation receives a new historical row.

### 5. Institution ownership is validated

Only institution actors can receive religious/cultural institution profiles. An observance attached to a religious institution must match that institution's configured tradition.

### 6. Backdating is rejected

New observances and obligations cannot be created with due dates already in the past. Historical reconstruction belongs to the crystallization/history layer rather than being smuggled through the live calendar API.

### 7. Repeated due processing cannot duplicate observances

Each observance/day pair is unique. Reprocessing the same story day does not create a duplicate rite or duplicate public event. Recurrence advances to the next scheduled occurrence.

### 8. Religious careers do not become immortal offices

Religious offices accumulate seniority as story time passes but do not auto-promote. A deceased officeholder is automatically removed from active office. Institutional dissolution also ends its active offices.

### 9. Patronage cannot mint money

Patronage checks the actual household liquidity or enterprise cash balance. Insufficient sponsorship does not drive the source negative or grant funds to the target. The relationship becomes strained instead.

### 10. Obligations cannot farm reputation

Overdue obligations lower only the dedicated `religious_reliability` reputation domain. Fulfilling an obligation can repair some standing, but fulfilling the same completed obligation repeatedly cannot award reputation again.

### 11. Cultural institutions stop acting after dissolution

A dissolved institution cannot continue producing scheduled performances, readings, exhibitions, or other programs. Pending programs pause rather than firing posthumously.

### 12. Cultural influence is bounded

A cultural program linked to a style can nudge existing local style adoption, but it cannot exceed the 0–100 adoption range and does not create a style movement out of nothing.

### 13. Off-camera life remains real

Religion and cultural programs use independent due dates in the authoritative simulation clock. They occur without requiring the player to be present or interested.

## Audit result

`v21_test.py` and `v21_edge_test.py` both pass, followed by the complete cumulative regression suite from v0.1 through v0.21.

**Result: PASS.** v0.21.0 is the new baseline for the next depth pass.
