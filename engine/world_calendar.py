"""Calendar behind the world package: 'sv' (Caerness civil calendar) or 'gregorian' (start = ISO date of day 0)."""
from __future__ import annotations

import re
from datetime import date, timedelta

from engine import civil_calendar as cv

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")
_SEASONS = ("Winter", "Winter", "Spring", "Spring", "Spring", "Summer", "Summer", "Summer",
            "Autumn", "Autumn", "Autumn", "Winter")  # northern-hemisphere meteorological
_SV_RE = re.compile(r"^\s*(\d+)\s+(.+?),\s*(-?\d+)\s+SV\s*$")
_GR_RE = re.compile(r"^\s*(?:([A-Za-z]+)\s+)?(\d+)\s+([A-Za-z]+)\s+(-?\d+)\s*$")


def _kind(pkg) -> str:
    return pkg.calendar["kind"]


def _start(pkg) -> date:
    return date.fromisoformat(pkg.calendar["start"])


def _date(pkg, day: int) -> date:
    return _start(pkg) + timedelta(days=int(day))


def format_date(pkg, day: int) -> str:
    if _kind(pkg) == "sv":
        return cv.format_sv_date(day)
    d = _date(pkg, day)
    return f"{_WEEKDAYS[d.weekday()]} {d.day} {_MONTHS[d.month - 1]} {d.year}"


def season(pkg, day: int) -> str:
    if _kind(pkg) == "sv":
        return cv.season_for_day(day)
    return _SEASONS[_date(pkg, day).month - 1]


def birth_date_for(pkg, birth_day: int) -> str:
    return format_date(pkg, birth_day)


def day_for_date(pkg, text: str) -> int:
    if _kind(pkg) == "sv":
        m = _SV_RE.match(text or "")
        if not m or m.group(2) not in cv.MONTH_NAMES:
            raise ValueError(f"unrecognised SV date: {text!r}")
        return cv.day_from_sv_date(int(m.group(3)), cv.MONTH_NAMES.index(m.group(2)) + 1, int(m.group(1)))
    m = _GR_RE.match(text or "")
    if not m or m.group(3).capitalize() not in _MONTHS:
        raise ValueError(f"unrecognised date: {text!r}")
    d = date(int(m.group(4)), _MONTHS.index(m.group(3).capitalize()) + 1, int(m.group(2)))
    if m.group(1) and m.group(1).capitalize() != _WEEKDAYS[d.weekday()]:
        raise ValueError(f"weekday does not match date: {text!r}")
    return (d - _start(pkg)).days
