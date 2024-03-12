from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CarViewset, StationViewset

router = DefaultRouter()
router.register('cars', CarViewset, basename='cars')
router.register('stations', StationViewset, basename = 'stations')

urlpatterns = [
    path('', include(router.urls)),
]