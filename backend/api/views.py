import json
from datetime import timedelta

from django.utils import timezone
from django.db.models import Avg
from django.db.models.functions import TruncDate, TruncHour

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import Stations, StationReadingsGold, InferenceRuns, InferenceResults
from .serializers import StationSerializer, ForecastSerializer, HistorySerializer


class RegionViewset(ModelViewSet):
    queryset = Stations.objects.filter(region_id=1)
    serializer_class = StationSerializer


class StationViewset(ModelViewSet):
    queryset = Stations.objects.all()
    serializer_class = StationSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return Response(serializer.data)


    @action(detail=True, methods=['get'])
    def forecast(self, request, *args, **kwargs):
        station = self.get_object()
        
        aqi = StationReadingsGold.objects.filter(station_id=station.id).order_by('-date_localtime').first().aqi_pm2_5
        
        # get the latest inference result by id
        inference_result = InferenceResults.objects.filter(station_id=station.id).order_by('-id').first()
        
        # get the date of the inference run
        inference_date = InferenceRuns.objects.filter(id=inference_result.inference_run_id).first().run_date
        
        forecast_data = {
            'forecast_date': inference_date,
            'aqi': aqi,
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

        # define time ranges
        one_day_ago = timezone.now() - timedelta(days=1)
        seven_days_ago = timezone.now() - timedelta(days=7)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        # get the last 30 days
        history_readings = StationReadingsGold.objects.filter(
            station_id=station.id,
            date_localtime__gte=thirty_days_ago
        ).order_by('-date_localtime')

        # filter: last 24 hours
        historical_1d = history_readings.filter(date_localtime__gte=one_day_ago) \
                            .values('date_localtime', 'aqi_pm2_5') \
                            .order_by('date_localtime')

        historical_1d = [{'timestamp': entry['day'].strftime('%Y-%m-%d 00:00:00'), 'value': entry['aqi_pm2_5_avg']} for entry in historical_1d]

        # filter: last 7 days (group by day and aggregate)
        historical_7d = history_readings.filter(date_localtime__gte=seven_days_ago) \
                            .annotate(day=TruncDate('date_localtime')) \
                            .values('day') \
                            .annotate(aqi_pm2_5_avg=Avg('aqi_pm2_5')) \
                            .order_by('day')

        historical_7d = [{'timestamp': entry['day'].strftime('%Y-%m-%d 00:00:00'), 'value': entry['aqi_pm2_5_avg']} for entry in historical_7d]

        # filter: last 30 days (group by day and aggregate)
        historical_30d = history_readings \
                .annotate(day=TruncDate('date_localtime')) \
                .values('day') \
                .annotate(aqi_pm2_5_avg=Avg('aqi_pm2_5')) \
                .order_by('day')

        historical_30d = [{'timestamp': entry['day'].strftime('%Y-%m-%d 00:00:00'), 'value': entry['aqi_pm2_5_avg']} for entry in historical_30d]

        history_data = {
            'historical_1d': historical_1d,
            'historical_7d': historical_7d,
            'historical_30d': historical_30d
        }
        
        serializer = HistorySerializer(data=history_data)

        if serializer.is_valid():
            return Response(serializer.data)
        
        else:
            return Response(serializer.errors)