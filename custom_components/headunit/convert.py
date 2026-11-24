"""Übersetzung von HA-Zuständen in LIVI-Telemetriewerte.

Bewusst ohne Home-Assistant-Importe, damit es ohne HA testbar ist.
"""

from __future__ import annotations

from typing import Any

UNAVAILABLE = {"unavailable", "unknown", "none", ""}
TRUE_STATES = {"on", "true", "1", "yes", "home", "open", "below_horizon"}
FALSE_STATES = {"off", "false", "0", "no", "not_home", "closed", "above_horizon"}

_SPEED_TO_KPH = {
    "km/h": 1.0,
    "kph": 1.0,
    "m/s": 3.6,
    "mph": 1.609344,
    "kn": 1.852,
    "kt": 1.852,
}
_DIST_TO_KM = {"km": 1.0, "m": 0.001, "mi": 1.609344, "ft": 0.0003048}
_SPEED_TO_MS = {k: v / 3.6 for k, v in _SPEED_TO_KPH.items()}

GEARS_AUTOMATIC = {"P", "R", "N", "D", "S"}


def _num(state: str) -> float | None:
    try:
        value = float(state)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN/inf
        return None
    return value


def to_bool(state: str | None) -> bool | None:
    """on/off & Co. nach bool; unbekannt -> None."""
    if state is None:
        return None
    s = str(state).strip().lower()
    if s in TRUE_STATES:
        return True
    if s in FALSE_STATES:
        return False
    return None


def convert(kind: str, state: str | None, unit: str | None = None) -> Any:
    """Einen HA-Zustand für ein LIVI-Feld umrechnen. None = nicht senden."""
    if state is None or str(state).strip().lower() in UNAVAILABLE:
        return None
    unit = (unit or "").strip()

    if kind == "bool":
        return to_bool(state)

    if kind == "gear":
        s = str(state).strip().upper()
        if s in GEARS_AUTOMATIC or (s.startswith("M") and s[1:].isdigit()):
            return s
        n = _num(s)
        if n is not None and -1 <= n <= 10:
            return int(n)
        return None

    value = _num(state)
    if value is None:
        return None

    if kind == "speed":
        factor = _SPEED_TO_KPH.get(unit.lower(), 1.0)
        return round(max(value * factor, 0.0), 1)
    if kind == "distance":
        factor = _DIST_TO_KM.get(unit.lower(), 1.0)
        return round(value * factor, 1)
    if kind == "temp":
        if unit in ("°F", "F"):
            value = (value - 32.0) * 5.0 / 9.0
        elif unit in ("K",):
            value -= 273.15
        return round(value, 1)
    if kind == "pct":
        return round(min(max(value, 0.0), 100.0), 1)
    if kind == "voltage":
        if unit == "mV":
            value /= 1000.0
        return round(value, 2)
    return value


def speed_ms(state: str | None, unit: str | None) -> float | None:
    """Geschwindigkeit in m/s für gps.speedMs."""
    if state is None:
        return None
    value = _num(state)
    if value is None:
        return None
    return round(max(value * _SPEED_TO_MS.get((unit or "km/h").lower(), 1 / 3.6), 0.0), 2)


def gps_patch(
    tracker_attrs: dict[str, Any] | None,
    altitude: str | None = None,
    speed: tuple[str | None, str | None] | None = None,
    heading: str | None = None,
    accuracy: str | None = None,
) -> dict[str, Any] | None:
    """gps-Block aus device_tracker-Attributen und optionalen Sensoren bauen."""
    if not tracker_attrs:
        return None
    lat = tracker_attrs.get("latitude")
    lng = tracker_attrs.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    gps: dict[str, Any] = {"lat": float(lat), "lng": float(lng)}

    acc = _num(accuracy) if accuracy is not None else None
    if acc is None:
        acc = tracker_attrs.get("gps_accuracy")
    if isinstance(acc, (int, float)) and acc > 0:
        gps["accuracyM"] = float(acc)

    alt = _num(altitude) if altitude is not None else tracker_attrs.get("altitude")
    if isinstance(alt, (int, float)):
        gps["alt"] = float(alt)

    if speed is not None:
        sms = speed_ms(*speed)
        if sms is not None:
            gps["speedMs"] = sms

    hdg = _num(heading) if heading is not None else tracker_attrs.get("course")
    if isinstance(hdg, (int, float)) and 0 <= hdg <= 360:
        gps["heading"] = float(hdg) % 360
    return gps
