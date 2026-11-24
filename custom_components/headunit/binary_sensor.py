"""Erreichbarkeit von LIVI und camview."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeadunitConfigEntry
from .bridge import HeadunitBridge
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeadunitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    entities: list[BinarySensorEntity] = [LiviConnected(bridge, entry)]
    if bridge.camview_enabled:
        entities.append(CamviewConnected(bridge, entry))
    async_add_entities(entities)


class _Base(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, bridge: HeadunitBridge, entry: HeadunitConfigEntry) -> None:
        self.bridge = bridge
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="LIVI",
            model="Headunit",
            configuration_url=bridge.telemetry_url.removesuffix("/telemetry"),
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.bridge.add_listener(self.async_write_ha_state))


class LiviConnected(_Base):
    _attr_translation_key = "livi_connected"

    def __init__(self, bridge: HeadunitBridge, entry: HeadunitConfigEntry) -> None:
        super().__init__(bridge, entry)
        self._attr_unique_id = f"{entry.entry_id}_livi_connected"

    @property
    def is_on(self) -> bool | None:
        return self.bridge.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "url": self.bridge.telemetry_url,
            "last_push": self.bridge.last_push.isoformat() if self.bridge.last_push else None,
            "last_error": self.bridge.last_error,
        }


class CamviewConnected(_Base):
    _attr_translation_key = "camview_connected"

    def __init__(self, bridge: HeadunitBridge, entry: HeadunitConfigEntry) -> None:
        super().__init__(bridge, entry)
        self._attr_unique_id = f"{entry.entry_id}_camview_connected"

    @property
    def is_on(self) -> bool | None:
        return self.bridge.camview_available
