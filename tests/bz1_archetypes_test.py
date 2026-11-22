"""BZ1.1: Caerness's business archetypes are package data, not an engine constant.

Run: PYTHONPATH=. python tests/bz1_archetypes_test.py"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world


def test_caerness_archetypes_file_matches_old_constant():
    from engine import business
    frozen = json.loads((ROOT / "tests" / "fixtures" / "bz1_caerness_archetypes_frozen.json").read_text(encoding="utf-8"))
    got = json.loads(business.CAERNESS_ARCHETYPES_PATH.read_text(encoding="utf-8"))
    assert got == frozen and len(got) == 39
    assert business.archetypes(None) == frozen


def test_no_archetype_constant_in_engine():
    from engine import business
    assert not hasattr(business, "_ARCHETYPES")


def test_saintjude_author_bar_uses_package_archetype():
    from connector import store
    from engine import business
    from engine.authoring import author
    from engine.player import set_player
    w = _open_world()
    c = w.conn
    store.ensure_connector_schema(c)
    set_player(c, w.capo)
    from engine import ledger
    ledger.receive(c, ("person", w.capo), 50000.0, purpose="test funding")
    c.commit()
    assert business.package_has_own_archetypes(c)
    assert "bar" in business.archetypes(c)
    r = author(c, w.capo, "business", {"name": "Test Bar", "trade": "bar", "amount": "modest"}, "bz1-bar")
    eid = int(c.execute("SELECT id FROM civilian_enterprises WHERE name='Test Bar'").fetchone()[0])
    key = c.execute("""SELECT a.archetype_key FROM enterprise_business_profiles p
                       JOIN business_archetypes a ON a.id=p.archetype_id WHERE p.enterprise_id=?""", (eid,)).fetchone()[0]
    assert key == "bar", (key, r)


tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
tests.sort(key=lambda f: f.__code__.co_firstlineno)


def _run_all():
    ok = 0
    for t in tests:
        try:
            t()
            ok += 1
        except Exception:
            print("FAIL", t.__name__)
            traceback.print_exc()
    print(f"{ok}/{len(tests)} passed")
    return ok == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
