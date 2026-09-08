"""File exports for the institutional dashboard (RES-328).

Two downloads, both scoped to the caller's own institution and both built from
``station_readings_gold`` — the same readings the dashboard aggregates, so a
number in a report can always be traced back to the panel it came from:

* a monthly PDF report, summarising one calendar month;
* a raw XLSX export of every reading in a date range.

Kept in its own module rather than in ``views.py``: the PDF and spreadsheet
machinery has nothing to do with the JSON API, and isolating it keeps that file
reviewable.

``TIME_ZONE`` is UTC, but institutions read their data in Paraguayan local time,
so every timestamp rendered into a file is converted to ``REPORT_TIME_ZONE``
first. The API's JSON keeps sending UTC; only these human-facing files localise.
"""

from __future__ import annotations

import io
import zoneinfo
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from typing import Any

from dateutil.relativedelta import relativedelta
from django.db.models import Avg, Count, Max, Min
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from openpyxl import Workbook
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
from rest_framework.views import APIView

from .aqi import AQI_LEVELS, classify_aqi
from .models import ActionLog, StationReadingsGold, get_institution_for_user
from .permissions import IsInstitutionUser

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

# A guard, not a product decision: an unbounded range on a busy station would
# build a workbook far larger than a browser will happily download. Callers who
# hit it are told to narrow the range rather than being handed a truncated file.
MAX_EXPORT_ROWS = 200_000


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


# --- raw XLSX export --------------------------------------------------------

_EXPORT_COLUMNS = [
    ("Fecha y hora (Asunción)", "date_utc"),
    ("PM1", "pm1"),
    ("PM2.5", "pm2_5"),
    ("PM10", "pm10"),
    ("AQI PM2.5", "aqi_pm2_5"),
    ("AQI PM10", "aqi_pm10"),
]


def build_raw_export_xlsx(institution, contract, rows) -> bytes:
    # `write_only` streams rows to the archive instead of holding a cell object
    # per value: a year of hourly readings is ~9k rows, and this keeps the
    # memory flat if a station ever reports far more often than that.
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title="Mediciones")
    sheet.append([label for label, _ in _EXPORT_COLUMNS])

    for row in rows:
        moment = _localise(row["date_utc"])
        sheet.append(
            [
                # Naive local time: Excel has no time-zone type, and a value
                # carrying an offset shows up as text in most spreadsheets.
                moment.replace(tzinfo=None) if moment else None,
                row["pm1"],
                row["pm2_5"],
                row["pm10"],
                row["aqi_pm2_5"],
                row["aqi_pm10"],
            ]
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@extend_schema(
    tags=["Institutional Dashboard"],
    summary="Download the institution's raw measurement history",
    description=(
        "Every reading recorded by the institution's own sensor in the "
        "requested range, as an XLSX spreadsheet. Defaults to the whole "
        "contract, from its start date to today. Timestamps are converted to "
        "Asunción local time. Returns 404 when the institution has no "
        "assigned sensor, and 400 when the range holds more rows than a "
        "single file should carry."
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

        # `end` is inclusive for the caller; the query bound is exclusive.
        lower, upper = _range_bounds(start, end + timedelta(days=1))

        queryset = (
            _readings(contract.station_id, lower, upper)
            .order_by("date_utc")
            .values("date_utc", "pm1", "pm2_5", "pm10", "aqi_pm2_5", "aqi_pm10")
        )

        total = queryset.count()
        if total > MAX_EXPORT_ROWS:
            raise ValidationError(
                {
                    "from": (
                        f"The selected range holds {total} readings, over the "
                        f"{MAX_EXPORT_ROWS} a single export may carry. Narrow it "
                        "with the 'from' and 'to' parameters."
                    )
                }
            )

        content = build_raw_export_xlsx(institution, contract, queryset.iterator())

        return _attachment(
            content,
            _filename(
                "historial",
                institution,
                f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}",
                "xlsx",
            ),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
