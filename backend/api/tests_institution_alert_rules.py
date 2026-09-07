"""Tests for the configurable institutional alerts (api.push).

What separates these from ``tests_sensor_alerts``: those cover the fixed AQI
level table applied to every station, these cover an institution's own
threshold and its own wording applied to its own sensor. The properties worth
holding onto are that the configured copy is what actually reaches the device,
that a threshold below the public alert levels still fires, and that a sensor
hovering at its threshold notifies once rather than on every run.

Expo is the only thing stubbed, as in the sibling module — the tests assert on
what would be sent.
"""

from datetime import date
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import InstitutionAlertRuleForm
from .models import (
    DeviceFollower,
    DeviceInstallation,
    Institution,
    InstitutionAlert,
    InstitutionAlertRule,
    InstitutionAlertRuleState,
    InstitutionContract,
    Regions,
    SensorAlert,
    StationReadingsGold,
    Stations,
)
from .push import rearm_threshold, rule_transition, send_institution_alerts

INSTALLATION_ID = "8f14e45f-ceea-467e-bd97-1a2b3c4d5e6f"
OTHER_INSTALLATION_ID = "2c1f9b4a-77d3-4e21-9a5c-6b0e8d3f1a2b"


def ok_tickets(messages):
    return {"data": [{"status": "ok", "id": f"tk-{i}"} for i in range(len(messages))]}


class Capture:
    """Stands in for Expo, recording what would have been sent."""

    def __init__(self):
        self.messages: list[dict] = []

    def __call__(self, messages):
        self.messages.extend(messages)
        return ok_tickets(messages)["data"]

    def recipients(self) -> list[str]:
        return [message["to"] for message in self.messages]


class RuleTransitionTests(TestCase):
    """The decision itself, apart from any delivery."""

    def test_crossing_the_threshold_fires(self):
        self.assertEqual(rule_transition(False, 41, 40), "fire")

    def test_sitting_at_the_threshold_does_not_fire(self):
        # Strictly above: a threshold of 40 means "worse than 40".
        self.assertIsNone(rule_transition(False, 40, 40))

    def test_a_firing_rule_does_not_fire_again(self):
        # The property that stops one episode notifying on every run.
        self.assertIsNone(rule_transition(True, 95, 40))

    def test_dropping_below_the_threshold_is_not_yet_a_rearm(self):
        # 39 is under the threshold but inside the band, so the rule stays
        # firing — otherwise 41/39/42 would be three separate alerts.
        self.assertIsNone(rule_transition(True, 39, 40))

    def test_falling_through_the_band_rearms(self):
        self.assertEqual(rule_transition(True, 34, 40), "rearm")

    def test_the_band_scales_with_the_threshold(self):
        self.assertAlmostEqual(rearm_threshold(40), 35.2)
        self.assertAlmostEqual(rearm_threshold(150), 132.0)


class SendInstitutionAlertsTests(TestCase):
    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Colegio San José",
            region=self.region,
            station_code="RSP-001",
            is_station_on=True,
        )
        self.other_station = Stations.seed_for_tests(
            name="Respira: San Lorenzo",
            region=self.region,
            station_code="RSP-002",
            is_station_on=True,
        )
        self.institution = Institution.objects.create(legal_name="Colegio San José")

    def _rule(self, station=None, threshold=40, **kwargs):
        return InstitutionAlertRule.objects.create(
            institution=self.institution,
            station=station or self.station,
            threshold=threshold,
            push_title=kwargs.pop("push_title", "Aire regular en el colegio"),
            push_body=kwargs.pop(
                "push_body", "El aire en {station} superó el umbral."
            ),
            **kwargs,
        )

    def _reading(self, station, aqi):
        return StationReadingsGold.seed_for_tests(
            station=station, date_utc=timezone.now(), aqi_pm2_5=aqi
        )

    def _follower(self, station_code, token, installation_id=INSTALLATION_ID):
        installation, _ = DeviceInstallation.register(installation_id, push_token=token)
        DeviceFollower.objects.create(
            installation=installation, station_code=station_code
        )
        return installation

    def test_the_configured_copy_is_what_reaches_the_device(self):
        # The point of the whole feature: the admin's wording, not LEVEL_COPY.
        self._rule(push_title="Recreo suspendido", push_body="Aire alto en {station}.")
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 55)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            send_institution_alerts()

        self.assertEqual(len(capture.messages), 1)
        self.assertEqual(capture.messages[0]["title"], "Recreo suspendido")
        self.assertEqual(
            capture.messages[0]["body"], "Aire alto en Colegio San José."
        )

    def test_a_threshold_below_the_public_alert_levels_still_fires(self):
        # AQI 45 is "good"/"moderate" territory, which the public path stays
        # deliberately quiet for. An institution may still want to be told.
        self._rule(threshold=40)
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 45)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            result = send_institution_alerts()

        self.assertEqual(result.alerted_stations, 1)
        self.assertEqual(len(capture.messages), 1)

    def test_only_the_followers_of_that_sensor_are_notified(self):
        self._rule()
        self._follower("RSP-001", "token-a")
        self._follower("RSP-002", "token-b", OTHER_INSTALLATION_ID)
        self._reading(self.station, 55)
        self._reading(self.other_station, 300)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            send_institution_alerts()

        self.assertEqual(capture.recipients(), ["token-a"])

    def test_an_episode_notifies_once_not_on_every_run(self):
        rule = self._rule(threshold=40)
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 55)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            send_institution_alerts()
            # Still over the threshold on the next run, and worse.
            self._reading(self.station, 70)
            send_institution_alerts()

        self.assertEqual(len(capture.messages), 1)
        self.assertTrue(InstitutionAlertRuleState.objects.get(rule=rule).is_firing)

    def test_the_rule_fires_again_after_the_air_recovers(self):
        self._rule(threshold=40)
        self._follower("RSP-001", "token-a")

        capture = Capture()
        with patch("api.push._post_batch", capture):
            self._reading(self.station, 55)
            send_institution_alerts()
            # Through the rearm band (below 35.2), then bad again.
            self._reading(self.station, 20)
            send_institution_alerts()
            self._reading(self.station, 60)
            send_institution_alerts()

        self.assertEqual(len(capture.messages), 2)

    def test_rearming_is_silent(self):
        self._rule(threshold=40)
        self._follower("RSP-001", "token-a")

        capture = Capture()
        with patch("api.push._post_batch", capture):
            self._reading(self.station, 55)
            send_institution_alerts()
            self._reading(self.station, 15)
            result = send_institution_alerts()

        # One warning, and no all-clear: the threshold is an operational
        # trigger, not a health level with a recovery message of its own.
        self.assertEqual(len(capture.messages), 1)
        self.assertEqual(result.alerted_stations, 0)

    def test_an_inactive_rule_is_skipped(self):
        self._rule(is_active=False)
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 300)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            result = send_institution_alerts()

        self.assertEqual(capture.messages, [])
        self.assertEqual(result.considered, 0)

    def test_firing_records_the_event_with_the_threshold_of_the_day(self):
        rule = self._rule(threshold=40)
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 55)

        with patch("api.push._post_batch", Capture()):
            send_institution_alerts()

        alert = InstitutionAlert.objects.get()
        self.assertEqual(alert.institution, self.institution)
        self.assertEqual(alert.aqi_value, 55)
        self.assertEqual(alert.alert_threshold, 40)

        # Editing the rule afterwards must not rewrite history.
        rule.threshold = 90
        rule.save(update_fields=["threshold"])
        alert.refresh_from_db()
        self.assertEqual(alert.alert_threshold, 40)

    def test_delivery_is_recorded_for_the_audit_trail(self):
        self._rule()
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 55)

        with patch("api.push._post_batch", Capture()):
            send_institution_alerts()

        self.assertEqual(SensorAlert.objects.get().recipients, 1)

    def test_a_station_the_pipeline_turned_off_is_skipped(self):
        off = Stations.seed_for_tests(
            name="Apagada",
            region=self.region,
            station_code="RSP-003",
            is_station_on=False,
        )
        self._rule(station=off)
        self._follower("RSP-003", "token-a")
        self._reading(off, 300)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            send_institution_alerts()

        self.assertEqual(capture.messages, [])

    def test_a_rejected_delivery_is_retried_rather_than_marked_sent(self):
        rule = self._rule()
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 55)

        def rejected(messages):
            return [
                {"status": "error", "message": "rate limited"} for _ in messages
            ]

        with patch("api.push._post_batch", rejected):
            result = send_institution_alerts()

        self.assertFalse(InstitutionAlertRuleState.objects.get(rule=rule).is_firing)
        self.assertEqual(result.alerted_stations, 0)
        self.assertTrue(result.errors)
        # Nothing was delivered, so nothing is claimed in the audit trail.
        self.assertFalse(InstitutionAlert.objects.exists())
        self.assertFalse(SensorAlert.objects.exists())

    def test_a_dead_token_is_cleared_without_failing_the_run(self):
        self._rule()
        self._follower("RSP-001", "token-a")
        self._follower("RSP-001", "token-b", OTHER_INSTALLATION_ID)
        self._reading(self.station, 55)

        def one_dead(messages):
            return [
                {"status": "ok", "id": "tk-0"},
                {
                    "status": "error",
                    "message": "gone",
                    "details": {"error": "DeviceNotRegistered"},
                },
            ]

        with patch("api.push._post_batch", one_dead):
            result = send_institution_alerts()

        self.assertEqual(result.alerted_stations, 1)
        self.assertEqual(result.tokens_cleared, 1)

    def test_a_dry_run_reports_without_sending(self):
        self._rule()
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 55)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            result = send_institution_alerts(dry_run=True)

        self.assertEqual(capture.messages, [])
        self.assertEqual(result.alerted_stations, 1)
        self.assertFalse(InstitutionAlertRuleState.objects.exists())

    def test_a_stray_brace_in_the_message_does_not_break_delivery(self):
        self._rule(push_body="Retiro a las {hora} en {station}.")
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 55)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            send_institution_alerts()

        self.assertEqual(
            capture.messages[0]["body"],
            "Retiro a las {hora} en Colegio San José.",
        )


class AlertRuleFormTests(TestCase):
    """The station is derived from the institution, never chosen."""

    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Colegio San José",
            region=self.region,
            station_code="RSP-001",
            is_station_on=True,
        )
        self.institution = Institution.objects.create(legal_name="Colegio San José")
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            start_date=date(2026, 1, 1),
        )

    def _data(self, **kwargs):
        return {
            "institution": self.institution.pk,
            "threshold": 40,
            "push_title": "Aire regular",
            "push_body": "El aire en {station} superó el umbral.",
            "is_active": True,
            **kwargs,
        }

    def test_the_station_is_filled_in_from_the_contract(self):
        form = InstitutionAlertRuleForm(self._data())
        self.assertTrue(form.is_valid(), form.errors)
        rule = form.save()
        self.assertEqual(rule.station, self.station)

    def test_the_picker_offers_only_the_contracted_sensor(self):
        # What the operator sees: one institution, one sensor. The queryset is
        # also what a posted value is validated against.
        Stations.seed_for_tests(
            name="Otra", region=self.region, station_code="RSP-002"
        )
        form = InstitutionAlertRuleForm(self._data())
        self.assertEqual(
            list(form.fields["station"].queryset), [self.station]
        )

    def test_the_picker_is_empty_until_an_institution_is_chosen(self):
        # An empty list says "pick an institution first" rather than inviting a
        # choice that would have to be rejected.
        self.assertEqual(list(InstitutionAlertRuleForm().fields["station"].queryset), [])

    def test_another_institutions_sensor_is_rejected(self):
        # The narrowing is enforcement, not only presentation: forcing a
        # foreign station id into the POST does not get past the field.
        other = Stations.seed_for_tests(
            name="Otra", region=self.region, station_code="RSP-002"
        )
        InstitutionContract.objects.create(
            institution=Institution.objects.create(legal_name="Otra institución"),
            station=other,
            start_date=date(2026, 1, 1),
        )
        form = InstitutionAlertRuleForm(self._data(station=other.pk))
        self.assertFalse(form.is_valid())
        self.assertIn("station", form.errors)

    def test_a_blank_station_resolves_to_the_contracted_one(self):
        # The ordinary path with scripting off: there is only one valid answer,
        # so the operator is not made to select it.
        form = InstitutionAlertRuleForm(self._data(station=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().station, self.station)

    def test_an_institution_without_a_contract_is_refused(self):
        orphan = Institution.objects.create(legal_name="Sin contrato")
        form = InstitutionAlertRuleForm(self._data(institution=orphan.pk))
        self.assertFalse(form.is_valid())
        self.assertIn("institution", form.errors)


class ContractedStationLookupTests(TestCase):
    """The JSON the station select is repopulated from."""

    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Colegio San José", region=self.region, station_code="RSP-001"
        )
        self.institution = Institution.objects.create(legal_name="Colegio San José")
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            start_date=date(2026, 1, 1),
        )
        self.url = reverse("admin:api_institutionalertrule_contracted_station")

    def test_it_returns_the_contracted_station(self):
        user = get_user_model().objects.create_superuser(
            email="admin@example.com", password="x"
        )
        self.client.force_login(user)

        response = self.client.get(self.url, {"institution": self.institution.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["station"],
            {"id": self.station.id, "name": "Colegio San José"},
        )

    def test_an_institution_without_a_contract_returns_null(self):
        user = get_user_model().objects.create_superuser(
            email="admin2@example.com", password="x"
        )
        self.client.force_login(user)
        orphan = Institution.objects.create(legal_name="Sin contrato")

        response = self.client.get(self.url, {"institution": orphan.pk})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["station"])

    def test_it_is_behind_the_admin_login(self):
        # Which sensor an institution leases is not public information.
        response = self.client.get(self.url, {"institution": self.institution.pk})
        self.assertNotEqual(response.status_code, 200)


class EvaluateOnSaveTests(TestCase):
    """Configuring an alert for air that is already bad notifies now.

    The scheduled sender reacts to readings changing, so without this a rule
    created mid-episode would stay silent until the next run — about air that
    is already over its threshold.
    """

    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Colegio San José",
            region=self.region,
            station_code="RSP-001",
            is_station_on=True,
        )
        self.institution = Institution.objects.create(legal_name="Colegio San José")
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            start_date=date(2026, 1, 1),
        )
        installation, _ = DeviceInstallation.register(
            INSTALLATION_ID, push_token="token-a"
        )
        DeviceFollower.objects.create(
            installation=installation, station_code="RSP-001"
        )
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com", password="x"
        )
        self.client.force_login(self.user)
        self.url = reverse("admin:api_institutionalertrule_add")

    def _reading(self, aqi):
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=timezone.now(), aqi_pm2_5=aqi
        )

    def _post(self, url, follow=False, **overrides):
        data = {
            "institution": self.institution.pk,
            "station": self.station.pk,
            "threshold": 13,
            "push_title": "Aire regular",
            "push_body": "El aire en {station} superó el umbral.",
            "is_active": "on",
            "_save": "Save",
            # The history inline the change form renders.
            "events-TOTAL_FORMS": "0",
            "events-INITIAL_FORMS": "0",
            "events-MIN_NUM_FORMS": "0",
            "events-MAX_NUM_FORMS": "0",
            **overrides,
        }
        return self.client.post(url, data, follow=follow)

    @override_settings(SENSOR_ALERTS_ENABLED=True)
    def test_creating_an_alert_for_air_already_over_it_notifies_now(self):
        self._reading(15)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            self._post(self.url)

        self.assertEqual(len(capture.messages), 1)
        self.assertEqual(capture.messages[0]["to"], "token-a")

    @override_settings(SENSOR_ALERTS_ENABLED=True)
    def test_creating_an_alert_for_clean_air_notifies_nobody(self):
        self._reading(5)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            self._post(self.url)

        self.assertEqual(capture.messages, [])

    @override_settings(SENSOR_ALERTS_ENABLED=True)
    def test_editing_the_wording_does_not_notify(self):
        # Fixing a typo must not interrupt anybody.
        self._reading(15)
        rule = InstitutionAlertRule.objects.create(
            institution=self.institution,
            station=self.station,
            threshold=13,
            push_title="Aire regular",
            push_body="Original.",
        )
        url = reverse("admin:api_institutionalertrule_change", args=[rule.pk])

        capture = Capture()
        with patch("api.push._post_batch", capture):
            self._post(url, push_body="Corregido.")

        self.assertEqual(capture.messages, [])

    @override_settings(SENSOR_ALERTS_ENABLED=True)
    def test_lowering_the_threshold_notifies(self):
        # "I want to hear about this sooner" should take effect now.
        self._reading(15)
        rule = InstitutionAlertRule.objects.create(
            institution=self.institution,
            station=self.station,
            threshold=90,
            push_title="Aire regular",
            push_body="Cuerpo.",
        )
        url = reverse("admin:api_institutionalertrule_change", args=[rule.pk])

        capture = Capture()
        with patch("api.push._post_batch", capture):
            self._post(url, threshold=13)

        self.assertEqual(len(capture.messages), 1)

    @override_settings(SENSOR_ALERTS_ENABLED=True)
    def test_raising_the_threshold_does_not_notify(self):
        self._reading(15)
        rule = InstitutionAlertRule.objects.create(
            institution=self.institution,
            station=self.station,
            threshold=13,
            push_title="Aire regular",
            push_body="Cuerpo.",
        )
        url = reverse("admin:api_institutionalertrule_change", args=[rule.pk])

        capture = Capture()
        with patch("api.push._post_batch", capture):
            self._post(url, threshold=200)

        self.assertEqual(capture.messages, [])

    @override_settings(SENSOR_ALERTS_ENABLED=True)
    def test_the_alert_is_saved_even_when_delivery_fails(self):
        # Configuration must not be lost because the push service is down.
        self._reading(15)

        def down(messages):
            raise requests.RequestException("connection reset")

        with patch("api.push._post_batch", down):
            self._post(self.url)

        self.assertEqual(InstitutionAlertRule.objects.count(), 1)

    @override_settings(SENSOR_ALERTS_ENABLED=False)
    def test_nothing_is_sent_when_alerts_are_disabled(self):
        # Pinned rather than relying on the default: the setting is read from
        # the environment, so a developer with alerts switched on locally would
        # otherwise see this test fail for a reason that is not about the code.
        self._reading(15)

        capture = Capture()
        with patch("api.push._post_batch", capture):
            response = self._post(self.url, follow=True)

        self.assertEqual(capture.messages, [])
        self.assertEqual(InstitutionAlertRule.objects.count(), 1)
        # And says so: an alert saved for air already over its threshold, then
        # sitting at "Idle" with no explanation, reads as a broken feature.
        self.assertContains(response, "switched off in this environment")
