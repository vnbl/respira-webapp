from django.urls import path, include
from rest_framework.routers import DefaultRouter

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import StationViewset, RegionViewset, MapViewset, HealthCheckView

router = DefaultRouter()

router.register(r'regions', RegionViewset, basename='regions')
router.register(r'stations', StationViewset, basename='stations')

urlpatterns = [
    path(r'', include(router.urls)),
    path(r'map/', MapViewset.as_view(), name='map'),
    path(r'health/', HealthCheckView.as_view(), name='health'),
    path(r'schema/', SpectacularAPIView.as_view(), name='schema'),
    path(r'schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]