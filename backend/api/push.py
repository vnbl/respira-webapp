"""Per-sensor push alerts, sent to the devices that follow each sensor.

The audience is :class:`DeviceFollower` — the same rows the app writes when a
user follows a sensor. Deriving it from anywhere else (a segment in the push
provider, say) would mean a second copy that can drift, and drift here means
somebody paying for a leased sensor silently stops being warned about their own
air.

Delivery goes through Expo's push service, which is what the tokens are for:
`PushWaveClient.init()` obtains an Expo push token on the device, and the app
registers it against its installation. PushWave keeps handling the regional
campaigns it already handles; this path exists because "notify exactly the
followers of station X when it crosses a threshold" has to be driven by our own
data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .aqi import classify_aqi
from .models import (
    DeviceFollower,
    DeviceInstallation,
    InstitutionAlert,
    InstitutionAlertRule,
    InstitutionAlertRuleState,
    PushBroadcast,
    SensorAlert,
    SensorAlertState,
    StationReadingsGold,
    Stations,
)

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# Expo accepts at most 100 messages per request.
EXPO_BATCH_SIZE = 100

REQUEST_TIMEOUT_SECONDS = 15

# Levels worth interrupting somebody for. "Good" and "moderate" are not alerts;
# sending them would train people to dismiss the ones that matter.
ALERT_LEVELS = ("unhealthySensitive", "unhealthy", "veryUnhealthy", "hazardous")

LEVEL_RANK = {
    "good": 0,
    "moderate": 1,
    "unhealthySensitive": 2,
    "unhealthy": 3,
    "veryUnhealthy": 4,
    "hazardous": 5,
}

# Spanish copy, mirroring the strings the app already ships for its own local
# notifications (`src/i18n/ui.ts`, `aqi.notif.*`). The device shows whatever the
# payload carries, so the wording lives here for the alerts we originate.
LEVEL_COPY = {
    "unhealthySensitive": (
        "Precaución para grupos sensibles",
        "La calidad del aire en {station} puede afectar a personas sensibles. "
        "Reducí actividades físicas prolongadas al aire libre.",
    ),
    "unhealthy": (
        "Calidad del aire insalubre",
        "{station} registra aire insalubre. Reducí al mínimo la exposición "
        "prolongada al aire libre.",
    ),
    "veryUnhealthy": (
        "Alerta de calidad del aire",
        "{station} registra aire muy insalubre. Evitá actividades al aire libre.",
    ),
    "hazardous": (
        "Alerta sanitaria por calidad del aire",
        "{station} registra aire peligroso. Permanecé en interiores y evitá la "
        "exposición al aire exterior.",
    ),
}

# The other direction: what followers are told once the air at a station they
# were warned about gets better. Keyed by the level being *arrived at*, which is
# why there is no `hazardous` entry — nothing outranks it, so it can never be
# the destination of an improvement.
#
# Every drop is announced, including one that lands on another alert-worthy
# level: going from hazardous to unhealthy still changes what somebody deciding
# whether to go outside should do, and staying silent until `good` would leave
# them acting on the worst reading of the episode for hours.
RECOVERY_COPY = {
    "good": (
        "El aire mejoró",
        "{station} volvió a niveles buenos de calidad del aire. Podés retomar "
        "tus actividades al aire libre.",
    ),
    "moderate": (
        "El aire mejoró",
        "{station} bajó a calidad del aire moderada. Ya no hay riesgo para la "
        "mayoría de las personas.",
    ),
    "unhealthySensitive": (
        "El aire mejoró",
        "{station} bajó a un nivel que solo afecta a grupos sensibles. Si sos "
        "sensible, seguí con precaución.",
    ),
    "unhealthy": (
        "El aire mejoró",
        "{station} bajó a aire insalubre. Sigue conviniendo limitar la "
        "exposición prolongada al aire libre.",
    ),
    "veryUnhealthy": (
        "El aire mejoró",
        "{station} bajó a aire muy insalubre. Seguí evitando las actividades "
        "al aire libre.",
    ),
}

WORSENING = SensorAlert.TREND_WORSENING
IMPROVING = SensorAlert.TREND_IMPROVING
CATCH_UP = SensorAlert.TREND_CATCH_UP


@dataclass
class SendResult:
    """What one run did, for logging and for the management command's output."""

    considered: int = 0
    alerted_stations: int = 0
    # Counted apart from `alerted_stations` so a run that only stood people
    # down is not reported as a run that warned them.
    recovered_stations: int = 0
    messages_sent: int = 0
    tokens_cleared: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def notified_stations(self) -> int:
        return self.alerted_stations + self.recovered_stations


@dataclass
class Delivery:
    """What Expo did with one station's batch of alerts."""

    accepted: int = 0
    cleared: int = 0
    # Errors worth trying again: anything that is not a device that has
    # unregistered, plus messages Expo answered 200 to without a ticket.
    retriable_failures: int = 0

    @property
    def delivered(self) -> bool:
        """Whether the alerting state may advance past this level.

        The partial-delivery policy, stated once: one accepted message is
        enough. Retrying the whole station because a single token was rate
        limited would re-notify everyone the first attempt did reach, and
        duplicate alerts are the failure this feature exists to avoid.

        Nothing to retry also counts — no follower holds a token, or every
        token turned out to be dead — since a later run would find exactly the
        same nobody to send to.
        """
        return self.accepted > 0 or self.retriable_failures == 0


def should_alert(level: str, last_alerted_level: str | None) -> bool:
    """Whether a station at ``level`` warrants notifying its followers now.

    Mirrors the rule the app already applies to its own local notifications:
    only alert-worthy levels, and only when the air has actually got worse than
    what these followers were last told. Without the second half, a station
    hovering at the boundary would notify on every single reading.

    ``last_alerted_level`` is blank both for a station that has never alerted
    and for one that has since recovered to a safe level (see
    :meth:`_remember`), so the next bad episode alerts from its first reading
    rather than having to beat the worst level of the previous one.
    """
    if level not in ALERT_LEVELS:
        return False
    if not last_alerted_level:
        return True
    return LEVEL_RANK[level] > LEVEL_RANK[last_alerted_level]


def should_notify_recovery(level: str, last_alerted_level: str | None) -> bool:
    """Whether followers should be told the air at this station has improved.

    Only while an episode is open. Blank ``last_alerted_level`` means these
    followers were never warned about anything, and an all-clear for a warning
    nobody received is pure noise — it would fire on every station sitting
    quietly at ``good``.

    Any drop counts, not only a return to safety: see :data:`RECOVERY_COPY`.
    """
    if not last_alerted_level or level not in LEVEL_RANK:
        return False
    return LEVEL_RANK[level] < LEVEL_RANK[last_alerted_level]


def notification_for(level: str, last_alerted_level: str | None) -> str | None:
    """Which notification this reading warrants, or ``None`` for silence.

    One place to ask, so the sender and the dry run cannot answer differently.
    """
    if should_alert(level, last_alerted_level):
        return WORSENING
    if should_notify_recovery(level, last_alerted_level):
        return IMPROVING
    return None


def _remember(state: SensorAlertState, level: str, *, notified: bool) -> None:
    """Writes back what this run saw, and what its followers were last told.

    ``last_alerted_level`` is the level the followers currently believe, so it
    moves in both directions: up when they are warned, down when they are told
    the air improved, and back to blank once the station is safe again. That
    blank is what ends the episode — without it a station that alerted at
    ``hazardous`` could never alert again, since no later level outranks it.

    Left untouched when the notification did not reach anybody, so the next run
    makes the same announcement again rather than treating it as delivered.
    """
    state.last_level = level
    if notified:
        state.last_alerted_level = "" if level not in ALERT_LEVELS else level
    state.save(update_fields=["last_level", "last_alerted_level", "updated_at"])


def _latest_level(station: Stations) -> tuple[str, float] | None:
    """The station's most recent reading, as ``(level, aqi)``.

    ``None`` when there is nothing to judge: no reading, or one without an AQI.

    Rows without a timestamp are excluded rather than sorted around: ``date_utc``
    is nullable and PostgreSQL puts nulls first on a descending sort, so one
    undated row would shadow the genuinely latest reading and have the sender
    act on air of unknown age.
    """
    reading = (
        StationReadingsGold.objects.filter(
            station_id=station.id, date_utc__isnull=False
        )
        .order_by("-date_utc")
        .first()
    )
    if reading is None or reading.aqi_pm2_5 is None:
        return None

    classified = classify_aqi(reading.aqi_pm2_5)
    if classified is None:
        return None

    level = {
        "unhealthy_sensitive": "unhealthySensitive",
        "very_unhealthy": "veryUnhealthy",
    }.get(classified["key"], classified["key"])
    return level, reading.aqi_pm2_5


def _tokens_following(station_code: str) -> list[str]:
    """Push tokens of every installation following ``station_code``.

    Deduplicated, even though ``uniq_active_push_token`` now keeps a live token
    on a single installation: sending the same device two copies of one alert
    is the failure this whole path is trying to avoid, and it is cheap to be
    sure of it here rather than infer it from a constraint two models away.
    """
    tokens = (
        DeviceInstallation.objects.filter(follows__station_code=station_code)
        .exclude(push_token="")
        # `order_by()` clears the model's default ordering. Without it Django
        # adds `updated_at` to the SELECT so it can sort, and DISTINCT then
        # operates over the (token, updated_at) pair — which never collides, so
        # the deduplication silently does nothing and the device is notified
        # once per installation holding the token.
        .order_by()
        .values_list("push_token", flat=True)
        .distinct()
    )
    return list(tokens)


def _message(
    token: str,
    station: Stations,
    level: str,
    aqi: float,
    trend: str,
    copy_override: tuple[str, str] | None = None,
) -> dict:
    # `LEVEL_COPY` covers a catch-up as well as a warning: its wording is
    # present tense ("{station} registra aire insalubre"), which is true either
    # way. Only the all-clear needs to talk about a change.
    #
    # `copy_override` is an institution's own wording for its own sensor
    # (`InstitutionAlertRule`). It *replaces* the level table rather than being
    # sent alongside it: a follower would otherwise receive two near-identical
    # notifications about one reading, which is the failure this module exists
    # to avoid. Its `{station}` is already resolved by `rule.message_for`.
    if copy_override is not None:
        title, body = copy_override
    else:
        copy = RECOVERY_COPY if trend == IMPROVING else LEVEL_COPY
        title, body = copy[level]
        body = body.format(station=station.name)
    return {
        "to": token,
        "title": title,
        "body": body,
        "sound": "default",
        "data": {
            # Still `sensor_alert` for an all-clear. The shipped app routes on
            # this exact value and treats anything else as unknown, so a new
            # type would produce a notification that does nothing when tapped
            # until every user updates. The direction rides alongside instead.
            "type": "sensor_alert",
            # The stable code, never the id: dbt regenerates station ids on
            # every run, so an id in a payload can already mean a different
            # sensor by the time the notification is opened. The app resolves
            # this code against the follows it holds.
            "station_code": station.station_code,
            "aqi": round(aqi),
            "level": level,
            "trend": trend,
        },
    }


def _is_dead(ticket: dict) -> bool:
    """Whether Expo says this token belongs to an app that is gone.

    Only ``DeviceNotRegistered`` counts — other errors are transient and acting
    on them would lose a live device's token.
    """
    return (
        ticket.get("status") == "error"
        and (ticket.get("details") or {}).get("error") == "DeviceNotRegistered"
    )


def _clear_dead_tokens(tokens: list[str], tickets: list[dict]) -> int:
    """Blanks the tokens Expo says are no longer registered.

    An uninstalled app keeps its row forever otherwise, and every later run
    pays to deliver to it.
    """
    dead = [token for token, ticket in zip(tokens, tickets) if _is_dead(ticket)]
    if not dead:
        return 0

    return DeviceInstallation.objects.filter(push_token__in=dead).update(
        push_token="", updated_at=timezone.now()
    )


def _post_batch(messages: list[dict]) -> list[dict]:
    response = requests.post(
        EXPO_PUSH_URL,
        json=messages,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data")
    return data if isinstance(data, list) else []


def notify_followers(
    station: Stations,
    level: str,
    aqi: float,
    trend: str = WORSENING,
    copy_override: tuple[str, str] | None = None,
) -> Delivery:
    """Sends one notification about ``station`` to everyone following it."""
    delivery = Delivery()

    tokens = _tokens_following(station.station_code)
    if not tokens:
        logger.info("No registered tokens follow %s", station.station_code)
        return delivery

    for start in range(0, len(tokens), EXPO_BATCH_SIZE):
        batch = tokens[start : start + EXPO_BATCH_SIZE]
        messages = [
            _message(token, station, level, aqi, trend, copy_override)
            for token in batch
        ]
        tickets = _post_batch(messages)
        delivery.accepted += sum(1 for t in tickets if t.get("status") == "ok")
        delivery.cleared += _clear_dead_tokens(batch, tickets)
        # A 200 with fewer tickets than messages, or none at all, is not a
        # delivery: those messages were never accepted and there is no ticket
        # to check later, so they count as failures like any rejection does.
        delivery.retriable_failures += len(batch) - len(tickets[: len(batch)])
        delivery.retriable_failures += sum(
            1
            for ticket in tickets[: len(batch)]
            if ticket.get("status") != "ok" and not _is_dead(ticket)
        )

    return delivery


def catch_up_follower(installation: DeviceInstallation, station: Stations) -> bool:
    """Tells one installation how the air is at a station it has just followed.

    Why this exists: :class:`SensorAlertState` is per station, not per follower.
    Somebody who follows a sensor that is *already* over the threshold — and
    that some other device was warned about hours ago — matches no change, so
    the scheduled sender has nothing to say about it. They would hear nothing
    until the air got worse still, or recovered. That silence is worst in
    exactly the case the feature exists for: air that is bad right now.

    Deliberately one device and one message. It does not touch the station's
    state — neither the level path's nor a rule's — because that state is what
    every *other* follower's next notification is judged against, and advancing
    it here would suppress a real warning for all of them.

    An institution's own alert is consulted first and, when one is firing, its
    wording is what gets sent. Without that this catch-up would answer the
    question "is this air worth interrupting somebody for?" with the public
    thresholds only, and a sensor whose institution alerts from AQI 40 would
    stay silent for its newest follower while actively firing for everybody
    else — the leased sensor notifying *less* than a public one.

    Returns whether a message was accepted, and raises nothing the caller has
    to handle: a follow must succeed even when the push service does not.
    """
    if not is_configured():
        return False
    if not installation.push_token:
        return False
    if not station.is_station_on:
        return False

    latest = _latest_level(station)
    if latest is None:
        return False
    level, aqi = latest

    copy_override = _firing_rule_copy(station, aqi)
    # Only air worth interrupting somebody for. Following a healthy sensor is
    # not news, and a "the air is fine" push on every follow would be noise.
    # A firing institutional alert is that institution declaring this air worth
    # interrupting for, which is the judgement the level table cannot make.
    if copy_override is None and level not in ALERT_LEVELS:
        return False

    try:
        tickets = _post_batch(
            [
                _message(
                    installation.push_token,
                    station,
                    level,
                    aqi,
                    CATCH_UP,
                    copy_override,
                )
            ]
        )
    except requests.RequestException as error:
        # The follow itself already succeeded and is what the user asked for.
        # Losing the catch-up is a missed courtesy, not a failed action, and
        # the next real change at this station will reach them normally.
        logger.warning(
            "Catch-up push failed for %s on %s: %s",
            installation.installation_id,
            station.station_code,
            error,
        )
        return False

    accepted = sum(1 for ticket in tickets if ticket.get("status") == "ok")
    _clear_dead_tokens([installation.push_token], tickets)
    if accepted:
        SensorAlert.record(station.station_code, level, aqi, accepted, trend=CATCH_UP)
    return bool(accepted)


def _broadcast_station_codes(broadcast: PushBroadcast) -> list[str] | None:
    """Which stations a broadcast addresses, or ``None`` for every one of them.

    ``None`` rather than a list of every code because the two mean different
    things downstream: a platform-wide send takes every follower whatever they
    follow, and enumerating stations to reach them would silently drop the
    followers of a station the pipeline has since removed.
    """
    if broadcast.scope == PushBroadcast.SCOPE_ALL:
        return None
    if broadcast.scope == PushBroadcast.SCOPE_STATION:
        return [broadcast.station.station_code] if broadcast.station else []
    if broadcast.institution is None:
        return []
    stations = Stations.objects.filter(
        institution_contract__institution=broadcast.institution
    ).values_list("station_code", flat=True)
    return [code for code in stations if code]


def broadcast_tokens(broadcast: PushBroadcast) -> list[str]:
    """Push tokens for a broadcast's audience, deduplicated.

    Deduplication matters more here than on the per-station path: somebody
    following three of an institution's sensors is one person who should read
    one announcement, not three copies of it.
    """
    codes = _broadcast_station_codes(broadcast)

    installations = DeviceInstallation.objects.exclude(push_token="")
    if codes is None:
        installations = installations.filter(follows__isnull=False)
    else:
        if not codes:
            return []
        installations = installations.filter(follows__station_code__in=codes)

    # `order_by()` for the same reason as `_tokens_following`: the model's
    # default ordering would join `updated_at` into the DISTINCT and defeat it.
    return list(
        installations.order_by().values_list("push_token", flat=True).distinct()
    )


def send_broadcast(broadcast: PushBroadcast) -> Delivery:
    """Delivers one manual broadcast to its audience.

    The row already exists when this is called — it is the record that a send
    was attempted, and creating it first is what stops one announcement being
    sent twice. This fills in what the push service did with it.

    A failed batch is recorded rather than raised: a broadcast that reached
    most of its audience is not something to retry wholesale, since retrying
    would re-notify everyone the first attempt did reach.
    """
    delivery = Delivery()
    tokens = broadcast_tokens(broadcast)

    if not tokens:
        logger.info("Broadcast %s matched no registered tokens", broadcast.pk)
        return delivery

    message_base = {
        "title": broadcast.push_title,
        "body": broadcast.push_body,
        "sound": "default",
        "data": {
            # `screen`, with no `type` at all — the exact shape the shipped app
            # recognises as a general notification. Its `parseNotificationPayload`
            # requires `type === null` before it will read `screen`, and maps
            # anything else it does not know to `unknown`, which
            # `shouldPresentNotification` then suppresses in the foreground. A
            # `type: "broadcast"` was tried and silently hidden that way, and a
            # `type: "forecast"` would be hidden just the same.
            #
            # Not `sensor_alert` either: that routes a tap to one station's
            # screen, and an announcement may not be about a single station at
            # all.
            #
            # The consequence to accept: this is what the app understands
            # *today*, so it works on installs already out in the world. Giving
            # broadcasts a routing of their own means teaching respira-mobile a
            # new type first and waiting for that release to land.
            "screen": "forecast",
            "broadcast_id": broadcast.pk,
        },
    }

    for start in range(0, len(tokens), EXPO_BATCH_SIZE):
        batch = tokens[start : start + EXPO_BATCH_SIZE]
        messages = [{"to": token, **message_base} for token in batch]
        try:
            tickets = _post_batch(messages)
        except requests.RequestException as error:
            # One batch failing must not discard the batches already delivered.
            logger.error("Broadcast %s batch failed: %s", broadcast.pk, error)
            delivery.retriable_failures += len(batch)
            continue

        delivery.accepted += sum(1 for t in tickets if t.get("status") == "ok")
        delivery.cleared += _clear_dead_tokens(batch, tickets)
        delivery.retriable_failures += len(batch) - len(tickets[: len(batch)])
        delivery.retriable_failures += sum(
            1
            for ticket in tickets[: len(batch)]
            if ticket.get("status") != "ok" and not _is_dead(ticket)
        )

    PushBroadcast.objects.filter(pk=broadcast.pk).update(
        recipients=delivery.accepted, failures=delivery.retriable_failures
    )
    return delivery


# How far the air must fall back below a rule's threshold before that rule may
# fire again, as a fraction of the threshold. A sensor sitting near its
# threshold otherwise re-alerts on every scheduled run: at a threshold of 40,
# readings of 41, 39, 42 are three separate crossings.
#
# Proportional rather than a fixed number of AQI points, so it holds at
# whatever threshold an institution picks — 12% of 40 is a meaningful drop, and
# so is 12% of 150, where a fixed 5-point band would be within the noise.
REARM_FRACTION = 0.12


def rearm_threshold(threshold: int) -> float:
    """The level a firing rule must fall under before it may alert again."""
    return threshold * (1 - REARM_FRACTION)


def rule_transition(is_firing: bool, aqi: float, threshold: int) -> str | None:
    """What this reading does to a rule: ``"fire"``, ``"rearm"``, or nothing.

    One place to ask, so the sender and the dry run cannot answer differently.
    Firing is a strict crossing of the threshold; rearming needs the fall all
    the way through the band below it, never merely back under the threshold.
    """
    if not is_firing and aqi > threshold:
        return "fire"
    if is_firing and aqi < rearm_threshold(threshold):
        return "rearm"
    return None


def _firing_rule_copy(station: Stations, aqi: float) -> tuple[str, str] | None:
    """The wording of the institutional alert this station is currently over.

    For :func:`catch_up_follower`, which has one device to tell and needs to
    know what the followers who were already here have been told.

    Judged on the reading rather than on ``is_firing``: a new follower has to
    hear about air that is over the threshold right now, and the state flag
    answers a different question — whether the *others* have been notified
    already, which for this one device is not relevant. Reading the flag would
    also make the catch-up depend on the scheduled run having happened yet.

    The *highest* matching threshold wins, and deliberately only one is sent.
    An institution may configure escalating advice — a caution at one AQI, an
    evacuation at a higher one — and the followers who were already here
    received those one at a time as the air crossed each in turn. Somebody
    arriving mid-episode cannot be given that history retroactively, so they
    get the one that describes the air as it is now: the most severe alert it
    is currently over. Sending every matching alert instead would open a
    catch-up with a string of notifications, the newest follower being the only
    person interrupted several times for a single reading.

    ``station_id`` is safe to match on here (unlike in stored rows) because it
    is read and used within the same request.
    """
    rule = (
        InstitutionAlertRule.objects.filter(
            is_active=True, station_id=station.id, threshold__lt=aqi
        )
        .order_by("-threshold")
        .first()
    )
    return rule.message_for(station.name) if rule else None


def evaluate_rule(rule: InstitutionAlertRule) -> Delivery | None:
    """Evaluates one alert against its sensor's latest reading, and notifies.

    The single place a rule is judged, so the scheduled run and the immediate
    evaluation on save cannot drift apart — including the state locking, which
    is what stops the two firing the same alert twice if they overlap.

    Returns the delivery when a notification was attempted, and ``None`` when
    there was nothing to do: an inactive rule, a station the pipeline dropped
    or turned off, no reading to judge, an unchanged state, or a rearm (which
    is deliberately silent — see :func:`send_institution_alerts`).

    Raises ``requests.RequestException`` if the push service is unreachable;
    callers decide whether that is fatal.
    """
    if not rule.is_active:
        return None

    station = rule.station
    if station is None or not station.station_code or not station.is_station_on:
        return None

    latest = _latest_level(station)
    if latest is None:
        return None
    level, aqi = latest

    with transaction.atomic():
        # Held for the whole send. Two overlapping evaluations — two scheduled
        # runs, or a run and a save — would otherwise both read an idle rule,
        # both decide to notify, and both call Expo before either wrote back.
        state = InstitutionAlertRuleState.lock(rule.id)
        transition = rule_transition(state.is_firing, aqi, rule.threshold)

        if transition is None:
            state.last_aqi = aqi
            state.save(update_fields=["last_aqi", "updated_at"])
            return None

        if transition == "rearm":
            # Silent, but recorded: clearing the flag is what lets the next
            # genuine crossing notify instead of being suppressed forever.
            state.is_firing = False
            state.last_aqi = aqi
            state.save(update_fields=["is_firing", "last_aqi", "updated_at"])
            return None

        delivery = notify_followers(
            station,
            level,
            aqi,
            WORSENING,
            copy_override=rule.message_for(station.name),
        )

        if delivery.accepted:
            SensorAlert.record(station.station_code, level, aqi, delivery.accepted)
            InstitutionAlert.objects.create(
                institution=rule.institution,
                station=station,
                aqi_value=aqi,
                # Copied, not referenced: editing the rule's threshold later
                # must not rewrite what this event fired at. The `rule` link is
                # for grouping the history under its rule, not for reading the
                # threshold back.
                alert_threshold=rule.threshold,
                rule=rule,
            )

        if delivery.delivered:
            state.is_firing = True
            state.last_aqi = aqi
            state.last_notified_at = timezone.now()
            state.save(
                update_fields=[
                    "is_firing",
                    "last_aqi",
                    "last_notified_at",
                    "updated_at",
                ]
            )
        else:
            # Left idle on purpose, so the next run retries this crossing
            # rather than treating followers as warned.
            state.last_aqi = aqi
            state.save(update_fields=["last_aqi", "updated_at"])

        return delivery


def send_institution_alerts(dry_run: bool = False) -> SendResult:
    """Evaluates every active institutional rule and notifies on the crossings.

    The configurable half of the feature: where :func:`send_sensor_alerts`
    applies one fixed table of AQI levels to every station on the platform,
    this applies each institution's own threshold and wording to its own
    sensor.

    A rule notifies once per episode. It fires when the air first exceeds its
    threshold and then stays quiet — however many runs the episode lasts —
    until the air falls back through :func:`rearm_threshold`. That is what
    stops a sensor hovering at its threshold from notifying on every run.

    Rearming is silent. An institution's threshold is its own operational
    trigger rather than a health level, so there is no meaningful all-clear to
    announce; the recovery notifications belong to the level path, which knows
    what the air actually became.
    """
    result = SendResult()

    rules = (
        InstitutionAlertRule.objects.filter(is_active=True)
        .select_related("institution", "station")
        .order_by("institution_id", "threshold")
    )

    for rule in rules:
        station = rule.station
        if station is None or not station.station_code:
            continue
        if not station.is_station_on:
            continue

        latest = _latest_level(station)
        if latest is None:
            continue
        level, aqi = latest

        result.considered += 1

        if dry_run:
            state = InstitutionAlertRuleState.objects.filter(rule=rule).first()
            firing = state.is_firing if state else False
            if rule_transition(firing, aqi, rule.threshold) == "fire":
                result.alerted_stations += 1
            continue

        try:
            delivery = evaluate_rule(rule)
            if delivery is None:
                # Nothing to notify: unchanged, or a silent rearm. Either way
                # `evaluate_rule` has already recorded what it saw.
                continue
        except requests.RequestException as error:
            # One rule's delivery failing must not stop the others, and the
            # state is deliberately left untouched so the next run retries it.
            message = f"rule {rule.id} ({station.station_code}): {error}"
            logger.error("Institution alert delivery failed for %s", message)
            result.errors.append(message)
            continue

        result.tokens_cleared += delivery.cleared

        if not delivery.delivered:
            message = (
                f"rule {rule.id} ({station.station_code}): "
                f"{delivery.retriable_failures} message(s) rejected, none "
                "accepted; will retry"
            )
            logger.warning("Institution alert not accepted for %s", message)
            result.errors.append(message)
            continue

        result.alerted_stations += 1
        result.messages_sent += delivery.accepted

    return result


def send_sensor_alerts(dry_run: bool = False) -> SendResult:
    """Checks every followed station and notifies the ones whose air moved.

    Both directions: a station that worsened warns its followers, and one that
    improved while an episode was open tells them so. Which of the two, if
    either, is :func:`notification_for`.

    Only stations somebody actually follows are read: with no followers there
    is no one to notify, and the reading would be wasted work.

    Every station that is read has its level written to
    :class:`SensorAlertState`, notified or not — that record of the safe
    readings is what lets the sender tell a station that has recovered from one
    still sitting at the level it last warned about.
    """
    result = SendResult()

    followed_codes = (
        DeviceFollower.objects.values_list("station_code", flat=True)
        .distinct()
        .order_by()
    )

    for station_code in followed_codes:
        station = Stations.objects.filter(station_code=station_code).first()
        if station is None:
            # The pipeline dropped it. The follows survive so the app can tell
            # the user, but there is nothing to read.
            continue
        if not station.is_station_on:
            continue

        latest = _latest_level(station)
        if latest is None:
            continue
        level, aqi = latest

        result.considered += 1

        if dry_run:
            state = SensorAlertState.objects.filter(station_code=station_code).first()
            trend = notification_for(level, state.last_alerted_level if state else "")
            if trend == WORSENING:
                result.alerted_stations += 1
            elif trend == IMPROVING:
                result.recovered_stations += 1
            continue

        try:
            with transaction.atomic():
                # Held for the whole send. Two overlapping scheduled runs would
                # otherwise both read the same state, both decide to notify and
                # both call Expo before either wrote anything back — the same
                # message twice on one phone.
                state = SensorAlertState.lock(station_code)
                trend = notification_for(level, state.last_alerted_level)
                if trend is None:
                    # Still recorded: `last_level` is the record of the safe
                    # readings, which is what tells a station that recovered
                    # from one still sitting where it was last warned about.
                    _remember(state, level, notified=False)
                    continue

                delivery = notify_followers(station, level, aqi, trend)
                if delivery.accepted:
                    SensorAlert.record(
                        station_code,
                        level,
                        aqi,
                        delivery.accepted,
                        trend=trend,
                    )
                _remember(state, level, notified=delivery.delivered)
        except requests.RequestException as error:
            # One station's delivery failing must not stop the others, and the
            # state is deliberately left untouched so the next run retries it.
            message = f"{station_code}: {error}"
            logger.error("Push delivery failed for %s", message)
            result.errors.append(message)
            continue

        result.tokens_cleared += delivery.cleared

        if not delivery.delivered:
            # Expo answered, but for nobody. Leaving `last_alerted_level` where
            # it was is what makes the next run try this level again instead of
            # treating followers as warned.
            message = (
                f"{station_code} ({trend}): {delivery.retriable_failures} "
                "message(s) rejected, none accepted; will retry"
            )
            logger.warning("Push delivery not accepted for %s", message)
            result.errors.append(message)
            continue

        if trend == WORSENING:
            result.alerted_stations += 1
        else:
            result.recovered_stations += 1
        result.messages_sent += delivery.accepted

    return result


def is_configured() -> bool:
    """Whether alerts should be attempted at all in this environment."""
    return bool(getattr(settings, "SENSOR_ALERTS_ENABLED", False))
