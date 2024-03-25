from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import StationViewset, StationReadingsViewset

router = DefaultRouter()
router.register('stations', StationViewset, basename = 'stations')
router.register('station_values', StationReadingsViewset, basename = 'station_values')

urlpatterns = [
    path('', include(router.urls)),
]