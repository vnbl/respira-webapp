import ipaddress
import uuid
from collections import defaultdict
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt
from statistics import median, quantiles

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.forms import PasswordResetForm
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Prefetch
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.middleware.csrf import get_token
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet

from .aqi import classify_aqi
from .models import (
    ActionLog,
    DeviceFollower,
    DeviceInstallation,
    FaqCategory,
    FaqQuestion,
    InferenceResults,
    InferenceRuns,
    Institution,
    InstitutionAlert,
    PushBroadcast,
    RegionReadings,
    Regions,
    StationReadingsGold,
    Stations,
    UserRole,
    get_institution_for_user,
)
from .pagination import StandardResultsSetPagination
from .permissions import IsAdminRole, IsInstitutionUser, IsOwnInstitution
from .push import catch_up_follower
from .serializers import (
    ActionLogSerializer,
    AdminUserCreateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    DeviceFollowerSerializer,
    DeviceFollowerWriteSerializer,
    DeviceInstallationSerializer,
    DeviceInstallationWriteSerializer,
    FaqCategorySerializer,
    ForecastSerializer,
    HealthSerializer,
    InstitutionAlertSerializer,
    InstitutionDashboardSerializer,
    InstitutionLoginSerializer,
    InstitutionNotificationSerializer,
    InstitutionPasswordResetConfirmSerializer,
    InstitutionPasswordResetSerializer,
    InstitutionSerializer,
    MapSerializer,
    RegionSerializer,
    StationSerializer,
)

User = get_user_model()


def _flatten_forecast_rows(rows):
    flattened = []
    for row in rows:
        if row:
            flattened.extend(row)
    return flattened


def _mean_forecast_by_timestamp(rows):
    grouped_values = defaultdict(list)
    for point in _flatten_forecast_rows(rows):
        grouped_values[point["timestamp"]].append(point["value"])

    return [
        {
            "timestamp": timestamp,
            "value": sum(values) / len(values),
        }
        for timestamp, values in sorted(grouped_values.items())
    ]


def _successful_inference_runs():
    return InferenceRuns.objects.filter(status=InferenceRuns.Status.SUCCESS)


def _latest_region_forecasts(region_id):
    candidate_runs = (
        _successful_inference_runs()
        .filter(
            inferenceresults__station__region_id=region_id,
            inferenceresults__station__is_station_on=True,
        )
        .distinct()
        .order_by("-run_date", "-created_at")
    )

    for inference_run in candidate_runs:
        run_results = InferenceResults.objects.filter(
            inference_run=inference_run,
            station__region_id=region_id,
            station__is_station_on=True,
        )
        forecast_6h = _mean_forecast_by_timestamp(
            run_results.values_list("forecasts_6h", flat=True)
        )
        forecast_12h = _mean_forecast_by_timestamp(
            run_results.values_list("forecasts_12h", flat=True)
        )

        if forecast_6h and forecast_12h:
            return inference_run, forecast_6h, forecast_12h

    return None, [], []


def _latest_station_forecasts(station_id):
    candidate_runs = (
        _successful_inference_runs()
        .filter(inferenceresults__station_id=station_id)
        .distinct()
        .order_by("-run_date", "-created_at")
    )

    for inference_run in candidate_runs:
        run_results = InferenceResults.objects.filter(
            inference_run=inference_run,
            station_id=station_id,
        )
        forecast_6h = _flatten_forecast_rows(
            run_results.values_list("forecasts_6h", flat=True)
        )
        forecast_12h = _flatten_forecast_rows(
            run_results.values_list("forecasts_12h", flat=True)
        )

        if forecast_6h and forecast_12h:
            return inference_run, forecast_6h, forecast_12h

    return None, [], []


def _parse_lat_lon(request):
    lat_raw = request.query_params.get("lat")
    lon_raw = request.query_params.get("lon")
    if lat_raw is None or lon_raw is None:
        return (
            None,
            None,
            Response(
                {"error": "Both 'lat' and 'lon' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            ),
        )
    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except ValueError:
        return (
            None,
            None,
            Response(
                {"error": "'lat' and 'lon' must be valid numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            ),
        )
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return (
            None,
            None,
            Response(
                {"error": "'lat' must be in [-90,90] and 'lon' in [-180,180]."},
                status=status.HTTP_400_BAD_REQUEST,
            ),
        )
    return lat, lon, None


# Provider must return JSON with a truthy "success" flag plus "latitude" and
# "longitude" fields (ipwho.is shape). Override via settings if needed.
# Prefer an endpoint that accepts the IP as a query parameter to avoid
# interpolating user-controlled values into the request URL path (SSRF).
IP_GEOLOCATION_URL = getattr(settings, "IP_GEOLOCATION_URL", "https://ipwho.is/json")
IP_GEOLOCATION_TIMEOUT = getattr(settings, "IP_GEOLOCATION_TIMEOUT", 4)
IP_GEOLOCATION_CACHE_TTL = getattr(settings, "IP_GEOLOCATION_CACHE_TTL", 6 * 60 * 60)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        # X-Forwarded-For is a comma-separated list; the original client is first.
        return forwarded.split(",")[0].strip()
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")


def _ip_geolocate(ip):
    """Resolve an approximate (lat, lon) for a public IP, or None on failure.

    Used as a fallback when a request arrives without coordinates (e.g. the
    mobile widget before the app has been opened and location granted). Results
    are cached per IP to avoid hammering the external provider on every widget
    refresh.
    """
    if not ip:
        return None
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if parsed.is_private or parsed.is_loopback or parsed.is_reserved:
        return None

    cache_key = f"ip_geo:{ip}"
    cached = cache.get(cache_key)
    if cached is not None:
        # Empty tuple marks a cached "no result" so repeated failures don't
        # keep calling the provider.
        return cached or None

    coords = None
    try:
        # Use a query parameter for the IP rather than formatting it into the
        # URL path. Ensure the IP was already validated by ipaddress above.
        response = requests.get(
            IP_GEOLOCATION_URL,
            params={"ip": str(parsed)},
            timeout=IP_GEOLOCATION_TIMEOUT,
        )
        if response.status_code == 200:
            data = response.json()
            # Many providers use `success` flag; default to True if absent.
            if data.get("success", True):
                lat = data.get("latitude")
                lon = data.get("longitude")
                if lat is not None and lon is not None:
                    coords = (float(lat), float(lon))
    except (requests.RequestException, ValueError, TypeError):
        coords = None

    cache.set(cache_key, coords or (), IP_GEOLOCATION_CACHE_TTL)
    return coords


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlam / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _nearest_active_station(lat, lon):
    candidates = Stations.objects.filter(
        is_station_on=True,
        is_pattern_station=False,
        latitude__isnull=False,
        longitude__isnull=False,
    )
    nearest = None
    nearest_distance = None
    for station in candidates:
        distance = _haversine_km(lat, lon, station.latitude, station.longitude)
        if nearest_distance is None or distance < nearest_distance:
            nearest = station
            nearest_distance = distance
    return nearest, nearest_distance


def _latest_station_inference_result(station_id):
    candidate_results = (
        InferenceResults.objects.filter(
            station_id=station_id,
            inference_run__status=InferenceRuns.Status.SUCCESS,
        )
        .select_related("inference_run")
        .order_by("-inference_run__run_date", "-inference_run__created_at")[:50]
    )

    for inference_result in candidate_results:
        if inference_result.forecasts_6h and inference_result.forecasts_12h:
            return inference_result

    return None


class HealthCheckView(generics.GenericAPIView):
    serializer_class = HealthSerializer
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class MapViewset(generics.GenericAPIView):
    serializer_class = MapSerializer
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        entity = request.query_params.get("entity")
        entity_id = request.query_params.get("id")

        if not entity or not entity_id:
            return Response(
                {"error": "Both 'entity' and 'id' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if entity not in ["region", "station"]:
            return Response(
                {"error": "'entity' must be either 'region' or 'station'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            entity_id = int(entity_id)
        except ValueError:
            return Response(
                {"error": "'id' must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if entity == "region":
            latest_region_reading = (
                RegionReadings.objects.filter(region_id=entity_id)
                .order_by("-date_utc")
                .first()
            )

            if latest_region_reading is None:
                return Response(
                    {"error": "No readings found for this region."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            _, result_forecast_6h, result_forecast_12h = _latest_region_forecasts(
                entity_id
            )

            if not result_forecast_6h or not result_forecast_12h:
                return Response(
                    {"error": "No forecast data available for this region."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            latest_aqi = latest_region_reading.aqi_region_avg

        else:
            try:
                station = Stations.objects.get(id=entity_id)
            except Stations.DoesNotExist:
                return Response(
                    {"error": "Station ID does not exist in the database."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if station.is_pattern_station:
                return Response(
                    {"error": "Station ID is a pattern station."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not station.is_station_on:
                return Response(
                    {
                        "error": "Station ID has been manually shut down due to maintenance."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            latest_station_reading = (
                StationReadingsGold.objects.filter(station_id=entity_id)
                .order_by("-date_utc")
                .first()
            )

            if latest_station_reading is None:
                return Response(
                    {"error": "No readings found for this station."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            _, result_forecast_6h, result_forecast_12h = _latest_station_forecasts(
                entity_id
            )
            if not result_forecast_6h:
                return Response(
                    {"error": "No forecast data available for this station."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not result_forecast_12h:
                return Response(
                    {"error": "No 12-hour forecast data available for this station."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            latest_aqi = latest_station_reading.aqi_pm2_5

        return Response(
            {
                "aqi": latest_aqi,
                "forecast_6h": result_forecast_6h,
                "forecast_12h": result_forecast_12h,
            },
            status=status.HTTP_200_OK,
        )


def _region_aqi_payload(region_id):
    latest_region_reading = (
        RegionReadings.objects.filter(region_id=region_id).order_by("-date_utc").first()
    )
    if latest_region_reading is None:
        return None, Response(
            {"error": "No readings found for this region."},
            status=status.HTTP_404_NOT_FOUND,
        )

    _, forecast_6h, forecast_12h = _latest_region_forecasts(region_id)
    if not forecast_6h or not forecast_12h:
        return None, Response(
            {"error": "No forecast data available for this region."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return {
        "aqi": latest_region_reading.aqi_region_avg,
        "forecast_6h": forecast_6h,
        "forecast_12h": forecast_12h,
    }, None


class NearestRegionView(generics.GenericAPIView):
    serializer_class = MapSerializer
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        lat_raw = request.query_params.get("lat")
        lon_raw = request.query_params.get("lon")

        if lat_raw is None and lon_raw is None:
            # No coordinates supplied (e.g. the mobile widget before the app has
            # been opened and location granted). Resolve an approximate location
            # from the request IP so the first render still shows a nearby region.
            coords = _ip_geolocate(_client_ip(request))
            if coords is None:
                return Response(
                    {"error": "Could not resolve a location for this request."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            lat, lon = coords
        else:
            lat, lon, err = _parse_lat_lon(request)
            if err is not None:
                return err

        nearest_station, _ = _nearest_active_station(lat, lon)
        if nearest_station is None or nearest_station.region_id is None:
            return Response(
                {"error": "No region could be resolved for these coordinates."},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload, err = _region_aqi_payload(nearest_station.region_id)
        if err is not None:
            return err

        payload["region_id"] = nearest_station.region_id
        return Response(payload, status=status.HTTP_200_OK)


class NearestStationView(generics.GenericAPIView):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        lat, lon, err = _parse_lat_lon(request)
        if err is not None:
            return err

        nearest_station, distance_km = _nearest_active_station(lat, lon)
        if nearest_station is None:
            return Response(
                {"error": "No active station available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "id": nearest_station.id,
                "distance_km": distance_km,
            },
            status=status.HTTP_200_OK,
        )


class RegionViewset(ModelViewSet):
    queryset = Regions.objects.all()
    serializer_class = RegionSerializer
    http_method_names = ["get"]


class StationViewset(ModelViewSet):
    queryset = Stations.objects.all().order_by("id")
    serializer_class = StationSerializer
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset().filter(
            latitude__isnull=False, longitude__isnull=False
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def forecast(self, request, *args, **kwargs):
        station = self.get_object()
        last_inference = _latest_station_inference_result(station.id)

        if last_inference is None:
            return Response(
                {"error": "No forecast data available for this station."},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = {
            "forecast_date": last_inference.inference_run.run_date,
            "aqi_level": last_inference.aqi_input or [],
            "forecast_6h": last_inference.forecasts_6h or [],
            "forecast_12h": last_inference.forecasts_12h or [],
        }
        serializer = ForecastSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def boxplot(self, request, *args, **kwargs):
        station = self.get_object()
        period = request.query_params.get("period", "7d")

        now = timezone.now()
        if period == "7d":
            start_date = now - timedelta(days=7)
            trunc_func = TruncDate
        elif period == "30d":
            start_date = now - timedelta(days=30)
            trunc_func = TruncWeek
        elif period == "1y":
            start_date = now - timedelta(days=365)
            trunc_func = TruncMonth
        else:
            return Response(
                {"error": "Invalid period. Use '7d', '30d' or '1y'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        readings = (
            StationReadingsGold.objects.filter(
                station_id=station.id, date_utc__gte=start_date
            )
            .annotate(period=trunc_func("date_utc"))
            .values("period", "aqi_pm2_5")
        )

        period_values = defaultdict(list)
        for reading in readings:
            if reading["period"] is not None and reading["aqi_pm2_5"] is not None:
                period_values[reading["period"]].append(reading["aqi_pm2_5"])

        box_data = {
            "x": [],
            "q1": [],
            "median": [],
            "q3": [],
            "lowerfence": [],
            "upperfence": [],
        }

        for period_value, values in sorted(period_values.items()):
            values.sort()
            if len(values) == 1:
                q1 = median_value = q3 = lowerfence = upperfence = values[0]
            else:
                q1, _, q3 = quantiles(values, n=4)
                median_value = median(values)
                iqr = q3 - q1
                lowerfence = max(min(values), q1 - 1.5 * iqr)
                upperfence = min(max(values), q3 + 1.5 * iqr)

            box_data["x"].append(period_value.strftime("%Y-%m-%d"))
            box_data["q1"].append(q1)
            box_data["median"].append(median_value)
            box_data["q3"].append(q3)
            box_data["lowerfence"].append(lowerfence)
            box_data["upperfence"].append(upperfence)

        return Response(box_data, status=status.HTTP_200_OK)


def _parse_bool(value):
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


@extend_schema_view(
    list=extend_schema(
        summary="List platform users",
        parameters=[
            OpenApiParameter(
                name="email",
                type=OpenApiTypes.STR,
                description="Filter by case-insensitive partial email match.",
            ),
            OpenApiParameter(
                name="role",
                type=OpenApiTypes.STR,
                enum=[choice.value for choice in UserRole],
                description="Filter by exact role.",
            ),
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                description="Filter by active status.",
            ),
        ],
    ),
    create=extend_schema(summary="Create a platform user"),
    retrieve=extend_schema(summary="Retrieve a platform user"),
    partial_update=extend_schema(summary="Update a platform user"),
    destroy=extend_schema(summary="Deactivate (soft delete) a platform user"),
)
@extend_schema(tags=["Admin Users"])
class AdminUserViewSet(ModelViewSet):
    """Administrative CRUD for platform users and their assigned roles.

    Restricted to authenticated users with the ``admin`` or ``superadmin`` role.
    """

    queryset = User.objects.select_related("profile").all().order_by("id")
    permission_classes = [IsAuthenticated, IsAdminRole]
    pagination_class = StandardResultsSetPagination
    http_method_names = ["get", "post", "patch", "delete"]

    def get_serializer_class(self):
        if self.action == "create":
            return AdminUserCreateSerializer
        if self.action in {"update", "partial_update"}:
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        email = self.request.query_params.get("email")
        if email:
            queryset = queryset.filter(email__icontains=email)

        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(profile__role=role)

        is_active = _parse_bool(self.request.query_params.get("is_active"))
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        return queryset

    def perform_destroy(self, instance):
        """Soft delete: deactivate the account instead of removing the row."""
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance == request.user:
            raise PermissionDenied("You cannot delete your own account.")
        return super().destroy(request, *args, **kwargs)


def _dashboard_sensor(station):
    details = getattr(station, "details", None)
    last_reading = (
        StationReadingsGold.objects.filter(station_id=station.id)
        .order_by("-date_utc")
        .first()
    )
    return {
        "id": station.id,
        "name": station.name,
        "status": "online" if station.is_station_on else "offline",
        "location": {
            "city": details.city if details else None,
            "specific_location": details.specific_location if details else None,
            "latitude": station.latitude,
            "longitude": station.longitude,
        },
        "last_measurement_at": last_reading.date_utc if last_reading else None,
    }, last_reading


def _dashboard_air_quality(last_reading):
    if last_reading is None or last_reading.aqi_pm2_5 is None:
        return None
    level = classify_aqi(last_reading.aqi_pm2_5)
    return {
        "aqi": last_reading.aqi_pm2_5,
        "category": level["key"],
        "category_label": level["label"],
        "message": level["message"],
        "recommendations": level["recommendations"],
    }


def _dashboard_history(station):
    """Daily-averaged AQI for the trailing three months, oldest first.

    Aggregated by day (rather than raw readings) so three months of data
    stays a chart-sized payload instead of tens of thousands of points.
    """
    start_date = timezone.now() - relativedelta(months=3)
    rows = (
        StationReadingsGold.objects.filter(
            station_id=station.id, date_utc__gte=start_date, aqi_pm2_5__isnull=False
        )
        .annotate(day=TruncDate("date_utc"))
        .values("day")
        .annotate(aqi=Avg("aqi_pm2_5"))
        .order_by("day")
    )
    return [{"date": row["day"], "aqi": row["aqi"]} for row in rows]


def _dashboard_alert_config(institution):
    alert_config = getattr(institution, "alert_config", None)
    if alert_config is None:
        return {"is_enabled": False, "alert_threshold": None, "sensitive_groups": []}
    return {
        "is_enabled": alert_config.is_enabled,
        "alert_threshold": alert_config.alert_threshold,
        "sensitive_groups": list(alert_config.sensitive_groups.all()),
    }


def _build_institution_dashboard(institution):
    contract = getattr(institution, "contract", None)
    if contract is None:
        raise NotFound("This institution does not have an assigned sensor.")

    sensor, last_reading = _dashboard_sensor(contract.station)
    return {
        "sensor": sensor,
        "air_quality": _dashboard_air_quality(last_reading),
        "history": _dashboard_history(contract.station),
        "alert_config": _dashboard_alert_config(institution),
    }


def _notification_from_alert(alert):
    """One AQI-triggered alert, as a notification.

    The wording is read back from the rule that fired it rather than stored on
    the event: ``InstitutionAlertRule`` owns the copy an institution configured,
    and ``message_for`` is the same call the sender used, so the dashboard shows
    what the devices were sent. The trade-off is deliberate — editing a rule
    later also changes how its past notifications read here.

    ``rule`` is ``SET_NULL``, so events survive the rule that produced them and
    rows predating the rules have none at all. Both fall back to the AQI level's
    own label and message, which is what the notification was about anyway.
    """
    station = alert.station
    level = classify_aqi(alert.aqi_value)

    if alert.rule is not None:
        title, body = alert.rule.message_for(station.name if station else "")
    elif level is not None:
        title, body = level["label"], level["message"]
    else:
        title, body = "", ""

    return {
        "id": f"alert-{alert.id}",
        "type": InstitutionNotificationSerializer.TYPE_AQI,
        "title": title,
        "body": body,
        "sent_at": alert.triggered_at,
        "station": alert.station_id,
        "station_name": station.name if station else None,
        "aqi": alert.aqi_value,
        "aqi_category": level["key"] if level else None,
        "aqi_category_label": level["label"] if level else None,
        "alert_threshold": alert.alert_threshold,
        "alert": alert.id,
    }


def _notification_from_broadcast(broadcast):
    """One manually sent broadcast, as a notification.

    Everything AQI-shaped is null: a broadcast carries an operational message —
    "mantenimiento del sensor el martes" — that has nothing to do with a
    reading, which is why the model has no threshold and no level.

    ``station`` is null for institution-scoped sends, which reach every station
    the institution holds. The dashboard shows one sensor, so there is nothing
    more specific to name.
    """
    station = broadcast.station
    return {
        "id": f"broadcast-{broadcast.id}",
        "type": InstitutionNotificationSerializer.TYPE_GENERAL,
        "title": broadcast.push_title,
        "body": broadcast.push_body,
        "sent_at": broadcast.sent_at,
        "station": broadcast.station_id,
        "station_name": station.name if station else None,
        "aqi": None,
        "aqi_category": None,
        "aqi_category_label": None,
        "alert_threshold": None,
        "alert": None,
    }


def _institution_notifications(institution):
    """Both notification feeds for one institution, merged newest-first.

    Merged in memory rather than in the database: the two tables share no
    columns worth a UNION, and an institution's notification history is small
    enough (one sensor, one institution) that reading both and sorting is
    cheaper than the machinery a database-level merge would need.

    Platform-wide broadcasts (``scope="all"``) are left out. They carry no
    institution and are announcements to every follower on the platform, so
    they are not notifications *about this sensor* — which is what this section
    promises to show.
    """
    if institution is None:
        return []

    alerts = (
        InstitutionAlert.objects.filter(institution=institution)
        .select_related("station", "rule")
        .order_by("-triggered_at", "-id")
    )
    broadcasts = (
        PushBroadcast.objects.filter(institution=institution)
        .exclude(scope=PushBroadcast.SCOPE_ALL)
        .select_related("station")
        .order_by("-sent_at", "-id")
    )

    notifications = [_notification_from_alert(alert) for alert in alerts]
    notifications += [
        _notification_from_broadcast(broadcast) for broadcast in broadcasts
    ]

    # Newest first, with the id breaking ties so two notifications stamped in
    # the same instant still come back in a stable order — the same guarantee
    # `ActionLog.Meta.ordering` gives the action history, which a merged list
    # has to reproduce by hand.
    notifications.sort(key=lambda item: (item["sent_at"], item["id"]), reverse=True)
    return notifications


def _absolute_for_email(request, configured: str) -> str:
    """Resolves a configured path (or URL) against the request being served.

    Settings that end up inside an email hold a *path* by default, and the
    scheme and host come from the request — so what the recipient receives
    points at whatever environment they asked from (local, demo, production)
    rather than a URL baked into the image. An absolute URL in the setting wins,
    for a deployment where the site and the API do not share an origin.
    """
    if configured.startswith(("http://", "https://")):
        return configured.rstrip("/")
    return request.build_absolute_uri(configured).rstrip("/")


@extend_schema(tags=["Institutional Dashboard"])
class InstitutionViewSet(ReadOnlyModelViewSet):
    """Self-service, read-only view of an institution's own dashboard data.

    Distinct from the Django Admin's Institution CRUD (backoffice-only,
    session-authenticated staff): this is what the institutional dashboard
    itself consumes. Access is limited to the institution the caller is
    linked to via ``InstitutionUser`` (see ``IsInstitutionUser`` /
    ``IsOwnInstitution``), never another institution's records.

    ``list`` is scoped through ``get_queryset`` — DRF does not run
    object-level permissions per row — while ``retrieve`` relies on
    ``IsOwnInstitution`` so requesting another institution's id by pk still
    returns 403 rather than leaking its existence via a 200.
    """

    serializer_class = InstitutionSerializer
    permission_classes = [IsAuthenticated, IsInstitutionUser, IsOwnInstitution]
    # Declared so the password-reset actions below can override it through
    # `@action(throttle_scope=...)`: DRF's `as_view` rejects any initkwarg that
    # is not already an attribute of the viewset. `None` leaves every other
    # route unthrottled, which is what `ScopedRateThrottle` does with no scope.
    throttle_scope = None
    # Unpaginated by default — an institution has one of itself to list. Named
    # here for the same reason as `throttle_scope`: `as_view` rejects an
    # initkwarg that is not already an attribute, and the `notifications`
    # action sets its own.
    pagination_class = None
    # "get" for list/retrieve/me, "post" for the login/logout actions below —
    # this viewset otherwise offers no write access to Institution itself.
    http_method_names = ["get", "post"]

    def get_queryset(self):
        if self.action == "list":
            institution = get_institution_for_user(self.request.user)
            if institution is None:
                return Institution.objects.none()
            return Institution.objects.filter(pk=institution.pk)
        return Institution.objects.all()

    @extend_schema(summary="Retrieve the caller's own institution")
    @action(detail=False, methods=["get"])
    def me(self, request, *args, **kwargs):
        institution = get_institution_for_user(request.user)
        serializer = self.get_serializer(institution)
        return Response(serializer.data)

    @extend_schema(
        summary="Retrieve the caller's institutional dashboard",
        description=(
            "Consolidated data for the Institution Dashboard: the assigned "
            "sensor, current air quality (AQI, category, interpretive "
            "message and recommendation), three months of measurement "
            "history, and the institution's alert configuration (enabled "
            "flag, AQI threshold and configured sensitive groups). The "
            "institution is resolved automatically from the authenticated "
            "user — never from a request parameter — so a caller can only "
            "ever retrieve their own institution's data. Returns 404 when "
            "the institution has no assigned sensor yet; `air_quality` is "
            "`null` when the sensor has not reported a measurement yet."
        ),
        responses=InstitutionDashboardSerializer,
    )
    @action(detail=False, methods=["get"])
    def dashboard(self, request, *args, **kwargs):
        institution = get_institution_for_user(request.user)
        payload = _build_institution_dashboard(institution)
        serializer = InstitutionDashboardSerializer(payload)
        return Response(serializer.data)

    @extend_schema(
        summary="List the alerts recorded for the caller's institution",
        description=(
            "Air-quality events recorded for the institution's own sensor, "
            "most recent first. Read-only: alerts are produced by the "
            "platform, not authored by institutions. This is what makes "
            "`ActionLog.alert` usable from a client — without it the field is "
            "writable but a caller has no way to discover a valid id."
        ),
        responses=InstitutionAlertSerializer(many=True),
    )
    @action(detail=False, methods=["get"], serializer_class=InstitutionAlertSerializer)
    def alerts(self, request, *args, **kwargs):
        """Scoped in the queryset, like ``list``.

        Registered as a router action rather than a plain path, which also
        settles the ordering problem: the router emits dynamic list routes
        before ``institution/{pk}/``, so "alerts" is never read as a pk.
        """
        institution = get_institution_for_user(request.user)
        queryset = (
            InstitutionAlert.objects.filter(institution=institution).select_related(
                "station"
            )
            if institution is not None
            else InstitutionAlert.objects.none()
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="List the notifications sent about the caller's own sensor",
        description=(
            "Every notification sent about the institution's own sensor, most "
            "recent first: the AQI-triggered alerts its configured rules fired "
            "and the general, manually sent announcements, merged into one "
            "feed. Read-only — notifications are produced by the platform's "
            "scheduled sender or by an operator, never authored here.\n\n"
            "`type` says which kind each one is. Everything AQI-specific "
            "(`aqi`, `aqi_category`, `alert_threshold`, `alert`) is null on a "
            "general notification, so clients must key off `type` rather than "
            "assume those fields are present.\n\n"
            "The institution is resolved from the authenticated user — never "
            "from a request parameter — so a caller can only ever see "
            "notifications about their own sensor. Platform-wide announcements "
            "are excluded: they belong to every follower, not to this sensor."
        ),
        responses=InstitutionNotificationSerializer(many=True),
    )
    @action(
        detail=False,
        methods=["get"],
        serializer_class=InstitutionNotificationSerializer,
        # Set on this action alone rather than on the viewset: the viewset has
        # no `pagination_class`, and giving it one here would silently start
        # paginating `list`, `retrieve` and `alerts` as well. This feed is the
        # one that grows without bound — a sensor accumulates notifications for
        # as long as it is leased — so it is the one that has to be cut into
        # pages.
        pagination_class=StandardResultsSetPagination,
    )
    def notifications(self, request, *args, **kwargs):
        """Scoped from the session, like ``alerts``.

        Paginated over an already-merged list rather than a queryset: the two
        sources are separate tables, so the merge has to happen before the page
        is cut or a page would only ever hold one kind. ``paginate_queryset``
        takes a list just as happily as a queryset.
        """
        notifications = _institution_notifications(
            get_institution_for_user(request.user)
        )

        page = self.paginate_queryset(notifications)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Log in to the institutional dashboard",
        request=InstitutionLoginSerializer,
        responses=InstitutionSerializer,
    )
    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def login(self, request, *args, **kwargs):
        """Authenticate and start a session, same as the admin login form.

        Kept off ``IsInstitutionUser``/``IsAuthenticated`` (unlike every other
        action here) since, by definition, the caller isn't authenticated yet.
        Institution membership is checked *after* credentials succeed, so a
        valid admin/staff login without an Institution link gets a 403 here
        rather than a session — this endpoint only ever signs a caller into
        their own institutional dashboard, never into the backoffice.
        """
        serializer = InstitutionLoginSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        institution = get_institution_for_user(user)
        if institution is None:
            raise PermissionDenied(
                "This account does not have access to an institutional dashboard."
            )

        auth_login(request, user)
        # Forces the CSRF cookie to be set on the response so the frontend can
        # send it back on subsequent unsafe (non-GET) requests in this session.
        get_token(request)
        return Response(InstitutionSerializer(institution).data)

    @extend_schema(summary="Log out of the institutional dashboard")
    @action(detail=False, methods=["post"])
    def logout(self, request, *args, **kwargs):
        auth_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Request a password reset email",
        description=(
            "Starts Django's password reset workflow for the given address. "
            "Always answers 204, whether or not an account exists, so the "
            "endpoint cannot be used to find out which addresses are "
            "registered. The email carries a signed, time-limited link "
            "(`PASSWORD_RESET_TIMEOUT`) pointing at the public reset page."
        ),
        request=InstitutionPasswordResetSerializer,
        responses={204: None},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="password-reset",
        permission_classes=[AllowAny],
        throttle_classes=[ScopedRateThrottle],
        throttle_scope="password_reset",
        serializer_class=InstitutionPasswordResetSerializer,
    )
    def password_reset(self, request, *args, **kwargs):
        """Send a reset link, without revealing whether the address is known.

        Built on ``django.contrib.auth.forms.PasswordResetForm``, so the set of
        accounts that may be reset is Django's own: active users with a usable
        password. Nothing about the outcome reaches the caller — the response is
        identical for a registered address, an unregistered one, and an inactive
        account.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        form = PasswordResetForm(data={"email": serializer.validated_data["email"]})
        # `is_valid` only re-checks the address' shape here, which the serializer
        # already did; `save` is what looks accounts up and sends the mail.
        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                subject_template_name="institution/password_reset_subject.txt",
                email_template_name="institution/password_reset_email.txt",
                # Sent as a multipart message: the plain-text body above stays
                # the fallback (clients with HTML off, and what spam filters
                # read), with this as the alternative part.
                html_email_template_name="institution/password_reset_email.html",
                extra_email_context={
                    "reset_base_url": _absolute_for_email(
                        request, settings.INSTITUTION_PASSWORD_RESET_URL
                    ),
                    # Remote image: it has to be reachable from the recipient's
                    # mail client, so it resolves to the public site rather than
                    # to anything internal.
                    "logo_url": _absolute_for_email(
                        request, settings.INSTITUTION_EMAIL_LOGO_URL
                    ),
                    "timeout_hours": settings.PASSWORD_RESET_TIMEOUT // 3600,
                },
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Set a new password from a reset link",
        description=(
            "Completes the password reset. `uid` and `token` are the values "
            "carried by the emailed link. Returns 400 when the link is "
            "expired, malformed, already used or belongs to an inactive "
            "account, and 400 with `new_password` errors when the password "
            "does not satisfy the platform's password rules."
        ),
        request=InstitutionPasswordResetConfirmSerializer,
        responses={204: None},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="password-reset/confirm",
        permission_classes=[AllowAny],
        throttle_classes=[ScopedRateThrottle],
        throttle_scope="password_reset_confirm",
        serializer_class=InstitutionPasswordResetConfirmSerializer,
    )
    def password_reset_confirm(self, request, *args, **kwargs):
        """Consume a reset link and store the new password.

        The old password stops working the moment this succeeds, and so does
        the link: Django's token hashes the password and ``last_login``, so a
        second POST with the same `uid`/`token` fails validation.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Sessions the account had open elsewhere die with the old password:
        # Django stores a hash of it in the session and `auth.get_user` rejects
        # any session whose hash no longer matches. Nothing to flush by hand.
        serializer.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="List the caller's institutional action history",
        description=(
            "Actions recorded by the authenticated user's institution, most "
            "recent first. The institution is resolved from the session, so "
            "the history never contains another institution's records."
        ),
    ),
    create=extend_schema(
        summary="Record an action taken by the caller's institution",
        description=(
            "Creates one entry in the institutional action history. "
            "`institution` and `timestamp` are assigned by the backend and "
            "ignored if sent. `station` must be the station the institution "
            "holds a contract for; `alert` is optional and, when given, must "
            "belong to the same institution and station."
        ),
    ),
)
@extend_schema(tags=["Institutional Dashboard"])
class ActionLogViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, GenericViewSet):
    """Create and list an institution's record of actions taken.

    Deliberately create + list only: the action history is an audit trail, so
    entries are never edited or removed through the API — which is also why
    ``timestamp`` is stamped by the model rather than accepted from a client.

    Scoping works the same way as ``InstitutionViewSet``: ``get_queryset``
    filters the list down to the caller's own institution (DRF does not run
    object-level permissions per row), and the serializer refuses a station or
    alert belonging to anyone else on the way in.
    """

    serializer_class = ActionLogSerializer
    permission_classes = [IsAuthenticated, IsInstitutionUser]
    pagination_class = StandardResultsSetPagination
    http_method_names = ["get", "post"]

    def get_queryset(self):
        institution = get_institution_for_user(self.request.user)
        if institution is None:
            return ActionLog.objects.none()
        return ActionLog.objects.filter(institution=institution).select_related(
            "institution", "station", "alert"
        )

    def get_serializer_context(self):
        """Hand the caller's institution to the serializer's validation.

        Passed explicitly rather than re-resolved inside each validator, so the
        institution used for authorization is the same object the created row
        is assigned to.
        """
        context = super().get_serializer_context()
        context["institution"] = get_institution_for_user(self.request.user)
        return context

    def perform_create(self, serializer):
        serializer.save(institution=get_institution_for_user(self.request.user))


@extend_schema(
    responses=FaqCategorySerializer(many=True),
    description=(
        "Published FAQ categories with their published questions, ordered for "
        "display. Every question carries all supported languages; untranslated "
        "fields fall back to Spanish."
    ),
)
class FaqListView(generics.ListAPIView):
    """Public, read-only feed for the /recursos page.

    Unpublished categories and questions are filtered out here rather than in
    the frontend, so a draft is never shipped to the browser.
    """

    serializer_class = FaqCategorySerializer
    pagination_class = None

    def get_queryset(self):
        return (
            FaqCategory.objects.filter(is_published=True)
            .prefetch_related(
                Prefetch(
                    "questions",
                    queryset=FaqQuestion.objects.filter(is_published=True).order_by(
                        "order", "id"
                    ),
                )
            )
            .order_by("order", "id")
        )


# --- Device followers (respira-mobile, unauthenticated) ---------------------

INSTALLATION_ID_HEADER = "X-Installation-Id"

# How many stations one installation may follow. A bound on abuse of an
# unauthenticated endpoint rather than a product limit, which is why it lives
# here and is tunable rather than being a database constraint.
MAX_FOLLOWS_PER_INSTALLATION = getattr(settings, "MAX_FOLLOWS_PER_INSTALLATION", 10)

INSTALLATION_ID_PARAMETER = OpenApiParameter(
    name=INSTALLATION_ID_HEADER,
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "UUIDv4 identifying the app installation. Preferred over the "
        "`installation_id` query parameter, which is also accepted but ends "
        "up written to proxy access logs."
    ),
)

INSTALLATION_ID_QUERY_PARAMETER = OpenApiParameter(
    name="installation_id",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Fallback for clients that cannot set the header.",
)


def _resolve_installation_id(request) -> uuid.UUID:
    """Read the caller's installation id from header, query string or body.

    Three sources because the same identifier has to travel on requests that
    have no body (GET, DELETE) and on ones that do. The header is listed first
    and documented as preferred: a query string is recorded verbatim in the
    proxy's access log, and this is the only identifier the feature has.

    Version 4 is required, not merely a well-formed UUID. A v1 UUID encodes a
    MAC address and a timestamp and a v5 is a hash of some seed — both are the
    derived, guessable kind of identifier this feature deliberately rejected,
    so the rule is enforced here rather than left to a mobile code review.
    """
    raw = (
        request.headers.get(INSTALLATION_ID_HEADER)
        or request.query_params.get("installation_id")
        or (
            request.data.get("installation_id")
            if isinstance(request.data, dict)
            else None
        )
    )
    if not raw:
        raise ValidationError(
            {
                "installation_id": (
                    f"Required, in the {INSTALLATION_ID_HEADER} header, the "
                    "'installation_id' query parameter or the request body."
                )
            }
        )
    try:
        installation_id = uuid.UUID(str(raw))
    except (AttributeError, TypeError, ValueError):
        raise ValidationError({"installation_id": "Must be a valid UUID."})
    if installation_id.version != 4:
        raise ValidationError({"installation_id": "Must be a random (version 4) UUID."})
    return installation_id


@extend_schema(tags=["Device Followers"])
class DeviceFollowerView(APIView):
    """The stations a mobile installation follows, with no login involved.

    Deliberately unauthenticated: the app identifies itself with the UUIDv4 it
    generated on first launch, and that unguessable value is what stands in for
    a credential. The throttle below is the compensating control — it bounds
    what an abusive client can do without penalising a whole carrier NAT.

    Not a router-backed ``ViewSet``: the collection has to answer ``DELETE`` as
    well as ``GET`` and ``POST``, and the default router only maps the first
    two onto a list URL.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "device_followers"

    @extend_schema(
        summary="List the stations this installation follows",
        description=(
            "Returns an empty list — not a 404 — for an installation that has "
            "never followed anything, which is the normal state of a fresh "
            "install. Each `station` is resolved fresh on every read, so it is "
            "always the station's current id even after the pipeline renumbers "
            "them; it is null if that station no longer exists."
        ),
        parameters=[INSTALLATION_ID_PARAMETER, INSTALLATION_ID_QUERY_PARAMETER],
        responses={200: DeviceFollowerSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        installation_id = _resolve_installation_id(request)
        follows = DeviceFollower.objects.filter(
            installation__installation_id=installation_id
        )
        return Response(DeviceFollowerSerializer(follows, many=True).data)

    @extend_schema(
        summary="Follow a station",
        description=(
            "Adds a station to what this installation follows. Repeating the "
            "same request is safe: it returns 200 with the existing follow "
            "instead of creating a second one or failing. Returns 201 the "
            f"first time. An installation may follow up to "
            f"{MAX_FOLLOWS_PER_INSTALLATION} stations."
        ),
        parameters=[INSTALLATION_ID_PARAMETER],
        request=DeviceFollowerWriteSerializer,
        responses={200: DeviceFollowerSerializer, 201: DeviceFollowerSerializer},
    )
    def post(self, request, *args, **kwargs):
        installation_id = _resolve_installation_id(request)
        serializer = DeviceFollowerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        station = serializer.validated_data["station"]
        push_token = serializer.validated_data.get("push_token")

        with transaction.atomic():
            installation, _ = DeviceInstallation.register(
                installation_id, push_token=push_token
            )
            # The *installation* is what gets locked, not the follow: two
            # requests adding two different stations would each find no
            # existing row to lock, both read a count under the cap, and both
            # insert. Locking the row every follow of this installation hangs
            # off serialises them, so the count below is the real one.
            installation = DeviceInstallation.objects.select_for_update().get(
                pk=installation.pk
            )
            existing = installation.follows.filter(
                station_code=station.station_code
            ).first()
            if existing is not None:
                return Response(DeviceFollowerSerializer(existing).data)

            if installation.follows.count() >= MAX_FOLLOWS_PER_INSTALLATION:
                # A machine-readable `code`, not just prose: the app has to
                # tell this apart from the other 400 this endpoint can return
                # (a station with no `station_code`) to say something true to
                # the user, and it cannot do that by matching on an English
                # sentence it would then have to keep in step.
                return Response(
                    {
                        "code": "max_follows_reached",
                        "max": MAX_FOLLOWS_PER_INSTALLATION,
                        "detail": (
                            "This installation already follows the maximum of "
                            f"{MAX_FOLLOWS_PER_INSTALLATION} stations. Unfollow "
                            "one before adding another."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            follow = DeviceFollower.objects.create(
                installation=installation, station_code=station.station_code
            )

        # Outside the transaction on purpose. This calls the push service, and
        # doing that while still holding `select_for_update` on the
        # installation would block every other follow by the same device for
        # the length of an HTTP round trip.
        #
        # Only on a new follow — the `existing` branch above returns before
        # here, so re-sending the same request does not re-send the push.
        catch_up_follower(installation, station)

        return Response(
            DeviceFollowerSerializer(follow).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Stop following one station, or all of them",
        description=(
            "Pass `station_code` — or `station`, its current id — to unfollow "
            "that one; omit both to unfollow everything this installation "
            "follows. Idempotent: returns 204 whether or not anything was "
            "there to delete.\n\n"
            "`station_code` is the one that always works. A station the "
            "pipeline has dropped no longer has an id to look up, so a follow "
            "left pointing at it could never be removed by id — and that is "
            "exactly the follow a user most wants off their list."
        ),
        parameters=[
            INSTALLATION_ID_PARAMETER,
            INSTALLATION_ID_QUERY_PARAMETER,
            OpenApiParameter(
                name="station_code",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Stable code of the station to unfollow. Preferred over "
                    "`station`; takes precedence when both are sent. Sending "
                    "it blank is a 400 — omit it to unfollow everything."
                ),
            ),
            OpenApiParameter(
                name="station",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Current id of the station to unfollow. Omit both to "
                    "unfollow all of them."
                ),
            ),
        ],
        responses={204: None},
    )
    def delete(self, request, *args, **kwargs):
        installation_id = _resolve_installation_id(request)
        follows = DeviceFollower.objects.filter(
            installation__installation_id=installation_id
        )

        station_code = request.query_params.get("station_code")
        raw_station = request.query_params.get("station")

        if station_code is not None:
            # Rejected rather than ignored: omitting the parameter is how a
            # caller asks to unfollow *everything*, so treating `?station_code=`
            # as absent would turn a malformed single unfollow into wiping the
            # whole list.
            if not station_code:
                raise ValidationError({"station_code": "Must not be blank."})
            # Matched directly against what the row stores, so this works even
            # for a station that no longer exists.
            follows = follows.filter(station_code=station_code)
        elif raw_station is not None:
            try:
                station_id = int(raw_station)
            except (TypeError, ValueError):
                raise ValidationError({"station": "Must be an integer station id."})

            station = Stations.objects.filter(id=station_id).first()
            # A station the pipeline has already dropped cannot be looked up to
            # get its code, so there is nothing to match on. That is still a
            # successful unfollow of nothing rather than an error — the caller
            # asked for that station not to be followed, and it is not.
            if station is None or not station.station_code:
                return Response(status=status.HTTP_204_NO_CONTENT)

            follows = follows.filter(station_code=station.station_code)

        follows.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Device Followers"])
class DeviceInstallationView(APIView):
    """The installation itself, addressed by its own id.

    The push token lives here rather than on each follow: the OS rotates it at
    any time and independently of which stations are followed, and with several
    follows a per-row copy would have to be kept in step across all of them —
    and a notification fan-out would deliver once per follow to the same phone.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "device_followers"

    @extend_schema(
        summary="Read this installation's registration",
        description=(
            "Returns 404 for an installation the backend has never seen. The "
            "push token is reported as a boolean, never echoed: these "
            "endpoints are unauthenticated, so anyone holding an installation "
            "id could otherwise read the device's token."
        ),
        parameters=[INSTALLATION_ID_PARAMETER, INSTALLATION_ID_QUERY_PARAMETER],
        responses={200: DeviceInstallationSerializer},
    )
    def get(self, request, *args, **kwargs):
        installation_id = _resolve_installation_id(request)
        installation = DeviceInstallation.objects.filter(
            installation_id=installation_id
        ).first()
        if installation is None:
            raise NotFound("This installation has not registered.")
        return Response(DeviceInstallationSerializer(installation).data)

    @extend_schema(
        summary="Register or refresh the push token",
        description=(
            "Creates the installation if the backend has not seen it before, "
            "so the app can register a token before following anything. "
            "Registering a token also clears it from any other installation "
            "holding it, which is what stops a reinstall — new installation id, "
            "same token from the OS — being notified twice."
        ),
        parameters=[INSTALLATION_ID_PARAMETER],
        request=DeviceInstallationWriteSerializer,
        responses={200: DeviceInstallationSerializer},
    )
    def put(self, request, *args, **kwargs):
        installation_id = _resolve_installation_id(request)
        serializer = DeviceInstallationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        installation, _ = DeviceInstallation.register(
            installation_id, push_token=serializer.validated_data["push_token"]
        )
        return Response(DeviceInstallationSerializer(installation).data)
