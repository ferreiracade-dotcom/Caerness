"""Leak scan: find Caerness vocabulary and old-Saint-Jude-bible vocabulary in a Saint Jude campaign DB.

Usage:  python tools/leak_scan.py DB [--files] [--top N]

Two kinds of leak:
  caerness   a Caerness name (location, religion, good, actor) or a fixed Caerness word
  old_bible  a string that only the pre-reload Saint Jude bible/codex had

Matching rules (all case-sensitive unless noted, and all word-bounded unless noted):
  * Caerness names from data/caerness.db: whole-word, case-sensitive, length >= 4.
  * cultivat   substring, case-insensitive (cultivate, cultivation, Cultivator).
  * Stage      capitalised word only (cultivation sense; "stage" in lower case is ordinary English).
  * SV         word only (date marker; never inside a longer word).
  * Hollow     capitalised word only ("Holloway", "Hollowell" do not match; \\b on the right).
  * martial    lower-case word ("court-martial" / "martial law" are 1975-legitimate: see ALLOW).
  * Vein-Root, Veinborn, Salt Road, Aldergate, Caerness   substring, case-sensitive.
  * OLD_BIBLE strings: whole-word, case-sensitive.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = ROOT / "worlds" / "saintjude"
CAERNESS_DB = ROOT / "data" / "caerness.db"

# (regex, label). The label is what Leak.matched shows for fixed words.
_FIXED: tuple[tuple[str, str], ...] = (
    (r"(?i:cultivat)", "cultivat"),
    (r"\bStage\b", "Stage"),
    (r"Vein-Root", "Vein-Root"),
    (r"\bSV\b", "SV"),
    (r"\bHollow\b", "Hollow"),
    (r"Veinborn", "Veinborn"),
    (r"\bmartial\b", "martial"),
    (r"Salt Road", "Salt Road"),
    (r"Aldergate", "Aldergate"),
    (r"Caerness", "Caerness"),
)

# Known false positives. (regex, reason). A hit is discarded if its span lies inside an ALLOW match.
ALLOW: tuple[tuple[str, str], ...] = (
    (r"Holloway", "Part I 14.1 name pool surname; contains 'Hollow' as a substring only"),
    (r"Sparks Steak House", "real 1975 restaurant name (trips House/Hollow-type word lists)"),
    (r"Customs House", "real 1975 building name (trips House/Hollow-type word lists)"),
    (r"court[- ]martial", "1975 military-law term, not the cultivation/martial-path sense"),
    (r"martial law", "1975 civil-order term"),
    (r"martial arts?", "1975 boxing/karate gym term"),
)

# Tables that are engine vocabulary and never reach Claude. Each needs a reason. Deliberately empty:
# every table found leaking is reported first and only moved here once shown to be unread by the connector.
ALLOW_TABLES: dict[str, str] = {
    "schema_migrations": "migration ledger written by init_db; no connector or engine view returns its text",
    "engine_meta": "engine key/value bookkeeping (versions, cycle markers); only looked up by key, never listed to Claude",
    "coverage_registry": "engine self-audit registry (engine/coverage.py); connector never imports it",
    "process_execution_log": "engine process timing/result log; connector never reads it",
}

# canon_chunks / canon_sources rows that belong to the package's own bible are the authority, so they are skipped.
_OWN_BIBLE_NAME = "bible.md"

# --- OLD_BIBLE -------------------------------------------------------------------------------------------
# Source: docs/superpowers/plans/saintjude-bible-reload/step1_diff.md section 10 (10.1 words, 10.2 people,
# 10.3 institutions) plus the codex framing words. Candidates are filtered against worlds/saintjude/bible.md at
# import: a candidate that occurs in the bible as a whole word is dropped (the bible is the authority).
_OLD_BIBLE_CANDIDATES: tuple[str, ...] = (
    # 10.1 family / org / codex words
    "Castellano", "Castellanos", "Castellano Family", "Moretti schism", "Moretti crews", "Moretti specialty",
    "Moretti armory", "Moretti Family", "Moretti", "Ragmen", "Eastsiders", "Pier Rats",
    "Mercer Street Kings ground", "Eastside Realty and Management", "The Deacon", "The Bishop",
    "Vorovskoy Syndicate", "Cossacks", "Odessa Boys", "Petro-Star Fuel Terminal", "Petro-Star Fuel", "Petro-Star",
    "Brighton Point Furs", "Brighton Point Baths", "Cyrillic supper clubs", "daisy-chain",
    "gem and gold smuggling", "counterfeit cash",
    "FBI Organized Crime Strike Force", "The Feebs", "Choirboys", "Gordon Vance-Miller",
    "District Attorney's Office", "County District Attorney's office", "Assistant District Attorney",
    "County Courthouse", "The Triangle", "Ironhaven State Penitentiary", "1908 Gothic granite",
    "Going Away to College", "Italian Table", "D-Block",
    "Neon Strip", "East Bellacorte", "Central Hill", "Harbor Pointe", "Harbor Pointe Site", "Oakridge Estates",
    "Crown Harbor Offices", "Eastside Auto Crush", "Making Him a Bumper", "San Lorenzo Provisions Plant",
    "Pouring Him into the Skyline", "Going in the Vat", "Turning into Soap", "Taking a Ride to the Pines",
    "Jewish Lightning", "Italian Remodeling", "Greaseballs", "Wonderbread", "Medigan", "Pezzonovante",
    "Gavone", "Cafone", "Standing Tall", "Doing It on One Foot", "walk-talk", "stroking the chin",
    "tugging the earlobe", "three suits tailored",
    "Appendix A", "Appendix B", "Adaptation notes", "codex", "Codex", "Bellacorte Living World Codex",
    "Bellacorte_Living_World_Codex_Flexible_Date_Final", "Layer 1", "Layer 2", "Layer 3", "owner rule",
    "sovereign four-family underworld", "splintered cousins and former traitors", "hornets' nest",
    "New York stays out",
    # 10.2 people (full names and nicknames; surname-only entries are not used, the new bible reuses surnames)
    "Pietro Castellano", "Matteo Castellano", "Jackie Castellano", "Salvatore Moretti", "Gennaro Moretti",
    "Enzo Moretti", "Pasquale Ferrante", "Ignazio Pellegrino", "Salvatore Conti", "Sally Glasses",
    "Aurelio Sciarra", "Rocco Lamberti", "Teresa Ianelli", "Concetta Falcone", "Dominic Tarantino",
    "Walter Mulcahy", "Lucia Vannucci", "Donna Lucia", "Carlo Spatafore", "Paul Varga", "Paulie the Hammer",
    "Johnny Drago", "Handsome Johnny", "Michael Santoro", "Mikey Saints", "Declan Gallagher", "Liam Gallagher",
    "Brendan O'Malley", "Arkady Volkov", "Walter Pettiford", "Marcus Vance", "Roy Pike", "Raymond Doyle",
    "Francis Callahan", "Frankie Callahan", "Harrison Sterling III", "Arthur Blum", "Artie the Pen",
    "Thomas Pugliese", "the Bullhorn", "Eugene Cavallo", "Leo Rosen", "Sol Weiss", "Louis Castelluccio",
    "Golden Boy", "Darius Hollis", "John Kavanagh", "Irish Hammer", "Valerie St. Clair", "Salvatore Marchetti",
    "Arthur Pendergast", "Marvin Kesselman", "Dennis McCaffrey", "Edward Haggerty", "Harold Winslow",
    "Judith Katz", "Roland Whitcomb", "Gerald Lockwood", "Hector Rivera", "Patrick Keane", "Matteo Russo",
    "Martin Keogh", "Maureen Tierney", "Anthony Russo", "Gino Fabbri", "Margaret Dunleavy",
    "Marty the Nose Breslin", "David Rossi", "Matty Castellano", "Danny Lombardo", "Vinny Scales", "Larry Nails",
    # 10.3 institutions and businesses
    "Teamsters Local 814", "Hotel and Restaurant Employees Local 211", "Municipal Sanitation Local 509",
    "Dockworkers Local 402", "Saint Jude Ready-Mix", "DeLuca Cadillac-Oldsmobile", "The Master Layoff Bank",
    "Hill Numbers Bank", "Saint Jude Wholesale Fish Market", "Pier 4 Diner and Fish Market", "Metro Enviro-Haul",
    "Enzo's Barber Shop", "The Pompeii Social Club and Cigar Store", "Kerry Harbor Towage", "Horsemen Machine Shop",
    "Sterling Properties", "Blum and Associates", "Kesselman's Discount Electronics and Furs", "Tri-City Promotions",
    "Bayview Towing", "Mercer Avenue Boxing Gym", "Channel 4 Action News", "St. Jude's Cathedral Parish",
    "Saint Jude Civic Arena",
)


def _walk_json(node, path=""):
    """Yield (json_path, string) for every string VALUE (keys are config, not prose)."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_json(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_json(v, f"{path}[{i}]")


def _word_re(s: str) -> str:
    """Whole-word regex for a literal; \\b only where the edge character is a word character."""
    left = r"\b" if re.match(r"\w", s[0]) else ""
    right = r"\b" if re.match(r"\w", s[-1]) else ""
    return left + re.escape(s) + right


def _bible_text() -> str:
    p = PACKAGE_DIR / _OWN_BIBLE_NAME
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _seed_text_without_meta() -> str:
    """The seed's own content (names, roles, public text) is legitimate; its `meta` authoring notes are not."""
    p = PACKAGE_DIR / "seed.json"
    if not p.exists():
        return ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return ""
    d.pop("meta", None)
    return "\n".join(s for _, s in _walk_json(d))


def _pool_names() -> set[str]:
    """Every given name and surname in the package's name pools (names.json male/female/family lists)."""
    p = PACKAGE_DIR / "names.json"
    out: set[str] = set()
    if not p.exists():
        return out

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("male", "female", "family") and isinstance(v, list):
                    out.update(x for x in v if isinstance(x, str))
                else:
                    walk(v)

    walk(json.loads(p.read_text(encoding="utf-8")))
    return out


def _split_old_bible() -> tuple[tuple[str, ...], tuple[str, ...]]:
    # The authorities are the new bible AND the Saint Jude seed (minus meta): a candidate present in either is
    # a 1975 name, not a leak (e.g. Arthur Blum, Mikey Saints, Teamsters Local 814 are seeded cast/institutions).
    # A two-word name made only of pool names (e.g. Hector Rivera) can be drawn by the name generator, so finding
    # it proves nothing; such a man's nickname, where he had one, stays on the list.
    bible = _bible_text() + "\n" + _seed_text_without_meta()
    pool = _pool_names()
    keep: list[str] = []
    dropped: list[str] = []
    for s in _OLD_BIBLE_CANDIDATES:
        parts = s.split()
        if (bible and re.search(_word_re(s), bible)) or (len(parts) == 2 and all(t in pool for t in parts)):
            dropped.append(s)
        else:
            keep.append(s)
    return tuple(keep), tuple(dropped)


OLD_BIBLE, OLD_BIBLE_DROPPED = _split_old_bible()
# DROPPED_NOTE: OLD_BIBLE_DROPPED lists the candidates removed because worlds/saintjude/bible.md contains them
# (computed at import; recorded here after the first run, see the comment block at the end of this file).


# --- FORBIDDEN -------------------------------------------------------------------------------------------
# Caerness name sources: (table, column). Each is a table whose names are Caerness-world proper names.
_NAME_SOURCES: tuple[tuple[str, str], ...] = (
    ("locations", "name"),
    ("religious_traditions", "name"),
    ("market_goods", "name"),
    ("actors", "name"),
)
_MIN_NAME_LEN = 4


def _package_corpus() -> str:
    """Text of the Saint Jude seed + name pools + bible: a Caerness string found here is legitimate."""
    parts = []
    for name in ("seed.json", "names.json", _OWN_BIBLE_NAME):
        p = PACKAGE_DIR / name
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    # the manifest's name_pools are the live name source
    wj = PACKAGE_DIR / "world.json"
    if wj.exists():
        try:
            parts.append(json.dumps(json.loads(wj.read_text(encoding="utf-8")).get("name_pools", {})))
        except Exception:
            pass
    return "\n".join(parts)


def caerness_names(db_path: Path = CAERNESS_DB) -> tuple[str, ...]:
    if not Path(db_path).exists():
        return ()
    corpus = _package_corpus()
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        names: set[str] = set()
        for table, col in _NAME_SOURCES:
            try:
                for (v,) in conn.execute(f'SELECT DISTINCT "{col}" FROM "{table}"'):
                    if isinstance(v, str) and len(v.strip()) >= _MIN_NAME_LEN:
                        names.add(v.strip())
            except sqlite3.Error:
                continue
    finally:
        conn.close()
    return tuple(sorted(n for n in names if not re.search(_word_re(n), corpus)))


def _build_forbidden() -> tuple[str, ...]:
    return tuple(label for _, label in _FIXED) + caerness_names()


FORBIDDEN: tuple[str, ...] = _build_forbidden()


# --- matching --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Leak:
    table: str
    column: str
    rowid: object
    matched: str
    kind: str  # "caerness" | "old_bible"
    excerpt: str


def _compile():
    fixed = [(re.compile(rx), label) for rx, label in _FIXED]
    names = sorted(FORBIDDEN[len(_FIXED):], key=len, reverse=True)
    name_re = re.compile("|".join(_word_re(n) for n in names)) if names else None
    old = sorted(OLD_BIBLE, key=len, reverse=True)
    old_re = re.compile("|".join(_word_re(n) for n in old)) if old else None
    allow = [re.compile(rx) for rx, _ in ALLOW]
    return fixed, name_re, old_re, allow


_FIXED_RE, _NAME_RE, _OLD_RE, _ALLOW_RE = _compile()


def find_hits(text: str) -> list[tuple[str, str, str]]:
    """Return [(matched, kind, excerpt)] for one text value."""
    if not text or len(text) < 2:
        return []
    allowed = [m.span() for rx in _ALLOW_RE for m in rx.finditer(text)]

    def ok(span):
        return not any(a <= span[0] and span[1] <= b for a, b in allowed)

    def excerpt(span):
        a, b = max(0, span[0] - 40), min(len(text), span[1] + 40)
        return text[a:b].replace("\n", " ")

    out: list[tuple[str, str, str]] = []
    for rx, label in _FIXED_RE:
        for m in rx.finditer(text):
            if ok(m.span()):
                out.append((label, "caerness", excerpt(m.span())))
    if _NAME_RE:
        for m in _NAME_RE.finditer(text):
            if ok(m.span()):
                out.append((m.group(0), "caerness", excerpt(m.span())))
    if _OLD_RE:
        for m in _OLD_RE.finditer(text):
            if ok(m.span()):
                out.append((m.group(0), "old_bible", excerpt(m.span())))
    return out


def _text_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")') if "CHAR" in (r[2] or "").upper()
            or "TEXT" in (r[2] or "").upper() or "CLOB" in (r[2] or "").upper() or (r[2] or "") == ""]


def _own_bible_source_ids(conn: sqlite3.Connection) -> set[int]:
    try:
        rows = conn.execute("SELECT id, source_path FROM canon_sources").fetchall()
    except sqlite3.Error:
        return set()
    return {r[0] for r in rows if str(r[1]).replace("\\", "/").endswith("saintjude/" + _OWN_BIBLE_NAME)}


def scan(db_path) -> list[Leak]:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    leaks: list[Leak] = []
    try:
        own = _own_bible_source_ids(conn)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tables:
            if t in ALLOW_TABLES:
                continue
            cols = _text_columns(conn, t)
            if not cols:
                continue
            q = ",".join(f'"{c}"' for c in cols)
            try:
                cur = conn.execute(f'SELECT rowid, {q} FROM "{t}"')
                has_rowid = True
            except sqlite3.OperationalError:
                cur = conn.execute(f'SELECT NULL, {q} FROM "{t}"')
                has_rowid = False
            skip_idx = None
            if t == "canon_chunks" and own and "source_id" in [r[1] for r in conn.execute('PRAGMA table_info("canon_chunks")')]:
                skip_src = {r[0]: r[1] for r in conn.execute("SELECT id, source_id FROM canon_chunks")}
                skip_idx = skip_src
            for row in cur:
                rid = row[0]
                if skip_idx is not None and skip_idx.get(rid) in own:
                    continue
                for c, v in zip(cols, row[1:]):
                    if isinstance(v, str):
                        for matched, kind, ex in find_hits(v):
                            leaks.append(Leak(t, c, rid if has_rowid else None, matched, kind, ex))
    finally:
        conn.close()
    return leaks


def package_files() -> list[Path]:
    return sorted(p for p in PACKAGE_DIR.iterdir()
                  if p.suffix in (".md", ".json") and p.name != _OWN_BIBLE_NAME)


def scan_files(paths=None) -> list[Leak]:
    leaks: list[Leak] = []
    for p in (list(paths) if paths is not None else package_files()):
        p = Path(p)
        if p.name == _OWN_BIBLE_NAME:
            continue
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".json":
            try:
                doc = json.loads(text)
                if p.name == "seed.json" and isinstance(doc, dict):
                    doc.pop("meta", None)  # authoring notes (backdating_notes, removed_from_old_seed...): never imported
                items = list(_walk_json(doc))
            except ValueError:
                items = [("", text)]
            for jp, s in items:
                for matched, kind, ex in find_hits(s):
                    leaks.append(Leak(p.name, jp, None, matched, kind, ex))
        else:
            for n, line in enumerate(text.splitlines(), 1):
                for matched, kind, ex in find_hits(line):
                    leaks.append(Leak(p.name, "line", n, matched, kind, ex))
    return leaks


def summarize(leaks: list[Leak], top: int = 3) -> str:
    groups: dict[tuple, list[Leak]] = {}
    for lk in leaks:
        groups.setdefault((lk.table, lk.column, lk.matched, lk.kind), []).append(lk)
    lines = [f"{len(leaks)} hits in {len(groups)} groups  (FORBIDDEN={len(FORBIDDEN)} OLD_BIBLE={len(OLD_BIBLE)})"]
    per_table: dict[str, int] = {}
    for lk in leaks:
        per_table[lk.table] = per_table.get(lk.table, 0) + 1
    lines.append("by table: " + ", ".join(f"{t}={n}" for t, n in sorted(per_table.items(), key=lambda x: -x[1])))
    shown: dict[tuple, int] = {}
    for key, items in sorted(groups.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        t, c, m, k = key
        lines.append(f"[{k}] {t}.{c} {m!r} x{len(items)}")
        n = shown.get((t, m), 0)
        if n < top:
            shown[(t, m)] = n + 1
            lines.append(f"      rowid={items[0].rowid}: ...{items[0].excerpt}...")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    top = 3
    if "--top" in argv:
        i = argv.index("--top")
        top = int(argv[i + 1])
        args = [a for a in args if a != argv[i + 1]]
    leaks: list[Leak] = []
    if args:
        leaks += scan(Path(args[0]))
    if "--files" in argv:
        leaks += scan_files()
    print(summarize(leaks, top))
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
