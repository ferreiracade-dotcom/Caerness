"""Gemini's G1-G5 prose patterns and cutaway stripper, filed 2026-11-28 as a starting point for Task 7.

Kept from its draft tools/gm_check.py: the regexes and _strip_cutaway_blocks only. Its JSONL and --db halves
were dropped (among other things they assumed an actors.is_protagonist column, which does not exist).
Not imported by anything. Task 7 renumbers the checks to match the scoring sheet (Task 1): there G3 is
out-of-character flags, G4 exposed machinery and G5 moralizing; here G3 is machinery, G4 moralising and
G5 meta-prompts. Tune against docs/playtests/2026-11-25-dominic-2.txt.
"""

from __future__ import annotations

import re

# --- Pattern fault rules (G1–G5) ---
# Tune against docs/playtests/2026-11-25-dominic-2.txt in Task 7 Step 4.

G1_MENU_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*]\s*(?:Option|Choice)\s+\d+)\s+\S+", re.IGNORECASE)
G2_ASK_INVENT = re.compile(
    r"\b(?:what(?:'s| is) (?:the|his|her|their) name|"
    r"what do you (?:want to )?(?:name|call) (?:him|her|them|the)|"
    r"who (?:do you want|should) (?:it|that|they) to be|"
    r"tell me (?:what|who) (?:he|she|they|the \w+) (?:looks like|is named))\b",
    re.IGNORECASE,
)
G3_MACHINERY = re.compile(
    r"\b(?:sim_resolution|actor_decisions|actor_pressures|scene_stamps|holds_true|"
    r"nominations?\s+queue|engine\s+(?:says|decided|rolled|veto)|pressure\s+score)\b",
    re.IGNORECASE,
)
G4_MORALISE = re.compile(
    r"\b(?:it(?:'s| is) important to remember|the right thing to do|"
    r"morally (?:wrong|questionable)|you (?:really )?shouldn't|"
    r"violence is never|consider the ethical)\b",
    re.IGNORECASE,
)
G5_META_PROMPT = re.compile(
    r"\b(?:would you like to proceed|let me know how you(?:'d| would) like to|"
    r"how would you like to handle this\??\s*$)\b",
    re.IGNORECASE,
)

CUTAWAY_START = re.compile(r"^\s*(?:\[?\s*cutaway\b|---\s*cutaway\b)", re.IGNORECASE)
CUTAWAY_END = re.compile(r"^\s*(?:---\s*$|\[/\s*cutaway\s*\]|back to\b)", re.IGNORECASE)
RECAP_HEADER = re.compile(r"^\s*(?:#+\s*)?(?:recap|open threads|where things stand)\b", re.IGNORECASE)
THREAD_LINE = re.compile(
    r"\b(?:owe[sd]?|debt|due\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|\w+\s+\d+)|"
    r"promised?|meeting\s+(?:with|on)|plan(?:ning)?\s+to)\b",
    re.IGNORECASE,
)


def _strip_cutaway_blocks(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line_no, text) excluding marked cutaway blocks."""
    kept: list[tuple[int, str]] = []
    in_cutaway = False
    for idx, line in enumerate(lines, start=1):
        if CUTAWAY_START.search(line):
            in_cutaway = True
            continue
        if in_cutaway:
            if CUTAWAY_END.search(line):
                in_cutaway = False
            continue
        kept.append((idx, line))
    return kept
