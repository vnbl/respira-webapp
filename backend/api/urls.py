from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import StationViewset, RegionViewset

router = DefaultRouter()

router.register(r'regions', RegionViewset, basename='regions')
router.register(r'stations', StationViewset, basename='stations')

urlpatterns = [
    path(r'', include(router.urls)),
]