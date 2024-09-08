from typing import List
from django.db import models

class RegionCodes(models.TextChoices):
    ASUNCION = ('ASUNCION', 'ASUNCION')
    GRAN_ASUNCION = ('GRAN_ASUNCION', 'GRAN_ASUNCION')
    CHACO = ('CHACO', 'CHACO')


class Regions(models.Model):
    name = models.CharField(max_length=255)
    region_code = models.CharField(max_length=255, choices=RegionCodes.choices)
    bbox = models.CharField(max_length=255)
    has_weather_data = models.BooleanField(default=False)
    has_pattern_station = models.BooleanField(default=False)

    class Meta:
        db_table = 'regions'


class Stations(models.Model):
    name = models.CharField(max_length=255)
    region = models.ForeignKey('Regions', on_delete=models.DO_NOTHING)
    latitude = models.FloatField()
    longitude = models.FloatField()
    is_station_on = models.BooleanField(default=False)
    is_pattern_station = models.BooleanField(default=False)

    class Meta:
        db_table = 'stations'

    @property
    def coordinates(self):
        return (self.latitude, self.longitude)


class StationReadingsGold(models.Model):
    station = models.ForeignKey('Stations', on_delete=models.DO_NOTHING)
    date_localtime = models.DateTimeField()
    pm1 = models.FloatField(blank=True, null=True)
    pm2_5 = models.FloatField(blank=True, null=True)
    pm10 = models.FloatField(blank=True, null=True)
    pm2_5_avg_6h = models.FloatField(blank=True, null=True)
    pm2_5_max_6h = models.FloatField(blank=True, null=True)
    pm2_5_skew_6h = models.FloatField(blank=True, null=True)
    pm2_5_std_6h = models.FloatField(blank=True, null=True)
    aqi_pm2_5 = models.FloatField(blank=True, null=True)
    aqi_pm10 = models.FloatField(blank=True, null=True)
    aqi_level = models.IntegerField(blank=True, null=True)
    aqi_pm2_5_max_24h = models.FloatField(blank=True, null=True)
    aqi_pm2_5_skew_24h = models.FloatField(blank=True, null=True)
    aqi_pm2_5_std_24h = models.FloatField(blank=True, null=True)
    temperature = models.FloatField(blank=True, null=True)
    humidity = models.FloatField(blank=True, null=True)
    pressure = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = 'station_readings_gold'


class InferenceRuns(models.Model):
    run_date = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inference_runs'


class InferenceResults(models.Model):
    inference_run = models.ForeignKey('InferenceRuns', on_delete=models.DO_NOTHING)
    station = models.ForeignKey('Stations', on_delete=models.DO_NOTHING)

    forecast_6h = models.JSONField(blank=True, null=True)
    forecast_12h = models.JSONField(blank=True, null=True)
    aqi_input = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = 'inference_results'