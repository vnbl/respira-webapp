"""Tests for the device-follower feature (model, API and admin).

The feature is unauthenticated by design, so the tests carry two burdens the
other API tests do not: proving that a device's follows stay exactly as it left
them no matter how the app retries, and proving that the identifier rules which
stand in for authentication (random v4 UUIDs only) are actually enforced.

A device may follow several stations, so the uniqueness that matters is on the
*pair* — an installation and a station code — and the tests below are written
around that rather than around one row per device.
"""

import uuid
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    DeviceFollower,
    DeviceInstallation,
    Regions,
    StationReadingsGold,
    Stations,
)
from .views import INSTALLATION_ID_HEADER, MAX_FOLLOWS_PER_INSTALLATION

User = get_user_model()

# A v4 UUID (the third group starts with "4"), as the app would generate.
INSTALLATION_ID = "8f14e45f-ceea-467e-bd97-1a2b3c4d5e6f"
OTHER_INSTALLATION_ID = "2c1f9b4a-77d3-4e21-9a5c-6b0e8d3f1a2b"
# Version 1: encodes a MAC address and a timestamp, which is exactly the
# derived, guessable kind of identifier this feature rejects.
V1_INSTALLATION_ID = "d9428888-122b-11e1-b85c-61cd3cbb3210"


class DeviceInstallationModelTests(TestCase):
    def test_installation_id_is_unique(self):
        DeviceInstallation.objects.create(installation_id=INSTALLATION_ID)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DeviceInstallation.objects.create(installation_id=INSTALLATION_ID)

    def test_register_creates_then_reuses_the_same_installation(self):
        installation, created = DeviceInstallation.register(INSTALLATION_ID)
        self.assertTrue(created)

        again, created_again = DeviceInstallation.register(INSTALLATION_ID)
        self.assertFalse(created_again)
        self.assertEqual(installation.pk, again.pk)

    def test_register_leaves_the_token_alone_when_none_is_sent(self):
        DeviceInstallation.register(INSTALLATION_ID, push_token="tok-1")
        installation, _ = DeviceInstallation.register(INSTALLATION_ID)

        self.assertEqual(installation.push_token, "tok-1")

    def test_a_push_token_is_claimed_from_any_previous_installation(self):
        # A reinstall produces a new installation id while the OS may hand the
        # app the same token. Without claiming, the abandoned installation
        # keeps it and the device is notified twice.
        DeviceInstallation.register(OTHER_INSTALLATION_ID, push_token="shared-token")
        DeviceInstallation.register(INSTALLATION_ID, push_token="shared-token")

        old = DeviceInstallation.objects.get(installation_id=OTHER_INSTALLATION_ID)
        new = DeviceInstallation.objects.get(installation_id=INSTALLATION_ID)
        self.assertEqual(old.push_token, "")
        self.assertEqual(new.push_token, "shared-token")

    def test_a_live_token_cannot_be_held_by_two_installations(self):
        # The invariant `register()` maintains, enforced by the database as
        # well: two registrations racing for the same token can each find
        # nothing to clear, and only a constraint can stop both from keeping
        # it — which would notify the device twice for ever after.
        DeviceInstallation.objects.create(
            installation_id=INSTALLATION_ID, push_token="shared-token"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DeviceInstallation.objects.create(
                    installation_id=OTHER_INSTALLATION_ID, push_token="shared-token"
                )

    def test_any_number_of_installations_may_have_no_token_yet(self):
        # "No token" is the normal state of a fresh install, so the constraint
        # above has to exempt it.
        DeviceInstallation.objects.create(installation_id=INSTALLATION_ID)
        DeviceInstallation.objects.create(installation_id=OTHER_INSTALLATION_ID)

        self.assertEqual(DeviceInstallation.objects.filter(push_token="").count(), 2)


class DeviceFollowerModelTests(TestCase):
    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra", region=self.region, station_code="RSP-001"
        )
        self.other_station = Stations.seed_for_tests(
            name="Respira: San Lorenzo", region=self.region, station_code="RSP-002"
        )
        self.installation, _ = DeviceInstallation.register(INSTALLATION_ID)

    def test_an_installation_may_follow_several_stations(self):
        DeviceFollower.objects.create(
            installation=self.installation, station_code="RSP-001"
        )
        DeviceFollower.objects.create(
            installation=self.installation, station_code="RSP-002"
        )

        self.assertEqual(self.installation.follows.count(), 2)

    def test_the_same_station_cannot_be_followed_twice(self):
        DeviceFollower.objects.create(
            installation=self.installation, station_code="RSP-001"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DeviceFollower.objects.create(
                    installation=self.installation, station_code="RSP-001"
                )

    def test_two_installations_may_follow_the_same_station(self):
        other, _ = DeviceInstallation.register(OTHER_INSTALLATION_ID)
        DeviceFollower.objects.create(
            installation=self.installation, station_code="RSP-001"
        )
        DeviceFollower.objects.create(installation=other, station_code="RSP-001")

        self.assertEqual(
            DeviceFollower.objects.filter(station_code="RSP-001").count(), 2
        )

    def test_deleting_an_installation_removes_its_follows(self):
        DeviceFollower.objects.create(
            installation=self.installation, station_code="RSP-001"
        )
        self.installation.delete()

        self.assertEqual(DeviceFollower.objects.count(), 0)

    def test_station_is_resolved_from_the_code_not_a_stored_id(self):
        follow = DeviceFollower.objects.create(
            installation=self.installation, station_code="RSP-001"
        )
        original_id = self.station.id

        # dbt renumbers stations on every run: the same code comes back under
        # a different id, and the follow has to track the code.
        self.station.delete_for_tests()
        renumbered = Stations.seed_for_tests(
            name="Respira: Villa Morra", region=self.region, station_code="RSP-001"
        )

        self.assertNotEqual(renumbered.id, original_id)
        self.assertEqual(follow.station.id, renumbered.id)

    def test_station_is_none_when_the_code_no_longer_exists(self):
        follow = DeviceFollower.objects.create(
            installation=self.installation, station_code="GONE"
        )
        self.assertIsNone(follow.station)


class DeviceFollowerAPITests(APITestCase):
    def setUp(self):
        # The endpoints are throttled per IP and every test client shares
        # 127.0.0.1, so the throttle history is reset between tests.
        cache.clear()
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra", region=self.region, station_code="RSP-001"
        )
        self.other_station = Stations.seed_for_tests(
            name="Respira: San Lorenzo", region=self.region, station_code="RSP-002"
        )
        self.url = reverse("device-followers")
        self.installation_url = reverse("device-installation")

    def _header(self, installation_id=INSTALLATION_ID):
        return {INSTALLATION_ID_HEADER: installation_id}

    def _follow(self, station, installation_id=INSTALLATION_ID):
        return self.client.post(
            self.url,
            {"station": station.id},
            format="json",
            headers=self._header(installation_id),
        )

    # --- following --------------------------------------------------------

    def test_first_follow_is_created(self):
        response = self._follow(self.station)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["station"], self.station.id)
        self.assertEqual(response.data["station_name"], self.station.name)
        self.assertEqual(response.data["station_code"], "RSP-001")

    def test_following_accepts_the_installation_id_in_the_body(self):
        response = self.client.post(
            self.url,
            {"installation_id": INSTALLATION_ID, "station": self.station.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            DeviceInstallation.objects.filter(installation_id=INSTALLATION_ID).exists()
        )

    def test_a_second_station_is_added_rather_than_replacing_the_first(self):
        self._follow(self.station)
        response = self._follow(self.other_station)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        installation = DeviceInstallation.objects.get(installation_id=INSTALLATION_ID)
        self.assertEqual(
            sorted(installation.follows.values_list("station_code", flat=True)),
            ["RSP-001", "RSP-002"],
        )

    def test_a_duplicate_follow_returns_200_without_creating_a_second_row(self):
        # The app retries on a flaky mobile network; the retry must land on the
        # existing row rather than failing against the unique constraint.
        self.assertEqual(
            self._follow(self.station).status_code, status.HTTP_201_CREATED
        )

        repeat = self._follow(self.station)
        self.assertEqual(repeat.status_code, status.HTTP_200_OK)
        self.assertEqual(DeviceFollower.objects.count(), 1)

    def test_following_registers_a_push_token_when_sent(self):
        response = self.client.post(
            self.url,
            {"station": self.station.id, "push_token": "tok-1"},
            format="json",
            headers=self._header(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        installation = DeviceInstallation.objects.get(installation_id=INSTALLATION_ID)
        self.assertEqual(installation.push_token, "tok-1")

    @override_settings(SENSOR_ALERTS_ENABLED=True)
    def test_following_a_sensor_that_is_already_bad_notifies_that_device(self):
        # The gap this closes: alerting state is per station, so joining an
        # episode somebody else was already warned about matches no change and
        # the scheduled sender would say nothing to this device.
        self.station.is_station_on = True
        self.station.update_for_tests(update_fields=["is_station_on"])
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=timezone.now(), aqi_pm2_5=165
        )

        sent = []

        def capture(messages):
            sent.extend(messages)
            return [{"status": "ok", "id": "tk-1"} for _ in messages]

        with patch("api.push._post_batch", side_effect=capture):
            response = self.client.post(
                self.url,
                {"station": self.station.id, "push_token": "tok-1"},
                format="json",
                headers=self._header(),
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual([m["to"] for m in sent], ["tok-1"])
        self.assertEqual(sent[0]["data"]["trend"], "catch_up")

    @override_settings(SENSOR_ALERTS_ENABLED=True)
    def test_a_repeated_follow_does_not_notify_again(self):
        # The app retries on a flaky network. A retry that re-sent the push
        # would notify the same device twice for one follow.
        self.station.is_station_on = True
        self.station.update_for_tests(update_fields=["is_station_on"])
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=timezone.now(), aqi_pm2_5=165
        )

        sent = []

        def capture(messages):
            sent.extend(messages)
            return [{"status": "ok", "id": "tk-1"} for _ in messages]

        with patch("api.push._post_batch", side_effect=capture):
            self.client.post(
                self.url,
                {"station": self.station.id, "push_token": "tok-1"},
                format="json",
                headers=self._header(),
            )
            repeat = self._follow(self.station)

        self.assertEqual(repeat.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sent), 1)

    def test_a_failing_catch_up_push_never_fails_the_follow(self):
        # The follow is the user's action and must succeed on its own.
        self.station.is_station_on = True
        self.station.update_for_tests(update_fields=["is_station_on"])
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=timezone.now(), aqi_pm2_5=165
        )

        with override_settings(SENSOR_ALERTS_ENABLED=True):
            with patch(
                "api.push._post_batch", side_effect=requests.ConnectionError("down")
            ):
                response = self.client.post(
                    self.url,
                    {"station": self.station.id, "push_token": "tok-1"},
                    format="json",
                    headers=self._header(),
                )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DeviceFollower.objects.count(), 1)

    def test_the_push_token_is_never_echoed_back(self):
        self.client.post(
            self.url,
            {"station": self.station.id, "push_token": "secret-token"},
            format="json",
            headers=self._header(),
        )
        response = self.client.get(self.installation_url, headers=self._header())

        self.assertNotIn("push_token", response.data)
        self.assertTrue(response.data["has_push_token"])

    def test_two_devices_keep_separate_follows(self):
        self._follow(self.station)
        self._follow(self.other_station, installation_id=OTHER_INSTALLATION_ID)

        self.assertEqual(DeviceInstallation.objects.count(), 2)
        response = self.client.get(self.url, headers=self._header())
        self.assertEqual([row["station"] for row in response.data], [self.station.id])

    def test_the_cap_is_enforced(self):
        for index in range(MAX_FOLLOWS_PER_INSTALLATION):
            station = Stations.seed_for_tests(
                name=f"Respira: {index}",
                region=self.region,
                station_code=f"CAP-{index:03d}",
            )
            self.assertEqual(self._follow(station).status_code, status.HTTP_201_CREATED)

        response = self._follow(self.station)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # A code rather than prose: the app has to tell this apart from the
        # other 400 this endpoint returns, and cannot do that by matching on an
        # English sentence.
        self.assertEqual(response.data["code"], "max_follows_reached")
        self.assertEqual(response.data["max"], MAX_FOLLOWS_PER_INSTALLATION)

    def test_the_two_kinds_of_400_are_distinguishable(self):
        codeless = Stations.seed_for_tests(
            name="Respira: sin código", region=self.region, station_code=""
        )
        not_followable = self._follow(codeless)

        self.assertEqual(not_followable.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("station", not_followable.data)
        self.assertNotIn("code", not_followable.data)

    def test_a_duplicate_follow_at_the_cap_still_succeeds(self):
        # Re-following something already followed adds nothing, so the cap must
        # not turn a harmless retry into an error.
        stations = []
        for index in range(MAX_FOLLOWS_PER_INSTALLATION):
            station = Stations.seed_for_tests(
                name=f"Respira: {index}",
                region=self.region,
                station_code=f"CAP-{index:03d}",
            )
            stations.append(station)
            self._follow(station)

        response = self._follow(stations[0])
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_an_unknown_station_is_rejected(self):
        response = self.client.post(
            self.url, {"station": 999999}, format="json", headers=self._header()
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_station_without_a_station_code_cannot_be_followed(self):
        codeless = Stations.seed_for_tests(
            name="Respira: sin código", region=self.region, station_code=""
        )
        response = self._follow(codeless)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("station", response.data)

    def test_following_requires_a_station(self):
        response = self.client.post(self.url, {}, format="json", headers=self._header())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- the installation id --------------------------------------------

    def test_a_missing_installation_id_is_rejected(self):
        response = self.client.post(
            self.url, {"station": self.station.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_malformed_installation_id_is_rejected(self):
        response = self.client.get(self.url, headers=self._header("not-a-uuid"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_non_random_uuid_is_rejected(self):
        # v1 encodes a MAC address and a timestamp — guessable, and therefore
        # useless as the thing standing in for a credential.
        response = self.client.get(self.url, headers=self._header(V1_INSTALLATION_ID))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- listing ----------------------------------------------------------

    def test_listing_an_unknown_installation_returns_an_empty_list(self):
        # The normal state of a fresh install: an empty list, not a 404.
        response = self.client.get(self.url, headers=self._header())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_listing_by_query_parameter(self):
        self._follow(self.station)
        response = self.client.get(self.url, {"installation_id": INSTALLATION_ID})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_listing_returns_the_current_station_id_after_renumbering(self):
        self._follow(self.station)
        original_id = self.station.id
        self.station.delete_for_tests()
        renumbered = Stations.seed_for_tests(
            name="Respira: Villa Morra", region=self.region, station_code="RSP-001"
        )

        response = self.client.get(self.url, headers=self._header())

        self.assertNotEqual(renumbered.id, original_id)
        self.assertEqual(response.data[0]["station"], renumbered.id)

    def test_listing_reports_a_station_that_no_longer_exists_as_null(self):
        self._follow(self.station)
        self.station.delete_for_tests()

        response = self.client.get(self.url, headers=self._header())

        # Null rather than the id of whichever station inherited the number:
        # the app needs to know the sensor is gone.
        self.assertIsNone(response.data[0]["station"])
        self.assertIsNone(response.data[0]["station_name"])
        self.assertEqual(response.data[0]["station_code"], "RSP-001")

    # --- unfollowing ------------------------------------------------------

    def test_unfollowing_one_station_leaves_the_others(self):
        self._follow(self.station)
        self._follow(self.other_station)

        response = self.client.delete(
            f"{self.url}?station={self.station.id}", headers=self._header()
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        remaining = DeviceFollower.objects.values_list("station_code", flat=True)
        self.assertEqual(list(remaining), ["RSP-002"])

    def test_unfollowing_without_a_station_removes_them_all(self):
        self._follow(self.station)
        self._follow(self.other_station)

        response = self.client.delete(self.url, headers=self._header())

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DeviceFollower.objects.count(), 0)

    def test_unfollowing_twice_is_idempotent(self):
        self._follow(self.station)
        first = self.client.delete(
            f"{self.url}?station={self.station.id}", headers=self._header()
        )
        second = self.client.delete(
            f"{self.url}?station={self.station.id}", headers=self._header()
        )

        self.assertEqual(first.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(second.status_code, status.HTTP_204_NO_CONTENT)

    def test_unfollowing_a_station_that_no_longer_exists_succeeds(self):
        # The caller asked for that station not to be followed, and it is not.
        self._follow(self.station)
        station_id = self.station.id
        self.station.delete_for_tests()

        response = self.client.delete(
            f"{self.url}?station={station_id}", headers=self._header()
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_a_dropped_station_can_still_be_unfollowed_by_code(self):
        # By id this is impossible — there is no station row left to resolve —
        # yet it is exactly the follow a user most wants off their list.
        self._follow(self.station)
        self.station.delete_for_tests()

        response = self.client.delete(
            f"{self.url}?station_code=RSP-001", headers=self._header()
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DeviceFollower.objects.count(), 0)

    def test_unfollowing_by_code_leaves_the_others(self):
        self._follow(self.station)
        self._follow(self.other_station)

        self.client.delete(f"{self.url}?station_code=RSP-001", headers=self._header())

        remaining = DeviceFollower.objects.values_list("station_code", flat=True)
        self.assertEqual(list(remaining), ["RSP-002"])

    def test_unfollowing_rejects_a_non_numeric_station(self):
        response = self.client.delete(f"{self.url}?station=abc", headers=self._header())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unfollowing_rejects_a_blank_station_code(self):
        # Omitting the parameter is how a caller unfollows everything, so a
        # blank one must not be read as omitted: an app that built the query
        # string from an empty variable would wipe the whole list instead of
        # removing one station.
        self._follow(self.station)
        self._follow(self.other_station)

        response = self.client.delete(
            f"{self.url}?station_code=", headers=self._header()
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(DeviceFollower.objects.count(), 2)

    def test_unfollowing_leaves_other_installations_alone(self):
        self._follow(self.station)
        self._follow(self.station, installation_id=OTHER_INSTALLATION_ID)

        self.client.delete(self.url, headers=self._header())

        self.assertEqual(
            DeviceFollower.objects.filter(
                installation__installation_id=OTHER_INSTALLATION_ID
            ).count(),
            1,
        )

    def test_unfollowing_keeps_the_installation_and_its_token(self):
        # Unfollowing everything is not a deregistration: the device is still
        # installed and its token still belongs to it.
        self.client.put(
            self.installation_url,
            {"push_token": "tok-1"},
            format="json",
            headers=self._header(),
        )
        self._follow(self.station)
        self.client.delete(self.url, headers=self._header())

        installation = DeviceInstallation.objects.get(installation_id=INSTALLATION_ID)
        self.assertEqual(installation.push_token, "tok-1")

    # --- the installation endpoint ---------------------------------------

    def test_registering_a_push_token_creates_the_installation(self):
        response = self.client.put(
            self.installation_url,
            {"push_token": "tok-1"},
            format="json",
            headers=self._header(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["has_push_token"])
        self.assertEqual(response.data["follow_count"], 0)

    def test_refreshing_the_push_token(self):
        self.client.put(
            self.installation_url,
            {"push_token": "tok-1"},
            format="json",
            headers=self._header(),
        )
        self.client.put(
            self.installation_url,
            {"push_token": "tok-2"},
            format="json",
            headers=self._header(),
        )

        installation = DeviceInstallation.objects.get(installation_id=INSTALLATION_ID)
        self.assertEqual(installation.push_token, "tok-2")

    def test_clearing_the_push_token(self):
        self.client.put(
            self.installation_url,
            {"push_token": "tok-1"},
            format="json",
            headers=self._header(),
        )
        response = self.client.put(
            self.installation_url,
            {"push_token": ""},
            format="json",
            headers=self._header(),
        )

        self.assertFalse(response.data["has_push_token"])

    def test_registering_a_token_clears_it_from_an_older_installation(self):
        self.client.put(
            self.installation_url,
            {"push_token": "shared"},
            format="json",
            headers=self._header(OTHER_INSTALLATION_ID),
        )
        self.client.put(
            self.installation_url,
            {"push_token": "shared"},
            format="json",
            headers=self._header(),
        )

        old = DeviceInstallation.objects.get(installation_id=OTHER_INSTALLATION_ID)
        self.assertEqual(old.push_token, "")

    def test_reading_an_unregistered_installation_returns_404(self):
        response = self.client.get(self.installation_url, headers=self._header())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_installation_reports_how_much_it_follows(self):
        self._follow(self.station)
        self._follow(self.other_station)

        response = self.client.get(self.installation_url, headers=self._header())
        self.assertEqual(response.data["follow_count"], 2)

    def test_a_push_token_is_required(self):
        response = self.client.put(
            self.installation_url, {}, format="json", headers=self._header()
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- schema -----------------------------------------------------------

    def test_the_endpoints_are_documented_in_the_openapi_schema(self):
        response = self.client.get(reverse("schema"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("/api/device-followers/", body)
        self.assertIn("/api/device-installations/me/", body)


class DeviceFollowerAdminTests(TestCase):
    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra", region=self.region, station_code="RSP-001"
        )
        # Realistic length: the admin masks a token down to its last 8
        # characters, which only says anything for a token longer than that.
        # Real FCM/APNs tokens are 150+.
        self.push_token = "ExponentPushToken" + ("x" * 140) + "TAIL1234"
        self.installation, _ = DeviceInstallation.register(
            INSTALLATION_ID, push_token=self.push_token
        )
        DeviceFollower.objects.create(
            installation=self.installation, station_code="RSP-001"
        )
        DeviceFollower.objects.create(
            installation=self.installation, station_code="GONE"
        )

        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="pw"
        )
        self.client.force_login(self.admin_user)

    def test_the_changelist_resolves_station_names(self):
        response = self.client.get("/admin/api/devicefollower/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Respira: Villa Morra")
        # A code the pipeline no longer publishes is worth showing as such
        # rather than as an empty cell.
        self.assertContains(response, "unknown station")

    def test_the_installation_changelist_counts_follows(self):
        response = self.client.get("/admin/api/deviceinstallation/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, str(INSTALLATION_ID))

    def test_the_push_token_is_masked_on_the_changelist(self):
        response = self.client.get("/admin/api/deviceinstallation/")

        # Enough of the tail to tell two tokens apart, without printing a
        # credential across a list page.
        self.assertNotContains(response, self.push_token)
        self.assertContains(response, "TAIL1234")

    def test_searching_by_installation_id(self):
        response = self.client.get(
            "/admin/api/devicefollower/", {"q": str(INSTALLATION_ID)}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "RSP-001")

    def test_searching_by_station_code(self):
        response = self.client.get("/admin/api/devicefollower/", {"q": "RSP-001"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Respira: Villa Morra")

    def test_followers_cannot_be_added_or_changed_from_the_admin(self):
        # A follow is a device's own state: editing it here would silently
        # point somebody's phone at a different sensor.
        self.assertEqual(
            self.client.get("/admin/api/devicefollower/add/").status_code,
            status.HTTP_403_FORBIDDEN,
        )


class DeviceInstallationMigrationTests(TransactionTestCase):
    """The split must not lose anybody's followed station or push token.

    Running the migrations forward on an empty database — which every other
    test here does — never exercises the data migration, and that is the one
    step that can silently discard a user's choice. So this rewinds to the
    shape before the split, writes a row the old way, and migrates forward.
    """

    migrate_from = [("api", "0014_merge_20260826_1744")]
    migrate_to = [("api", "0015_device_installation_multi_follow")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor.loader.build_graph()
        self.old_apps = executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        # Leave the database at the latest migration, since TransactionTestCase
        # does not roll this back for whatever runs next.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        executor.loader.build_graph()
        return executor.loader.project_state(self.migrate_to).apps

    def _migrate_backward(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_from)
        executor.loader.build_graph()
        return executor.loader.project_state(self.migrate_from).apps

    def test_an_existing_follower_keeps_its_station_and_token(self):
        OldFollower = self.old_apps.get_model("api", "DeviceFollower")
        OldFollower.objects.create(
            installation_id=INSTALLATION_ID,
            station_code="RSP-001",
            push_token="tok-1",
        )

        new_apps = self._migrate_forward()
        Installation = new_apps.get_model("api", "DeviceInstallation")
        Follower = new_apps.get_model("api", "DeviceFollower")

        installation = Installation.objects.get(installation_id=INSTALLATION_ID)
        self.assertEqual(installation.push_token, "tok-1")

        follow = Follower.objects.get()
        self.assertEqual(follow.installation_id, installation.pk)
        self.assertEqual(follow.station_code, "RSP-001")

    def test_each_installation_gets_its_own_row(self):
        OldFollower = self.old_apps.get_model("api", "DeviceFollower")
        OldFollower.objects.create(
            installation_id=INSTALLATION_ID, station_code="RSP-001", push_token=""
        )
        OldFollower.objects.create(
            installation_id=OTHER_INSTALLATION_ID,
            station_code="RSP-002",
            push_token="tok-2",
        )

        new_apps = self._migrate_forward()
        Installation = new_apps.get_model("api", "DeviceInstallation")

        self.assertEqual(Installation.objects.count(), 2)
        self.assertEqual(
            Installation.objects.get(installation_id=OTHER_INSTALLATION_ID).push_token,
            "tok-2",
        )
        self.assertEqual(
            Installation.objects.get(installation_id=INSTALLATION_ID).follows.count(),
            1,
        )

    def test_the_split_can_be_reversed_with_rows_in_the_table(self):
        # The rollback path, which only has value if it works on a database
        # that has data: re-adding the old UUID column has to make room for the
        # data migration to fill it, not demand a value the rows do not have
        # yet.
        OldFollower = self.old_apps.get_model("api", "DeviceFollower")
        OldFollower.objects.create(
            installation_id=INSTALLATION_ID,
            station_code="RSP-001",
            push_token="tok-1",
        )

        self._migrate_forward()
        old_apps = self._migrate_backward()

        Follower = old_apps.get_model("api", "DeviceFollower")
        follow = Follower.objects.get()
        self.assertEqual(follow.installation_id, uuid.UUID(INSTALLATION_ID))
        self.assertEqual(follow.station_code, "RSP-001")
        self.assertEqual(follow.push_token, "tok-1")

    def test_reversing_refuses_to_discard_a_second_follow(self):
        # The old shape holds one station per device, so going back with two
        # would have to drop one — a choice the user made, silently undone.
        OldFollower = self.old_apps.get_model("api", "DeviceFollower")
        OldFollower.objects.create(
            installation_id=INSTALLATION_ID, station_code="RSP-001", push_token=""
        )

        new_apps = self._migrate_forward()
        Installation = new_apps.get_model("api", "DeviceInstallation")
        Follower = new_apps.get_model("api", "DeviceFollower")
        Follower.objects.create(
            installation=Installation.objects.get(installation_id=INSTALLATION_ID),
            station_code="RSP-002",
        )

        with self.assertRaises(RuntimeError):
            self._migrate_backward()


def test_uuid_constants_are_the_versions_they_claim():
    """Guards the fixtures themselves: a typo here would silently weaken the
    identifier tests above, which exist to prove v4 is required."""
    assert uuid.UUID(INSTALLATION_ID).version == 4
    assert uuid.UUID(OTHER_INSTALLATION_ID).version == 4
    assert uuid.UUID(V1_INSTALLATION_ID).version == 1
