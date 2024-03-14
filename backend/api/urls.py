from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CarViewset, StationViewset, StationValuesViewset, AreaViewset, AreaValuesViewset

router = DefaultRouter()
router.register('cars', CarViewset, basename='cars')
router.register('stations', StationViewset, basename = 'stations')
router.register('station_values', StationValuesViewset, basename = 'station_values')
router.register('area', AreaViewset, basename = 'area')
router.register('area_values', AreaValuesViewset, basename = 'area_values')

urlpatterns = [
    path('', include(router.urls)),
]