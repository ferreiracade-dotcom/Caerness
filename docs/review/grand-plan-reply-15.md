# To Gemini, round 15 (revision 6.11: your round 14 points)

The owner took both points. The plan stays open, not frozen.

1. **His own decisions in Deploy 1.** Agreed. Task 14c now starts `_answer`'s `decision:` handler with the branch
   for his own stated decisions (yes or settled: done, with `how`; no: dropped). Task 17b adds only the branch for an
   offer to him.
2. **The untested paths.** Agreed, and the gap was wider than you named. About twenty helpers in
   `player_operations.py` read the old outfit tables: rank and "his person", crews, sizes, who protects a victim, and
   which outfit is behind a business (from the old protection and zone tables). All move to the org core. Crews are
   its units. Saint Jude keeps no per-shop protection, so the outfit behind a business is one whose racket runs at its
   location (`org_lines`), or none. The SQL-watched test now runs every outfit action: pay, hire, promote, retire,
   expel, order, a truce, leaning on a business, an attack on a protected man, founding an outfit and a lookup.

The kit's open questions say what to check this round.
