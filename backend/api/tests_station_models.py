"""Tests for the admin-owned station models (StationDetails, StationOverride).

These models are written by the backoffice, not by the dbt gold pipeline, so
what matters here is that the schema persists every documented field and that
the uniqueness rules hold at the database level.
"""

from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Regions, StationDetails, StationOverride, Stations


class StationDetailsModelTests(TestCase):
    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            region=self.region,
            latitude=-25.29,
            longitude=-57.57,
        )

    def test_details_are_reachable_from_the_station(self):
        details = StationDetails.objects.create(
            station=self.station, serial_number="SN-001"
        )

        self.station.refresh_from_db()
        self.assertEqual(self.station.details, details)
        self.assertEqual(details.station, self.station)

    def test_every_documented_field_persists(self):
        StationDetails.objects.create(
            station=self.station,
            serial_number="SN-001",
            sensor_type="PMS5003",
            model="Respira v2",
            city="Asunción",
            specific_location="Azara esq. Estados Unidos, poste municipal",
            locality="Villa Morra",
            environment_type="urban background",
            connectivity="wifi",
            power_source="grid",
            installation_date=date(2025, 3, 14),
            responsible="Equipo de campo",
            contact_info="campo@proyectorespira.net / +595 981 000000",
            notes="Requiere escalera para el mantenimiento.",
        )

        details = StationDetails.objects.get(station=self.station)
        self.assertEqual(details.serial_number, "SN-001")
        self.assertEqual(details.sensor_type, "PMS5003")
        self.assertEqual(details.model, "Respira v2")
        self.assertEqual(details.city, "Asunción")
        self.assertEqual(
            details.specific_location, "Azara esq. Estados Unidos, poste municipal"
        )
        self.assertEqual(details.locality, "Villa Morra")
        self.assertEqual(details.environment_type, "urban background")
        self.assertEqual(details.connectivity, "wifi")
        self.assertEqual(details.power_source, "grid")
        self.assertEqual(details.installation_date, date(2025, 3, 14))
        self.assertEqual(details.responsible, "Equipo de campo")
        self.assertEqual(
            details.contact_info, "campo@proyectorespira.net / +595 981 000000"
        )
        self.assertEqual(details.notes, "Requiere escalera para el mantenimiento.")

    def test_descriptive_fields_are_optional(self):
        # Operators load the spreadsheet data incrementally, so a record with
        # only the station attached must be valid.
        details = StationDetails.objects.create(station=self.station)

        self.assertEqual(details.serial_number, "")
        self.assertIsNone(details.installation_date)

    def test_one_details_record_per_station(self):
        StationDetails.objects.create(station=self.station)

        # The unique index backing the OneToOne is enforced in the database even
        # though the physical FOREIGN KEY is disabled (dbt recreates `stations`).
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StationDetails.objects.create(station=self.station)

    def test_details_do_not_add_a_foreign_key_to_the_dbt_table(self):
        # A FOREIGN KEY against `stations` would break the dbt run that drops
        # and recreates it, so the relation must stay constraint-free.
        field = StationDetails._meta.get_field("station")
        self.assertFalse(field.db_constraint)
        self.assertTrue(field.one_to_one)

    def test_str_identifies_the_station(self):
        details = StationDetails.objects.create(station=self.station)

        self.assertEqual(str(details), "Details for Respira: Villa Morra")


class StationOverrideModelTests(TestCase):
    """StationOverride replaces station_status_seed.csv, whose rows were
    ``station_code,status,note`` — the same shape this model persists."""

    def setUp(self):
        # Migration 0006 seeds the three stations that the CSV held off. Clear
        # them so each test asserts only on the rows it creates; the seeding
        # itself is covered by tests_station_migrations.
        StationOverride.objects.all().delete()

    def test_every_documented_field_persists(self):
        override = StationOverride.objects.create(
            station_code="mades_open_ic08p0002",
            field="status",
            value="inactive",
            note="Costanera Asunción: shut down by MADES request",
        )

        override.refresh_from_db()
        self.assertEqual(override.station_code, "mades_open_ic08p0002")
        self.assertEqual(override.field, "status")
        self.assertEqual(override.value, "inactive")
        self.assertEqual(
            override.note, "Costanera Asunción: shut down by MADES request"
        )
        self.assertIsNotNone(override.change_date)
        self.assertFalse(override.processed)

    def test_note_is_optional(self):
        override = StationOverride.objects.create(
            station_code="airelibre_d87553", field="status", value="inactive"
        )

        self.assertEqual(override.note, "")

    def test_same_station_and_field_cannot_be_overridden_twice(self):
        StationOverride.objects.create(
            station_code="airelibre_d87553", field="status", value="inactive"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StationOverride.objects.create(
                    station_code="airelibre_d87553", field="status", value="active"
                )

    def test_a_station_can_override_several_distinct_fields(self):
        StationOverride.objects.create(
            station_code="airelibre_d87553", field="status", value="inactive"
        )
        StationOverride.objects.create(
            station_code="airelibre_d87553",
            field="is_pattern_station",
            value="true",
        )

        self.assertEqual(
            StationOverride.objects.filter(station_code="airelibre_d87553").count(), 2
        )

    def test_overrides_are_listed_most_recent_first(self):
        older = StationOverride.objects.create(
            station_code="a", field="status", value="inactive"
        )
        newer = StationOverride.objects.create(
            station_code="b", field="status", value="active"
        )
        older.change_date = newer.change_date - timedelta(days=1)
        older.save(update_fields=["change_date"])

        self.assertEqual(list(StationOverride.objects.all()), [newer, older])

    def test_str_describes_the_override(self):
        override = StationOverride.objects.create(
            station_code="airelibre_d87553", field="status", value="inactive"
        )

        self.assertEqual(str(override), "airelibre_d87553: status = inactive")
