"""Gregorian <-> Jalali (Solar Hijri) conversion, algorithm A: the 33-year-cycle arithmetic (Borkowski / jalaali-js).

Used for the request-number series only (contract section 8, D1).  The API itself never returns Jalali dates.
Valid for Jalali years -61..3177; the supported business range is much smaller (see numbering.py).
Algorithm B (jalali_astro.py, Meeus equinox) is an independent implementation used to cross-check this one.
"""
from __future__ import annotations

from datetime import date

_BREAKS = (-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178)


def _div(a: int, b: int) -> int:
    return a // b


def nowruz(jy: int) -> date:
    """Gregorian date of 1 Farvardin of Jalali year jy (arithmetic rule)."""
    if jy < _BREAKS[0] or jy >= _BREAKS[-1]:
        raise ValueError(f"Jalali year {jy} outside the supported range")
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += _div(jump, 33) * 8 + _div(jump % 33, 4)
        jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(n % 33 + 3, 4)
    if jump % 33 == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    return date(gy, 3, march)


def jalali_year(g: date, nowruz_fn=nowruz) -> int:
    jy = g.year - 621
    return jy if g >= nowruz_fn(jy) else jy - 1


def is_leap(jy: int, nowruz_fn=nowruz) -> bool:
    return (nowruz_fn(jy + 1) - nowruz_fn(jy)).days == 366


def to_jalali(g: date, nowruz_fn=nowruz) -> tuple[int, int, int]:
    """(year, month, day). Month lengths: 1-6 -> 31, 7-11 -> 30, 12 -> 29 (30 in a leap year)."""
    jy = jalali_year(g, nowruz_fn)
    doy = (g - nowruz_fn(jy)).days            # 0-based
    if doy < 186:
        return jy, doy // 31 + 1, doy % 31 + 1
    doy -= 186                                  # days since 1 Mehr
    if doy < 150:                               # months 7..11 (30 days each)
        return jy, 7 + doy // 30, doy % 30 + 1
    return jy, 12, doy - 150 + 1                # Esfand
