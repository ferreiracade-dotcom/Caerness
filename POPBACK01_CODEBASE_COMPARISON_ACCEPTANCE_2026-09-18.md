# CAERNESS — POPBACK-01 CODEBASE COMPARISON & BACKGROUND IDENTITY SUBSTRATE ACCEPTANCE
**Date:** 18 September 2026  
**Engine:** v0.60.0 working line  
**Schema:** 73  
**Status:** ACCEPTED FOUNDATION; direct third-party runtime adoption deferred pending an environment where the packages can actually be executed.

## 1. Question tested

After SCALE-01 and TRADE-01, should Caerness represent its 52,000,000 people by:

1. one SQL row per person;
2. a dense/vectorized full-population backend;
3. Starsim-style stable raw slots plus active UIDs;
4. a dataframe/Polars/Mesa-Frames backend;
5. neworder-style dynamic microsimulation;
6. or a resolution hybrid in which aggregates remain authoritative and only bounded identity reservoirs are individualized?

The comparison deliberately tests the architecture Caerness actually needs rather than asking which external framework is generally fastest.

## 2. External projects reviewed

### Starsim
Current source/changelog confirms the key pattern relevant to Caerness:

- stable raw array slots;
- active UIDs stored separately;
- dead/removed agents cease to participate in active-array operations without forcing raw-slot remapping;
- large-agent performance is an explicit design concern.

Caerness adopts **this pattern**, not Starsim's epidemiological domain model.

Source: https://github.com/starsimhub/starsim

### neworder
Current project description explicitly targets dynamic microsimulation and combines Python model code with optimized compiled routines. It supports NumPy/Pandas data, reproducible random seeding and optional MPI execution.

That makes neworder a serious future backend candidate if Caerness proves it needs millions of individually simulated life-course records at once.

It does **not** by itself solve Caerness's authority/resolution problem: which people require individual identity, how aggregate state and named state coexist, and how identity promotes without duplication remain Caerness-specific.

Source: https://github.com/virgesmith/neworder

### Mesa-Frames / Polars
Mesa-Frames stores agents in Polars DataFrames and is designed around vectorized set operations. Its own project description explicitly says this is a strong fit for large vectorizable populations and a poor fit for models requiring strict per-agent sequencing or fine-grained identity tracking.

This strongly supports using columnar/vectorized operations for bulk population state, but not using Mesa-Frames as Caerness's universal identity/agency layer.

Sources:
- https://github.com/mesa/mesa-frames
- https://pypi.org/project/polars/

## 3. Runtime limitation

The current execution environment has NumPy, pandas and SQLite available. It does not have Polars, neworder, Starsim or mesa-frames installed, and normal package installation cannot reach PyPI from this runtime.

Therefore this report keeps two evidence classes separate:

- **measured runtime evidence:** NumPy, pandas, SQLite, and a Caerness implementation of the Starsim active-UID pattern;
- **source/API evidence only:** neworder, Starsim proper, Polars and mesa-frames.

No unavailable framework is mislabeled as directly benchmarked.

## 4. Common benchmark workload

Synthetic populations of:

- 10,000;
- 100,000;
- 1,000,000 identities.

Twelve monthly steps perform:

- stable identity lookup;
- aging;
- mortality eligibility;
- migration eligibility;
- occupation transition;
- Core-assessment transition;
- checkpoint;
- restart;
- deterministic-state comparison.

The array backends use stateless deterministic draws keyed by `(uid, step, stream)`, so restart does not depend on a hidden RNG cursor.

Full machine-readable results: `POPBACK01_backend_benchmark.jsonl`.

## 5. One-million identity result

| Backend | 12 steps | Approx state | Checkpoint | Restore | Stable identity | Deterministic restart |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| NumPy dense | 0.965 s | 24.0 MB | 0.025 s | 0.017 s | PASS | PASS |
| Starsim active-UID pattern | 1.228 s | 31.9 MB | 0.025 s | 0.027 s | PASS | PASS |
| pandas columnar | 0.876 s | 24.0 MB | 0.010 s | 0.008 s | PASS | PASS |
| SQLite row-per-person control | 7.456 s | 30.1 MB | 0.022 s | 0.050 s | PASS | PASS |

Important: the SQL control uses a different deterministic set predicate, so its resulting counts are **not an outcome-parity comparison**. The meaningful comparison is execution/storage shape.

The NumPy, Starsim-pattern and pandas runs produce the same measured outcome counts because they share the same stateless draws.

## 6. Why not simply individualize all 52 million people?

Observed lean state at 1M projects approximately to:

- NumPy: **1.16 GiB** for 52M;
- Starsim active-UID pattern: **1.55 GiB**;
- pandas: **1.16 GiB**;
- SQLite control: **1.46 GiB**.

Those figures cover only the deliberately tiny benchmark state. They exclude:

- names;
- kinship;
- households;
- profession history;
- property;
- relationships;
- information/belief;
- institutional memberships;
- travel;
- health history;
- cultivation history;
- event provenance;
- indexes and transactional overhead.

Therefore a 52M fully individualized population would spend a very large amount of memory/persistence merely to preserve identities that almost never become causally relevant.

That is contrary to Caerness's resolution architecture.

## 7. Accepted architecture

### 7.1 Population authority

`population_scale_buckets` remains the SCALE-01 52M baseline authority.

Schema 73 adds `background_population_sources`, a **disjoint operational decomposition** of that denominator:

- 59 named-settlement sources;
- 8 rural residual sources;
- 1 unresolved structural-urban source.

Acceptance result:

- **68 sources**;
- source total = **52,000,000 exactly**;
- every regional source subtotal exactly equals its SCALE-01 bucket.

This is crucial: POPBACK does not sample from the old partial Hearth-only `demographic_cohorts` table.

### 7.2 Bounded identity reservoirs

A source may have one bounded `background_population_partition`.

The partition stores:

- stable local UID;
- exact sampled age in days;
- living/dead state;
- demographic sex;
- accumulated causal exposure;
- active raw-slot indexes.

The serialized state is checkpointed as a checksummed NumPy NPZ BLOB inside SQLite.

SQLite therefore remains the durable authority and transaction boundary while NumPy handles compact high-volume state.

### 7.3 No double counting

A 1,000-identity reservoir sampled from Aldergate's 210,000 population does not turn Aldergate into 211,000.

Partition size is resolution state, not population state.

Monthly sampled mortality similarly changes the identity sample's active view but does not independently subtract a second death from the aggregate population denominator.

### 7.4 Promotion continuity

The accepted pipeline is now:

```text
SCALE-01 population source
    ↓
bounded POPBACK ordinary identity
    ↓
causal exposure from merchant / crime / war / religion / etc.
    ↓
latent person
    ↓
existing resolution controller
    ↓
named TRACKED actor
```

The same identity is preserved through every step.

The acceptance test proves one Aldergate identity retained:

- POPBACK source identity;
- local UID;
- sex;
- exact birth day;
- settlement location;
- latent identity link;
- final actor link.

The old latent materializer was also repaired so a known exact `birth_day` is no longer rounded back into a newly invented chronology during crystallization.

## 8. Framework verdicts

### NumPy — **ADOPT NOW for bounded micro-population partitions**

Why:

- already available;
- fastest/simplest measured low-level representation in this environment within the same broad performance class as the dataframe control;
- predictable memory;
- stable slot identity is easy;
- no framework authority conflict;
- easy to checkpoint inside SQLite;
- exact control over deterministic draws and promotion semantics.

### Starsim — **ADOPT PATTERN; do not adopt framework yet**

The stable-raw-slot + active-UID design is directly useful and is now implemented in POPBACK-01.

A direct dependency is not justified until actual Starsim runtime can be benchmarked against the accepted native implementation.

### neworder — **KEEP AS THE STRONGEST DIRECT MICROSIM CHALLENGER**

If later evidence shows that large individually resolved life-course partitions dominate runtime, benchmark real neworder against the native partition backend.

Do not migrate merely because its compiled Monte Carlo is attractive: Caerness still needs its own identity-resolution, persistence and domain-authority rules.

### Polars / Mesa-Frames — **BENCHMARK WHEN AVAILABLE; likely best for bulk columnar transformations, not universal agency**

Their architecture fits vectorizable population operations well. Mesa-Frames' own stated limitation around fine-grained identity/sequencing is particularly relevant to Caerness.

### SQLite one-row-per-person — **REJECT as high-volume execution backend**

Keep SQLite for:

- durable authoritative metadata;
- provenance;
- relationships;
- named/strategic state;
- partition checkpoints;
- audit/event records.

Do not create 52M ordinary-person SQL rows simply because SQLite is already the authoritative database.

## 9. Regression result

PASS after POPBACK-01:

- POPBACK-01 acceptance;
- TRADE-01;
- MERCHANT-01;
- GROWTH-01;
- CRAFT-01;
- INTEGRATION-01 health/agriculture/law;
- WAR-01;
- COVERAGE-01;
- DEC-01;
- EVENTS-01;
- smoke test;
- age/birth-date completeness;
- age/birth-date mortality trigger;
- Python compileall for `engine/`.

Database integrity and foreign-key checks are part of POPBACK-01 acceptance and pass.

## 10. What this means for the earlier emergence problem

The engine no longer needs to choose between:

- an anonymous aggregate merchant who suddenly appears from nowhere when important; or
- simulating all 52M people as expensive full actors.

A bounded settlement/source reservoir can contain ordinary persistent identities. Domain systems can accumulate evidence against those identities. A merchant, gang member, healer, craftsman, preacher, official or fighter can become important enough to promote while remaining the **same person who existed before the camera cared about them**.

The same principle applies downward: when an actor ceases to justify rich resolution, historical identity can persist while expensive state is reduced.

## 11. Next implementation boundary

POPBACK-01 solves **identity continuity and backend shape**. It does not yet make the full 52M population demographically dynamic.

The next population slice should be **POPLIFE-01**:

1. derive live age-band cohorts from the 68 disjoint sources;
2. evolve births, deaths and aging causally without rebalancing to the 52M starting anchor;
3. later add migration/displacement as explicit transfers between sources;
4. make TRADE-01 consume live population rather than only the opening SCALE-01 denominator;
5. have POPBACK identity deaths/promotions reconcile with that aggregate life-course owner rather than acting as a second population counter.

Only after this should the ten-year run be considered population-complete.
