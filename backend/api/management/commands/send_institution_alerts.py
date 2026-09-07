"""Evaluates the configurable institutional alert rules and sends the pushes.

A separate command from ``send_sensor_alerts`` because the two answer to
different owners: that one applies a fixed table of AQI levels to every station
on the platform, while this one applies each institution's own threshold and
wording to its own sensor. Keeping them apart means one institution's
misconfigured rule cannot stop the public alerts going out, and either can be
scheduled on its own cadence.

Meant to run on a schedule, shortly after the pipeline publishes new readings.
"""

from django.core.management.base import BaseCommand

from api.push import is_configured, send_institution_alerts


class Command(BaseCommand):
    help = "Notify followers when an institution's configured AQI threshold is crossed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report which rules would fire without sending anything.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when SENSOR_ALERTS_ENABLED is off.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Off by default, like the sensor alerts: a freshly deployed
        # environment must not start notifying real devices before somebody
        # decides it should.
        if not dry_run and not options["force"] and not is_configured():
            self.stdout.write(
                self.style.WARNING(
                    "SENSOR_ALERTS_ENABLED is off; nothing sent. "
                    "Use --dry-run to preview or --force to override."
                )
            )
            return

        result = send_institution_alerts(dry_run=dry_run)

        prefix = "[dry run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}{result.considered} active rule(s) evaluated, "
            f"{result.alerted_stations} fired, "
            f"{result.messages_sent} message(s) accepted, "
            f"{result.tokens_cleared} dead token(s) cleared."
        )

        for error in result.errors:
            self.stdout.write(self.style.ERROR(f"  failed: {error}"))

        if result.errors:
            # A non-zero exit so a scheduler surfaces the failure instead of
            # recording a silently partial run as a success.
            raise SystemExit(1)
