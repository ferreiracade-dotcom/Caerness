"""Task 16: the Saint Jude bible (worlds/saintjude/bible.md) adapted from the Bellacorte codex."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PKG = ROOT / "worlds" / "saintjude"
BIBLE = PKG / "bible.md"
# Words that must never reach a Saint Jude player. Task 21 widens this via tools/leak_scan.FORBIDDEN.
LEAK_WORDS = ("Caerness", "cultivat", "Stage", "Vein-Root", "SV", "Hollow", "Veinborn", "martial", "Salt Road",
              "Aldergate", "House")
PLACE_KINDS = ("bar", "club", "church", "precinct", "office", "street")


def run():
    assert BIBLE.exists(), "worlds/saintjude/bible.md missing"
    text = BIBLE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        os.environ["CAERNESS_DB_PATH"] = str(tmp / "canon.db")
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from engine import canon
        from engine.db import connect, init_db
        from connector.lore import lore

        init_db()
        res = canon.index_canon(BIBLE, force=True)
        assert res["chunks"] >= 60, res
        with connect() as conn:
            rows = conn.execute("SELECT heading_path, text FROM canon_chunks ORDER BY chunk_index").fetchall()
            assert len(rows) >= 60
            for r in rows:
                hp = r["heading_path"] or ""
                assert hp and hp != "Document", hp

            # Names: the city is Saint Jude; Bellacorte is only a district.
            assert not re.search(r"city of Bellacorte|Bellacorte, ", text), "Bellacorte used as a city name"
            for old in ("Port St. Jude", "Meadowlands"):
                assert old not in text, old
            for city_use in ("Bellacorte Daily", "Bellacorte Chronicle", "Bellacorte Police", "Bellacorte MCC",
                             "Bellacorte Civic", "Archdiocese of Bellacorte", "Bellacorte State", "BCPD"):
                assert city_use not in text, city_use

            # Hard-coded character secrets and pressures appear only under an "Examples" heading, if at all.
            for needle in ("Sally Glasses", "Vinny Scales", "David Rossi", "Matty", "Barber Shop Hit"):
                for r in rows:
                    if needle in r["text"]:
                        assert "Examples" in (r["heading_path"] or ""), (needle, r["heading_path"])
            assert "Roster" not in text and "Private Vector" not in text

            # Shape: required sections.
            paths = "\n".join(r["heading_path"] for r in rows)
            for need in ("Founding and history", "Adaptation notes", "Taboos", "Street dictionary",
                         "Technology", "Economic reference ledger"):
                assert need.lower() in paths.lower(), need
            assert "never impossible" in text
            assert text.count("Assumption:") >= 8, text.count("Assumption:")
            notes = text[text.index("## Adaptation notes"):]
            for fix in ("8.1", "8.2", "12.2", "13.2", "Pressure 2"):
                assert fix in notes, fix

            # lore() finds the renamed places and the founding story.
            out = lore(conn, "Killbuck Point")
            assert out["passages"], out
            assert any("Killbuck Point" in p["text"] for p in out["passages"])
            out = lore(conn, "founding church cathedral St. Jude's")
            assert any("cathedral" in p["text"] for p in out["passages"])
            out = lore(conn, "the Pines")
            assert any("Pines" in p["text"] for p in out["passages"])
    print("saintjude_package_test (bible) passed")


def run_sections():
    """Task 17: rulebook and creation sections, and manners."""
    import json
    for name in ("rulebook_section.md", "creation_section.md", "manners.json"):
        assert (PKG / name).is_file(), name
    try:
        from tools.leak_scan import FORBIDDEN
        words = tuple(dict.fromkeys(LEAK_WORDS + tuple(FORBIDDEN)))
    except ImportError:  # Task 21 not built yet
        words = LEAK_WORDS
    rule = (PKG / "rulebook_section.md").read_text(encoding="utf-8")
    create = (PKG / "creation_section.md").read_text(encoding="utf-8")
    manners = json.loads((PKG / "manners.json").read_text(encoding="utf-8"))
    for label, text in (("rulebook", rule), ("creation", create), ("manners", json.dumps(manners))):
        for w in words:
            assert w not in text, (label, w)
    assert "veto" in rule and "menu of" not in rule and "menu of" not in create
    for need in ("tendenc", "never choose", "Plain English", "continuity check", "not a rank number"):
        assert need.lower() in rule.lower(), need
    assert "new person" in create and "lore" in create
    for kind in PLACE_KINDS + ("default",):
        assert str(manners.get(kind, "")).strip(), kind

    # The section fills every marker of the shared core and keeps the connector's whitespace rule.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        worlds = tmp / "worlds"
        (worlds / "sjtmp").mkdir(parents=True)
        (worlds / "sjtmp" / "seed.json").write_text("{}", encoding="utf-8")
        (worlds / "sjtmp" / "world.json").write_text(json.dumps({
            "id": "sjtmp", "display_name": "Saint Jude", "calendar": {"kind": "gregorian", "start": "1975-01-01"},
            "bible_path": str(BIBLE), "seed_path": "seed.json", "seed_namespace": "x",
            "rulebook_section": str(PKG / "rulebook_section.md"), "creation_section": str(PKG / "creation_section.md"),
            "systems": {}, "data": {}}), encoding="utf-8")
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        os.environ["CAERNESS_WORLD_PACKAGE"] = "sjtmp"
        try:
            from connector.session import RULEBOOK_CORE_PATH, load_creation, load_rulebook
            rb = load_rulebook()
            assert "{{" not in rb and rb.count("\n" * 3) == 0
            assert "game master for Saint Jude" in rb and "Close third person" in rb
            for w in words:
                assert w not in rb, w
            assert "Caerness" not in load_creation()
            core = RULEBOOK_CORE_PATH.read_text(encoding="utf-8")
            for key in set(re.findall(r"[{][{]world:(\w+)[}][}]", core)):
                assert "{{" + key + "}}" in rule, key
        finally:
            os.environ.pop("CAERNESS_WORLDS_DIR", None)
            os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    print("saintjude_package_test (sections) passed")


if __name__ == "__main__":
    run()
    run_sections()
