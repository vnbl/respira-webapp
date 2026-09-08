"""Tests for the Sensor Leasing models (Institution, InstitutionContract).

Like StationDetails/StationOverride (see tests_station_models.py), these
models are admin-owned rather than written by the dbt pipeline, so what
matters here is that the schema persists every documented field and that the
one-to-one uniqueness rules hold at the database level.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import (
    Institution,
    InstitutionContract,
    InstitutionUser,
    Regions,
    Stations,
    get_institution_for_user,
)

User = get_user_model()


class InstitutionModelTests(TestCase):
    def test_every_documented_field_persists(self):
        institution = Institution.objects.create(
            legal_name="Colegio San Jose S.A.",
            display_name="Colegio San Jose",
            institution_type="school",
            contact_name="Maria Gonzalez",
            contact_email="maria@colegiosanjose.edu.py",
            contact_phone="+595 981 000000",
            address="Av. Mariscal Lopez 1234",
            city="Asuncion",
            notes="Renueva contrato cada marzo.",
        )

        institution.refresh_from_db()
        self.assertEqual(institution.legal_name, "Colegio San Jose S.A.")
        self.assertEqual(institution.display_name, "Colegio San Jose")
        self.assertEqual(institution.institution_type, "school")
        self.assertEqual(institution.contact_name, "Maria Gonzalez")
        self.assertEqual(institution.contact_email, "maria@colegiosanjose.edu.py")
        self.assertEqual(institution.contact_phone, "+595 981 000000")
        self.assertEqual(institution.address, "Av. Mariscal Lopez 1234")
        self.assertEqual(institution.city, "Asuncion")
        self.assertEqual(institution.notes, "Renueva contrato cada marzo.")

    def test_only_legal_name_is_required(self):
        institution = Institution.objects.create(legal_name="Hospital Bautista")

        self.assertEqual(institution.display_name, "")
        self.assertEqual(institution.contact_email, "")

    def test_str_prefers_display_name(self):
        with_display = Institution.objects.create(
            legal_name="Colegio San Jose S.A.", display_name="Colegio San Jose"
        )
        without_display = Institution.objects.create(legal_name="Hospital Bautista")

        self.assertEqual(str(with_display), "Colegio San Jose")
        self.assertEqual(str(without_display), "Hospital Bautista")


class InstitutionContractModelTests(TestCase):
    def setUp(self):
        self.region = Regions.seed_for_tests(name="Gran Asuncion", region_code="GA")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            region=self.region,
            latitude=-25.29,
            longitude=-57.57,
        )
        self.other_station = Stations.seed_for_tests(
            name="Respira: Recoleta",
            region=self.region,
            latitude=-25.28,
            longitude=-57.58,
        )
        self.institution = Institution.objects.create(legal_name="Hospital Bautista")
        self.other_institution = Institution.objects.create(
            legal_name="Colegio San Jose S.A."
        )

    def test_every_documented_field_persists(self):
        contract = InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            contract_status=InstitutionContract.ContractStatus.ACTIVE,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            monthly_fee=Decimal("450.00"),
            signed_contract_url="https://drive.example.com/contracts/hb-2026.pdf",
        )

        contract.refresh_from_db()
        self.assertEqual(contract.institution, self.institution)
        self.assertEqual(contract.station, self.station)
        self.assertEqual(contract.contract_status, "active")
        self.assertEqual(contract.start_date, date(2026, 1, 1))
        self.assertEqual(contract.end_date, date(2026, 12, 31))
        self.assertEqual(contract.monthly_fee, Decimal("450.00"))
        self.assertEqual(
            contract.signed_contract_url,
            "https://drive.example.com/contracts/hb-2026.pdf",
        )
        self.assertIsNotNone(contract.created_at)
        self.assertIsNotNone(contract.updated_at)

    def test_defaults_to_draft_status(self):
        contract = InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            start_date=date(2026, 1, 1),
        )

        self.assertEqual(contract.contract_status, "draft")
        self.assertIsNone(contract.end_date)
        self.assertIsNone(contract.monthly_fee)
        self.assertEqual(contract.signed_contract_url, "")

    def test_updated_at_changes_on_save(self):
        contract = InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            start_date=date(2026, 1, 1),
        )
        first_updated_at = contract.updated_at

        contract.contract_status = InstitutionContract.ContractStatus.ACTIVE
        contract.save()

        self.assertGreater(contract.updated_at, first_updated_at)

    def test_an_institution_cannot_have_two_contracts(self):
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            start_date=date(2026, 1, 1),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InstitutionContract.objects.create(
                    institution=self.institution,
                    station=self.other_station,
                    start_date=date(2026, 1, 1),
                )

    def test_a_station_cannot_be_bound_to_two_contracts(self):
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            start_date=date(2026, 1, 1),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InstitutionContract.objects.create(
                    institution=self.other_institution,
                    station=self.station,
                    start_date=date(2026, 1, 1),
                )

    def test_contract_does_not_add_a_foreign_key_to_the_dbt_table(self):
        # Same reasoning as StationDetails: a FOREIGN KEY against `stations`
        # would break the dbt run that drops and recreates it.
        field = InstitutionContract._meta.get_field("station")
        self.assertFalse(field.db_constraint)
        self.assertTrue(field.one_to_one)

    def test_str_describes_the_contract(self):
        contract = InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            start_date=date(2026, 1, 1),
        )

        self.assertEqual(str(contract), "Hospital Bautista — Respira: Villa Morra")


class InstitutionUserModelTests(TestCase):
    """Tests for the User <-> Institution link and its resolver helper."""

    def setUp(self):
        self.institution = Institution.objects.create(legal_name="Hospital Bautista")
        self.other_institution = Institution.objects.create(
            legal_name="Colegio San Jose S.A."
        )
        self.user = User.objects.create_user(
            username="contact@hospitalbautista.org.py",
            email="contact@hospitalbautista.org.py",
            password="S3ed!Pass99",
        )

    def test_links_a_user_to_an_institution(self):
        link = InstitutionUser.objects.create(
            user=self.user, institution=self.institution
        )

        link.refresh_from_db()
        self.assertEqual(link.user, self.user)
        self.assertEqual(link.institution, self.institution)

    def test_an_institution_can_have_several_users(self):
        second_user = User.objects.create_user(
            username="other@hospitalbautista.org.py",
            email="other@hospitalbautista.org.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(user=self.user, institution=self.institution)
        InstitutionUser.objects.create(user=second_user, institution=self.institution)

        self.assertEqual(
            InstitutionUser.objects.filter(institution=self.institution).count(), 2
        )

    def test_a_user_cannot_be_linked_to_two_institutions(self):
        InstitutionUser.objects.create(user=self.user, institution=self.institution)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InstitutionUser.objects.create(
                    user=self.user, institution=self.other_institution
                )

    def test_str_describes_the_link(self):
        link = InstitutionUser.objects.create(
            user=self.user, institution=self.institution
        )

        self.assertEqual(str(link), f"{self.user} → {self.institution}")

    def test_resolver_returns_the_linked_institution(self):
        InstitutionUser.objects.create(user=self.user, institution=self.institution)

        self.assertEqual(get_institution_for_user(self.user), self.institution)

    def test_resolver_returns_none_for_a_user_without_a_link(self):
        self.assertIsNone(get_institution_for_user(self.user))

    def test_resolver_returns_none_for_an_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertIsNone(get_institution_for_user(AnonymousUser()))

    def test_resolver_returns_none_for_none(self):
        self.assertIsNone(get_institution_for_user(None))
