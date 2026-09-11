"""File exports for the institutional dashboard (RES-328).

Two downloads, both scoped to the caller's own institution:

* a monthly PDF report, summarising one calendar month, built from
  ``station_readings_gold`` — the same readings the dashboard aggregates, so a
  number in a report can always be traced back to the panel it came from;
* a raw CSV export of every reading in a date range, read live from the
  AirGradient API (see ``airgradient.py``).

The raw export deliberately bypasses the warehouse: gold keeps only the
particulate columns the forecast needs, while the sensor also reports CO2,
temperature, humidity and VOC/NOx indices, and institutions asked for all of it.

It reproduces AirGradient's own export format byte for byte — their column
names and order, their row order, their timestamp formats, a UTF-8 BOM — so a
file downloaded from the panel and one downloaded from AirGradient's portal can
be used interchangeably, and an institution already working with theirs does not
have to rewrite anything. Deviating would make the panel's file the odd one out,
so ``_CSV_COLUMNS`` is a specification, not a preference: it is worth checking
against a fresh AirGradient export before changing it.

Kept in its own module rather than in ``views.py``: the PDF and spreadsheet
machinery has nothing to do with the JSON API, and isolating it keeps that file
reviewable.

``TIME_ZONE`` is UTC, but institutions read their data in Paraguayan local time,
so every timestamp rendered into a file is converted to ``REPORT_TIME_ZONE``
first. The API's JSON keeps sending UTC; only these human-facing files localise.
"""

from __future__ import annotations

import csv
import io
import logging
import zoneinfo
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from typing import Any

from dateutil.relativedelta import relativedelta
from django.db.models import Avg, Count, Max, Min
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .airgradient import (
    AirGradientError,
    fetch_past_measures,
    location_id_for_station,
    location_type,
)
from .aqi import AQI_LEVELS, classify_aqi
from .models import ActionLog, StationReadingsGold, get_institution_for_user
from .permissions import IsInstitutionUser

logger = logging.getLogger(__name__)

REPORT_TIME_ZONE = zoneinfo.ZoneInfo("America/Asuncion")

# Palette from the frontend's Tailwind config, so a report looks like the panel
# it was downloaded from.
BRAND_INK = colors.HexColor("#1a1a1a")
BRAND_GRAY = colors.HexColor("#535353")
BRAND_RULE = colors.HexColor("#DBD3D0")
BRAND_GREEN = colors.HexColor("#4B7A3D")
BRAND_BASE = colors.HexColor("#F0ECEA")

AQI_BAND_COLORS = {
    "good": colors.HexColor("#AFFAAF"),
    "moderate": colors.HexColor("#FFEB7F"),
    "unhealthy_sensitive": colors.HexColor("#FBC189"),
    "unhealthy": colors.HexColor("#F27474"),
    "very_unhealthy": colors.HexColor("#B179B6"),
    "hazardous": colors.HexColor("#98334F"),
}

# A guard, not a product decision: the sensor API serves 10 days per call, so an
# unbounded range would fan out into hundreds of upstream requests inside one
# HTTP response. A year of 5-minute buckets is ~105k rows, which a browser still
# downloads happily; callers past that are told to narrow the range rather than
# being handed a truncated file.
MAX_EXPORT_DAYS = 366


# --- shared helpers ---------------------------------------------------------


def _contract_for_request(request):
    """The caller's contract, or 404 when their institution has no sensor.

    Mirrors the dashboard endpoint: an institution with no contract is a real
    stage of onboarding, reported the same way in both places.
    """
    institution = get_institution_for_user(request.user)
    contract = getattr(institution, "contract", None)
    if contract is None:
        raise NotFound("This institution does not have an assigned sensor.")
    return institution, contract


def _localise(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt_timezone.utc)
    return value.astimezone(REPORT_TIME_ZONE)


def _parse_month(raw: str | None) -> date:
    """The month to report on, defaulting to the last *complete* one.

    Defaulting to the current month would produce a report that changes every
    time it is downloaded; the previous month is closed and final.
    """
    if not raw:
        today = timezone.now().astimezone(REPORT_TIME_ZONE).date()
        return (today.replace(day=1) - relativedelta(months=1)).replace(day=1)
    try:
        return datetime.strptime(raw, "%Y-%m").date().replace(day=1)
    except ValueError:
        raise ValidationError(
            {"month": "Expected a month in YYYY-MM format, e.g. 2026-07."}
        )


def _available_months(station_id: int, contract_start: date) -> list[date]:
    """The months the station actually recorded readings in, oldest first.

    Drives the month selector: offering a month with no readings would hand the
    institution an empty report and no explanation. Months before the contract
    started are excluded even when the station has older readings — those
    predate the institution's relationship with the sensor.
    """
    rows = (
        StationReadingsGold.objects.filter(
            station_id=station_id, aqi_pm2_5__isnull=False
        )
        .annotate(month=TruncMonth("date_utc"))
        .values("month")
        .annotate(readings=Count("id"))
        .order_by("month")
    )
    first_of_contract = contract_start.replace(day=1)
    months = []
    for row in rows:
        month = row["month"]
        if month is None:
            continue
        month = month.date() if isinstance(month, datetime) else month
        month = month.replace(day=1)
        if month >= first_of_contract:
            months.append(month)
    return months


def _parse_date(raw: str | None, field: str) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(
            {field: "Expected a date in YYYY-MM-DD format, e.g. 2026-07-01."}
        )


def _range_bounds(start: date, end_exclusive: date) -> tuple[datetime, datetime]:
    """Local-midnight bounds as aware datetimes, for filtering UTC timestamps."""
    return (
        datetime.combine(start, time.min, tzinfo=REPORT_TIME_ZONE),
        datetime.combine(end_exclusive, time.min, tzinfo=REPORT_TIME_ZONE),
    )


def _readings(station_id: int, start: datetime, end: datetime):
    return StationReadingsGold.objects.filter(
        station_id=station_id,
        date_utc__gte=start,
        date_utc__lt=end,
    )


def _filename(prefix: str, institution, suffix: str, extension: str) -> str:
    name = slugify(institution.display_name or institution.legal_name) or "institucion"
    return f"{prefix}-{name}-{suffix}.{extension}"


def _airgradient_filename(station, start: date, end: date) -> str:
    """A filename shaped like AirGradient's own export.

    Theirs reads ``export_Encarnación_-_Costanera_10m_2026-08-01_2026-08-31.csv``
    — the location name with spaces as underscores (accents intact), the bucket
    width, then the range. The bucket is reported by the API per row rather than
    chosen by us, and mixed widths are possible across a long range, so the
    interval segment is omitted rather than stated wrongly.
    """
    name = (station.name or "").strip() or "sensor"
    # Their file keeps the accents and only swaps spaces; `_attachment` sends an
    # RFC 5987 header, so non-ASCII survives the download.
    name = name.replace(" ", "_")
    return f"export_{name}_{start.isoformat()}_{end.isoformat()}.csv"


def _attachment(content: bytes, filename: str, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    # Both forms: the plain one for older clients, the RFC 5987 one so accented
    # institution names survive. The frontend reads either.
    response["Content-Disposition"] = (
        f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename}"
    )
    response["Content-Length"] = str(len(content))
    return response


# --- monthly PDF report -----------------------------------------------------


def _month_statistics(station_id: int, month_start: date) -> dict[str, Any]:
    month_end = month_start + relativedelta(months=1)
    start, end = _range_bounds(month_start, month_end)

    readings = _readings(station_id, start, end).filter(aqi_pm2_5__isnull=False)

    totals = readings.aggregate(
        average=Avg("aqi_pm2_5"),
        highest=Max("aqi_pm2_5"),
        lowest=Min("aqi_pm2_5"),
        measurements=Count("id"),
    )

    daily = list(
        readings.annotate(day=TruncDate("date_utc"))
        .values("day")
        .annotate(average=Avg("aqi_pm2_5"), highest=Max("aqi_pm2_5"))
        .order_by("day")
    )

    # Categories are counted per *day*, on the daily average — the same number
    # the dashboard's history chart plots, so the two never disagree.
    distribution: dict[str, int] = {level["key"]: 0 for level in AQI_LEVELS}
    for row in daily:
        level = classify_aqi(row["average"])
        if level is not None:
            distribution[level["key"]] += 1

    return {
        "month_start": month_start,
        "month_end": month_end,
        "daily": daily,
        "distribution": distribution,
        **totals,
    }


def _paragraph_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "RespiraTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            alignment=TA_LEFT,
            textColor=BRAND_INK,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "RespiraSubtitle",
            parent=base["Normal"],
            fontSize=10.5,
            leading=15,
            textColor=BRAND_GRAY,
        ),
        "heading": ParagraphStyle(
            "RespiraHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=BRAND_INK,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "RespiraBody",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13,
            textColor=BRAND_INK,
        ),
        "muted": ParagraphStyle(
            "RespiraMuted",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=BRAND_GRAY,
        ),
    }


_TABLE_BASE = TableStyle(
    [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_GRAY),
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BASE),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, BRAND_RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]
)

_MONTH_NAMES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def _month_label(value: date) -> str:
    return f"{_MONTH_NAMES[value.month - 1]} de {value.year}"


def _aqi(value: float | None) -> str:
    return "—" if value is None else str(round(value))


def _month_actions(institution, month_start: date):
    """The institution's own action log for the month, oldest first.

    Reads the same rows the dashboard lists, so the report is a record of what
    the institution did about the air it measured — the two halves of the month
    in one document, rather than a page of numbers with no response attached.
    """
    month_end = month_start + relativedelta(months=1)
    start, end = _range_bounds(month_start, month_end)
    return list(
        ActionLog.objects.filter(
            institution=institution, timestamp__gte=start, timestamp__lt=end
        )
        .select_related("alert")
        .order_by("timestamp", "id")
    )


def _generated_note(station_name: str, styles) -> Paragraph:
    stamp = timezone.now().astimezone(REPORT_TIME_ZONE).strftime("%d/%m/%Y %H:%M")
    return Paragraph(
        f"Generado por Proyecto Respira el {stamp}. Los valores son promedios "
        "diarios del índice AQI para PM2.5 medido por el sensor "
        f"{station_name}.",
        styles["muted"],
    )


def _actions_flow(actions, styles) -> list[Any]:
    """The month's action log, as report flowables."""
    flow: list[Any] = [
        Spacer(1, 6 * mm),
        Paragraph("Acciones registradas", styles["heading"]),
    ]

    if not actions:
        flow.append(
            Paragraph(
                "La institución no registró acciones en este período.",
                styles["body"],
            )
        )
        flow.append(Spacer(1, 4 * mm))
        return flow

    rows = [["Fecha", "Acción", "Alerta"]]
    for entry in actions:
        moment = _localise(entry.timestamp)
        alert = entry.alert
        rows.append(
            [
                moment.strftime("%d/%m %H:%M") if moment else "—",
                # Wrapped in a Paragraph so a long note flows over several
                # lines instead of overflowing its cell.
                Paragraph(entry.note, styles["body"]),
                f"AQI {round(alert.aqi_value)}" if alert else "—",
            ]
        )

    flow += [
        Table(
            rows,
            colWidths=[28 * mm, 118 * mm, 28 * mm],
            style=_TABLE_BASE,
            repeatRows=1,
        ),
        Spacer(1, 4 * mm),
    ]
    return flow


def build_monthly_report_pdf(institution, contract, stats, threshold, actions) -> bytes:
    styles = _paragraph_styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Reporte mensual — {institution}",
        author="Proyecto Respira",
    )

    station_name = contract.station.name
    flow: list[Any] = [
        Paragraph("Reporte mensual de calidad del aire", styles["title"]),
        Paragraph(
            f"{institution} · Sensor {station_name} · {_month_label(stats['month_start'])}",
            styles["subtitle"],
        ),
        Spacer(1, 4 * mm),
    ]

    if not stats["daily"]:
        # No readings does not mean nothing happened: an institution may still
        # have logged actions this month, so the report keeps that section
        # rather than coming out empty.
        flow.append(
            Paragraph(
                "El sensor no registró mediciones en este período.", styles["body"]
            )
        )
        flow += _actions_flow(actions, styles)
        flow.append(_generated_note(station_name, styles))
        document.build(flow)
        return buffer.getvalue()

    days_over = (
        sum(
            1 for row in stats["daily"] if row["average"] and row["average"] > threshold
        )
        if threshold
        else None
    )

    summary_rows = [
        ["Indicador", "Valor"],
        ["Días con mediciones", str(len(stats["daily"]))],
        ["Mediciones registradas", str(stats["measurements"])],
        ["AQI promedio del mes", _aqi(stats["average"])],
        ["AQI máximo", _aqi(stats["highest"])],
        ["AQI mínimo", _aqi(stats["lowest"])],
    ]
    if days_over is not None:
        summary_rows.append(
            [f"Días sobre el umbral de alerta ({threshold})", str(days_over)]
        )

    flow += [
        Paragraph("Resumen", styles["heading"]),
        Table(summary_rows, colWidths=[95 * mm, 79 * mm], style=_TABLE_BASE),
        Paragraph("Días por categoría", styles["heading"]),
    ]

    distribution_rows = [["Categoría", "Rango AQI", "Días"]]
    band_styles = list(_TABLE_BASE.getCommands())
    lower = 0
    for index, level in enumerate(AQI_LEVELS, start=1):
        upper = level["max"]
        distribution_rows.append(
            [
                level["label"].capitalize(),
                f"{lower}–{upper}" if upper is not None else f"{lower}+",
                str(stats["distribution"][level["key"]]),
            ]
        )
        band_styles.append(
            ("BACKGROUND", (0, index), (0, index), AQI_BAND_COLORS[level["key"]])
        )
        lower = (upper or lower) + 1

    flow += [
        Table(
            distribution_rows,
            colWidths=[95 * mm, 45 * mm, 34 * mm],
            style=TableStyle(band_styles),
        ),
        PageBreak(),
        Paragraph("Detalle diario", styles["heading"]),
    ]

    daily_rows = [["Fecha", "AQI promedio", "AQI máximo", "Categoría"]]
    for row in stats["daily"]:
        # Named apart from the `level` bound by the distribution loop above:
        # that one is always an AqiLevel, this one is nullable when a day has
        # no classifiable average.
        day_level = classify_aqi(row["average"])
        daily_rows.append(
            [
                row["day"].strftime("%d/%m/%Y"),
                _aqi(row["average"]),
                _aqi(row["highest"]),
                day_level["label"].capitalize() if day_level else "—",
            ]
        )

    flow.append(
        Table(
            daily_rows,
            colWidths=[38 * mm, 38 * mm, 38 * mm, 60 * mm],
            style=_TABLE_BASE,
            repeatRows=1,
        )
    )
    flow += _actions_flow(actions, styles)
    flow.append(_generated_note(station_name, styles))

    document.build(flow)
    return buffer.getvalue()


@extend_schema(
    tags=["Institutional Dashboard"],
    summary="Download the institution's monthly air-quality report",
    description=(
        "A PDF summarising one calendar month for the institution's own "
        "sensor: totals, days per AQI category and a day-by-day table. "
        "Defaults to the last complete month, since the current one would "
        "change between downloads. Returns 404 when the institution has no "
        "assigned sensor."
    ),
    parameters=[
        OpenApiParameter(
            name="month",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Month to report on, as YYYY-MM. Defaults to last month.",
        )
    ],
    responses={(200, "application/pdf"): OpenApiTypes.BINARY},
)
class InstitutionMonthlyReportView(APIView):
    permission_classes = [IsAuthenticated, IsInstitutionUser]
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        institution, contract = _contract_for_request(request)
        month_start = _parse_month(request.query_params.get("month"))

        # A month that has not happened yet is a mistake, not an empty report:
        # answering 200 with a blank PDF looks like the sensor recorded nothing,
        # which is a different and much more alarming statement.
        today = timezone.now().astimezone(REPORT_TIME_ZONE).date()
        if month_start > today.replace(day=1):
            raise ValidationError(
                {"month": "That month has not started yet; pick an earlier one."}
            )

        alert_config = getattr(institution, "alert_config", None)
        threshold = (
            alert_config.alert_threshold
            if alert_config and alert_config.is_enabled
            else None
        )

        stats = _month_statistics(contract.station_id, month_start)
        actions = _month_actions(institution, month_start)
        pdf = build_monthly_report_pdf(institution, contract, stats, threshold, actions)

        return _attachment(
            pdf,
            _filename(
                "reporte-mensual", institution, month_start.strftime("%Y-%m"), "pdf"
            ),
            "application/pdf",
        )


@extend_schema(
    tags=["Institutional Dashboard"],
    summary="List the months the institution has a report for",
    description=(
        "The months the institution's own sensor recorded readings in, oldest "
        "first, each as `YYYY-MM` with its reading count. Drives the month "
        "selector: a month absent from this list would produce an empty "
        "report. Scoped to the caller's institution and to months on or after "
        "its contract start. Returns 404 when the institution has no assigned "
        "sensor."
    ),
    responses={200: OpenApiTypes.OBJECT},
)
class InstitutionReportMonthsView(APIView):
    permission_classes = [IsAuthenticated, IsInstitutionUser]
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        _institution, contract = _contract_for_request(request)
        months = _available_months(contract.station_id, contract.start_date)
        return Response(
            {
                "months": [
                    {"month": month.strftime("%Y-%m"), "label": _month_label(month)}
                    for month in months
                ],
                # The one the panel should preselect: the most recent complete
                # month that actually has data, falling back to the newest month
                # available when the current one is all there is.
                "default": _default_month(months).strftime("%Y-%m") if months else None,
            }
        )


def _default_month(months: list[date]) -> date:
    """The month a freshly opened selector should show.

    Prefers the newest *complete* month, matching the report endpoint's own
    default — a report for a month still in progress changes between downloads.
    """
    if not months:
        raise ValueError("no months available")
    today = timezone.now().astimezone(REPORT_TIME_ZONE).date().replace(day=1)
    complete = [month for month in months if month < today]
    return complete[-1] if complete else months[-1]


# --- raw CSV export ---------------------------------------------------------

# The column set AirGradient's own portal exports, in its order and with its
# labels, so a file downloaded here opens interchangeably with one downloaded
# from them. Note the micro sign: their header uses U+03BC (GREEK SMALL LETTER
# MU), not U+00B5 (MICRO SIGN), and a diffing tool would flag the difference.
#
# Three of their columns cannot be filled from the public API and are written
# empty rather than guessed: "Location Group" and "Place Open" are portal-side
# metadata the API never returns, and "TVOC (ppb)" is empty in their own export
# too (the sensor reports only the index). "Heat Index (°C)" is theirs to
# compute — see `_HEAT_INDEX_NOTE` below.
_CSV_COLUMNS: list[str] = [
    "Location ID",
    "Location Name",
    "Location Group",
    "Location Type",
    "Sensor ID",
    "Place Open",
    "Local Date/Time",
    "UTC Date/Time",
    "# of aggregated records",
    "PM2.5 (μg/m³) raw",
    "PM2.5 (μg/m³) corrected",
    "0.3μm particle count",
    "CO2 (ppm) raw",
    "CO2 (ppm) corrected",
    "Temperature (°C) raw",
    "Temperature (°C) corrected",
    "Heat Index (°C)",
    "Humidity (%) raw",
    "Humidity (%) corrected",
    "TVOC (ppb)",
    "TVOC index",
    "NOX index",
    "PM1 (μg/m³)",
    "PM10 (μg/m³)",
]

# "Heat Index (°C)" is left empty on purpose. AirGradient's values match neither
# the NWS/Rothfusz heat index nor Steadman's apparent temperature (checked
# against 2789 rows of their own export: best fit still missed by up to 5.5 °C,
# and their figure can sit below the dry-bulb temperature, which Rothfusz never
# does). Writing a plausible-looking number that disagreed with theirs would be
# worse than leaving the cell blank, so the column is kept for shape and left
# for them to fill.
_HEAT_INDEX_NOTE = "not derivable from the public API"

def _number(value: Any) -> Any:
    """Coerce an API value to a real number.

    AirGradient sends some fields as strings (``batteryVoltage`` is ``"10.40"``,
    ``datapoints`` is ``"2"``); left as text they sort and chart wrongly.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        # `Z` is not accepted by `fromisoformat` before 3.11.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _stamp_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse each row's timestamp once, into ``_moment``."""
    for row in rows:
        row["_moment"] = _parse_timestamp(row.get("timestamp"))
    return rows


def _csv_value(value: Any) -> str:
    """Render a value the way AirGradient's own export does.

    Whole numbers lose their decimal point (their CO2 column is ``447``, not
    ``447.0``) and missing values are written as an empty field rather than as
    ``None``.
    """
    number = _number(value)
    if number is None:
        return ""
    if isinstance(number, float) and number.is_integer():
        return str(int(number))
    return str(number)


def build_raw_export_csv(location_type: str, rows) -> bytes:
    """The measurements as a CSV matching AirGradient's own export byte for byte.

    Written with CRLF-free ``\\n`` line endings, no trailing newline and a UTF-8
    BOM, all three copied from their file: the BOM is what makes Excel open the
    accented column headers correctly on Windows.
    """
    buffer = io.StringIO()
    # `lineterminator` overrides csv's default CRLF; quoting matches theirs,
    # which only quotes a field when it holds a comma.
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)

    for row in rows:
        moment = row.get("_moment")
        local = _localise(moment)
        serial = row.get("serialno") or ""
        writer.writerow(
            [
                _csv_value(row.get("locationId")),
                row.get("locationName") or "",
                "",  # Location Group — portal metadata, not in the API
                (location_type or "").capitalize(),
                f"airgradient:{serial}" if serial else "",
                "",  # Place Open — portal metadata, not in the API
                local.strftime("%Y-%m-%d %H:%M:%S") if local else "",
                (
                    moment.astimezone(dt_timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%S.000Z"
                    )
                    if moment
                    else ""
                ),
                _csv_value(row.get("datapoints")),
                _csv_value(row.get("pm02")),
                _csv_value(row.get("pm02_corrected")),
                _csv_value(row.get("pm003Count")),
                _csv_value(row.get("rco2")),
                _csv_value(row.get("rco2_corrected")),
                _csv_value(row.get("atmp")),
                _csv_value(row.get("atmp_corrected")),
                "",  # Heat Index — see `_HEAT_INDEX_NOTE`
                _csv_value(row.get("rhum")),
                _csv_value(row.get("rhum_corrected")),
                _csv_value(row.get("tvoc")),
                _csv_value(row.get("tvocIndex")),
                _csv_value(row.get("noxIndex")),
                _csv_value(row.get("pm01")),
                _csv_value(row.get("pm10")),
            ]
        )

    body = buffer.getvalue()
    if body.endswith("\n"):
        body = body[:-1]
    return body.encode("utf-8-sig")


@extend_schema(
    tags=["Institutional Dashboard"],
    summary="Download the institution's raw measurement history",
    description=(
        "Every reading recorded by the institution's own sensor in the "
        "requested range, read live from the AirGradient API and written as "
        "a CSV in exactly the format AirGradient's own portal exports — same "
        "columns, same order, same labels, newest row first — so the two "
        "files are interchangeable. Defaults to the whole contract, from its "
        "start date to today. Timestamps are given in both sensor-local time "
        "and UTC. Returns 404 when the institution has no assigned sensor or "
        "the sensor is not linked to the provider, and 400 when the range is "
        "longer than a single export may carry or the provider is "
        "unreachable. An `X-Respira-Partial-Export` header on a 200 counts "
        "the sub-ranges the provider failed to serve."
    ),
    parameters=[
        OpenApiParameter(
            name="from",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=False,
            description="First day to include (YYYY-MM-DD). Defaults to the contract start.",
        ),
        OpenApiParameter(
            name="to",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Last day to include (YYYY-MM-DD, inclusive). Defaults to today.",
        ),
    ],
    responses={
        (
            200,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ): OpenApiTypes.BINARY
    },
)
class InstitutionRawExportView(APIView):
    permission_classes = [IsAuthenticated, IsInstitutionUser]
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        institution, contract = _contract_for_request(request)
        today = timezone.now().astimezone(REPORT_TIME_ZONE).date()

        start = _parse_date(request.query_params.get("from"), "from") or (
            contract.start_date
        )
        end = _parse_date(request.query_params.get("to"), "to") or today
        if end < start:
            raise ValidationError({"to": "The end date cannot precede the start date."})

        span = (end - start).days + 1
        if span > MAX_EXPORT_DAYS:
            # Bounded by wall-clock time, not row count: every extra day is
            # another upstream call, and the range has to be walked before its
            # size is known. Ten days per call means this stays well inside a
            # request timeout.
            raise ValidationError(
                {
                    "from": (
                        f"The selected range covers {span} days, over the "
                        f"{MAX_EXPORT_DAYS} a single export may carry. Narrow it "
                        "with the 'from' and 'to' parameters."
                    )
                }
            )

        # `end` is inclusive for the caller; the fetch bound is exclusive.
        lower, upper = _range_bounds(start, end + timedelta(days=1))

        # The AQI of the first rows depends on the 24 hours before them, so the
        # window is primed with a day of readings that are dropped before the
        # file is written. Without it the export would open with a stretch of
        # indices computed from a partial average.
        # Two failures that would otherwise look alike, kept apart: a station
        # with no AirGradient identity is a permanent configuration error that
        # retrying will never fix, while a failed call is transient. Reporting
        # the first as "try again later" sends whoever reads it looking in the
        # wrong place.
        try:
            location_id = location_id_for_station(contract.station)
        except AirGradientError:
            logger.exception(
                "Institution %s is bound to station %s, which has no "
                "AirGradient location; the raw export cannot be built.",
                institution.pk,
                contract.station_id,
            )
            raise NotFound(
                "This institution's sensor is not linked to the measurement "
                "provider, so its history cannot be exported. Please contact "
                "Proyecto Respira."
            )

        try:
            result = fetch_past_measures(location_id, lower, upper)
        except AirGradientError:
            logger.exception(
                "Raw export could not reach AirGradient for institution %s",
                institution.pk,
            )
            raise ValidationError(
                {
                    "detail": (
                        "The sensor data provider is unavailable right now. "
                        "Please try again in a few minutes."
                    )
                }
            )

        rows = _stamp_rows(result.rows)
        rows = [
            row
            for row in rows
            if row.get("_moment") is not None and lower <= row["_moment"] < upper
        ]
        # Newest first, as AirGradient's own export orders it.
        rows.reverse()

        content = build_raw_export_csv(location_type(location_id), rows)

        response = _attachment(
            content,
            _airgradient_filename(contract.station, start, end),
            "text/csv; charset=utf-8",
        )
        if result.failed_windows:
            # The file is still served — a partial history beats an error — but
            # the gap is stated rather than left for the institution to notice.
            response["X-Respira-Partial-Export"] = str(result.failed_windows)
        return response
