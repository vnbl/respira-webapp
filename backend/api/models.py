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
    '''
    Example:
    - name = 'Barrio Jara'
    - station_id = 6
    - latitude = "-25.28833455406130"
    - longitude = "-57.60329900309440"

    '''
    name = models.CharField(max_length = 100) 
    station_id = models.IntegerField()
    latitude = models.CharField(max_length = 100)
    longitude = models.CharField(max_length = 100)

    def __str__(self):
        return f"{self.station_id} {self.name}"

class StationValues(models.Model):

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
    
class Area(models.Model):
    # For our project, we only have 1 area, "Gran Asunción". 
    # Could expand in the future (we have sensors in the Chaco region)
    name = models.CharField(max_length = 100) 
    latitude = models.CharField(max_length = 100)
    longitude = models.CharField(max_length = 100)
    # we should perhaps add info about what stations are in the area? how can we do that? 

    def __str__(self):
        return f"{self.name}"
    
class AreaValues(models.Model):
    # ID info
    area = models.ForeignKey(Area, on_delete = models.RESTRICT) #not sure about this RESTRICT
    date = models.DateTimeField()

    # Average values of every station in Area. PM values should not be included.
    temperature = models.FloatField() # in °C
    humidity = models.FloatField() # in % , should we add a validator here?
    pressure = models.FloatField() # in Pa
    # AQI values. Note: these are not direct measurements. 
    # They are calculated based on pm2_5 and pm10 averages over 24hs using a formula
    aqi_pm2_5 = models.FloatField() 
    aqi_pm10 = models.FloatField() 

    def __str__(self):
        return f"{self.area}"



