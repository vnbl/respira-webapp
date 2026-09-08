"""Tests for the Sensor Registry import command.

The spreadsheet is maintained by hand, so what matters is that the command
survives its shape: Spanish headers with accents, mixed date formats, blank
cells, names that don't carry the pipeline's source prefix, rows for stations
that don't exist, and being run twice.
"""

import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Regions, StationDetails, Stations

HEADERS = (
    "Estación,N° de serie,Tipo de Sensor,Modelo,Ciudad,Ubicación específica,"
    "Localidad,Tipo de entorno,Prioridad,Conectividad,Energía,"
    "Fecha instalación,Responsable,Contacto,Notas"
)


class ImportStationDetailsTests(TestCase):
    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asunción", region_code="GA")
        # The gold pipeline prefixes names by source; the sheet holds the bare name.
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra", region=self.region, is_station_on=True
        )

    def _run(self, csv_text, *args):
        path = Path(tempfile.mkdtemp()) / "registry.csv"
        path.write_text(csv_text, encoding="utf-8")
        out, err = StringIO(), StringIO()
        call_command("import_station_details", str(path), *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_every_spreadsheet_field_is_mapped(self):
        self._run(
            f"{HEADERS}\n"
            "Villa Morra,SN-001,PMS5003,Respira v2,Asunción,"
            "Azara esq. Estados Unidos,Villa Morra,urbano de fondo,Alta,wifi,"
            "red eléctrica,2025-03-14,Equipo de campo,campo@proyectorespira.net,"
            "Requiere escalera.\n"
        )

        details = StationDetails.objects.get(station=self.station)
        self.assertEqual(details.serial_number, "SN-001")
        self.assertEqual(details.sensor_type, "PMS5003")
        self.assertEqual(details.model, "Respira v2")
        self.assertEqual(details.city, "Asunción")
        self.assertEqual(details.specific_location, "Azara esq. Estados Unidos")
        self.assertEqual(details.locality, "Villa Morra")
        self.assertEqual(details.environment_type, "urbano de fondo")
        self.assertEqual(details.connectivity, "wifi")
        self.assertEqual(details.power_source, "red eléctrica")
        self.assertEqual(details.installation_date, date(2025, 3, 14))
        self.assertEqual(details.responsible, "Equipo de campo")
        self.assertEqual(details.contact_info, "campo@proyectorespira.net")
        self.assertEqual(details.notes, "Requiere escalera.")

    def test_rows_are_linked_to_the_right_station(self):
        other = Stations.seed_for_tests(name="MADES: Costanera", region=self.region)

        self._run("Estación,N° de serie\nVilla Morra,SN-001\nCostanera,SN-002\n")

        self.assertEqual(
            StationDetails.objects.get(station=self.station).serial_number, "SN-001"
        )
        self.assertEqual(
            StationDetails.objects.get(station=other).serial_number, "SN-002"
        )

    def test_headers_are_matched_despite_accents_and_case(self):
        self._run("ESTACION,No de serie,ENERGIA\nVilla Morra,SN-001,solar\n")

        details = StationDetails.objects.get(station=self.station)
        self.assertEqual(details.serial_number, "SN-001")
        self.assertEqual(details.power_source, "solar")

    def test_blank_cells_never_erase_stored_values(self):
        StationDetails.objects.create(
            station=self.station, serial_number="SN-001", notes="Requiere escalera."
        )

        self._run("Estación,N° de serie,Notas\nVilla Morra,SN-002,\n")

        details = StationDetails.objects.get(station=self.station)
        self.assertEqual(details.serial_number, "SN-002")
        self.assertEqual(details.notes, "Requiere escalera.")

    def test_day_first_dates_are_understood(self):
        self._run("Estación,Fecha instalación\nVilla Morra,14/03/2025\n")

        self.assertEqual(
            StationDetails.objects.get(station=self.station).installation_date,
            date(2025, 3, 14),
        )

    def test_an_unreadable_date_does_not_lose_the_rest_of_the_row(self):
        _, err = self._run(
            "Estación,N° de serie,Fecha instalación\nVilla Morra,SN-001,marzo\n"
        )

        details = StationDetails.objects.get(station=self.station)
        self.assertEqual(details.serial_number, "SN-001")
        self.assertIsNone(details.installation_date)
        self.assertIn("cannot read installation date", err)

    def test_running_twice_updates_instead_of_duplicating(self):
        self._run("Estación,N° de serie\nVilla Morra,SN-001\n")

        out, _ = self._run("Estación,N° de serie\nVilla Morra,SN-002\n")

        self.assertEqual(StationDetails.objects.count(), 1)
        self.assertEqual(
            StationDetails.objects.get(station=self.station).serial_number, "SN-002"
        )
        self.assertIn("1 updated", out)

    def test_rows_for_unknown_stations_are_reported_and_skipped(self):
        out, err = self._run(
            "Estación,N° de serie\nVilla Morra,SN-001\nEstación Fantasma,SN-002\n"
        )

        self.assertEqual(StationDetails.objects.count(), 1)
        self.assertIn("no station matches 'Estación Fantasma'", err)
        self.assertIn("1 skipped", out)

    def test_an_ambiguous_name_is_skipped_rather_than_guessed(self):
        # Two stations whose names both end in ": Villa Morra".
        Stations.seed_for_tests(name="MADES: Villa Morra", region=self.region)

        out, err = self._run("Estación,N° de serie\nVilla Morra,SN-001\n")

        self.assertFalse(StationDetails.objects.exists())
        self.assertIn("matches", err)
        self.assertIn("1 skipped", out)

    def test_a_row_without_a_station_name_is_skipped(self):
        _, err = self._run("Estación,N° de serie\n,SN-001\n")

        self.assertFalse(StationDetails.objects.exists())
        self.assertIn("no station name", err)

    def test_dbt_managed_station_fields_are_never_written(self):
        self._run("Estación,N° de serie,Ciudad\nVilla Morra,SN-001,Asunción\n")

        self.station.refresh_from_db()
        self.assertEqual(self.station.name, "Respira: Villa Morra")
        self.assertEqual(self.station.region, self.region)
        self.assertTrue(self.station.is_station_on)

    def test_dry_run_reports_the_matching_without_writing(self):
        out, _ = self._run("Estación,N° de serie\nVilla Morra,SN-001\n", "--dry-run")

        self.assertFalse(StationDetails.objects.exists())
        self.assertIn("Dry run", out)
        self.assertIn("1 created", out)
        # The report names both sides of the match, so it can be reviewed.
        self.assertIn("'Villa Morra' -> Respira: Villa Morra", out)

    def test_columns_with_no_field_are_reported(self):
        out, _ = self._run(
            "Estación,N° de serie,Prioridad,Color favorito\n"
            "Villa Morra,SN-001,Alta,azul\n"
        )

        # "Prioridad" is a known sheet column with no model field, so it stays
        # quiet; a genuinely unrecognised one is surfaced.
        self.assertIn("Color favorito", out)
        self.assertNotIn("Prioridad", out)

    def test_an_empty_csv_is_an_error(self):
        with self.assertRaises(CommandError):
            self._run("Estación,N° de serie\n")

    def test_a_missing_file_is_an_error(self):
        with self.assertRaises(CommandError):
            call_command("import_station_details", "/nonexistent/registry.csv")
