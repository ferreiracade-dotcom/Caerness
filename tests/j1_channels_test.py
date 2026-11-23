"""Prison J1.4: channels, visits, letters and the grip on the outside, for NPCs and the protagonist alike.

Run: PYTHONPATH=. python tests/j1_channels_test.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.j1_admission_test import _convict, _men, _run, _stay  # noqa: E402
from tests.outfit_choice_fixture import DAY, open_world  # noqa: E402

from engine import prison, prison_channels as pc  # noqa: E402
from engine.player import set_player  # noqa: E402


class _Chan:
    """Swap prison.rules for a copy with some channel figures replaced, and put it back."""

    def __init__(self, **over):
        self.over, self.orig = over, prison.rules

    def __enter__(self):
        base = self.orig

        def patched(conn):
            r = copy.deepcopy(base(conn))
            r["channels"].update(self.over)
            return r
        prison.rules = patched
        pc.rules = patched

    def __exit__(self, *a):
        prison.rules = self.orig
        pc.rules = self.orig


def _fig(v):
    return {"value": v, "mark": "Design proposal", "why": "test"}


def _spouse(c, a, b):
    c.execute("INSERT INTO typed_relationship_facts(actor_a_id,actor_b_id,relation_type,status) VALUES (?,?,'spouse','active')", (a, b))


def _kin(c, a, b, kind):
    c.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?,?,'recognized',0)", (a, b, kind))


def _free(c, n, skip=()):
    """Men who are not inside, for visitors."""
    return [int(r[0]) for r in c.execute("SELECT id FROM actors WHERE status='active' AND actor_type='character' AND id NOT IN (SELECT actor_id FROM inmate_stays WHERE status='inside') ORDER BY id LIMIT ?", (n + len(skip) + 5,))
            if int(r[0]) not in skip][:n]


def _setup(n=2, protagonist=None):
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    men = _men(c, n)
    if protagonist is not None:
        set_player(c, men[protagonist])
    for m in men:
        _convict(c, m, 1000)
    _run(c)
    return c, men


def _rel(c, a, b):
    return c.execute("SELECT * FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (a, b)).fetchone()


def _visits(c, man):
    return c.execute("SELECT COUNT(*) FROM prison_contacts t JOIN prison_channels h ON h.id=t.channel_id WHERE h.kind='visit' AND t.to_actor_id=?", (man,)).fetchone()[0]


def test_family_visits_by_pull():
    c, men = _setup(3)
    close, distant, far = men
    free = _free(c, 3, skip=men)
    _spouse(c, close, free[0])
    _kin(c, distant, free[1], "other")
    _spouse(c, far, free[2])
    # the third man is held in a far place
    far_fac = c.execute("SELECT id FROM facilities WHERE json_extract(metadata_json,'$.off_map')=1 ORDER BY id LIMIT 1").fetchone()[0]
    c.execute("UPDATE inmate_stays SET facility_id=? WHERE actor_id=?", (far_fac, far))
    c.execute("UPDATE inmate_stays SET facility_id=(SELECT id FROM facilities WHERE json_extract(metadata_json,'$.off_map')=0 ORDER BY id LIMIT 1) WHERE actor_id IN (?,?)", (close, distant))
    for week in range(1, 121):
        pc.weekly(c, DAY + 7 * week)
    n_close, n_distant, n_far = _visits(c, close), _visits(c, distant), _visits(c, far)
    assert n_close > n_distant, (n_close, n_distant)  # a spouse comes more than a distant relative
    assert n_close > n_far, (n_close, n_far)  # a far place is visited less


def test_visit_moves_the_relationship_both_ways_for_everyone():
    for protagonist in (False, True):
        c, men = _setup(2, protagonist=0 if protagonist else None)
        inmate, other = men
        visitor = _free(c, 1, skip=men)[0]
        if protagonist:
            set_player(c, visitor)  # the protagonist visiting: the same call
        before_out, before_in = _rel(c, visitor, inmate), _rel(c, inmate, visitor)
        out = pc.visit(c, visitor, inmate, DAY + 10)
        assert out["ok"], out
        after_out, after_in = _rel(c, visitor, inmate), _rel(c, inmate, visitor)
        assert after_out["familiarity"] > (before_out["familiarity"] if before_out else 0.0)
        assert after_in["affection"] > (before_in["affection"] if before_in else 0.0)
        assert c.execute("SELECT COUNT(*) FROM prison_contacts WHERE kind='visit' AND to_actor_id=?", (inmate,)).fetchone()[0] == 1


def test_protagonist_visits_and_is_visited():
    c, men = _setup(2, protagonist=0)
    p, npc = men
    v1, v2 = _free(c, 2, skip=men)
    assert pc.visit(c, v1, p, DAY + 10)["ok"]  # an NPC visits the jailed protagonist
    set_player(c, v2)
    assert pc.visit(c, v2, npc, DAY + 10)["ok"]  # the protagonist visits an NPC
    assert pc.visit(c, men[0], men[1], DAY + 11)["ok"] is False  # a man inside cannot visit another from outside
    assert pc.visit(c, v1, v2, DAY + 11)["ok"] is False  # nobody to visit


def test_watched_channel_can_be_overheard_a_bought_one_is_not():
    c, men = _setup(2)
    a, b = men
    sa, sb = int(_stay(c, a)["id"]), int(_stay(c, b)["id"])
    with _Chan(intercept_rate=_fig(1.0)):
        watched = pc.open_channel(c, sa, "visit", None, DAY + 5)
        bought = pc.open_channel(c, sb, "bought_guard", None, DAY + 5)
        c.execute("UPDATE prison_channels SET watched=1.0 WHERE id=?", (watched,))
        c.execute("UPDATE prison_channels SET watched=0.0 WHERE id=?", (bought,))
        n0 = c.execute("SELECT COUNT(*) FROM crime_reports WHERE crime_kind='racket'").fetchone()[0]
        r1 = pc.contact(c, bought, DAY + 6, orders=True)
        assert r1["ok"] and not r1["intercepted"]
        assert c.execute("SELECT COUNT(*) FROM crime_reports WHERE crime_kind='racket'").fetchone()[0] == n0
        r2 = pc.contact(c, watched, DAY + 6, orders=True)
        assert r2["intercepted"]
        assert c.execute("SELECT COUNT(*) FROM crime_reports WHERE crime_kind='racket'").fetchone()[0] == n0 + 1
        assert c.execute("SELECT intercepted FROM prison_contacts WHERE id=?", (r2["contact_id"],)).fetchone()[0] == 1
        # a plain contact (no orders) is never overheard
        assert not pc.contact(c, watched, DAY + 7, orders=False)["intercepted"]


def test_grip_reads_quality_recency_and_the_watch():
    for protagonist in (False, True):
        c, men = _setup(3, protagonist=0 if protagonist else None)
        a, b, d = men
        assert pc.channel_grip(c, a) == 0.0  # nothing open
        sa, sb = int(_stay(c, a)["id"]), int(_stay(c, b)["id"])
        good = pc.open_channel(c, sa, "bought_guard", None, DAY)
        poor = pc.open_channel(c, sb, "letter", None, DAY)
        c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
        assert pc.channel_grip(c, a) > pc.channel_grip(c, b) > 0.0
        fresh = pc.channel_grip(c, a)
        c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY + 300,))
        assert pc.channel_grip(c, a) < fresh  # an unused channel fades
        c.execute("UPDATE prison_channels SET status='closed' WHERE id=?", (good,))
        assert pc.channel_grip(c, a) == 0.0
        assert poor


def test_letters_reach_only_if_the_channel_is_open():
    c, men = _setup(2)
    a = men[0]
    other = _free(c, 1, skip=men)[0]
    ch = pc.open_channel(c, int(_stay(c, a)["id"]), "letter", other, DAY + 3)
    before = _rel(c, other, a)
    assert pc.contact(c, ch, DAY + 4)["ok"]
    mid = _rel(c, other, a)
    assert mid is not None and (before is None or mid["familiarity"] > before["familiarity"])
    c.execute("UPDATE prison_channels SET status='closed' WHERE id=?", (ch,))
    out = pc.contact(c, ch, DAY + 5)
    assert out["ok"] is False
    assert _rel(c, other, a)["familiarity"] == mid["familiarity"]


def test_channels_close_when_the_stay_ends():
    c, men = _setup(1)
    a = men[0]
    st = _stay(c, a)
    pc.open_channel(c, int(st["id"]), "phone", None, DAY)
    prison.leave(c, int(st["id"]), DAY + 20, "released")
    assert c.execute("SELECT COUNT(*) FROM prison_channels WHERE stay_id=? AND status='open'", (int(st["id"]),)).fetchone()[0] == 0
    assert pc.channel_grip(c, a) == 0.0


def test_a_channel_he_cannot_pay_for_closes():
    c, men = _setup(1)
    a = men[0]
    st = _stay(c, a)
    ch = pc.open_channel(c, int(st["id"]), "bought_guard", None, DAY)
    c.execute("DELETE FROM underworld_leader_wealth WHERE actor_id=?", (a,))
    c.execute("DELETE FROM resources WHERE actor_id=? AND resource_type='cash'", (a,))
    assert pc._upkeep(c, DAY + 7) == 1
    assert c.execute("SELECT status FROM prison_channels WHERE id=?", (ch,)).fetchone()[0] == "closed"


def test_the_module_names_no_player_branch():
    src = (ROOT / "engine" / "prison_channels.py").read_text(encoding="utf-8")
    assert "get_player" not in src and "is_player" not in src


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print("ok", n)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
