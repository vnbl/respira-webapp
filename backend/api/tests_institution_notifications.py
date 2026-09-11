"""Tests for the sensor notifications feed (/api/institution/notifications/).

The endpoint merges two tables an institution experiences as one thing: the
AQI-triggered `InstitutionAlert` rows its rules fired, and the manually sent
`PushBroadcast` announcements. So the tests cover the merge itself — one ordered
feed, both kinds rendered correctly, AQI fields null where they do not apply —
alongside the scoping boundary, which is the promise the dashboard section makes:
an institution sees notifications about its own sensor and nothing else.
"""

from datetime import date, datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .models import (
    Institution,
    InstitutionAlert,
    InstitutionAlertRule,
    InstitutionContract,
    InstitutionUser,
    PushBroadcast,
    Regions,
    Stations,
)

User = get_user_model()


def _at(day, hour=12):
    return datetime(2026, 8, day, hour, tzinfo=dt_timezone.utc)


class InstitutionNotificationsTests(APITestCase):
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

        self.other_institution = Institution.objects.create(legal_name="Colegio Otro")

    # --- helpers ------------------------------------------------------------

    def url(self):
        return reverse("institution-notifications")

    def login(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def results(self, response):
        payload = response.json()
        return payload["results"] if isinstance(payload, dict) else payload

    def rule(self, institution=None, threshold=100, **kwargs):
        return InstitutionAlertRule.objects.create(
            institution=institution or self.institution,
            station=kwargs.pop("station", self.station),
            threshold=threshold,
            push_title=kwargs.pop("push_title", "Aire insalubre"),
            push_body=kwargs.pop("push_body", "El sensor {station} superó el umbral."),
            **kwargs,
        )

    def alert(self, institution=None, **kwargs):
        kwargs.setdefault("station", self.station)
        kwargs.setdefault("aqi_value", 137.0)
        kwargs.setdefault("alert_threshold", 100)
        kwargs.setdefault("triggered_at", _at(22))
        return InstitutionAlert.objects.create(
            institution=institution or self.institution, **kwargs
        )

    def broadcast(self, institution=None, **kwargs):
        kwargs.setdefault("scope", PushBroadcast.SCOPE_STATION)
        kwargs.setdefault("station", self.station)
        kwargs.setdefault("push_title", "Mantenimiento del sensor")
        kwargs.setdefault("push_body", "El martes no habrá lecturas.")
        return PushBroadcast.objects.create(
            institution=institution or self.institution, **kwargs
        )

    def broadcast_at(self, when, **kwargs):
        """A broadcast stamped at ``when``.

        Written and then updated because ``sent_at`` is ``auto_now_add``: the
        model stamps it on insert and ignores anything passed in, so a test that
        needs a specific instant has to set it afterwards.
        """
        broadcast = self.broadcast(**kwargs)
        PushBroadcast.objects.filter(pk=broadcast.pk).update(sent_at=when)
        broadcast.refresh_from_db()
        return broadcast

    # --- authorization ------------------------------------------------------

    def test_anonymous_request_is_rejected(self):
        self.assertIn(self.client.get(self.url()).status_code, (401, 403))

    def test_user_without_institution_is_rejected(self):
        outsider = User.objects.create_user(
            email="nadie@example.test", password="Respira.Test.2026"
        )
        self.login(outsider)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_another_institutions_notifications_never_surface(self):
        """The boundary the section promises: own sensor only, both kinds."""
        self.alert(
            institution=self.other_institution,
            station=self.other_station,
            aqi_value=500.0,
        )
        self.broadcast_at(
            _at(23),
            institution=self.other_institution,
            station=self.other_station,
            push_title="Aviso de otro colegio",
        )
        mine = self.alert()

        self.login()
        results = self.results(self.client.get(self.url()))

        self.assertEqual([row["id"] for row in results], [f"alert-{mine.id}"])
        self.assertNotIn(500.0, [row["aqi"] for row in results])
        self.assertNotIn("Aviso de otro colegio", [row["title"] for row in results])

    def test_is_read_only(self):
        self.login()
        self.assertIn(self.client.post(self.url(), {}).status_code, (403, 405))
        self.assertIn(self.client.put(self.url(), {}).status_code, (403, 405))
        self.assertIn(self.client.delete(self.url()).status_code, (403, 405))

    # --- the merge ----------------------------------------------------------

    def test_merges_both_kinds_newest_first(self):
        """The point of the endpoint: one feed, ordered across both tables."""
        oldest = self.alert(triggered_at=_at(10))
        middle = self.broadcast_at(_at(15))
        newest = self.alert(triggered_at=_at(20), aqi_value=155.0)

        self.login()
        results = self.results(self.client.get(self.url()))

        self.assertEqual(
            [row["id"] for row in results],
            [f"alert-{newest.id}", f"broadcast-{middle.id}", f"alert-{oldest.id}"],
        )

    def test_is_paginated(self):
        """The feed grows for as long as the sensor is leased, so it is cut.

        Also pins the response *shape*: the panel reads `results`/`next`, and
        this action opting into pagination is what produces them — the rest of
        the viewset answers bare lists.
        """
        for day in range(1, 26):
            self.alert(triggered_at=_at(day))

        self.login()
        payload = self.client.get(self.url()).json()

        self.assertEqual(payload["count"], 25)
        self.assertEqual(len(payload["results"]), 20)
        self.assertIsNotNone(payload["next"])

        # Page two continues the same ordering rather than restarting it.
        second = self.client.get(self.url(), {"page": 2}).json()
        self.assertEqual(len(second["results"]), 5)
        self.assertNotIn(
            second["results"][0]["id"], [row["id"] for row in payload["results"]]
        )

    def test_other_institution_routes_are_not_paginated(self):
        """`pagination_class` is set on the action, not on the viewset."""
        self.login()
        self.assertIsInstance(
            self.client.get(reverse("institution-alerts")).json(), list
        )

    def test_empty_when_the_sensor_has_no_notifications(self):
        self.login()
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.results(response), [])

    # --- AQI notifications --------------------------------------------------

    def test_aqi_notification_carries_its_reading_and_rule_copy(self):
        rule = self.rule()
        self.alert(rule=rule, aqi_value=137.0, alert_threshold=100)

        self.login()
        (row,) = self.results(self.client.get(self.url()))

        self.assertEqual(row["type"], "aqi")
        self.assertEqual(row["title"], "Aire insalubre")
        # `{station}` is resolved from the station, as the sender resolves it.
        self.assertEqual(
            row["body"], "El sensor Respira: Villa Morra superó el umbral."
        )
        self.assertEqual(row["aqi"], 137.0)
        self.assertEqual(row["aqi_category"], "unhealthy_sensitive")
        self.assertEqual(row["alert_threshold"], 100)
        self.assertEqual(row["station_name"], "Respira: Villa Morra")

    def test_aqi_notification_without_a_rule_falls_back_to_the_level(self):
        """`rule` is SET_NULL, so events outlive the rule that produced them."""
        self.alert(rule=None, aqi_value=137.0)

        self.login()
        (row,) = self.results(self.client.get(self.url()))

        self.assertEqual(row["type"], "aqi")
        self.assertEqual(row["title"], "INSALUBRE PARA GRUPOS SENSIBLES")
        self.assertTrue(row["body"])
        self.assertEqual(row["aqi_category"], "unhealthy_sensitive")

    def test_aqi_notification_links_back_to_its_alert(self):
        """So a client can tie it to the alert an ActionLog responds to."""
        alert = self.alert()

        self.login()
        (row,) = self.results(self.client.get(self.url()))

        self.assertEqual(row["alert"], alert.id)

    # --- general notifications ---------------------------------------------

    def test_general_notification_renders_with_no_aqi_at_all(self):
        """A manual announcement has no reading behind it — every AQI field null."""
        self.broadcast()

        self.login()
        (row,) = self.results(self.client.get(self.url()))

        self.assertEqual(row["type"], "general")
        self.assertEqual(row["title"], "Mantenimiento del sensor")
        self.assertEqual(row["body"], "El martes no habrá lecturas.")
        self.assertIsNone(row["aqi"])
        self.assertIsNone(row["aqi_category"])
        self.assertIsNone(row["alert_threshold"])
        self.assertIsNone(row["alert"])

    def test_institution_scoped_broadcast_is_included_without_a_station(self):
        self.broadcast(scope=PushBroadcast.SCOPE_INSTITUTION, station=None)

        self.login()
        (row,) = self.results(self.client.get(self.url()))

        self.assertEqual(row["type"], "general")
        self.assertIsNone(row["station"])
        self.assertIsNone(row["station_name"])

    def test_platform_wide_broadcasts_are_excluded(self):
        """`scope="all"` is an announcement to everyone, not about this sensor."""
        PushBroadcast.objects.create(
            scope=PushBroadcast.SCOPE_ALL,
            institution=None,
            push_title="Respira cumple un año",
            push_body="Gracias por acompañarnos.",
        )

        self.login()
        self.assertEqual(self.results(self.client.get(self.url())), [])
