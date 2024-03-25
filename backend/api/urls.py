from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CarViewset, StationViewset, StationReadingsViewset

router = DefaultRouter()
router.register('cars', CarViewset, basename='cars')
router.register('stations', StationViewset, basename = 'stations')
router.register('station_values', StationReadingsViewset, basename = 'station_values')

urlpatterns = [
    path('', include(router.urls)),
]