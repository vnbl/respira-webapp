from rest_framework import serializers
from .models import Car, Station, StationReadings

class CarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Car
        fields = '__all__'

class StationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Station
        fields = '__all__'

class StationReadingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StationReadings
        fields = '__all__'

