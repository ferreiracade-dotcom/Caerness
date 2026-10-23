"""Task 16: the Saint Jude bible (worlds/saintjude/bible.md) adapted from the Bellacorte codex."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BIBLE = ROOT / "worlds" / "saintjude" / "bible.md"


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


if __name__ == "__main__":
    run()
