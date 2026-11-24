"""L1 task 6: people at the opening are tied to street, parish and workplace; no self-links, order held."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def test_people_are_tied_to_street_parish_and_workplace():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = connect(build_saintjude(Path(t)))
        kinds = {r[0]: r[1] for r in c.execute("SELECT context_kind,COUNT(*) FROM social_contact_links GROUP BY 1")}
        for k in ("household", "work", "institution", "locality"):
            assert kinds.get(k, 0) > 0, kinds
        assert c.execute("SELECT COUNT(*) FROM social_contact_links WHERE actor_a_id>=actor_b_id").fetchone()[0] == 0
        miss = c.execute("""SELECT COUNT(*) FROM enterprise_staff s WHERE s.status='active' AND
              (SELECT COUNT(*) FROM enterprise_staff x WHERE x.enterprise_id=s.enterprise_id AND x.status='active')>1 AND NOT EXISTS
              (SELECT 1 FROM social_contact_links l WHERE l.context_kind='work' AND (l.actor_a_id=s.actor_id OR l.actor_b_id=s.actor_id))""").fetchone()[0]
        assert miss == 0, miss
        c.close()


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
