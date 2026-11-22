"""No Saint Jude word in the engine's Saint Jude-era modules (task D2; spec 5.0: packages are data, the engine names no world).

Run: PYTHONPATH=. python tests/no_world_words_test.py
Scans the organisation core, the underworld layer, the authorities builder and the connector views for rank titles, the
mob's own words and the families' and gangs' names. Comments and docstrings are ignored. Caerness modules are not scanned
(Caerness is shelved and its world-only code stays in engine/ until it resumes); in connector/views.py the lines that read
Caerness's own underworld_* tables are Caerness code and are skipped.
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDS = re.compile(
    r"\b(capos?|soldiers?|boss(?:es)?|underbosses|underboss|consigliere|associates?|pad|made_men|mobs?|mobster|mafia|"
    r"sabatini|pellegrino|ferrante|vannucci|brigades|combine|horsemen|russians|bolita|charlestown|families|family)\b", re.I)
CAERNESS_TABLES = re.compile(r"underworld_(personnel|crews|organizations|leader_wealth)")


def scanned_files() -> list[Path]:
    files = [ROOT / "engine" / "orgs.py", ROOT / "engine" / "law_opening.py", ROOT / "engine" / "crime_response.py", ROOT / "connector" / "views.py",
             ROOT / "engine" / "bearing.py", ROOT / "engine" / "texture.py", ROOT / "engine" / "claims.py", ROOT / "engine" / "news_choices.py",
             ROOT / "engine" / "business_data.py"]
    files += sorted((ROOT / "engine").glob("org_*.py")) + sorted((ROOT / "engine").glob("outfit_*.py"))
    out: list[Path] = []
    for f in files:
        if f.exists() and f not in out:
            out.append(f)
    return out


def code_lines(path: Path) -> list[tuple[int, str]]:
    """(line number, text) with comments and docstrings blanked."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc: list[tuple[int, int]] = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
                doc.append((first.lineno, first.end_lineno))
    comments = {t.start[0]: t.start[1] for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT}
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        if any(a <= i <= b for a, b in doc):
            continue
        if i in comments:
            line = line[:comments[i]]
        out.append((i, line))
    return out


def offenders() -> list[str]:
    found = []
    for path in scanned_files():
        for i, line in code_lines(path):
            if path.name == "views.py" and CAERNESS_TABLES.search(line):
                continue
            for m in WORDS.finditer(line):
                found.append(f"{path.relative_to(ROOT)}:{i}: {m.group(0)!r} in {line.strip()[:90]}")
    return found


def test_no_world_words_in_saintjude_era_modules():
    bad = offenders()
    assert not bad, "world words in engine code:\n" + "\n".join(bad)


def test_scan_sees_the_modules_and_catches_a_word():
    names = {p.name for p in scanned_files()}
    assert {"orgs.py", "org_money.py", "outfit_opening.py", "outfit_choices.py", "law_opening.py", "views.py"} <= names, names
    tmp = ROOT / "tests" / "_word_probe.py"
    try:
        tmp.write_text('"""a capo in a docstring"""\nx = "the capo"  # a boss in a comment\n', encoding="utf-8")
        hits = [(i, m.group(0)) for i, line in code_lines(tmp) for m in WORDS.finditer(line)]
    finally:
        tmp.unlink()
    assert hits == [(2, "capo")], hits


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok {name}")
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
                sys.exit(1)
