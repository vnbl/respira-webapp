"""Move accounts tables into the ``django_admin`` schema.

Table ownership used to be expressed only through PostgreSQL's search_path
order (``BACKEND_POSTGRES_SCHEMA``), which made resolution depend on schema
order rather than an explicit contract. ``db_table`` intentionally stays
unqualified here (Django's own introspection — used by ``flush``,
``dumpdata``/``loaddata``, and ``TransactionTestCase`` teardown — compares
``db_table`` against unqualified names from ``pg_catalog`` and silently stops
matching anything once ``db_table`` carries a schema prefix). Instead,
settings.DATABASES fixes search_path to ``django_admin, respira_gold,
public`` unconditionally — not configurable, not reorderable — and this
migration makes that safe by actually moving every accounts table into
``django_admin``, the schema search_path always checks first.

Purely a database-side move (no ``AlterModelTable``: ``db_table`` is not
changing, so there is nothing for Django's migration state to record).
RunPython, not RunSQL, so every statement can be guarded by a read-only check
first and skipped when the database is already in the target state — safe to
run against a fresh test/dev/CI database (0001_initial just created these
tables, unqualified, wherever search_path pointed at the time) and against a
deployed database where the schemas were already separated by hand, which
issues no DDL at all.

That last case is a requirement, not an optimization: the role these
migrations run as is scoped to ``django_admin`` and holds no ``CREATE``
privilege on the database, so even ``CREATE SCHEMA IF NOT EXISTS`` raises
``permission denied for database`` there. See api/schema_moves.py.
"""

from django.db import migrations

from api.schema_moves import ensure_schema, is_postgresql, move_tables

TABLES = [
    "accounts_role",
    "accounts_user",
    "accounts_user_groups",
    "accounts_user_user_permissions",
]


def _move_tables(apps, schema_editor):
    if not is_postgresql(schema_editor):
        return
    with schema_editor.connection.cursor() as cursor:
        ensure_schema(cursor, "django_admin")
        move_tables(cursor, "django_admin", TABLES)


def _reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_seed_roles"),
    ]

    operations = [
        migrations.RunPython(_move_tables, _reverse_noop),
    ]
