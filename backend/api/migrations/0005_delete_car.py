# Generated by Django 4.2.8 on 2024-03-25 12:42

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_rename_stationvalues_stationreadings_and_more'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Car',
        ),
    ]
