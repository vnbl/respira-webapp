from rest_framework import serializers
from .models import Stations, Forecasts

class StationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stations
        fields = ['id', 'name', 'description', 'coordinates', 
                  'region', 'is_station_on', 'active_params', 
                  'online_since', 'last_update']
        
class ForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = Forecasts
        fields = '__all__'