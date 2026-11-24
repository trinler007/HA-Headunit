"""Integrationstests mit der Home-Assistant-Testumgebung."""

import asyncio
import json

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries  # noqa: E402
from homeassistant.const import CONF_HOST, CONF_NAME  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.headunit.const import DOMAIN  # noqa: E402

URL = "http://hu.local:4000/telemetry"
CAM = "http://hu.local:8088"


def _bodies(aioclient_mock):
    return [json.loads(c[2]) if isinstance(c[2], (str, bytes)) else c[2]
            for c in aioclient_mock.mock_calls if str(c[1]) == URL]


async def _setup(hass, aioclient_mock, options):
    aioclient_mock.post(URL, status=204)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Headunit",
        data={CONF_NAME: "Headunit", CONF_HOST: "hu.local", "telemetry_port": 4000},
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _settle(hass):
    await asyncio.sleep(0.3)  # Bündelungsfenster 200 ms
    await hass.async_block_till_done()


async def test_config_flow(hass, aioclient_mock):
    aioclient_mock.post(URL, status=204)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Headunit", CONF_HOST: "hu.local", "telemetry_port": 4000},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "hu.local"


async def test_config_flow_cannot_connect(hass, aioclient_mock):
    aioclient_mock.post(URL, exc=asyncio.TimeoutError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Headunit", CONF_HOST: "hu.local", "telemetry_port": 4000},
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_snapshot_and_changes(hass, aioclient_mock):
    hass.states.async_set("sensor.tacho", "36", {"unit_of_measurement": "km/h"})
    hass.states.async_set("binary_sensor.rueckwaerts", "off")
    hass.states.async_set(
        "device_tracker.rutx", "not_home",
        {"latitude": 47.72, "longitude": 10.31, "gps_accuracy": 5},
    )
    await _setup(hass, aioclient_mock, {
        "speedKph": "sensor.tacho",
        "reverse": "binary_sensor.rueckwaerts",
        "gps_tracker": "device_tracker.rutx",
    })
    first = _bodies(aioclient_mock)[0]
    assert first == {
        "speedKph": 36.0, "reverse": False,
        "gps": {"lat": 47.72, "lng": 10.31, "accuracyM": 5.0},
    }
    assert hass.states.get("binary_sensor.headunit_livi_reachable").state == "on"

    n = len(_bodies(aioclient_mock))
    hass.states.async_set("sensor.tacho", "10", {"unit_of_measurement": "m/s"})
    hass.states.async_set("binary_sensor.rueckwaerts", "on")
    await _settle(hass)
    bodies = _bodies(aioclient_mock)[n:]
    assert bodies == [{"speedKph": 36.0, "reverse": True}]  # gebündelt in einem Push


async def test_unreachable_then_back_sends_snapshot(hass, aioclient_mock):
    hass.states.async_set("sensor.tacho", "50", {"unit_of_measurement": "km/h"})
    entry = await _setup(hass, aioclient_mock, {"speedKph": "sensor.tacho"})
    bridge = entry.runtime_data

    aioclient_mock.clear_requests()
    aioclient_mock.post(URL, exc=asyncio.TimeoutError())
    assert not await bridge.async_push({"speedKph": 1})
    assert bridge.available is False
    await hass.async_block_till_done()

    aioclient_mock.clear_requests()
    aioclient_mock.post(URL, status=204)
    assert await bridge.async_push({"speedKph": 60})
    bodies = _bodies(aioclient_mock)
    assert bodies[0] == {"speedKph": 60}
    assert bodies[1] == {"speedKph": 50.0}  # kompletter Stand hinterher


async def test_reverse_triggers_camview(hass, aioclient_mock):
    aioclient_mock.get(f"{CAM}/show", status=200)
    aioclient_mock.get(f"{CAM}/hide", status=200)
    hass.states.async_set("binary_sensor.rueckwaerts", "off")
    await _setup(hass, aioclient_mock, {
        "reverse": "binary_sensor.rueckwaerts",
        "camview_enabled": True, "camview_port": 8088, "camview_token": "geheim",
        "reverse_camera": True, "reverse_layout": "reverse", "reverse_hide_delay": 0,
    })
    hass.states.async_set("binary_sensor.rueckwaerts", "on")
    await _settle(hass)
    shows = [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(f"{CAM}/show")]
    assert shows and "layout=reverse" in str(shows[0][1])
    assert shows[0][3]["Authorization"] == "Bearer geheim"

    hass.states.async_set("binary_sensor.rueckwaerts", "off")
    await hass.async_block_till_done()
    async_fire_time_changed(hass)
    await _settle(hass)
    assert any(str(c[1]).startswith(f"{CAM}/hide") for c in aioclient_mock.mock_calls)


async def test_service_push(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, {})
    aioclient_mock.clear_requests()
    aioclient_mock.post(URL, status=204)
    await hass.services.async_call(
        DOMAIN, "push_telemetry", {"data": {"gear": "D"}}, blocking=True
    )
    assert _bodies(aioclient_mock) == [{"gear": "D"}]
