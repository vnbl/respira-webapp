from typing import List
from django.db import models


class RegionCodes(models.TextChoices):
    ASUNCION = ('ASUNCION', 'ASUNCION')


class Regions(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    region_code = models.CharField(max_length=255, choices=RegionCodes.choices, blank=True, null=True)
    bbox = models.CharField(max_length=255, blank=True, null=True)
    has_weather_data = models.BooleanField(default=False)
    has_pattern_station = models.BooleanField(default=False)

    class Meta:
        db_table = 'regions'


class Stations(models.Model):
    name = models.CharField(max_length=255)
    region = models.ForeignKey('Regions', on_delete=models.DO_NOTHING)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    is_station_on = models.BooleanField(default=False)
    is_pattern_station = models.BooleanField(default=False)

    class Meta:
        db_table = 'stations'

    @property
    def coordinates(self):
        return (self.latitude, self.longitude)


class RegionReadings(models.Model):
    region = models.ForeignKey('Regions', on_delete=models.DO_NOTHING)
    date_utc = models.DateTimeField()
    pm2_5_region_avg = models.FloatField(blank=True, null=True)
    pm2_5_region_max = models.FloatField(blank=True, null=True)
    pm2_5_region_skew = models.FloatField(blank=True, null=True)
    pm2_5_region_std = models.FloatField(blank=True, null=True)
    aqi_region_avg = models.FloatField(blank=True, null=True)
    aqi_region_max = models.FloatField(blank=True, null=True)
    aqi_region_skew = models.FloatField(blank=True, null=True)
    aqi_region_std = models.FloatField(blank=True, null=True)
    level_region_max = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = 'region_readings'


class StationReadingsGold(models.Model):
    station = models.ForeignKey('Stations', on_delete=models.DO_NOTHING)
    airnow_id = models.IntegerField(blank=True, null=True)
    date_utc = models.DateTimeField(blank=True, null=True)
    pm_calibrated = models.BooleanField(blank=True, null=True)
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

    class Meta:
        db_table = 'station_readings_gold'


class InferenceRuns(models.Model):
    run_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'inference_runs'


class InferenceResults(models.Model):
    inference_run = models.ForeignKey('InferenceRuns', on_delete=models.DO_NOTHING)
    station = models.ForeignKey('Stations', on_delete=models.DO_NOTHING)
    forecasts_6h = models.JSONField(blank=True, null=True)
    forecasts_12h = models.JSONField(blank=True, null=True)
    aqi_input = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = 'inference_results'