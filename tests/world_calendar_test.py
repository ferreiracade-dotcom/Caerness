"""Task 5: calendar behind the world package."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    from engine import civil_calendar as cv
    from engine import world_calendar as wc

    sv = SimpleNamespace(calendar={"kind": "sv"})
    for d in (0, 364, 365, -3650):
        assert wc.format_date(sv, d) == cv.format_sv_date(d)
        assert wc.birth_date_for(sv, d) == cv.format_sv_date(d)
        assert wc.season(sv, d) == cv.season_for_day(d)
        assert wc.day_for_date(sv, cv.format_sv_date(d)) == d
    assert wc.format_date(sv, 0) == "1 First Month, 624 SV"

    g = SimpleNamespace(calendar={"kind": "gregorian", "start": "1975-01-01"})
    assert wc.format_date(g, 0) == "Wednesday 1 January 1975"
    assert wc.format_date(g, 59) == "Saturday 1 March 1975"
    # 1976 is a leap year: five years after day 0 is day 1826 (1 January 1980 was a Tuesday)
    assert wc.format_date(g, 1825) == "Monday 31 December 1979"
    assert wc.format_date(g, 1826) == "Tuesday 1 January 1980"
    assert wc.format_date(g, 1826 + 59) == "Friday 29 February 1980"
    assert wc.format_date(g, -1) == "Tuesday 31 December 1974"
    assert wc.season(g, 0) == "Winter" and wc.season(g, 59) == "Spring"
    assert wc.season(g, 170) == "Summer" and wc.season(g, 270) == "Autumn" and wc.season(g, -1) == "Winter"
    assert wc.birth_date_for(g, 59) == wc.format_date(g, 59)
    for d in (0, 59, 1825, 1826, -1, -3650, 20000):
        assert wc.day_for_date(g, wc.format_date(g, d)) == d
    assert wc.day_for_date(g, "1 March 1975") == 59
    for bad in ("Monday 1 January 1975", "nonsense"):
        try:
            wc.day_for_date(g, bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    print("world_calendar_test passed")


if __name__ == "__main__":
    run()
