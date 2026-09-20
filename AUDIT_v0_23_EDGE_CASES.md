# v0.23 Adversarial Edge-Case Audit

This audit was run before accepting v0.23 as the next baseline.

## Audit standard

A political feature counts only if it has persistent authoritative state, participates in runtime story time where appropriate, and survives adversarial tests. Descriptive prose or an unused schema does not count.

## Cases tested

### Polity identity
- A character actor cannot be configured as a polity.
- A dead character cannot be installed as ruler.
- The engine seeds no campaign polities automatically.

### Territorial authority
- One crystallized location has one authoritative controller row.
- Reassigning control produces a transfer rather than duplicate ownership.
- Transfers update `locations.political_owner` for compatibility.
- A dissolved polity cannot acquire territory.

### State dissolution
- A polity controlling territory cannot simply be dissolved and orphan its land.
- Supplying a successor transfers all controlled territory before dissolution.
- Active hierarchy links involving the dissolved polity are closed.
- Active territorial claims belonging to the dissolved polity fail.

### Political hierarchy
- Direct self-subordination is rejected.
- Indirect vassal/protectorate/tributary cycles are rejected.
- Ordinary federation/personal-union records remain distinct from hierarchical reachability.

### Succession
- Ruler death is detected by shared-clock political review.
- Dead succession claimants are marked and excluded.
- A clear established claimant may resolve ordinary succession.
- Equal or near-equal claims produce `succession_crisis` instead of arbitrary selection.
- Manual resolution requires an already-established living active claimant.

### Territorial claims
- Claims below threshold do not alter borders.
- A claim reaching threshold follows its persisted campaign resolution policy.
- Transfer policy causes a real authoritative control change and history entry.
- Dispute policy can mark control politically disputed without pretending ownership changed.

### Off-camera political change
- Political due dates participate in the shared story clock.
- Succession and territorial-claim events occur without player presence.
- Political structural processes can change persisted polity/territory state off-camera.

### History and continuity
- Political transitions append durable history rather than overwriting the past.
- The current map can change while historical ownership remains reconstructable from the ledger.

## Result

`tests/v23_test.py`: PASS  
`tests/v23_edge_test.py`: PASS  
Full cumulative `tests/run_all.py`: PASS

**Status: IMPLEMENTED, WIRED, ADVERSARIALLY AUDITED.**
