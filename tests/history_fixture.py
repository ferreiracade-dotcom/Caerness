"""Shared helpers for the R1 history tests: a scratch Saint Jude opening, the intake door, runner."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world  # noqa: F401


def world():
    from engine.player import set_player
    w = open_world()
    set_player(w.conn, w.capo)
    w.conn.commit()
    return w


_n = [0]


def door(w, kind, details, call_id=None):
    """author through the one door; returns the result dict."""
    from engine import authoring
    _n[0] += 1
    return authoring.author(w.conn, w.capo, kind, details, call_id or f"h-{_n[0]}")


def fact(w, what, klass="law", real_date="1973-06-01", source="https://example.test/x \"quote\"", **more):
    return door(w, klass, {"what": what, "class": klass, "real_date": real_date, "source": source, **more})


def set_day(w, day):
    w.conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))


def run_all(globs):
    tests = [v for k, v in sorted(globs.items()) if k.startswith("test_")]
    tests.sort(key=lambda f: f.__code__.co_firstlineno)
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
