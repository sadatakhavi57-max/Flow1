import random
import unittest
from datetime import date, datetime, timedelta, timezone

from tradeflow_core import jalali as A, jalali_astro as B, numbering as N

UTC = timezone.utc


class JalaliCalendar(unittest.TestCase):
    def test_nowruz_anchors_both_algorithms(self):
        anchors = {1391: (2012, 3, 20), 1395: (2016, 3, 20), 1399: (2020, 3, 20), 1400: (2021, 3, 21),
                   1403: (2024, 3, 20), 1404: (2025, 3, 21), 1405: (2026, 3, 21), 1406: (2027, 3, 21), 1407: (2028, 3, 20)}
        for y, d in anchors.items():
            self.assertEqual(A.nowruz(y), date(*d), y)
            self.assertEqual(B.nowruz(y), date(*d), y)

    def test_independent_algorithms_agree_1365_to_1528(self):
        self.assertEqual([y for y in range(1365, 1529) if A.nowruz(y) != B.nowruz(y)], [])

    def test_known_risk_years_are_outside_the_supported_range(self):
        near = [y for y in range(1365, 1529) if B.minutes_from_noon(y) < 15]
        self.assertEqual(near, [1470, 1503])
        self.assertTrue(all(y not in N.SUPPORTED_YEARS for y in [1503]))
        # 1470 is inside range(1400,1500): the two algorithms agree there, and it is listed so a reviewer sees it
        self.assertEqual(A.nowruz(1470), B.nowruz(1470))

    def test_year_lengths_and_leap_years(self):
        for y in range(1400, 1500):
            self.assertIn((A.nowruz(y + 1) - A.nowruz(y)).days, (365, 366))
        self.assertEqual([y for y in range(1399, 1413) if A.is_leap(y)], [1399, 1403, 1408, 1412])     # 1408, not 1407
        self.assertEqual([y for y in range(1399, 1413) if (B.nowruz(y + 1) - B.nowruz(y)).days == 366], [1399, 1403, 1408, 1412])

    def test_to_jalali_known_dates(self):
        self.assertEqual(A.to_jalali(date(2026, 3, 21)), (1405, 1, 1))
        self.assertEqual(A.to_jalali(date(2026, 3, 20)), (1404, 12, 29))
        self.assertEqual(A.to_jalali(date(2025, 3, 20)), (1403, 12, 30))          # leap year's 30th Esfand
        self.assertEqual(A.to_jalali(date(2026, 10, 12)), (1405, 7, 20))           # 20 Mehr 1405
        self.assertEqual(A.to_jalali(date(2026, 9, 22)), (1405, 6, 31))            # last day of Shahrivar
        self.assertEqual(A.to_jalali(date(2026, 9, 23)), (1405, 7, 1))             # 1 Mehr

    def test_roundtrip_every_day_1400_to_1499(self):
        d = A.nowruz(1400); end = A.nowruz(1500); prev = None
        while d < end:
            jy, jm, jd = A.to_jalali(d)
            self.assertTrue(1 <= jm <= 12 and 1 <= jd <= 31)
            if prev:
                self.assertTrue((jy, jm, jd) > prev)                              # strictly increasing
            prev = (jy, jm, jd)
            d += timedelta(days=1)


class Series(unittest.TestCase):
    def test_nowruz_boundary_1405_in_tehran_time(self):
        # 2026-03-21 00:00 Tehran = 2026-03-20 20:30 UTC
        self.assertEqual(N.series_for(datetime(2026, 3, 20, 20, 29, 59, tzinfo=UTC)), "1404")
        self.assertEqual(N.series_for(datetime(2026, 3, 20, 20, 30, 0, tzinfo=UTC)), "1405")
        self.assertEqual(N.series_for(datetime(2026, 3, 21, 0, 0, 0, tzinfo=UTC)), "1405")

    def test_utc_date_differs_from_tehran_date(self):
        # 23:00 UTC on 20 March is already 21 March 02:30 in Tehran -> new year, although the UTC date is still the 20th
        self.assertEqual(N.series_for(datetime(2026, 3, 20, 23, 0, tzinfo=UTC)), "1405")
        # offset-aware instants in other zones normalise correctly
        self.assertEqual(N.series_for(datetime(2026, 3, 20, 23, 59, 59, tzinfo=timezone(timedelta(hours=3, minutes=30)))), "1404")

    def test_boundaries_every_year_against_astronomical_algorithm(self):
        for jy in range(1401, 1500):                                               # 1400's previous year (1399) is outside the supported range
            nz = B.nowruz(jy)                                                      # independent implementation
            midnight_tehran_utc = datetime(nz.year, nz.month, nz.day, tzinfo=UTC) - timedelta(hours=3, minutes=30)
            self.assertEqual(N.series_for(midnight_tehran_utc - timedelta(seconds=1)), str(jy - 1), jy)
            self.assertEqual(N.series_for(midnight_tehran_utc), str(jy), jy)

    def test_random_instants_equal_astronomical_result_2023_2100(self):
        rnd = random.Random(1405)
        lo = datetime(2023, 1, 1, tzinfo=UTC); span = int((datetime(2100, 1, 1, tzinfo=UTC) - lo).total_seconds())
        for _ in range(20000):
            t = lo + timedelta(seconds=rnd.randrange(span))
            local = (t + timedelta(hours=3, minutes=30)).date()                    # Iran has had no DST since 2022
            jy = local.year - 621
            want = jy if local >= B.nowruz(jy) else jy - 1
            self.assertEqual(N.series_for(t), str(want), t)

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError): N.series_for(datetime(2026, 10, 1))

    def test_outside_verified_range_rejected(self):
        with self.assertRaises(ValueError): N.series_for(datetime(2030, 1, 1, tzinfo=UTC).replace(year=2130))
        with self.assertRaises(ValueError): N.series_for(datetime(2020, 1, 1, tzinfo=UTC))      # 1398

    def test_today_in_tehran(self):
        self.assertEqual(N.tehran_today(datetime(2026, 10, 14, 21, 0, tzinfo=UTC)), date(2026, 10, 15))
        self.assertEqual(N.tehran_today(datetime(2026, 10, 14, 20, 29, tzinfo=UTC)), date(2026, 10, 14))


class Format(unittest.TestCase):
    def test_format_and_parse(self):
        self.assertEqual(N.format_request_number("1405", 1), "1405-000001")
        self.assertEqual(N.format_request_number("1405", 999999), "1405-999999")
        self.assertEqual(N.format_request_number("1405", 1000000), "1405-1000000")      # simply longer
        self.assertEqual(N.parse_request_number("1405-000042"), ("1405", 42))
        self.assertEqual(N.parse_request_number("1405-1000000"), ("1405", 1000000))
        for bad in ["2026-000001", "1405-1", "1405000001", "1405-00000a", ""]:
            with self.assertRaises(ValueError): N.parse_request_number(bad)
        with self.assertRaises(ValueError): N.format_request_number("1405", 0)
        with self.assertRaises(ValueError): N.format_request_number("405", 1)

    def test_series_is_text_not_derived_later(self):
        n = N.format_request_number(N.series_for(datetime(2026, 10, 14, tzinfo=UTC)), 7)
        self.assertEqual(n, "1405-000007")


if __name__ == "__main__":
    unittest.main()
