# v0.24 Adversarial Edge-Case Audit

This audit was run before accepting v0.24 as the next baseline.

## Audit standard

An education/transmission feature counts only if persistent authoritative state exists, shared story time can change it where appropriate, and adversarial tests demonstrate that knowledge and institutional continuity cannot bypass their own constraints.

## Cases tested

### Manuals and knowledge access
- Merely possessing or being allowed to study a manual does not increase competence.
- Required knowledge access is checked at enrollment and again while training continues.
- Required teacher authority/access is distinct from student access.
- Access can be revoked, regranted, and revoked again while preserving historical access rows.
- Lost/unavailable required knowledge interrupts training instead of being ignored.

### Teachers and transmission ownership
- Programs that require a teacher reject teacherless enrollment.
- Teachers must be living and meet persisted competence requirements.
- Teacher death pauses active training rather than silently completing it.
- Teaching relationships tied to a deceased teacher are interrupted.
- A replacement qualified teacher can resume a paused enrollment.
- Multiple teachers/mentors can coexist because ordinary instruction and personal mastery are distinct relationships.

### Competence progression
- Programs respect entry requirements, duration, capacity, and review cadence.
- A completed program cannot be repeated to farm competence or certificates.
- A program cannot elevate a student beyond the living primary teacher's actual domain competence merely because configured gain/max-score values are higher.
- Program completion can improve persisted domain competence and grant an explicit certification, but does not auto-advance cultivation Stage.

### Program capacity and duplicate state
- Capacity is enforced at authoritative enrollment time.
- Duplicate active/paused enrollment in the same program is rejected by runtime/schema constraints.
- Program completion is historical state, not a reusable active slot for the same student.

### Knowledge preservation and loss
- Documented knowledge can survive through institutional/archive custody.
- Oral/embodied/site-bound knowledge with no viable custody becomes endangered.
- Knowledge becomes truly lost only after a configured loss threshold, rather than immediately because a keeper dies.
- Custody owned by a dead character is closed by shared-clock review.

### Transmission lines
- Living teachers/inheritors/keepers sustain line vitality.
- A line with no living transmitters declines and can become dormant.
- The engine does not fabricate a replacement transmitter merely to preserve a lineage.

### Institutional reproduction and succession
- Institutional pipeline health is derived from actual teaching/training/archive state.
- Pipeline review does not create recruits, instructors, or successors.
- Successor candidates can become eligible, but are never automatically chosen.
- Dead candidates become unavailable and cannot be selected.
- Choosing a candidate records that explicit choice without silently changing unrelated political ruler or professional-office state.

### Off-camera behavior
- Education due dates participate in the shared authoritative story clock.
- Training can complete off-camera.
- Teacher death, knowledge loss, and institutional review can interrupt or change education state without player presence.

## Result

`tests/v24_test.py`: PASS  
`tests/v24_edge_test.py`: PASS  
Full cumulative `tests/run_all.py`: PASS

**Status: IMPLEMENTED, WIRED, ADVERSARIALLY AUDITED.**
