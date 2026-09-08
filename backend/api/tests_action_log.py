"""Tests for the institutional action log endpoints (/api/action-logs/).

Two things are being locked in here. First, the backend — not the client —
decides the two fields that make the history trustworthy: which institution an
entry belongs to and when it was recorded. Second, the isolation boundary: an
institution may only act on its own station, may only cite its own alerts, and
never sees another institution's history.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib import admin
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
    StationReadingsGold,
    Stations,
)

User = get_user_model()


class ActionLogTestCase(APITestCase):
    """Two fully independent institutions, each with its own station and alert."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("action-logs-list")

        region = Regions.seed_for_tests(name="Gran Asuncion", region_code="GA")

        self.institution = Institution.objects.create(legal_name="Hospital Bautista")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            region=region,
            latitude=-25.29,
            longitude=-57.57,
            is_station_on=True,
        )
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            contract_status=InstitutionContract.ContractStatus.ACTIVE,
            start_date=date(2026, 1, 1),
            monthly_fee=Decimal("450.00"),
        )
        self.alert = InstitutionAlert.objects.create(
            institution=self.institution,
            station=self.station,
            aqi_value=155.0,
            alert_threshold=100,
        )
        self.user = User.objects.create_user(
            username="contact@hospitalbautista.org.py",
            email="contact@hospitalbautista.org.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(user=self.user, institution=self.institution)

        self.other_institution = Institution.objects.create(
            legal_name="Colegio San Jose S.A."
        )
        self.other_station = Stations.seed_for_tests(
            name="Respira: Centro",
            region=region,
            latitude=-25.28,
            longitude=-57.48,
            is_station_on=True,
        )
        InstitutionContract.objects.create(
            institution=self.other_institution,
            station=self.other_station,
            contract_status=InstitutionContract.ContractStatus.ACTIVE,
            start_date=date(2026, 1, 1),
        )
        self.other_alert = InstitutionAlert.objects.create(
            institution=self.other_institution,
            station=self.other_station,
            aqi_value=180.0,
            alert_threshold=100,
        )
        self.other_user = User.objects.create_user(
            username="contact@colegiosanjose.edu.py",
            email="contact@colegiosanjose.edu.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(
            user=self.other_user, institution=self.other_institution
        )

        self.unlinked_user = User.objects.create_user(
            username="nobody@example.com",
            email="nobody@example.com",
            password="S3ed!Pass99",
        )

    def post(self, **payload):
        return self.client.post(self.url, payload, format="json")


class ActionLogCreateTests(ActionLogTestCase):
    def test_creating_an_action_for_the_own_station_succeeds(self):
        self.client.force_authenticate(self.user)
        response = self.post(
            station=self.station.id,
            note="Se suspendió la actividad física al aire libre.",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["station"], self.station.id)
        self.assertEqual(body["station_name"], "Respira: Villa Morra")
        self.assertEqual(
            body["note"], "Se suspendió la actividad física al aire libre."
        )
        self.assertEqual(ActionLog.objects.count(), 1)

    def test_creating_an_action_linked_to_an_alert_succeeds(self):
        self.client.force_authenticate(self.user)
        response = self.post(
            station=self.station.id,
            alert=self.alert.id,
            note="Se cerraron las ventanas del ala este.",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["alert"], self.alert.id)
        self.assertEqual(ActionLog.objects.get().alert_id, self.alert.id)

    def test_creating_an_action_without_an_alert_succeeds(self):
        self.client.force_authenticate(self.user)
        response = self.post(
            station=self.station.id, note="Mantenimiento preventivo programado."
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()["alert"])
        self.assertIsNone(ActionLog.objects.get().alert_id)

    def test_institution_is_assigned_from_the_authenticated_user(self):
        self.client.force_authenticate(self.user)
        response = self.post(station=self.station.id, note="Acción registrada.")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["institution"], self.institution.id)
        self.assertEqual(response.json()["institution_name"], "Hospital Bautista")
        self.assertEqual(ActionLog.objects.get().institution_id, self.institution.id)

    def test_a_supplied_institution_is_ignored_not_honoured(self):
        """The payload must never decide who the entry belongs to."""
        self.client.force_authenticate(self.user)
        response = self.post(
            institution=self.other_institution.id,
            station=self.station.id,
            note="Intento de registrar para otra institución.",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ActionLog.objects.get().institution_id, self.institution.id)

    def test_timestamp_is_generated_by_the_backend(self):
        before = timezone.now()
        self.client.force_authenticate(self.user)
        response = self.post(station=self.station.id, note="Acción registrada.")
        after = timezone.now()

        self.assertEqual(response.status_code, 201)
        entry = ActionLog.objects.get()
        self.assertIsNotNone(entry.timestamp)
        self.assertGreaterEqual(entry.timestamp, before)
        self.assertLessEqual(entry.timestamp, after)

    def test_a_supplied_timestamp_cannot_backdate_the_entry(self):
        backdated = timezone.now() - timedelta(days=365)

        self.client.force_authenticate(self.user)
        response = self.post(
            station=self.station.id,
            timestamp=backdated.isoformat(),
            note="Intento de antedatar la acción.",
        )

        self.assertEqual(response.status_code, 201)
        self.assertGreater(ActionLog.objects.get().timestamp, backdated)

    def test_note_is_required(self):
        self.client.force_authenticate(self.user)
        response = self.post(station=self.station.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn("note", response.json())
        self.assertEqual(ActionLog.objects.count(), 0)

    def test_empty_note_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.post(station=self.station.id, note="")

        self.assertEqual(response.status_code, 400)
        self.assertIn("note", response.json())
        self.assertEqual(ActionLog.objects.count(), 0)

    def test_whitespace_only_note_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.post(station=self.station.id, note="   \n  ")

        self.assertEqual(response.status_code, 400)
        self.assertIn("note", response.json())
        self.assertEqual(ActionLog.objects.count(), 0)

    def test_station_is_required(self):
        self.client.force_authenticate(self.user)
        response = self.post(note="Acción sin estación.")

        self.assertEqual(response.status_code, 400)
        self.assertIn("station", response.json())

    def test_nonexistent_station_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.post(
            station=999999, note="Acción sobre una estación inexistente."
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("station", response.json())
        self.assertEqual(ActionLog.objects.count(), 0)


class ActionLogAuthorizationTests(ActionLogTestCase):
    def test_unauthenticated_create_is_rejected(self):
        response = self.post(station=self.station.id, note="Acción anónima.")

        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(ActionLog.objects.count(), 0)

    def test_unauthenticated_list_is_rejected(self):
        response = self.client.get(self.url)

        self.assertIn(response.status_code, (401, 403))

    def test_user_without_an_institution_cannot_create(self):
        self.client.force_authenticate(self.unlinked_user)
        response = self.post(station=self.station.id, note="Acción sin institución.")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ActionLog.objects.count(), 0)

    def test_user_without_an_institution_cannot_list(self):
        self.client.force_authenticate(self.unlinked_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_another_institutions_station_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.post(
            station=self.other_station.id,
            note="Acción sobre la estación de otra institución.",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("station", response.json())
        self.assertEqual(ActionLog.objects.count(), 0)

    def test_another_institutions_alert_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.post(
            station=self.station.id,
            alert=self.other_alert.id,
            note="Acción citando la alerta de otra institución.",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("alert", response.json())
        self.assertEqual(ActionLog.objects.count(), 0)

    def test_nonexistent_alert_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.post(
            station=self.station.id,
            alert=999999,
            note="Acción citando una alerta inexistente.",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("alert", response.json())

    def test_own_alert_on_a_different_station_is_rejected(self):
        """An alert of the caller's institution, but about another station.

        Only reachable once an institution holds more than one station, but the
        combination is inconsistent regardless, so it is refused rather than
        silently stored.
        """
        stray_alert = InstitutionAlert.objects.create(
            institution=self.institution,
            station=self.other_station,
            aqi_value=140.0,
            alert_threshold=100,
        )

        self.client.force_authenticate(self.user)
        response = self.post(
            station=self.station.id,
            alert=stray_alert.id,
            note="Acción con alerta de otra estación.",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("alert", response.json())
        self.assertEqual(ActionLog.objects.count(), 0)


class ActionLogListTests(ActionLogTestCase):
    def test_listing_returns_the_institutions_own_entries(self):
        ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Primera acción."
        )
        ActionLog.objects.create(
            institution=self.institution,
            station=self.station,
            alert=self.alert,
            note="Segunda acción.",
        )

        self.client.force_authenticate(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 2)

    def test_list_entry_exposes_the_documented_fields(self):
        ActionLog.objects.create(
            institution=self.institution,
            station=self.station,
            alert=self.alert,
            note="Se activó el protocolo de calidad del aire.",
        )

        self.client.force_authenticate(self.user)
        entry = self.client.get(self.url).json()["results"][0]

        self.assertEqual(
            set(entry.keys()),
            {
                "id",
                "institution",
                "institution_name",
                "station",
                "station_name",
                "alert",
                # The same alert expanded, so a client listing actions can name
                # the event each one answered without a second request.
                "alert_detail",
                "timestamp",
                "note",
            },
        )
        self.assertEqual(entry["institution"], self.institution.id)
        self.assertEqual(entry["institution_name"], "Hospital Bautista")
        self.assertEqual(entry["station"], self.station.id)
        self.assertEqual(entry["station_name"], "Respira: Villa Morra")
        self.assertEqual(entry["alert"], self.alert.id)
        self.assertIsNotNone(entry["timestamp"])

    def test_entries_are_returned_newest_first(self):
        now = timezone.now()
        oldest = ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Hace tres días."
        )
        middle = ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Ayer."
        )
        newest = ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Hoy."
        )
        # ``timestamp`` is auto_now_add, so the three rows above land within the
        # same instant; spread them out to assert on ordering rather than on
        # insertion order.
        for entry, offset in ((oldest, 3), (middle, 1), (newest, 0)):
            ActionLog.objects.filter(pk=entry.pk).update(
                timestamp=now - timedelta(days=offset)
            )

        self.client.force_authenticate(self.user)
        results = self.client.get(self.url).json()["results"]

        self.assertEqual(
            [entry["id"] for entry in results], [newest.id, middle.id, oldest.id]
        )
        self.assertEqual(results[0]["note"], "Hoy.")

    def test_entries_created_through_the_api_are_listed_newest_first(self):
        self.client.force_authenticate(self.user)
        first = self.post(station=self.station.id, note="Primera.").json()
        second = self.post(station=self.station.id, note="Segunda.").json()

        results = self.client.get(self.url).json()["results"]

        self.assertEqual(
            [entry["id"] for entry in results], [second["id"], first["id"]]
        )

    def test_listing_never_leaks_another_institutions_entries(self):
        own = ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Acción propia."
        )
        foreign = ActionLog.objects.create(
            institution=self.other_institution,
            station=self.other_station,
            note="Acción ajena.",
        )

        self.client.force_authenticate(self.user)
        results = self.client.get(self.url).json()["results"]

        ids = [entry["id"] for entry in results]
        self.assertEqual(ids, [own.id])
        self.assertNotIn(foreign.id, ids)

    def test_each_institution_sees_only_its_own_history(self):
        ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Acción propia."
        )
        ActionLog.objects.create(
            institution=self.other_institution,
            station=self.other_station,
            note="Acción ajena.",
        )

        self.client.force_authenticate(self.other_user)
        results = self.client.get(self.url).json()["results"]

        self.assertEqual([entry["note"] for entry in results], ["Acción ajena."])

    def test_an_institution_without_entries_gets_an_empty_history(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])


class ActionLogSideEffectTests(ActionLogTestCase):
    """The action log records history; it must not rewrite any."""

    def test_creating_an_action_does_not_modify_the_alert(self):
        before = InstitutionAlert.objects.get(pk=self.alert.pk)

        self.client.force_authenticate(self.user)
        self.post(
            station=self.station.id,
            alert=self.alert.id,
            note="Se notificó al personal.",
        )

        after = InstitutionAlert.objects.get(pk=self.alert.pk)
        self.assertEqual(after.aqi_value, before.aqi_value)
        self.assertEqual(after.alert_threshold, before.alert_threshold)
        self.assertEqual(after.triggered_at, before.triggered_at)
        self.assertEqual(after.resolved_at, before.resolved_at)
        self.assertEqual(InstitutionAlert.objects.count(), 2)

    def test_creating_an_action_does_not_modify_stations_or_measurements(self):
        reading = StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=timezone.now(), aqi_pm2_5=155.0
        )

        self.client.force_authenticate(self.user)
        self.post(station=self.station.id, note="Se ventilaron las aulas.")

        self.station.refresh_from_db()
        reading.refresh_from_db()
        self.assertTrue(self.station.is_station_on)
        self.assertEqual(self.station.name, "Respira: Villa Morra")
        self.assertEqual(reading.aqi_pm2_5, 155.0)
        self.assertEqual(StationReadingsGold.objects.count(), 1)

    def test_the_api_offers_no_update_or_delete(self):
        entry = ActionLog.objects.create(
            institution=self.institution, station=self.station, note="Acción original."
        )
        detail_url = f"{self.url}{entry.id}/"

        self.client.force_authenticate(self.user)
        patch = self.client.patch(detail_url, {"note": "Editada."}, format="json")
        delete = self.client.delete(detail_url)

        self.assertIn(patch.status_code, (404, 405))
        self.assertIn(delete.status_code, (404, 405))
        entry.refresh_from_db()
        self.assertEqual(entry.note, "Acción original.")


class ActionLogAdminTests(ActionLogTestCase):
    """The backoffice review of the action history.

    Unlike the API, the admin sees *every* institution's entries — that is the
    point of an administrative audit view — but may not write any of them.
    """

    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(
            email="backoffice@example.com", password="pw-Str0ng!42"
        )
        self.client.force_login(self.superuser)

        self.own_entry = ActionLog.objects.create(
            institution=self.institution,
            station=self.station,
            alert=self.alert,
            note="Se activó el protocolo de calidad del aire.",
        )
        self.foreign_entry = ActionLog.objects.create(
            institution=self.other_institution,
            station=self.other_station,
            note="Se suspendió el recreo.",
        )

        self.changelist_url = reverse("admin:api_actionlog_changelist")

    def changelist(self, **params):
        response = self.client.get(self.changelist_url, params)
        self.assertEqual(response.status_code, 200)
        return list(response.context["cl"].queryset)

    def test_changelist_shows_the_complete_history_across_institutions(self):
        self.assertEqual(set(self.changelist()), {self.own_entry, self.foreign_entry})

    def test_history_is_listed_newest_first(self):
        now = timezone.now()
        ActionLog.objects.filter(pk=self.own_entry.pk).update(
            timestamp=now - timedelta(days=2)
        )
        ActionLog.objects.filter(pk=self.foreign_entry.pk).update(timestamp=now)

        self.assertEqual(self.changelist(), [self.foreign_entry, self.own_entry])

    # --- Search --------------------------------------------------------

    def test_search_by_institution(self):
        self.assertEqual(self.changelist(q="Bautista"), [self.own_entry])

    def test_search_by_station(self):
        self.assertEqual(self.changelist(q="Villa Morra"), [self.own_entry])

    def test_search_by_note(self):
        self.assertEqual(self.changelist(q="recreo"), [self.foreign_entry])

    # --- Filters -------------------------------------------------------

    def test_filter_by_institution(self):
        self.assertEqual(
            self.changelist(institution__id__exact=self.institution.pk),
            [self.own_entry],
        )

    def test_filter_by_station(self):
        self.assertEqual(
            self.changelist(station__id__exact=self.other_station.pk),
            [self.foreign_entry],
        )

    def test_filter_by_alert_association(self):
        self.assertEqual(self.changelist(has_alert="yes"), [self.own_entry])
        self.assertEqual(self.changelist(has_alert="no"), [self.foreign_entry])

    def test_filter_by_timestamp(self):
        ActionLog.objects.filter(pk=self.own_entry.pk).update(
            timestamp=timezone.now() - timedelta(days=30)
        )
        # Same shape the admin's own date-filter links use: an aware datetime,
        # so the comparison happens in the active time zone.
        cutoff = (timezone.now() - timedelta(days=1)).isoformat()

        self.assertEqual(self.changelist(timestamp__gte=cutoff), [self.foreign_entry])

    # --- Immutability ---------------------------------------------------

    def test_the_history_is_read_only_even_for_a_superuser(self):
        model_admin = admin.site._registry[ActionLog]
        request = self.client.get(self.changelist_url).wsgi_request

        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_posting_to_the_change_page_does_not_edit_an_entry(self):
        change_url = reverse("admin:api_actionlog_change", args=[self.own_entry.pk])

        response = self.client.post(
            change_url,
            {
                "institution": self.other_institution.pk,
                "station": self.other_station.pk,
                "note": "Nota reescrita desde el backoffice.",
            },
        )

        self.assertIn(response.status_code, (403, 302))
        self.own_entry.refresh_from_db()
        self.assertEqual(
            self.own_entry.note, "Se activó el protocolo de calidad del aire."
        )
        self.assertEqual(self.own_entry.institution_id, self.institution.pk)

    def test_an_entry_can_be_inspected_with_its_related_records(self):
        change_url = reverse("admin:api_actionlog_change", args=[self.own_entry.pk])

        response = self.client.get(change_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hospital Bautista")
        self.assertContains(response, "Respira: Villa Morra")


class InstitutionAlertAdminTests(ActionLogTestCase):
    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(
            email="backoffice@example.com", password="pw-Str0ng!42"
        )
        self.client.force_login(self.superuser)

    def test_alerts_are_listed_and_searchable(self):
        response = self.client.get(
            reverse("admin:api_institutionalert_changelist"), {"q": "Bautista"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].queryset), [self.alert])
