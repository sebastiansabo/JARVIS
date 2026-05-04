"""Romanian public holidays — pure computation, no external API.

Covers all holidays per Romanian law (2024 amendments):
- 12 fixed holidays
- 5 movable holidays (depend on Orthodox Easter)

Orthodox Easter is computed using the Meeus algorithm for the Julian calendar,
then converted to the Gregorian calendar (+ 13 days for years 1900-2099).

Inspired by: https://github.com/ciprian-chichirita/romanian-bank-holidays
"""
from datetime import date, timedelta

# ── Fixed holidays (month, day, name) ──────────────────────────────
FIXED_HOLIDAYS = [
    (1, 1, "Anul Nou"),
    (1, 2, "Anul Nou (ziua 2)"),
    (1, 6, "Boboteaza"),
    (1, 7, "Soborul Sf. Ioan Botezatorul"),
    (1, 24, "Ziua Unirii Principatelor Romane"),
    (5, 1, "Ziua Muncii"),
    (6, 1, "Ziua Copilului"),
    (8, 15, "Adormirea Maicii Domnului"),
    (11, 30, "Sfantul Andrei"),
    (12, 1, "Ziua Nationala a Romaniei"),
    (12, 25, "Craciunul"),
    (12, 26, "Craciunul (ziua 2)"),
]


def orthodox_easter(year: int) -> date:
    """Compute Orthodox Easter Sunday for a given year.

    Uses the Meeus algorithm for the Julian calendar,
    then converts the result to the Gregorian calendar.
    The Julian-to-Gregorian offset is 13 days for years 1900-2099.
    """
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    # Julian date → Gregorian (add 13 days for 1900-2099)
    return date(year, month, day) + timedelta(days=13)


def get_movable_holidays(year: int) -> list[tuple[date, str]]:
    """Return movable holidays for a year, based on Orthodox Easter."""
    easter = orthodox_easter(year)
    return [
        (easter - timedelta(days=2), "Vinerea Mare"),
        (easter, "Pastele Ortodox"),
        (easter + timedelta(days=1), "Pastele Ortodox (ziua 2)"),
        (easter + timedelta(days=49), "Rusaliile"),
        (easter + timedelta(days=50), "Rusaliile (ziua 2)"),
    ]


def get_all_holidays(year: int) -> list[tuple[date, str, str]]:
    """Return all Romanian public holidays for a year.

    Returns list of (date, name, holiday_type) tuples sorted by date.
    holiday_type is 'fixed' or 'movable'.
    """
    holidays = []
    for m, d, name in FIXED_HOLIDAYS:
        holidays.append((date(year, m, d), name, 'fixed'))
    for dt, name in get_movable_holidays(year):
        holidays.append((dt, name, 'movable'))
    holidays.sort(key=lambda x: x[0])
    return holidays
