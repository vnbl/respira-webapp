from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Car, Station, StationValues, Area, AreaValues
from .serializers import CarSerializer, StationSerializer, StationValuesSerializer, AreaSerializer, AreaValuesSerializer

class CarViewset(ModelViewSet):
    queryset = Car.objects.all()
    serializer_class = CarSerializer

class StationViewset(ModelViewSet):
    queryset = Station.objects.all()
    serializer_class = StationSerializer

class StationValuesViewset(ModelViewSet):
    queryset = StationValues.objects.all()
    serializer_class = StationValuesSerializer

class AreaViewset(ModelViewSet):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer

class AreaValuesViewset(ModelViewSet):
    queryset = AreaValues.objects.all()
    serializer_class = AreaValuesSerializer