# TENYEAR-02 fresh opening preflight — 21 Sep 2026

The first diagnostic TENYEAR-02 exposed a schema-current but activation-stale day-0 database.
The accepted replacement is rebuilt from current schema 104, current seed v1.4 and opening activation v20.

Opening state:
- population 52,000,000;
- 68 background population sources and 68 identity partitions;
- 2,272 pre-existing background-person profiles;
- 100 professional profiles;
- 96 institutional authority slots;
- current POPLIFE calibration: gross birth rate 27/1,000 and current age-specific mortality;
- SQLite integrity `ok`; zero foreign-key violations.

Fresh ONEYEAR capability evidence:
- day 365 population 52,117,780;
- births 1,404,000;
- deaths 1,286,220;
- zero contradiction errors and zero coverage failures;
- independent day-180 -> day-365 replay: zero substantive differences across 438 tables.

The packaged database remains day 0. TENYEAR-02 must reject a schema-current database whose opening activation is stale or incomplete.
