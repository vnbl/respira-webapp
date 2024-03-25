from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Station, StationReadings
from .serializers import StationSerializer, StationReadingsSerializer

class StationViewset(ModelViewSet):
    queryset = Station.objects.all()
    serializer_class = StationSerializer

class StationReadingsViewset(ModelViewSet):
    queryset = StationReadings.objects.all()
    serializer_class = StationReadingsSerializer
