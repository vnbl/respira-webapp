"""Tests for the institutional dashboard endpoint (/api/institution/).

Covers the authorization boundary the ticket cares about: an authenticated
user may only ever see the Institution their InstitutionUser link points to,
never another institution's data, and an anonymous request never gets in.
"""

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.test import APITestCase

from .models import (
    Institution,
    InstitutionAlertConfig,
    InstitutionContract,
    InstitutionUser,
    Regions,
    SensitiveGroup,
    StationDetails,
    StationReadingsGold,
    Stations,
)

User = get_user_model()


class InstitutionDashboardTests(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.institution = Institution.objects.create(legal_name="Hospital Bautista")
        self.other_institution = Institution.objects.create(
            legal_name="Colegio San Jose S.A."
        )

        region = Regions.seed_for_tests(name="Gran Asuncion", region_code="GA")
        station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            region=region,
            latitude=-25.29,
            longitude=-57.57,
        )
        InstitutionContract.objects.create(
            institution=self.institution,
            station=station,
            contract_status=InstitutionContract.ContractStatus.ACTIVE,
            start_date=date(2026, 1, 1),
            monthly_fee=Decimal("450.00"),
        )

        self.user = User.objects.create_user(
            username="contact@hospitalbautista.org.py",
            email="contact@hospitalbautista.org.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(user=self.user, institution=self.institution)

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

        self.me_url = reverse("institution-me")
        self.list_url = reverse("institution-list")

    def _detail_url(self, institution_id):
        return reverse("institution-detail", args=[institution_id])

    # --- Unauthenticated -------------------------------------------------

    def test_unauthenticated_me_is_rejected(self):
        response = self.client.get(self.me_url)
        self.assertIn(response.status_code, (401, 403))

    def test_unauthenticated_list_is_rejected(self):
        response = self.client.get(self.list_url)
        self.assertIn(response.status_code, (401, 403))

    def test_unauthenticated_detail_is_rejected(self):
        response = self.client.get(self._detail_url(self.institution.id))
        self.assertIn(response.status_code, (401, 403))

    # --- Authenticated without an institution link ------------------------

    def test_authenticated_user_without_institution_is_forbidden(self):
        self.client.force_authenticate(self.unlinked_user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 403)

    # --- Authenticated, own institution ------------------------------------

    def test_me_returns_own_institution_with_contract(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], self.institution.id)
        self.assertEqual(body["legal_name"], "Hospital Bautista")
        self.assertEqual(body["contract"]["contract_status"], "active")
        self.assertEqual(body["contract"]["station_name"], "Respira: Villa Morra")

    def test_retrieve_own_institution_by_id_succeeds(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self._detail_url(self.institution.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.institution.id)

    def test_list_returns_only_own_institution(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        results = response.json()
        ids = [item["id"] for item in results]
        self.assertEqual(ids, [self.institution.id])

    def test_institution_without_a_contract_returns_null_contract(self):
        contractless = Institution.objects.create(legal_name="Colegio Nuevo")
        contact = User.objects.create_user(
            username="contacto@colegionuevo.edu.py",
            email="contacto@colegionuevo.edu.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(user=contact, institution=contractless)

        self.client.force_authenticate(contact)
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["contract"])

    # --- Authenticated, another institution's resource ---------------------

    def test_retrieve_another_institutions_detail_is_forbidden(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self._detail_url(self.other_institution.id))

        self.assertEqual(response.status_code, 403)

    def test_list_never_leaks_another_institution(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.list_url)

        ids = [item["id"] for item in response.json()]
        self.assertNotIn(self.other_institution.id, ids)


class InstitutionLoginTests(APITestCase):
    """Tests for /api/institution/login/ and /logout/.

    Unlike the rest of this file, these use a real ``APIClient`` session
    (never ``force_authenticate``) so a passing test proves the login view
    actually establishes a Django session an institutional user can browse
    the dashboard with — the same mechanism the admin login form uses.
    """

    def setUp(self):
        self.client = APIClient()

        self.institution = Institution.objects.create(legal_name="Hospital Bautista")
        self.user = User.objects.create_user(
            username="dashboard@hospitalbautista.org.py",
            email="dashboard@hospitalbautista.org.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(user=self.user, institution=self.institution)

        # A platform user who is not tied to any institution (e.g. an admin
        # account created for the backoffice, or simply a stray account).
        self.staff_user = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="Adm1n!Pass99",
        )

        self.login_url = reverse("institution-login")
        self.logout_url = reverse("institution-logout")
        self.me_url = reverse("institution-me")

    def test_valid_credentials_log_in_and_return_the_institution(self):
        response = self.client.post(
            self.login_url,
            {"email": "dashboard@hospitalbautista.org.py", "password": "S3ed!Pass99"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.institution.id)

    def test_login_establishes_a_usable_session(self):
        self.client.post(
            self.login_url,
            {"email": "dashboard@hospitalbautista.org.py", "password": "S3ed!Pass99"},
            format="json",
        )

        # No force_authenticate here: this relies entirely on the session
        # cookie the login request above set on self.client.
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.institution.id)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            self.login_url,
            {"email": "dashboard@hospitalbautista.org.py", "password": "wrong"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unknown_email_is_rejected(self):
        response = self.client.post(
            self.login_url,
            {"email": "nobody@example.com", "password": "whatever123"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_account_without_an_institution_cannot_log_in_here(self):
        response = self.client.post(
            self.login_url,
            {"email": "admin@example.com", "password": "Adm1n!Pass99"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_account_without_an_institution_gets_no_session(self):
        self.client.post(
            self.login_url,
            {"email": "admin@example.com", "password": "Adm1n!Pass99"},
            format="json",
        )

        # The 403 above must not have logged the account in regardless.
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 403)

    def test_logout_clears_the_session(self):
        self.client.post(
            self.login_url,
            {"email": "dashboard@hospitalbautista.org.py", "password": "S3ed!Pass99"},
            format="json",
        )

        logout_response = self.client.post(self.logout_url)
        self.assertEqual(logout_response.status_code, 204)

        me_response = self.client.get(self.me_url)
        self.assertEqual(me_response.status_code, 403)

    def test_logout_without_a_session_is_rejected(self):
        response = self.client.post(self.logout_url)
        self.assertIn(response.status_code, (401, 403))

    def test_logout_requires_a_csrf_token_but_login_does_not(self):
        """Locks in the CSRF contract the frontend must implement.

        The default ``APIClient`` skips CSRF enforcement, which is why every
        other test above uses it — but that also means it can't catch a
        frontend integration bug here, so this one opts back into real
        enforcement. Login is a POST with no session yet, so Django never
        requires a CSRF token for it; logout runs *inside* the session login
        just created, so it does, via the ``csrftoken`` cookie login sets
        (see ``get_token(request)`` in the view) sent back as the
        ``X-CSRFToken`` header.
        """
        csrf_client = APIClient(enforce_csrf_checks=True)

        login_response = csrf_client.post(
            self.login_url,
            {"email": "dashboard@hospitalbautista.org.py", "password": "S3ed!Pass99"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)

        without_token = csrf_client.post(self.logout_url)
        self.assertEqual(without_token.status_code, 403)

        csrf_token = csrf_client.cookies["csrftoken"].value
        with_token = csrf_client.post(self.logout_url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(with_token.status_code, 204)


class InstitutionDashboardDataTests(APITestCase):
    """Tests for the consolidated GET /api/institution/dashboard/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.now = timezone.now()

        region = Regions.seed_for_tests(name="Gran Asuncion", region_code="GA")

        self.institution = Institution.objects.create(legal_name="Hospital Bautista")
        self.station = Stations.seed_for_tests(
            name="Respira: Villa Morra",
            region=region,
            latitude=-25.29,
            longitude=-57.57,
            is_station_on=True,
        )
        StationDetails.objects.create(
            station=self.station,
            city="Asunción",
            specific_location="3er piso, ala este",
        )
        InstitutionContract.objects.create(
            institution=self.institution,
            station=self.station,
            contract_status=InstitutionContract.ContractStatus.ACTIVE,
            start_date=date(2026, 1, 1),
            monthly_fee=Decimal("450.00"),
        )
        self.user = User.objects.create_user(
            username="contact@hospitalbautista.org.py",
            email="contact@hospitalbautista.org.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(user=self.user, institution=self.institution)

        # A second institution, fully independent, to prove no cross-leakage.
        self.other_institution = Institution.objects.create(
            legal_name="Colegio San Jose S.A."
        )
        other_station = Stations.seed_for_tests(
            name="Respira: Centro",
            region=region,
            latitude=-25.28,
            longitude=-57.48,
            is_station_on=True,
        )
        InstitutionContract.objects.create(
            institution=self.other_institution,
            station=other_station,
            contract_status=InstitutionContract.ContractStatus.ACTIVE,
            start_date=date(2026, 1, 1),
        )
        self.other_user = User.objects.create_user(
            username="contact@colegiosanjose.edu.py",
            email="contact@colegiosanjose.edu.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(
            user=self.other_user, institution=self.other_institution
        )
        StationReadingsGold.seed_for_tests(
            station=other_station, date_utc=self.now, aqi_pm2_5=42.0
        )

        self.unlinked_user = User.objects.create_user(
            username="nobody@example.com",
            email="nobody@example.com",
            password="S3ed!Pass99",
        )

        self.dashboard_url = reverse("institution-dashboard")

    # --- Access control -----------------------------------------------

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(self.dashboard_url)
        self.assertIn(response.status_code, (401, 403))

    def test_user_without_institution_is_forbidden(self):
        self.client.force_authenticate(self.unlinked_user)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 403)

    def test_institution_without_assigned_sensor_returns_404(self):
        contractless = Institution.objects.create(legal_name="Colegio Nuevo")
        contact = User.objects.create_user(
            username="contacto@colegionuevo.edu.py",
            email="contacto@colegionuevo.edu.py",
            password="S3ed!Pass99",
        )
        InstitutionUser.objects.create(user=contact, institution=contractless)

        self.client.force_authenticate(contact)
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 404)

    def test_dashboard_never_leaks_another_institutions_data(self):
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=self.now, aqi_pm2_5=42.0
        )

        self.client.force_authenticate(self.user)
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sensor"]["name"], "Respira: Villa Morra")
        self.assertNotEqual(response.json()["sensor"]["name"], "Respira: Centro")

    # --- Successful response structure ----------------------------------

    def test_successful_response_includes_all_sections(self):
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=self.now, aqi_pm2_5=42.0
        )

        self.client.force_authenticate(self.user)
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body.keys()), {"sensor", "air_quality", "history", "alert_config"}
        )
        self.assertEqual(
            set(body["sensor"].keys()),
            {"id", "name", "status", "location", "last_measurement_at"},
        )
        self.assertEqual(
            set(body["alert_config"].keys()),
            {"is_enabled", "alert_threshold", "sensitive_groups"},
        )

    def test_sensor_section_reflects_the_assigned_station(self):
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=self.now, aqi_pm2_5=42.0
        )

        self.client.force_authenticate(self.user)
        body = self.client.get(self.dashboard_url).json()

        sensor = body["sensor"]
        self.assertEqual(sensor["id"], self.station.id)
        self.assertEqual(sensor["name"], "Respira: Villa Morra")
        self.assertEqual(sensor["status"], "online")
        self.assertEqual(sensor["location"]["city"], "Asunción")
        self.assertEqual(sensor["location"]["specific_location"], "3er piso, ala este")
        self.assertEqual(sensor["location"]["latitude"], -25.29)
        self.assertIsNotNone(sensor["last_measurement_at"])

    def test_sensor_status_reflects_an_offline_station(self):
        self.station.is_station_on = False
        self.station.update_for_tests(update_fields=["is_station_on"])

        self.client.force_authenticate(self.user)
        body = self.client.get(self.dashboard_url).json()

        self.assertEqual(body["sensor"]["status"], "offline")

    # --- Air quality classification --------------------------------------

    def test_air_quality_uses_the_latest_reading_and_classification(self):
        StationReadingsGold.seed_for_tests(
            station=self.station,
            date_utc=self.now - relativedelta(days=1),
            aqi_pm2_5=30.0,
        )
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=self.now, aqi_pm2_5=120.0
        )

        self.client.force_authenticate(self.user)
        body = self.client.get(self.dashboard_url).json()

        air_quality = body["air_quality"]
        self.assertEqual(air_quality["aqi"], 120.0)
        self.assertEqual(air_quality["category"], "unhealthy_sensitive")
        self.assertEqual(
            air_quality["category_label"], "INSALUBRE PARA GRUPOS SENSIBLES"
        )
        self.assertTrue(air_quality["message"])
        self.assertTrue(air_quality["recommendations"])

    def test_missing_current_measurements_returns_null_air_quality(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["air_quality"])
        self.assertIsNone(response.json()["sensor"]["last_measurement_at"])
        self.assertEqual(response.json()["history"], [])

    # --- History (three-month window) -------------------------------------

    def test_history_excludes_readings_older_than_three_months(self):
        StationReadingsGold.seed_for_tests(
            station=self.station,
            date_utc=self.now - relativedelta(months=4),
            aqi_pm2_5=99.0,
        )
        StationReadingsGold.seed_for_tests(
            station=self.station,
            date_utc=self.now - relativedelta(months=1),
            aqi_pm2_5=55.0,
        )

        self.client.force_authenticate(self.user)
        history = self.client.get(self.dashboard_url).json()["history"]

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["aqi"], 55.0)

    def test_history_is_returned_in_chronological_order(self):
        StationReadingsGold.seed_for_tests(
            station=self.station,
            date_utc=self.now - relativedelta(months=2),
            aqi_pm2_5=40.0,
        )
        StationReadingsGold.seed_for_tests(
            station=self.station,
            date_utc=self.now - relativedelta(months=1),
            aqi_pm2_5=60.0,
        )
        StationReadingsGold.seed_for_tests(
            station=self.station, date_utc=self.now, aqi_pm2_5=80.0
        )

        self.client.force_authenticate(self.user)
        history = self.client.get(self.dashboard_url).json()["history"]

        dates = [point["date"] for point in history]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual([point["aqi"] for point in history], [40.0, 60.0, 80.0])

    # --- Alert configuration ------------------------------------------------

    def test_institution_without_alert_configuration_returns_a_controlled_default(self):
        self.client.force_authenticate(self.user)
        alert_config = self.client.get(self.dashboard_url).json()["alert_config"]

        self.assertEqual(
            alert_config,
            {"is_enabled": False, "alert_threshold": None, "sensitive_groups": []},
        )

    def test_configured_thresholds_and_sensitive_groups_are_returned(self):
        # These are seeded by migration 0012 alongside the rest of the fixed
        # catalog; fetched rather than created to avoid colliding with it.
        children = SensitiveGroup.objects.get(key="children")
        infants = SensitiveGroup.objects.get(key="infants")
        config = InstitutionAlertConfig.objects.create(
            institution=self.institution, is_enabled=True, alert_threshold=100
        )
        config.sensitive_groups.set([children, infants])

        self.client.force_authenticate(self.user)
        alert_config = self.client.get(self.dashboard_url).json()["alert_config"]

        self.assertTrue(alert_config["is_enabled"])
        self.assertEqual(alert_config["alert_threshold"], 100)
        self.assertEqual(
            {group["key"] for group in alert_config["sensitive_groups"]},
            {"children", "infants"},
        )
