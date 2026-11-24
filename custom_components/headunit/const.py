"""Konstanten der Headunit-Integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DOMAIN: Final = "headunit"

CONF_TELEMETRY_PORT: Final = "telemetry_port"
CONF_CAMVIEW_ENABLED: Final = "camview_enabled"
CONF_CAMVIEW_PORT: Final = "camview_port"
CONF_CAMVIEW_TOKEN: Final = "camview_token"
CONF_REVERSE_CAMERA: Final = "reverse_camera"
CONF_REVERSE_LAYOUT: Final = "reverse_layout"
CONF_REVERSE_HIDE_DELAY: Final = "reverse_hide_delay"
CONF_GPS_TRACKER: Final = "gps_tracker"
CONF_GPS_ALTITUDE: Final = "gps_altitude"
CONF_GPS_SPEED: Final = "gps_speed"
CONF_GPS_HEADING: Final = "gps_heading"
CONF_GPS_ACCURACY: Final = "gps_accuracy"

DEFAULT_TELEMETRY_PORT: Final = 4000
DEFAULT_CAMVIEW_PORT: Final = 8088
DEFAULT_REVERSE_LAYOUT: Final = "reverse"
DEFAULT_REVERSE_HIDE_DELAY: Final = 3

# Änderungen innerhalb dieses Fensters werden zu einem Push zusammengefasst
PUSH_COALESCE_S: Final = 0.2
# Vollständiger Stand in diesem Takt: hält LIVI nach Neustart aktuell und
# dient als Erreichbarkeitsprüfung
SNAPSHOT_INTERVAL_S: Final = 30
HTTP_TIMEOUT_S: Final = 3


@dataclass(frozen=True, slots=True)
class Field:
    """Ein LIVI-Telemetriefeld und wie ein HA-Zustand dorthin übersetzt wird."""

    key: str          # Name im LIVI-JSON
    kind: str         # bool | speed | temp | pct | distance | voltage | gear | number
    domains: tuple[str, ...] = ("sensor", "binary_sensor", "input_number", "input_boolean")


# Reihenfolge = Reihenfolge im Optionsdialog
FIELDS: Final[tuple[Field, ...]] = (
    Field("speedKph", "speed", ("sensor", "input_number")),
    Field("reverse", "bool", ("binary_sensor", "input_boolean", "switch")),
    Field("gear", "gear", ("sensor", "select", "input_select")),
    Field("parkingBrake", "bool", ("binary_sensor", "input_boolean", "switch")),
    Field("lights", "bool", ("binary_sensor", "light", "switch", "input_boolean")),
    Field("highBeam", "bool", ("binary_sensor", "light", "switch", "input_boolean")),
    Field("hazards", "bool", ("binary_sensor", "switch", "input_boolean")),
    Field("nightMode", "bool", ("binary_sensor", "input_boolean", "sun")),
    Field("fuelPct", "pct", ("sensor", "input_number")),
    Field("rangeKm", "distance", ("sensor", "input_number")),
    Field("odometerKm", "distance", ("sensor", "input_number")),
    Field("ambientC", "temp", ("sensor", "input_number")),
    Field("coolantC", "temp", ("sensor", "input_number")),
    Field("batteryV", "voltage", ("sensor", "input_number")),
    Field("rpm", "number", ("sensor", "input_number")),
)

GPS_KEYS: Final = (
    CONF_GPS_TRACKER,
    CONF_GPS_ALTITUDE,
    CONF_GPS_SPEED,
    CONF_GPS_HEADING,
    CONF_GPS_ACCURACY,
)

SERVICE_PUSH: Final = "push_telemetry"
SERVICE_CAMERA_SHOW: Final = "camera_show"
SERVICE_CAMERA_HIDE: Final = "camera_hide"
