"""Jalali (Solar Hijri) year of a Gregorian date - the 33-year-cycle arithmetic method with explicit break years.

Verification (tests/test_jalali.py): the Nowruz date of every Jalali year 1385..1529 equals an INDEPENDENT astronomical
reference (Meeus March equinox, Iranian noon rule, tests/astro_nowruz.py); the 2820-year-cycle algorithm was tried and
REJECTED because it is wrong for 1404, 1437 and 1470 (e.g. it puts Nowruz 1404 on 2025-03-20; the official date is
2025-03-21). Valid range of the break table: Jalali years -61..3177; checked range 1385..1529.
"""
from __future__ import annotations

from datetime import date

_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]


def _div(a, b):
    return a // b


def _jal_cal(jy):
    """Returns (leap, gy, march) for Jalali year jy: march = March day of Nowruz in gregorian year gy."""
    bl = len(_BREAKS)
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    if jy < jp or jy >= _BREAKS[bl - 1]:
        raise ValueError(f"Jalali year out of range: {jy}")
    jump = 0
    for i in range(1, bl):
        jm = _BREAKS[i]
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
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = ((n + 1) % 33 - 1) % 4
    if leap == -1:
        leap = 4
    return leap, gy, march


def _g2d(gy, gm, gd):
    d = (_div((gy + _div(gm - 8, 6) + 100100) * 1461, 4) + _div(153 * ((gm + 9) % 12) + 2, 5) + gd - 34840408)
    return d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752


def jalali_year_A_full(d: date) -> int:
    """Production: the year whose Nowruz is the latest one on or before d."""
    jy = d.year - 621
    _, gy, march = _jal_cal(jy + 1)
    if d >= date(gy, 3, march):
        return jy + 1
    _, gy0, march0 = _jal_cal(jy)
    if d >= date(gy0, 3, march0):
        return jy
    return jy - 1


def jalali_year(d: date) -> int:
    """Production entry point."""
    return jalali_year_A_full(d)
