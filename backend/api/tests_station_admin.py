"""Tests for the Station Administration modules in Django Admin.

Covers the backoffice that replaces the operational Google Spreadsheet and
station_status_seed.csv: the station changelist, the StationDetails inline on
the station page, and the StationOverride module.
"""

from django.contrib import admin
from django.contrib.admin import helpers
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from .admin import DBT_RUN_NOTICE, StationDetailsInline
from .models import Regions, StationDetails, StationOverride, Stations

User = get_user_model()


class StationAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@example.com", password="pw-Str0ng!42"
        )
        self.client.force_login(self.superuser)

        self.asuncion = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.encarnacion = Regions.seed_for_tests(name="Encarnación", region_code="EN")

        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            region=self.asuncion,
            latitude=-25.29,
            longitude=-57.57,
            is_station_on=True,
        )
        self.other_station = Stations.seed_for_tests(
            name="MADES: Costanera",
            region=self.encarnacion,
            latitude=-27.33,
            longitude=-55.87,
            is_station_on=False,
        )

        self.changelist_url = reverse("admin:api_stations_changelist")
        self.change_url = reverse("admin:api_stations_change", args=[self.station.pk])

    def _inline_payload(self, **details):
        """Management form for the StationDetails inline, plus its fields.

        The inline prefix is the OneToOne's related_name ("details").
        """
        payload = {
            "details-TOTAL_FORMS": "1",
            "details-INITIAL_FORMS": "0",
            "details-MIN_NUM_FORMS": "0",
            "details-MAX_NUM_FORMS": "1",
            "details-0-id": "",
            "details-0-station": str(self.station.pk),
        }
        payload.update({f"details-0-{key}": value for key, value in details.items()})
        return payload

    def test_changelist_renders_configured_columns(self):
        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        # The action checkbox comes from the activate/deactivate actions; bulk
        # delete is still unavailable, since stations cannot be deleted at all.
        self.assertEqual(
            list(response.context["cl"].list_display),
            [
                "action_checkbox",
                "name",
                "region",
                "is_station_on",
                "is_pattern_station",
            ],
        )
        self.assertContains(response, "Respira: Villa Morra")
        # Regions render by name rather than as "Regions object (1)".
        self.assertContains(response, "Gran Asunción")

    def test_search_by_station_name(self):
        response = self.client.get(self.changelist_url, {"q": "Villa Morra"})

        results = list(response.context["cl"].result_list)
        self.assertEqual(results, [self.station])

    def test_filter_by_region(self):
        response = self.client.get(
            self.changelist_url, {"region__id__exact": self.encarnacion.pk}
        )

        results = list(response.context["cl"].result_list)
        self.assertEqual(results, [self.other_station])

    def test_filter_by_station_status(self):
        response = self.client.get(self.changelist_url, {"is_station_on__exact": "1"})

        results = list(response.context["cl"].result_list)
        self.assertEqual(results, [self.station])

    def test_station_page_renders_the_details_inline(self):
        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 200)
        inlines = response.context["inline_admin_formsets"]
        self.assertEqual([inline.opts.model for inline in inlines], [StationDetails])
        self.assertIsInstance(inlines[0].opts, StationDetailsInline)
        self.assertIsInstance(inlines[0].opts, admin.StackedInline)

        # A station without details still gets a blank form, and every field of
        # the model is editable in it.
        for field in (
            "serial_number",
            "sensor_type",
            "model",
            "city",
            "specific_location",
            "locality",
            "environment_type",
            "connectivity",
            "power_source",
            "installation_date",
            "responsible",
            "contact_info",
            "notes",
        ):
            self.assertContains(response, f"details-0-{field}")

    def test_station_page_renders_existing_details(self):
        StationDetails.objects.create(station=self.station, serial_number="SN-001")

        response = self.client.get(self.change_url)

        self.assertContains(response, "SN-001")

    def test_details_can_be_created_from_the_station_page(self):
        response = self.client.post(
            self.change_url,
            self._inline_payload(
                serial_number="SN-001",
                sensor_type="PMS5003",
                model="Respira v2",
                city="Asunción",
                specific_location="Azara esq. Estados Unidos",
                locality="Villa Morra",
                environment_type="urban background",
                connectivity="wifi",
                power_source="grid",
                installation_date="2025-03-14",
                responsible="Equipo de campo",
                contact_info="campo@proyectorespira.net",
                notes="Requiere escalera.",
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        details = StationDetails.objects.get(station=self.station)
        self.assertEqual(details.serial_number, "SN-001")
        self.assertEqual(details.responsible, "Equipo de campo")

    def test_details_can_be_edited_from_the_station_page(self):
        details = StationDetails.objects.create(
            station=self.station, serial_number="SN-001"
        )
        payload = self._inline_payload(serial_number="SN-002")
        payload["details-INITIAL_FORMS"] = "1"
        payload["details-0-id"] = str(details.pk)

        self.client.post(self.change_url, payload, follow=True)

        details.refresh_from_db()
        self.assertEqual(details.serial_number, "SN-002")

    def test_station_fields_cannot_be_modified_through_the_admin(self):
        # `stations` is written by the dbt pipeline: even a superuser posting new
        # values for its fields must not change them.
        payload = self._inline_payload(serial_number="SN-001")
        payload.update(
            {
                "name": "Tampered name",
                "region": str(self.encarnacion.pk),
                "latitude": "0",
                "longitude": "0",
                "is_station_on": "on",
                "is_pattern_station": "on",
            }
        )

        self.client.post(self.change_url, payload, follow=True)

        self.station.refresh_from_db()
        self.assertEqual(self.station.name, "Respira: Villa Morra")
        self.assertEqual(self.station.region, self.asuncion)
        self.assertEqual(self.station.latitude, -25.29)
        self.assertEqual(self.station.longitude, -57.57)
        self.assertTrue(self.station.is_station_on)
        self.assertFalse(self.station.is_pattern_station)

    def test_stations_cannot_be_added_or_deleted(self):
        self.assertEqual(
            self.client.get(reverse("admin:api_stations_add")).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                reverse("admin:api_stations_delete", args=[self.station.pk])
            ).status_code,
            403,
        )
        self.assertEqual(Stations.objects.count(), 2)


class StationStatusOverrideActionTests(TestCase):
    """Activate / Deactivate on the station changelist.

    A station's status is owned by the dbt pipeline, so these actions only
    record the operator's decision as a StationOverride: `stations` is never
    written, and the operator is told a dbt run is needed for it to land.
    """

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@example.com", password="pw-Str0ng!42"
        )
        self.client.force_login(self.superuser)

        # Migration 0006 seeds the three stations that station_status_seed.csv
        # held off. Clear them so each test asserts only on the rows it creates;
        # the seeding itself is covered by tests_station_migrations.
        StationOverride.objects.all().delete()

        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            station_code="airelibre_d87553",
            region=self.region,
            is_station_on=True,
        )
        self.changelist_url = reverse("admin:api_stations_changelist")

    def _post(self, action, confirm=False, note=None, stations=None):
        payload = {
            "action": action,
            helpers.ACTION_CHECKBOX_NAME: [
                str(station.pk) for station in (stations or [self.station])
            ],
        }
        if confirm:
            payload["confirm"] = "yes"
        if note is not None:
            payload["note"] = note
        return self.client.post(self.changelist_url, payload)

    def _messages(self, response):
        return [str(message) for message in get_messages(response.wsgi_request)]

    def test_both_actions_are_offered_on_the_changelist(self):
        response = self.client.get(self.changelist_url)

        self.assertEqual(
            sorted(response.context["action_form"].fields["action"].choices)[1:],
            [
                ("activate_stations", "Activate selected stations"),
                ("deactivate_stations", "Deactivate selected stations"),
            ],
        )

    def test_deactivating_asks_for_confirmation_before_changing_anything(self):
        response = self._post("deactivate_stations")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Respira: Villa Morra")
        self.assertContains(response, "airelibre_d87553")
        self.assertContains(response, DBT_RUN_NOTICE)
        # Nothing is written until the operator confirms.
        self.assertFalse(StationOverride.objects.exists())

    def test_the_confirmation_page_explains_what_each_action_does(self):
        # `is_station_on` is derived by the pipeline from the source status *and*
        # recent readings, so an override can hold a station off but cannot bring
        # a silent one back. The operator has to be told which is about to happen.
        deactivating = self._post("deactivate_stations")
        self.assertContains(deactivating, "will be held inactive")

        activating = self._post("activate_stations")
        self.assertContains(activating, "The forced shutdown is lifted")
        self.assertContains(
            activating, "does not bring back a sensor that stopped reporting"
        )

    def test_deactivating_records_an_override(self):
        response = self._post(
            "deactivate_stations", confirm=True, note="Sensor retired from the site"
        )

        override = StationOverride.objects.get(station_code="airelibre_d87553")
        self.assertEqual(override.field, StationOverride.STATUS_FIELD)
        self.assertEqual(override.value, StationOverride.Status.INACTIVE)
        self.assertEqual(override.note, "Sensor retired from the site")
        # Unprocessed, so the next pipeline run picks it up.
        self.assertFalse(override.processed)
        self.assertRedirects(response, self.changelist_url)

    def test_activating_records_an_override(self):
        self._post("activate_stations", confirm=True, note="Back online after repair")

        override = StationOverride.objects.get(station_code="airelibre_d87553")
        self.assertEqual(override.field, StationOverride.STATUS_FIELD)
        self.assertEqual(override.value, StationOverride.Status.ACTIVE)

    def test_reactivating_updates_the_existing_override(self):
        self._post("deactivate_stations", confirm=True, note="Sensor retired")
        StationOverride.objects.update(processed=True)

        self._post("activate_stations", confirm=True, note="Back online after repair")

        # One row per station and field, rewritten in place — not a second row
        # the pipeline would have to disambiguate.
        override = StationOverride.objects.get(station_code="airelibre_d87553")
        self.assertEqual(StationOverride.objects.count(), 1)
        self.assertEqual(override.value, StationOverride.Status.ACTIVE)
        self.assertEqual(override.note, "Back online after repair")
        self.assertFalse(override.processed)

    def test_the_reason_is_mandatory(self):
        response = self._post("deactivate_stations", confirm=True, note="   ")

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "note", "This field is required."
        )
        self.assertFalse(StationOverride.objects.exists())

    def test_a_successful_operation_reports_the_dbt_run_requirement(self):
        response = self._post(
            "deactivate_stations", confirm=True, note="Sensor retired"
        )

        self.assertIn(DBT_RUN_NOTICE, self._messages(response))

    def test_the_stations_table_is_never_written(self):
        self._post("deactivate_stations", confirm=True, note="Sensor retired")

        self.station.refresh_from_db()
        self.assertTrue(self.station.is_station_on)

    def test_a_station_without_a_code_cannot_be_overridden(self):
        # Only possible before the pipeline has rebuilt `stations` with the
        # station_code column.
        unmapped = Stations.seed_for_tests(name="MADES: Costanera", region=self.region)

        response = self._post("deactivate_stations", stations=[self.station, unmapped])

        # The whole selection is refused: applying it to part of it would leave
        # the operator with no indication that a station was skipped.
        self.assertRedirects(response, self.changelist_url)
        self.assertFalse(StationOverride.objects.exists())
        self.assertIn(
            "No station code on: MADES: Costanera. The pipeline sets it; wait "
            "for the next dbt run.",
            self._messages(response),
        )

    def test_several_stations_are_overridden_at_once(self):
        other = Stations.seed_for_tests(
            name="MADES: Costanera",
            station_code="mades_open_ic08p0002",
            region=self.region,
        )

        self._post(
            "deactivate_stations",
            confirm=True,
            note="Network maintenance",
            stations=[self.station, other],
        )

        self.assertEqual(
            sorted(StationOverride.objects.values_list("station_code", flat=True)),
            ["airelibre_d87553", "mades_open_ic08p0002"],
        )

    def test_the_actions_require_permission_to_write_overrides(self):
        viewer = User.objects.create_user(
            email="viewer@example.com", password="pw-Str0ng!42", is_staff=True
        )
        viewer.user_permissions.add(
            *Permission.objects.filter(
                codename__in=("view_stations", "view_stationoverride")
            )
        )
        self.client.force_login(viewer)

        # No actions are offered at all, and posting one anyway writes nothing.
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["action_form"])

        self._post("deactivate_stations", confirm=True, note="Sensor retired")
        self.assertFalse(StationOverride.objects.exists())


class StationOverrideAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@example.com", password="pw-Str0ng!42"
        )
        self.client.force_login(self.superuser)

        # Migration 0006 seeds the three stations that station_status_seed.csv
        # held off. Clear them so each test asserts only on the rows it creates;
        # the seeding itself is covered by tests_station_migrations.
        StationOverride.objects.all().delete()

        self.override = StationOverride.objects.create(
            station_code="airelibre_d87553",
            field="status",
            value="inactive",
            note="FP-UNA San Lorenzo: inconsistent data",
        )
        self.changelist_url = reverse("admin:api_stationoverride_changelist")

    def test_changelist_renders_configured_columns(self):
        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        columns = [field for field in response.context["cl"].list_display]
        self.assertEqual(
            columns,
            [
                "action_checkbox",
                "station_code",
                "field",
                "value",
                "change_date",
                "processed",
            ],
        )
        self.assertContains(response, "airelibre_d87553")

    def test_search_by_station_code(self):
        StationOverride.objects.create(
            station_code="mades_open_ic08p0002", field="status", value="inactive"
        )

        response = self.client.get(self.changelist_url, {"q": "airelibre"})

        self.assertEqual(list(response.context["cl"].result_list), [self.override])

    def test_filter_by_processed(self):
        processed = StationOverride.objects.create(
            station_code="mades_open_ic08p0002",
            field="status",
            value="inactive",
            processed=True,
        )

        response = self.client.get(self.changelist_url, {"processed__exact": "1"})

        self.assertEqual(list(response.context["cl"].result_list), [processed])

    def test_override_can_be_created_from_the_admin(self):
        self.client.post(
            reverse("admin:api_stationoverride_add"),
            {
                "station_code": "mades_open_lvafyatdnok8ew",
                "field": "status",
                "value": "inactive",
                "note": "Shut down by MADES request",
                "change_date_0": "2026-07-29",
                "change_date_1": "12:00:00",
            },
            follow=True,
        )

        created = StationOverride.objects.get(station_code="mades_open_lvafyatdnok8ew")
        self.assertEqual(created.value, "inactive")
        # `processed` is owned by the pipeline, so it starts false and is not
        # part of the form.
        self.assertFalse(created.processed)

    def test_processed_is_read_only(self):
        change_url = reverse(
            "admin:api_stationoverride_change", args=[self.override.pk]
        )

        self.client.post(
            change_url,
            {
                "station_code": self.override.station_code,
                "field": self.override.field,
                "value": self.override.value,
                "note": self.override.note,
                "change_date_0": "2026-07-29",
                "change_date_1": "12:00:00",
                "processed": "on",
            },
            follow=True,
        )

        self.override.refresh_from_db()
        self.assertFalse(self.override.processed)


class RegionsAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@example.com", password="pw-Str0ng!42"
        )
        self.client.force_login(self.superuser)
        Regions.seed_for_tests(name="Gran Asunción", region_code="GA")

    def test_changelist_renders(self):
        response = self.client.get(reverse("admin:api_regions_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gran Asunción")

    def test_regions_stay_fully_read_only(self):
        # Unlike Stations, Regions has no editable inline, so it keeps the
        # ReadOnlyModelAdmin contract.
        self.assertEqual(
            self.client.get(reverse("admin:api_regions_add")).status_code, 403
        )

    def test_admin_index_lists_every_station_module(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:api_stations_changelist"))
        self.assertContains(response, reverse("admin:api_regions_changelist"))
        self.assertContains(response, reverse("admin:api_stationoverride_changelist"))
