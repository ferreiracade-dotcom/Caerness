from __future__ import annotations

"""Shared Caernessian civil calendar.

Day 0 is 1 First Month, 624 SV (Since the Vanishing).  The simulation keeps
integer day offsets as the authoritative arithmetic representation; civil dates
are a deterministic presentation/provenance view over those offsets.
"""

OPENING_YEAR_SV = 624
DAYS_PER_YEAR = 365
MONTH_NAMES = (
    "First Month", "Second Month", "Third Month", "Fourth Month",
    "Fifth Month", "Sixth Month", "Seventh Month", "Eighth Month",
    "Ninth Month", "Tenth Month", "Eleventh Month", "Twelfth Month",
)
MONTH_LENGTHS = (31, 30, 30, 31, 30, 30, 31, 30, 30, 31, 30, 31)

if sum(MONTH_LENGTHS) != DAYS_PER_YEAR:  # defensive import-time invariant
    raise RuntimeError("Caerness civil calendar must total exactly 365 days")


def sv_date_from_day(day_offset: int) -> tuple[int, int, int]:
    """Return ``(year_sv, month_number, day_of_month)`` for an opening-relative day."""
    year_delta, day_of_year = divmod(int(day_offset), DAYS_PER_YEAR)
    year = OPENING_YEAR_SV + year_delta
    for month, length in enumerate(MONTH_LENGTHS, start=1):
        if day_of_year < length:
            return year, month, day_of_year + 1
        day_of_year -= length
    raise AssertionError("unreachable calendar conversion state")


def day_from_sv_date(year_sv: int, month: int, day: int) -> int:
    """Return the opening-relative day for a civil SV date."""
    year_sv = int(year_sv); month = int(month); day = int(day)
    if not 1 <= month <= 12:
        raise ValueError("month must be in 1..12")
    length = MONTH_LENGTHS[month - 1]
    if not 1 <= day <= length:
        raise ValueError(f"day must be in 1..{length} for {MONTH_NAMES[month - 1]}")
    day_of_year = sum(MONTH_LENGTHS[: month - 1]) + day - 1
    return (year_sv - OPENING_YEAR_SV) * DAYS_PER_YEAR + day_of_year


def format_sv_date(day_offset: int) -> str:
    year, month, day = sv_date_from_day(day_offset)
    return f"{day} {MONTH_NAMES[month - 1]}, {year} SV"


def season_for_day(day_offset: int) -> str:
    """Spring months 1-3, Summer 4-6, Autumn 7-9, Winter 10-12 (World Bible, calendar and dating convention)."""
    return ("Spring", "Summer", "Autumn", "Winter")[(sv_date_from_day(day_offset)[1] - 1) // 3]
