"""Tests for the manual push broadcasts (api.push, api.forms).

The properties worth holding onto: a broadcast reaches exactly the audience its
scope names and nobody else, somebody following several of an institution's
sensors receives it once rather than once per sensor, and a platform-wide send
is gated behind a permission of its own.
"""

from datetime import date
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import PushBroadcastForm
from .models import (
    DeviceFollower,
    DeviceInstallation,
    Institution,
    InstitutionContract,
    PushBroadcast,
    Regions,
    Stations,
)
from .push import broadcast_tokens, send_broadcast

User = get_user_model()

INSTALLATION_A = "8f14e45f-ceea-467e-bd97-1a2b3c4d5e6f"
INSTALLATION_B = "2c1f9b4a-77d3-4e21-9a5c-6b0e8d3f1a2b"
INSTALLATION_C = "5d2e7a13-90bc-4f88-a1e3-7c4d9b6e2f01"


def ok_tickets(messages):
    return [{"status": "ok", "id": f"tk-{i}"} for i in range(len(messages))]


class Capture:
    def __init__(self):
        self.messages: list[dict] = []

    def __call__(self, messages):
        self.messages.extend(messages)
        return ok_tickets(messages)

    def recipients(self) -> list[str]:
        return sorted(message["to"] for message in self.messages)


class BroadcastAudienceTests(TestCase):
    """Who a broadcast reaches, which is the property that matters most."""

    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station_a = Stations.seed_for_tests(
            name="Colegio — patio",
            region=self.region,
            station_code="RSP-001",
            is_station_on=True,
        )
        self.station_b = Stations.seed_for_tests(
            name="Colegio — aula",
            region=self.region,
            station_code="RSP-002",
            is_station_on=True,
        )
        self.unrelated = Stations.seed_for_tests(
            name="Otra institución",
            region=self.region,
            station_code="RSP-003",
            is_station_on=True,
        )
        self.institution = Institution.objects.create(legal_name="Colegio San José")
        # Only `station_a` is under contract; `station_b` is deliberately left
        # out so institution scope is proven to follow contracts, not names.
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station_a,
            start_date=date(2026, 1, 1),
        )

    def _follower(self, installation_id, token, *station_codes):
        installation, _ = DeviceInstallation.register(installation_id, push_token=token)
        for code in station_codes:
            DeviceFollower.objects.create(installation=installation, station_code=code)
        return installation

    def _broadcast(self, scope, **kwargs):
        return PushBroadcast.objects.create(
            scope=scope, push_title="Aviso", push_body="Mensaje.", **kwargs
        )

    def test_station_scope_reaches_only_that_station(self):
        self._follower(INSTALLATION_A, "token-a", "RSP-001")
        self._follower(INSTALLATION_B, "token-b", "RSP-003")

        broadcast = self._broadcast(PushBroadcast.SCOPE_STATION, station=self.station_a)
        self.assertEqual(broadcast_tokens(broadcast), ["token-a"])

    def test_institution_scope_follows_the_contract(self):
        self._follower(INSTALLATION_A, "token-a", "RSP-001")
        # Follows a station of the same institution by name only — no contract,
        # so it is not part of the institution's audience.
        self._follower(INSTALLATION_B, "token-b", "RSP-002")

        broadcast = self._broadcast(
            PushBroadcast.SCOPE_INSTITUTION, institution=self.institution
        )
        self.assertEqual(broadcast_tokens(broadcast), ["token-a"])

    def test_a_device_following_several_stations_is_listed_once(self):
        # The reason deduplication exists: one person, one announcement.
        InstitutionContract.objects.create(
            institution=Institution.objects.create(legal_name="Otra"),
            station=self.station_b,
            start_date=date(2026, 1, 1),
        )
        self._follower(INSTALLATION_A, "token-a", "RSP-001", "RSP-002", "RSP-003")

        broadcast = self._broadcast(PushBroadcast.SCOPE_ALL)
        self.assertEqual(broadcast_tokens(broadcast), ["token-a"])

    def test_all_scope_reaches_every_follower(self):
        self._follower(INSTALLATION_A, "token-a", "RSP-001")
        self._follower(INSTALLATION_B, "token-b", "RSP-003")

        broadcast = self._broadcast(PushBroadcast.SCOPE_ALL)
        self.assertEqual(sorted(broadcast_tokens(broadcast)), ["token-a", "token-b"])

    def test_an_installation_following_nothing_is_not_reached(self):
        # Registered the app but never followed a sensor: no relationship to
        # any station, so a platform announcement is not theirs to receive.
        DeviceInstallation.register(INSTALLATION_C, push_token="token-c")
        self._follower(INSTALLATION_A, "token-a", "RSP-001")

        broadcast = self._broadcast(PushBroadcast.SCOPE_ALL)
        self.assertEqual(broadcast_tokens(broadcast), ["token-a"])

    def test_an_installation_without_a_token_is_skipped(self):
        self._follower(INSTALLATION_A, "", "RSP-001")

        broadcast = self._broadcast(PushBroadcast.SCOPE_STATION, station=self.station_a)
        self.assertEqual(broadcast_tokens(broadcast), [])


class SendBroadcastTests(TestCase):
    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Colegio San José",
            region=self.region,
            station_code="RSP-001",
            is_station_on=True,
        )

    def _follower(self, installation_id, token):
        installation, _ = DeviceInstallation.register(installation_id, push_token=token)
        DeviceFollower.objects.create(installation=installation, station_code="RSP-001")
        return installation

    def _broadcast(self, **kwargs):
        return PushBroadcast.objects.create(
            scope=PushBroadcast.SCOPE_STATION,
            station=self.station,
            push_title=kwargs.pop("push_title", "No hay clases"),
            push_body=kwargs.pop("push_body", "Mañana no hay clases."),
            **kwargs,
        )

    def test_the_composed_text_is_what_is_sent(self):
        self._follower(INSTALLATION_A, "token-a")
        broadcast = self._broadcast(
            push_title="Mantenimiento", push_body="El sensor estará fuera de línea."
        )

        capture = Capture()
        with patch("api.push._post_batch", capture):
            send_broadcast(broadcast)

        self.assertEqual(capture.messages[0]["title"], "Mantenimiento")
        self.assertEqual(
            capture.messages[0]["body"], "El sensor estará fuera de línea."
        )

    def test_the_payload_uses_a_type_the_app_already_understands(self):
        # Regression: a `broadcast` type was silently suppressed in the
        # foreground, because the app maps any type it does not recognise to
        # `unknown` and declines to present it. `forecast` is a type the
        # shipped app knows, so the announcement is actually shown.
        #
        # Not `sensor_alert`, which would route a tap to a single station's
        # screen that an announcement may not be about.
        self._follower(INSTALLATION_A, "token-a")
        broadcast = self._broadcast()

        capture = Capture()
        with patch("api.push._post_batch", capture):
            send_broadcast(broadcast)

        data = capture.messages[0]["data"]
        self.assertEqual(data["screen"], "forecast")
        # The app reads `screen` only when there is no `type` at all, so
        # setting one — even "forecast" — puts the payload back in the
        # suppressed `unknown` branch.
        self.assertNotIn("type", data)

    def test_the_delivery_count_is_recorded(self):
        self._follower(INSTALLATION_A, "token-a")
        self._follower(INSTALLATION_B, "token-b")
        broadcast = self._broadcast()

        with patch("api.push._post_batch", Capture()):
            send_broadcast(broadcast)

        broadcast.refresh_from_db()
        self.assertEqual(broadcast.recipients, 2)
        self.assertEqual(broadcast.failures, 0)

    def test_a_dead_token_is_cleared_without_failing_the_send(self):
        self._follower(INSTALLATION_A, "token-a")
        self._follower(INSTALLATION_B, "token-b")
        broadcast = self._broadcast()

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
            delivery = send_broadcast(broadcast)

        self.assertEqual(delivery.accepted, 1)
        self.assertEqual(delivery.cleared, 1)

    def test_a_network_failure_is_recorded_rather_than_raised(self):
        # Raising would lose the batches already delivered, and retrying the
        # whole broadcast would re-notify everyone the first attempt reached.
        self._follower(INSTALLATION_A, "token-a")
        broadcast = self._broadcast()

        def down(messages):
            raise requests.RequestException("connection reset")

        with patch("api.push._post_batch", down):
            delivery = send_broadcast(broadcast)

        self.assertEqual(delivery.accepted, 0)
        self.assertEqual(delivery.retriable_failures, 1)
        broadcast.refresh_from_db()
        self.assertEqual(broadcast.failures, 1)

    def test_an_audience_of_nobody_sends_nothing(self):
        broadcast = self._broadcast()

        capture = Capture()
        with patch("api.push._post_batch", capture):
            delivery = send_broadcast(broadcast)

        self.assertEqual(capture.messages, [])
        self.assertEqual(delivery.accepted, 0)


class PushBroadcastFormTests(TestCase):
    """The scope decides which field is required — checked, not hidden."""

    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Colegio", region=self.region, station_code="RSP-001"
        )
        self.institution = Institution.objects.create(legal_name="Colegio San José")

    def _data(self, **kwargs):
        return {"push_title": "Aviso", "push_body": "Mensaje.", **kwargs}

    def test_station_scope_requires_a_station(self):
        form = PushBroadcastForm(self._data(scope=PushBroadcast.SCOPE_STATION))
        self.assertFalse(form.is_valid())
        self.assertIn("station", form.errors)

    def test_institution_scope_requires_an_institution(self):
        form = PushBroadcastForm(self._data(scope=PushBroadcast.SCOPE_INSTITUTION))
        self.assertFalse(form.is_valid())
        self.assertIn("institution", form.errors)

    def test_all_scope_needs_neither(self):
        form = PushBroadcastForm(self._data(scope=PushBroadcast.SCOPE_ALL))
        self.assertTrue(form.is_valid())

    def test_all_scope_discards_a_leftover_selection(self):
        # Switching scope must not quietly narrow a platform-wide send.
        form = PushBroadcastForm(
            self._data(
                scope=PushBroadcast.SCOPE_ALL,
                station=self.station.pk,
                institution=self.institution.pk,
            )
        )
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["station"])
        self.assertIsNone(form.cleaned_data["institution"])


class GlobalBroadcastPermissionTests(TestCase):
    """Notifying the whole platform takes a permission of its own."""

    def setUp(self):
        self.user = User.objects.create_user(
            "operator", password="x", is_staff=True, is_superuser=False
        )
        for codename in ("view_pushbroadcast", "add_pushbroadcast"):
            self.user.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(self.user)

    def test_the_global_permission_exists_and_is_not_granted_by_default(self):
        self.assertTrue(
            Permission.objects.filter(codename="send_global_pushbroadcast").exists()
        )
        self.assertFalse(self.user.has_perm("api.send_global_pushbroadcast"))

    def test_a_platform_wide_send_is_refused_without_it(self):
        with patch("api.push.send_broadcast") as sender:
            response = self.client.post(
                reverse("admin:api_pushbroadcast_send"),
                {
                    "scope": PushBroadcast.SCOPE_ALL,
                    "push_title": "Aviso",
                    "push_body": "Mensaje.",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        sender.assert_not_called()
        self.assertFalse(PushBroadcast.objects.exists())


@override_settings(SENSOR_ALERTS_ENABLED=True)
class SendPageTests(TestCase):
    """The operational notice has a page of its own, reachable without an alert.

    An announcement about maintenance has no AQI threshold, so requiring an
    operator to pick one of the AQI alerts on the way to sending it would be
    asking for a number that has no bearing on the message.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            "operator", password="x", is_staff=True, is_superuser=False
        )
        for codename in ("view_pushbroadcast", "add_pushbroadcast"):
            self.user.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(self.user)

        region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            region=region,
            station_code="RSP-001",
            is_station_on=True,
        )
        installation, _ = DeviceInstallation.register(
            "8f14e45f-ceea-467e-bd97-1a2b3c4d5e6f", push_token="token-a"
        )
        DeviceFollower.objects.create(
            installation=installation, station_code="RSP-001"
        )

    def test_the_page_opens_without_selecting_an_alert(self):
        response = self.client.get(reverse("admin:api_pushbroadcast_send"))
        self.assertEqual(response.status_code, 200)

    def test_a_maintenance_notice_reaches_the_sensors_followers(self):
        with patch("api.push._post_batch", side_effect=ok_tickets) as post:
            response = self.client.post(
                reverse("admin:api_pushbroadcast_send"),
                {
                    "scope": PushBroadcast.SCOPE_STATION,
                    "station": self.station.pk,
                    "push_title": "Mantenimiento programado",
                    "push_body": "El sensor estará fuera de servicio el martes.",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        [messages_sent] = [call.args[0] for call in post.call_args_list]
        self.assertEqual(messages_sent[0]["to"], "token-a")
        self.assertEqual(messages_sent[0]["title"], "Mantenimiento programado")

        broadcast = PushBroadcast.objects.get()
        self.assertEqual(broadcast.recipients, 1)
        self.assertEqual(broadcast.sent_by, self.user)

    def test_an_operator_without_the_permission_cannot_reach_the_page(self):
        self.user.user_permissions.remove(
            Permission.objects.get(codename="add_pushbroadcast")
        )
        # Permissions are cached on the instance for the length of a request.
        self.client.force_login(User.objects.get(pk=self.user.pk))

        response = self.client.get(reverse("admin:api_pushbroadcast_send"))
        self.assertEqual(response.status_code, 403)

    def test_the_log_stays_read_only(self):
        # The record of a send is not an editable draft: Django's own add page
        # for this model must stay closed, so the only way to create a row is
        # actually sending one.
        response = self.client.get(reverse("admin:api_pushbroadcast_add"))
        self.assertEqual(response.status_code, 403)
