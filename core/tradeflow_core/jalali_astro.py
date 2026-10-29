"""Algorithm B: Nowruz from the astronomical rule, independent of jalali.py.

Official Iranian calendar rule: the year starts at the midnight before the March equinox if the equinox occurs before
noon Tehran solar time (UTC+3:30, meridian 52.5E), otherwise at the next midnight.  The equinox instant is computed with
Jean Meeus, 'Astronomical Algorithms' (2nd ed.), chapter 27 (accurate to about a minute for modern years).
Used by the tests to cross-check jalali.py and to flag years whose equinox falls within minutes of noon.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

_A = (485, 203, 199, 182, 156, 136, 77, 74, 70, 58, 52, 50, 45, 44, 29, 18, 17, 16, 14, 12, 12, 12, 9, 8)
_B = (324.96, 337.23, 342.08, 27.85, 73.14, 171.52, 222.54, 296.72, 243.58, 119.81, 297.17, 21.02,
      247.54, 325.15, 60.93, 155.12, 288.79, 198.04, 199.76, 95.39, 287.11, 320.81, 227.73, 15.45)
_C = (1934.136, 32964.467, 20.186, 445267.112, 45036.886, 22518.443, 65928.934, 3034.906, 9037.513,
      33718.147, 150.678, 2281.226, 29929.562, 31555.956, 4443.417, 67555.328, 4562.452, 62894.029,
      31436.921, 14577.848, 31931.756, 34777.259, 1222.114, 16859.074)


def _delta_t(year: float) -> float:
    """TT - UT in seconds (Espenak-Meeus polynomials)."""
    if 2005 <= year < 2050:
        t = year - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t * t
    if 2050 <= year <= 2150:
        return -20 + 32 * ((year - 1820) / 100) ** 2 - 0.5628 * (2150 - year)
    if 1986 <= year < 2005:
        t = year - 2000
        return 63.86 + 0.3345 * t - 0.060374 * t**2 + 0.0017275 * t**3 + 0.000651814 * t**4 + 0.00002373599 * t**5
    raise ValueError("equinox helper supports 1986..2150")


def march_equinox_ut(gy: int) -> datetime:
    y = (gy - 2000) / 1000
    jde0 = 2451623.80984 + 365242.37404 * y + 0.05169 * y**2 - 0.00411 * y**3 - 0.00057 * y**4
    t = (jde0 - 2451545.0) / 36525
    w = math.radians(35999.373 * t - 2.47)
    dl = 1 + 0.0334 * math.cos(w) + 0.0007 * math.cos(2 * w)
    s = sum(a * math.cos(math.radians(b + c * t)) for a, b, c in zip(_A, _B, _C))
    jde = jde0 + 0.00001 * s / dl
    jd_ut = jde - _delta_t(gy + 0.22) / 86400
    return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd_ut - 2451545.0)


def equinox_tehran(gy: int) -> datetime:
    return march_equinox_ut(gy) + timedelta(hours=3, minutes=30)          # naive-looking local solar time


def nowruz(jy: int) -> date:
    local = equinox_tehran(jy + 621)
    d = date(local.year, local.month, local.day)
    return d if local.hour < 12 else d + timedelta(days=1)


def minutes_from_noon(jy: int) -> float:
    local = equinox_tehran(jy + 621)
    return abs((local.hour * 60 + local.minute + local.second / 60) - 720)
