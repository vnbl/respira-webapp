from django.db import models
from enum import Enum


class Region(models.TextChoices):
    ASUNCION = "ASUNCION",
    CENTRAL = "CENTRAL"
    CHACO = "PRESIDENTE HAYES"
    

class Station(models.Model):
    '''
    Example:
    - name = 'Barrio Jara'
    - station_id = 6
    - latitude = "-25.28833455406130"
    - longitude = "-57.60329900309440"

    '''
    name = models.CharField(max_length = 100) 
    latitude = models.FloatField()
    longitude = models.FloatField()
    region = models.CharField(max_length = 100, choices = Region.choices, default = Region.ASUNCION)

    def __str__(self):
        return f"{self.name} {self.region}"


class StationReadings(models.Model):
    # ID info
    station = models.ForeignKey(Station, on_delete = models.RESTRICT)
    date = models.DateTimeField() 
    # Measured values
    pm1 = models.FloatField() # in ug/m^3
    pm2_5 = models.FloatField() # in ug/m^3
    pm10 = models.FloatField() # in ug/m^3
    temperature = models.FloatField() # in °C
    humidity = models.FloatField() # in % , should we add a validator here?
    pressure = models.FloatField() # in Pa
    # AQI values. Note: these are not direct measurements. 
    # They are calculated based on pm2_5 and pm10 averages over 24hs using a formula
    aqi_pm2_5 = models.FloatField() 
    aqi_pm10 = models.FloatField() 

    def __str__(self):
        return f"{self.station} {self.date}"