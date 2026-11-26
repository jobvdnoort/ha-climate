"""WebSocket API used by the HA Climate sidebar panel."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import logging
from typing import Any
import uuid

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .calculations import parse_time
from .const import (
    CONF_BASELINE_DAYS,
    CONF_COMFORT_TIME,
    CONF_DAY_TEMP,
    CONF_FIREPLACE_CLIMATE,
    CONF_FIREPLACE_TEMP_SENSOR,
    CONF_FIREPLACE_THRESHOLD,
    CONF_GAS_PRICE,
    CONF_GAS_PRICE_ENTITY,
    CONF_GAS_SENSOR,
    CONF_HEATING_LIMIT,
    CONF_NIGHT_END,
    CONF_NIGHT_OFFSET,
    CONF_NIGHT_START,
    CONF_NIGHT_TEMP,
    CONF_OPTIMUM_START,
    CONF_OUTDOOR_SENSOR,
    CONF_ROOM_CLIMATES,
    CONF_ROOM_ID,
    CONF_ROOM_NAME,
    CONF_ROOM_USE_GLOBAL,
    CONF_ROOMS,
    DEFAULT_BASELINE_DAYS,
    DEFAULT_COMFORT_TIME,
    DEFAULT_FIREPLACE_THRESHOLD,
    DEFAULT_GAS_PRICE,
    DEFAULT_HEATING_LIMIT,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_OFFSET,
    DEFAULT_NIGHT_START,
    DOMAIN,
)
from .coordinator import HaClimateConfigEntry, HaClimateCoordinator

_LOGGER = logging.getLogger(__name__)

RELOAD_TIMEOUT = 30

SETTING_KEYS = (
    CONF_OUTDOOR_SENSOR,
    CONF_GAS_SENSOR,
    CONF_GAS_PRICE,
    CONF_GAS_PRICE_ENTITY,
    CONF_HEATING_LIMIT,
    CONF_BASELINE_DAYS,
    CONF_NIGHT_START,
    CONF_NIGHT_END,
    CONF_NIGHT_OFFSET,
    CONF_FIREPLACE_CLIMATE,
    CONF_FIREPLACE_TEMP_SENSOR,
    CONF_FIREPLACE_THRESHOLD,
)
ROOM_KEYS = (
    CONF_ROOM_NAME,
    CONF_ROOM_CLIMATES,
    CONF_ROOM_USE_GLOBAL,
    CONF_NIGHT_START,
    CONF_NIGHT_END,
    CONF_NIGHT_OFFSET,
    CONF_DAY_TEMP,
    CONF_NIGHT_TEMP,
    CONF_COMFORT_TIME,
    CONF_OPTIMUM_START,
)


def _time(value: Any) -> str:
    """Validate a time and normalize it to HH:MM:SS."""
    try:
        return parse_time(str(value)).strftime("%H:%M:%S")
    except (TypeError, ValueError) as err:
        raise vol.Invalid(f"invalid time: {value}") from err


_TEMP = vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=5, max=30)))
_ENTITY = vol.Any(None, "", vol.Match(r"^[a-z0-9_]+\.[a-z0-9_]+$"))

ROOM_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ROOM_ID): str,
        vol.Optional(CONF_ROOM_NAME): vol.All(str, vol.Strip, vol.Length(min=1, max=64)),
        vol.Optional(CONF_ROOM_CLIMATES): [vol.Match(r"^climate\.[a-z0-9_]+$")],
        vol.Optional(CONF_ROOM_USE_GLOBAL): bool,
        vol.Optional(CONF_NIGHT_START): _time,
        vol.Optional(CONF_NIGHT_END): _time,
        vol.Optional(CONF_NIGHT_OFFSET): vol.All(vol.Coerce(float), vol.Range(min=-10, max=0)),
        vol.Optional(CONF_DAY_TEMP): _TEMP,
        vol.Optional(CONF_NIGHT_TEMP): _TEMP,
        vol.Optional(CONF_COMFORT_TIME): _time,
        vol.Optional(CONF_OPTIMUM_START): bool,
    }
)

SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_OUTDOOR_SENSOR): vol.Match(r"^sensor\.[a-z0-9_]+$"),
        vol.Optional(CONF_GAS_SENSOR): vol.Match(r"^sensor\.[a-z0-9_]+$"),
        vol.Optional(CONF_GAS_PRICE): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10))
        ),
        vol.Optional(CONF_GAS_PRICE_ENTITY): _ENTITY,
        vol.Optional(CONF_HEATING_LIMIT): vol.All(vol.Coerce(float), vol.Range(min=10, max=25)),
        vol.Optional(CONF_BASELINE_DAYS): vol.All(vol.Coerce(int), vol.Range(min=14, max=1095)),
        vol.Optional(CONF_NIGHT_START): _time,
        vol.Optional(CONF_NIGHT_END): _time,
        vol.Optional(CONF_NIGHT_OFFSET): vol.All(vol.Coerce(float), vol.Range(min=-10, max=0)),
        vol.Optional(CONF_FIREPLACE_CLIMATE): _ENTITY,
        vol.Optional(CONF_FIREPLACE_TEMP_SENSOR): _ENTITY,
        vol.Optional(CONF_FIREPLACE_THRESHOLD): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=5)
        ),
    }
)


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register all commands."""
    for command in (
        ws_state,
        ws_history,
        ws_save_room,
        ws_delete_room,
        ws_save_settings,
        ws_set_master,
        ws_set_room_enabled,
        ws_reset_model,
        ws_recalculate_baseline,
    ):
        websocket_api.async_register_command(hass, command)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _entry(hass: HomeAssistant, entry_id: str | None) -> HaClimateConfigEntry | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry_id in (None, entry.entry_id):
            return entry
    return None


def _with_entry(func):
    """Resolve the config entry or send an error."""

    async def wrapper(hass, connection, msg):
        entry = _entry(hass, msg.get("entry_id"))
        if entry is None:
            connection.send_error(msg["id"], "not_found", "HA Climate is not loaded")
            return
        await func(hass, connection, msg, entry)

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


async def _async_update_options(
    hass: HomeAssistant, entry: HaClimateConfigEntry, options: dict[str, Any]
) -> HaClimateCoordinator:
    """Store new options and wait until the entry has been reloaded."""
    old = entry.runtime_data
    hass.config_entries.async_update_entry(entry, options=options)
    async with asyncio.timeout(RELOAD_TIMEOUT):
        while not (
            entry.state is ConfigEntryState.LOADED
            and getattr(entry, "runtime_data", None) is not old
        ):
            await asyncio.sleep(0.05)
    return entry.runtime_data


def _round(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def _room_payload(coordinator: HaClimateCoordinator, room: dict[str, Any]) -> dict[str, Any]:
    room_id = room[CONF_ROOM_ID]
    schedule = coordinator.schedule(room)
    measured = coordinator.room_measurements(room)
    estimate = coordinator.model(room_id).estimate
    outside = coordinator.outdoor_temperature()
    inside = measured["current_temperature"]
    delta_t = inside - outside if inside is not None and outside is not None else None
    next_start = coordinator.next_heating_start(room)
    plan = coordinator.preheat_plan(room)
    return {
        "id": room_id,
        "name": room[CONF_ROOM_NAME],
        "climates": room.get(CONF_ROOM_CLIMATES, []),
        "config": {key: room.get(key) for key in ROOM_KEYS},
        "schedule": {
            "night_start": schedule.start.strftime("%H:%M"),
            "night_end": schedule.end.strftime("%H:%M"),
            "night_offset": schedule.offset,
            "day_temp": schedule.day_temp,
            "night_temp": schedule.night_temp,
            "comfort_time": schedule.comfort_time.strftime("%H:%M"),
            "optimum_start": schedule.optimum_start,
        },
        "enabled": coordinator.room_enabled(room_id),
        "setback_active": coordinator.room_setback_active(room_id),
        "status": coordinator.room_status(room),
        "has_fireplace": coordinator.room_has_fireplace(room),
        "current_temperature": _round(inside, 2),
        "target_temperature": _round(measured["target_temperature"], 2),
        "comfort_temperature": _round(coordinator.comfort_temperature(room), 2),
        "heating": measured["heating"],
        "loops": measured["loops"],
        "model": {
            "cooling_coefficient": _round(estimate.cooling_coefficient, 4),
            "heating_power": _round(estimate.heating_power),
            "cooling_rate": _round(estimate.cooling_rate(delta_t)),
            "heating_rate": _round(estimate.heating_rate(delta_t)),
            "cooling_confidence": estimate.cooling_confidence,
            "heating_confidence": estimate.heating_confidence,
            "confidence": estimate.confidence,
            "observations": estimate.observations,
            "delta_t": _round(delta_t, 2),
        },
        "preheat": {
            "next_heating_start": next_start.isoformat() if next_start else None,
            "lead_minutes": round(plan.lead.total_seconds() / 60) if plan else None,
            "method": plan.method if plan else None,
        },
    }


# ---------------------------------------------------------------------------
# Read commands
# ---------------------------------------------------------------------------
@websocket_api.websocket_command(
    {vol.Required("type"): "ha_climate/state", vol.Optional("entry_id"): str}
)
@websocket_api.async_response
@_with_entry
async def ws_state(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Return everything the panel needs."""
    coordinator = entry.runtime_data
    cfg = coordinator.config
    baseline = coordinator.baseline
    detector = coordinator.fireplace
    settings = {key: cfg.get(key) for key in SETTING_KEYS}
    settings.setdefault(CONF_HEATING_LIMIT, DEFAULT_HEATING_LIMIT)
    for key, default in (
        (CONF_HEATING_LIMIT, DEFAULT_HEATING_LIMIT),
        (CONF_BASELINE_DAYS, DEFAULT_BASELINE_DAYS),
        (CONF_NIGHT_START, DEFAULT_NIGHT_START),
        (CONF_NIGHT_END, DEFAULT_NIGHT_END),
        (CONF_NIGHT_OFFSET, DEFAULT_NIGHT_OFFSET),
        (CONF_FIREPLACE_THRESHOLD, DEFAULT_FIREPLACE_THRESHOLD),
    ):
        if settings.get(key) is None:
            settings[key] = default
    connection.send_result(
        msg["id"],
        {
            "entry_id": entry.entry_id,
            "is_admin": connection.user.is_admin,
            "settings": settings,
            "defaults": {
                "gas_price": DEFAULT_GAS_PRICE,
                "comfort_time": DEFAULT_COMFORT_TIME[:5],
            },
            "master": coordinator.master_enabled,
            "outdoor_temperature": coordinator.outdoor_temperature(),
            "energy": asdict(coordinator.data) if coordinator.data else None,
            "baseline": {
                "m3_per_degree_day": baseline.m3_per_degree_day if baseline else None,
                "days_used": baseline.days_used if baseline else 0,
                "reliable": bool(baseline and baseline.reliable),
                "excluded_fireplace": baseline.excluded_fireplace if baseline else 0,
                "excluded_setback": baseline.excluded_setback if baseline else 0,
                "updated": coordinator.baseline_updated.isoformat()
                if coordinator.baseline_updated
                else None,
            },
            "fireplace": {
                "configured": coordinator.fireplace_configured,
                "active": detector.active,
                "delta_to_target": _round(detector.delta_to_target, 2),
                "rise": _round(detector.rise, 2),
                "minutes_today": coordinator.fireplace_minutes_today(),
            },
            "rooms": [_room_payload(coordinator, room) for room in coordinator.rooms],
            "now": dt_util.now().isoformat(),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/history",
        vol.Optional("entry_id"): str,
        vol.Optional("days", default=60): vol.All(vol.Coerce(int), vol.Range(min=1, max=1095)),
    }
)
@websocket_api.async_response
@_with_entry
async def ws_history(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Return per-day analytics."""
    rows = await entry.runtime_data.async_history(msg["days"])
    connection.send_result(msg["id"], {"days": rows})


# ---------------------------------------------------------------------------
# Write commands (admin only)
# ---------------------------------------------------------------------------
def _validate_room(
    rooms: list[dict[str, Any]], room: dict[str, Any], room_id: str | None
) -> str | None:
    name = room.get(CONF_ROOM_NAME, "").strip()
    if not name:
        return "Geef de ruimte een naam."
    if any(
        r[CONF_ROOM_NAME].casefold() == name.casefold() and r[CONF_ROOM_ID] != room_id
        for r in rooms
    ):
        return "Er bestaat al een ruimte met deze naam."
    climates = room.get(CONF_ROOM_CLIMATES) or []
    if not climates:
        return "Kies minimaal één vloerverwarmingslus."
    used = {
        entity
        for r in rooms
        if r[CONF_ROOM_ID] != room_id
        for entity in r.get(CONF_ROOM_CLIMATES, [])
    }
    if used & set(climates):
        return "Een van deze lussen is al aan een andere ruimte gekoppeld."
    day, night = room.get(CONF_DAY_TEMP), room.get(CONF_NIGHT_TEMP)
    if day is not None and night is not None and night >= day:
        return "De nachttemperatuur moet lager zijn dan de dagtemperatuur."
    return None


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/room/save",
        vol.Optional("entry_id"): str,
        vol.Required("room"): ROOM_SCHEMA,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_save_room(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Create or update a room (partial updates are allowed)."""
    data: dict[str, Any] = dict(msg["room"])
    rooms = [dict(r) for r in entry.runtime_data.rooms]
    room_id = data.pop(CONF_ROOM_ID, None)
    if room_id is not None:
        current = next((r for r in rooms if r[CONF_ROOM_ID] == room_id), None)
        if current is None:
            connection.send_error(msg["id"], "not_found", "Ruimte niet gevonden")
            return
        merged = {**current, **data}
    else:
        room_id = uuid.uuid4().hex[:8]
        merged = {
            CONF_ROOM_ID: room_id,
            CONF_ROOM_USE_GLOBAL: True,
            CONF_COMFORT_TIME: DEFAULT_COMFORT_TIME,
            CONF_OPTIMUM_START: False,
            **data,
        }
        current = None
    if error := _validate_room(rooms, merged, room_id):
        connection.send_error(msg["id"], "invalid", error)
        return
    if current is None:
        rooms.append(merged)
    else:
        current.clear()
        current.update(merged)
    coordinator = await _async_update_options(
        hass, entry, {**entry.options, CONF_ROOMS: rooms}
    )
    if (room := coordinator.room(room_id)) is not None:
        await coordinator.async_apply_day_temperature(room)
    connection.send_result(msg["id"], {"room_id": room_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/room/delete",
        vol.Optional("entry_id"): str,
        vol.Required("room_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_delete_room(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Delete a room; lowered loops are restored by the coordinator."""
    rooms = [r for r in entry.runtime_data.rooms if r[CONF_ROOM_ID] != msg["room_id"]]
    await _async_update_options(hass, entry, {**entry.options, CONF_ROOMS: rooms})
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/settings/save",
        vol.Optional("entry_id"): str,
        vol.Required("settings"): SETTINGS_SCHEMA,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_save_settings(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Save general, night and fireplace settings."""
    options = dict(entry.options)
    for key, value in msg["settings"].items():
        if value in (None, ""):
            options.pop(key, None)
            if key in entry.data and key not in (CONF_OUTDOOR_SENSOR, CONF_GAS_SENSOR):
                options[key] = None
        else:
            options[key] = value
    merged = {**entry.data, **options}
    if merged.get(CONF_OUTDOOR_SENSOR) == merged.get(CONF_GAS_SENSOR):
        connection.send_error(
            msg["id"], "invalid", "Buitentemperatuur en gas moeten verschillend zijn."
        )
        return
    await _async_update_options(hass, entry, options)
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/master/set",
        vol.Optional("entry_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_set_master(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Switch the night setback for all thermostats."""
    await entry.runtime_data.async_set_master(msg["enabled"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/room/enable",
        vol.Optional("entry_id"): str,
        vol.Required("room_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_set_room_enabled(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Switch the night setback of one room."""
    await entry.runtime_data.async_set_room(msg["room_id"], msg["enabled"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/model/reset",
        vol.Optional("entry_id"): str,
        vol.Required("room_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_reset_model(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Forget the learned thermal model of a room."""
    entry.runtime_data.reset_model(msg["room_id"])
    entry.runtime_data.async_update_listeners()
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {vol.Required("type"): "ha_climate/baseline/recalculate", vol.Optional("entry_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_recalculate_baseline(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Recalculate the baseline."""
    coordinator = entry.runtime_data
    await coordinator.async_recalculate_baseline()
    await coordinator.async_refresh()
    connection.send_result(msg["id"], {})
