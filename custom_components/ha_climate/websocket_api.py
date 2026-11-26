"""WebSocket API used by the HA Climate sidebar panel."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
import logging
from typing import Any
import uuid

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .calculations import parse_time
from .const import (
    BOILER_BINARY_KEYS,
    BOILER_KEYS,
    CONF_BASELINE_DAYS,
    CONF_COMFORT_TIME,
    CONF_DAY_TEMP,
    CONF_FIREPLACE_CLIMATE,
    CONF_FIREPLACE_TEMP_SENSOR,
    CONF_FIREPLACE_THRESHOLD,
    CONF_GAS_PRICE,
    CONF_GAS_FIXED_COSTS,
    CONF_DD_INDOOR_CORRECTION,
    CONF_DD_REFERENCE_TEMP,
    CONF_GAS_FIXED_COSTS_UNIT,
    CONF_GAS_PRICE_ENTITY,
    CONF_GAS_SENSOR,
    CONF_HEATING_LIMIT,
    CONF_NIGHT_END,
    CONF_NIGHT_OFFSET,
    CONF_NIGHT_START,
    CONF_NIGHT_TEMP,
    CONF_OPTIMUM_START,
    CONF_OUTDOOR_SENSOR,
    CONF_ROOM_AIRCOS,
    CONF_ROOM_CLIMATES,
    CONF_ROOM_ID,
    CONF_ROOM_NAME,
    CONF_ROOM_USE_GLOBAL,
    CONF_ROOM_VALVES,
    CONF_ROOMS,
    CONF_SAVINGS_START,
    DEFAULT_BASELINE_DAYS,
    DEFAULT_DD_REFERENCE_TEMP,
    DEFAULT_COMFORT_TIME,
    DEFAULT_FIXED_COSTS_UNIT,
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
    CONF_GAS_FIXED_COSTS,
    CONF_GAS_FIXED_COSTS_UNIT,
    CONF_GAS_PRICE_ENTITY,
    CONF_HEATING_LIMIT,
    CONF_BASELINE_DAYS,
    CONF_SAVINGS_START,
    CONF_DD_INDOOR_CORRECTION,
    CONF_DD_REFERENCE_TEMP,
    CONF_NIGHT_START,
    CONF_NIGHT_END,
    CONF_NIGHT_OFFSET,
    CONF_FIREPLACE_CLIMATE,
    CONF_FIREPLACE_TEMP_SENSOR,
    CONF_FIREPLACE_THRESHOLD,
    *BOILER_KEYS,
)
ROOM_KEYS = (
    CONF_ROOM_NAME,
    CONF_ROOM_CLIMATES,
    CONF_ROOM_AIRCOS,
    CONF_ROOM_VALVES,
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


def _date(value: Any) -> str:
    """Validate an ISO date (YYYY-MM-DD)."""
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError as err:
        raise vol.Invalid(f"invalid date: {value}") from err


_TEMP = vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=5, max=30)))
_ENTITY = vol.Any(None, "", vol.Match(r"^[a-z0-9_]+\.[a-z0-9_]+$"))
_SENSOR = vol.Any(None, "", vol.Match(r"^sensor\.[a-z0-9_]+$"))
_BINARY = vol.Any(None, "", vol.Match(r"^binary_sensor\.[a-z0-9_]+$"))

ROOM_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ROOM_ID): str,
        vol.Optional(CONF_ROOM_NAME): vol.All(str, vol.Strip, vol.Length(min=1, max=64)),
        vol.Optional(CONF_ROOM_CLIMATES): [vol.Match(r"^climate\.[a-z0-9_]+$")],
        vol.Optional(CONF_ROOM_AIRCOS): [vol.Match(r"^climate\.[a-z0-9_]+$")],
        vol.Optional(CONF_ROOM_VALVES): [vol.Match(r"^sensor\.[a-z0-9_]+$")],
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
        vol.Optional(CONF_BASELINE_DAYS): vol.All(vol.Coerce(int), vol.Range(min=0, max=3650)),
        vol.Optional(CONF_GAS_FIXED_COSTS): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=500))
        ),
        vol.Optional(CONF_GAS_FIXED_COSTS_UNIT): vol.In(["month", "day"]),
        vol.Optional(CONF_SAVINGS_START): vol.Any(None, "", _date),
        vol.Optional(CONF_DD_INDOOR_CORRECTION): bool,
        vol.Optional(CONF_DD_REFERENCE_TEMP): vol.All(
            vol.Coerce(float), vol.Range(min=15, max=25)
        ),
        vol.Optional(CONF_NIGHT_START): _time,
        vol.Optional(CONF_NIGHT_END): _time,
        vol.Optional(CONF_NIGHT_OFFSET): vol.All(vol.Coerce(float), vol.Range(min=-10, max=0)),
        vol.Optional(CONF_FIREPLACE_CLIMATE): _ENTITY,
        vol.Optional(CONF_FIREPLACE_TEMP_SENSOR): _ENTITY,
        vol.Optional(CONF_FIREPLACE_THRESHOLD): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=5)
        ),
        **{
            vol.Optional(key): _BINARY if key in BOILER_BINARY_KEYS else _SENSOR
            for key in BOILER_KEYS
        },
    }
)


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register all commands."""
    for command in (
        ws_state,
        ws_export,
        ws_set_room_temperature,
        ws_airco,
        ws_freeze_baseline,
        ws_history,
        ws_boiler_trace,
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
    if not hass.config_entries.async_update_entry(entry, options=options):
        # Nothing changed, so there is no reload to wait for.
        return old
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
        "aircos": measured["aircos"],
        "valves": measured["valves"],
        "valve": _round(measured["valve"], 1),
        "valve_max": _round(measured["valve_max"], 1),
        "airco_active": measured["airco_active"],
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
        "model_status": coordinator.model_status(room_id),
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
        (CONF_GAS_FIXED_COSTS, 0.0),
        (CONF_GAS_FIXED_COSTS_UNIT, DEFAULT_FIXED_COSTS_UNIT),
        (CONF_DD_INDOOR_CORRECTION, False),
        (CONF_DD_REFERENCE_TEMP, DEFAULT_DD_REFERENCE_TEMP),
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
                "excluded_warm": baseline.excluded_warm if baseline else 0,
                "excluded_invalid": baseline.excluded_invalid if baseline else 0,
                "first_day": baseline.first_day.isoformat()
                if baseline and baseline.first_day
                else None,
                "last_day": baseline.last_day.isoformat()
                if baseline and baseline.last_day
                else None,
                **coordinator.baseline_info(),
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
            "boiler": coordinator.boiler_status(),
            "rooms": [_room_payload(coordinator, room) for room in coordinator.rooms],
            "ranking": coordinator.room_ranking(),
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


@websocket_api.websocket_command(
    {vol.Required("type"): "ha_climate/boiler/trace", vol.Optional("entry_id"): str}
)
@websocket_api.async_response
@_with_entry
async def ws_boiler_trace(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Return the last 24 h of the boiler sensors (5 minute grid)."""
    coordinator = entry.runtime_data
    if not coordinator.boiler_configured:
        connection.send_result(msg["id"], {"points": []})
        return
    try:
        points = await coordinator.async_boiler_trace()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Reading boiler history failed")
        points = []
    connection.send_result(msg["id"], {"points": points})


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
    aircos = set(room.get(CONF_ROOM_AIRCOS) or [])
    used_any = {
        entity
        for r in rooms
        if r[CONF_ROOM_ID] != room_id
        for key in (CONF_ROOM_CLIMATES, CONF_ROOM_AIRCOS)
        for entity in r.get(key, [])
    }
    if aircos & (used_any | set(climates)):
        return "Een airco is al als lus of in een andere kamer gekoppeld."
    valves = set(room.get(CONF_ROOM_VALVES) or [])
    used_valves = {
        entity
        for r in rooms
        if r[CONF_ROOM_ID] != room_id
        for entity in r.get(CONF_ROOM_VALVES, [])
    }
    if valves & used_valves:
        return "Een klepstand-sensor is al aan een andere ruimte gekoppeld."
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
    await coordinator.async_recalculate()
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {vol.Required("type"): "ha_climate/export", vol.Optional("entry_id"): str}
)
@websocket_api.async_response
@_with_entry
async def ws_export(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Return all permanently stored days for the CSV export."""
    coordinator = entry.runtime_data
    connection.send_result(
        msg["id"],
        {
            "days": coordinator.export_rows(),
            "gas_price": coordinator.data.gas_price if coordinator.data else None,
            "baseline": coordinator.effective_baseline,
        },
    )


def _room_or_error(connection, msg, coordinator: HaClimateCoordinator):
    room = coordinator.room(msg["room_id"])
    if room is None:
        connection.send_error(msg["id"], "not_found", "Ruimte niet gevonden")
    return room


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/room/set_temperature",
        vol.Optional("entry_id"): str,
        vol.Required("room_id"): str,
        vol.Required("temperature"): vol.All(vol.Coerce(float), vol.Range(min=5, max=30)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_set_room_temperature(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Set all floor heating loops of a room at once."""
    coordinator = entry.runtime_data
    if (room := _room_or_error(connection, msg, coordinator)) is None:
        return
    changed = await coordinator.async_set_room_temperature(room, msg["temperature"])
    connection.send_result(msg["id"], {"entities": changed})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/airco",
        vol.Optional("entry_id"): str,
        vol.Required("room_id"): str,
        vol.Optional("mode"): vol.In(["off", "cool", "boost"]),
        vol.Optional("temperature"): vol.All(vol.Coerce(float), vol.Range(min=10, max=32)),
        vol.Optional("entity_ids"): [str],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_airco(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Control the aircos of a room (separate from the floor heating)."""
    coordinator = entry.runtime_data
    if (room := _room_or_error(connection, msg, coordinator)) is None:
        return
    if "mode" not in msg and "temperature" not in msg:
        connection.send_error(msg["id"], "invalid", "Geef een modus of temperatuur op")
        return
    try:
        await coordinator.async_airco(
            room, msg.get("mode"), msg.get("temperature"), msg.get("entity_ids")
        )
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "failed", str(err))
        return
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ha_climate/baseline/freeze",
        vol.Optional("entry_id"): str,
        vol.Required("freeze"): bool,
        vol.Optional("savings_start"): vol.Any(None, "", _date),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_entry
async def ws_freeze_baseline(hass, connection, msg, entry: HaClimateConfigEntry) -> None:
    """Freeze/unfreeze the baseline and optionally set the savings start date."""
    coordinator = entry.runtime_data
    try:
        coordinator.freeze_baseline(msg["freeze"])
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "failed", str(err))
        return
    if "savings_start" in msg:
        options = dict(entry.options)
        if msg["savings_start"]:
            options[CONF_SAVINGS_START] = msg["savings_start"]
        else:
            options.pop(CONF_SAVINGS_START, None)
        if options != dict(entry.options):
            coordinator = await _async_update_options(hass, entry, options)
    await coordinator.async_recalculate_baseline()
    await coordinator.async_refresh()
    connection.send_result(msg["id"], {"baseline": coordinator.baseline_info()})
