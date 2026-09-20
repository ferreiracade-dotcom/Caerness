# CAERNESS — RESCLEAN-01 RESOLUTION OWNER CLEANUP ACCEPTANCE
**Date:** 18 September 2026  
**Engine:** v0.60.0 / schema 76  
**Status:** ACCEPTED

The final TENYEAR overdue-work audit found 112 old `entity_resolution` rows with stale review dates. Investigation showed they were not live missed work:
- 98 were legacy compatibility duplicates: institution actors incorrectly seeded once as `entity_kind='actor'` while correct `entity_kind='institution'` rows also existed and had been reviewed normally;
- 14 were fixed aggregate cohort anchors with no autonomous resolution owner.

RESCLEAN-01:
- classifies compatibility resolution rows from the actual actor type;
- never creates unsupported resolution kinds from simulation profiles;
- keeps old duplicate rows as inert compatibility history with no review clock rather than deleting them;
- removes review clocks from fixed structural cohort anchors;
- avoids `INSERT OR IGNORE` on the AUTOINCREMENT resolution table, because ignored inserts can still advance SQLite sequences and break replay-equivalent surrogate IDs.

After the migration, processable overdue resolution rows are zero. The dedicated regression passes with integrity `ok` and zero FK violations.

Most importantly, Year 10 replay from the exact Year-9 checkpoint now reproduces all 379 persisted tables and all SQLite AUTOINCREMENT sequences exactly (excluding only wall-clock timestamp fields from table hashing).
