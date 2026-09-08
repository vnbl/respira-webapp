"""Regression tests for the django_admin / respira_gold schema contract.

Table ownership is a fixed, non-configurable search_path (see
backend/settings.py) plus ReadOnlyGoldModel (api/gold.py) rather than an
operator-configurable schema order. These tests exist so that contract can
never quietly regress:

* no table name is ever shared between the two schemas — the one thing that
  would let search_path order matter again;
* every gold model actually lives in respira_gold and rejects writes from
  the backend, regardless of search_path order;
* `manage.py migrate` never emits a schema-changing operation against a
  respira_gold table.
"""

import unittest

from django.apps import apps
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase

from .gold import GoldTableWriteError, ReadOnlyGoldModel
from .models import (
    InferenceResults,
    InferenceRuns,
    RegionReadings,
    Regions,
    StationReadingsGold,
    Stations,
)

GOLD_MODELS = [
    Regions,
    Stations,
    StationReadingsGold,
    RegionReadings,
    InferenceRuns,
    InferenceResults,
]


def _owned_tables_by_schema():
    """(django_admin tables, respira_gold tables), from every installed model.

    Ownership here is *not* read from search_path — it is derived the same
    way settings.py's migrations move tables: gold models are the ones
    mixing in ReadOnlyGoldModel, everything else managed by this project's
    apps is django_admin.
    """
    django_admin_tables = set()
    respira_gold_tables = set()
    for app_config in apps.get_app_configs():
        if app_config.name not in {"api", "accounts"}:
            continue
        for model in app_config.get_models():
            if issubclass(model, ReadOnlyGoldModel):
                respira_gold_tables.add(model._meta.db_table)
            else:
                django_admin_tables.add(model._meta.db_table)
    return django_admin_tables, respira_gold_tables


# Everything that inspects *where* a table physically lives is PostgreSQL-only:
# SQLite has no schemas, so 0019/0003 move nothing there and there is no
# ownership to assert. CI runs these for real by pointing BACKEND_POSTGRES_* at
# a Postgres service (see .github/workflows/backend-test.yml); a local SQLite
# run skips them rather than failing.
requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "schema ownership is a PostgreSQL-only contract (SQLite has no schemas)",
)


class SchemaOwnershipContractTests(TestCase):
    def test_no_table_name_is_shared_between_the_two_schemas(self):
        # This is what makes a fixed search_path order safe: if this ever
        # fails, django_admin/respira_gold order would start mattering again
        # exactly like BACKEND_POSTGRES_SCHEMA used to.
        django_admin_tables, respira_gold_tables = _owned_tables_by_schema()
        self.assertFalse(django_admin_tables & respira_gold_tables)
        # Sanity: both sets are non-empty, so the assertion above is actually
        # exercising real table lists rather than passing vacuously.
        self.assertTrue(django_admin_tables)
        self.assertTrue(respira_gold_tables)

    def test_gold_models_are_marked_read_only(self):
        for model in GOLD_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, ReadOnlyGoldModel))

    @requires_postgres
    def test_gold_tables_actually_live_in_respira_gold(self):
        with connection.cursor() as cursor:
            for model in GOLD_MODELS:
                cursor.execute(
                    """
                    SELECT table_schema FROM information_schema.tables
                    WHERE table_name = %s
                      AND table_schema NOT IN ('pg_catalog', 'information_schema')
                    """,
                    [model._meta.db_table],
                )
                schemas = {row[0] for row in cursor.fetchall()}
                with self.subTest(model=model.__name__):
                    self.assertEqual(schemas, {"respira_gold"})

    @requires_postgres
    def test_django_owned_tables_actually_live_in_django_admin(self):
        django_admin_tables, _ = _owned_tables_by_schema()
        with connection.cursor() as cursor:
            for table_name in django_admin_tables:
                cursor.execute(
                    """
                    SELECT table_schema FROM information_schema.tables
                    WHERE table_name = %s
                      AND table_schema NOT IN ('pg_catalog', 'information_schema')
                    """,
                    [table_name],
                )
                schemas = {row[0] for row in cursor.fetchall()}
                with self.subTest(table=table_name):
                    self.assertEqual(schemas, {"django_admin"})

    def test_gold_model_save_is_rejected(self):
        region = Regions.seed_for_tests(name="Test region", region_code="TR")
        with self.assertRaises(GoldTableWriteError):
            region.save()

    def test_gold_model_delete_is_rejected(self):
        region = Regions.seed_for_tests(name="Test region", region_code="TR")
        with self.assertRaises(GoldTableWriteError):
            region.delete()

    def test_gold_model_create_is_rejected(self):
        with self.assertRaises(GoldTableWriteError):
            Regions.objects.create(name="Test region", region_code="TR")

    def test_gold_model_bulk_create_is_rejected(self):
        with self.assertRaises(GoldTableWriteError):
            Regions.objects.bulk_create([Regions(name="Test region", region_code="TR")])

    def test_gold_model_queryset_update_is_rejected(self):
        Regions.seed_for_tests(name="Test region", region_code="TR")
        with self.assertRaises(GoldTableWriteError):
            Regions.objects.all().update(name="Tampered")

    def test_gold_model_queryset_delete_is_rejected(self):
        Regions.seed_for_tests(name="Test region", region_code="TR")
        with self.assertRaises(GoldTableWriteError):
            Regions.objects.all().delete()

    def test_gold_model_reads_are_unaffected(self):
        region = Regions.seed_for_tests(name="Test region", region_code="TR")
        self.assertEqual(Regions.objects.get(pk=region.pk).name, "Test region")


@requires_postgres
class SearchPathOrderIndependenceTests(TestCase):
    """A query must resolve to the same table regardless of search_path order.

    BACKEND_POSTGRES_SCHEMA no longer controls resolution order — settings.py
    fixes search_path unconditionally. These tests exercise the connection
    with each order directly (independent of settings) to prove the *tables
    themselves* are unambiguous — not merely that the current process
    happens to be configured one particular way — addressing the DoD's "both
    schema orders" requirement.
    """

    def _resolved_schema(self, table_name, search_path_sql):
        # SET LOCAL is scoped to the current transaction; TestCase already
        # wraps each test in one, so nest a savepoint rather than issuing a
        # raw BEGIN/ROLLBACK that would conflict with it.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL search_path = {search_path_sql}")
                cursor.execute(
                    """
                    SELECT n.nspname
                    FROM pg_class c
                    JOIN pg_namespace n ON c.relnamespace = n.oid
                    WHERE c.relname = %s
                      AND pg_catalog.pg_table_is_visible(c.oid)
                    """,
                    [table_name],
                )
                row = cursor.fetchone()
                return row[0] if row else None

    def test_stations_resolves_to_respira_gold_with_django_admin_first(self):
        schema = self._resolved_schema(
            "stations", '"django_admin", "respira_gold", "public"'
        )
        self.assertEqual(schema, "respira_gold")

    def test_stations_resolves_to_respira_gold_with_respira_gold_first(self):
        schema = self._resolved_schema(
            "stations", '"respira_gold", "django_admin", "public"'
        )
        self.assertEqual(schema, "respira_gold")

    def test_user_profile_resolves_to_django_admin_regardless_of_order(self):
        for search_path_sql in (
            '"django_admin", "respira_gold", "public"',
            '"respira_gold", "django_admin", "public"',
        ):
            with self.subTest(search_path=search_path_sql):
                schema = self._resolved_schema("user_profile", search_path_sql)
                self.assertEqual(schema, "django_admin")


@requires_postgres
class MigrateNeverTouchesGoldSchemaTests(TransactionTestCase):
    """`manage.py migrate` must never create/alter/drop respira_gold objects.

    Runs migrate against the already-migrated test database (a no-op — "no
    migrations to apply") while snapshotting every respira_gold object
    before and after, so any accidental schema-changing operation against a
    gold table — the exact failure mode BACKEND_POSTGRES_SCHEMA ambiguity
    used to allow — would show up as a diff here.
    """

    def _respira_gold_objects(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'respira_gold'
                ORDER BY table_name, column_name
                """
            )
            return list(cursor.fetchall())

    def test_migrate_is_a_noop_against_respira_gold(self):
        from django.core.management import call_command

        before = self._respira_gold_objects()
        self.assertTrue(before, "expected respira_gold to already have columns")

        call_command("migrate", verbosity=0, interactive=False)

        after = self._respira_gold_objects()
        self.assertEqual(before, after)
