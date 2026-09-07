"""Helpers shared by the schema-ownership migrations (api 0019, accounts 0003).

These migrations move tables into their owning schema (``django_admin`` for
Django-owned tables, ``respira_gold`` for pipeline-owned ones). On a database
where that move already happened — every deployed environment, where the
schemas were separated by hand before Django Admin work started — they must
emit no DDL at all, because the migration role deliberately has no rights
beyond ``django_admin``:

* it has no ``CREATE`` privilege on the database, so ``CREATE SCHEMA IF NOT
  EXISTS`` fails with ``permission denied for database``. ``IF NOT EXISTS``
  does not save it: PostgreSQL checks the ``CREATE`` privilege *before* it
  checks whether the schema already exists, so the statement raises even when
  the schema has existed for months;
* it does not own the ``respira_gold`` tables (``dbtuser`` does), so
  ``ALTER TABLE ... SET SCHEMA`` against them would fail too.

So every statement here is guarded by a read-only check first: look, and only
then act. If the database is already in the target state, nothing runs.

Schema existence and table location are read from ``pg_catalog`` rather than
``information_schema``. ``information_schema.tables`` only lists tables the
current role holds some privilege on, so a gold table the migration role
cannot touch reads as *missing* there — and "missing" is indistinguishable
from "not yet moved". ``pg_catalog`` shows it regardless of privileges, which
is exactly what lets these migrations skip work they must not attempt.
"""

PG_INTERNAL_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


def is_postgresql(schema_editor):
    # SQLite (local dev, and any run without BACKEND_POSTGRES_* configured)
    # has no notion of schemas: every table already lives in the single
    # namespace search_path would otherwise disambiguate, so there is nothing
    # to move and CREATE SCHEMA is a syntax error.
    return schema_editor.connection.vendor == "postgresql"


def schema_exists(cursor, schema_name):
    cursor.execute(
        "SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = %s",
        [schema_name],
    )
    return cursor.fetchone() is not None


def ensure_schema(cursor, schema_name):
    """Create ``schema_name`` only if it does not already exist.

    The read comes first so an already-provisioned database issues no DDL and
    therefore needs no CREATE privilege. Only ``django_admin`` is ever passed
    here: ``respira_gold`` belongs to the data pipeline (dbt creates and owns
    it), so the webapp must never try to create it.
    """
    if schema_exists(cursor, schema_name):
        return
    cursor.execute(f'CREATE SCHEMA "{schema_name}"')


def table_schemas(cursor, table_name):
    """Every non-internal schema holding a table called ``table_name``."""
    cursor.execute(
        """
        SELECT n.nspname
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = %s
          AND c.relkind IN ('r', 'p')
          AND n.nspname NOT IN %s
        """,
        [table_name, PG_INTERNAL_SCHEMAS],
    )
    return {row[0] for row in cursor.fetchall()}


# The only schemas a table may be moved *out of*. `public` is where an
# upgraded database left its tables; `django_admin` is where a fresh database
# just created them, because 0001_initial creates unqualified tables in the
# first schema on search_path (settings.py pins that to django_admin) — which
# is the wrong home for the gold tables and has to be corrected here.
#
# Anything outside this set is off limits: a table in some other schema was
# put there deliberately, and must not be dragged across on a name match.
MOVABLE_SOURCE_SCHEMAS = ("public", "django_admin")


def move_tables(cursor, target_schema, table_names):
    """Move each table into ``target_schema``, if it is not already there.

    A table moves only when it is absent from ``target_schema`` and present in
    one of ``MOVABLE_SOURCE_SCHEMAS`` (never the target itself). ``public`` is
    preferred as the source when a table sits in more than one, so an upgraded
    database sheds its stale copy first.

    ``target_schema`` is created only at the point the first table actually
    has to move there, and only if it does not already exist. That laziness is
    what keeps this safe for ``respira_gold``: a deployed database already has
    that schema (dbt owns it) and nothing left to move, so no CREATE is ever
    attempted by a role that has no right to issue one. A fresh database has
    neither, and gets the schema built on demand.
    """
    candidate_sources = [s for s in MOVABLE_SOURCE_SCHEMAS if s != target_schema]
    target_ready = False
    for table_name in table_names:
        schemas = table_schemas(cursor, table_name)
        if target_schema in schemas:
            continue
        source_schema = next((s for s in candidate_sources if s in schemas), None)
        if source_schema is None:
            continue
        if not target_ready:
            ensure_schema(cursor, target_schema)
            target_ready = True
        cursor.execute(
            f'ALTER TABLE "{source_schema}"."{table_name}" '
            f'SET SCHEMA "{target_schema}"'
        )
