# Caerness Named-Person Age / Birth-Date Repair

**Scope:** World Bible master + current simulation seed

## Policy

- No named persistent person may remain age-unknown merely because earlier prose was light.
- The civil calendar remains open, so exact birthdays are represented as opening-relative `birth_day` integers.
- Existing canon ages/relationships/roles are preserved; only missing values are assigned.
- Historical dead figures receive concrete birth/death chronology and age at death.

## Repaired missing ages

| Person | Age | Basis |
|---|---:|---|
| Maurice Penn | 55 | Established Fifth-stage free Undertow warlord with an existing following; mature but still active career. |
| Brock Ames | 41 | Breach-stage free Undertow light seed; mature professional-age practitioner without further fixed chronology. |
| Vaughn Hester | 48 | Breach-stage free Undertow light seed; older than Brock by working choice to avoid cohort uniformity. |
| Clive Orton | 36 | Third-stage free Undertow light seed; established adult practitioner. |
| Tucker Hewitt | 44 | Third-stage free Undertow light seed; older mid-career practitioner to preserve heterogeneous Stage/age history. |
| Nadine Croft | 30 | Temper-stage free Undertow light seed; adult early/mid-career practitioner. |
| Eli Hobb | 34 | Temper-stage free Undertow light seed; adult practitioner with more years in the field than Nadine by working choice. |
| Joyce Rudd | 21 | First-stage free Undertow light seed; young adult, not a child prodigy. |
| Beatrice Snow | 57 | Principal direct inheritor of Conrad Slate (94); established senior disciple generation. |
| Alaric Boone | 45 | Major direct student of Elise Arden (76); established mid-career disciple generation. |
| Dominic Pryce | 52 | Advanced combat-medicine practitioner receiving personal investment from Damian Frost (85); mature specialist. |
| Damon Flint | 49 | Likely major recipient of Seth Carrick (83); established adult inheritor, with exact Reckoning relationship still separate. |
| Hadrian Bellgrave | 65 | Archbishop and major Greywood institutional anchor; senior office-holder comparable in generation to other kingdom anchors. |
| Wilfred Penrose | 71 | Senior Greywood Fifth-stage martial anchor; elder but active. |
| Alban Fairwick | 58 | Senior Greywood Fifth-stage martial anchor; younger than Penrose by working choice. |
| Marius Ashcombe | 64 | Senior Greywood Fifth-stage martial anchor; mature senior generation. |
| Thaddeus Ormond | 61 | Senior Greywood Fifth-stage martial anchor; mature senior generation. |
| Rolfe Durn | 74 | Senior Greywood Fifth-stage martial anchor; oldest of the five working anchors. |
| Bishop Dario Pellin | 59 | Senior Witness churchman governing Sunreach local episcopal structure; mature senior cleric below archiepiscopal generation. |
| Aurelia Morn | 68 | Historical Greywood painter intended to be a genuinely old cultural reference; lifespan fixed as a working registry anchor. |
| Corvin Latch | 75 | Historical Dunmoor sculptor/maker whose reputation and object provenance predate the opening generation; lifespan fixed as a working registry anchor. |

## Completeness

- Named persons: **464**
- Missing ages after repair: **0**
- Missing explicit birth_day after repair: **0**
- Civil-calendar names/months remain open; chronology does not.


## Runtime validation

Fresh seed v1.3 + opening activation validation:

- named registry persons imported: 464;
- character actors after ordinary activation: 514;
- life profiles: 514;
- life profiles with missing `birth_day`: 0;
- living life profiles with missing `birth_day`: 0;
- health profiles: 512;
- health profiles whose actor lacks `birth_day`: 0;
- activation version: 14;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

A disposable manufactured ordinary 105-year-old elder was then advanced only through the production scheduler. Age-derived mortality pressure woke on the scheduled health review and the actor died naturally on day 1200. No direct death call was used. This confirms the mortality owner is functional once chronology is present.

## Acceptance rule

Current seed/bootstrap imports now reject a named person if `age` or explicit opening-relative `birth_day` is absent. For historical/deceased named people, `death_day` and age-at-death consistency are also required.

TENYEAR-01 must restart from day 0 because the opening chronology authority has changed.
