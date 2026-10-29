"""Independent astronomical reference for Nowruz (Meeus, 'Astronomical Algorithms' ch. 27, March equinox).
Iranian official rule: the new year starts on the Tehran civil day on which the spring equinox falls when it occurs
BEFORE 12:00 Tehran time, otherwise on the following day. Tehran is UTC+03:30 (no DST since 2022; for 2008-2021 the DST
was in effect from 22 March, i.e. after the equinox, so the equinox itself is always evaluated at +03:30).
Accuracy of the equinox instant here is about +-1 minute; years whose equinox is within AMBIG_MIN minutes of noon are
reported as ambiguous instead of being used as proof."""
import math
from datetime import date, datetime, timedelta, timezone

_TERMS = [(485, 324.96, 1934.136), (203, 337.23, 32964.467), (199, 342.08, 20.186), (182, 27.85, 445267.112),
          (156, 73.14, 45036.886), (136, 171.52, 22518.443), (77, 222.54, 65928.934), (74, 296.72, 3034.906),
          (70, 243.58, 9037.513), (58, 119.81, 33718.147), (52, 297.17, 150.678), (50, 21.02, 2281.226),
          (45, 247.54, 29929.562), (44, 325.15, 31555.956), (29, 60.93, 4443.417), (18, 155.12, 67555.328),
          (17, 288.79, 4562.452), (16, 198.04, 62894.029), (14, 199.76, 31436.921), (12, 95.39, 14577.848),
          (12, 287.11, 31931.756), (12, 320.81, 34777.259), (9, 227.73, 1222.114), (8, 15.45, 16859.074)]
AMBIG_MIN = 6
TEHRAN = timezone(timedelta(hours=3, minutes=30))


def _delta_t(y):
    t = y - 2000
    if 2005 <= y < 2050:
        return 62.92 + 0.32217 * t + 0.005589 * t * t
    if 2050 <= y <= 2150:
        return -20 + 32 * ((y - 1820) / 100) ** 2 - 0.5628 * (2150 - y)
    if 1986 <= y < 2005:
        return 63.86 + 0.3345 * t - 0.060374 * t * t + 0.0017275 * t ** 3
    raise ValueError(y)


def equinox_utc(gy: int) -> datetime:
    Y = (gy - 2000) / 1000
    jde0 = 2451623.80984 + 365242.37404 * Y + 0.05169 * Y ** 2 - 0.00411 * Y ** 3 - 0.00057 * Y ** 4
    T = (jde0 - 2451545.0) / 36525
    W = math.radians(35999.373 * T - 2.47)
    dl = 1 + 0.0334 * math.cos(W) + 0.0007 * math.cos(2 * W)
    S = sum(a * math.cos(math.radians(b + c * T)) for a, b, c in _TERMS)
    jde = jde0 + 0.00001 * S / dl
    jd_utc = jde - _delta_t(gy) / 86400
    return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd_utc - 2451545.0)


def nowruz(gy: int):
    """(date, minutes_from_noon) of 1 Farvardin that starts in Gregorian year gy."""
    eq = equinox_utc(gy).astimezone(TEHRAN)
    noon = eq.replace(hour=12, minute=0, second=0, microsecond=0)
    delta_min = (eq - noon).total_seconds() / 60
    d = eq.date() if eq < noon else eq.date() + timedelta(days=1)
    return d, delta_min
