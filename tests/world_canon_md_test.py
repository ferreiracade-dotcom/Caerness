"""Task 10: a Markdown package bible is indexed with real headings; the Caerness docx is unchanged."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        os.environ["CAERNESS_DB_PATH"] = str(tmp / "canon.db")
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from engine import canon
        from engine.db import connect, init_db

        md = tmp / "bible.md"
        md.write_text("# A\n\nIntro to A.\n\n## B\nThe second heading.\n\n### C\nThird level.\n", encoding="utf-8")
        blocks = canon.extract_markdown_blocks(md)
        assert blocks[0] == ("Heading 1", "A") and ("Heading 2", "B") in blocks and ("Normal", "Intro to A.") in blocks
        init_db()
        res = canon.index_canon(md)
        assert res["chunks"] == 3, res
        with connect() as conn:
            paths = [r[0] for r in conn.execute("SELECT heading_path FROM canon_chunks ORDER BY chunk_index")]
        assert paths == ["A", "A > B", "A > B > C"], paths

        res = canon.index_canon(canon.DEFAULT_CANON)
        assert res["chunks"] == 601, res  # the count before Markdown support
    print("world_canon_md_test passed")


if __name__ == "__main__":
    run()
