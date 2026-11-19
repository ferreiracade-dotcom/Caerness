"""Organisation core (task C2): roles come from package data, the seat is generic, lines pass to stand-ins.

Run: CAERNESS_DB_PATH=<scratch>.db PYTHONPATH=. python tests/org_core_test.py
The first tests run on tests/org_core_fixture.py (a minimal non-Saint-Jude package); the last one runs the Saint Jude
opening and checks one period's money against tests/fixtures/org_refactor_baseline.json.
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import org_core_fixture as fx

CORE_FILES = ("orgs.py", "org_money.py", "org_motives.py", "org_choices.py", "org_lifecycle.py", "crime_response.py")
SPHERE_WORDS = re.compile(r"\b(boss|underboss|consigliere|capo|soldier|associate|made|president|banker|pad)\b", re.IGNORECASE)


def _raises(fn, exc, text):
    try:
        fn()
    except exc as e:
        assert text in str(e), str(e)
        return
    raise AssertionError(f"{exc.__name__} not raised")


def test_roles_come_from_data():
    from engine import orgs
    f = fx.build()
    conn = f.conn
    assert orgs.head_of(conn, f.firm) == f.chair
    assert orgs.unit_leader_of(conn, f.clerks[0], f.firm) == f.managers[0]
    assert orgs.unit_leader_of(conn, f.clerks[3], f.firm) == f.managers[1]
    assert orgs.unit_leader_of(conn, f.managers[0], f.firm) == f.managers[0]  # a leader leads himself
    assert orgs.unit_leader_of(conn, f.chair, f.firm) is None
    assert orgs.stand_in_for(conn, f.clerks[0], f.firm) == f.managers[0]
    assert orgs.kind_rules(conn, f.firm)["head"] == "chair" and orgs.kind_rules(conn, 10 ** 9) == {}
    assert orgs.seat_of(conn, f.clerks[0], f.firm)["role_key"] == "clerk" and orgs.seat_of(conn, f.chair, f.solo) is None
    assert [r["actor_id"] for r in orgs.members(conn, f.firm, "manager")] == f.managers
    assert orgs.superior_of(conn, f.clerks[0], f.firm) == f.managers[0]
    role = conn.execute("SELECT role_text FROM institution_memberships WHERE member_actor_id=?", (f.clerks[0],)).fetchone()[0]
    assert role == "Clerk in the Alpha Firm", role  # the label comes from the package, not capitalize()


def test_line_passes_to_stand_in():
    from engine import org_money
    f = fx.build()
    conn = f.conn
    line = f.lines[0]
    assert org_money.line_holder(conn, line) == f.clerks[0]
    fx.kill(conn, f.clerks[0])
    assert org_money.line_holder(conn, line) == f.managers[0]
    fx.kill(conn, f.managers[0])
    assert org_money.line_holder(conn, line) == f.chair
    out = org_money.post_period(conn, 28, 28)
    assert abs(out["take"] - 3 * 500.0 * 4) < 0.01 and out["unearned_lines"] == 0  # two firm lines and the solo line
    got = conn.execute("SELECT SUM(amount) FROM org_money WHERE kind='take' AND to_actor_id=?", (f.chair,)).fetchone()[0]
    assert abs(got - 2000.0) < 0.01, got  # the dead clerk's line is the chair's now


def test_kind_without_unit_leader():
    from engine import org_money
    f = fx.build()
    conn = f.conn
    assert org_money.line_holder(conn, f.solo_line) == f.hand
    fx.kill(conn, f.hand)
    assert org_money.line_holder(conn, f.solo_line) == f.owner  # straight to the head
    fx.kill(conn, f.owner)
    _raises(lambda: org_money.line_holder(conn, f.solo_line), RuntimeError, "no live earner")
    out = org_money.post_period(conn, 28, 28)  # skips the unearned line and carries on
    assert out["unearned_lines"] == 1.0 and abs(out["take"] - 4000.0) < 0.01, out
    assert conn.execute("SELECT COUNT(*) FROM org_money WHERE line_id=?", (f.solo_line,)).fetchone()[0] == 0


def test_two_seats_two_stand_ins():
    from engine import org_money, orgs
    f = fx.build()
    conn = f.conn
    clerk = f.clerks[0]
    assert conn.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?", (clerk,)).fetchone()[0] == "STRATEGIC"
    beta = fx.org(conn, "Beta Firm", "firm")
    chair2, manager2 = fx.person(conn, "Chair Two"), fx.person(conn, "Manager Two")
    unit2 = int(conn.execute("INSERT INTO org_units(org_actor_id,leader_actor_id,label) VALUES (?,?,'beta unit')", (beta, manager2)).lastrowid)
    orgs.seat(conn, chair2, beta, "chair", unit_id=None, superior_actor_id=None, level=4, day=0)
    orgs.seat(conn, manager2, beta, "manager", unit_id=unit2, superior_actor_id=chair2, level=4, day=0)
    orgs.seat(conn, clerk, beta, "clerk", unit_id=unit2, superior_actor_id=manager2, level=4, day=0)
    holding2 = int(conn.execute("INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) "
                                "VALUES (?, 'trade', 100, 26000, 'opening', 0)", (beta,)).lastrowid)
    beta_line = fx.line(conn, holding2, unit2, clerk, 500.0)
    # level 4 in one firm, 3 in the other: one person, one profile, the higher level
    row = conn.execute("SELECT tier,cadence_days FROM simulation_profiles WHERE actor_id=?", (clerk,)).fetchone()
    assert (row["tier"], row["cadence_days"]) == ("ACTIVE", 1), dict(row)
    assert sorted(r["level"] for r in orgs.seats_of(conn, clerk)) == [3, 4]
    fx.kill(conn, clerk)
    assert org_money.line_holder(conn, f.lines[0]) == f.managers[0]
    assert org_money.line_holder(conn, beta_line) == manager2
    assert orgs.stand_in_for(conn, clerk, f.firm) == f.managers[0] and orgs.stand_in_for(conn, clerk, beta) == manager2
    fx.kill(conn, manager2)
    assert org_money.line_holder(conn, beta_line) == chair2


def test_non_outfit_seat_gets_the_quiet_routine():
    from engine import orgs
    f = fx.build()
    conn = f.conn
    clerk = f.clerks[1]
    p = conn.execute("SELECT quiet_routine,tier FROM simulation_profiles WHERE actor_id=?", (clerk,)).fetchone()
    assert (p["quiet_routine"], p["tier"]) == (1, "STRATEGIC")
    due = 40
    orgs.add_agenda(conn, clerk, "chase_invoice", due)
    p = conn.execute("SELECT forced_tier,forced_until_day FROM simulation_profiles WHERE actor_id=?", (clerk,)).fetchone()
    assert (p["forced_tier"], p["forced_until_day"]) == ("ACTIVE", due + 7), dict(p)
    assert not orgs.has_reason_to_choose(conn, clerk, due - 1)
    assert orgs.has_reason_to_choose(conn, clerk, due)


def _code_words(path: Path) -> list[str]:
    """Identifiers and string literals of a module, without comments and docstrings."""
    src = path.read_text(encoding="utf-8")
    docs: set[tuple[int, int]] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docs.add((first.value.lineno, first.value.col_offset))
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.NAME or (tok.type == tokenize.STRING and tok.start not in docs):
            out.append(tok.string)
    return out


def test_core_has_no_sphere_words():
    checked = 0
    for name in CORE_FILES:
        path = ROOT / "engine" / name
        if not path.exists():
            continue  # later tasks add the rest of the core
        checked += 1
        bad = [w for w in _code_words(path) if SPHERE_WORDS.search(w)]
        assert not bad, (name, bad)
    assert checked >= 2


def test_saintjude_period_matches_baseline():
    """One 28-day period of the Saint Jude opening: take, kickup and the envelope flow match the pre-refactor sums."""
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    from tests.make_org_refactor_baseline import main
    want = json.loads((ROOT / "tests" / "fixtures" / "org_refactor_baseline.json").read_text(encoding="utf-8"))
    got = main()
    for k in ("take", "kickup", "pad"):
        assert abs(got[k] - want[k]) <= 1.0, (k, got[k], want[k])


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and k != "test_saintjude_period_matches_baseline"]
TESTS.append(test_saintjude_period_matches_baseline)  # last: it re-points the environment at Saint Jude

if __name__ == "__main__":
    bad = []
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            bad.append(t.__name__)
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, repr(e)[:300])
        else:
            print("ok", t.__name__)
    print(f"{len(TESTS) - len(bad)} passed" + (f", {len(bad)} FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)
