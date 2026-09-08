import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import (
    FaqCategory,
    FaqQuestion,
    InferenceResults,
    InferenceRuns,
    RegionReadings,
    Regions,
    StationReadingsGold,
    Stations,
)


class IpGeolocateTests(TestCase):
    def test_ip_geolocate_private_ip_returns_none(self):
        from .views import _ip_geolocate

        # Private IPs should not be geolocated
        self.assertIsNone(_ip_geolocate("10.0.0.1"))

    def test_ip_geolocate_calls_provider_with_ip_in_path(self):
        from . import views

        cache.clear()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "latitude": -25.3,
            "longitude": -57.5,
        }

        with patch("api.views.requests.get", return_value=mock_resp) as mock_get:
            coords = views._ip_geolocate("8.8.8.8")
            self.assertEqual(coords, (-25.3, -57.5))
            mock_get.assert_called_once()
            called_args, _ = mock_get.call_args
            # ipwho.is is path-based: the IP is formatted into the URL, not
            # passed as a query param.
            self.assertEqual(
                called_args[0], views.IP_GEOLOCATION_URL.format(ip="8.8.8.8")
            )


class BackendEndpointTests(TestCase):
    def _create_inference_run(
        self,
        *,
        run_id,
        run_date,
        flow_run_id,
        status=InferenceRuns.Status.SUCCESS,
        started_at=None,
    ):
        started_at = started_at or (run_date - timedelta(minutes=5))
        return InferenceRuns.seed_for_tests(
            id=run_id,
            run_date=run_date,
            flow_run_id=flow_run_id,
            deployment=self.base_run_payload["deployment"],
            window_hours=self.base_run_payload["window_hours"],
            min_points=self.base_run_payload["min_points"],
            model_6h_version=self.base_run_payload["model_6h_version"],
            model_12h_version=self.base_run_payload["model_12h_version"],
            model_6h_path=self.base_run_payload["model_6h_path"],
            model_12h_path=self.base_run_payload["model_12h_path"],
            started_at=started_at,
            status=status,
            stations_total=self.base_run_payload["stations_total"],
            stations_success=self.base_run_payload["stations_success"],
            stations_skipped=self.base_run_payload["stations_skipped"],
            stations_failed=self.base_run_payload["stations_failed"],
        )

    def setUp(self):
        self.client = APIClient()

        self.region = Regions.seed_for_tests(
            id=1,
            name="Gran Asuncion",
            region_code="GRAN_ASUNCION",
            bbox="-57.680,-25.410,-57.470,-25.140",
            has_weather_data=True,
            has_pattern_station=False,
        )
        self.other_region = Regions.seed_for_tests(
            id=2,
            name="Central",
            region_code="CENTRAL",
            bbox="-57.620,-25.500,-57.300,-25.100",
            has_weather_data=False,
            has_pattern_station=True,
        )

        self.station = Stations.seed_for_tests(
            id=101,
            name="FIUNA: Campus",
            region=self.region,
            latitude=-25.3,
            longitude=-57.5,
            is_station_on=True,
            is_pattern_station=False,
        )
        self.region_station_2 = Stations.seed_for_tests(
            id=102,
            name="AireLibre: Centro",
            region=self.region,
            latitude=-25.29,
            longitude=-57.49,
            is_station_on=True,
            is_pattern_station=False,
        )
        self.other_station = Stations.seed_for_tests(
            id=201,
            name="AireLibre: Other",
            region=self.other_region,
            latitude=-25.28,
            longitude=-57.48,
            is_station_on=True,
            is_pattern_station=False,
        )

        latest_reading_time = datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)
        StationReadingsGold.seed_for_tests(
            station=self.station,
            date_utc=latest_reading_time,
            aqi_pm2_5=84.0,
        )
        StationReadingsGold.seed_for_tests(
            station=self.region_station_2,
            date_utc=latest_reading_time,
            aqi_pm2_5=60.0,
        )
        StationReadingsGold.seed_for_tests(
            station=self.other_station,
            date_utc=latest_reading_time,
            aqi_pm2_5=150.0,
        )
        RegionReadings.seed_for_tests(
            region=self.region,
            date_utc=latest_reading_time,
            aqi_region_avg=72.0,
        )

        self.base_run_payload = {
            "flow_run_id": "flow-run-test",
            "deployment": "test",
            "window_hours": 24,
            "min_points": 6,
            "model_6h_version": "model-6h-v1",
            "model_12h_version": "model-12h-v1",
            "model_6h_path": "/models/6h.pkl",
            "model_12h_path": "/models/12h.pkl",
            "started_at": latest_reading_time - timedelta(minutes=5),
            "status": InferenceRuns.Status.SUCCESS,
            "stations_total": 3,
            "stations_success": 3,
            "stations_skipped": 0,
            "stations_failed": 0,
        }

        self.older_run = self._create_inference_run(
            run_id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            run_date=latest_reading_time - timedelta(hours=6),
            flow_run_id=f"{self.base_run_payload['flow_run_id']}-older",
            status=self.base_run_payload["status"],
            started_at=self.base_run_payload["started_at"] - timedelta(hours=6),
        )
        self.latest_run = self._create_inference_run(
            run_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            run_date=latest_reading_time,
            flow_run_id=self.base_run_payload["flow_run_id"],
            status=self.base_run_payload["status"],
            started_at=self.base_run_payload["started_at"],
        )

        InferenceResults.seed_for_tests(
            inference_run=self.older_run,
            station=self.station,
            forecasts_6h=[{"timestamp": "2026-03-31 05:00:00", "value": 10}],
            forecasts_12h=[{"timestamp": "2026-03-31 05:00:00", "value": 15}],
            aqi_input=[{"timestamp": "2026-03-31 04:00:00", "value": 50}],
        )
        InferenceResults.seed_for_tests(
            inference_run=self.latest_run,
            station=self.station,
            forecasts_6h=[{"timestamp": "2026-03-31 12:00:00", "value": 20}],
            forecasts_12h=[{"timestamp": "2026-03-31 12:00:00", "value": 25}],
            aqi_input=[{"timestamp": "2026-03-31 11:00:00", "value": 84}],
        )
        InferenceResults.seed_for_tests(
            inference_run=self.latest_run,
            station=self.region_station_2,
            forecasts_6h=[{"timestamp": "2026-03-31 12:00:00", "value": 40}],
            forecasts_12h=[{"timestamp": "2026-03-31 12:00:00", "value": 45}],
            aqi_input=[{"timestamp": "2026-03-31 11:00:00", "value": 60}],
        )
        InferenceResults.seed_for_tests(
            inference_run=self.latest_run,
            station=self.other_station,
            forecasts_6h=[{"timestamp": "2026-03-31 12:00:00", "value": 90}],
            forecasts_12h=[{"timestamp": "2026-03-31 12:00:00", "value": 95}],
            aqi_input=[{"timestamp": "2026-03-31 11:00:00", "value": 150}],
        )

    def test_health_endpoint(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_station_list_keeps_frontend_shape(self):
        response = self.client.get(reverse("stations-list"))

        self.assertEqual(response.status_code, 200)
        first_station = response.json()[0]
        self.assertEqual(
            set(first_station.keys()),
            {
                "id",
                "name",
                "region",
                "coordinates",
                "is_station_on",
                "is_pattern_station",
                "aqi_pm2_5",
            },
        )
        self.assertEqual(first_station["region"]["has_pattern_station"], False)
        self.assertEqual(first_station["coordinates"], [-25.3, -57.5])
        self.assertEqual(first_station["aqi_pm2_5"], 84.0)

    def test_station_list_is_ordered_by_id(self):
        response = self.client.get(reverse("stations-list"))

        self.assertEqual(response.status_code, 200)
        ids = [station["id"] for station in response.json()]
        self.assertEqual(ids, sorted(ids))

    def test_station_map_returns_station_specific_forecasts(self):
        response = self.client.get(
            reverse("map"), {"entity": "station", "id": self.station.id}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload.keys()), {"aqi", "forecast_6h", "forecast_12h"})
        self.assertEqual(payload["aqi"], 84.0)
        self.assertEqual(
            payload["forecast_6h"], [{"timestamp": "2026-03-31 12:00:00", "value": 20}]
        )
        self.assertEqual(
            payload["forecast_12h"], [{"timestamp": "2026-03-31 12:00:00", "value": 25}]
        )

    def test_region_map_averages_only_region_stations(self):
        response = self.client.get(
            reverse("map"), {"entity": "region", "id": self.region.id}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["aqi"], 72.0)
        self.assertEqual(
            payload["forecast_6h"],
            [{"timestamp": "2026-03-31 12:00:00", "value": 30.0}],
        )
        self.assertEqual(
            payload["forecast_12h"],
            [{"timestamp": "2026-03-31 12:00:00", "value": 35.0}],
        )

    def test_region_map_ignores_latest_non_success_run(self):
        failed_run = self._create_inference_run(
            run_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            run_date=datetime(2026, 3, 31, 13, 0, tzinfo=timezone.utc),
            flow_run_id="flow-run-failed",
            status=InferenceRuns.Status.FAILED,
        )
        InferenceResults.seed_for_tests(
            inference_run=failed_run,
            station=self.station,
            forecasts_6h=[{"timestamp": "2026-03-31 13:00:00", "value": 999}],
            forecasts_12h=[{"timestamp": "2026-03-31 13:00:00", "value": 999}],
            aqi_input=[{"timestamp": "2026-03-31 12:00:00", "value": 84}],
        )
        InferenceResults.seed_for_tests(
            inference_run=failed_run,
            station=self.region_station_2,
            forecasts_6h=[{"timestamp": "2026-03-31 13:00:00", "value": 999}],
            forecasts_12h=[{"timestamp": "2026-03-31 13:00:00", "value": 999}],
            aqi_input=[{"timestamp": "2026-03-31 12:00:00", "value": 60}],
        )

        response = self.client.get(
            reverse("map"), {"entity": "region", "id": self.region.id}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["forecast_6h"],
            [{"timestamp": "2026-03-31 12:00:00", "value": 30.0}],
        )
        self.assertEqual(
            payload["forecast_12h"],
            [{"timestamp": "2026-03-31 12:00:00", "value": 35.0}],
        )

    def test_region_map_uses_latest_region_run_without_mixing_station_runs(self):
        newest_success_run = self._create_inference_run(
            run_id=uuid.UUID("00000000-0000-0000-0000-000000000006"),
            run_date=datetime(2026, 3, 31, 13, 30, tzinfo=timezone.utc),
            flow_run_id="flow-run-region-newest",
            status=InferenceRuns.Status.SUCCESS,
        )
        InferenceResults.seed_for_tests(
            inference_run=newest_success_run,
            station=self.region_station_2,
            forecasts_6h=[{"timestamp": "2026-03-31 13:30:00", "value": 55}],
            forecasts_12h=[{"timestamp": "2026-03-31 13:30:00", "value": 65}],
            aqi_input=[{"timestamp": "2026-03-31 13:00:00", "value": 60}],
        )

        response = self.client.get(
            reverse("map"), {"entity": "region", "id": self.region.id}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["forecast_6h"],
            [{"timestamp": "2026-03-31 13:30:00", "value": 55.0}],
        )
        self.assertEqual(
            payload["forecast_12h"],
            [{"timestamp": "2026-03-31 13:30:00", "value": 65.0}],
        )

    def test_region_map_falls_back_when_latest_region_run_has_empty_forecasts(self):
        newest_success_run = self._create_inference_run(
            run_id=uuid.UUID("00000000-0000-0000-0000-000000000007"),
            run_date=datetime(2026, 3, 31, 14, 30, tzinfo=timezone.utc),
            flow_run_id="flow-run-region-empty",
            status=InferenceRuns.Status.SUCCESS,
        )
        InferenceResults.seed_for_tests(
            inference_run=newest_success_run,
            station=self.station,
            forecasts_6h=[],
            forecasts_12h=[],
            aqi_input=[{"timestamp": "2026-03-31 14:00:00", "value": 84}],
        )
        InferenceResults.seed_for_tests(
            inference_run=newest_success_run,
            station=self.region_station_2,
            forecasts_6h=[],
            forecasts_12h=[],
            aqi_input=[{"timestamp": "2026-03-31 14:00:00", "value": 60}],
        )

        response = self.client.get(
            reverse("map"), {"entity": "region", "id": self.region.id}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["forecast_6h"],
            [{"timestamp": "2026-03-31 12:00:00", "value": 30.0}],
        )
        self.assertEqual(
            payload["forecast_12h"],
            [{"timestamp": "2026-03-31 12:00:00", "value": 35.0}],
        )

    def test_station_map_resolves_latest_available_forecast_per_station(self):
        newest_success_run = self._create_inference_run(
            run_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
            run_date=datetime(2026, 3, 31, 13, 30, tzinfo=timezone.utc),
            flow_run_id="flow-run-success-newest",
            status=InferenceRuns.Status.SUCCESS,
        )
        InferenceResults.seed_for_tests(
            inference_run=newest_success_run,
            station=self.station,
            forecasts_6h=[],
            forecasts_12h=[],
            aqi_input=[{"timestamp": "2026-03-31 13:00:00", "value": 84}],
        )
        InferenceResults.seed_for_tests(
            inference_run=newest_success_run,
            station=self.region_station_2,
            forecasts_6h=[{"timestamp": "2026-03-31 13:30:00", "value": 55}],
            forecasts_12h=[{"timestamp": "2026-03-31 13:30:00", "value": 65}],
            aqi_input=[{"timestamp": "2026-03-31 13:00:00", "value": 60}],
        )

        station_1_response = self.client.get(
            reverse("map"), {"entity": "station", "id": self.station.id}
        )
        station_2_response = self.client.get(
            reverse("map"), {"entity": "station", "id": self.region_station_2.id}
        )

        self.assertEqual(station_1_response.status_code, 200)
        self.assertEqual(station_2_response.status_code, 200)

        self.assertEqual(
            station_1_response.json()["forecast_6h"],
            [{"timestamp": "2026-03-31 12:00:00", "value": 20}],
        )
        self.assertEqual(
            station_1_response.json()["forecast_12h"],
            [{"timestamp": "2026-03-31 12:00:00", "value": 25}],
        )
        self.assertEqual(
            station_2_response.json()["forecast_6h"],
            [{"timestamp": "2026-03-31 13:30:00", "value": 55}],
        )
        self.assertEqual(
            station_2_response.json()["forecast_12h"],
            [{"timestamp": "2026-03-31 13:30:00", "value": 65}],
        )

    def test_station_forecast_uses_latest_run_date_not_latest_uuid(self):
        response = self.client.get(reverse("stations-forecast", args=[self.station.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()),
            {"forecast_date", "aqi_level", "forecast_6h", "forecast_12h"},
        )
        self.assertEqual(payload["forecast_date"], "2026-03-31T12:00:00Z")
        self.assertEqual(
            payload["aqi_level"], [{"timestamp": "2026-03-31 11:00:00", "value": 84}]
        )
        self.assertEqual(
            payload["forecast_6h"], [{"timestamp": "2026-03-31 12:00:00", "value": 20}]
        )
        self.assertEqual(
            payload["forecast_12h"], [{"timestamp": "2026-03-31 12:00:00", "value": 25}]
        )

    def test_station_forecast_ignores_latest_non_success_run(self):
        failed_run = self._create_inference_run(
            run_id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
            run_date=datetime(2026, 3, 31, 14, 0, tzinfo=timezone.utc),
            flow_run_id="flow-run-failed-station-endpoint",
            status=InferenceRuns.Status.FAILED,
        )
        InferenceResults.seed_for_tests(
            inference_run=failed_run,
            station=self.station,
            forecasts_6h=[{"timestamp": "2026-03-31 14:00:00", "value": 999}],
            forecasts_12h=[{"timestamp": "2026-03-31 14:00:00", "value": 999}],
            aqi_input=[{"timestamp": "2026-03-31 13:30:00", "value": 200}],
        )

        response = self.client.get(reverse("stations-forecast", args=[self.station.id]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["forecast_date"], "2026-03-31T12:00:00Z")
        self.assertEqual(
            payload["forecast_6h"], [{"timestamp": "2026-03-31 12:00:00", "value": 20}]
        )

    def test_station_forecast_falls_back_when_latest_success_has_empty_forecasts(self):
        newer_success_run = self._create_inference_run(
            run_id=uuid.UUID("00000000-0000-0000-0000-000000000005"),
            run_date=datetime(2026, 3, 31, 14, 30, tzinfo=timezone.utc),
            flow_run_id="flow-run-success-empty-forecast",
            status=InferenceRuns.Status.SUCCESS,
        )
        InferenceResults.seed_for_tests(
            inference_run=newer_success_run,
            station=self.station,
            forecasts_6h=[],
            forecasts_12h=[],
            aqi_input=[{"timestamp": "2026-03-31 14:00:00", "value": 120}],
        )

        response = self.client.get(reverse("stations-forecast", args=[self.station.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["forecast_date"], "2026-03-31T12:00:00Z")
        self.assertEqual(
            payload["aqi_level"], [{"timestamp": "2026-03-31 11:00:00", "value": 84}]
        )
        self.assertEqual(
            payload["forecast_6h"], [{"timestamp": "2026-03-31 12:00:00", "value": 20}]
        )
        self.assertEqual(
            payload["forecast_12h"], [{"timestamp": "2026-03-31 12:00:00", "value": 25}]
        )

    def _geo_response(self, *, latitude, longitude, success=True):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {
            "success": success,
            "latitude": latitude,
            "longitude": longitude,
        }
        return fake

    @patch("api.views.requests.get")
    def test_nearest_region_resolves_from_ip_when_no_coords(self, mock_get):
        cache.clear()
        # Coordinates close to the Gran Asuncion stations; the endpoint should
        # resolve that region without any lat/lon query params.
        mock_get.return_value = self._geo_response(latitude=-25.3, longitude=-57.5)

        response = self.client.get(
            reverse("nearest-region"), HTTP_X_FORWARDED_FOR="8.8.8.8"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["region_id"], self.region.id)
        self.assertEqual(payload["aqi"], 72.0)
        mock_get.assert_called_once()

    @patch("api.views.requests.get")
    def test_nearest_region_caches_ip_geolocation(self, mock_get):
        cache.clear()
        mock_get.return_value = self._geo_response(latitude=-25.3, longitude=-57.5)

        for _ in range(3):
            response = self.client.get(
                reverse("nearest-region"), HTTP_X_FORWARDED_FOR="8.8.8.8"
            )
            self.assertEqual(response.status_code, 200)

        # Repeated widget refreshes from the same IP hit the cache, not the
        # external geolocation provider.
        mock_get.assert_called_once()

    @patch("api.views.requests.get")
    def test_nearest_region_without_coords_returns_404_when_ip_unresolved(
        self, mock_get
    ):
        cache.clear()
        mock_get.side_effect = __import__("requests").RequestException("boom")

        response = self.client.get(
            reverse("nearest-region"), HTTP_X_FORWARDED_FOR="8.8.8.8"
        )

        self.assertEqual(response.status_code, 404)

    @patch("api.views.requests.get")
    def test_nearest_region_skips_geolocation_for_private_ip(self, mock_get):
        cache.clear()

        response = self.client.get(
            reverse("nearest-region"), HTTP_X_FORWARDED_FOR="10.0.0.1"
        )

        self.assertEqual(response.status_code, 404)
        # Private/loopback IPs never reach the external provider.
        mock_get.assert_not_called()

    @patch("api.views.requests.get")
    def test_nearest_region_with_coords_ignores_ip_geolocation(self, mock_get):
        cache.clear()

        response = self.client.get(
            reverse("nearest-region"),
            {"lat": -25.3, "lon": -57.5},
            HTTP_X_FORWARDED_FOR="8.8.8.8",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["region_id"], self.region.id)
        mock_get.assert_not_called()


class AdminUserManagementTests(TestCase):
    """Tests for the /api/admin/users/ administrative CRUD endpoints."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from api.models import UserProfile

        self.User = get_user_model()
        self.UserProfile = UserProfile
        self.client = APIClient()

        self.list_url = reverse("admin-users-list")

        self.superadmin = self._make_user("super@example.com", "superadmin")
        self.admin = self._make_user("admin@example.com", "admin")
        self.viewer = self._make_user("viewer@example.com", "viewer")

    def _make_user(self, email, role, password="S3ed!Pass99"):
        user = self.User.objects.create_user(
            username=email, email=email, password=password
        )
        self.UserProfile.objects.create(user=user, role=role)
        return user

    def _role_of(self, user):
        return self.User.objects.get(pk=user.pk).profile.role

    def _detail_url(self, user_id):
        return reverse("admin-users-detail", args=[user_id])

    # --- Permissions ---------------------------------------------------

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(self.list_url)
        self.assertIn(response.status_code, (401, 403))

    def test_viewer_cannot_manage_users(self):
        self.client.force_authenticate(self.viewer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_users(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    # --- Create --------------------------------------------------------

    def test_admin_creates_user_and_password_is_hashed(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            self.list_url,
            {
                "email": "new@example.com",
                "password": "Br4nd!New99",
                "first_name": "New",
                "last_name": "User",
                "role": "viewer",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.json())

        created = self.User.objects.get(email="new@example.com")
        self.assertNotEqual(created.password, "Br4nd!New99")
        self.assertTrue(created.password.startswith("pbkdf2_"))
        self.assertTrue(created.check_password("Br4nd!New99"))

        # Appears in subsequent list requests
        list_response = self.client.get(self.list_url, {"email": "new@example.com"})
        emails = [u["email"] for u in list_response.json()["results"]]
        self.assertIn("new@example.com", emails)

    def test_duplicate_email_is_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            self.list_url,
            {"email": "viewer@example.com", "password": "An0ther!Pass99"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json())

    def test_weak_password_is_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            self.list_url,
            {"email": "weak@example.com", "password": "123"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.json())

    # --- Superadmin role restriction ----------------------------------

    def test_admin_cannot_assign_superadmin_role_on_create(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            self.list_url,
            {
                "email": "wannabe@example.com",
                "password": "W4nna!Pass99",
                "role": "superadmin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("role", response.json())

    def test_superadmin_can_assign_superadmin_role(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            self.list_url,
            {
                "email": "promoted@example.com",
                "password": "Pr0mo!Pass99",
                "role": "superadmin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.User.objects.get(email="promoted@example.com").profile.role,
            "superadmin",
        )

    def test_admin_cannot_promote_existing_user_to_superadmin(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            self._detail_url(self.viewer.id), {"role": "superadmin"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    # --- Update --------------------------------------------------------

    def test_admin_updates_profile_and_role(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            self._detail_url(self.viewer.id),
            {"first_name": "Updated", "role": "admin"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        # Response must reflect the new role immediately, not a stale profile.
        self.assertEqual(response.json()["role"], "admin")
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.first_name, "Updated")
        self.assertEqual(self._role_of(self.viewer), "admin")

    def test_update_password_is_hashed(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            self._detail_url(self.viewer.id),
            {"password": "Ch4nged!Pass99"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.viewer.refresh_from_db()
        self.assertTrue(self.viewer.check_password("Ch4nged!Pass99"))

    # --- Delete (soft) -------------------------------------------------

    def test_delete_deactivates_user(self):
        self.client.force_authenticate(self.admin)
        response = self.client.delete(self._detail_url(self.viewer.id))
        self.assertEqual(response.status_code, 204)
        self.viewer.refresh_from_db()
        self.assertFalse(self.viewer.is_active)
        # Row still exists (soft delete)
        self.assertTrue(self.User.objects.filter(id=self.viewer.id).exists())

    def test_admin_cannot_delete_own_account(self):
        self.client.force_authenticate(self.admin)
        response = self.client.delete(self._detail_url(self.admin.id))
        self.assertEqual(response.status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    # --- Filtering & pagination ---------------------------------------

    def test_filter_by_role_and_active_status(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(self.list_url, {"role": "viewer"})
        roles = {u["role"] for u in response.json()["results"]}
        self.assertEqual(roles, {"viewer"})

        self.viewer.is_active = False
        self.viewer.save(update_fields=["is_active"])
        response = self.client.get(self.list_url, {"is_active": "false"})
        ids = {u["id"] for u in response.json()["results"]}
        self.assertIn(str(self.viewer.id), ids)
        self.assertNotIn(str(self.admin.id), ids)

    def test_list_is_paginated(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.list_url)
        body = response.json()
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, body)


class FaqEndpointTests(TestCase):
    """Covers the public /api/faq/ feed: shape, ordering, publishing, fallback."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("faq")
        # The seed migration already populated the table; start from a clean
        # slate so assertions are about the rows this test creates.
        FaqCategory.objects.all().delete()

        self.category = FaqCategory.objects.create(
            slug="sensor",
            order=1,
            label_es="El sensor",
            label_en="The sensor",
            label_pt="O sensor",
        )
        FaqQuestion.objects.create(
            category=self.category,
            order=0,
            question_es="¿Qué mide?",
            answer_es="PM2.5 y PM10.",
            question_en="What does it measure?",
            answer_en="PM2.5 and PM10.",
            question_pt="O que mede?",
            answer_pt="PM2.5 e PM10.",
        )

    def test_returns_categories_with_all_languages(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(len(body), 1)
        # `id` is the slug, not the primary key: the public page uses it as an
        # anchor, so it must not change when rows are recreated.
        self.assertEqual(body[0]["id"], "sensor")
        self.assertEqual(
            body[0]["label"],
            {"es": "El sensor", "en": "The sensor", "pt": "O sensor"},
        )
        question = body[0]["questions"][0]
        self.assertEqual(question["q"]["en"], "What does it measure?")
        self.assertEqual(question["a"]["pt"], "PM2.5 e PM10.")

    def test_untranslated_fields_fall_back_to_spanish(self):
        FaqQuestion.objects.create(
            category=self.category,
            order=1,
            question_es="¿Necesita mantenimiento?",
            answer_es="Sí, mantenimiento preventivo.",
        )

        question = self.client.get(self.url).json()[0]["questions"][1]
        for lang in ("es", "en", "pt"):
            self.assertEqual(question["q"][lang], "¿Necesita mantenimiento?")
            self.assertEqual(question["a"][lang], "Sí, mantenimiento preventivo.")

    def test_unpublished_rows_are_hidden(self):
        hidden_question = FaqQuestion.objects.create(
            category=self.category,
            order=2,
            question_es="Borrador",
            answer_es="Sin publicar.",
            is_published=False,
        )
        hidden_category = FaqCategory.objects.create(
            slug="draft", order=2, label_es="Borrador", is_published=False
        )
        FaqQuestion.objects.create(
            category=hidden_category, order=0, question_es="X", answer_es="Y"
        )

        body = self.client.get(self.url).json()
        self.assertEqual([c["id"] for c in body], ["sensor"])
        questions = [q["q"]["es"] for q in body[0]["questions"]]
        self.assertNotIn(hidden_question.question_es, questions)

    def test_ordering_follows_order_field(self):
        first = FaqCategory.objects.create(
            slug="project", order=0, label_es="Proyecto Respira"
        )
        FaqQuestion.objects.create(
            category=first, order=1, question_es="Segunda", answer_es="."
        )
        FaqQuestion.objects.create(
            category=first, order=0, question_es="Primera", answer_es="."
        )

        body = self.client.get(self.url).json()
        self.assertEqual([c["id"] for c in body], ["project", "sensor"])
        self.assertEqual(
            [q["q"]["es"] for q in body[0]["questions"]], ["Primera", "Segunda"]
        )

    def test_answers_preserve_newlines_and_bullets(self):
        FaqQuestion.objects.create(
            category=self.category,
            order=3,
            question_es="¿Qué incluye?",
            answer_es="Incluye:\n• Instalación.\n• Soporte.",
        )
        answers = [
            q["a"]["es"] for q in self.client.get(self.url).json()[0]["questions"]
        ]
        self.assertIn("Incluye:\n• Instalación.\n• Soporte.", answers)

    def test_endpoint_is_public(self):
        # No credentials are set on self.client; the feed must still answer.
        self.assertEqual(self.client.get(self.url).status_code, 200)


class FaqSeedMigrationTests(TestCase):
    """The seed migration should leave the FAQ populated on a fresh database."""

    def test_seed_populated_the_faq(self):
        self.assertEqual(FaqCategory.objects.count(), 6)
        self.assertEqual(FaqQuestion.objects.count(), 31)
        self.assertEqual(
            list(FaqCategory.objects.order_by("order").values_list("slug", flat=True)),
            ["project", "air-quality", "sensor", "leasing", "alerts", "privacy"],
        )
