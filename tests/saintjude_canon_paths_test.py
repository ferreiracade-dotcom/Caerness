"""Saint Jude bible: distinct chunk paths across Parts, whole-paragraph lore, hash-driven re-index."""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        os.environ["CAERNESS_DB_PATH"] = str(tmp / "canon.db")
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(tmp / "campaigns")
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from engine import canon
        from engine.db import connect, init_db

        bible = ROOT / "worlds" / "saintjude" / "bible.md"
        init_db()
        shutil.copy2(tmp / "canon.db", tmp / "base.db")  # a packaged opening without a bible index
        canon.index_canon(bible)
        with connect() as conn:
            rows = conn.execute("SELECT chunk_index, heading_path, text FROM canon_chunks ORDER BY chunk_index").fetchall()

        def part_of(path):
            m = re.search(r"> (Part [IVX]+|Index and Status)\b", path)
            return m.group(1) if m else None

        by_path = {}
        for r in rows:
            by_path.setdefault(r["heading_path"], []).append(r)
        for path, group in by_path.items():
            if path.count(">") >= 1:
                assert part_of(path), ("section path carries no Part", path)
            # a repeated path may only be consecutive pieces of one long section
            idx = [g["chunk_index"] for g in group]
            assert idx == list(range(idx[0], idx[0] + len(idx))), ("non-consecutive repeat", path, idx)
        parts_of_text = {}
        for r in rows:
            parts_of_text.setdefault(r["heading_path"], set()).add(part_of(r["heading_path"]))
        assert all(len(v) == 1 for v in parts_of_text.values())

        # lore returns the whole Part III 7.2 numbers paragraph, not a 1,800-character stub
        from connector.lore import lore, PASSAGE_CHARS

        with connect() as conn:
            res = lore(conn, "numbers policy daily number runner 600 to 1 Bayview Downs")
        hit = [p for p in res["passages"] if "Part III" in p["section"] and "7.2" in p["section"]]
        assert hit, [p["section"] for p in res["passages"]]
        assert "almost impossible to stamp out" in hit[0]["text"], hit[0]["text"][-200:]
        assert "runner" in hit[0]["text"]
        assert all(len(p["text"]) <= PASSAGE_CHARS + 80 for p in res["passages"])

        # a long passage points at the rest, and the continuation query returns it
        with connect() as conn:
            big = conn.execute("SELECT id, text FROM canon_chunks ORDER BY LENGTH(text) DESC LIMIT 1").fetchone()
            first = lore(conn, f"chunk {big['id']} part 1")["passages"][0]
            if len(big["text"]) > PASSAGE_CHARS:
                assert "continues: ask lore for" in first["text"], first["text"][-120:]
                second = lore(conn, f"chunk {big['id']} part 2")["passages"][0]
                assert second["text"] and second["part"].startswith("2 of")

        # re-index on bible change; Caerness untouched when its bible is unchanged
        from connector import campaign

        campaign._packaged_db = lambda pkg_id: tmp / "base.db"

        path = campaign.open_campaign("sj", package="saintjude")
        with connect() as conn:
            n1 = conn.execute("SELECT COUNT(*) FROM canon_chunks").fetchone()[0]
            conn.execute("UPDATE canon_sources SET content_hash='stale'")  # as if built from an older bible
            conn.execute("DELETE FROM canon_chunks WHERE id IN (SELECT id FROM canon_chunks LIMIT 5)")
            conn.commit()
        campaign.open_campaign("sj")
        with connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM canon_chunks").fetchone()[0] == n1
            assert conn.execute("SELECT content_hash FROM canon_sources").fetchone()[0] != "stale"
            marker = conn.execute("SELECT MIN(id) FROM canon_chunks").fetchone()[0]
        campaign.open_campaign("sj")  # unchanged hash: no rebuild (chunk ids stay)
        with connect() as conn:
            assert conn.execute("SELECT MIN(id) FROM canon_chunks").fetchone()[0] == marker

        canon.index_canon(canon.DEFAULT_CANON)
        assert campaign._bible_needs_index(canon.DEFAULT_CANON, 601) is False
    print("saintjude_canon_paths_test passed")


if __name__ == "__main__":
    run()
