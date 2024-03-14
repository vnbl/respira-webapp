from rest_framework import serializers
from .models import Car, Station, StationValues, Area, AreaValues

class CarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Car
        fields = '__all__'

class StationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Station
        fields = '__all__'

class StationValuesSerializer(serializers.ModelSerializer):
    class Meta:
        model = StationValues
        fields = '__all__'

class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = '__all__'

class AreaValuesSerializer(serializers.ModelSerializer):
    class Meta:
        model: AreaValues
        fields = '__all__'