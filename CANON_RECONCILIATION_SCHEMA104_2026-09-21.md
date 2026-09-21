# Caerness schema 104 — canon/calendar reconciliation

Date: 21 September 2026

## Problem fixed

The accepted schema-104 release tree still embedded the immediately previous World Bible snapshot, while the latest MASTER FINAL had subsequently closed the calendar question. The newer master establishes one shared 365-day civil calendar, numbered Since the Vanishing (SV), with the simulation opening on 1 First Month, 624 SV.

The newer master itself also contained one stale leftover sentence under the open-questions heading saying that choosing shared or competing civil calendars remained a useful decision. That sentence was moved into the resolved-calendar paragraph and rewritten so it now describes only still-latent local feast and seasonal detail.

## Reconciliation performed

- Replaced canon/world_bible_current.docx with the latest MASTER FINAL and corrected the stale calendar-open sentence.
- Added engine/civil_calendar.py as the authoritative deterministic day-offset ↔ SV-date conversion layer.
- Preserved day 0 as the arithmetic opening point; no simulation chronology was shifted.
- Versioned the current engine-facing seed from v1.3 to v1.4 rather than mutating the old seed in place.
- Versioned the production bootstrap seed from v2 to v3.
- Removed open:calendar from the current seed's protected-open-question list.
- Added exact birth_date_sv to all named current-seed people and exact death_date_sv to historical dead people.
- Added engine-side validation that those civil dates exactly match birth_day/death_day.
- Added a canon SHA-256 firewall to current-seed import so this mismatch cannot silently recur.
- Updated the packaged day-0 database's current-seed chronology/provenance metadata without changing day, actor count, location count, institution count, source-map count, or event count.
- Updated religious/economic comments and metadata to distinguish the fixed shared civil calendar from still-unassigned local feast/auction dates.

## Current hashes

- World Bible: 45947d046f816a95d118167e03a7d24872867b1521eb1a9414c5fe4349d995e3
- current seed v1.4: 98dd199d657cbd9780988901100c2c973e5230ecacab6ae4359f21e83d461985
- bootstrap seed v3: 0b331c2dd0670b1b22fbf58a9248a872cef5dfca1d1a0979501bde099434c290
- day-0 database after reconciliation: 179246f18e8369866fa5635f201c99119fb12266628949031bb77feee7bfd4c8

## Calendar invariants

- 1 First Month, 624 SV = day 0.
- Year length = 365 days.
- Month lengths = 31/30/30, 31/30/30, 31/30/30, 31/30/31.
- No leap/intercalation rule.
- Corvin Latch birth/death resolve to 3 Fifth Month, 477 SV / 3 Fifth Month, 552 SV.
- Aurelia Morn birth/death resolve to 23 Sixth Month, 491 SV / 23 Sixth Month, 559 SV.

## Simulation consequence

This is not a demographic, economic, war, underworld, scheduler, or mortality mechanics change. Existing long-horizon schema-104 evidence therefore remains mechanically applicable; the ordinary/focused regression suite is re-run on the reconciled tree and becomes the direct code-level acceptance evidence for this change.
