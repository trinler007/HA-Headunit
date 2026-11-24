"""Brücke HA -> LIVI-Telemetrie und HA -> camview."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, CONF_HOST
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)

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
    FIELDS,
    GPS_KEYS,
    HTTP_TIMEOUT_S,
    PUSH_COALESCE_S,
    SNAPSHOT_INTERVAL_S,
)
from .convert import convert, gps_patch, to_bool

_LOGGER = logging.getLogger(__name__)


class HeadunitBridge:
    """Beobachtet die zugeordneten Entitäten und schickt Änderungen an LIVI."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._session = async_get_clientsession(hass)
        self._pending: dict[str, Any] = {}
        self._flush_cancel: CALLBACK_TYPE | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._hide_cancel: CALLBACK_TYPE | None = None
        self._lock = asyncio.Lock()
        self.available: bool | None = None
        self.last_push: datetime | None = None
        self.last_error: str | None = None
        self.camview_available: bool | None = None
        self._listeners: list[Callable[[], None]] = []

    # --- Konfiguration ------------------------------------------------------
    @property
    def _opts(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    @property
    def telemetry_url(self) -> str:
        port = self._opts.get(CONF_TELEMETRY_PORT, DEFAULT_TELEMETRY_PORT)
        return f"http://{self._opts[CONF_HOST]}:{port}/telemetry"

    @property
    def camview_enabled(self) -> bool:
        return bool(self._opts.get(CONF_CAMVIEW_ENABLED))

    def _field_map(self) -> dict[str, str]:
        """LIVI-Feld -> entity_id (nur belegte)."""
        return {f.key: self._opts[f.key] for f in FIELDS if self._opts.get(f.key)}

    def _gps_entities(self) -> dict[str, str]:
        return {k: self._opts[k] for k in GPS_KEYS if self._opts.get(k)}

    def _reverse_entity(self) -> str | None:
        return self._opts.get("reverse")

    # --- Lebenszyklus -------------------------------------------------------
    async def async_start(self) -> None:
        watched = set(self._field_map().values()) | set(self._gps_entities().values())
        if watched:
            self._unsubs.append(
                async_track_state_change_event(self.hass, sorted(watched), self._on_change)
            )
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._snapshot_tick, timedelta(seconds=SNAPSHOT_INTERVAL_S)
            )
        )
        self.hass.async_create_task(self.async_push_snapshot())

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for cancel in (self._flush_cancel, self._hide_cancel):
            if cancel:
                cancel()

    @callback
    def add_listener(self, cb: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    # --- Werte bilden -------------------------------------------------------
    def _field_value(self, key: str, entity_id: str) -> Any:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        kind = next(f.kind for f in FIELDS if f.key == key)
        return convert(kind, state.state, state.attributes.get(ATTR_UNIT_OF_MEASUREMENT))

    def _gps_value(self) -> dict[str, Any] | None:
        ents = self._gps_entities()
        tracker = self.hass.states.get(ents.get(CONF_GPS_TRACKER, ""))
        if tracker is None:
            return None

        def st(key: str) -> str | None:
            s = self.hass.states.get(ents.get(key, ""))
            return s.state if s else None

        speed = None
        if CONF_GPS_SPEED in ents and (s := self.hass.states.get(ents[CONF_GPS_SPEED])):
            speed = (s.state, s.attributes.get(ATTR_UNIT_OF_MEASUREMENT))
        return gps_patch(
            dict(tracker.attributes),
            altitude=st(CONF_GPS_ALTITUDE),
            speed=speed,
            heading=st(CONF_GPS_HEADING),
            accuracy=st(CONF_GPS_ACCURACY),
        )

    def snapshot(self) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        for key, entity_id in self._field_map().items():
            value = self._field_value(key, entity_id)
            if value is not None:
                patch[key] = value
        if (gps := self._gps_value()) is not None:
            patch["gps"] = gps
        return patch

    # --- Ereignisse ---------------------------------------------------------
    @callback
    def _on_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        for key, eid in self._field_map().items():
            if eid == entity_id:
                value = self._field_value(key, eid)
                if value is not None:
                    self._pending[key] = value
        if entity_id in self._gps_entities().values():
            if (gps := self._gps_value()) is not None:
                self._pending["gps"] = gps
        if entity_id == self._reverse_entity():
            self._on_reverse(event)
        if self._pending and self._flush_cancel is None:
            self._flush_cancel = async_call_later(self.hass, PUSH_COALESCE_S, self._flush)

    @callback
    def _flush(self, _now: datetime) -> None:
        self._flush_cancel = None
        patch, self._pending = self._pending, {}
        if patch:
            self.hass.async_create_task(self.async_push(patch))

    @callback
    def _snapshot_tick(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_push_snapshot())

    # --- Rückwärtsgang -> camview --------------------------------------------
    @callback
    def _on_reverse(self, event: Event[EventStateChangedData]) -> None:
        if not (self.camview_enabled and self._opts.get(CONF_REVERSE_CAMERA)):
            return
        new = event.data["new_state"]
        on = to_bool(new.state) if new else None
        if on is None:
            return
        if self._hide_cancel:
            self._hide_cancel()
            self._hide_cancel = None
        if on:
            layout = self._opts.get(CONF_REVERSE_LAYOUT, DEFAULT_REVERSE_LAYOUT)
            self.hass.async_create_task(self.async_camera_show(layout=layout))
        else:
            delay = self._opts.get(CONF_REVERSE_HIDE_DELAY, DEFAULT_REVERSE_HIDE_DELAY)

            @callback
            def _hide(_now: datetime) -> None:
                self._hide_cancel = None
                self.hass.async_create_task(self.async_camera_hide())

            self._hide_cancel = async_call_later(self.hass, delay, _hide)

    # --- HTTP -----------------------------------------------------------------
    async def async_push_snapshot(self) -> bool:
        return await self.async_push(self.snapshot(), keepalive=True)

    async def async_push(self, patch: dict[str, Any], keepalive: bool = False) -> bool:
        """Ein Patch an LIVI. Leerer Patch nur als Erreichbarkeitsprüfung."""
        if not patch and not keepalive:
            return True
        async with self._lock:
            try:
                async with self._session.post(
                    self.telemetry_url,
                    json=patch,
                    timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S),
                ) as resp:
                    ok = resp.status < 300
                    self.last_error = None if ok else f"HTTP {resp.status}"
            except (aiohttp.ClientError, TimeoutError) as err:
                ok = False
                self.last_error = str(err) or type(err).__name__
        was = self.available
        self.available = ok
        if ok:
            self.last_push = datetime.now().astimezone()
        if ok and was is False:
            _LOGGER.info("LIVI wieder erreichbar")
            if not keepalive:
                # LIVI war weg (Neustart?) – kompletten Stand nachschieben
                await self.async_push_snapshot()
        elif not ok and was is not False:
            _LOGGER.info("LIVI nicht erreichbar: %s", self.last_error)
        if was != ok or keepalive:
            self._notify()
        return ok

    async def _camview(self, path: str, params: dict[str, str] | None = None) -> bool:
        if not self.camview_enabled:
            return False
        port = self._opts.get(CONF_CAMVIEW_PORT, DEFAULT_CAMVIEW_PORT)
        url = f"http://{self._opts[CONF_HOST]}:{port}{path}"
        headers = {}
        if token := self._opts.get(CONF_CAMVIEW_TOKEN):
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with self._session.get(
                url, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S),
            ) as resp:
                ok = resp.status < 300
                if not ok:
                    _LOGGER.warning("camview %s: HTTP %s", path, resp.status)
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("camview %s nicht erreichbar: %s", path, err)
            ok = False
        if self.camview_available != ok:
            self.camview_available = ok
            self._notify()
        return ok

    async def async_camera_show(
        self, layout: str | None = None, cams: list[int] | None = None
    ) -> bool:
        params = {"layout": layout} if layout else {"cams": ",".join(map(str, cams or [1]))}
        return await self._camview("/show", params)

    async def async_camera_hide(self) -> bool:
        return await self._camview("/hide")
