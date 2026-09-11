"""Air quality classification and recommendation logic.

Mirrors the ``AQI_LEVELS`` table maintained in respira-mobile
(``src/constants/aqiLevels.ts``) so the institutional dashboard reports the
same category, interpretive message and recommendations as the mobile app for
a given AQI value.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict


class AqiLevel(TypedDict):
    key: str
    label: str
    max: int | None
    message: str
    emoji: str
    recommendations: list[str]


AQI_LEVELS: list[AqiLevel] = [
    {
        "key": "good",
        "label": "BUENO",
        "max": 50,
        "message": "¡Es un día excelente para realizar actividades al aire libre!",
        "emoji": "😁",
        "recommendations": [
            "Ventilá habitaciones y oficinas.",
            "Disfrutá de actividades al aire libre.",
            "Aprovechá para hacer ejercicio.",
        ],
    },
    {
        "key": "moderate",
        "label": "MODERADO",
        "max": 100,
        "message": (
            "Las personas sensibles pueden presentar síntomas como tos o "
            "dificultad para respirar y deben seguir las precauciones "
            "habituales pero es un buen día para realizar actividades al "
            "aire libre."
        ),
        "emoji": "🙂",
        "recommendations": [
            "Grupos sensibles: reducí la actividad física si presentás síntomas.",
            "Prestá atención a la tos, dificultad para respirar o irritación ocular.",
            "Evitá zonas con alta contaminación.",
        ],
    },
    {
        "key": "unhealthy_sensitive",
        "label": "INSALUBRE PARA GRUPOS SENSIBLES",
        "max": 150,
        "message": (
            "Las personas sensibles pueden presentar síntomas y deben "
            "seguir las precauciones habituales para manejar."
        ),
        "emoji": "😷",
        "recommendations": [
            "Grupos sensibles: usá tapabocas y llevá medicamentos si es necesario salir.",
            "Evitá esfuerzos prolongados al aire libre.",
            "Preferí actividades en espacios cerrados y ventilados.",
        ],
    },
    {
        "key": "unhealthy",
        "label": "INSALUBRE",
        "max": 200,
        "message": (
            "Todos debemos limitar actividades al aire libre. Las personas "
            "sensibles deben evitar las actividades al aire libre y "
            "reprogramar cualquier evento al aire libre."
        ),
        "emoji": "😶‍🌫️",
        "recommendations": [
            "Grupos sensibles: evitá cualquier actividad al aire libre.",
            "Si tenés que salir, usá tapabocas.",
            "Mantené tu hogar u oficina bien sellados para evitar el aire contaminado.",
        ],
    },
    {
        "key": "very_unhealthy",
        "label": "MUY INSALUBRE",
        "max": 300,
        "message": (
            "Traslade a un lugar cerrado las actividades innecesarias. "
            "Todos debemos evitar actividades al aire libre extenuantes y "
            "prolongadas. Reprograme actividades al aire libre."
        ),
        "emoji": "😨",
        "recommendations": [
            "Todos: evitá actividades al aire libre.",
            "Si es necesario salir, usá tapabocas y tené medicamentos a mano.",
            "Consultá a un médico si los síntomas se agravan.",
        ],
    },
    {
        "key": "hazardous",
        "label": "PELIGROSO",
        "max": None,
        "message": (
            "Todos debemos evitar las actividades al aire libre "
            "innecesarias por completo. Permanezca adentro y mantenga un "
            "nivel de actividad bajo."
        ),
        "emoji": "💀",
        "recommendations": [
            "Todos: evitá la exposición al aire contaminado.",
            "Permanecé en interiores con ventanas y puertas cerradas.",
            "Prestá atención a los síntomas respiratorios y consultá a un médico si es necesario.",
        ],
    },
]


# EPA breakpoint tables, mirrored from the pipeline's `dbt/macros/aqi.sql` so an
# AQI computed here matches the one the warehouse publishes for the same
# concentration. Each entry is (concentration_high, index_low, index_high); the
# concentration_low of a band is the previous band's high plus one step.
_PM25_BREAKPOINTS = [
    (Decimal("12.0"), 0, 50),
    (Decimal("35.4"), 51, 100),
    (Decimal("55.4"), 101, 150),
    (Decimal("150.4"), 151, 200),
    (Decimal("250.4"), 201, 300),
    (Decimal("350.4"), 301, 400),
    (Decimal("500.4"), 401, 500),
]

_PM10_BREAKPOINTS = [
    (Decimal("54"), 0, 50),
    (Decimal("154"), 51, 100),
    (Decimal("254"), 101, 150),
    (Decimal("354"), 151, 200),
    (Decimal("424"), 201, 300),
    (Decimal("504"), 301, 400),
    (Decimal("604"), 401, 500),
]


def _truncate(value: float | int, places: int) -> Decimal:
    """Drop digits beyond ``places`` without rounding, as SQL ``trunc`` does."""
    quantum = Decimal(1).scaleb(-places)
    return Decimal(str(value)).quantize(quantum, rounding="ROUND_DOWN")


def _aqi_from_breakpoints(
    value: float | int | None, breakpoints, places: int
) -> int | None:
    """Piecewise-linear AQI, matching ``aqi_linear`` in the dbt macro.

    Returns ``None`` for a missing or negative concentration, and caps at 500
    above the last band — both the same as the macro.
    """
    if value is None:
        return None
    concentration = _truncate(value, places)
    if concentration < 0:
        return None

    step = Decimal(1).scaleb(-places)
    low = Decimal(0)
    for high, index_low, index_high in breakpoints:
        if concentration <= high:
            span = high - low
            if span <= 0:
                return index_low
            raw = (
                (Decimal(index_high - index_low) / span) * (concentration - low)
            ) + index_low
            return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        low = high + step
    return 500


def aqi_from_pm25(value: float | int | None) -> int | None:
    """AQI for a PM2.5 concentration, truncated to one decimal first."""
    return _aqi_from_breakpoints(value, _PM25_BREAKPOINTS, 1)


def aqi_from_pm10(value: float | int | None) -> int | None:
    """AQI for a PM10 concentration, truncated to a whole number first."""
    return _aqi_from_breakpoints(value, _PM10_BREAKPOINTS, 0)


def classify_aqi(value: float | int | None) -> AqiLevel | None:
    """Return the ``AQI_LEVELS`` entry covering ``value``.

    Mirrors respira-mobile's ``getAqiLevelByValue``: the last level (with
    ``max=None``) catches everything above the second-to-last cutoff.
    Returns ``None`` when there is no value to classify.
    """
    if value is None:
        return None
    for level in AQI_LEVELS:
        if level["max"] is None or value <= level["max"]:
            return level
    return AQI_LEVELS[-1]
