from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet

from .models import Stations, Forecasts
from .serializers import StationSerializer, ForecastSerializer

class StationViewset(ModelViewSet):
    queryset = Stations.objects.all()
    serializer_class = StationSerializer

class ForecastViewset(ModelViewSet):
    queryset = Forecasts.objects.all()
    serializer_class = ForecastSerializer

class HistoricalViewset(ModelViewSet):
    pass


class RegionViewset(ModelViewSet):
    pass