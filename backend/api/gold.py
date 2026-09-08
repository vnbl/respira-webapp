"""Shared base for models backed by tables the backend does not own.

``respira_gold`` tables are produced by the data pipeline (dbt SQL models and
the Prefect inference flow in respira-data) and consumed by the backend as
read-only data. ``ReadOnlyGoldModel`` blocks writes through the ORM itself —
independent of admin permissions or API views, and independent of whether the
table happens to be reachable through some other code path — so a gold table
can never be mutated by the backend regardless of who calls ``save()``.

Migrations still create these tables in dev/test/CI, where no pipeline exists
to create them first (see api/migrations/0001_initial.py and
0019_move_to_owning_schemas.py). Only writes from application code are
blocked; Django's own migration machinery is unaffected.
"""

from django.db import models


class GoldTableWriteError(RuntimeError):
    """Raised when application code attempts to write to a gold table."""


def _blocked(model_name, method_name):
    raise GoldTableWriteError(
        f"{model_name}.objects.{method_name}() targets a respira_gold table "
        "owned by the data pipeline; the backend must not write to it."
    )


class ReadOnlyGoldQuerySet(models.QuerySet):
    """QuerySet whose bulk-write entry points refuse to run.

    ``bulk_create``, ``update`` and ``delete`` issue SQL directly and never go
    through an instance's ``save()``/``delete()``, so they need their own
    guard — ``ReadOnlyGoldModel`` alone would not catch them.
    """

    def bulk_create(self, *args, **kwargs):
        _blocked(self.model.__name__, "bulk_create")

    def bulk_update(self, *args, **kwargs):
        _blocked(self.model.__name__, "bulk_update")

    def update(self, *args, **kwargs):
        _blocked(self.model.__name__, "update")

    def delete(self, *args, **kwargs):
        _blocked(self.model.__name__, "delete")


class ReadOnlyGoldModel(models.Model):
    """Mixin that rejects writes on models backed by ``respira_gold``.

    Read access (querysets, filters, joins) is untouched — only mutation is
    blocked, since the pipeline is the sole writer of these tables. Covers
    both instance-level writes (``save``/``delete``) and queryset-level bulk
    writes (``bulk_create``/``update``/``delete`` via ``objects``).
    """

    objects = ReadOnlyGoldQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        _blocked(type(self).__name__, "save")

    def delete(self, *args, **kwargs):
        _blocked(type(self).__name__, "delete")

    @classmethod
    def seed_for_tests(cls, **kwargs):
        """Insert a row bypassing the write guard, for test fixtures only.

        Production code has no reason to call this — it exists because tests
        build a dev-only copy of these tables (see api/migrations/0001_initial)
        and need to seed rows the pipeline would normally write.
        """
        instance = cls(**kwargs)
        super(ReadOnlyGoldModel, instance).save()
        return instance

    def update_for_tests(self, *args, **kwargs):
        """Save changes to an existing row bypassing the write guard.

        Test-only, like ``seed_for_tests`` — simulates the pipeline updating
        a row it owns (e.g. flipping ``is_station_on`` on the next gold run)
        without going through the backend's own, deliberately blocked, save().
        """
        return super().save(*args, **kwargs)

    def delete_for_tests(self, *args, **kwargs):
        """Delete a row bypassing the write guard, for test fixtures only."""
        return super().delete(*args, **kwargs)
