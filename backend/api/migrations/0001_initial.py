# Generated by Django 4.2.8 on 2024-10-16 03:25

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='InferenceRuns',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('run_date', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'inference_runs',
            },
        ),
        migrations.CreateModel(
            name='Regions',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
                ('region_code', models.CharField(blank=True, choices=[('ASUNCION', 'ASUNCION')], max_length=255, null=True)),
                ('bbox', models.CharField(blank=True, max_length=255, null=True)),
                ('has_weather_data', models.BooleanField(default=False)),
                ('has_pattern_station', models.BooleanField(default=False)),
            ],
            options={
                'db_table': 'regions',
            },
        ),
        migrations.CreateModel(
            name='Stations',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('latitude', models.FloatField(blank=True, null=True)),
                ('longitude', models.FloatField(blank=True, null=True)),
                ('is_station_on', models.BooleanField(default=False)),
                ('is_pattern_station', models.BooleanField(default=False)),
                ('region', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='api.regions')),
            ],
            options={
                'db_table': 'stations',
            },
        ),
        migrations.CreateModel(
            name='StationReadingsGold',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('airnow_id', models.IntegerField(blank=True, null=True)),
                ('date_utc', models.DateTimeField(blank=True, null=True)),
                ('pm_calibrated', models.BooleanField(blank=True, null=True)),
                ('pm1', models.FloatField(blank=True, null=True)),
                ('pm2_5', models.FloatField(blank=True, null=True)),
                ('pm10', models.FloatField(blank=True, null=True)),
                ('pm2_5_avg_6h', models.FloatField(blank=True, null=True)),
                ('pm2_5_max_6h', models.FloatField(blank=True, null=True)),
                ('pm2_5_skew_6h', models.FloatField(blank=True, null=True)),
                ('pm2_5_std_6h', models.FloatField(blank=True, null=True)),
                ('aqi_pm2_5', models.FloatField(blank=True, null=True)),
                ('aqi_pm10', models.FloatField(blank=True, null=True)),
                ('aqi_level', models.IntegerField(blank=True, null=True)),
                ('aqi_pm2_5_max_24h', models.FloatField(blank=True, null=True)),
                ('aqi_pm2_5_skew_24h', models.FloatField(blank=True, null=True)),
                ('aqi_pm2_5_std_24h', models.FloatField(blank=True, null=True)),
                ('station', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='api.stations')),
            ],
            options={
                'db_table': 'station_readings_gold',
            },
        ),
        migrations.CreateModel(
            name='RegionReadings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_utc', models.DateTimeField()),
                ('pm2_5_region_avg', models.FloatField(blank=True, null=True)),
                ('pm2_5_region_max', models.FloatField(blank=True, null=True)),
                ('pm2_5_region_skew', models.FloatField(blank=True, null=True)),
                ('pm2_5_region_std', models.FloatField(blank=True, null=True)),
                ('aqi_region_avg', models.FloatField(blank=True, null=True)),
                ('aqi_region_max', models.FloatField(blank=True, null=True)),
                ('aqi_region_skew', models.FloatField(blank=True, null=True)),
                ('aqi_region_std', models.FloatField(blank=True, null=True)),
                ('level_region_max', models.FloatField(blank=True, null=True)),
                ('region', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='api.regions')),
            ],
            options={
                'db_table': 'region_readings',
            },
        ),
        migrations.CreateModel(
            name='InferenceResults',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('forecasts_6h', models.JSONField(blank=True, null=True)),
                ('forecasts_12h', models.JSONField(blank=True, null=True)),
                ('aqi_input', models.JSONField(blank=True, null=True)),
                ('inference_run', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='api.inferenceruns')),
                ('station', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='api.stations')),
            ],
            options={
                'db_table': 'inference_results',
            },
        ),
    ]
