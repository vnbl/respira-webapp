"""Tests for the AirGradient client and the AQI functions it feeds.

The client's job is to hide two upstream quirks from the export: a 10-day cap
per request, and buckets that change width (5 or 60 minutes) with the age of the
data. Both are covered here so ``tests_institution_exports`` can stub the client
and talk about spreadsheets instead.

The AQI cases are the pipeline's own reference values, copied from
``dbt/tests/respira_gold/aqi_macro_reference_values.sql``: these two
implementations must agree, or a downloaded file and the dashboard would show
different numbers for the same reading.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import Mock

import requests
from django.test import SimpleTestCase, override_settings

from .airgradient import (
    MAX_WINDOW,
    AirGradientError,
    fetch_past_measures,
    location_id_for_station,
    _windows,
)
from .aqi import aqi_from_pm10, aqi_from_pm25


class _FakeStation:
    def __init__(self, station_code):
        self.station_code = station_code

    def __str__(self):
        return "Estación de prueba"


class LocationIdTests(SimpleTestCase):
    def test_reads_the_location_from_the_station_code(self):
        self.assertEqual(
            location_id_for_station(_FakeStation("respira_191355")), 191355
        )

    def test_rejects_a_station_from_another_network(self):
        # FIUNA and MADES stations reach gold too, but have no AirGradient
        # identity; exporting one is a configuration error, not an empty file.
        with self.assertRaises(AirGradientError):
            location_id_for_station(_FakeStation("fiuna_3"))

    def test_rejects_a_malformed_code(self):
        with self.assertRaises(AirGradientError):
            location_id_for_station(_FakeStation("respira_villa_morra"))

    def test_rejects_a_station_with_no_code(self):
        with self.assertRaises(AirGradientError):
            location_id_for_station(_FakeStation(""))


class WindowTests(SimpleTestCase):
    def test_a_short_range_is_a_single_window(self):
        start = datetime(2026, 7, 1, tzinfo=dt_timezone.utc)
        end = start + timedelta(days=3)
        self.assertEqual(list(_windows(start, end)), [(start, end)])

    def test_a_long_range_is_split_at_the_cap(self):
        start = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        end = start + timedelta(days=25)
        windows = list(_windows(start, end))

        self.assertEqual(len(windows), 3)
        for window_start, window_end in windows:
            self.assertLessEqual(window_end - window_start, MAX_WINDOW)

    def test_windows_are_contiguous_and_cover_the_range(self):
        """No gap and no overlap: a reading is fetched exactly once."""
        start = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        end = start + timedelta(days=25)
        windows = list(_windows(start, end))

        self.assertEqual(windows[0][0], start)
        self.assertEqual(windows[-1][1], end)
        for earlier, later in zip(windows, windows[1:]):
            self.assertEqual(earlier[1], later[0])

    def test_an_empty_range_yields_nothing(self):
        moment = datetime(2026, 7, 1, tzinfo=dt_timezone.utc)
        self.assertEqual(list(_windows(moment, moment)), [])


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@override_settings(AIRGRADIENT_API_TOKEN="test-token")
class FetchPastMeasuresTests(SimpleTestCase):
    def setUp(self):
        self.start = datetime(2026, 7, 1, tzinfo=dt_timezone.utc)

    def test_requires_a_token(self):
        with override_settings(AIRGRADIENT_API_TOKEN=""):
            with self.assertRaises(AirGradientError):
                fetch_past_measures(1, self.start, self.start + timedelta(days=1))

    def test_concatenates_every_window(self):
        session = Mock()
        session.get.side_effect = [
            _response([{"timestamp": "2026-07-01T00:00:00.000Z"}]),
            _response([{"timestamp": "2026-07-11T00:00:00.000Z"}]),
        ]

        result = fetch_past_measures(
            1, self.start, self.start + timedelta(days=15), session=session
        )

        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.failed_windows, 0)

    def test_rows_come_back_in_timestamp_order(self):
        session = Mock()
        session.get.return_value = _response(
            [
                {"timestamp": "2026-07-02T00:00:00.000Z"},
                {"timestamp": "2026-07-01T00:00:00.000Z"},
            ]
        )

        result = fetch_past_measures(
            1, self.start, self.start + timedelta(days=2), session=session
        )

        self.assertEqual(
            [row["timestamp"] for row in result.rows],
            ["2026-07-01T00:00:00.000Z", "2026-07-02T00:00:00.000Z"],
        )

    def test_duplicate_timestamps_are_dropped(self):
        """Bucket width changes with age, so a boundary can repeat an hour."""
        session = Mock()
        session.get.side_effect = [
            _response([{"timestamp": "2026-07-10T23:00:00.000Z", "pm02": 1}]),
            _response([{"timestamp": "2026-07-10T23:00:00.000Z", "pm02": 2}]),
        ]

        result = fetch_past_measures(
            1, self.start, self.start + timedelta(days=15), session=session
        )

        self.assertEqual(len(result.rows), 1)

    def test_windows_are_fetched_concurrently(self):
        """A year of history is 37 windows; serially that is a minute of waiting."""
        import threading

        barrier = threading.Barrier(2, timeout=5)

        def slow_get(*args, **kwargs):
            # Deadlocks unless two calls are genuinely in flight at once, so
            # this fails rather than hangs if the fetch goes back to serial.
            barrier.wait()
            return _response([])

        session = Mock()
        session.get.side_effect = slow_get

        fetch_past_measures(
            1, self.start, self.start + timedelta(days=15), session=session
        )

        self.assertEqual(session.get.call_count, 2)

    def test_rows_keep_window_order_regardless_of_completion_order(self):
        """Concurrency must not make the output depend on which call finished first."""
        session = Mock()
        session.get.side_effect = [
            _response([{"timestamp": "2026-07-05T00:00:00.000Z"}]),
            _response([{"timestamp": "2026-07-12T00:00:00.000Z"}]),
        ]

        result = fetch_past_measures(
            1, self.start, self.start + timedelta(days=15), session=session
        )

        self.assertEqual(
            [row["timestamp"] for row in result.rows],
            ["2026-07-05T00:00:00.000Z", "2026-07-12T00:00:00.000Z"],
        )

    def test_a_failing_window_is_counted_not_fatal(self):
        """A partial history beats an error page, but the gap is reported."""
        session = Mock()
        session.get.side_effect = [
            requests.RequestException("boom"),
            _response([{"timestamp": "2026-07-11T00:00:00.000Z"}]),
        ]

        result = fetch_past_measures(
            1, self.start, self.start + timedelta(days=15), session=session
        )

        self.assertEqual(result.failed_windows, 1)
        self.assertEqual(len(result.rows), 1)

    def test_an_unexpected_payload_shape_is_counted(self):
        session = Mock()
        session.get.return_value = _response({"error": "not a list"})

        result = fetch_past_measures(
            1, self.start, self.start + timedelta(days=1), session=session
        )

        self.assertEqual(result.failed_windows, 1)
        self.assertEqual(result.rows, [])

    def test_rows_without_a_timestamp_are_skipped(self):
        session = Mock()
        session.get.return_value = _response([{"pm02": 5}, {"timestamp": None}])

        result = fetch_past_measures(
            1, self.start, self.start + timedelta(days=1), session=session
        )

        self.assertEqual(result.rows, [])

    def test_the_token_is_sent_as_a_query_parameter(self):
        session = Mock()
        session.get.return_value = _response([])

        fetch_past_measures(
            191355, self.start, self.start + timedelta(days=1), session=session
        )

        _, kwargs = session.get.call_args
        self.assertEqual(kwargs["params"]["token"], "test-token")
        # Basic ISO 8601, as the API's `from`/`to` require.
        self.assertEqual(kwargs["params"]["from"], "20260701T000000Z")

    def test_timestamps_are_sent_in_utc(self):
        """A local-time bound would silently shift the range by three hours."""
        import zoneinfo

        session = Mock()
        session.get.return_value = _response([])
        asuncion = zoneinfo.ZoneInfo("America/Asuncion")
        local_start = datetime(2026, 7, 1, tzinfo=asuncion)

        fetch_past_measures(
            1, local_start, local_start + timedelta(days=1), session=session
        )

        _, kwargs = session.get.call_args
        self.assertEqual(kwargs["params"]["from"], "20260701T030000Z")


class AqiReferenceTests(SimpleTestCase):
    """The pipeline's own reference values; the two must not drift apart."""

    def test_pm25_reference_value(self):
        self.assertEqual(aqi_from_pm25(17.301805555333335), 62)

    def test_pm25_truncates_to_one_decimal(self):
        self.assertEqual(aqi_from_pm25(12.09), 50)

    def test_pm10_truncates_to_integer(self):
        self.assertEqual(aqi_from_pm10(54.99), 50)

    def test_band_boundaries(self):
        for concentration, expected in (
            (0, 0),
            (12.0, 50),
            (12.1, 51),
            (35.4, 100),
            (55.4, 150),
            (150.4, 200),
            (250.4, 300),
            (350.4, 400),
            (500.4, 500),
        ):
            with self.subTest(concentration=concentration):
                self.assertEqual(aqi_from_pm25(concentration), expected)

    def test_values_above_the_last_band_cap_at_500(self):
        self.assertEqual(aqi_from_pm25(9000), 500)
        self.assertEqual(aqi_from_pm10(9000), 500)

    def test_missing_and_negative_concentrations_have_no_index(self):
        self.assertIsNone(aqi_from_pm25(None))
        self.assertIsNone(aqi_from_pm25(-1))
        self.assertIsNone(aqi_from_pm10(None))
        self.assertIsNone(aqi_from_pm10(-1.5))

    def test_a_negative_pm10_truncating_to_zero_reads_as_zero(self):
        """Matches the dbt macro: `trunc(-0.5, 0)` is 0 in Postgres, not -1.

        Faithfulness to the pipeline matters more here than the intuitive
        answer — the two implementations have to agree on every input.
        """
        self.assertEqual(aqi_from_pm10(-0.5), 0)
