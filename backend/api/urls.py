from django.urls import path, include
from rest_framework.routers import DefaultRouter

from rest_framework_nested import routers

from .views import StationViewset, ForecastViewset, HistoricalViewset

router = DefaultRouter()
router.register(r'stations', StationViewset, basename='stations')
router.register(r'forecast', ForecastViewset, basename='regions')
router.register(r'historical', HistoricalViewset, basename='historical')

urlpatterns = [
    path(r'', include(router.urls)),
]