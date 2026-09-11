"""Client for the AirGradient public API.

The institutional raw export reads its measurements straight from AirGradient
rather than from ``station_readings_gold``, so an institution downloads every
field its own sensor reports — CO2, VOC/NOx indices, temperature, humidity,
battery — instead of the particulate subset the warehouse keeps.

Two things the warehouse did for us have to be done here instead:

* **Pagination.** ``/measures/past`` caps a request at 10 days, so a longer
  range is walked in windows and concatenated.
* **AQI.** AirGradient reports concentrations, not indices. ``aqi.py`` holds the
  breakpoint tables, mirrored from the pipeline's ``dbt/macros/aqi.sql`` so a
  downloaded number matches the one the dashboard shows.

A station is addressed by its AirGradient ``locationId``, recovered from the
pipeline's ``station_code`` (``respira_<locationId>``) — the same natural key
dbt builds in ``stg_respira_measurements``.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any, Iterator

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_ROOT = "https://api.airgradient.com/public/api/v1"

# The API rejects a wider window; see the `from`/`to` parameters in its docs.
MAX_WINDOW = timedelta(days=10)

# Per-request timeouts (connect, read). An export walks several windows in one
# HTTP request, so a hung upstream call must fail fast rather than sit on the
# worker until the browser gives up.
TIMEOUT = (5, 30)

# How many windows are in flight at once. Enough that a year of history costs a
# few seconds rather than a minute, low enough to stay a polite client: the
# provider serves every institution's export from the same account.
MAX_CONCURRENCY = 8

STATION_CODE_PREFIX = "respira_"


class AirGradientError(Exception):
    """Raised when the upstream API cannot serve a range."""


def location_id_for_station(station) -> int:
    """The AirGradient ``locationId`` behind a gold ``stations`` row.

    ``station_code`` is the pipeline's stable natural key; for sensors ingested
    from AirGradient it is ``respira_<locationId>``. Stations from the other
    networks (FIUNA, MADES) carry a different prefix and have no AirGradient
    identity at all, which is a configuration error rather than a missing value.
    """
    code = (getattr(station, "station_code", "") or "").strip()
    if not code.startswith(STATION_CODE_PREFIX):
        raise AirGradientError(
            f"Station {station!s} is not an AirGradient sensor "
            f"(station_code={code!r})."
        )
    suffix = code[len(STATION_CODE_PREFIX) :]
    if not suffix.isdigit():
        raise AirGradientError(
            f"Station {station!s} has a malformed AirGradient code: {code!r}."
        )
    return int(suffix)


def _token() -> str:
    token = getattr(settings, "AIRGRADIENT_API_TOKEN", "") or ""
    if not token:
        raise AirGradientError(
            "AIRGRADIENT_API_TOKEN is not configured; the raw export cannot "
            "reach the sensor API."
        )
    return token


def _stamp(moment: datetime) -> str:
    """ISO 8601 basic format in UTC, e.g. ``20220328T120500Z``."""
    return moment.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _windows(start: datetime, end: datetime) -> Iterator[tuple[datetime, datetime]]:
    """Split ``[start, end)`` into windows the API will accept.

    Windows are half-open and never overlap, so a reading on a boundary is
    fetched exactly once and the concatenated series has no duplicates.
    """
    cursor = start
    while cursor < end:
        stop = min(cursor + MAX_WINDOW, end)
        yield cursor, stop
        cursor = stop


def location_type(location_id: int, *, session=None) -> str:
    """The sensor's placement ("outdoor"/"indoor"), or "" when unknown.

    Only the ``current`` listing carries it — ``past`` rows do not — so this is
    one extra call, and a failure is not worth losing an export over: the column
    it fills is descriptive, so an empty value is an acceptable outcome.
    """
    try:
        http = session or requests.Session()
        response = http.get(
            f"{API_ROOT}/locations/measures/current",
            params={"token": _token()},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (AirGradientError, requests.RequestException, ValueError):
        logger.exception("Could not read location type for %s", location_id)
        return ""

    if not isinstance(payload, list):
        return ""
    for entry in payload:
        if entry.get("locationId") == location_id:
            return entry.get("locationType") or ""
    return ""


@dataclass
class FetchResult:
    """Measurements for a range, plus what went wrong while collecting them."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    failed_windows: int = 0


def _fetch_window(
    http, location_id: int, token: str, window: tuple[datetime, datetime]
) -> list[dict[str, Any]] | None:
    """One window's measurements, or ``None`` when it could not be fetched."""
    window_start, window_end = window
    params = {
        "from": _stamp(window_start),
        "to": _stamp(window_end),
        "token": token,
    }
    url = f"{API_ROOT}/locations/{location_id}/measures/past"
    try:
        response = http.get(url, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        # `exception` rather than `error`: a failed window is rare enough that
        # the traceback is worth keeping, and the token lives in `params`, which
        # is not part of the logged message.
        logger.exception(
            "AirGradient window failed for location %s (%s to %s)",
            location_id,
            params["from"],
            params["to"],
        )
        return None

    if not isinstance(payload, list):
        logger.error(
            "AirGradient returned %s, not a list, for location %s",
            type(payload).__name__,
            location_id,
        )
        return None

    return payload


def fetch_past_measures(
    location_id: int, start: datetime, end: datetime, *, session=None
) -> FetchResult:
    """Every measurement AirGradient holds for ``location_id`` in ``[start, end)``.

    Rows come back in ascending timestamp order, deduplicated on the timestamp:
    the API buckets at 5 or 60 minutes depending on the age of the data, and a
    range spanning that change can otherwise repeat an hour.

    Windows are fetched concurrently. They are independent of each other, and a
    year of history is 37 of them: serially that is a minute of latency, which
    no browser will wait through. Concurrency is capped so a long export cannot
    open an unbounded number of sockets against the provider.

    A window that fails is logged and skipped rather than failing the whole
    export — a partial spreadsheet covering 11 of 12 months is more useful to an
    institution than an error page, and the caller reports the gap.
    """
    token = _token()
    result = FetchResult()
    windows = list(_windows(start, end))
    if not windows:
        return result

    payloads: list[list[dict[str, Any]] | None]
    if len(windows) == 1:
        payloads = [
            _fetch_window(session or requests.Session(), location_id, token, windows[0])
        ]
    else:
        # A `Session` is not documented as thread-safe, so each worker gets its
        # own — except when the caller supplied one, which is how tests inject a
        # stub and must keep seeing every call.
        local = threading.local()

        def fetch(window):
            if session is not None:
                return _fetch_window(session, location_id, token, window)
            http = getattr(local, "session", None)
            if http is None:
                http = local.session = requests.Session()
            return _fetch_window(http, location_id, token, window)

        with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENCY, len(windows))) as pool:
            # `map` keeps results in window order, so the dedup below always
            # prefers the earlier window's copy of a shared timestamp and the
            # output does not depend on which request finished first.
            payloads = list(pool.map(fetch, windows))

    seen: set[str] = set()
    for payload in payloads:
        if payload is None:
            result.failed_windows += 1
            continue
        for row in payload:
            stamp = row.get("timestamp")
            if not stamp or stamp in seen:
                continue
            seen.add(stamp)
            result.rows.append(row)

    result.rows.sort(key=lambda row: row["timestamp"])
    return result
