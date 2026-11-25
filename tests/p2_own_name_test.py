"""P2.18: a person's own full name resolves to that person, though a household or business carries the same name."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def main() -> None:
    from engine.free_operation import resolve_ref
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn = connect(build_saintjude(Path(tmp)))
        try:
            aid, name = conn.execute("""SELECT a.id,a.name FROM actors a WHERE a.status='active' AND a.actor_type<>'institution'
                                        AND (SELECT COUNT(*) FROM actors b WHERE b.name=a.name)=1 ORDER BY a.id LIMIT 1""").fetchone()
            conn.execute("UPDATE households SET name=? WHERE id=(SELECT MIN(id) FROM households)", (name,))
            got = resolve_ref(conn, name)
            assert got == ("actor", aid, name), got
        finally:
            conn.close()
    print("PASS p2_own_name_test")


if __name__ == "__main__":
    main()
