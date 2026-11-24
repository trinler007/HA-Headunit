"""Headunit: Fahrzeugdaten aus Home Assistant an eine LIVI-Headunit."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .bridge import HeadunitBridge
from .const import DOMAIN, SERVICE_CAMERA_HIDE, SERVICE_CAMERA_SHOW, SERVICE_PUSH

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR]

type HeadunitConfigEntry = ConfigEntry[HeadunitBridge]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_ENTRY = "config_entry_id"
_ENTRY = vol.Optional(ATTR_ENTRY)

PUSH_SCHEMA = vol.Schema({_ENTRY: cv.string, vol.Required("data"): dict})
SHOW_SCHEMA = vol.Schema(
    {
        _ENTRY: cv.string,
        vol.Exclusive("layout", "what"): cv.string,
        vol.Exclusive("cameras", "what"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
    }
)
HIDE_SCHEMA = vol.Schema({_ENTRY: cv.string})


def _bridges(hass: HomeAssistant, call: ServiceCall) -> list[HeadunitBridge]:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if entry_id := call.data.get(ATTR_ENTRY):
        entries = [e for e in entries if e.entry_id == entry_id]
    if not entries:
        raise ServiceValidationError("Keine geladene Headunit gefunden")
    return [e.runtime_data for e in entries]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Dienste registrieren."""

    async def push(call: ServiceCall) -> None:
        for bridge in _bridges(hass, call):
            if not await bridge.async_push(call.data["data"]):
                raise HomeAssistantError(f"LIVI nicht erreichbar: {bridge.last_error}")

    async def show(call: ServiceCall) -> None:
        for bridge in _bridges(hass, call):
            if not bridge.camview_enabled:
                raise ServiceValidationError("camview ist für diese Headunit nicht aktiviert")
            await bridge.async_camera_show(call.data.get("layout"), call.data.get("cameras"))

    async def hide(call: ServiceCall) -> None:
        for bridge in _bridges(hass, call):
            await bridge.async_camera_hide()

    hass.services.async_register(DOMAIN, SERVICE_PUSH, push, PUSH_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CAMERA_SHOW, show, SHOW_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CAMERA_HIDE, hide, HIDE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HeadunitConfigEntry) -> bool:
    """Brücke starten."""
    bridge = HeadunitBridge(hass, entry)
    entry.runtime_data = bridge
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await bridge.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HeadunitConfigEntry) -> bool:
    """Brücke stoppen."""
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: HeadunitConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
