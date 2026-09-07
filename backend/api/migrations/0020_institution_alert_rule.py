"""The configurable institutional alert rule.

Django-owned, so the new table is moved into ``django_admin`` after creation
for the same reason as every table in 0019: ``db_table`` stays unqualified and
the fixed search_path resolves it to whichever schema actually holds it. A
table left behind in ``public`` would still be found today (it is last in the
search_path) but breaks the ownership invariant asserted by
``api/tests_schema_ownership.py``.

The move is a no-op on SQLite, which has no schemas at all, and on any
database where the table already sits in ``django_admin``. It has to be: the
role that runs migrations in deployed environments is scoped to that schema
and holds no CREATE privilege on the database, so nothing here may issue DDL
it has not first established is necessary — see api/schema_moves.py.
"""

from django.db import migrations, models
import django.db.models.deletion

from api.schema_moves import is_postgresql, move_tables

TABLE_NAME = "institution_alert_rule"


def _move_to_django_admin(apps, schema_editor):
    if not is_postgresql(schema_editor):
        return
    with schema_editor.connection.cursor() as cursor:
        move_tables(cursor, "django_admin", [TABLE_NAME])


def _reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0019_move_to_owning_schemas"),
    ]

    operations = [
        migrations.CreateModel(
            name="InstitutionAlertRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "threshold",
                    models.PositiveIntegerField(
                        help_text="AQI value above which this rule notifies the station's followers. Any value — an institution may choose to alert its own community at a level the public alerts deliberately stay quiet for."
                    ),
                ),
                (
                    "push_title",
                    models.CharField(
                        help_text="Notification title, as it appears on the device.",
                        max_length=100,
                    ),
                ),
                (
                    "push_body",
                    models.TextField(
                        help_text="Notification body. {station} is replaced with the station's name.",
                        max_length=500,
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Inactive rules are skipped by the scheduled sender.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "institution",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alert_rules",
                        to="api.institution",
                    ),
                ),
                (
                    "station",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="institution_alert_rules",
                        to="api.stations",
                    ),
                ),
            ],
            options={
                "db_table": "institution_alert_rule",
                "ordering": ("institution", "threshold"),
            },
        ),
        migrations.AddConstraint(
            model_name="institutionalertrule",
            constraint=models.UniqueConstraint(
                fields=("institution", "station"),
                name="uniq_alert_rule_per_institution_station",
            ),
        ),
        migrations.RunPython(_move_to_django_admin, _reverse_noop),
    ]
