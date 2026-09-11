from django.urls import path, include
from rest_framework.routers import DefaultRouter

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .exports import (
    InstitutionMonthlyReportView,
    InstitutionRawExportView,
    InstitutionReportMonthsView,
)
from .views import (
    ActionLogViewSet,
    AdminUserViewSet,
    DeviceFollowerView,
    DeviceInstallationView,
    FaqListView,
    InstitutionViewSet,
    StationViewset,
    RegionViewset,
    MapViewset,
    HealthCheckView,
    NearestRegionView,
    NearestStationView,
)

router = DefaultRouter()

router.register(r"regions", RegionViewset, basename="regions")
router.register(r"stations", StationViewset, basename="stations")
router.register(r"admin/users", AdminUserViewSet, basename="admin-users")
router.register(r"institution", InstitutionViewSet, basename="institution")
# Top-level rather than nested under "institution/": the institution router
# entry matches any single path segment as a pk, so "institution/actions/"
# would be swallowed by institution-detail depending on registration order.
router.register(r"action-logs", ActionLogViewSet, basename="action-logs")

urlpatterns = [
    # Not router-registered: the collection has to answer DELETE as well as
    # GET and POST, and the default router only maps the first two onto a
    # list URL.
    path(
        r"device-followers/",
        DeviceFollowerView.as_view(),
        name="device-followers",
    ),
    path(
        r"device-installations/me/",
        DeviceInstallationView.as_view(),
        name="device-installation",
    ),
    path(r"map/nearest-region/", NearestRegionView.as_view(), name="nearest-region"),
    path(r"stations/nearest/", NearestStationView.as_view(), name="nearest-station"),
    # Ahead of the router on purpose: it maps `institution/<pk>/` with a
    # permissive pk pattern, so registered after these it would swallow
    # `institution/export/` as a lookup for an institution called "export".
    path(
        r"institution/report/months/",
        InstitutionReportMonthsView.as_view(),
        name="institution-report-months",
    ),
    path(
        r"institution/report/monthly/",
        InstitutionMonthlyReportView.as_view(),
        name="institution-monthly-report",
    ),
    path(
        r"institution/export/",
        InstitutionRawExportView.as_view(),
        name="institution-raw-export",
    ),
    path(r"", include(router.urls)),
    path(r"faq/", FaqListView.as_view(), name="faq"),
    path(r"map/", MapViewset.as_view(), name="map"),
    path(r"health/", HealthCheckView.as_view(), name="health"),
    path(r"schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        r"schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
