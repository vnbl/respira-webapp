"""Tests for the institutional alerts feed (/api/institution/alerts/).

The endpoint exists so a client can populate "which alert does this action
respond to?" — `ActionLog.alert` is writable, and without a way to discover a
valid id the field is unusable from a browser. So the tests cover both the
scoping boundary and the contract the action form depends on: the alert's
station, its AQI and the threshold in force when it fired.
"""

from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import (
    ActionLog,
    Institution,
    InstitutionAlert,
    InstitutionContract,
    InstitutionUser,
    Regions,
    Stations,
)

User = get_user_model()


class InstitutionAlertsTests(APITestCase):
    def setUp(self):
        self.client = APIClient()

        region = Regions.seed_for_tests(name="Gran Asuncion", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra", region=region, is_station_on=True
        )
        self.other_station = Stations.seed_for_tests(
            name="Respira: Sajonia", region=region, is_station_on=True
        )

        self.institution = Institution.objects.create(legal_name="Hospital Bautista")
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            contract_status=InstitutionContract.ContractStatus.ACTIVE,
            start_date=date(2026, 1, 1),
        )
        self.user = User.objects.create_user(
            email="contacto@bautista.test", password="Respira.Test.2026"
        )
        InstitutionUser.objects.create(user=self.user, institution=self.institution)

        # Another institution's alert, which must never surface here.
        self.other_institution = Institution.objects.create(legal_name="Colegio Otro")
        InstitutionAlert.objects.create(
            institution=self.other_institution,
            station=self.other_station,
            aqi_value=500.0,
            triggered_at=timezone.now(),
        )

        self.older = InstitutionAlert.objects.create(
            institution=self.institution,
            station=self.station,
            aqi_value=118.0,
            alert_threshold=100,
            triggered_at=datetime(2026, 8, 11, 12, tzinfo=dt_timezone.utc),
            resolved_at=datetime(2026, 8, 11, 20, tzinfo=dt_timezone.utc),
        )
        self.newer = InstitutionAlert.objects.create(
            institution=self.institution,
            station=self.station,
            aqi_value=137.0,
            alert_threshold=100,
            triggered_at=datetime(2026, 8, 22, 14, tzinfo=dt_timezone.utc),
        )

    def url(self):
        return reverse("institution-alerts")

    def login(self):
        self.client.force_authenticate(user=User.objects.get(pk=self.user.pk))

    def results(self, response):
        payload = response.json()
        return payload["results"] if isinstance(payload, dict) else payload

    def test_anonymous_request_is_rejected(self):
        response = self.client.get(self.url())
        self.assertIn(response.status_code, (401, 403))

    def test_user_without_institution_is_rejected(self):
        outsider = User.objects.create_user(
            email="nadie@example.test", password="Respira.Test.2026"
        )
        self.client.force_authenticate(user=outsider)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_lists_only_the_callers_own_alerts_newest_first(self):
        self.login()
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        results = self.results(response)
        self.assertEqual([row["id"] for row in results], [self.newer.id, self.older.id])
        # The other institution's 500 would be here if the queryset leaked.
        self.assertNotIn(500.0, [row["aqi_value"] for row in results])

    def test_carries_the_fields_the_action_form_needs(self):
        self.login()
        first = self.results(self.client.get(self.url()))[0]

        self.assertEqual(first["station"], self.station.id)
        self.assertEqual(first["station_name"], "Respira: Villa Morra")
        self.assertEqual(first["aqi_value"], 137.0)
        self.assertEqual(first["alert_threshold"], 100)
        self.assertIn("triggered_at", first)

    def test_is_resolved_reflects_resolved_at(self):
        self.login()
        by_id = {row["id"]: row for row in self.results(self.client.get(self.url()))}

        self.assertTrue(by_id[self.older.id]["is_resolved"])
        self.assertFalse(by_id[self.newer.id]["is_resolved"])

    def test_endpoint_is_read_only(self):
        self.login()
        response = self.client.post(
            self.url(), {"aqi_value": 10, "station": self.station.id}, format="json"
        )
        self.assertEqual(response.status_code, 405)

    def test_alerts_is_not_read_as_an_institution_pk(self):
        """The router maps `institution/<pk>/`; the action must win over it."""
        self.login()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("legal_name", str(response.content))


class ActionLogAlertDetailTests(InstitutionAlertsTests):
    """`alert_detail` lets a list of actions name the event each one answered."""

    def test_action_expands_its_alert(self):
        action = ActionLog.objects.create(
            institution=self.institution,
            station=self.station,
            alert=self.newer,
            note="Se suspendió el recreo al aire libre.",
        )
        self.login()

        response = self.client.get(reverse("action-logs-list"))
        self.assertEqual(response.status_code, 200)

        row = next(r for r in response.json()["results"] if r["id"] == action.id)
        self.assertEqual(row["alert"], self.newer.id)
        self.assertEqual(row["alert_detail"]["aqi_value"], 137.0)
        self.assertEqual(row["alert_detail"]["alert_threshold"], 100)

    def test_action_without_an_alert_has_a_null_detail(self):
        ActionLog.objects.create(
            institution=self.institution,
            station=self.station,
            note="Se instalaron cortinas de aire.",
        )
        self.login()

        row = self.client.get(reverse("action-logs-list")).json()["results"][0]
        self.assertIsNone(row["alert"])
        self.assertIsNone(row["alert_detail"])

    def test_alert_detail_is_read_only(self):
        """Posting it must not create or alter an alert."""
        self.login()
        before = InstitutionAlert.objects.count()

        response = self.client.post(
            reverse("action-logs-list"),
            {
                "station": self.station.id,
                "note": "Nota con detalle inventado.",
                "alert_detail": {"id": 999, "aqi_value": 1.0},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()["alert_detail"])
        self.assertEqual(InstitutionAlert.objects.count(), before)


class MonthlyReportActionsTests(InstitutionAlertsTests):
    """The month's actions belong in the monthly report, next to the readings."""

    def test_month_actions_are_scoped_and_bounded(self):
        from .exports import _month_actions

        inside = ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Dentro del mes."
        )
        ActionLog.objects.filter(pk=inside.pk).update(
            timestamp=datetime(2026, 8, 12, 10, tzinfo=dt_timezone.utc)
        )

        outside = ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Mes siguiente."
        )
        ActionLog.objects.filter(pk=outside.pk).update(
            timestamp=datetime(2026, 9, 2, 10, tzinfo=dt_timezone.utc)
        )

        other = ActionLog.objects.create(
            institution=self.other_institution,
            station=self.other_station,
            note="De otra institución.",
        )
        ActionLog.objects.filter(pk=other.pk).update(
            timestamp=datetime(2026, 8, 12, 11, tzinfo=dt_timezone.utc)
        )

        actions = _month_actions(self.institution, date(2026, 8, 1))

        self.assertEqual([a.note for a in actions], ["Dentro del mes."])

    def test_report_carries_the_action_text_and_its_alert(self):
        """Asserting the bytes, not just that a PDF came back.

        reportlab compresses page streams by default, which makes the text
        unsearchable; turning that off for the length of the test is what lets
        the assertion look at what the document actually says.
        """
        from reportlab import rl_config

        from .exports import (
            _month_actions,
            _month_statistics,
            build_monthly_report_pdf,
        )

        action = ActionLog.objects.create(
            institution=self.institution,
            station=self.station,
            alert=self.newer,
            note="Se suspendio el recreo al aire libre.",
        )
        ActionLog.objects.filter(pk=action.pk).update(
            timestamp=datetime(2026, 8, 23, 10, tzinfo=dt_timezone.utc)
        )

        month = date(2026, 8, 1)
        stats = _month_statistics(self.station.id, month)
        actions = _month_actions(self.institution, month)

        previous = rl_config.pageCompression
        rl_config.pageCompression = 0
        try:
            pdf = build_monthly_report_pdf(
                self.institution, self.institution.contract, stats, 100, actions
            )
        finally:
            rl_config.pageCompression = previous

        body = pdf.decode("latin-1")
        self.assertIn("Acciones registradas", body)
        self.assertIn("recreo", body)
        # The alert the action answered, by the AQI that triggered it.
        self.assertIn("AQI 137", body)

    def test_report_renders_with_actions_and_no_readings(self):
        """No readings does not mean nothing happened."""
        ActionLog.objects.create(
            institution=self.institution,
            station=self.station,
            alert=self.newer,
            note="Se avisó a las familias.",
        )
        self.login()

        month = (timezone.now().date().replace(day=1) - timedelta(days=1)).strftime(
            "%Y-%m"
        )
        response = self.client.get(
            reverse("institution-monthly-report"), {"month": month}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))
