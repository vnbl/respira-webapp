import os
import uuid
from typing import Any

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .gold import ReadOnlyGoldModel


def _column_env_or_default(key: str, default: str) -> str:
    return (os.getenv(key) or "").strip() or default


class UserRole(models.TextChoices):
    VIEWER = "viewer", "Viewer"
    ADMIN = "admin", "Admin"
    SUPERADMIN = "superadmin", "Superadmin"


class UserProfile(models.Model):
    """Platform role attached to a standard Django auth user.

    Kept as a separate additive model (rather than swapping AUTH_USER_MODEL) so
    the feature deploys onto an already-migrated database without rewriting the
    existing auth history.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=20, choices=UserRole.choices, default=UserRole.VIEWER
    )

    class Meta:
        db_table = "user_profile"

    def __str__(self):
        return f"{self.user} ({self.role})"


def user_role(user) -> str:
    """Return the effective platform role of an auth user.

    Falls back to ``superadmin`` for Django superusers without a profile (so the
    bootstrap superuser can manage the platform) and ``viewer`` otherwise.
    """
    profile = getattr(user, "profile", None)
    if profile is not None:
        return profile.role
    if getattr(user, "is_superuser", False):
        return UserRole.SUPERADMIN
    return UserRole.VIEWER


class Regions(ReadOnlyGoldModel):
    name = models.CharField(max_length=255)
    region_code = models.CharField(max_length=255)
    bbox = models.CharField(max_length=255, blank=True, null=True)
    has_weather_data = models.BooleanField(default=False)
    has_pattern_station = models.BooleanField(
        db_column="has_pattern_data", default=False
    )

    class Meta:
        db_table = "regions"

    def __str__(self):
        return self.name


class Stations(ReadOnlyGoldModel):
    name = models.CharField(max_length=255)
    # The pipeline's stable natural key (``dim_stations.code``), exposed on the
    # gold table so operational records can address a station by something that
    # survives a rebuild — ``id`` comes from a ``row_number()`` in dbt and shifts
    # whenever a station is added. Written by dbt, never by the backend.
    station_code = models.CharField(max_length=255, blank=True, default="")
    region = models.ForeignKey(
        "Regions", on_delete=models.DO_NOTHING, blank=True, null=True
    )
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    is_station_on = models.BooleanField(default=False)
    is_pattern_station = models.BooleanField(default=False)

    class Meta:
        db_table = "stations"

    def __str__(self):
        return self.name

    @property
    def coordinates(self):
        return (self.latitude, self.longitude)


class StationDetails(models.Model):
    """Operational and contact information for a station, owned by the backend.

    Kept out of ``stations`` — which the dbt gold pipeline rewrites on every run
    — so operators can edit it from the admin without the next run overwriting
    it. Replaces the operational Google Spreadsheet.

    ``db_constraint=False``: dbt materializes ``stations`` as a table and drops
    and recreates it on every run, so a physical FOREIGN KEY would either break
    that run or be dropped with CASCADE. The one-to-one relationship (and its
    unique index) is enforced at the Django level instead.

    Note that ``stations.id`` is itself derived from a ``row_number()`` in dbt
    (``int_station_id_map``), so ids shift when a station is added. Re-linking
    details after such a shift requires exposing the stable ``station_code`` on
    the gold ``stations`` model — tracked separately in respira-data.
    """

    station = models.OneToOneField(
        "Stations",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="details",
    )
    serial_number = models.CharField(max_length=255, blank=True)
    sensor_type = models.CharField(max_length=255, blank=True)
    model = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    specific_location = models.CharField(max_length=255, blank=True)
    locality = models.CharField(max_length=255, blank=True)
    environment_type = models.CharField(max_length=255, blank=True)
    connectivity = models.CharField(max_length=255, blank=True)
    power_source = models.CharField(max_length=255, blank=True)
    installation_date = models.DateField(blank=True, null=True)
    responsible = models.CharField(max_length=255, blank=True)
    contact_info = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "station_details"
        verbose_name = "station details"
        verbose_name_plural = "station details"

    def __str__(self):
        return f"Details for {self.station.name}"


class Institution(models.Model):
    """A client organization in the Sensor Leasing program.

    Admin-owned, like ``StationDetails``: created and edited from the Django
    Admin, independent of the dbt-managed ``stations``/``regions`` tables.
    """

    legal_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    institution_type = models.CharField(max_length=100, blank=True)
    contact_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "institution"

    def __str__(self):
        return self.display_name or self.legal_name


class InstitutionContract(models.Model):
    """The leasing contract binding an :class:`Institution` to a station.

    ``institution`` is OneToOne so an institution has at most one contract.
    ``station`` mirrors :class:`StationDetails`: a plain ``OneToOneField`` with
    ``db_constraint=False``, since dbt drops and recreates ``stations`` on
    every gold run and a physical FOREIGN KEY would not survive that. The
    relationship (and its unique index) is enforced at the Django level, which
    is what guarantees a station is bound to at most one contract.
    """

    class ContractStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    institution = models.OneToOneField(
        "Institution", on_delete=models.CASCADE, related_name="contract"
    )
    station = models.OneToOneField(
        "Stations",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="institution_contract",
    )
    contract_status = models.CharField(
        max_length=20,
        choices=ContractStatus.choices,
        default=ContractStatus.DRAFT,
    )
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    monthly_fee = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    signed_contract_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "institution_contract"

    def __str__(self):
        return f"{self.institution} — {self.station.name}"


class InstitutionUser(models.Model):
    """Grants a platform user access to a single Institution's private dashboard.

    Additive, mirroring ``UserProfile``: kept separate from ``accounts.User``
    instead of adding a field there, so this feature deploys without a
    migration on the core auth model. ``user`` is OneToOne — a user reaches at
    most one institution's data — while ``institution`` is a plain FK, since an
    institution may have more than one contact with dashboard access.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="institution_user",
    )
    institution = models.ForeignKey(
        "Institution", on_delete=models.CASCADE, related_name="users"
    )

    class Meta:
        db_table = "institution_user"

    def __str__(self):
        return f"{self.user} → {self.institution}"


def get_institution_for_user(user) -> "Institution | None":
    """Resolve the single Institution an authenticated user may access.

    Centralized so every institutional endpoint (and its tests) checks access
    the same way, rather than each view querying ``InstitutionUser`` directly.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    link = getattr(user, "institution_user", None)
    return link.institution if link else None


def get_institution_station_ids(institution) -> set[int]:
    """Station ids an institution is entitled to act on.

    Today that is the single station bound by its :class:`InstitutionContract`
    — an institution leases at most one sensor. Centralized here (like
    :func:`get_institution_for_user`) so every institutional endpoint resolves
    "which stations are mine" identically, and so widening the rule later
    (several contracts per institution) is a one-place change.
    """
    if institution is None:
        return set()
    contract = getattr(institution, "contract", None)
    return {contract.station_id} if contract is not None else set()


class SensitiveGroup(models.Model):
    """Catalog of at-risk population groups an institution can flag for alerts.

    Mirrors the fixed list respira-mobile ships in ``aqiLevels.ts``
    (``SENSITIVE_GROUPS_ALL``), kept as a table rather than a
    ``TextChoices`` so it is manageable from the admin instead of a code
    deploy, and can back a proper many-to-many selection per institution.
    """

    key = models.SlugField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    emoji = models.CharField(max_length=8, blank=True)

    class Meta:
        db_table = "sensitive_group"
        ordering = ("label",)

    def __str__(self):
        return self.label


class InstitutionAlertConfig(models.Model):
    """An institution's own configuration for institutional air-quality alerts.

    OneToOne, like ``InstitutionContract``: an institution has at most one
    alert configuration. Absent entirely for institutions that never opted
    into alerts — callers resolve that case to a controlled default instead
    of treating it as an error.
    """

    institution = models.OneToOneField(
        "Institution", on_delete=models.CASCADE, related_name="alert_config"
    )
    is_enabled = models.BooleanField(default=False)
    alert_threshold = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="AQI value above which an alert is triggered.",
    )
    sensitive_groups: "models.ManyToManyField[SensitiveGroup, Any]" = (
        models.ManyToManyField(
            "SensitiveGroup", blank=True, related_name="alert_configs"
        )
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "institution_alert_config"

    def __str__(self):
        return f"Alert config for {self.institution}"


class InstitutionAlert(models.Model):
    """A poor-air-quality event recorded for an institution's station.

    Records that an institution's AQI threshold was actually crossed, so an
    :class:`ActionLog` entry can point at the event it responded to. The
    threshold itself is per-institution configuration, tracked separately.

    Nothing writes these automatically yet — alerts are computed client-side in
    respira-mobile and never stored — so rows are created from the admin until
    an alert generator exists. Adding one is purely additive: it neither reads
    nor changes the existing notification path.

    ``station`` mirrors :class:`InstitutionContract`: ``db_constraint=False``
    because dbt drops and recreates ``stations`` on every gold run, so a
    physical FOREIGN KEY would not survive it.
    """

    institution = models.ForeignKey(
        "Institution", on_delete=models.CASCADE, related_name="alerts"
    )
    station = models.ForeignKey(
        "Stations",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="institution_alerts",
    )
    aqi_value = models.FloatField(
        help_text="AQI reading that triggered the alert.",
    )
    alert_threshold = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text=(
            "Threshold in force when the alert fired, copied from the "
            "institution's alert configuration so later edits to that "
            "configuration don't rewrite history."
        ),
    )
    rule = models.ForeignKey(
        "InstitutionAlertRule",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="events",
        help_text=(
            "The rule that fired this event, when one did. Null for events "
            "predating the rules, and kept null-able so deleting a rule "
            "preserves the history it produced."
        ),
    )
    triggered_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Left empty while the event is still ongoing.",
    )

    class Meta:
        db_table = "institution_alert"
        ordering = ("-triggered_at", "-id")

    def __str__(self):
        return f"{self.institution} — AQI {self.aqi_value} at {self.triggered_at:%Y-%m-%d %H:%M}"


class InstitutionAlertRule(models.Model):
    """An institution's configurable push alert for one of its stations.

    What makes institutional alerts *configurable* rather than compiled in: the
    threshold and the wording live here, editable from the admin, instead of in
    ``push.LEVEL_COPY``'s fixed table of AQI levels. Editing a rule changes what
    followers receive on the next scheduled run, with no deploy involved.

    Why a numeric threshold and not a level. The public alert path deliberately
    only fires from ``unhealthySensitive`` upward — waking people for good air
    trains them to ignore the alerts that matter. An institution leasing its own
    sensor has a different audience: a school may well want to tell its
    community at an AQI the general public should not be interrupted for. A
    number expresses that; a level cannot.

    Separate from :class:`InstitutionAlertConfig` rather than an extension of
    it. That model is one row per institution holding institution-wide
    preferences (``sensitive_groups``), is a ``OneToOneField``, and is already
    read by the institutional dashboard through
    ``InstitutionAlertConfigSerializer``. Widening it to one row per station
    would change what a single row means and break that serializer's
    assumption, for a gain this model provides on its own.

    ``station`` mirrors :class:`InstitutionContract`: ``db_constraint=False``
    because dbt drops and recreates ``stations`` on every gold run, so a
    physical FOREIGN KEY would not survive it.
    """

    institution = models.ForeignKey(
        "Institution", on_delete=models.CASCADE, related_name="alert_rules"
    )
    station = models.ForeignKey(
        "Stations",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="institution_alert_rules",
    )
    threshold = models.PositiveIntegerField(
        help_text=(
            "AQI value above which this rule notifies the station's followers. "
            "Any value — an institution may choose to alert its own community "
            "at a level the public alerts deliberately stay quiet for."
        ),
    )
    push_title = models.CharField(
        max_length=100,
        help_text="Notification title, as it appears on the device.",
    )
    push_body = models.TextField(
        max_length=500,
        help_text="Notification body. {station} is replaced with the station's name.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive rules are skipped by the scheduled sender.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "institution_alert_rule"
        ordering = ("institution", "threshold")
        # "Institution alert" in the admin, because this is the one page an
        # operator uses for the feature. The events it produces
        # (:class:`InstitutionAlert`) are shown inline on this page rather than
        # as a section of their own — two menu entries whose names differ by the
        # word "rule" is a distinction nobody should have to learn.
        verbose_name = "institution alert"
        verbose_name_plural = "institution alerts"
        constraints = [
            # Several alerts per sensor on purpose: an institution that wants a
            # caution at one AQI and an evacuation at a higher one has said so
            # twice, deliberately, and both are meant to arrive. Escalating
            # advice is how air-quality guidance is normally written, and
            # collapsing it to one message per sensor would lose the middle
            # step.
            #
            # Only an exact duplicate is refused, since two alerts at the same
            # threshold could never say anything the other did not — they would
            # fire together, every time, and send the same follower two
            # notifications about one reading.
            models.UniqueConstraint(
                fields=["institution", "station", "threshold"],
                name="uniq_alert_rule_per_threshold",
            )
        ]

    def __str__(self):
        return f"{self.institution} — AQI > {self.threshold}"

    def message_for(self, station_name: str) -> tuple[str, str]:
        """This rule's copy, with ``{station}`` resolved.

        ``format_map`` over ``format`` so an operator who types a stray brace
        into the body gets their literal text through rather than a
        ``KeyError`` at send time, when there is no admin around to see it.
        """

        class _Defaults(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        return (
            self.push_title,
            self.push_body.format_map(_Defaults(station=station_name)),
        )


class InstitutionAlertRuleState(models.Model):
    """Whether one rule is currently holding an alert open, run to run.

    A numeric threshold needs its own memory and cannot borrow
    :class:`SensorAlertState`: that model records AQI *level* keys, so with a
    threshold of 40 a station oscillating 38→42→39→41 sits at ``good``
    throughout and no level ever changes. Every crossing would be invisible to
    it.

    ``is_firing`` is the crossing itself. It turns on when a reading first
    exceeds ``threshold`` and turns off only once the air falls back under
    ``push.rearm_threshold`` — a band below it. Without that band a sensor
    hovering at its threshold re-alerts on every scheduled run, which is the
    duplicate-notification failure the level path avoids by requiring a
    *worsening*, expressed here in the terms a bare number allows.

    One row per rule, taken with ``select_for_update`` for the length of a
    send, which is also what stops two overlapping runs from both notifying.
    """

    rule = models.OneToOneField(
        "InstitutionAlertRule", on_delete=models.CASCADE, related_name="state"
    )
    is_firing = models.BooleanField(
        default=False,
        help_text=(
            "True while followers have been warned and the air has not yet "
            "fallen back below the rearm band."
        ),
    )
    last_aqi = models.FloatField(
        blank=True,
        null=True,
        help_text="The most recent reading this rule was evaluated against.",
    )
    last_notified_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "institution_alert_rule_state"

    def __str__(self):
        return f"{self.rule_id}: {'firing' if self.is_firing else 'idle'}"

    @classmethod
    def lock(cls, rule_id: int) -> "InstitutionAlertRuleState":
        """The rule's state row, locked until the caller's transaction ends.

        Created first and locked second, for the same reason as
        :meth:`SensorAlertState.lock`: there is no row to lock on a rule's very
        first run.
        """
        cls.objects.get_or_create(rule_id=rule_id)
        return cls.objects.select_for_update().get(rule_id=rule_id)


class PushBroadcast(models.Model):
    """One manually sent push, and the record that it was sent.

    Separate from :class:`InstitutionAlertRule` because the two are different
    kinds of thing. A rule is standing configuration the scheduled sender
    evaluates over and over; a broadcast is written once, sent once, and never
    fires again. Modelling both as rows of one table would leave half the
    columns meaningless in either case, and "active" meaning two different
    things.

    This is what carries an operational message — "no hay clases mañana",
    "mantenimiento del sensor el martes" — that has nothing to do with the
    current AQI, which is why it has no threshold and no state.

    A row exists only once a send has been attempted: there is no draft to
    submit twice, and ``sent_at`` is stamped on creation. That is what stops
    the same announcement going out repeatedly.

    ``scope`` is the audience. ``ALL`` reaches every follower of every station
    and is not an institutional alert at all — it is a platform announcement,
    which is why this model has no required institution and why the admin gates
    that scope behind a permission of its own.
    """

    SCOPE_STATION = "station"
    SCOPE_INSTITUTION = "institution"
    SCOPE_ALL = "all"
    SCOPE_CHOICES = (
        (SCOPE_STATION, "One station's followers"),
        (SCOPE_INSTITUTION, "All of an institution's stations"),
        (SCOPE_ALL, "Every follower on the platform"),
    )

    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES)
    institution = models.ForeignKey(
        "Institution",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="broadcasts",
        help_text="Set for institution-scoped sends; blank for a platform-wide one.",
    )
    station = models.ForeignKey(
        "Stations",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        blank=True,
        null=True,
        related_name="broadcasts",
        help_text="Set for station-scoped sends.",
    )
    push_title = models.CharField(max_length=100)
    push_body = models.TextField(max_length=500)
    recipients = models.PositiveIntegerField(
        default=0,
        help_text="How many devices the push service accepted this broadcast for.",
    )
    failures = models.PositiveIntegerField(
        default=0,
        help_text="Messages the push service rejected for a reason worth retrying.",
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="push_broadcasts",
        help_text="Who sent it. Kept for the audit trail.",
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "push_broadcast"
        ordering = ("-sent_at",)
        permissions = [
            (
                "send_global_pushbroadcast",
                "Can send a push notification to every follower on the platform",
            )
        ]

    def __str__(self):
        return f"{self.get_scope_display()} — {self.push_title}"


class ActionLog(models.Model):
    """An action an institution took in response to an air quality event.

    The institutional audit trail: what was decided or done, when, on which
    station, and — when applicable — which alert prompted it. Written through
    the institutional API (never by the pipeline), which is why ``timestamp``
    is ``auto_now_add``: the backend stamps it, and no client can backdate an
    entry.

    Deletion behaviour follows what each relationship means for the record:

    * ``institution`` cascades — the history belongs to the institution and has
      no meaning once the institution is gone (same as ``InstitutionContract``
      and ``InstitutionUser``).
    * ``station`` is ``DO_NOTHING`` with ``db_constraint=False``, like every
      other backend-owned model pointing at the dbt-managed ``stations``.
    * ``alert`` is ``SET_NULL`` — the alert is context, not the record's
      subject. Removing an alert must not erase the fact that the institution
      acted, so the entry survives as an action without a linked alert.
    """

    institution = models.ForeignKey(
        "Institution", on_delete=models.CASCADE, related_name="action_logs"
    )
    station = models.ForeignKey(
        "Stations",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="action_logs",
    )
    alert = models.ForeignKey(
        "InstitutionAlert",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="action_logs",
        help_text="Optional: the alert this action responded to.",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(help_text="The action taken by the institution.")

    class Meta:
        db_table = "action_log"
        # Most recent action first, as the institutional history is read.
        # ``-id`` breaks ties so two entries written in the same instant (a
        # realistic case for a stamped-by-the-server timestamp) still come back
        # in a stable, newest-first order.
        ordering = ("-timestamp", "-id")

    def __str__(self):
        return f"{self.institution} — {self.timestamp:%Y-%m-%d %H:%M}"


class StationOverride(models.Model):
    """An operational override of a station field, editable from the admin.

    Replaces ``station_status_seed.csv`` in respira-data: instead of committing
    a CSV and running dbt for every operational change, an operator creates a
    row here and the pipeline consumes it.

    Stations are addressed by ``station_code`` — the pipeline's stable natural
    key — rather than by ``stations.id``, which dbt regenerates from a
    ``row_number()`` on every run.

    ``processed`` is set by the pipeline once it has picked the change up, so it
    is system-managed and read-only in the admin.

    ``field``/``value`` are deliberately free-form so any station column can be
    overridden. The activate/deactivate workflow is one such override, pinned to
    ``STATUS_FIELD`` with a :class:`Status` value — hence the constants rather
    than ``choices`` on the field itself.
    """

    # The station column the activate/deactivate workflow overrides.
    STATUS_FIELD = "is_station_on"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    station_code = models.CharField(max_length=255, db_index=True)
    field = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    note = models.TextField(blank=True)
    change_date = models.DateTimeField(default=timezone.now)
    processed = models.BooleanField(default=False)

    class Meta:
        db_table = "station_overrides"
        ordering = ("-change_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["station_code", "field"],
                name="uniq_station_override_code_field",
            )
        ]

    def __str__(self):
        return f"{self.station_code}: {self.field} = {self.value}"


# One retry is enough for the token claim: the conflict can only be lost to a
# transaction that has since committed, so the second attempt sees its row and
# clears it. The third is there so a pathological pile-up raises rather than
# loops.
_TOKEN_CLAIM_ATTEMPTS = 3


class DeviceInstallation(models.Model):
    """One installation of the mobile app, without any login.

    Split out from :class:`DeviceFollower` when a device became able to follow
    several stations. The push token belongs to the *installation*, not to any
    one follow: while the rule was one station per device the two were the same
    row, but with N follows the token would otherwise be stored N times and
    every write would have to keep the copies in step — and a notification
    fan-out would deliver N times to the same phone.

    ``installation_id`` is a UUIDv4 the app generates on first launch and
    stores locally (Keystore on Android, Keychain on iOS). It is deliberately
    *not* derived from a hardware or OS identifier: a derived value would be
    predictable, would be correlatable with the same device across other apps,
    and — since it is a pure function of the device — would collide
    deterministically whenever an installation is cloned or restored from a
    backup. 122 random bits from a CSPRNG make an accidental collision
    negligible (~10⁻²⁵ across a million installations) and, more importantly,
    make the identifier unguessable, which is what stands in for authentication
    on these endpoints. See
    docs/device-follower-identifier-investigation.md.
    """

    installation_id = models.UUIDField(
        unique=True,
        editable=False,
        help_text="UUIDv4 generated by the app on first launch.",
    )
    push_token = models.TextField(
        blank=True,
        default="",
        help_text="Current FCM/APNs token; blank until the app registers one.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "device_installation"
        ordering = ("-updated_at",)
        constraints = [
            # The invariant behind `register()`: a live token identifies exactly
            # one installation. Enforced by the database rather than by the
            # clearing query alone, because two registrations of the same
            # previously-unclaimed token can each clear nothing and then both
            # write it — application code cannot see a row the other
            # transaction has not committed yet. Blank is exempt: "no token" is
            # the normal state of any number of installations.
            models.UniqueConstraint(
                fields=["push_token"],
                condition=~models.Q(push_token=""),
                name="uniq_active_push_token",
            )
        ]

    def __str__(self):
        return str(self.installation_id)

    @classmethod
    def register(cls, installation_id, *, push_token=None):
        """Get or create the installation, optionally refreshing its token.

        Claiming the push token — clearing it from any other installation that
        holds it — matters because a reinstall produces a new
        ``installation_id`` while the OS may hand the app the same token.
        Without this, the abandoned installation keeps the token and the device
        receives a second copy of every notification, for stations it no longer
        follows.

        The claim races with itself: two installations registering the same
        token concurrently both find nothing to clear. ``uniq_active_push_token``
        turns that into an :class:`IntegrityError` on whichever commits second,
        and the retry then sees the winner's row and clears it — so the loser of
        the race ends up the sole holder instead of both keeping the token.
        """
        for attempt in range(_TOKEN_CLAIM_ATTEMPTS):
            try:
                # A savepoint when there is an outer transaction, which is what
                # lets the caller keep using it after the retry below.
                with transaction.atomic():
                    installation, created = cls.objects.get_or_create(
                        installation_id=installation_id
                    )
                    if push_token is not None:
                        if push_token:
                            cls.objects.filter(push_token=push_token).exclude(
                                pk=installation.pk
                            ).update(push_token="", updated_at=timezone.now())
                        installation.push_token = push_token
                        installation.save(update_fields=["push_token", "updated_at"])
                    return installation, created
            except IntegrityError:
                if attempt == _TOKEN_CLAIM_ATTEMPTS - 1:
                    raise


class DeviceFollower(models.Model):
    """One station a mobile installation follows.

    A device may follow several, so uniqueness is on the *pair*: re-following a
    station it already follows updates nothing rather than creating a second
    row, which is what makes the follow endpoint safe to retry on a flaky
    mobile network. The cap on how many a single installation may hold is a
    view concern (`MAX_FOLLOWS_PER_INSTALLATION`) rather than a constraint,
    since it is about bounding abuse of an unauthenticated endpoint and is
    expected to be tuned.

    Stations are addressed by ``station_code``, not by ``stations.id``, for the
    same reason as :class:`StationOverride`: dbt derives that id from a
    ``row_number()`` and regenerates it on every run, so a stored id would
    silently come to mean a different station. The API still speaks in station
    ids — the code is resolved on write and back to the current id on read — so
    respira-mobile is unaffected.
    """

    installation = models.ForeignKey(
        DeviceInstallation,
        on_delete=models.CASCADE,
        related_name="follows",
        help_text="The installation that follows this station.",
    )
    station_code = models.CharField(
        max_length=255,
        db_index=True,
        help_text="The pipeline's stable natural key for the followed station.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "device_follower"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["installation", "station_code"],
                name="uniq_follow_per_installation",
            )
        ]

    def __str__(self):
        return f"{self.installation.installation_id} → {self.station_code}"

    @property
    def station(self) -> "Stations | None":
        """The station currently carrying ``station_code``, if it still exists.

        Resolved per call rather than stored, since the id it returns is only
        valid until the next dbt run renumbers ``stations``.
        """
        if not self.station_code:
            return None
        return Stations.objects.filter(station_code=self.station_code).first()


class SensorAlert(models.Model):
    """A per-sensor push alert that reached at least one of that sensor's followers.

    The audit trail, and only that: Sensor Leasing is a paid, institutional
    programme, so "this sensor was alerted on, at this level, at this time, and
    the push service accepted it for this many devices" has to be answerable
    from our own data rather than from a push provider's dashboard. It is a
    count, not a roster — reconstructing *which* devices were warned would need
    a row per recipient, which is a deliberate non-goal here: it would build a
    lasting per-device record of an endpoint that has no login and is
    identified only by an installation UUID.

    Deciding whether to alert is a separate question with separate state, in
    :class:`SensorAlertState`. Keeping the two apart is what lets a failed
    delivery be retried without the audit log claiming an alert that never
    landed, and what lets a station recover and alert again later.

    History is kept rather than one row per station: the latest is just the
    first by ``sent_at``, and the older rows are the audit trail.

    Addressed by ``station_code`` for the same reason as
    :class:`DeviceFollower` — dbt regenerates ``stations.id`` on every run.
    """

    # Which way the air moved. Without it a row reading "level: good" is
    # indistinguishable from a warning about good air, which is not a thing —
    # the audit has to say whether followers were warned or stood down.
    #
    # `catch_up` is neither: it goes to one installation that has just followed
    # a station already sitting in an alert level, telling it how the air is
    # right now. Distinct from the other two because it is not about a change,
    # and because its audience is one device rather than every follower.
    TREND_WORSENING = "worsening"
    TREND_IMPROVING = "improving"
    TREND_CATCH_UP = "catch_up"
    TREND_CHOICES = (
        (TREND_WORSENING, "Worsening"),
        (TREND_IMPROVING, "Improving"),
        (TREND_CATCH_UP, "Catch-up on follow"),
    )

    station_code = models.CharField(
        max_length=255,
        db_index=True,
        help_text="The pipeline's stable natural key for the station alerted about.",
    )
    level = models.CharField(
        max_length=32,
        help_text="AQI level key at the time of the alert, e.g. 'unhealthy'.",
    )
    trend = models.CharField(
        max_length=16,
        choices=TREND_CHOICES,
        default=TREND_WORSENING,
        help_text=(
            "Why followers were notified: the air got worse, it improved, or "
            "one installation was caught up on a station it just followed. "
            "Defaults to worsening: every row predating this field was a "
            "warning."
        ),
    )
    aqi = models.FloatField(help_text="The reading that triggered the alert.")
    recipients = models.PositiveIntegerField(
        default=0,
        help_text="How many devices the push service accepted the alert for.",
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sensor_alert"
        ordering = ("-sent_at",)

    def __str__(self):
        arrow = "↑" if self.trend == self.TREND_WORSENING else "↓"
        return f"{self.station_code} {arrow} {self.level} ({self.recipients} devices)"

    @classmethod
    def record(
        cls,
        station_code: str,
        level: str,
        aqi: float,
        recipients: int,
        trend: str = TREND_WORSENING,
    ):
        return cls.objects.create(
            station_code=station_code,
            level=level,
            trend=trend,
            aqi=aqi,
            recipients=recipients,
        )


class SensorAlertState(models.Model):
    """What one station's alerting knows about that station, run to run.

    Split from :class:`SensorAlert` because the audit log is a poor memory for
    two reasons:

    Recovery. An audit log only ever holds levels that were alerted on, so a
    station that alerted at ``hazardous``, cleared to ``good`` and worsened
    again to ``unhealthy`` still shows ``hazardous`` as its last entry — and
    since nothing outranks ``hazardous``, that station could never alert again.
    ``last_level`` records every reading's level, safe ones included, which is
    what makes the recovery visible and reopens alerting.

    Delivery. ``last_alerted_level`` only moves when an alert actually reached
    somebody, so a push that Expo rejected is retried on the next run instead
    of being suppressed by an audit row for a warning nobody received.

    One row per station, taken with ``select_for_update`` for the length of a
    send, which is also what stops two overlapping scheduled runs from both
    deciding to alert the same station.
    """

    station_code = models.CharField(
        max_length=255,
        unique=True,
        help_text="The pipeline's stable natural key for the station.",
    )
    last_level = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="AQI level key of the most recent reading, alert-worthy or not.",
    )
    last_alerted_level = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "Level of the last alert that reached a device; blank once the "
            "station drops back below the alert threshold."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sensor_alert_state"
        ordering = ("station_code",)

    def __str__(self):
        return f"{self.station_code}: {self.last_level or '—'}"

    @classmethod
    def lock(cls, station_code: str) -> "SensorAlertState":
        """The station's state row, locked until the caller's transaction ends.

        Created first and locked second because there is no row to lock on a
        station's first run. ``get_or_create`` is safe against a concurrent run
        creating it too — the unique constraint makes one of them lose and
        re-read — and the lock is what serialises everything after it.
        """
        cls.objects.get_or_create(station_code=station_code)
        return cls.objects.select_for_update().get(station_code=station_code)


class RegionReadings(ReadOnlyGoldModel):
    region = models.ForeignKey("Regions", on_delete=models.DO_NOTHING)
    date_utc = models.DateTimeField()
    pm2_5_region_avg = models.FloatField(blank=True, null=True)
    pm2_5_region_max = models.FloatField(blank=True, null=True)
    pm2_5_region_skew = models.FloatField(blank=True, null=True)
    pm2_5_region_std = models.FloatField(blank=True, null=True)
    aqi_region_avg = models.FloatField(blank=True, null=True)
    aqi_region_max = models.FloatField(blank=True, null=True)
    aqi_region_skew = models.FloatField(blank=True, null=True)
    aqi_region_std = models.FloatField(blank=True, null=True)
    level_region_max = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "region_readings_gold"


class StationReadingsGold(ReadOnlyGoldModel):
    station = models.ForeignKey("Stations", on_delete=models.DO_NOTHING)
    airnow_id = models.IntegerField(blank=True, null=True)
    date_utc = models.DateTimeField(
        blank=True,
        null=True,
        db_column=_column_env_or_default(
            "BACKEND_STATION_READINGS_DATE_COLUMN", "date_localtime"
        ),
    )
    pm_calibrated = models.BooleanField(blank=True, null=True)
    pm1 = models.FloatField(blank=True, null=True)
    pm2_5 = models.FloatField(blank=True, null=True)
    pm10 = models.FloatField(blank=True, null=True)
    pm2_5_avg_6h = models.FloatField(blank=True, null=True)
    pm2_5_max_6h = models.FloatField(blank=True, null=True)
    pm2_5_skew_6h = models.FloatField(blank=True, null=True)
    pm2_5_std_6h = models.FloatField(blank=True, null=True)
    aqi_pm2_5 = models.FloatField(blank=True, null=True)
    aqi_pm10 = models.FloatField(blank=True, null=True)
    aqi_level = models.IntegerField(blank=True, null=True)
    aqi_pm2_5_max_24h = models.FloatField(blank=True, null=True)
    aqi_pm2_5_skew_24h = models.FloatField(blank=True, null=True)
    aqi_pm2_5_std_24h = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "station_readings_gold"


class InferenceRuns(ReadOnlyGoldModel):
    class Status(models.TextChoices):
        RUNNING = "running", "running"
        SUCCESS = "success", "success"
        FAILED = "failed", "failed"
        CANCELLED = "cancelled", "cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_date = models.DateTimeField(
        db_column="as_of",
    )
    flow_run_id = models.TextField()
    deployment = models.TextField(blank=True, null=True)
    window_hours = models.IntegerField()
    min_points = models.IntegerField()
    model_6h_version = models.TextField()
    model_12h_version = models.TextField()
    model_6h_path = models.TextField(blank=True, null=True)
    model_12h_path = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(blank=True, null=True)
    duration_s = models.IntegerField(blank=True, null=True)
    status = models.TextField(choices=Status.choices)
    stations_total = models.IntegerField(default=0)
    stations_success = models.IntegerField(default=0)
    stations_skipped = models.IntegerField(default=0)
    stations_failed = models.IntegerField(default=0)
    error_summary = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "inference_runs"


class InferenceResults(ReadOnlyGoldModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Written by the same Prefect/Python inference pipeline as InferenceRuns
    # (not dbt SQL), so it is gold data too — see ReadOnlyGoldModel. The FKs
    # below intentionally omit db_constraint=False: unlike stations/regions,
    # inference_runs/inference_results are append-only and never dropped and
    # recreated wholesale by the pipeline, so a physical FK is safe here.
    inference_run = models.ForeignKey("InferenceRuns", on_delete=models.DO_NOTHING)
    station = models.ForeignKey("Stations", on_delete=models.DO_NOTHING)
    forecasts_6h = models.JSONField(
        blank=True,
        null=True,
        db_column=_column_env_or_default(
            "BACKEND_INFERENCE_RESULTS_6H_COLUMN", "forecast_6h"
        ),
    )
    forecasts_12h = models.JSONField(
        blank=True,
        null=True,
        db_column=_column_env_or_default(
            "BACKEND_INFERENCE_RESULTS_12H_COLUMN", "forecast_12h"
        ),
    )
    aqi_input = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = "inference_results"


# --- FAQ (public /recursos page) -------------------------------------------
#
# Admin-owned content: unlike stations/regions (written by the dbt pipeline and
# exposed through ReadOnlyModelAdmin), these rows are created and edited from the
# Django Admin, so they use RoleBasedModelAdmin.
#
# Translations are stored as one column per language rather than a separate
# translations table. The site ships a closed set of three languages, fixed by
# the frontend's language selector, so six columns keep the admin form a single
# screen where a language can be neither duplicated nor silently omitted.

# Must stay in sync with the frontend's `i18n/config.ts`.
FAQ_LANGS = ("es", "en", "pt")
FAQ_DEFAULT_LANG = "es"


def faq_localized(instance, field: str, lang: str) -> str:
    """Return ``<field>_<lang>``, falling back to Spanish when untranslated.

    Mirrors the frontend's ``useTranslations`` fallback: a question nobody has
    translated yet renders in Spanish instead of as an empty accordion row.
    """
    if lang not in FAQ_LANGS:
        lang = FAQ_DEFAULT_LANG
    value = (getattr(instance, f"{field}_{lang}", "") or "").strip()
    if value:
        return value
    return (getattr(instance, f"{field}_{FAQ_DEFAULT_LANG}", "") or "").strip()


def faq_localized_map(instance, field: str) -> dict[str, str]:
    """Return ``{lang: text}`` for every supported language, fallback applied."""
    return {lang: faq_localized(instance, field, lang) for lang in FAQ_LANGS}


def faq_missing_langs(instance, field: str) -> list[str]:
    """Languages where ``<field>_<lang>`` is blank (i.e. still untranslated)."""
    return [
        lang
        for lang in FAQ_LANGS
        if lang != FAQ_DEFAULT_LANG
        and not (getattr(instance, f"{field}_{lang}", "") or "").strip()
    ]


class FaqCategory(models.Model):
    """A group of FAQ questions, rendered as one section on /recursos."""

    slug = models.SlugField(
        max_length=64,
        unique=True,
        help_text=(
            "Anchor used in the public URL (e.g. #sensor). Changing it breaks "
            "links people have already shared."
        ),
    )
    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Sections are shown from lowest to highest.",
    )
    is_published = models.BooleanField(
        default=True,
        help_text="Unpublished categories are hidden from the public page.",
    )

    label_es = models.CharField(max_length=120)
    label_en = models.CharField(max_length=120, blank=True)
    label_pt = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "faq_category"
        ordering = ["order", "id"]
        verbose_name = "FAQ category"
        verbose_name_plural = "FAQ categories"

    def __str__(self):
        return self.label_es


class FaqQuestion(models.Model):
    """A single question/answer pair inside a :class:`FaqCategory`.

    Answers are plain text: the page renders them with ``white-space: pre-line``,
    so a newline is a line break and a leading "• " makes a bullet. No markup is
    interpreted, which keeps admin-authored content safe to render as-is.
    """

    category = models.ForeignKey(
        FaqCategory, on_delete=models.CASCADE, related_name="questions"
    )
    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Questions are shown from lowest to highest within a category.",
    )
    is_published = models.BooleanField(
        default=True,
        help_text="Unpublished questions are hidden from the public page.",
    )

    question_es = models.CharField(max_length=300)
    answer_es = models.TextField()
    question_en = models.CharField(max_length=300, blank=True)
    answer_en = models.TextField(blank=True)
    question_pt = models.CharField(max_length=300, blank=True)
    answer_pt = models.TextField(blank=True)

    class Meta:
        db_table = "faq_question"
        ordering = ["category__order", "order", "id"]
        verbose_name = "FAQ question"
        verbose_name_plural = "FAQ questions"

    def __str__(self):
        return self.question_es
