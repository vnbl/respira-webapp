from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.db.models import Count, OuterRef, Subquery
from django.http import JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from accounts.admin_base import ReadOnlyModelAdmin, RoleBasedModelAdmin

from . import push
from .forms import (
    InstitutionAlertRuleForm,
    PushBroadcastForm,
    StationStatusOverrideForm,
)
from .models import (
    ActionLog,
    DeviceFollower,
    DeviceInstallation,
    FaqCategory,
    FaqQuestion,
    Institution,
    InstitutionAlert,
    InstitutionAlertConfig,
    InstitutionAlertRule,
    InstitutionAlertRuleState,
    InstitutionContract,
    InstitutionUser,
    PushBroadcast,
    Regions,
    SensitiveGroup,
    SensorAlert,
    StationDetails,
    StationOverride,
    Stations,
    faq_missing_langs,
)

# Shown after every activation/deactivation: the override row is written
# immediately, but `stations.is_station_on` is only rewritten by the pipeline.
DBT_RUN_NOTICE = "Changes to station status require a dbt run to take effect."

# What each action actually does downstream. `stations.is_station_on` is derived
# by the pipeline as "the source reports the station active AND it has reported
# recently"; an override only forces the first half to false. So deactivating
# holds a station off, while activating merely stops holding it off — it cannot
# bring back a station that has gone silent.
STATUS_EXPLANATION = {
    "inactive": (
        "The station will be held inactive: the pipeline excludes it from the "
        "public map regardless of the data it reports."
    ),
    "active": (
        "The forced shutdown is lifted. The station returns only if its source "
        "still reports it as active and it has been sending data recently — "
        "activating it here does not bring back a sensor that stopped reporting."
    ),
}


@admin.register(Regions)
class RegionsViewer(ReadOnlyModelAdmin):
    list_display = ("name", "region_code", "has_weather_data", "has_pattern_station")
    search_fields = ("name", "region_code")
    ordering = ("name",)


class StationDetailsInline(admin.StackedInline):
    """Operational details edited from the station page.

    ``StationDetails`` has no changelist of its own — a details record only
    makes sense next to its station, so the station page is the single place
    operators manage it (replacing the operational spreadsheet).
    """

    model = StationDetails
    can_delete = False
    # One blank form when a station has no details yet, so the operator lands
    # straight on the fields instead of having to click "Add another".
    extra = 1
    verbose_name_plural = "Station details"
    fieldsets = (
        ("Hardware", {"fields": ("serial_number", "sensor_type", "model")}),
        (
            "Location",
            {"fields": ("city", "locality", "specific_location", "environment_type")},
        ),
        (
            "Installation",
            {"fields": ("connectivity", "power_source", "installation_date")},
        ),
        ("Contact", {"fields": ("responsible", "contact_info")}),
        ("Notes", {"fields": ("notes",)}),
    )


@admin.register(Stations)
class StationsViewer(RoleBasedModelAdmin):
    """Station page: the station itself is immutable, its details are not.

    ``stations`` is written by the dbt gold pipeline, so every one of its own
    fields is in ``readonly_fields`` and add/delete are disabled for everyone —
    a record can never be edited into a state the next pipeline run overwrites.

    It cannot extend ``ReadOnlyModelAdmin`` like ``RegionsViewer`` does, though:
    Django refuses to save inlines when the parent denies change permission, and
    the DoD requires editing StationDetails from this page. Change permission is
    therefore granted on the details model instead — "you may open this station
    to edit its details" — never on the station fields themselves.
    """

    list_display = ("name", "region", "is_station_on", "is_pattern_station")
    list_filter = ("is_station_on", "is_pattern_station", "region")
    search_fields = ("name", "station_code")
    ordering = ("name",)
    readonly_fields = (
        "name",
        "station_code",
        "region",
        "latitude",
        "longitude",
        "is_station_on",
        "is_pattern_station",
    )
    fieldsets = (
        (None, {"fields": ("name", "region")}),
        ("Pipeline", {"fields": ("station_code",)}),
        ("Coordinates", {"fields": ("latitude", "longitude")}),
        ("Status", {"fields": ("is_station_on", "is_pattern_station")}),
    )
    inlines = (StationDetailsInline,)
    actions = ("activate_stations", "deactivate_stations")
    status_override_template = "admin/api/stations/status_override_confirmation.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        # Opens the station page for editing its inline details only; the
        # station's own fields stay read-only regardless.
        return request.user.has_perm("api.change_stationdetails")

    def save_model(self, request, obj, form, change):
        # Every station field is readonly, so this page never has a
        # legitimate change to `obj` itself — only its StationDetails inline
        # does, saved separately by `save_formset`. Skip the parent save
        # instead of calling it: `Stations` is a `ReadOnlyGoldModel` and
        # `obj.save()` unconditionally rejects writes to a dbt-owned table,
        # even one that changes nothing (see api/gold.py).
        pass

    def has_override_permission(self, request):
        """Gate for the activate/deactivate actions (``permissions=["override"]``).

        The actions write ``StationOverride`` rows and never touch ``stations``,
        so they are keyed on that model's permissions — not on this one's, which
        grants no write access to anybody.
        """
        return request.user.has_perm(
            "api.add_stationoverride"
        ) and request.user.has_perm("api.change_stationoverride")

    @admin.action(description="Activate selected stations", permissions=["override"])
    def activate_stations(self, request, queryset):
        return self._override_status(request, queryset, StationOverride.Status.ACTIVE)

    @admin.action(description="Deactivate selected stations", permissions=["override"])
    def deactivate_stations(self, request, queryset):
        return self._override_status(request, queryset, StationOverride.Status.INACTIVE)

    def _override_status(self, request, queryset, value):
        """Confirm, then record the requested status as a ``StationOverride``.

        Two passes through the same action, the way Django's own
        ``delete_selected`` works: the first renders a confirmation page asking
        for the mandatory reason, the second (carrying ``confirm``) writes the
        overrides and returns ``None`` so the admin redirects back to the list.

        ``stations`` is never written here — the pipeline propagates the change
        on its next run, which is what ``DBT_RUN_NOTICE`` tells the operator.
        """
        stations = list(queryset.order_by("name"))

        unmapped = [station for station in stations if not station.station_code]
        if unmapped:
            # An override is keyed by station code, so a station without one
            # cannot be addressed at all. Refuse the whole selection rather than
            # applying it to part of it, so the operator sees one consistent
            # outcome instead of a silent partial change.
            self.message_user(
                request,
                "No station code on: "
                + ", ".join(str(station) for station in unmapped)
                + ". The pipeline sets it; wait for the next dbt run.",
                messages.ERROR,
            )
            return None

        confirmed = bool(request.POST.get("confirm"))
        form = (
            StationStatusOverrideForm(request.POST)
            if confirmed
            else StationStatusOverrideForm()
        )
        if confirmed and form.is_valid():
            self._write_status_overrides(stations, value, form.cleaned_data["note"])
            self.message_user(
                request,
                f"{len(stations)} station override(s) recorded as "
                f"{value.label.lower()}.",
                messages.SUCCESS,
            )
            self.message_user(request, DBT_RUN_NOTICE, messages.INFO)
            return None

        context = {
            **self.admin_site.each_context(request),
            "title": f"{value.label} stations",
            "opts": self.opts,
            "media": self.media + form.media,
            "selection": stations,
            "form": form,
            "action": (
                "activate_stations"
                if value == StationOverride.Status.ACTIVE
                else "deactivate_stations"
            ),
            "action_label": value.label.lower(),
            "action_explanation": STATUS_EXPLANATION[value],
            "dbt_run_notice": DBT_RUN_NOTICE,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        }
        return TemplateResponse(request, self.status_override_template, context)

    @staticmethod
    def _write_status_overrides(stations, value, note):
        change_date = timezone.now()
        for station in stations:
            StationOverride.objects.update_or_create(
                station_code=station.station_code,
                field=StationOverride.STATUS_FIELD,
                defaults={
                    "value": value,
                    "note": note,
                    "change_date": change_date,
                    # Re-deciding a status means the pipeline has to pick the row
                    # up again, even if it had already consumed the previous one.
                    "processed": False,
                },
            )


class UntranslatedListFilter(admin.SimpleListFilter):
    """Filters rows still missing a translation in a given language.

    Spanish is the source language and always required, so it is not offered as
    an option. Subclasses set ``fields`` to the untranslated column prefixes.
    """

    title = "pending translation"
    parameter_name = "untranslated"
    fields: tuple[str, ...] = ()

    def lookups(self, request, model_admin):
        return (("en", "Missing English"), ("pt", "Missing Portuguese"))

    def queryset(self, request, queryset):
        lang = self.value()
        if lang not in ("en", "pt"):
            return queryset
        for field in self.fields:
            queryset = queryset.filter(**{f"{field}_{lang}": ""})
        return queryset


class CategoryUntranslatedFilter(UntranslatedListFilter):
    fields = ("label",)


class QuestionUntranslatedFilter(UntranslatedListFilter):
    fields = ("question",)


@admin.register(FaqCategory)
class FaqCategoryAdmin(RoleBasedModelAdmin):
    """Sections of the public FAQ page.

    Admin-owned content (see docs/django-admin-conventions.md): unlike the
    reflected dbt tables, these rows are created and edited here, so this
    extends RoleBasedModelAdmin rather than ReadOnlyModelAdmin.
    """

    list_display = ("label_es", "slug", "order", "is_published", "question_count")
    list_filter = ("is_published", CategoryUntranslatedFilter)
    search_fields = ("slug", "label_es", "label_en", "label_pt")
    ordering = ("order", "id")
    list_editable = ("order", "is_published")
    fieldsets = (
        (None, {"fields": ("slug", "order", "is_published")}),
        (
            "Español",
            {
                "fields": ("label_es",),
                "description": (
                    "Source language: always required. The other languages fall "
                    "back to this text until they are filled in."
                ),
            },
        ),
        ("English", {"fields": ("label_en",)}),
        ("Português", {"fields": ("label_pt",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_questions=Count("questions"))

    @admin.display(description="Questions", ordering="_questions")
    def question_count(self, obj):
        return obj._questions


@admin.register(FaqQuestion)
class FaqQuestionAdmin(RoleBasedModelAdmin):
    """Question/answer pairs shown on the public FAQ page.

    Answers are plain text: a newline is a line break and a leading "• " renders
    as a bullet. No markup is interpreted.
    """

    list_display = (
        "question_es",
        "category",
        "order",
        "is_published",
        "pending_translations",
    )
    list_filter = ("is_published", "category", QuestionUntranslatedFilter)
    search_fields = (
        "question_es",
        "question_en",
        "question_pt",
        "answer_es",
        "answer_en",
        "answer_pt",
    )
    ordering = ("category__order", "order", "id")
    list_select_related = ("category",)
    list_editable = ("order", "is_published")
    autocomplete_fields = ("category",)
    fieldsets = (
        (None, {"fields": ("category", "order", "is_published")}),
        (
            "Español",
            {
                "fields": ("question_es", "answer_es"),
                "description": (
                    "Source language: always required. The other languages fall "
                    "back to this text until they are filled in."
                ),
            },
        ),
        ("English", {"fields": ("question_en", "answer_en")}),
        ("Português", {"fields": ("question_pt", "answer_pt")}),
    )

    @admin.display(description="Pending translation")
    def pending_translations(self, obj):
        missing = set(faq_missing_langs(obj, "question"))
        missing |= set(faq_missing_langs(obj, "answer"))
        if not missing:
            return "—"
        return ", ".join(lang.upper() for lang in sorted(missing))


class InstitutionUserInline(admin.TabularInline):
    """Users granted access to this institution's private dashboard.

    Lives on the Institution page rather than as its own changelist — an
    institution-user link only makes sense in the context of its institution,
    same reasoning as ``StationDetailsInline`` on the station page.
    """

    model = InstitutionUser
    extra = 1
    autocomplete_fields = ("user",)
    verbose_name = "Dashboard user"
    verbose_name_plural = "Dashboard users"


class InstitutionAlertConfigInline(admin.StackedInline):
    """Alert configuration edited from the institution page.

    ``InstitutionAlertConfig`` has no changelist of its own — same reasoning
    as ``StationDetailsInline`` — and a config only makes sense alongside its
    institution.
    """

    model = InstitutionAlertConfig
    can_delete = False
    extra = 1
    filter_horizontal = ("sensitive_groups",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Institution)
class InstitutionAdmin(RoleBasedModelAdmin):
    """Client organizations in the Sensor Leasing program."""

    list_display = ("legal_name", "display_name", "institution_type", "city")
    list_filter = ("institution_type", "city")
    search_fields = ("legal_name", "display_name", "contact_name", "contact_email")
    ordering = ("legal_name",)
    inlines = (InstitutionUserInline, InstitutionAlertConfigInline)
    fieldsets = (
        (None, {"fields": ("legal_name", "display_name", "institution_type")}),
        (
            "Contact",
            {"fields": ("contact_name", "contact_email", "contact_phone")},
        ),
        ("Location", {"fields": ("address", "city")}),
        ("Notes", {"fields": ("notes",)}),
    )


@admin.register(SensitiveGroup)
class SensitiveGroupAdmin(RoleBasedModelAdmin):
    """Fixed catalog of at-risk groups institutions can flag for alerts."""

    list_display = ("label", "key", "emoji")
    search_fields = ("label", "key")
    ordering = ("label",)


@admin.register(InstitutionContract)
class InstitutionContractAdmin(RoleBasedModelAdmin):
    """Leasing contracts binding an Institution to a station.

    ``institution`` and ``station`` are each OneToOne, so the admin's own
    unique index (not custom validation) is what prevents an institution or a
    station from being attached to more than one contract.
    """

    list_display = (
        "institution",
        "station",
        "contract_status",
        "start_date",
        "end_date",
        "monthly_fee",
    )
    list_filter = ("contract_status",)
    search_fields = (
        "institution__legal_name",
        "institution__display_name",
        "station__name",
    )
    ordering = ("-start_date",)
    autocomplete_fields = ("institution", "station")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("institution", "station", "contract_status")}),
        ("Term", {"fields": ("start_date", "end_date", "monthly_fee")}),
        ("Document", {"fields": ("signed_contract_url",)}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )


class HasPushTokenFilter(admin.SimpleListFilter):
    """Splits installations by whether the app has registered a push token yet.

    The operational question behind it: an installation with follows but no
    token is following stations and cannot be notified about any of them, so
    this is how that gap gets spotted.
    """

    title = "push token"
    parameter_name = "has_push_token"

    def lookups(self, request, model_admin):
        return (("yes", "Registered"), ("no", "Missing"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(push_token="")
        if self.value() == "no":
            return queryset.filter(push_token="")
        return queryset


@admin.register(DeviceInstallation)
class DeviceInstallationAdmin(RoleBasedModelAdmin):
    """Installations of the mobile app, and the push token each one holds.

    Written exclusively by the device-follower API, so add and change are
    disabled: this is a device's own state and editing it here would silently
    redirect somebody's notifications without the app ever knowing. Delete
    stays available under the normal role matrix, so a data-removal request can
    be honoured — and it cascades to the installation's follows, which is what
    such a request means.
    """

    list_display = (
        "installation_id",
        "follow_count",
        "masked_push_token",
        "updated_at",
    )
    list_filter = (HasPushTokenFilter, "updated_at")
    search_fields = ("installation_id", "push_token")
    ordering = ("-updated_at",)
    readonly_fields = (
        "installation_id",
        "push_token",
        "follow_count",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("installation_id", "follow_count")}),
        ("Notifications", {"fields": ("push_token",)}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # Counted in the query rather than per row: the changelist would
        # otherwise issue one COUNT per installation.
        return super().get_queryset(request).annotate(_follow_count=Count("follows"))

    @admin.display(description="Follows", ordering="_follow_count")
    def follow_count(self, obj):
        count = getattr(obj, "_follow_count", None)
        if count is None:
            count = obj.follows.count()
        return count

    @admin.display(description="Push token")
    def masked_push_token(self, obj):
        """Show only enough of the token to tell two of them apart.

        Full tokens are 150+ characters and would swamp the changelist; the
        detail page carries the real value for anyone debugging delivery.
        """
        if not obj.push_token:
            return "—"
        return f"…{obj.push_token[-8:]}"


@admin.register(DeviceFollower)
class DeviceFollowerAdmin(RoleBasedModelAdmin):
    """Which stations each installation follows — one row per pair.

    Read-only for the same reason as the installation above: this is a device's
    own state, written only by the API.

    Rows address their station by ``station_code``, not by a foreign key, so
    the station's name is resolved with a subquery rather than a join — one
    query for the whole changelist instead of one per row.
    """

    list_display = (
        "installation_uuid",
        "station_code",
        "station_name",
        "created_at",
    )
    list_filter = ("station_code", "created_at")
    search_fields = ("installation__installation_id", "station_code")
    ordering = ("-created_at",)
    readonly_fields = (
        "installation",
        "station_code",
        "station_name",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("installation",)}),
        ("Followed station", {"fields": ("station_code", "station_name")}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        station_names = Stations.objects.filter(
            station_code=OuterRef("station_code")
        ).values("name")[:1]
        return (
            super()
            .get_queryset(request)
            .select_related("installation")
            .annotate(_station_name=Subquery(station_names))
        )

    @admin.display(description="Installation", ordering="installation__installation_id")
    def installation_uuid(self, obj):
        return obj.installation.installation_id

    @admin.display(description="Station", ordering="_station_name")
    def station_name(self, obj):
        # Annotated on the changelist; resolved directly on the detail page,
        # which loads the object without going through get_queryset's annotation.
        name = getattr(obj, "_station_name", None)
        if name is None:
            station = obj.station
            name = station.name if station else None
        # An unknown code means the pipeline dropped the station the device
        # follows — worth showing as such rather than as an empty cell.
        return name or "unknown station"


class InstitutionAlertEventInline(admin.TabularInline):
    """The times this alert has fired, shown under the alert that fires them.

    Configuration and history are one page rather than two sections, because
    "AQI > 40 at this school" and "AQI 55 at this school on Tuesday" read as the
    same words and nobody should have to learn which menu entry holds which. The
    events stay their own model — ``ActionLog`` points at them, and the
    institutional dashboard reads them — but an operator never has to know that.

    Read-only, and no add form: an event records that a threshold was actually
    crossed, so a hand-typed row would be indistinguishable from a measured one
    in the audit trail the institution's own action log points at.
    """

    model = InstitutionAlert
    extra = 0
    can_delete = False
    verbose_name = "Time it fired"
    verbose_name_plural = "History — times this alert fired"
    fields = ("triggered_at", "aqi_value", "alert_threshold", "resolved_at")
    readonly_fields = fields
    ordering = ("-triggered_at",)
    # The most recent handful. An alert that has fired for months would
    # otherwise render its entire history on the configuration page.
    max_num = 10

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(InstitutionAlertRule)
class InstitutionAlertRuleAdmin(RoleBasedModelAdmin):
    """Institutional alerts: what triggers one, what it says, and when it fired.

    The single page for the feature. The fields configure the alert — threshold,
    wording, on/off — and the inline below shows the history of it actually
    firing, so an operator sets one up and audits it in the same place.

    Editing here changes what followers receive on the next scheduled run, with
    no deploy involved, which is the whole reason the model exists.
    """

    form = InstitutionAlertRuleForm
    inlines = (InstitutionAlertEventInline,)
    list_display = (
        "institution",
        "station",
        "threshold",
        "push_title",
        "is_active",
        "firing_state",
        "updated_at",
    )
    list_filter = ("is_active", "institution")
    search_fields = (
        "institution__legal_name",
        "institution__display_name",
        "station__name",
        "push_title",
        "push_body",
    )
    ordering = ("institution", "threshold")
    # `state` included so `firing_state` does not issue a query per row.
    list_select_related = ("institution", "station", "state")
    # `station` deliberately stays a plain select rather than an autocomplete:
    # the form narrows it to the chosen institution's single contracted sensor,
    # and an autocomplete widget would go back to the server for its options and
    # undo that narrowing.
    autocomplete_fields = ("institution",)
    readonly_fields = ("created_at", "updated_at")

    class Media:
        # Repopulates the station select when the institution changes, so the
        # narrowing is visible while filling the form rather than only enforced
        # on submit. Progressive enhancement: the form is correct without it.
        js = ("admin/js/institution_alert_rule.js",)

    fieldsets = (
        (
            None,
            {
                "fields": ("institution", "station", "is_active"),
                "description": (
                    "Choose the institution first — the sensor list then holds "
                    "only the one under contract to it."
                ),
            },
        ),
        (
            "AQI condition",
            {
                "fields": ("threshold",),
                "description": (
                    "Followers are notified when this station's AQI rises above "
                    "this value. Any value may be used — an institution may "
                    "choose to alert its own community at a level the public "
                    "alerts deliberately stay quiet for."
                ),
            },
        ),
        (
            "Notification",
            {
                "fields": ("push_title", "push_body"),
                "description": (
                    "What the notification says on the device. Write "
                    "{station} in the message to have the station's name "
                    "substituted."
                ),
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )

    def get_urls(self):
        """Adds the lookup the station select is repopulated from."""
        return [
            path(
                "contracted-station/",
                self.admin_site.admin_view(self.contracted_station_view),
                name="api_institutionalertrule_contracted_station",
            ),
            *super().get_urls(),
        ]

    def contracted_station_view(self, request):
        """The station under contract to one institution, as JSON.

        Wrapped in ``admin_view`` so it is behind the admin login like every
        other page here, and gated on the same permission as the form it
        serves: this reports which sensor an institution leases, which is not
        public information.
        """
        if not (
            self.has_add_permission(request) or self.has_change_permission(request)
        ):
            return JsonResponse({"detail": "Not permitted."}, status=403)

        contract = (
            InstitutionContract.objects.filter(
                institution_id=request.GET.get("institution") or 0
            )
            .select_related("station")
            .first()
        )
        if contract is None or contract.station is None:
            return JsonResponse({"station": None})
        return JsonResponse(
            {"station": {"id": contract.station_id, "name": contract.station.name}}
        )

    @admin.display(description="State", ordering="state__is_firing")
    def firing_state(self, obj):
        """Whether this alert is currently holding an episode open.

        Surfaced here because the state model itself is out of the menu, and
        this answers the question an operator actually has — "did it already
        notify, and why has it gone quiet?" — which the configuration fields
        alone cannot.
        """
        state = getattr(obj, "state", None)
        if state is None or not state.is_firing:
            return "Idle"
        if state.last_aqi is None:
            return "Firing"
        return f"Firing (AQI {state.last_aqi:.0f})"

    def save_model(self, request, obj, form, change):
        """Saves the alert, then evaluates it right away when that is warranted.

        Why evaluate here at all: the scheduled sender reacts to *readings*
        changing, so configuring an alert for air that is already over its
        threshold would notify nobody until the next run — silence about air
        that is bad right now, which is the case the feature exists for. The
        same reasoning already drives ``push.catch_up_follower`` for somebody
        who follows a sensor mid-episode.

        Only on creation, and on a lowered threshold. Fixing a typo in the
        message is not a reason to interrupt anybody, while lowering the
        threshold is exactly the "I want to hear about this sooner" change that
        should take effect now rather than at the next run.

        Delivery failure never blocks the save: the alert is configuration, and
        an unreachable push service is not a reason to lose it.
        """
        lowered = (
            change
            and "threshold" in form.changed_data
            and form.initial.get("threshold") is not None
            and obj.threshold < form.initial["threshold"]
        )
        super().save_model(request, obj, form, change)

        if not (not change or lowered):
            return
        if not push.is_configured():
            # Said out loud rather than skipped quietly: an alert saved for air
            # that is already over its threshold and then sitting at "Idle"
            # looks broken, and the reason is an environment flag the operator
            # cannot see from this page.
            self.message_user(
                request,
                "Saved. Push notifications are switched off in this "
                "environment (BACKEND_SENSOR_ALERTS_ENABLED), so nothing was "
                "sent even though the air may already be over this threshold.",
                messages.WARNING,
            )
            return

        try:
            delivery = push.evaluate_rule(obj)
        except Exception as error:  # noqa: BLE001 - reported, never fatal
            self.message_user(
                request,
                f"Saved, but the immediate check could not be delivered: {error}",
                messages.WARNING,
            )
            return

        if delivery is None:
            return
        if delivery.accepted:
            self.message_user(
                request,
                f"The air is already over this threshold — notified "
                f"{delivery.accepted} device(s) now.",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "The air is already over this threshold, but no device "
                "accepted the notification. It may be that nobody follows "
                "this sensor yet.",
                messages.WARNING,
            )


@admin.register(PushBroadcast)
class PushBroadcastAdmin(ReadOnlyModelAdmin):
    """Send a notification that has nothing to do with air quality, and the log of them.

    The page for messages an AQI threshold cannot express — planned maintenance,
    an outage, anything operational. It carries its own "Send a notification"
    button rather than living as an action on the alert page, because reaching
    a send through a list of AQI alerts would mean picking a threshold that has
    no bearing on the message.

    The rows themselves stay read-only: a broadcast is something that already
    happened, and editing its text afterwards would make this log disagree with
    what the devices actually showed. A send is composed on the page below and
    written only once it is attempted, which is also what stops the same
    announcement going out twice.
    """

    list_display = (
        "sent_at",
        "scope",
        "institution",
        "station",
        "push_title",
        "recipients",
        "failures",
        "sent_by",
    )
    list_filter = ("scope", "sent_at", "institution")
    search_fields = ("push_title", "push_body")
    ordering = ("-sent_at",)
    list_select_related = ("institution", "station", "sent_by")
    compose_template = "admin/api/pushbroadcast/compose.html"
    change_list_template = "admin/api/pushbroadcast/change_list.html"

    def get_urls(self):
        """Adds the compose page under this model's own admin URLs.

        Before ``super()``'s patterns, since those end in a catch-all for object
        ids that would otherwise swallow ``send/``.
        """
        return [
            path(
                "send/",
                self.admin_site.admin_view(self.send_view),
                name="api_pushbroadcast_send",
            ),
            *super().get_urls(),
        ]

    def has_send_permission(self, request):
        """Whether this user may send to one station's or one institution's followers."""
        return request.user.has_perm("api.add_pushbroadcast")

    def has_global_send_permission(self, request):
        """Whether this user may notify every follower on the platform.

        Deliberately a permission of its own. A platform-wide push reaches
        people who never followed any particular sensor and cannot be recalled,
        so being trusted to notify one institution's followers is not the same
        as being trusted to notify everybody.
        """
        return request.user.has_perm("api.send_global_pushbroadcast")

    def changelist_view(self, request, extra_context=None):
        # Drives the "Send a notification" button in the template, so it is
        # absent rather than dead for a user who may not send.
        extra_context = {
            **(extra_context or {}),
            "may_send": self.has_send_permission(request),
        }
        return super().changelist_view(request, extra_context)

    def send_view(self, request):
        """Composes and sends one notification, independent of any AQI value.

        Two passes like ``StationsViewer._override_status``: a GET renders the
        composer, and the POST it submits sends. There is no draft in between —
        the ``PushBroadcast`` row is written at send time, so a resubmitted page
        cannot deliver an announcement that was already delivered.
        """
        if not self.has_send_permission(request):
            raise PermissionDenied

        if request.method == "POST":
            form = PushBroadcastForm(request.POST)
            if form.is_valid():
                self._send(request, form.cleaned_data)
                return redirect("admin:api_pushbroadcast_changelist")
        else:
            form = PushBroadcastForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Send a notification",
            "opts": self.opts,
            "media": self.media + form.media,
            "form": form,
            "may_send_to_everyone": self.has_global_send_permission(request),
        }
        return TemplateResponse(request, self.compose_template, context)

    def _send(self, request, data):
        """Records the broadcast, then delivers it."""
        scope = data["scope"]

        if scope == PushBroadcast.SCOPE_ALL and not self.has_global_send_permission(
            request
        ):
            self.message_user(
                request,
                "You do not have permission to notify every follower on the platform.",
                messages.ERROR,
            )
            return

        if not push.is_configured():
            # Checked before the row is written, so a disabled environment does
            # not accumulate broadcasts that never went anywhere.
            self.message_user(
                request,
                "Push notifications are switched off in this environment "
                "(BACKEND_SENSOR_ALERTS_ENABLED); nothing sent.",
                messages.WARNING,
            )
            return

        # Created before delivery, so an attempt that fails halfway is still on
        # record rather than looking like it never happened.
        broadcast = PushBroadcast.objects.create(
            scope=scope,
            institution=data.get("institution"),
            station=data.get("station"),
            push_title=data["push_title"],
            push_body=data["push_body"],
            sent_by=request.user,
        )

        try:
            delivery = push.send_broadcast(broadcast)
        except Exception as error:  # noqa: BLE001 - surfaced to the operator
            self.message_user(request, f"Delivery failed: {error}", messages.ERROR)
            return

        if delivery.accepted:
            note = (
                f"; {delivery.retriable_failures} rejected"
                if delivery.retriable_failures
                else ""
            )
            self.message_user(
                request,
                f"Notification accepted for {delivery.accepted} device(s){note}.",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "No device accepted the notification. It may be that nobody "
                "follows the selected sensor(s) yet.",
                messages.WARNING,
            )


@admin.register(SensorAlert)
class SensorAlertAdmin(ReadOnlyModelAdmin):
    """Delivery log for the automatic alerts, institutional ones included.

    Here so that "did this alert actually go out, and to how many devices?" is
    answerable from the backoffice rather than only from the container's logs.
    """

    list_display = ("sent_at", "station_code", "level", "trend", "aqi", "recipients")
    list_filter = ("trend", "level", "sent_at")
    search_fields = ("station_code",)
    ordering = ("-sent_at",)


@admin.register(InstitutionAlertRuleState)
class InstitutionAlertRuleStateAdmin(ReadOnlyModelAdmin):
    """Per-alert sender state, for diagnosing one that is not firing.

    Kept out of the menu like the events: this is the sender's own bookkeeping,
    not something an operator manages. The alert page already reports whether
    an alert is currently firing, which is the part worth knowing; this remains
    reachable by URL when a "why has this not fired again?" needs answering.

    Read-only because it *is* that memory: editing ``is_firing`` by hand would
    either suppress a real alert or replay one followers already received.
    """

    list_display = ("rule", "is_firing", "last_aqi", "last_notified_at", "updated_at")
    list_filter = ("is_firing",)
    search_fields = ("rule__institution__legal_name", "rule__station__name")
    list_select_related = ("rule", "rule__institution", "rule__station")

    def has_module_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        """Deletable as a consequence of deleting its alert, never on its own.

        ``ReadOnlyModelAdmin`` refuses deletion outright, which is right for the
        pipeline-owned tables it was written for but wrong here: this row is a
        ``CASCADE`` dependent of ``InstitutionAlertRule``, so Django consults
        this admin while working out what deleting an alert would take with it,
        and a flat ``False`` fails that check and blocks deleting the alert
        itself — for everyone, superusers included, since no permission can
        override a hardcoded refusal.

        A state row is the sender's memory of one alert and means nothing
        without it, so it must go when the alert goes.

        The two cases are told apart by which admin is being asked, not by
        ``obj``: ``get_deleted_objects`` passes each *concrete* row it is about
        to remove, so an ``obj is not None`` test refuses the cascade it means
        to allow. What actually separates them is the request — a deletion
        started from this model's own pages is a hand-typed one and stays
        refused, since removing the memory of an alert that is currently firing
        replays it to followers on the next run.
        """
        if request.path.startswith(
            reverse("admin:api_institutionalertrulestate_changelist")
        ):
            return False
        return RoleBasedModelAdmin.has_delete_permission(self, request, obj)


@admin.register(InstitutionAlert)
class InstitutionAlertEventAdmin(ReadOnlyModelAdmin):
    """The individual firings, registered but kept out of the menu.

    Still registered for two reasons that have nothing to do with browsing it:
    ``ActionLogAdmin`` offers it as an autocomplete target, which requires a
    registered admin with ``search_fields``; and the changelist remains
    reachable by URL for anyone who needs the unfiltered history.

    Hidden from the index (``has_module_permission``) because the operator-facing
    page is ``InstitutionAlertRuleAdmin``, which shows each alert's own firings
    inline. Two menu entries whose names differ only by the word "rule" is the
    confusion this removes.

    Read-only for everyone: the scheduled sender writes these, and a hand-typed
    row would be indistinguishable from a measured one in the audit trail that
    ``ActionLog`` entries point at.
    """

    list_display = (
        "triggered_at",
        "institution",
        "station",
        "aqi_value",
        "alert_threshold",
        "resolved_at",
    )
    list_filter = ("institution", "station", "triggered_at")
    search_fields = (
        "institution__legal_name",
        "institution__display_name",
        "station__name",
    )
    ordering = ("-triggered_at",)
    list_select_related = ("institution", "station", "rule")

    def has_module_permission(self, request):
        """Keeps this out of the admin index without unregistering it.

        Autocomplete and the direct URL both keep working; only the menu entry
        goes away.
        """
        return False

    def has_delete_permission(self, request, obj=None):
        """Never deletable on its own, but never in the way of deleting an alert.

        Same shape as ``InstitutionAlertRuleStateAdmin``, for a different
        relationship. ``InstitutionAlert.institution`` cascades, so Django
        consults this admin while working out what deleting an *institution*
        would take with it, and ``ReadOnlyModelAdmin``'s flat refusal fails
        that check and blocks the deletion outright — for everyone, superusers
        included, since no permission overrides a hardcoded ``False``.

        Told apart by which admin is being asked, not by ``obj``:
        ``get_deleted_objects`` passes each concrete row it is about to remove,
        so an ``obj is not None`` test would refuse the very cascade it means to
        allow. A deletion started from this model's own pages is a hand-typed
        one and stays refused — the firings are the audit trail an ``ActionLog``
        entry points at, so they go when their institution goes and never one at
        a time.

        Note this is not what a deleted *alert* does to its firings:
        ``InstitutionAlert.rule`` is ``SET_NULL``, so retiring an alert keeps
        every event it ever fired and merely forgets which alert produced it.
        """
        if request.path.startswith(reverse("admin:api_institutionalert_changelist")):
            return False
        return RoleBasedModelAdmin.has_delete_permission(self, request, obj)


class AlertLinkFilter(admin.SimpleListFilter):
    """Splits the history by whether an action responded to a recorded alert.

    A plain ``("alert",)`` filter would list every alert individually, which is
    not the question an operator asks here — they want the actions that answered
    *some* alert, versus the ones logged on their own initiative.
    """

    title = "alert association"
    parameter_name = "has_alert"

    def lookups(self, request, model_admin):
        return (("yes", "Linked to an alert"), ("no", "No alert linked"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(alert__isnull=False)
        if self.value() == "no":
            return queryset.filter(alert__isnull=True)
        return queryset


@admin.register(ActionLog)
class ActionLogAdmin(ReadOnlyModelAdmin):
    """The institutional action history, for review from the backoffice.

    ``ReadOnlyModelAdmin`` — for everyone, superadmins included — because this
    is an audit trail: entries are written by the institutions themselves
    through the API, and a history that the backoffice can rewrite after the
    fact is not traceable. That also enforces the ticket's rule that
    ``timestamp`` cannot be overwritten by hand.
    """

    list_display = ("timestamp", "institution", "station", "alert", "note_excerpt")
    list_filter = (AlertLinkFilter, "institution", "station", "timestamp")
    search_fields = (
        "institution__legal_name",
        "institution__display_name",
        "station__name",
        "note",
    )
    ordering = ("-timestamp", "-id")
    list_select_related = ("institution", "station", "alert")
    fieldsets = (
        (None, {"fields": ("institution", "station", "timestamp")}),
        ("Alert", {"fields": ("alert",)}),
        ("Action", {"fields": ("note",)}),
    )

    @admin.display(description="Note")
    def note_excerpt(self, obj):
        """First line of the note, so the changelist stays one row per action."""
        first_line = obj.note.strip().splitlines()[0] if obj.note.strip() else ""
        return first_line if len(first_line) <= 80 else f"{first_line[:77]}…"


@admin.register(StationOverride)
class StationOverrideAdmin(RoleBasedModelAdmin):
    """Operational overrides consumed by the dbt pipeline.

    Replaces editing ``station_status_seed.csv`` by hand.
    """

    list_display = ("station_code", "field", "value", "change_date", "processed")
    list_filter = ("processed", "field")
    search_fields = ("station_code", "value", "note")
    ordering = ("-change_date",)
    # Set by the pipeline once it has consumed the override.
    readonly_fields = ("processed",)
    fieldsets = (
        (None, {"fields": ("station_code", "field", "value")}),
        ("Context", {"fields": ("note", "change_date")}),
        ("Pipeline", {"fields": ("processed",)}),
    )
