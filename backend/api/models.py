from django.db import models

class Car(models.Model):
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.IntegerField()
    color = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.year} {self.make} {self.model}"
    

class Station(models.Model):
    name = models.CharField(max_length = 100)
    station_id = models.IntegerField()
    latitude = models.CharField(max_length = 100)
    longitude = models.CharField(max_length = 100)
    aqi = models.IntegerField()

    def __str__(self):
        return f"{self.station_id} {self.name} {self.aqi}"