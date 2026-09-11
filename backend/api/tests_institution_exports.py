"""Tests for the institutional file exports (/api/institution/report|export).

Two things matter here and are covered separately: the authorization boundary
(an institution may only ever export its own sensor's readings) and the file
itself actually being a well-formed PDF/XLSX built from the right rows — a
download that returns 200 with a corrupt body is a failure the status code
cannot catch.
"""

import csv
import io
from datetime import date, datetime, time, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .exports import REPORT_TIME_ZONE
from .models import (
    Institution,
    InstitutionAlertConfig,
    InstitutionContract,
    InstitutionUser,
    Regions,
    StationReadingsGold,
    Stations,
)

User = get_user_model()


def _at(day: date, hour: int) -> datetime:
    """A reading timestamp at a given local hour, stored as UTC."""
    return datetime.combine(day, time(hour), tzinfo=REPORT_TIME_ZONE).astimezone(
        dt_timezone.utc
    )


class InstitutionExportTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

        region = Regions.seed_for_tests(name="Gran Asuncion", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            # `respira_<locationId>`: the raw export resolves the AirGradient
            # location from this, so the code has to look like a real one.
            station_code="respira_191355",
            region=region,
            latitude=-25.28,
            longitude=-57.57,
            is_station_on=True,
        )
        self.other_station = Stations.seed_for_tests(
            name="Respira: Sajonia",
            station_code="respira_192812",
            region=region,
            is_station_on=True,
        )

        self.institution = Institution.objects.create(
            legal_name="Hospital Bautista", display_name="Hospital Bautista"
        )
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            contract_status=InstitutionContract.ContractStatus.ACTIVE,
            start_date=date(2026, 6, 1),
        )
        self.user = User.objects.create_user(
            email="contacto@bautista.test", password="Respira.Test.2026"
        )
        InstitutionUser.objects.create(user=self.user, institution=self.institution)

        # July 2026: three days of readings on the institution's own sensor.
        self.july_days = [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)]
        for index, day in enumerate(self.july_days):
            for hour, aqi in ((8, 40 + index * 30), (20, 60 + index * 30)):
                StationReadingsGold.seed_for_tests(
                    station=self.station,
                    date_utc=_at(day, hour),
                    pm1=5.0,
                    pm2_5=12.5 + index,
                    pm10=20.0,
                    aqi_pm2_5=float(aqi),
                    aqi_pm10=30.0,
                )

        # A reading on somebody else's sensor, same month: it must never appear.
        StationReadingsGold.seed_for_tests(
            station=self.other_station,
            date_utc=_at(date(2026, 7, 2), 12),
            aqi_pm2_5=500.0,
        )

    def login(self):
        # Re-read the user rather than reusing the instance built in setUp:
        # `force_authenticate` hands the view the very object passed here, so a
        # related object touched by the test (`institution.contract`) would stay
        # cached on it and the view would see a row the test had already
        # deleted. A real request loads the user fresh from the session.
        self.client.force_authenticate(user=User.objects.get(pk=self.user.pk))

    def drop_contract(self):
        """Remove the contract without caching it on any instance first."""
        InstitutionContract.objects.filter(institution=self.institution).delete()


class MonthlyReportTests(InstitutionExportTestCase):
    def url(self):
        return reverse("institution-monthly-report")

    def test_anonymous_request_is_rejected(self):
        response = self.client.get(self.url())
        self.assertIn(response.status_code, (401, 403))

    def test_user_without_institution_is_rejected(self):
        outsider = User.objects.create_user(
            email="nadie@example.test", password="Respira.Test.2026"
        )
        self.client.force_authenticate(user=outsider)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 403)

    def test_returns_a_pdf_for_the_requested_month(self):
        self.login()
        response = self.client.get(self.url(), {"month": "2026-07"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        # A real PDF, not an error page with an optimistic content type.
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn(
            "reporte-mensual-hospital-bautista-2026-07.pdf",
            response["Content-Disposition"],
        )

    def test_defaults_to_the_last_complete_month(self):
        """The current month would change between downloads, so it is not the default."""
        self.login()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_rejects_a_malformed_month(self):
        self.login()
        response = self.client.get(self.url(), {"month": "julio"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("month", response.json())

    def test_institution_without_a_sensor_gets_404(self):
        self.drop_contract()
        self.login()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 404)

    def test_month_without_readings_still_renders(self):
        self.login()
        response = self.client.get(self.url(), {"month": "2026-01"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_statistics_cover_only_the_institutions_own_station(self):
        from .exports import _month_statistics

        stats = _month_statistics(self.station.id, date(2026, 7, 1))

        self.assertEqual(len(stats["daily"]), 3)
        self.assertEqual(stats["measurements"], 6)
        # The other station's 500 would dominate if the query leaked across.
        self.assertEqual(stats["highest"], 120.0)
        self.assertEqual(stats["lowest"], 40.0)

    def test_daily_categories_are_counted_on_the_daily_average(self):
        from .exports import _month_statistics

        stats = _month_statistics(self.station.id, date(2026, 7, 1))

        # Averages are 50, 80 and 110 → good, moderate, unhealthy_sensitive.
        self.assertEqual(stats["distribution"]["good"], 1)
        self.assertEqual(stats["distribution"]["moderate"], 1)
        self.assertEqual(stats["distribution"]["unhealthy_sensitive"], 1)
        self.assertEqual(stats["distribution"]["hazardous"], 0)

    def test_a_month_that_has_not_started_is_rejected(self):
        """A blank PDF would read as "the sensor recorded nothing", which is worse."""
        self.login()
        response = self.client.get(self.url(), {"month": "2099-01"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("month", response.json())

    def test_report_matches_the_requested_month(self):
        """Two months with data must not produce the same document."""
        self.login()
        july = self.client.get(self.url(), {"month": "2026-07"})
        january = self.client.get(self.url(), {"month": "2026-01"})

        self.assertEqual(july.status_code, 200)
        self.assertEqual(january.status_code, 200)
        self.assertIn("2026-07", july["Content-Disposition"])
        self.assertIn("2026-01", january["Content-Disposition"])
        self.assertNotEqual(july.content, january.content)

    def test_threshold_is_only_applied_when_alerts_are_enabled(self):
        InstitutionAlertConfig.objects.create(
            institution=self.institution, is_enabled=False, alert_threshold=10
        )
        self.login()
        response = self.client.get(self.url(), {"month": "2026-07"})
        self.assertEqual(response.status_code, 200)


class ReportMonthsTests(InstitutionExportTestCase):
    """The month selector's source of truth."""

    def url(self):
        return reverse("institution-report-months")

    def test_anonymous_request_is_rejected(self):
        response = self.client.get(self.url())
        self.assertIn(response.status_code, (401, 403))

    def test_lists_only_months_with_readings(self):
        self.login()
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        months = [entry["month"] for entry in response.json()["months"]]
        # The fixtures seed July 2026 only; a month with no readings would
        # produce an empty report, so it must not be offered.
        self.assertEqual(months, ["2026-07"])

    def test_months_carry_a_readable_label(self):
        self.login()
        response = self.client.get(self.url())

        self.assertEqual(response.json()["months"][0]["label"], "julio de 2026")

    def test_default_is_the_newest_complete_month(self):
        self.login()
        response = self.client.get(self.url())

        self.assertEqual(response.json()["default"], "2026-07")

    def test_does_not_leak_another_institutions_months(self):
        """The core authorization rule: months come from the caller's own sensor."""
        StationReadingsGold.seed_for_tests(
            station=self.other_station,
            date_utc=_at(date(2026, 3, 4), 10),
            aqi_pm2_5=80.0,
        )
        self.login()
        response = self.client.get(self.url())

        months = [entry["month"] for entry in response.json()["months"]]
        self.assertNotIn("2026-03", months)

    def test_months_before_the_contract_are_excluded(self):
        """Readings predating the contract are not the institution's history."""
        StationReadingsGold.seed_for_tests(
            station=self.station,
            date_utc=_at(date(2025, 12, 2), 10),
            aqi_pm2_5=40.0,
        )
        self.login()
        response = self.client.get(self.url())

        months = [entry["month"] for entry in response.json()["months"]]
        self.assertNotIn("2025-12", months)

    def test_institution_without_a_sensor_gets_404(self):
        self.drop_contract()
        self.login()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 404)

    def test_no_data_yields_an_empty_list_and_no_default(self):
        """The panel's "no months" state has to be distinguishable from a failure."""
        for reading in StationReadingsGold.objects.filter(station=self.station):
            reading.delete_for_tests()
        self.login()
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["months"], [])
        self.assertIsNone(response.json()["default"])


def _measure(moment: datetime, **overrides) -> dict:
    """One AirGradient ``past`` row, shaped like the real API's payload."""
    row = {
        "locationId": 191355,
        "locationName": "Respira: Villa Morra",
        "pm01": 5.0,
        "pm02": 20.3,
        "pm10": 20.0,
        "pm01_corrected": 5.0,
        "pm02_corrected": 12.5,
        "pm10_corrected": 20.0,
        "pm003Count": 1529,
        "rco2": 429,
        "rco2_corrected": 429,
        "atmp": 13.5,
        "atmp_corrected": 13.5,
        "rhum": 54,
        "rhum_corrected": 54,
        "tvoc": None,
        "tvocIndex": 35709,
        "noxIndex": 18307,
        "wifi": -63,
        # Strings on purpose: the real API sends these quoted, and the export
        # has to turn them back into numbers.
        "batteryVoltage": "12.10",
        "panelVoltage": "2.09",
        "datapoints": "2",
        "model": "O-M-1PPST-CE",
        "serialno": "588c813fe18c",
        "firmwareVersion": None,
        "timestamp": moment.astimezone(dt_timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        ),
    }
    row.update(overrides)
    return row


class RawExportTests(InstitutionExportTestCase):
    """The raw export reads AirGradient live, so every test here stubs it.

    The stub stands in for ``fetch_past_measures`` rather than for ``requests``:
    windowing and deduplication are the client's own concern and are covered in
    ``tests_airgradient``, so these tests can speak in measurements.
    """

    def setUp(self):
        super().setUp()
        # Two readings a day across the same three July days the gold fixtures
        # use, so the two exports stay comparable.
        self.measures = [
            _measure(_at(day, hour))
            for day in self.july_days
            for hour in (8, 20)
        ]

    def url(self):
        return reverse("institution-raw-export")

    def stub(self, rows=None, failed_windows=0):
        """Patch the API client, capturing the range it was asked for."""
        from unittest.mock import patch

        from .airgradient import FetchResult

        captured = {}

        def fake_fetch(location_id, start, end, **kwargs):
            captured["location_id"] = location_id
            captured["start"] = start
            captured["end"] = end
            return FetchResult(
                rows=list(self.measures if rows is None else rows),
                failed_windows=failed_windows,
            )

        patcher = patch("api.exports.fetch_past_measures", side_effect=fake_fetch)
        patcher.start()
        self.addCleanup(patcher.stop)

        # The location type comes from a second endpoint; stubbed here so these
        # tests never reach the network.
        type_patcher = patch("api.exports.location_type", return_value="outdoor")
        type_patcher.start()
        self.addCleanup(type_patcher.stop)
        return captured

    def test_anonymous_request_is_rejected(self):
        response = self.client.get(self.url())
        self.assertIn(response.status_code, (401, 403))

    def rows_from(self, response):
        """The CSV body as dicts, the way a consumer would read it."""
        text = response.content.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))

    def test_returns_a_readable_csv(self):
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(len(self.rows_from(response)), 6)

    def test_columns_match_airgradients_own_export(self):
        """The whole point of this format: the two files must be interchangeable.

        Header text is asserted literally, including the Greek mu AirGradient
        uses in its unit labels, because a consumer keying on these names breaks
        on any drift.
        """
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        header = response.content.decode("utf-8-sig").split("\n", 1)[0]
        self.assertEqual(
            header,
            "Location ID,Location Name,Location Group,Location Type,Sensor ID,"
            "Place Open,Local Date/Time,UTC Date/Time,# of aggregated records,"
            "PM2.5 (μg/m³) raw,PM2.5 (μg/m³) corrected,0.3μm particle count,"
            "CO2 (ppm) raw,CO2 (ppm) corrected,Temperature (°C) raw,"
            "Temperature (°C) corrected,Heat Index (°C),Humidity (%) raw,"
            "Humidity (%) corrected,TVOC (ppb),TVOC index,NOX index,"
            "PM1 (μg/m³),PM10 (μg/m³)",
        )

    def test_body_starts_with_a_utf8_bom(self):
        """Without it Excel on Windows mangles the accented headers."""
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))

    def test_values_are_carried_across(self):
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        first = self.rows_from(response)[0]
        self.assertEqual(first["Location ID"], "191355")
        self.assertEqual(first["CO2 (ppm) raw"], "429")
        self.assertEqual(first["Temperature (°C) raw"], "13.5")
        self.assertEqual(first["Sensor ID"], "airgradient:588c813fe18c")
        self.assertEqual(first["PM2.5 (μg/m³) corrected"], "12.5")

    def test_whole_numbers_lose_their_decimal_point(self):
        """AirGradient writes CO2 as `429`, not `429.0`; a diff would flag ours."""
        self.stub(rows=[_measure(_at(self.july_days[0], 8), rco2=429.0)])
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        self.assertEqual(self.rows_from(response)[0]["CO2 (ppm) raw"], "429")

    def test_rows_are_newest_first(self):
        """AirGradient's export is descending; ours has to match to be swappable."""
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        stamps = [row["UTC Date/Time"] for row in self.rows_from(response)]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_columns_absent_from_the_api_are_left_empty(self):
        """Better an empty cell than a plausible-looking invention."""
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        first = self.rows_from(response)[0]
        for column in ("Location Group", "Place Open", "Heat Index (°C)"):
            self.assertEqual(first[column], "")

    def test_only_the_requested_range_is_fetched(self):
        """No warm-up window: the CSV carries no derived rolling values."""
        captured = self.stub()
        self.login()
        self.client.get(self.url(), {"from": "2026-07-02", "to": "2026-07-03"})

        requested = (captured["end"] - captured["start"]).total_seconds()
        self.assertAlmostEqual(requested / 3600, 48, places=3)

    def test_readings_outside_the_range_are_dropped(self):
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-02", "to": "2026-07-03"}
        )

        # July 1st's two readings were in the stub but are before the range.
        self.assertEqual(len(self.rows_from(response)), 4)

    def test_local_time_column_is_in_sensor_local_time(self):
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-01"}
        )

        first = self.rows_from(response)[0]
        # Seeded at 20:00 local; newest-first puts it in row one. A UTC leak
        # would render 23:00.
        self.assertTrue(first["Local Date/Time"].endswith("20:00:00"))
        self.assertEqual(first["UTC Date/Time"], "2026-07-01T23:00:00.000Z")

    def test_range_is_inclusive_of_the_end_day(self):
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-03", "to": "2026-07-03"}
        )
        self.assertEqual(len(self.rows_from(response)), 2)

    def test_defaults_to_the_whole_contract(self):
        self.stub()
        self.login()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.rows_from(response)), 6)

    def test_requests_the_stations_own_location(self):
        captured = self.stub()
        self.login()
        self.client.get(self.url(), {"from": "2026-07-01", "to": "2026-07-03"})

        self.assertEqual(captured["location_id"], 191355)

    def test_rejects_an_inverted_range(self):
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-03", "to": "2026-07-01"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("to", response.json())

    def test_rejects_a_malformed_date(self):
        self.login()
        response = self.client.get(self.url(), {"from": "01/07/2026"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("from", response.json())

    def test_institution_without_a_sensor_gets_404(self):
        self.drop_contract()
        self.login()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 404)

    def test_day_cap_is_enforced(self):
        from unittest.mock import patch

        self.login()
        with patch("api.exports.MAX_EXPORT_DAYS", 2):
            response = self.client.get(
                self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("from", response.json())

    def test_partial_export_is_flagged(self):
        """A file served with a gap says so instead of looking complete."""
        self.stub(failed_windows=2)
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Respira-Partial-Export"], "2")

    def test_complete_export_carries_no_partial_header(self):
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        self.assertNotIn("X-Respira-Partial-Export", response)

    def test_station_without_an_airgradient_code_is_reported_as_such(self):
        """A misconfigured station must not read as a passing outage.

        Telling somebody to "try again in a few minutes" when the station will
        never resolve sends them looking in the wrong place; this is the shape
        seeded demo data had, and it reached a browser before being caught.
        """
        self.station.station_code = "RSP-DEMO-01"
        self.station.update_for_tests()
        self.login()

        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("try again", str(response.json()).lower())

    def test_provider_failure_is_reported(self):
        from unittest.mock import patch

        from .airgradient import AirGradientError

        self.login()
        with patch(
            "api.exports.fetch_past_measures",
            side_effect=AirGradientError("no token"),
        ):
            response = self.client.get(
                self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_filename_carries_the_requested_range(self):
        self.stub()
        self.login()
        response = self.client.get(
            self.url(), {"from": "2026-07-01", "to": "2026-07-03"}
        )
        self.assertIn(
            "export_Respira:_Villa_Morra_2026-07-01_2026-07-03.csv",
            response["Content-Disposition"],
        )
