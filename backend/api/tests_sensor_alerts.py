"""Tests for the per-sensor push alerts (api.push).

The rule the whole feature turns on: an alert about a sensor reaches the
devices that follow *that* sensor, and no others. These tests exercise it
against the real follower tables rather than a mock of them, because the
audience being derived from `DeviceFollower` is the point.

Expo's push service is the only thing stubbed — the tests assert on what would
be sent, which is what determines who gets warned.
"""

from unittest.mock import patch

import requests
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .models import (
    DeviceFollower,
    DeviceInstallation,
    Institution,
    InstitutionAlertRule,
    InstitutionAlertRuleState,
    Regions,
    SensorAlert,
    SensorAlertState,
    StationReadingsGold,
    Stations,
)
from .push import (
    catch_up_follower,
    notification_for,
    send_sensor_alerts,
    should_alert,
    should_notify_recovery,
)

INSTALLATION_ID = "8f14e45f-ceea-467e-bd97-1a2b3c4d5e6f"
OTHER_INSTALLATION_ID = "2c1f9b4a-77d3-4e21-9a5c-6b0e8d3f1a2b"


def ok_tickets(messages):
    """Expo's success shape: one ticket per message, in order."""
    return {"data": [{"status": "ok", "id": f"tk-{i}"} for i in range(len(messages))]}


class ShouldAlertTests(TestCase):
    def test_only_alert_worthy_levels_notify(self):
        self.assertFalse(should_alert("good", None))
        self.assertFalse(should_alert("moderate", None))
        self.assertTrue(should_alert("unhealthySensitive", None))
        self.assertTrue(should_alert("hazardous", None))

    def test_the_same_level_does_not_notify_twice(self):
        # A station sitting just over a threshold would otherwise notify on
        # every reading, which trains people to ignore the alerts that matter.
        self.assertFalse(should_alert("unhealthy", "unhealthy"))

    def test_only_a_worsening_notifies(self):
        self.assertTrue(should_alert("veryUnhealthy", "unhealthy"))
        self.assertFalse(should_alert("unhealthySensitive", "unhealthy"))

    def test_improving_into_a_safe_level_does_not_notify(self):
        self.assertFalse(should_alert("good", "hazardous"))

    def test_a_station_with_no_open_episode_alerts_from_its_first_bad_reading(self):
        # Blank is both "never alerted" and "recovered since", which is what
        # makes a new episode start from scratch instead of having to beat the
        # worst level of the previous one.
        self.assertTrue(should_alert("unhealthySensitive", ""))


class ShouldNotifyRecoveryTests(TestCase):
    def test_an_open_episode_getting_better_notifies(self):
        self.assertTrue(should_notify_recovery("good", "unhealthy"))

    def test_every_drop_notifies_not_only_a_return_to_safety(self):
        # Hazardous down to unhealthy is still news to somebody deciding
        # whether to go outside, and waiting for `good` could leave them acting
        # on the worst reading of the episode for hours.
        self.assertTrue(should_notify_recovery("unhealthy", "hazardous"))

    def test_a_station_nobody_was_warned_about_sends_no_all_clear(self):
        # Otherwise every station sitting quietly at `good` would notify on
        # every run.
        self.assertFalse(should_notify_recovery("good", ""))
        self.assertFalse(should_notify_recovery("good", None))

    def test_standing_still_notifies_nothing(self):
        self.assertFalse(should_notify_recovery("unhealthy", "unhealthy"))

    def test_worsening_is_not_a_recovery(self):
        self.assertFalse(should_notify_recovery("hazardous", "unhealthy"))


class NotificationForTests(TestCase):
    """The one place that decides, so sender and dry run cannot disagree."""

    def test_it_picks_the_direction(self):
        self.assertEqual(notification_for("hazardous", ""), "worsening")
        self.assertEqual(notification_for("good", "hazardous"), "improving")
        self.assertIsNone(notification_for("good", ""))
        self.assertIsNone(notification_for("unhealthy", "unhealthy"))


class SendSensorAlertsTests(TestCase):
    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
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

    def test_only_the_followers_of_that_sensor_are_notified(self):
        # The rule the whole feature exists for.
        self._follower("RSP-001", "token-a")
        self._follower("RSP-002", "token-b", OTHER_INSTALLATION_ID)
        self._reading(self.station, 165)
        self._reading(self.other_station, 20)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()

        self.assertEqual(capture.recipients(), ["token-a"])

    def test_the_payload_identifies_the_sensor_by_its_stable_code(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()

        [message] = capture.messages
        self.assertEqual(message["data"]["type"], "sensor_alert")
        # The code, not the id: dbt regenerates station ids on every run, so an
        # id here could mean a different sensor by the time it is opened.
        self.assertEqual(message["data"]["station_code"], "RSP-001")
        self.assertNotIn("station", message["data"])
        self.assertEqual(message["data"]["level"], "unhealthy")
        self.assertIn(self.station.name, message["body"])

    def test_a_station_nobody_follows_is_never_read(self):
        self._reading(self.station, 300)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            result = send_sensor_alerts()

        self.assertEqual(result.considered, 0)
        self.assertEqual(capture.messages, [])

    def test_a_second_run_at_the_same_level_sends_nothing(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()
            first = len(capture.messages)
            send_sensor_alerts()

        self.assertEqual(first, 1)
        self.assertEqual(len(capture.messages), 1)

    def test_a_worsening_sends_again(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()
            self._reading(self.station, 320)
            send_sensor_alerts()

        self.assertEqual(
            [m["data"]["level"] for m in capture.messages], ["unhealthy", "hazardous"]
        )

    def test_a_station_that_recovered_alerts_again_on_the_next_episode(self):
        # The bug this guards: with only the alert log to go on, the last thing
        # known about this station stays `hazardous` for ever, and since
        # nothing outranks it the station could never alert again.
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 320)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()
            self._reading(self.station, 20)  # good
            send_sensor_alerts()
            self._reading(self.station, 165)  # unhealthy
            send_sensor_alerts()

        # The middle message is the all-clear for the first episode; the third
        # is the new episode alerting from scratch.
        self.assertEqual(
            [(m["data"]["level"], m["data"]["trend"]) for m in capture.messages],
            [
                ("hazardous", "worsening"),
                ("good", "improving"),
                ("unhealthy", "worsening"),
            ],
        )

    def test_a_reading_below_the_threshold_is_remembered_even_though_it_is_silent(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 20)

        with patch("api.push._post_batch", side_effect=Capture()):
            send_sensor_alerts()

        state = SensorAlertState.objects.get(station_code="RSP-001")
        self.assertEqual(state.last_level, "good")
        self.assertEqual(state.last_alerted_level, "")

    def test_an_undated_reading_never_stands_in_for_the_latest_one(self):
        # `date_utc` is nullable and PostgreSQL sorts nulls first descending,
        # so an undated row would otherwise shadow the real latest reading and
        # alert on air of unknown age.
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 20)
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=None, aqi_pm2_5=320
        )

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()

        self.assertEqual(capture.messages, [])

    def test_a_rejected_delivery_is_retried_and_not_recorded(self):
        # Expo answered, but for nobody: the followers were never warned, so
        # the next run has to try again rather than treat them as told.
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        def throttled(messages):
            return [
                {"status": "error", "details": {"error": "MessageRateExceeded"}}
                for _ in messages
            ]

        with patch("api.push._post_batch", side_effect=throttled):
            result = send_sensor_alerts()

        self.assertEqual(result.alerted_stations, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(SensorAlert.objects.count(), 0)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()

        self.assertEqual(capture.recipients(), ["token-a"])

    def test_a_reply_missing_its_tickets_is_treated_as_undelivered(self):
        # A 200 with no ticket for a message is not a delivery: there is
        # nothing that says it was accepted and nothing to check later.
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        with patch("api.push._post_batch", return_value=[]):
            result = send_sensor_alerts()

        self.assertEqual(result.alerted_stations, 0)
        self.assertEqual(SensorAlert.objects.count(), 0)

    def test_one_accepted_message_is_enough_not_to_alert_everyone_again(self):
        # Retrying the station because a single token was rate limited would
        # send a second copy to everyone the first attempt did reach.
        self._follower("RSP-001", "token-a")
        self._follower("RSP-001", "token-b", OTHER_INSTALLATION_ID)
        self._reading(self.station, 165)

        def one_of_each(messages):
            return [
                {"status": "ok", "id": "tk-1"},
                {"status": "error", "details": {"error": "MessageRateExceeded"}},
            ]

        with patch("api.push._post_batch", side_effect=one_of_each):
            first = send_sensor_alerts()

        self.assertEqual(first.alerted_stations, 1)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()

        self.assertEqual(capture.messages, [])

    def test_a_station_switched_off_is_skipped(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 300)
        self.station.is_station_on = False
        self.station.update_for_tests(update_fields=["is_station_on"])

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            result = send_sensor_alerts()

        self.assertEqual(result.considered, 0)
        self.assertEqual(capture.messages, [])

    def test_a_follow_whose_station_the_pipeline_dropped_is_skipped(self):
        self._follower("GONE", "token-a")

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            result = send_sensor_alerts()

        self.assertEqual(result.considered, 0)
        self.assertEqual(capture.messages, [])

    def test_an_installation_without_a_token_is_skipped(self):
        installation, _ = DeviceInstallation.register(INSTALLATION_ID)
        DeviceFollower.objects.create(installation=installation, station_code="RSP-001")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            result = send_sensor_alerts()

        # Read and judged worth alerting, but nobody reachable to alert.
        self.assertEqual(result.considered, 1)
        self.assertEqual(capture.messages, [])

    def test_a_reinstall_taking_over_a_token_is_sent_one_copy(self):
        # A reinstall produces a new installation while the OS may hand the app
        # the same token. The device is one device and must be told once, so
        # the new installation takes the token off the old one.
        self._follower("RSP-001", "same-token", INSTALLATION_ID)
        self._follower("RSP-001", "same-token", OTHER_INSTALLATION_ID)
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()

        self.assertEqual(capture.recipients(), ["same-token"])
        self.assertEqual(
            DeviceInstallation.objects.get(installation_id=INSTALLATION_ID).push_token,
            "",
        )

    def test_a_dead_token_is_cleared(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        def dead(messages):
            return [
                {"status": "error", "details": {"error": "DeviceNotRegistered"}}
                for _ in messages
            ]

        with patch("api.push._post_batch", side_effect=dead):
            result = send_sensor_alerts()

        self.assertEqual(result.tokens_cleared, 1)
        self.assertEqual(
            DeviceInstallation.objects.get(installation_id=INSTALLATION_ID).push_token,
            "",
        )

    def test_a_transient_error_does_not_clear_the_token(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        def throttled(messages):
            return [
                {"status": "error", "details": {"error": "MessageRateExceeded"}}
                for _ in messages
            ]

        with patch("api.push._post_batch", side_effect=throttled):
            send_sensor_alerts()

        self.assertNotEqual(
            DeviceInstallation.objects.get(installation_id=INSTALLATION_ID).push_token,
            "",
        )

    def test_a_delivery_failure_is_not_recorded_so_the_next_run_retries(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        with patch(
            "api.push._post_batch", side_effect=requests.ConnectionError("down")
        ):
            result = send_sensor_alerts()

        self.assertEqual(len(result.errors), 1)
        self.assertEqual(SensorAlert.objects.count(), 0)

    def test_one_station_failing_does_not_stop_the_others(self):
        self._follower("RSP-001", "token-a")
        self._follower("RSP-002", "token-b", OTHER_INSTALLATION_ID)
        self._reading(self.station, 165)
        self._reading(self.other_station, 165)

        calls = {"n": 0}

        def fail_first(messages):
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.ConnectionError("down")
            return ok_tickets(messages)["data"]

        with patch("api.push._post_batch", side_effect=fail_first):
            result = send_sensor_alerts()

        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.alerted_stations, 1)

    def test_the_alert_is_recorded_for_audit(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()

        alert = SensorAlert.objects.get()
        self.assertEqual(alert.station_code, "RSP-001")
        self.assertEqual(alert.level, "unhealthy")
        self.assertEqual(alert.recipients, 1)

    def test_the_all_clear_reaches_the_same_followers(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()
            self._reading(self.station, 20)
            result = send_sensor_alerts()

        self.assertEqual(capture.recipients(), ["token-a", "token-a"])
        self.assertEqual(result.recovered_stations, 1)
        self.assertEqual(result.alerted_stations, 0)

    def test_the_all_clear_still_routes_in_the_shipped_app(self):
        # The app switches on `type` and treats anything it does not know as
        # unknown, so an all-clear announcing a new type would open nothing
        # when tapped until every user had updated.
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()
            self._reading(self.station, 20)
            send_sensor_alerts()

        all_clear = capture.messages[-1]
        self.assertEqual(all_clear["data"]["type"], "sensor_alert")
        self.assertEqual(all_clear["data"]["station_code"], "RSP-001")
        self.assertEqual(all_clear["data"]["trend"], "improving")
        self.assertEqual(all_clear["data"]["level"], "good")
        self.assertIn(self.station.name, all_clear["body"])

    def test_each_step_down_notifies(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 320)  # hazardous

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()
            self._reading(self.station, 165)  # unhealthy
            send_sensor_alerts()
            self._reading(self.station, 20)  # good
            send_sensor_alerts()

        self.assertEqual(
            [(m["data"]["level"], m["data"]["trend"]) for m in capture.messages],
            [
                ("hazardous", "worsening"),
                ("unhealthy", "improving"),
                ("good", "improving"),
            ],
        )

    def test_staying_safe_after_the_all_clear_says_nothing_more(self):
        # The episode is closed; further good readings are not news.
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()
            self._reading(self.station, 20)
            send_sensor_alerts()
            sent = len(capture.messages)
            self._reading(self.station, 30)
            send_sensor_alerts()

        self.assertEqual(len(capture.messages), sent)

    def test_a_station_that_was_never_bad_sends_no_all_clear(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 20)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            result = send_sensor_alerts()

        self.assertEqual(capture.messages, [])
        self.assertEqual(result.recovered_stations, 0)

    def test_an_undelivered_all_clear_is_retried(self):
        # Same policy as a warning: the followers were not told, so the episode
        # stays open and the next run tries again.
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        with patch("api.push._post_batch", side_effect=Capture()):
            send_sensor_alerts()

        self._reading(self.station, 20)

        def throttled(messages):
            return [
                {"status": "error", "details": {"error": "MessageRateExceeded"}}
                for _ in messages
            ]

        with patch("api.push._post_batch", side_effect=throttled):
            result = send_sensor_alerts()

        self.assertEqual(result.recovered_stations, 0)
        self.assertEqual(len(result.errors), 1)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            send_sensor_alerts()

        self.assertEqual(capture.recipients(), ["token-a"])
        self.assertEqual(capture.messages[0]["data"]["trend"], "improving")

    def test_the_all_clear_is_recorded_as_such_for_audit(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        with patch("api.push._post_batch", side_effect=Capture()):
            send_sensor_alerts()
            self._reading(self.station, 20)
            send_sensor_alerts()

        warning, all_clear = SensorAlert.objects.order_by("sent_at")
        self.assertEqual((warning.level, warning.trend), ("unhealthy", "worsening"))
        self.assertEqual((all_clear.level, all_clear.trend), ("good", "improving"))

    def test_a_dry_run_reports_the_all_clear_it_would_send(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        with patch("api.push._post_batch", side_effect=Capture()):
            send_sensor_alerts()

        self._reading(self.station, 20)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            result = send_sensor_alerts(dry_run=True)

        self.assertEqual(result.recovered_stations, 1)
        self.assertEqual(result.alerted_stations, 0)
        self.assertEqual(capture.messages, [])

    def test_a_dry_run_sends_nothing_and_records_nothing(self):
        self._follower("RSP-001", "token-a")
        self._reading(self.station, 165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            result = send_sensor_alerts(dry_run=True)

        self.assertEqual(result.alerted_stations, 1)
        self.assertEqual(capture.messages, [])
        self.assertEqual(SensorAlert.objects.count(), 0)


@override_settings(SENSOR_ALERTS_ENABLED=True)
class CatchUpFollowerTests(TestCase):
    """Following a sensor that is already bad has to say so.

    `SensorAlertState` is per station, so somebody joining an episode that is
    already open matches no change and the scheduled sender has nothing to say
    about them. Without this they would hear nothing until the air worsened
    further or recovered — silence in exactly the case the feature exists for.
    """

    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            region=self.region,
            station_code="RSP-001",
            is_station_on=True,
        )

    def _reading(self, aqi):
        return StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=timezone.now(), aqi_pm2_5=aqi
        )

    def _installation(self, token="token-a", installation_id=INSTALLATION_ID):
        installation, _ = DeviceInstallation.register(installation_id, push_token=token)
        return installation

    def test_joining_an_open_episode_is_told_how_the_air_is(self):
        self._reading(165)
        installation = self._installation()

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            sent = catch_up_follower(installation, self.station)

        self.assertTrue(sent)
        self.assertEqual(capture.recipients(), ["token-a"])
        [message] = capture.messages
        self.assertEqual(message["data"]["type"], "sensor_alert")
        self.assertEqual(message["data"]["station_code"], "RSP-001")
        self.assertEqual(message["data"]["level"], "unhealthy")
        self.assertEqual(message["data"]["trend"], "catch_up")

    def test_it_does_not_advance_the_stations_state(self):
        # The state is what every *other* follower's next notification is
        # judged against. Moving it here would suppress a real warning for all
        # of them just because one device joined.
        self._reading(165)
        installation = self._installation()

        with patch("api.push._post_batch", side_effect=Capture()):
            catch_up_follower(installation, self.station)

        self.assertFalse(
            SensorAlertState.objects.filter(station_code="RSP-001").exists()
        )

    def test_a_healthy_sensor_says_nothing(self):
        self._reading(20)
        installation = self._installation()

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            sent = catch_up_follower(installation, self.station)

        self.assertFalse(sent)
        self.assertEqual(capture.messages, [])

    def test_an_installation_without_a_token_says_nothing(self):
        self._reading(165)
        installation, _ = DeviceInstallation.register(INSTALLATION_ID)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            self.assertFalse(catch_up_follower(installation, self.station))

        self.assertEqual(capture.messages, [])

    def test_a_station_switched_off_says_nothing(self):
        self._reading(165)
        self.station.is_station_on = False
        self.station.update_for_tests(update_fields=["is_station_on"])

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            self.assertFalse(catch_up_follower(self._installation(), self.station))

        self.assertEqual(capture.messages, [])

    def test_a_station_with_no_reading_says_nothing(self):
        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            self.assertFalse(catch_up_follower(self._installation(), self.station))

        self.assertEqual(capture.messages, [])

    @override_settings(SENSOR_ALERTS_ENABLED=False)
    def test_it_respects_the_environment_switch(self):
        self._reading(165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            self.assertFalse(catch_up_follower(self._installation(), self.station))

        self.assertEqual(capture.messages, [])

    def test_a_push_failure_is_swallowed(self):
        # The follow already succeeded and is what the user asked for; losing
        # the catch-up is a missed courtesy, not a failed action.
        self._reading(165)

        with patch(
            "api.push._post_batch", side_effect=requests.ConnectionError("down")
        ):
            self.assertFalse(catch_up_follower(self._installation(), self.station))

    def test_a_dead_token_is_cleared(self):
        self._reading(165)
        installation = self._installation()

        def dead(messages):
            return [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]

        with patch("api.push._post_batch", side_effect=dead):
            self.assertFalse(catch_up_follower(installation, self.station))

        installation.refresh_from_db()
        self.assertEqual(installation.push_token, "")

    def test_it_is_recorded_as_a_catch_up_for_audit(self):
        self._reading(165)

        with patch("api.push._post_batch", side_effect=Capture()):
            catch_up_follower(self._installation(), self.station)

        alert = SensorAlert.objects.get()
        self.assertEqual(alert.trend, "catch_up")
        self.assertEqual(alert.level, "unhealthy")
        self.assertEqual(alert.recipients, 1)

    def _alert_rule(self, threshold, title="Aire regular", body="Cuidado en {station}."):
        institution = Institution.objects.create(legal_name="Colegio San Juan")
        return InstitutionAlertRule.objects.create(
            institution=institution,
            station=self.station,
            threshold=threshold,
            push_title=title,
            push_body=body,
        )

    def test_a_firing_institutional_alert_catches_up_below_the_public_levels(self):
        # The whole point of a configurable threshold: an institution alerting
        # from AQI 40 is declaring that air worth interrupting for. Judging a
        # new follower by the public levels alone would leave the leased sensor
        # notifying *less* than a public one.
        self._alert_rule(40)
        self._reading(55)  # "moderate" — silent on the public path
        installation = self._installation()

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            sent = catch_up_follower(installation, self.station)

        self.assertTrue(sent)
        [message] = capture.messages
        self.assertEqual(message["title"], "Aire regular")
        self.assertEqual(message["body"], "Cuidado en Respira: Villa Morra.")

    def test_air_below_the_institutions_threshold_still_says_nothing(self):
        self._alert_rule(40)
        self._reading(30)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            self.assertFalse(catch_up_follower(self._installation(), self.station))

        self.assertEqual(capture.messages, [])

    def test_an_inactive_alert_does_not_catch_anybody_up(self):
        rule = self._alert_rule(40)
        rule.is_active = False
        rule.save(update_fields=["is_active"])
        self._reading(55)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            self.assertFalse(catch_up_follower(self._installation(), self.station))

        self.assertEqual(capture.messages, [])

    def test_another_stations_alert_does_not_apply(self):
        # The audience rule the whole feature turns on, in the catch-up path:
        # a rule configured for one sensor must not put words in another's
        # notification.
        other = Stations.seed_for_tests(
            name="Respira: San Lorenzo",
            region=self.region,
            station_code="RSP-002",
            is_station_on=True,
        )
        institution = Institution.objects.create(legal_name="Otra")
        InstitutionAlertRule.objects.create(
            institution=institution,
            station=other,
            threshold=40,
            push_title="No es para acá",
            push_body="No corresponde.",
        )
        self._reading(55)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            self.assertFalse(catch_up_follower(self._installation(), self.station))

        self.assertEqual(capture.messages, [])

    def test_an_institutions_wording_wins_over_the_public_copy(self):
        # Air bad enough for both paths: the follower gets one notification,
        # in the institution's words, never two near-identical ones.
        self._alert_rule(40, title="Aviso del colegio", body="Recreo suspendido.")
        self._reading(165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            self.assertTrue(catch_up_follower(self._installation(), self.station))

        [message] = capture.messages
        self.assertEqual(message["title"], "Aviso del colegio")
        self.assertEqual(message["body"], "Recreo suspendido.")
        # The payload still routes the app to the station, whoever wrote the copy.
        self.assertEqual(message["data"]["station_code"], "RSP-001")
        self.assertEqual(message["data"]["trend"], "catch_up")

    def test_the_most_severe_matching_alert_is_the_one_caught_up_on(self):
        # An institution's escalating advice, joined mid-episode. The followers
        # who were already here got the caution when the air crossed 40 and the
        # evacuation when it crossed 100; somebody arriving now cannot be given
        # that sequence retroactively, so they get the one that describes the
        # air as it stands.
        institution = Institution.objects.create(legal_name="Colegio San Juan")
        for threshold, title in ((40, "Precaución"), (100, "No salir al patio")):
            InstitutionAlertRule.objects.create(
                institution=institution,
                station=self.station,
                threshold=threshold,
                push_title=title,
                push_body="x",
            )
        self._reading(165)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            catch_up_follower(self._installation(), self.station)

        self.assertEqual(len(capture.messages), 1)
        self.assertEqual(capture.messages[0]["title"], "No salir al patio")

    def test_a_catch_up_only_matches_alerts_the_air_is_actually_over(self):
        institution = Institution.objects.create(legal_name="Colegio San Juan")
        for threshold, title in ((40, "Precaución"), (100, "No salir al patio")):
            InstitutionAlertRule.objects.create(
                institution=institution,
                station=self.station,
                threshold=threshold,
                push_title=title,
                push_body="x",
            )
        self._reading(55)  # over the first, under the second

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            catch_up_follower(self._installation(), self.station)

        self.assertEqual(capture.messages[0]["title"], "Precaución")

    def test_a_catch_up_does_not_advance_the_alerts_state(self):
        # Same reasoning as the station state: the alert's state is what every
        # other follower's next notification is judged against.
        rule = self._alert_rule(40)
        self._reading(55)

        with patch("api.push._post_batch", side_effect=Capture()):
            catch_up_follower(self._installation(), self.station)

        self.assertFalse(
            InstitutionAlertRuleState.objects.filter(rule=rule, is_firing=True).exists()
        )

    def test_the_next_scheduled_run_still_warns_the_original_followers(self):
        # The whole point of not touching the state: a device that joined must
        # not silence the warning everyone else is waiting on.
        self._reading(165)
        first = self._installation("token-a")
        DeviceFollower.objects.create(installation=first, station_code="RSP-001")

        joiner = self._installation("token-b", OTHER_INSTALLATION_ID)

        capture = Capture()
        with patch("api.push._post_batch", side_effect=capture):
            catch_up_follower(joiner, self.station)
            DeviceFollower.objects.create(installation=joiner, station_code="RSP-001")
            send_sensor_alerts()

        # The catch-up to the joiner, then the station's own first warning to
        # both of them.
        self.assertEqual(capture.recipients(), ["token-b", "token-a", "token-b"])


class SensorAlertStateMigrationTests(TransactionTestCase):
    """The deploy that introduces the state table must not re-alert everybody.

    Before it, the last alert in the log *was* the dedup state. Arriving with
    an empty state table would make every station currently over a threshold
    look like it had never alerted, and the first run after deploy would
    notify all of their followers a second time.
    """

    migrate_from = [("api", "0016_sensor_alert")]
    migrate_to = [("api", "0017_sensor_alert_state_and_token_claim")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor.loader.build_graph()
        self.old_apps = executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_the_last_alert_becomes_the_stations_state(self):
        OldAlert = self.old_apps.get_model("api", "SensorAlert")
        OldAlert.objects.create(
            station_code="RSP-001", level="unhealthy", aqi=165, recipients=2
        )
        OldAlert.objects.create(
            station_code="RSP-001", level="hazardous", aqi=320, recipients=2
        )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        executor.loader.build_graph()
        new_apps = executor.loader.project_state(self.migrate_to).apps

        State = new_apps.get_model("api", "SensorAlertState")
        state = State.objects.get(station_code="RSP-001")
        self.assertEqual(state.last_alerted_level, "hazardous")
        self.assertEqual(state.last_level, "hazardous")


class Capture:
    """Stands in for Expo, recording what would have been sent."""

    def __init__(self):
        self.messages: list[dict] = []

    def __call__(self, messages):
        self.messages.extend(messages)
        return ok_tickets(messages)["data"]

    def recipients(self) -> list[str]:
        return [message["to"] for message in self.messages]
