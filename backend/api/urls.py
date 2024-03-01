from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CarViewset

router = DefaultRouter()
router.register('cars', CarViewset, basename='cars')

urlpatterns = [
    path('', include(router.urls)),
]