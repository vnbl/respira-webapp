from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from .models import (
    ActionLog,
    DeviceFollower,
    DeviceInstallation,
    FaqCategory,
    FaqQuestion,
    Institution,
    InstitutionAlert,
    InstitutionContract,
    Regions,
    SensitiveGroup,
    Stations,
    StationReadingsGold,
    UserProfile,
    UserRole,
    faq_localized_map,
    get_institution_for_user,
    get_institution_station_ids,
    user_role,
)

User = get_user_model()


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regions
        fields = [
            "id",
            "name",
            "region_code",
            "bbox",
            "has_weather_data",
            "has_pattern_station",
        ]


class StationSerializer(serializers.ModelSerializer):
    region = RegionSerializer(allow_null=True)
    coordinates = serializers.SerializerMethodField()
    aqi_pm2_5 = serializers.SerializerMethodField()

    class Meta:
        model = Stations
        fields = [
            "id",
            "name",
            "region",
            "coordinates",
            "is_station_on",
            "is_pattern_station",
            "aqi_pm2_5",
        ]

    @extend_schema_field(
        serializers.ListField(
            child=serializers.FloatField(allow_null=True),
            min_length=2,
            max_length=2,
        )
    )
    def get_coordinates(self, obj) -> list[float | None]:
        return [obj.latitude, obj.longitude]

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_aqi_pm2_5(self, obj) -> float | None:
        last_reading = (
            StationReadingsGold.objects.filter(station_id=obj.id)
            .order_by("-date_utc")
            .first()
        )
        return last_reading.aqi_pm2_5 if last_reading else None


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()


class MapSerializer(serializers.Serializer):
    aqi = serializers.FloatField()
    forecast_6h = serializers.JSONField()
    forecast_12h = serializers.JSONField()


class ForecastSerializer(serializers.Serializer):
    forecast_date = serializers.DateTimeField()
    aqi_level = serializers.JSONField()
    forecast_6h = serializers.JSONField()
    forecast_12h = serializers.JSONField()


class HistorySerializer(serializers.Serializer):
    historical_1d = serializers.JSONField()
    historical_7d = serializers.JSONField()
    historical_30d = serializers.JSONField()


class _RoleAssignmentMixin:
    """Enforce that only a superadmin may assign or modify the superadmin role."""

    def _acting_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def validate_role(self, value):
        acting_user = self._acting_user()
        acting_is_superadmin = (
            acting_user is not None and user_role(acting_user) == UserRole.SUPERADMIN
        )

        if value == UserRole.SUPERADMIN and not acting_is_superadmin:
            raise serializers.ValidationError(
                "Only a superadmin may assign the superadmin role."
            )

        target = getattr(self, "instance", None)
        if (
            target is not None
            and user_role(target) == UserRole.SUPERADMIN
            and value != UserRole.SUPERADMIN
            and not acting_is_superadmin
        ):
            raise serializers.ValidationError(
                "Only a superadmin may modify a superadmin's role."
            )

        return value


class AdminUserSerializer(serializers.ModelSerializer):
    """Read representation of a platform user (auth user + platform role)."""

    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_role(self, obj) -> str:
        return user_role(obj)


class AdminUserCreateSerializer(_RoleAssignmentMixin, serializers.ModelSerializer):
    """Create a platform user with a hashed password and a unique email."""

    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="A user with this email already exists.",
            )
        ]
    )
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    role = serializers.ChoiceField(
        choices=UserRole.choices, required=False, default=UserRole.VIEWER
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
            "is_active",
        ]

    @transaction.atomic
    def create(self, validated_data):
        role = validated_data.pop("role", UserRole.VIEWER)
        password = validated_data.pop("password")
        email = validated_data["email"]
        # The default Django user requires a username; keep it in sync with email.
        user = User(username=email, **validated_data)
        user.set_password(password)
        user.save()
        UserProfile.objects.create(user=user, role=role)
        return user

    def to_representation(self, instance):
        return AdminUserSerializer(instance, context=self.context).data


class AdminUserUpdateSerializer(_RoleAssignmentMixin, serializers.ModelSerializer):
    """Update profile information, role and status of a platform user."""

    email = serializers.EmailField(
        required=False,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="A user with this email already exists.",
            )
        ],
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    role = serializers.ChoiceField(choices=UserRole.choices, required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
            "is_active",
        ]

    @transaction.atomic
    def update(self, instance, validated_data):
        role = validated_data.pop("role", None)
        password = validated_data.pop("password", None)
        email = validated_data.get("email")

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if email:
            instance.username = email
        if password is not None:
            instance.set_password(password)
        instance.save()

        if role is not None:
            profile, _ = UserProfile.objects.update_or_create(
                user=instance, defaults={"role": role}
            )
            # Refresh the cached reverse relation so the response reflects the
            # new role (validate_role may have cached the old profile).
            instance.profile = profile
        return instance

    def to_representation(self, instance):
        return AdminUserSerializer(instance, context=self.context).data


class FaqQuestionSerializer(serializers.ModelSerializer):
    """Serializes a question into the `{ q: {es, en, pt}, a: {...} }` shape the
    frontend already uses for its bundled seed, so the two are interchangeable.

    The Spanish fallback is applied here rather than in the frontend so the rule
    lives in one place; an untranslated question ships Spanish text under every
    language key instead of an empty string.
    """

    q = serializers.SerializerMethodField()
    a = serializers.SerializerMethodField()

    class Meta:
        model = FaqQuestion
        fields = ["id", "q", "a"]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_q(self, obj):
        return faq_localized_map(obj, "question")

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_a(self, obj):
        return faq_localized_map(obj, "answer")


class FaqCategorySerializer(serializers.ModelSerializer):
    """Serializes a category with its published questions nested.

    ``id`` is the slug, not the primary key: the public page uses it as the
    anchor (``#sensor``), so it must survive rows being recreated.
    """

    id = serializers.CharField(source="slug")
    label = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()

    class Meta:
        model = FaqCategory
        fields = ["id", "label", "questions"]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_label(self, obj):
        return faq_localized_map(obj, "label")

    @extend_schema_field(FaqQuestionSerializer(many=True))
    def get_questions(self, obj):
        published = [q for q in obj.questions.all() if q.is_published]
        return FaqQuestionSerializer(published, many=True).data


class InstitutionContractSerializer(serializers.ModelSerializer):
    """Contract summary nested under the institution's own dashboard view."""

    station_name = serializers.CharField(source="station.name", read_only=True)

    class Meta:
        model = InstitutionContract
        fields = [
            "id",
            "station",
            "station_name",
            "contract_status",
            "start_date",
            "end_date",
            "monthly_fee",
            "signed_contract_url",
        ]
        read_only_fields = fields


class InstitutionSerializer(serializers.ModelSerializer):
    """Self-service representation of an institution for its own dashboard.

    Distinct from any future backoffice serializer: this is what an
    institutional user sees about *their own* institution, so it never nests
    other institutions' data.
    """

    contract = serializers.SerializerMethodField()

    class Meta:
        model = Institution
        fields = [
            "id",
            "legal_name",
            "display_name",
            "institution_type",
            "contact_name",
            "contact_email",
            "contact_phone",
            "address",
            "city",
            "contract",
        ]
        read_only_fields = fields

    @extend_schema_field(InstitutionContractSerializer(allow_null=True))
    def get_contract(self, obj):
        contract = getattr(obj, "contract", None)
        return InstitutionContractSerializer(contract).data if contract else None


class InstitutionLoginSerializer(serializers.Serializer):
    """Validates institutional-dashboard login credentials.

    Authenticates through the platform's existing ``authenticate()`` call —
    same ``AUTHENTICATION_BACKENDS`` (including axes lockout), same
    ``accounts.User`` model and password hasher as the admin login — so this
    is a new entry point, not a new authentication mechanism.

    Whether the authenticated user actually has an institution to access is
    checked in the view rather than here, so that case can be rejected with
    403 instead of being folded into the 400 this raises for bad credentials.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request, username=attrs["email"], password=attrs["password"]
        )
        if user is None or not user.is_active:
            raise serializers.ValidationError("Invalid email or password.")
        attrs["user"] = user
        return attrs


class InstitutionPasswordResetSerializer(serializers.Serializer):
    """Accepts the email a password reset was requested for.

    Deliberately does nothing beyond validating the address' shape. Whether an
    account exists is decided (and acted on) in the view, which answers the same
    way either way — see ``InstitutionViewSet.password_reset``. Rejecting an
    unknown address here would turn this endpoint into an account oracle.
    """

    email = serializers.EmailField()


class InstitutionPasswordResetConfirmSerializer(serializers.Serializer):
    """Validates a reset link and the new password chosen through it.

    The token machinery is Django's own
    (``default_token_generator`` + ``urlsafe_base64`` uid), so an expired,
    tampered-with or already-used link fails here exactly as it would in the
    admin flow: ``check_token`` hashes the user's current password and
    ``last_login`` into the token, so consuming a link invalidates it.

    Password rules come from ``AUTH_PASSWORD_VALIDATORS`` via
    ``validate_password``, the same pipeline the admin and the user API use.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    default_error_messages = {
        "invalid_link": "This password reset link is invalid or has expired.",
    }

    def _user_from_uid(self, uid: str):
        try:
            pk = urlsafe_base64_decode(uid).decode()
            return User.objects.get(pk=pk)
        except (
            TypeError,
            ValueError,
            OverflowError,
            # `User.pk` is a UUID, so a decodable-but-nonsensical uid fails in
            # the field's `to_python` rather than as a plain ValueError.
            DjangoValidationError,
            User.DoesNotExist,
        ):
            return None

    def validate(self, attrs):
        user = self._user_from_uid(attrs["uid"])
        # One message for every way a link can be unusable — a decodable uid
        # that maps to no user would otherwise confirm which ids exist.
        if (
            user is None
            or not user.is_active
            or not default_token_generator.check_token(user, attrs["token"])
        ):
            self.fail("invalid_link")

        # Run the validators against the target user so the ones that compare
        # the password to account attributes (similarity) have something to
        # compare with. Errors are re-raised under `new_password` so the form
        # can put them next to the field the visitor has to fix.
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {
                    "new_password": error.messages,
                    # Django's messages are English whatever the client speaks.
                    # The codes are stable identifiers a client can map onto its
                    # own copy — which is what the Spanish reset page does.
                    "new_password_codes": [
                        item.code for item in error.error_list if item.code
                    ],
                }
            )

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class InstitutionAlertSerializer(serializers.ModelSerializer):
    """Read-only view of an alert recorded for the caller's own institution.

    Read-only on purpose: alerts record that a threshold was crossed, so they
    are produced by the platform (today from the admin, later by an alert
    generator) and only ever consulted by an institution — never authored by
    one. Exposing them is what lets the dashboard offer "which alert does this
    action respond to?" instead of leaving ``ActionLog.alert`` writable with no
    way for a client to discover a valid value.
    """

    station_name = serializers.CharField(source="station.name", read_only=True)
    is_resolved = serializers.SerializerMethodField()

    class Meta:
        model = InstitutionAlert
        fields = [
            "id",
            "station",
            "station_name",
            "aqi_value",
            "alert_threshold",
            "triggered_at",
            "resolved_at",
            "is_resolved",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_resolved(self, obj) -> bool:
        """``resolved_at`` is left empty while the event is still ongoing."""
        return obj.resolved_at is not None


class InstitutionNotificationSerializer(serializers.Serializer):
    """One notification sent about an institution's own sensor.

    A plain ``Serializer`` rather than a ``ModelSerializer`` because there is no
    single model behind it: what an institution experiences as "a notification"
    is produced by two different tables with two different shapes —
    :class:`InstitutionAlert` for the AQI-triggered ones and
    :class:`PushBroadcast` for the manual, operational ones. The view normalises
    both into the dicts this serializes, so the dashboard reads one ordered list
    instead of having to merge two feeds itself.

    Read-only throughout: notifications are produced by the platform (the
    scheduled sender, or an operator in the admin) and only ever consulted by an
    institution — never authored by one from the dashboard.

    Everything specific to the AQI path (``aqi``, ``aqi_category``,
    ``aqi_category_label``, ``alert_threshold``, ``alert``) is nullable, because
    a manual announcement — "no hay clases mañana" — has no reading behind it.
    Clients must key off ``type`` rather than assume any of those are present.
    """

    TYPE_AQI = "aqi"
    TYPE_GENERAL = "general"

    # Prefixed with its source table ("alert-12", "broadcast-7") so the merged
    # list has stable, collision-free keys: the two tables number their rows
    # independently, so a bare pk would repeat across the feed.
    id = serializers.CharField(read_only=True)
    type = serializers.ChoiceField(
        choices=((TYPE_AQI, "AQI-triggered"), (TYPE_GENERAL, "General/manual")),
        read_only=True,
    )
    title = serializers.CharField(read_only=True)
    body = serializers.CharField(read_only=True)
    sent_at = serializers.DateTimeField(read_only=True)

    station = serializers.IntegerField(read_only=True, allow_null=True)
    station_name = serializers.CharField(read_only=True, allow_null=True)

    aqi = serializers.FloatField(read_only=True, allow_null=True)
    aqi_category = serializers.CharField(read_only=True, allow_null=True)
    aqi_category_label = serializers.CharField(read_only=True, allow_null=True)
    alert_threshold = serializers.IntegerField(read_only=True, allow_null=True)

    # The `InstitutionAlert` row this notification came from, when it came from
    # one. Exposed so a client can tie a notification back to the alert an
    # `ActionLog` entry responds to — the two features name the same event.
    alert = serializers.IntegerField(read_only=True, allow_null=True)


class ActionLogSerializer(serializers.ModelSerializer):
    """Create and read the actions an institution recorded.

    A single serializer for both directions: the fields a client must not
    control — ``institution`` and ``timestamp`` — are read-only, so they are
    ignored if posted and assigned by the backend instead. That is what makes
    "the client cannot create a record on behalf of another institution" a
    property of the serializer rather than a check the view has to remember.

    ``station`` and ``alert`` *are* writable, so both are validated against the
    caller's own institution below; the caller's institution comes from the
    request (via the view's context), never from the payload.
    """

    institution_name = serializers.SerializerMethodField()
    station_name = serializers.CharField(source="station.name", read_only=True)
    # `alert` stays the writable id; this is the same alert expanded, so a
    # client rendering a list of actions can show which event each one answered
    # without fetching every alert separately and joining them itself.
    alert_detail = InstitutionAlertSerializer(source="alert", read_only=True)

    class Meta:
        model = ActionLog
        fields = [
            "id",
            "institution",
            "institution_name",
            "station",
            "station_name",
            "alert",
            "alert_detail",
            "timestamp",
            "note",
        ]
        read_only_fields = ["id", "institution", "timestamp"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_institution_name(self, obj) -> str:
        return str(obj.institution)

    def _institution(self):
        """The caller's institution, resolved from the request — never the payload."""
        institution = self.context.get("institution")
        if institution is not None:
            return institution
        request = self.context.get("request")
        return get_institution_for_user(getattr(request, "user", None))

    def validate_station(self, value):
        """Reject a station the caller's institution does not hold a contract for.

        A caller with no institution at all resolves to an empty set of allowed
        stations and lands here too, though in practice ``IsInstitutionUser``
        has already answered that case with a 403.
        """
        if value.pk not in get_institution_station_ids(self._institution()):
            raise serializers.ValidationError(
                "This station is not assigned to your institution."
            )
        return value

    def validate_alert(self, value):
        if value is None:
            return value
        institution = self._institution()
        if institution is None or value.institution_id != institution.pk:
            raise serializers.ValidationError(
                "This alert does not belong to your institution."
            )
        return value

    def validate(self, attrs):
        """Cross-field check: an alert must concern the station being acted on.

        Both fields have already been confirmed to belong to the caller's
        institution individually; this rejects the remaining inconsistent
        combination, where a valid alert is attached to a different station.
        """
        alert = attrs.get("alert")
        station = attrs.get("station")
        if alert is not None and station is not None and alert.station_id != station.pk:
            raise serializers.ValidationError(
                {"alert": "This alert does not belong to the selected station."}
            )
        return attrs


class SensitiveGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensitiveGroup
        fields = ["key", "label", "emoji"]
        read_only_fields = fields


class DashboardLocationSerializer(serializers.Serializer):
    city = serializers.CharField(allow_blank=True, allow_null=True)
    specific_location = serializers.CharField(allow_blank=True, allow_null=True)
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)


class DashboardSensorSerializer(serializers.Serializer):
    """The institution's assigned sensor, as shown on its dashboard."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=["online", "offline"])
    location = DashboardLocationSerializer()
    last_measurement_at = serializers.DateTimeField(allow_null=True)


class DashboardAirQualitySerializer(serializers.Serializer):
    """Current AQI plus the Proyecto Respira classification for it."""

    aqi = serializers.FloatField()
    category = serializers.CharField()
    category_label = serializers.CharField()
    message = serializers.CharField()
    recommendations = serializers.ListField(child=serializers.CharField())


class DashboardHistoryPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    aqi = serializers.FloatField(allow_null=True)


class InstitutionAlertConfigSerializer(serializers.Serializer):
    """The institution's alert configuration, or a controlled default.

    Backed by a plain dict built in the view rather than the model directly,
    so an institution with no ``InstitutionAlertConfig`` row still gets a
    valid, consistent shape (disabled, no threshold, no groups) instead of a
    missing section.
    """

    is_enabled = serializers.BooleanField()
    alert_threshold = serializers.IntegerField(allow_null=True)
    sensitive_groups = SensitiveGroupSerializer(many=True)


class InstitutionDashboardSerializer(serializers.Serializer):
    """Consolidated payload for the institutional dashboard's single request."""

    sensor = DashboardSensorSerializer()
    air_quality = DashboardAirQualitySerializer(allow_null=True)
    history = DashboardHistoryPointSerializer(many=True)
    alert_config = InstitutionAlertConfigSerializer()


class DeviceFollowerSerializer(serializers.ModelSerializer):
    """One station a mobile installation follows.

    ``station`` is resolved from the stored ``station_code`` on every read, so
    the id handed to the app is the one that is current *now* — ids move when
    dbt renumbers ``stations``. It is null when the code no longer matches any
    station, which tells the app that sensor is gone rather than silently
    pointing it at whichever station inherited the id.

    The installation id is not echoed back on each row: the caller supplied it,
    and repeating it once per follow is noise.
    """

    station = serializers.SerializerMethodField()
    station_name = serializers.SerializerMethodField()

    class Meta:
        model = DeviceFollower
        fields = [
            "station",
            "station_code",
            "station_name",
            "created_at",
        ]
        read_only_fields = fields

    @staticmethod
    def _station(obj):
        # Cached on the instance so the two method fields below resolve the
        # station once per response instead of querying twice.
        if not hasattr(obj, "_resolved_station"):
            obj._resolved_station = obj.station
        return obj._resolved_station

    @extend_schema_field(OpenApiTypes.INT)
    def get_station(self, obj) -> int | None:
        station = self._station(obj)
        return station.id if station else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_station_name(self, obj) -> str | None:
        station = self._station(obj)
        return station.name if station else None


class DeviceInstallationSerializer(serializers.ModelSerializer):
    """The installation itself: its token status and how much it follows.

    The push token is reported as a boolean rather than echoed back. These
    endpoints are unauthenticated, so anyone holding an installation id could
    otherwise read the device's token.
    """

    has_push_token = serializers.SerializerMethodField()
    follow_count = serializers.SerializerMethodField()

    class Meta:
        model = DeviceInstallation
        fields = [
            "installation_id",
            "has_push_token",
            "follow_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_has_push_token(self, obj) -> bool:
        return bool(obj.push_token)

    @extend_schema_field(OpenApiTypes.INT)
    def get_follow_count(self, obj) -> int:
        return obj.follows.count()


class DeviceFollowerWriteSerializer(serializers.Serializer):
    """Validates a follow request from a mobile installation.

    Not a ``ModelSerializer``: the request speaks in station ids while the row
    stores ``station_code``.

    ``installation_id`` is declared here so it appears in the OpenAPI request
    body, but the view resolves it (header first, then query string, then body)
    before this serializer runs — a request may legitimately carry it in the
    header instead.
    """

    installation_id = serializers.UUIDField(
        required=False,
        help_text=(
            "UUIDv4 identifying the app installation. May be sent in the "
            "X-Installation-Id header instead, which is preferred."
        ),
    )
    station = serializers.PrimaryKeyRelatedField(
        queryset=Stations.objects.all(),
        help_text="Id of the station to follow.",
    )
    push_token = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text=(
            "Current FCM/APNs token, if the app has one to register alongside "
            "the follow. Send an empty string to clear it."
        ),
    )

    def validate_station(self, value):
        if not value.station_code:
            # A follower row addresses its station by code, so a station the
            # pipeline has not assigned one to cannot be followed at all —
            # same limitation the admin's activate/deactivate action hits.
            raise serializers.ValidationError(
                "This station has no station code yet and cannot be followed."
            )
        return value


class DeviceInstallationWriteSerializer(serializers.Serializer):
    """Registers or refreshes the installation's push token.

    Separate from following, because the OS rotates the token at any time and
    independently of which stations the device follows — and because with
    several follows the token belongs to the installation, not to any one of
    them.
    """

    installation_id = serializers.UUIDField(
        required=False,
        help_text=(
            "UUIDv4 identifying the app installation. May be sent in the "
            "X-Installation-Id header instead, which is preferred."
        ),
    )
    push_token = serializers.CharField(
        allow_blank=True,
        help_text="Current FCM/APNs token. Send an empty string to clear it.",
    )
