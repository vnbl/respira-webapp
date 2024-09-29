from datetime import timedelta

from django.utils import timezone
from django.db.models import Avg, Max, OuterRef, Subquery
from django.db.models.functions import TruncDate

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from .models import Stations, Regions, RegionReadings, StationReadingsGold, InferenceRuns, InferenceResults
from .serializers import StationSerializer, RegionSerializer, ForecastSerializer, HistorySerializer


class HealthCheckView(APIView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class MapViewset(APIView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        entity = request.query_params.get('entity')
        entity_id = request.query_params.get('id')

        if not entity or not entity_id:
            return Response({
                "error": "Both 'entity' and 'id' are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        if entity not in ['region', 'station']:
            return Response({
                "error": "'entity' must be either 'region' or 'station'."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            entity_id = int(entity_id)
        except ValueError:
            return Response({
                "error": "'id' must be an integer."
            }, status=status.HTTP_400_BAD_REQUEST)

        # average the aqi of all the stations in the region and their forecast
        if entity == 'region':
            latest_readings = StationReadingsGold.objects.filter(station_id=OuterRef('station_id')).order_by('-timestamp')
            result = StationReadingsGold.objects.filter(station__region_id=entity_id).annotate(
                latest_aqi=Subquery(latest_readings.values('aqi')[:1])
            ).aggregate(average_aqi=Avg('latest_aqi'))

        # get the station and its forecast
        elif entity == 'station':
            latest_readings = StationReadingsGold.objects.filter(station_id=entity_id).order_by('-timestamp').first()
            result = {"station_id": entity_id, "latest_aqi": latest_readings.aqi if latest_readings else None}

        return Response(result, status=status.HTTP_200_OK)
    

class RegionViewset(ModelViewSet):
    queryset = Regions.objects.filter(id=1)
    serializer_class = RegionSerializer
    http_method_names = ['get']

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def forecast(self, request, *args, **kwargs):
        # GET CORRECT FORECAST, 6H AND 12H
        region_readings = RegionReadings.objects.filter(region_id=self.get_object().id)
        serializer = StationSerializer(region_readings, many=True)

        if serializer.is_valid():
            return Response(serializer.data)
        else:
            return Response(serializer.errors)


    @action(detail=True, methods=['get'])
    def history(self, request, *args, **kwargs):
        # ADD DATE FILTER
        region_readings = RegionReadings.objects.filter(region_id=self.get_object().id)
        serializer = StationSerializer(region_readings, many=True)

        if serializer.is_valid():
            return Response(serializer.data)
        else:
            return Response(serializer.errors)


class StationViewset(ModelViewSet):
    queryset = Stations.objects.all()
    serializer_class = StationSerializer
    http_method_names = ['get']

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return Response(serializer.data)


    @action(detail=True, methods=['get'])
    def forecast(self, request, *args, **kwargs):
        station = self.get_object()
        
        yesterday = timezone.now() - timedelta(days=1)

        aqi_series = StationReadingsGold.objects.filter(
                station_id=station.id, 
                date_localtime__gte=yesterday
            ) \
            .order_by('-date_localtime') \
            .values('date_localtime', 'aqi_pm2_5')
        
        aqi_series = [{'value': entry['aqi_pm2_5'], 'timestamp': entry['date_localtime'].strftime('%Y-%m-%d %H:%M:%S')} for entry in aqi_series]

        # get the latest inference result by id
        inference_result = InferenceResults.objects.filter(station_id=station.id).order_by('-id').first()
        
        # get the date of the inference run
        inference_date = InferenceRuns.objects.filter(id=inference_result.inference_run_id).first().run_date
        
        forecast_data = {
            'forecast_date': inference_date,
            'aqi': aqi_series,
            'forecast_6h': inference_result.forecast_6h,
            'forecast_12h': inference_result.forecast_12h
        }

        serializer = ForecastSerializer(data=forecast_data)

        if serializer.is_valid():
            return Response(serializer.data)
        
        else:
            return Response(serializer.errors)


    @action(detail=True, methods=['get'])
    def history(self, request, *args, **kwargs):
        station = self.get_object()

        metric = request.query_params.get('metric', 'aqi_pm2_5')
        
        if metric == 'pm2_5':
            field = 'pm2_5'
            avg_field = 'pm2_5_avg'
        
        else:
            field = 'aqi_pm2_5'
            avg_field = 'aqi_pm2_5_avg'

        # Define the time ranges
        one_day_ago = timezone.now() - timedelta(days=1)
        seven_days_ago = timezone.now() - timedelta(days=7)
        thirty_days_ago = timezone.now() - timedelta(days=30)

        # Get the last 30 days
        history_readings = StationReadingsGold.objects.filter(
            station_id=station.id,
            date_localtime__gte=thirty_days_ago
        ).order_by('-date_localtime')

        # Filter: last 24 hours
        historical_1d = history_readings.filter(date_localtime__gte=one_day_ago) \
                                .values('date_localtime', field) \
                                .order_by('date_localtime')

        historical_1d = [{'value': entry[field], 'timestamp': entry['date_localtime'].strftime('%Y-%m-%d %H:%M:%S')} for entry in historical_1d]

        # Filter: last 7 days (group by day and aggregate)
        historical_7d = history_readings.filter(date_localtime__gte=seven_days_ago) \
                                .annotate(day=TruncDate('date_localtime')) \
                                .values('day') \
                                .annotate(avg_value=Avg(field)) \
                                .order_by('day')

        historical_7d = [{'value': entry['avg_value'], 'timestamp': entry['day'].strftime('%Y-%m-%d 00:00:00')} for entry in historical_7d]

        # Filter: last 30 days (group by day and aggregate)
        historical_30d = history_readings \
                    .annotate(day=TruncDate('date_localtime')) \
                    .values('day') \
                    .annotate(avg_value=Avg(field)) \
                    .order_by('day')

        historical_30d = [{'value': entry['avg_value'], 'timestamp': entry['day'].strftime('%Y-%m-%d 00:00:00')} for entry in historical_30d]

        # Prepare the data to return
        history_data = {
            'historical_1d': historical_1d,
            'historical_7d': historical_7d,
            'historical_30d': historical_30d
        }
        
        serializer = HistorySerializer(data=history_data)

        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)

        else:
            return Response(serializer.errors)