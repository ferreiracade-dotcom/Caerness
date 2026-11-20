"""Weekly reviews are spread across the week, and anything imposed on a man pulls his next review to tomorrow."""
from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine import orgs
from engine.harm import record_harm
from engine.simulation import advance_connection, current_day


def _open():
    path = build_saintjude(Path(tempfile.mkdtemp()))
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    return connect(path)


def _weekly(conn):
    return [dict(r) for r in conn.execute(
        "SELECT actor_id,next_review_day,cadence_days FROM simulation_profiles WHERE quiet_routine=1 AND cadence_days=7")]


def test_weekly_reviews_spread_across_the_week():
    conn = _open()
    today = current_day(conn)
    weekly = _weekly(conn)
    assert len(weekly) > 700
    days = Counter(int(r["next_review_day"]) for r in weekly)
    assert set(days) == {today + 1 + k for k in range(7)}, sorted(days)
    assert max(days.values()) <= 0.25 * len(weekly), days
    # the phase is the person's: the same actor lands on the same weekday after a level change
    one = int(weekly[0]["actor_id"])
    first = int(weekly[0]["next_review_day"])
    seat = conn.execute("SELECT org_actor_id,level FROM org_seats WHERE actor_id=? AND status='active' LIMIT 1", (one,)).fetchone()
    orgs.set_level(conn, one, 4, today, int(seat[0]))
    orgs.set_level(conn, one, int(seat[1]), today, int(seat[0]))
    again = conn.execute("SELECT next_review_day FROM simulation_profiles WHERE actor_id=?", (one,)).fetchone()[0]
    assert (again - first) % 7 == 0, (first, again)
    # later reviews stay on his weekday
    advance_connection(conn, 30)
    reviewed = Counter()
    for r in conn.execute("SELECT next_review_day FROM simulation_profiles WHERE quiet_routine=1 AND cadence_days=7 AND forced_tier IS NOT 'ACTIVE'"):
        reviewed[int(r[0])] += 1
    assert max(reviewed.values()) <= 0.25 * sum(reviewed.values()), reviewed


def test_imposed_event_pulls_review_forward():
    conn = _open()
    today = current_day(conn)
    soldier = None
    for r in conn.execute("SELECT o.actor_id,p.next_review_day FROM org_seats o JOIN simulation_profiles p ON p.actor_id=o.actor_id "
                          "WHERE o.role_key='soldier' AND o.status='active' AND p.cadence_days=7 ORDER BY o.actor_id"):
        if int(r[1]) - today >= 5:
            soldier = int(r[0])
            break
    assert soldier is not None
    due = conn.execute("SELECT next_review_day FROM simulation_profiles WHERE actor_id=?", (soldier,)).fetchone()[0]
    assert due - today >= 5
    record_harm(conn, soldier, source_kind="test_blow", source_ref_id=1, severity=20.0, intent_class="hostile", outcome_override="transient")
    assert conn.execute("SELECT next_review_day FROM simulation_profiles WHERE actor_id=?", (soldier,)).fetchone()[0] == today + 1
    advance_connection(conn, 1)
    assert conn.execute("SELECT last_review_day FROM simulation_profiles WHERE actor_id=?", (soldier,)).fetchone()[0] == today + 1


def test_harm_to_someone_without_a_seat_changes_nothing():
    conn = _open()
    civ = int(conn.execute("SELECT p.actor_id FROM simulation_profiles p WHERE p.actor_id NOT IN (SELECT actor_id FROM org_seats) LIMIT 1").fetchone()[0])
    before = tuple(conn.execute("SELECT next_review_day,forced_tier,forced_until_day FROM simulation_profiles WHERE actor_id=?", (civ,)).fetchone())
    record_harm(conn, civ, source_kind="test_blow", source_ref_id=2, severity=20.0, intent_class="hostile", outcome_override="transient")
    assert tuple(conn.execute("SELECT next_review_day,forced_tier,forced_until_day FROM simulation_profiles WHERE actor_id=?", (civ,)).fetchone()) == before


def test_a_superiors_death_and_a_new_leader_pull_his_men_forward():
    from engine import outfit_choices
    conn = _open()
    today = current_day(conn)
    capo, org, unit = conn.execute(
        "SELECT o.actor_id,o.org_actor_id,o.unit_id FROM org_seats o WHERE o.role_key='capo' AND o.status='active' AND "
        "(SELECT COUNT(*) FROM org_seats s WHERE s.superior_actor_id=o.actor_id AND s.status='active')>3 ORDER BY o.actor_id LIMIT 1").fetchone()
    men = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active'", (capo,))]
    far = [m for m in men if conn.execute("SELECT next_review_day FROM simulation_profiles WHERE actor_id=?", (m,)).fetchone()[0] - today >= 3]
    assert far
    head = orgs.head_of(conn, int(org))
    outfit_choices.kill(conn, int(head), int(capo), today, sanctioned=True)
    for m in men:
        assert conn.execute("SELECT next_review_day FROM simulation_profiles WHERE actor_id=?", (m,)).fetchone()[0] == today + 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
