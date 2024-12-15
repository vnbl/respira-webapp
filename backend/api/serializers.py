from rest_framework import serializers
from .models import Regions, Stations, StationReadingsGold


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regions
        fields = ['id', 'name', 'region_code', 'bbox', 'has_weather_data', 'has_pattern_station']


class StationSerializer(serializers.ModelSerializer):
    region = RegionSerializer()
    aqi_pm2_5 = serializers.SerializerMethodField()
    
    class Meta:
        model = Stations
        fields = ['id', 'name', 'region', 'coordinates', 'is_station_on', 'is_pattern_station', 'aqi_pm2_5']

    def get_aqi_pm2_5(self, obj):
        last_reading = StationReadingsGold.objects.filter(station_id=obj.id).order_by('-date_utc').first()
        return last_reading.aqi_pm2_5 if last_reading else None

    @property
    def coordinates(self):
        return (self.latitude, self.longitude)


class MapSerializer(serializers.Serializer):
    aqi = serializers.IntegerField()
    forecast_6h = serializers.JSONField()
    forecast_12h = serializers.JSONField()


class ForecastSerializer(serializers.Serializer):
    forecast_date = serializers.DateTimeField()
    aqi = serializers.JSONField()
    forecast_6h = serializers.JSONField()
    forecast_12h = serializers.JSONField()


class HistorySerializer(serializers.Serializer):
    historical_1d = serializers.JSONField()
    historical_7d = serializers.JSONField()
    historical_30d = serializers.JSONField()