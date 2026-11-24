"""Tests für die Umrechnung (ohne Home Assistant lauffähig)."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "convert", Path(__file__).parents[1] / "custom_components/headunit/convert.py"
)
convert_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(convert_mod)
convert, gps_patch, to_bool = convert_mod.convert, convert_mod.gps_patch, convert_mod.to_bool


def test_unavailable_is_not_sent():
    for state in ("unavailable", "unknown", None, ""):
        assert convert("speed", state, "km/h") is None
        assert convert("bool", state) is None


def test_bool():
    assert convert("bool", "on") is True
    assert convert("bool", "off") is False
    assert convert("bool", "below_horizon") is True  # sun -> nightMode
    assert convert("bool", "garbage") is None
    assert to_bool("TRUE") is True


def test_speed_units():
    assert convert("speed", "50", "km/h") == 50.0
    assert convert("speed", "10", "m/s") == 36.0
    assert convert("speed", "10", "mph") == 16.1
    assert convert("speed", "-0.3", "km/h") == 0.0
    assert convert("speed", "nan", "km/h") is None


def test_temp_distance_pct_voltage():
    assert convert("temp", "212", "°F") == 100.0
    assert convert("distance", "1000", "m") == 1.0
    assert convert("distance", "10", "mi") == 16.1
    assert convert("pct", "120", "%") == 100.0
    assert convert("voltage", "12650", "mV") == 12.65


def test_gear():
    assert convert("gear", "r") == "R"
    assert convert("gear", "M3") == "M3"
    assert convert("gear", "-1") == -1
    assert convert("gear", "4") == 4
    assert convert("gear", "X") is None


def test_gps_from_tracker():
    attrs = {"latitude": 47.72, "longitude": 10.31, "gps_accuracy": 4, "altitude": 700}
    assert gps_patch(attrs) == {"lat": 47.72, "lng": 10.31, "accuracyM": 4.0, "alt": 700.0}


def test_gps_sensors_override():
    attrs = {"latitude": 47.72, "longitude": 10.31}
    g = gps_patch(attrs, altitude="701.5", speed=("36", "km/h"), heading="370", accuracy="2.5")
    assert g["alt"] == 701.5 and g["speedMs"] == 10.0 and g["accuracyM"] == 2.5
    assert "heading" not in g  # außerhalb 0..360 verworfen
    g = gps_patch(attrs, heading="90")
    assert g["heading"] == 90.0


def test_gps_invalid():
    assert gps_patch(None) is None
    assert gps_patch({"latitude": None, "longitude": 10}) is None
    assert gps_patch({"latitude": 95, "longitude": 10}) is None
