"""Move api tables into their explicit owning schemas.

Table ownership used to be expressed only through PostgreSQL's search_path
order (``BACKEND_POSTGRES_SCHEMA``): with e.g. ``django_admin,respira_gold``
configured, an unqualified table name resolved to whichever schema
search_path checked first, and a same-named table (or an accidental one) in
the wrong schema could silently redirect reads or writes.

``db_table`` intentionally stays unqualified (Django's own introspection —
used by ``flush``, ``dumpdata``/``loaddata``, and ``TransactionTestCase``
teardown — compares ``db_table`` against unqualified names from
``pg_catalog`` and silently stops matching anything once ``db_table`` carries
a schema prefix, which breaks those commands and every test that flushes
between cases). Instead, settings.DATABASES now fixes search_path to
``django_admin, respira_gold, public`` unconditionally — not configurable,
not reorderable by ``BACKEND_POSTGRES_SCHEMA`` — and this migration makes
that safe by actually moving every table into the schema search_path always
checks for it:

* ``django_admin``: every Django-owned model (auth, admin, accounts, and the
  operational models in api/models.py — institutions, station overrides,
  device followers, sensor alerts, FAQs, ...).
* ``respira_gold``: every model backed by a data-pipeline table — dbt SQL for
  ``regions``/``stations``/``station_readings_gold``/``region_readings_gold``,
  the Prefect inference flow for ``inference_runs``/``inference_results``.
  These are additionally marked ``ReadOnlyGoldModel`` (api/gold.py), which
  blocks writes to them from the backend ORM regardless of search_path.

Because no ``django_admin`` table shares a name with a ``respira_gold``
table (see the regression test in api/tests_schema_ownership.py, which fails
if that ever stops being true), a fixed, non-configurable search_path order
cannot introduce ambiguity: reordering it would still resolve every table to
the same place.

Purely a database-side move — no ``AlterModelTable``, since ``db_table`` is
not changing. RunPython, not RunSQL, so every statement can be guarded by a
read-only check and skipped when the database is already in the target state:

* Fresh test/dev/CI databases: 0001_initial created every table unqualified,
  so they all landed in the first schema on search_path — ``django_admin``.
  This migration creates that schema and then moves the pipeline-owned tables
  out of it into ``respira_gold``, where they belong.
* Production/staging/demo: the schemas were separated by hand before Django
  Admin work started, so every table is already in place and this migration
  issues no DDL whatsoever.

That second case is not an optimization, it is a requirement. The role these
migrations run as is scoped to ``django_admin`` and nothing else: it holds no
``CREATE`` privilege on the database and does not own the ``respira_gold``
tables. So this migration must never issue a statement it does not first
establish is necessary — see api/schema_moves.py, which also explains why
these checks read ``pg_catalog`` rather than ``information_schema``.

``respira_gold`` is never created here. That schema belongs to the data
pipeline: dbt creates it, owns it, and materializes into it. If it is
missing, the fix is to run the pipeline, not to have the webapp conjure a
schema it does not own. Its tables are still listed below so a fresh database
that materialized them into ``public`` gets them filed correctly.

Every operation is a no-op on non-PostgreSQL backends: SQLite (local dev
without ``BACKEND_POSTGRES_*`` set) has no schemas at all, so there is
nothing to separate and ``CREATE SCHEMA`` is a syntax error there.
"""

from django.db import migrations

from api.schema_moves import ensure_schema, is_postgresql, move_tables

DJANGO_ADMIN_TABLES = [
    "action_log",
    "device_follower",
    "device_installation",
    "faq_category",
    "faq_question",
    "institution",
    "institution_alert",
    "institution_alert_config",
    "institution_alert_config_sensitive_groups",
    "institution_contract",
    "institution_user",
    "sensitive_group",
    "sensor_alert",
    "sensor_alert_state",
    "station_details",
    "station_overrides",
    "user_profile",
]

RESPIRA_GOLD_TABLES = [
    "inference_results",
    "inference_runs",
    "region_readings_gold",
    "regions",
    "station_readings_gold",
    "stations",
]


def _ensure_django_admin_schema(apps, schema_editor):
    if not is_postgresql(schema_editor):
        return
    with schema_editor.connection.cursor() as cursor:
        ensure_schema(cursor, "django_admin")


def _move_tables(target_schema, table_names):
    def _move(apps, schema_editor):
        if not is_postgresql(schema_editor):
            return
        with schema_editor.connection.cursor() as cursor:
            move_tables(cursor, target_schema, table_names)

    return _move


def _reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0018_sensor_alert_trend"),
    ]

    operations = [
        migrations.RunPython(_ensure_django_admin_schema, _reverse_noop),
        migrations.RunPython(
            _move_tables("django_admin", DJANGO_ADMIN_TABLES), _reverse_noop
        ),
        migrations.RunPython(
            _move_tables("respira_gold", RESPIRA_GOLD_TABLES), _reverse_noop
        ),
    ]
