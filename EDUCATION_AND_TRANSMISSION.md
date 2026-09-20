# v0.24 — Education, Transmission & Institutional Reproduction

v0.24 makes training, teaching, knowledge custody, transmission lines, certification, and institutional reproduction authoritative simulation state.

## Design rules

- Most martial artists have teachers; far fewer have a personal master.
- Ordinary teaching is scalable through instructors, branch structures, households, companies, local schools, and other institutions.
- Personal master–disciple transmission is a distinct enduring relationship rather than a synonym for receiving lessons.
- Manuals are media of transmission, not mastery objects. Access can support training but never grants competence by itself.
- Deep inheritance can require both a qualified teacher and explicit authority/access.
- Training takes story time. Programs have capacity, entry requirements, teacher requirements, cadence, duration, and bounded outcomes.
- A living teacher cannot train a student beyond the teacher's own established competence merely because a program's numerical gain is generous.
- Completed programs cannot be repeatedly farmed for competence.
- Institutions can possess recruitment/training/instructor/archive capacity and a derived pipeline health, but the engine never manufactures recruits or promotes successors merely to keep an institution alive.
- Successor candidates can become eligible through persisted readiness/legitimacy/transmission depth, but selection remains an explicit institutional act.
- Oral, embodied, or site-bound knowledge can become endangered and—only when a campaign-defined loss threshold exists—genuinely lost after custody/transmission fails.
- Transmission lines can become fragile or dormant when living transmitters disappear. The engine does not invent replacement masters.

## Persistent state

New v0.24 tables:

- `education_programs`
- `teaching_relationships`
- `education_enrollments`
- `knowledge_assets`
- `knowledge_custody`
- `knowledge_access`
- `program_knowledge_assets`
- `transmission_lines`
- `actor_transmissions`
- `professional_certifications`
- `institution_reproduction_profiles`
- `institutional_successor_candidates`
- `education_history`

## Shared-clock behavior

Education due dates participate in `advance_connection()`. Active programs progress off-camera. Teacher death, revoked knowledge authority, unavailable programs, and knowledge loss can pause or interrupt training without player presence.

Institutional reproduction profiles review their actual active students, paused students, living teaching depth, transmission lines, and archival problems. The result is structural pipeline health—not a destiny score and not an automatic succession engine.

## Camera integration

Scene packets now include `education_context`, containing the player's persisted enrollments, teachers, certifications, transmission-line membership, and knowledge access.

The narration boundary is explicit: access is not mastery, elapsed time alone is not mastery, and unrecorded master–disciple relationships or certifications must not be invented in prose.

## Deliberate boundaries

v0.24 does not create a universal school system, mandatory certification regime, named curriculum, or standardized martial bureaucracy. Those would exceed the current World Bible. Programs and knowledge assets are campaign state unless canon explicitly establishes them.

v0.24 also does not automatically advance cultivation Stage. It develops domain competence and transmission history; cultivation Stage remains a separate capability/state question.
