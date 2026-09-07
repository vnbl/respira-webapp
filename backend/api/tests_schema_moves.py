"""The schema-ownership migrations must issue no DDL on an already-moved database.

Deployed environments had their schemas separated by hand before Django Admin
work started, and the role that runs migrations there is scoped to
``django_admin``: no ``CREATE`` privilege on the database, no ownership of the
``respira_gold`` tables. A migration that issues DDL unconditionally therefore
fails against exactly the databases where it has nothing left to do — which is
what broke the demo deploy: ``CREATE SCHEMA IF NOT EXISTS "django_admin"``
raised ``permission denied for database`` even though the schema, and every
table in it, was already in place (PostgreSQL checks the CREATE privilege
before it checks ``IF NOT EXISTS``).

These tests drive the helpers with a fake cursor that records every statement,
so "emits nothing when the work is already done" is asserted directly rather
than inferred.
"""

import unittest

from django.db import connection
from django.test import SimpleTestCase, TestCase

from .schema_moves import ensure_schema, move_tables, schema_exists, table_schemas


class FakeCursor:
    """Minimal cursor double recording statements and replaying canned reads.

    ``existing`` maps table name -> set of schemas holding it; ``schemas`` is
    the set of existing schema names. Reads are answered from those; anything
    else is recorded as executed DDL.
    """

    def __init__(self, schemas=(), existing=None):
        self.schemas = set(schemas)
        self.existing = existing or {}
        self.executed = []
        self._result = []

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT 1 FROM pg_catalog.pg_namespace"):
            self._result = [(params[0],)] if params[0] in self.schemas else []
            return
        if normalized.startswith("SELECT n.nspname"):
            self._result = [(s,) for s in sorted(self.existing.get(params[0], ()))]
            return
        self.executed.append(normalized)
        self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class EnsureSchemaTests(SimpleTestCase):
    def test_no_ddl_when_schema_already_exists(self):
        # The demo-deploy failure: the schema is there, so nothing may run.
        cursor = FakeCursor(schemas={"django_admin", "respira_gold", "public"})
        ensure_schema(cursor, "django_admin")
        self.assertEqual(cursor.executed, [])

    def test_creates_schema_when_missing(self):
        cursor = FakeCursor(schemas={"public"})
        ensure_schema(cursor, "django_admin")
        self.assertEqual(cursor.executed, ['CREATE SCHEMA "django_admin"'])

    def test_create_is_issued_without_if_not_exists(self):
        # IF NOT EXISTS would not help — PostgreSQL checks the CREATE
        # privilege on the database before checking existence — so the guard
        # has to be the preceding SELECT, and the CREATE must be reached only
        # when the schema genuinely does not exist.
        cursor = FakeCursor(schemas={"public"})
        ensure_schema(cursor, "django_admin")
        self.assertNotIn("IF NOT EXISTS", cursor.executed[0])


class MoveTablesTests(SimpleTestCase):
    def test_no_ddl_when_every_table_is_already_in_target(self):
        cursor = FakeCursor(
            existing={"user_profile": {"django_admin"}, "institution": {"django_admin"}}
        )
        move_tables(cursor, "django_admin", ["user_profile", "institution"])
        self.assertEqual(cursor.executed, [])

    def test_moves_table_sitting_in_public(self):
        cursor = FakeCursor(
            schemas={"public", "django_admin"},
            existing={"user_profile": {"public"}},
        )
        move_tables(cursor, "django_admin", ["user_profile"])
        self.assertEqual(
            cursor.executed,
            ['ALTER TABLE "public"."user_profile" SET SCHEMA "django_admin"'],
        )

    def test_target_schema_is_created_when_a_move_needs_it(self):
        # A fresh database has no respira_gold yet: it is created on demand,
        # immediately before the first table that has to land in it.
        cursor = FakeCursor(schemas={"public"}, existing={"stations": {"public"}})
        move_tables(cursor, "respira_gold", ["stations"])
        self.assertEqual(
            cursor.executed,
            [
                'CREATE SCHEMA "respira_gold"',
                'ALTER TABLE "public"."stations" SET SCHEMA "respira_gold"',
            ],
        )

    def test_target_schema_is_created_at_most_once(self):
        cursor = FakeCursor(
            schemas={"public"},
            existing={"stations": {"public"}, "regions": {"public"}},
        )
        move_tables(cursor, "respira_gold", ["stations", "regions"])
        self.assertEqual(
            cursor.executed.count('CREATE SCHEMA "respira_gold"'), 1
        )

    def test_gold_table_already_in_respira_gold_is_untouched(self):
        # The migration role does not own these tables; attempting the move
        # would fail even though there is nothing to do.
        cursor = FakeCursor(existing={"stations": {"respira_gold"}})
        move_tables(cursor, "respira_gold", ["stations"])
        self.assertEqual(cursor.executed, [])

    def test_table_in_target_and_public_is_untouched(self):
        # A stale copy left behind in public must not drag the real table
        # across schemas (nor collide with it).
        cursor = FakeCursor(existing={"stations": {"respira_gold", "public"}})
        move_tables(cursor, "respira_gold", ["stations"])
        self.assertEqual(cursor.executed, [])

    def test_table_in_an_unrelated_schema_is_left_alone(self):
        # Only public/django_admin are legitimate sources: a table anywhere
        # else was put there deliberately and is not this migration's to move.
        cursor = FakeCursor(existing={"stations": {"some_other_schema"}})
        move_tables(cursor, "respira_gold", ["stations"])
        self.assertEqual(cursor.executed, [])

    def test_gold_table_created_in_django_admin_is_moved_out(self):
        # A fresh database (CI): 0001_initial creates unqualified tables in
        # the first schema on search_path, django_admin, so the gold tables
        # start in the wrong home and this migration is what corrects them.
        cursor = FakeCursor(
            schemas={"django_admin", "respira_gold"},
            existing={"stations": {"django_admin"}},
        )
        move_tables(cursor, "respira_gold", ["stations"])
        self.assertEqual(
            cursor.executed,
            ['ALTER TABLE "django_admin"."stations" SET SCHEMA "respira_gold"'],
        )

    def test_public_is_preferred_when_a_table_sits_in_two_sources(self):
        cursor = FakeCursor(
            schemas={"public", "django_admin", "respira_gold"},
            existing={"stations": {"public", "django_admin"}},
        )
        move_tables(cursor, "respira_gold", ["stations"])
        self.assertEqual(
            cursor.executed,
            ['ALTER TABLE "public"."stations" SET SCHEMA "respira_gold"'],
        )

    def test_django_admin_target_never_moves_a_table_onto_itself(self):
        # django_admin is both a valid source and, here, the target: the
        # table is already home and must not be ALTERed.
        cursor = FakeCursor(existing={"user_profile": {"django_admin"}})
        move_tables(cursor, "django_admin", ["user_profile"])
        self.assertEqual(cursor.executed, [])

    def test_missing_table_is_skipped(self):
        cursor = FakeCursor(existing={})
        move_tables(cursor, "django_admin", ["user_profile"])
        self.assertEqual(cursor.executed, [])


@unittest.skipUnless(
    connection.vendor == "postgresql",
    "pg_catalog introspection is PostgreSQL-only",
)
class CatalogIntrospectionTests(TestCase):
    """The real queries must work against a live database.

    They read pg_catalog rather than information_schema on purpose:
    information_schema.tables only lists tables the current role holds a
    privilege on, so a respira_gold table the migration role cannot touch
    would read as missing there — indistinguishable from "not yet moved".
    """

    def test_schema_exists_agrees_with_the_database(self):
        with connection.cursor() as cursor:
            self.assertTrue(schema_exists(cursor, "django_admin"))
            self.assertFalse(schema_exists(cursor, "schema_that_does_not_exist"))

    def test_table_schemas_locates_a_django_owned_table(self):
        with connection.cursor() as cursor:
            self.assertEqual(table_schemas(cursor, "user_profile"), {"django_admin"})

    def test_table_schemas_locates_a_gold_table(self):
        with connection.cursor() as cursor:
            self.assertEqual(table_schemas(cursor, "stations"), {"respira_gold"})

    def test_table_schemas_is_empty_for_an_unknown_table(self):
        with connection.cursor() as cursor:
            self.assertEqual(table_schemas(cursor, "table_that_does_not_exist"), set())
