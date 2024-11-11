from datetime import datetime, timedelta

from django.utils import timezone
from django.db.models import Avg, Min, Max, OuterRef, Subquery
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import generics

from rest_framework.viewsets import ModelViewSet
from statistics import median, quantiles
from collections import defaultdict

import pandas as pd

from .models import Stations, Regions, RegionReadings, StationReadingsGold, InferenceRuns, InferenceResults
from .serializers import StationSerializer, RegionSerializer, MapSerializer, ForecastSerializer, HistorySerializer

class HealthCheckView(generics.GenericAPIView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class MapViewset(generics.GenericAPIView):
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

        latest_inference_run_id = InferenceRuns.objects.order_by('-run_date').first().id
            
        # get region_readings, average forecast for regions beloging to region
        if entity == 'region':
            latest_region_reading = RegionReadings.objects.filter(region_id=entity_id) \
                            .order_by('-date_utc').first()

            if latest_region_reading:
                latest_aqi = latest_region_reading.aqi_region_avg
            else:
                return Response({
                    "error": "No readings found for this region."
                }, status=status.HTTP_404_NOT_FOUND)

            # 6h forecast
            forecast_6h = InferenceResults.objects.filter(inference_run=latest_inference_run_id) \
                            .values_list('forecasts_6h', flat=True)
            forecast_6h_data = [item for sublist in forecast_6h for item in sublist]
            
            result_forecast_6h = pd.DataFrame(forecast_6h_data) \
                                    .groupby('timestamp', as_index=False)['value'].mean()
            
            # 12h forecast
            forecast_12h = InferenceResults.objects.filter(inference_run=latest_inference_run_id) \
                            .values_list('forecasts_12h', flat=True)
            forecast_12h_data = [item for sublist in forecast_12h for item in sublist]

            result_forecast_12h = pd.DataFrame(forecast_12h_data) \
                                    .groupby('timestamp', as_index=False)['value'].mean()

        # get station_readings
        elif entity == 'station':

            try:
                station = Stations.objects.get(id=entity_id)
            except Stations.DoesNotExist:
                return Response({
                    'error': 'Station ID does not exist in the database.'
                }, status=status.HTTP_404_NOT_FOUND)
            
            if station.is_pattern_station:
                return Response({
                    'error':'Station ID is a pattern station.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not station.is_station_on:
                return Response({
                    'error':'Station ID has been manually shut down due to maintenance.'
                }, status=status.HTTP_400_BAD_REQUEST)

            latest_station_reading = StationReadingsGold.objects.filter(station_id=entity_id) \
                                        .order_by('-date_utc').first()

            if latest_station_reading:
                latest_aqi = latest_station_reading.aqi_pm2_5
            else:
                return Response({
                    "error": "No readings found for this station."
                }, status=status.HTTP_404_NOT_FOUND)

            # 6h forecast
            forecast_6h = InferenceResults.objects.filter(inference_run=latest_inference_run_id, station_id=entity_id) \
                            .values_list('forecasts_6h', flat=True)
            forecast_6h_data = [item for sublist in forecast_6h for item in sublist]

            if not forecast_6h_data:
                return Response({
                    "error": "No forecast data available for this station."
                }, status=status.HTTP_404_NOT_FOUND)
            
            result_forecast_6h = pd.DataFrame(forecast_6h_data)

            # 12h forecast
            forecast_12h = InferenceResults.objects.filter(inference_run=latest_inference_run_id, station_id=entity_id) \
                            .values_list('forecasts_12h', flat=True)
            forecast_12h_data = [item for sublist in forecast_12h for item in sublist]

            if not forecast_12h_data:
                return Response({
                    "error": "No 12-hour forecast data available for this station."
                }, status=status.HTTP_404_NOT_FOUND)

            result_forecast_12h = pd.DataFrame(forecast_12h_data)

        return Response({
            "aqi": latest_aqi,
            "forecast_6h": result_forecast_6h.to_dict(orient='records'),
            "forecast_12h": result_forecast_12h.to_dict(orient='records')
        }, status=status.HTTP_200_OK)


class RegionViewset(ModelViewSet):
    queryset = Regions.objects.all()
    serializer_class = RegionSerializer
    http_method_names = ['get']


class StationViewset(ModelViewSet):
    queryset = Stations.objects.all()
    serializer_class = StationSerializer
    http_method_names = ['get']

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def forecast(self, request, *args, **kwargs):
        station = self.get_object()
        
        last_inference = InferenceResults.objects.filter(station=station.id).order_by('-inference_run_id').first()
        inference_run = InferenceRuns.objects.filter(id=last_inference.inference_run_id).first()

        return Response({
            "forecast_date": inference_run.run_date,
            "aqi_level": pd.DataFrame(last_inference.aqi_input).to_dict(orient='records'),
            "forecast_6h": pd.DataFrame(last_inference.forecasts_6h).to_dict(orient='records'),
            "forecast_12h": pd.DataFrame(last_inference.forecasts_12h).to_dict(orient='records')
        }, status=status.HTTP_200_OK)

    # @action(detail=True, methods=['get'])
    # def history(self, request, *args, **kwargs):
    #     station = self.get_object()

    #     metric = request.query_params.get('metric', 'aqi_pm2_5')
        
    #     if metric == 'pm2_5':
    #         field = 'pm2_5'
    #         avg_field = 'pm2_5_avg'
        
    #     else:
    #         field = 'aqi_pm2_5'
    #         avg_field = 'aqi_pm2_5_avg'

    #     # Define the time ranges
    #     one_day_ago = timezone.now() - timedelta(days=1)
    #     seven_days_ago = timezone.now() - timedelta(days=7)
    #     thirty_days_ago = timezone.now() - timedelta(days=30)

    #     # Get the last 30 days
    #     history_readings = StationReadingsGold.objects.filter(
    #         station_id=station.id,
    #         date_utc__gte=thirty_days_ago
    #     ).order_by('-date_utc')

    #     # Filter: last 24 hours
    #     historical_1d = history_readings.filter(date_utc__gte=one_day_ago) \
    #                             .values('date_utc', field) \
    #                             .order_by('date_utc')

    #     historical_1d = [{'value': entry[field], 'timestamp': entry['date_utc'].strftime('%Y-%m-%d %H:%M:%S')} for entry in historical_1d]

    #     # Filter: last 7 days (group by day and aggregate)
    #     historical_7d = history_readings.filter(date_utc__gte=seven_days_ago) \
    #                             .annotate(day=TruncDate('date_utc')) \
    #                             .values('day') \
    #                             .annotate(avg_value=Avg(field)) \
    #                             .order_by('day')

    #     historical_7d = [{'value': entry['avg_value'], 'timestamp': entry['day'].strftime('%Y-%m-%d 00:00:00')} for entry in historical_7d]

    #     # Filter: last 30 days (group by day and aggregate)
    #     historical_30d = history_readings \
    #                 .annotate(day=TruncDate('date_utc')) \
    #                 .values('day') \
    #                 .annotate(avg_value=Avg(field)) \
    #                 .order_by('day')

    #     historical_30d = [{'value': entry['avg_value'], 'timestamp': entry['day'].strftime('%Y-%m-%d 00:00:00')} for entry in historical_30d]

    #     # Prepare the data to return
    #     history_data = {
    #         'historical_1d': historical_1d,
    #         'historical_7d': historical_7d,
    #         'historical_30d': historical_30d
    #     }
        
    #     serializer = HistorySerializer(data=history_data)

    #     if serializer.is_valid():
    #         return Response(serializer.data, status=status.HTTP_200_OK)

    #     else:
    #         return Response(serializer.errors, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

    @action(detail=True, methods=['get'])
    def boxplot(self, request, *args, **kwargs):
        station = self.get_object()
        period = request.query_params.get('period', '7d')

        now = timezone.now()
        if period == '7d':
            start_date = now - timedelta(days=7)
            trunc_func = TruncDate
        elif period == '30d':
            start_date = now - timedelta(days=30)
            trunc_func = TruncWeek
        elif period == '1y':
            start_date = now - timedelta(days=365)
            trunc_func = TruncMonth
        else:
            return Response({"error": "Invalid period. Use '7d', '30d' or '1y'."}, status=status.HTTP_400_BAD_REQUEST)

        readings = (
            StationReadingsGold.objects.filter(station_id=station.id, date_utc__gte=start_date)
            .annotate(period=trunc_func('date_utc'))
            .values('period', 'aqi_pm2_5')
        )

        period_values = defaultdict(list)
        for reading in readings:
            period_values[reading['period']].append(reading['aqi_pm2_5'])

        box_data = {
            "x": [],
            "q1": [],
            "median": [],
            "q3": [],
            "lowerfence": [],
            "upperfence": []
        }

        # boxplot calculation - improved
        for period, values in period_values.items():
            values.sort()  
            q1, median_val, q3 = quantiles(values, n=4)[0], median(values), quantiles(values, n=4)[2]
            iqr = q3 - q1
            lowerfence = max(min(values), q1 - 1.5 * iqr)
            upperfence = min(max(values), q3 + 1.5 * iqr)

            box_data["x"].append(period.strftime('%Y-%m-%d'))
            box_data["q1"].append(q1)
            box_data["median"].append(median_val)
            box_data["q3"].append(q3)
            box_data["lowerfence"].append(lowerfence)
            box_data["upperfence"].append(upperfence)

        return Response(box_data, status=status.HTTP_200_OK)
