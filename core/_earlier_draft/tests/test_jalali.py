import unittest
from datetime import date, datetime, timedelta, timezone

from tradeflow_core import jalali as J
from tradeflow_core.numbering import format_request_number, series_for
from . import astro_nowruz as astro

KNOWN = {1399: (2020, 3, 20), 1400: (2021, 3, 21), 1401: (2022, 3, 21), 1402: (2023, 3, 21),
         1403: (2024, 3, 20), 1404: (2025, 3, 21), 1405: (2026, 3, 21)}


class Nowruz(unittest.TestCase):
    def test_known_official_dates(self):
        for jy, (y, m, d) in KNOWN.items():
            _, gy, mar = J._jal_cal(jy)
            self.assertEqual(date(gy, 3, mar), date(y, m, d), jy)

    def test_equals_astronomy_for_1385_to_1529(self):
        checked, ambiguous = 0, []
        for jy in range(1385, 1530):
            gy = jy + 621
            if gy > 2150:
                break
            expected, minutes = astro.nowruz(gy)
            _, g, mar = J._jal_cal(jy)
            if abs(minutes) < astro.AMBIG_MIN:
                ambiguous.append(jy)
                continue
            self.assertEqual(date(g, 3, mar), expected, f"Jalali {jy} (equinox {minutes:+.1f} min from noon)")
            checked += 1
        self.assertGreater(checked, 140)
        self.assertLessEqual(len(ambiguous), 2)

    def test_year_of_dates_around_nowruz(self):
        cases = {date(2025, 3, 20): 1403, date(2025, 3, 21): 1404, date(2026, 3, 20): 1404, date(2026, 3, 21): 1405,
                 date(2027, 3, 20): 1405, date(2027, 3, 21): 1406, date(2026, 12, 31): 1405, date(2026, 1, 1): 1404}
        for d, y in cases.items():
            self.assertEqual(J.jalali_year(d), y, d)

    def test_year_is_monotonic_and_changes_once_a_year(self):
        d, prev, changes = date(2020, 1, 1), None, 0
        while d < date(2060, 1, 1):
            y = J.jalali_year(d)
            if prev is not None:
                self.assertIn(y - prev, (0, 1))
                changes += y != prev
            prev, d = y, d + timedelta(days=1)
        self.assertEqual(changes, 40)           # Nowruz of 2020..2059 inclusive = 40 boundaries


class RequestNumber(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_request_number("1405", 1), "1405-000001")
        self.assertEqual(format_request_number("1405", 999999), "1405-999999")
        self.assertEqual(format_request_number("1405", 1000000), "1405-1000000")      # longer, no truncation
        with self.assertRaises(ValueError):
            format_request_number("1405", 0)

    def test_series_uses_tehran_midnight_not_utc(self):
        # Nowruz 1405 = 2026-03-21 Tehran. Tehran midnight = 2026-03-20T20:30:00Z.
        before = datetime(2026, 3, 20, 20, 29, 59, 999999, tzinfo=timezone.utc)
        at = datetime(2026, 3, 20, 20, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(series_for(before), "1404")
        self.assertEqual(series_for(at), "1405")
        # a UTC instant that is already 21 March in Tehran but still 20 March in UTC
        self.assertEqual(series_for(datetime(2026, 3, 20, 23, 0, tzinfo=timezone.utc)), "1405")

    def test_naive_datetime_is_refused(self):
        with self.assertRaises(ValueError):
            series_for(datetime(2026, 3, 21, 12, 0))

    def test_display_is_derived_from_the_stored_instant(self):
        inst = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(series_for(inst), "1405")
        self.assertEqual(inst.isoformat(), "2026-10-10T09:00:00+00:00")        # the instant itself is untouched


if __name__ == "__main__":
    unittest.main()
