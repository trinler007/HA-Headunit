"""Einrichtung und Optionen."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CAMVIEW_ENABLED,
    CONF_CAMVIEW_PORT,
    CONF_CAMVIEW_TOKEN,
    CONF_GPS_ACCURACY,
    CONF_GPS_ALTITUDE,
    CONF_GPS_HEADING,
    CONF_GPS_SPEED,
    CONF_GPS_TRACKER,
    CONF_REVERSE_CAMERA,
    CONF_REVERSE_HIDE_DELAY,
    CONF_REVERSE_LAYOUT,
    CONF_TELEMETRY_PORT,
    DEFAULT_CAMVIEW_PORT,
    DEFAULT_REVERSE_HIDE_DELAY,
    DEFAULT_REVERSE_LAYOUT,
    DEFAULT_TELEMETRY_PORT,
    DOMAIN,
    FIELDS,
    HTTP_TIMEOUT_S,
)

PORT = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))


async def _probe(hass, host: str, port: int) -> bool:
    """LIVI antwortet auf einen leeren Patch mit 204."""
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            f"http://{host}:{port}/telemetry",
            json={},
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S),
        ) as resp:
            return resp.status < 300
    except (aiohttp.ClientError, TimeoutError):
        return False


class HeadunitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Headunit hinzufügen."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_TELEMETRY_PORT]
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            if not await _probe(self.hass, host, port) and not user_input.get("skip_check"):
                errors["base"] = "cannot_connect"
            else:
                data = {k: v for k, v in user_input.items() if k != "skip_check"}
                data[CONF_HOST] = host
                return self.async_create_entry(title=user_input[CONF_NAME], data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Headunit"): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_TELEMETRY_PORT, default=DEFAULT_TELEMETRY_PORT): PORT,
                vol.Optional("skip_check", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HeadunitOptionsFlow()


def _entity(domains: tuple[str, ...] | list[str]) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=list(domains)))


class HeadunitOptionsFlow(OptionsFlow):
    """Zuordnung Entitäten -> LIVI-Felder, GPS, camview."""

    def __init__(self) -> None:
        self._opts: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["vehicle", "gps", "camview"])

    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.options, **self._opts}

    def _save(self, user_input: dict[str, Any], keys: list[str]) -> ConfigFlowResult:
        merged = {k: v for k, v in self._current().items() if k not in keys}
        # Geleerte Felder entfernen statt leere Strings zu speichern
        merged.update({k: v for k, v in user_input.items() if v not in (None, "")})
        return self.async_create_entry(data=merged)

    async def async_step_vehicle(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        keys = [f.key for f in FIELDS]
        if user_input is not None:
            return self._save(user_input, keys)
        schema = vol.Schema({vol.Optional(f.key): _entity(f.domains) for f in FIELDS})
        return self.async_show_form(
            step_id="vehicle",
            data_schema=self.add_suggested_values_to_schema(schema, self._current()),
        )

    async def async_step_gps(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        keys = [CONF_GPS_TRACKER, CONF_GPS_ALTITUDE, CONF_GPS_SPEED, CONF_GPS_HEADING, CONF_GPS_ACCURACY]
        if user_input is not None:
            return self._save(user_input, keys)
        sensor = _entity(("sensor", "input_number"))
        schema = vol.Schema(
            {
                vol.Optional(CONF_GPS_TRACKER): _entity(("device_tracker",)),
                vol.Optional(CONF_GPS_ALTITUDE): sensor,
                vol.Optional(CONF_GPS_SPEED): sensor,
                vol.Optional(CONF_GPS_HEADING): sensor,
                vol.Optional(CONF_GPS_ACCURACY): sensor,
            }
        )
        return self.async_show_form(
            step_id="gps",
            data_schema=self.add_suggested_values_to_schema(schema, self._current()),
        )

    async def async_step_camview(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        keys = [
            CONF_CAMVIEW_ENABLED, CONF_CAMVIEW_PORT, CONF_CAMVIEW_TOKEN,
            CONF_REVERSE_CAMERA, CONF_REVERSE_LAYOUT, CONF_REVERSE_HIDE_DELAY,
        ]
        if user_input is not None:
            return self._save(user_input, keys)
        cur = self._current()
        schema = vol.Schema(
            {
                vol.Required(CONF_CAMVIEW_ENABLED, default=cur.get(CONF_CAMVIEW_ENABLED, False)): bool,
                vol.Required(CONF_CAMVIEW_PORT, default=cur.get(CONF_CAMVIEW_PORT, DEFAULT_CAMVIEW_PORT)): PORT,
                vol.Optional(CONF_CAMVIEW_TOKEN): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_REVERSE_CAMERA, default=cur.get(CONF_REVERSE_CAMERA, True)): bool,
                vol.Required(
                    CONF_REVERSE_LAYOUT, default=cur.get(CONF_REVERSE_LAYOUT, DEFAULT_REVERSE_LAYOUT)
                ): str,
                vol.Required(
                    CONF_REVERSE_HIDE_DELAY,
                    default=cur.get(CONF_REVERSE_HIDE_DELAY, DEFAULT_REVERSE_HIDE_DELAY),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
            }
        )
        return self.async_show_form(
            step_id="camview",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_CAMVIEW_TOKEN: cur.get(CONF_CAMVIEW_TOKEN)}
            ),
        )
