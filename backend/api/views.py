from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Car, Station
from .serializers import CarSerializer, StationSerializer

class CarViewset(ModelViewSet):
    queryset = Car.objects.all()
    serializer_class = CarSerializer

class StationViewset(ModelViewSet):
    queryset = Station.objects.all()
    serializer_class = StationSerializer