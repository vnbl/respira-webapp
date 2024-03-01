from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Car
from .serializers import CarSerializer

class CarViewset(ModelViewSet):
    queryset = Car.objects.all()
    serializer_class = CarSerializer