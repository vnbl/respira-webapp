from django.db import models

class Forecasts(models.Model):
    value = models.IntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now=True)


class Regions(models.TextChoices):
    ASUNCION = "ASUNCION",
    CENTRAL = "CENTRAL"
    CHACO = "PRESIDENTE HAYES"


class Stations(models.Model):
    '''
    {
        "id": 10,
        "name": "Campus UNA",
        "description": "Cerca del campus",
        "coord": [
            -25.2800459,
            -57.6343814
        ],
        "region": "Gran Asuncion",
        "is_station_on": true,
        "active_params": {
            "params": "aqi"
        },
        "online_since": "2024-09-02T14:48:12.716Z",
        "last_update": "2024-09-02T14:48:12.716Z"
    }
    '''
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    region = models.CharField(max_length=255)
    is_station_on = models.BooleanField(default=True)
    active_params = models.JSONField(blank=True, null=True)
    online_since = models.DateTimeField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True)
    current_aqi = models.IntegerField(blank=True, null=True)
    last_calculated = models.DateTimeField(auto_now=True)
    forecast = models.ManyToManyField(Forecasts)

    @property
    def coordinates(self):
        return [self.latitude, self.longitude]    


class ForecastData(models.Model):
    aqi = models.IntegerField()
    forecast = models.ForeignKey(Forecasts, on_delete=models.CASCADE)
    stations = models.ForeignKey(Stations, on_delete=models.CASCADE)