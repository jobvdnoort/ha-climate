"""Coordinator for HA Climate.

Combines energy statistics (degree days, baseline, savings), the night setback
with optimum start, the self-learning thermal model per room and the fireplace
detection.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .calculations import (
    BaselineResult,
    DayRecord,
    FireplaceDetector,
    accumulated_degree_days,
    calculate_baseline,
    day_fraction,
    degree_days,
    expected_gas,
    fireplace_excluded_days,
    gas_savings,
    money,
    parse_time,
    restore_value,
    setback_target,
)
from .const import (
    BASELINE_MIN_DAYS,
    BASELINE_MIN_DEGREE_DAYS,
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
    FIREPLACE_EXCLUDE_MINUTES,
    FIREPLACE_HEATING_COOLDOWN,
    FIREPLACE_RISE_WINDOW,
    HEATING_ACTIONS,
    HISTORY_RETENTION_DAYS,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .statistics import async_daily_history, async_period_value
from .thermal import PreheatPlan, RoomThermalModel, night_period, preheat_lead

_LOGGER = logging.getLogger(__name__)

type HaClimateConfigEntry = ConfigEntry[HaClimateCoordinator]


def _float_or_none(value: Any) -> float | None:
    """Convert a state/attribute value to float."""
    if value in (None, STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def merged_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return config entry data with options applied on top."""
    return {**entry.data, **entry.options}


@dataclass(slots=True)
class RoomSchedule:
    """Effective schedule of a room."""

    start: time
    end: time
    offset: float
    day_temp: float | None
    night_temp: float | None
    comfort_time: time
    optimum_start: bool


@dataclass(slots=True)
class EnergyData:
    """Values exposed by the sensors."""

    mean_temp_today: float | None = None
    mean_temp_yesterday: float | None = None
    degree_days_today: float | None = None
    degree_days_today_forecast: float | None = None
    degree_days_yesterday: float | None = None
    gas_today: float | None = None
    gas_yesterday: float | None = None
    expected_today: float | None = None
    expected_yesterday: float | None = None
    saved_today: float | None = None
    saved_yesterday: float | None = None
    saved_total: float | None = None
    saved_total_days: int = 0
    gas_price: float = DEFAULT_GAS_PRICE
    gas_price_source: str = "standaard"


class HaClimateCoordinator(DataUpdateCoordinator[EnergyData]):
    """Central coordinator of the integration."""

    config_entry: HaClimateConfigEntry

    def __init__(self, hass: HomeAssistant, entry: HaClimateConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        self._stored: dict[str, Any] = {}
        self._unsub: list[CALLBACK_TYPE] = []
        self._setback_lock = asyncio.Lock()
        self.baseline: BaselineResult | None = None
        self.baseline_updated: datetime | None = None
        self.models: dict[str, RoomThermalModel] = {}
        self.plans: dict[str, dict[str, Any]] = {}
        self.fireplace = FireplaceDetector(
            threshold=float(
                self.config.get(CONF_FIREPLACE_THRESHOLD, DEFAULT_FIREPLACE_THRESHOLD)
            ),
            rise_window=FIREPLACE_RISE_WINDOW,
            heating_cooldown=FIREPLACE_HEATING_COOLDOWN,
        )

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    @property
    def config(self) -> dict[str, Any]:
        """Return the merged configuration."""
        return merged_config(self.config_entry)

    @property
    def heating_limit(self) -> float:
        """Return the heating limit (stookgrens)."""
        return float(self.config.get(CONF_HEATING_LIMIT, DEFAULT_HEATING_LIMIT))

    @property
    def rooms(self) -> list[dict[str, Any]]:
        """Return the configured rooms."""
        return list(self.config.get(CONF_ROOMS, []))

    def room(self, room_id: str) -> dict[str, Any] | None:
        """Return a room by id."""
        return next((r for r in self.rooms if r[CONF_ROOM_ID] == room_id), None)

    @property
    def fireplace_configured(self) -> bool:
        """Return whether a fireplace thermostat is configured."""
        return bool(self.config.get(CONF_FIREPLACE_CLIMATE))

    def schedule(self, room: dict[str, Any]) -> RoomSchedule:
        """Return the effective schedule of a room."""
        cfg = self.config
        source = cfg if room.get(CONF_ROOM_USE_GLOBAL, True) else room
        return RoomSchedule(
            start=parse_time(source.get(CONF_NIGHT_START) or DEFAULT_NIGHT_START),
            end=parse_time(source.get(CONF_NIGHT_END) or DEFAULT_NIGHT_END),
            offset=float(source.get(CONF_NIGHT_OFFSET, DEFAULT_NIGHT_OFFSET)),
            day_temp=_float_or_none(room.get(CONF_DAY_TEMP)),
            night_temp=_float_or_none(room.get(CONF_NIGHT_TEMP)),
            comfort_time=parse_time(room.get(CONF_COMFORT_TIME) or DEFAULT_COMFORT_TIME),
            optimum_start=bool(room.get(CONF_OPTIMUM_START, False)),
        )

    # Backwards compatible name used by entities.
    night_settings = schedule

    def outdoor_temperature(self) -> float | None:
        """Return the current outdoor temperature."""
        state = self.hass.states.get(self.config[CONF_OUTDOOR_SENSOR])
        return _float_or_none(state.state) if state else None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    async def async_load(self) -> None:
        """Load persisted state."""
        stored = await self._store.async_load() or {}
        stored.setdefault("master", True)
        stored.setdefault("room_enabled", {})
        stored.setdefault("room_state", {})
        stored.setdefault("fireplace_minutes", {})
        stored.setdefault("setback_dates", [])
        stored.setdefault("savings", {})
        stored.setdefault("savings_offset", 0.0)
        stored.setdefault("meter_start", {})
        stored.setdefault("baseline", None)
        stored.setdefault("models", {})
        stored.setdefault(
            "installed_on",
            min([*stored["savings"].keys(), dt_util.now().date().isoformat()]),
        )
        self._stored = stored
        if (cached := stored.get("baseline")) is not None:
            self.baseline = _baseline_from_dict(cached)
            self.baseline_updated = dt_util.parse_datetime(cached.get("updated", ""))
        for room in self.rooms:
            self.models[room[CONF_ROOM_ID]] = RoomThermalModel.from_dict(
                stored["models"].get(room[CONF_ROOM_ID])
            )

    @callback
    def _async_save(self) -> None:
        """Schedule a save of the persisted state."""
        self._prune_history()
        self._store.async_delay_save(self._data_to_save, 10)

    def _data_to_save(self) -> dict[str, Any]:
        self._stored["models"] = {
            room_id: model.as_dict() for room_id, model in self.models.items()
        }
        return self._stored

    def _prune_history(self) -> None:
        cutoff = (dt_util.now().date() - timedelta(days=HISTORY_RETENTION_DAYS)).isoformat()
        for key in ("fireplace_minutes", "meter_start"):
            self._stored[key] = {
                day: value for day, value in self._stored[key].items() if day >= cutoff
            }
        self._stored["setback_dates"] = sorted(
            day for day in set(self._stored["setback_dates"]) if day >= cutoff
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @callback
    def async_start(self) -> None:
        """Start listeners and timers."""
        self._unsub.append(
            async_track_time_change(self.hass, self._async_tick, second=0)
        )
        # Recalculate the baseline every night, after the day statistics are compiled.
        self._unsub.append(
            async_track_time_change(
                self.hass, self._async_nightly_baseline, hour=0, minute=20, second=30
            )
        )
        tracked = [
            entity
            for entity in (
                self.config.get(CONF_FIREPLACE_CLIMATE),
                self.config.get(CONF_FIREPLACE_TEMP_SENSOR),
            )
            if entity
        ]
        if tracked:
            self._unsub.append(
                async_track_state_change_event(
                    self.hass, tracked, self._async_fireplace_state_changed
                )
            )
        self._unsub.append(async_at_started(self.hass, self._async_started))

    async def _async_started(self, _hass: HomeAssistant) -> None:
        """Run once Home Assistant has fully started."""
        await self.async_recalculate_baseline()
        await self._async_tick(dt_util.now())
        # Sensors may not have had a state yet during the first refresh.
        await self.async_request_refresh()

    @callback
    def async_stop(self) -> None:
        """Stop listeners and timers."""
        while self._unsub:
            self._unsub.pop()()

    async def async_shutdown(self) -> None:
        """Flush state on shutdown."""
        self.async_stop()
        await self._store.async_save(self._data_to_save())
        await super().async_shutdown()

    # ------------------------------------------------------------------
    # Switch state
    # ------------------------------------------------------------------
    @property
    def master_enabled(self) -> bool:
        """Return whether the night setback is enabled for all thermostats."""
        return bool(self._stored.get("master", True))

    def room_enabled(self, room_id: str) -> bool:
        """Return whether the night setback is enabled for a room."""
        return bool(self._stored["room_enabled"].get(room_id, True))

    def room_setback_active(self, room_id: str) -> bool:
        """Return whether the night setback is currently applied in a room."""
        return bool(self._stored["room_state"].get(room_id, {}).get("active"))

    async def async_set_master(self, enabled: bool) -> None:
        """Enable/disable the night setback for all thermostats."""
        self._stored["master"] = enabled
        self._async_save()
        await self._async_evaluate_setback(dt_util.now())
        self.async_update_listeners()

    async def async_set_room(self, room_id: str, enabled: bool) -> None:
        """Enable/disable the night setback for a single room."""
        self._stored["room_enabled"][room_id] = enabled
        self._async_save()
        await self._async_evaluate_setback(dt_util.now())
        self.async_update_listeners()

    # ------------------------------------------------------------------
    # Periodic tick (every minute)
    # ------------------------------------------------------------------
    async def _async_tick(self, now: datetime) -> None:
        """Evaluate fireplace, thermal model and night setback."""
        now = dt_util.as_local(now)
        if self.fireplace_configured:
            self._evaluate_fireplace(now)
            if self.fireplace.active:
                day = now.date().isoformat()
                minutes = self._stored["fireplace_minutes"]
                minutes[day] = minutes.get(day, 0) + 1
                self._async_save()
        self._learn(now)
        await self._async_evaluate_setback(now)
        self.async_update_listeners()

    async def _async_nightly_baseline(self, _now: datetime) -> None:
        await self.async_recalculate_baseline()
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Room measurements
    # ------------------------------------------------------------------
    def room_measurements(self, room: dict[str, Any]) -> dict[str, Any]:
        """Return the live measurements of the loops in a room."""
        loops = []
        for entity_id in room.get(CONF_ROOM_CLIMATES, []):
            state = self.hass.states.get(entity_id)
            if state is None:
                loops.append({"entity_id": entity_id, "available": False})
                continue
            loops.append(
                {
                    "entity_id": entity_id,
                    "name": state.attributes.get("friendly_name", entity_id),
                    "available": state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN),
                    "hvac_mode": state.state,
                    "hvac_action": state.attributes.get(ATTR_HVAC_ACTION),
                    "current_temperature": _float_or_none(
                        state.attributes.get(ATTR_CURRENT_TEMPERATURE)
                    ),
                    "target_temperature": _float_or_none(
                        state.attributes.get(ATTR_TEMPERATURE)
                    ),
                    "min_temp": _float_or_none(state.attributes.get(ATTR_MIN_TEMP)),
                    "max_temp": _float_or_none(state.attributes.get(ATTR_MAX_TEMP)),
                }
            )
        available = [loop for loop in loops if loop.get("available")]
        actions = [loop["hvac_action"] for loop in available if loop.get("hvac_action")]
        return {
            "loops": loops,
            "current_temperature": _mean([loop["current_temperature"] for loop in available]),
            "target_temperature": _mean([loop["target_temperature"] for loop in available]),
            "heating": (any(a in HEATING_ACTIONS for a in actions) if actions else None),
        }

    def room_has_fireplace(self, room: dict[str, Any]) -> bool:
        """Return whether the fireplace thermostat belongs to this room."""
        return self.config.get(CONF_FIREPLACE_CLIMATE) in room.get(CONF_ROOM_CLIMATES, [])

    # ------------------------------------------------------------------
    # Thermal model
    # ------------------------------------------------------------------
    def model(self, room_id: str) -> RoomThermalModel:
        """Return (and create) the thermal model of a room."""
        return self.models.setdefault(room_id, RoomThermalModel())

    def _learn(self, now: datetime) -> None:
        outside = self.outdoor_temperature()
        learned = False
        for room in self.rooms:
            measured = self.room_measurements(room)
            valid = not (self.room_has_fireplace(room) and self.fireplace.active)
            if self.model(room[CONF_ROOM_ID]).add_sample(
                now, measured["current_temperature"], outside, measured["heating"], valid
            ):
                learned = True
        if learned:
            self._async_save()

    def reset_model(self, room_id: str) -> None:
        """Forget what was learned for a room."""
        self.model(room_id).reset()
        self._async_save()

    def comfort_temperature(self, room: dict[str, Any]) -> float | None:
        """Return the temperature the room should have during the day."""
        schedule = self.schedule(room)
        if schedule.day_temp is not None:
            return schedule.day_temp
        state = self._stored["room_state"].get(room[CONF_ROOM_ID], {})
        if state.get("active") and state.get("entities"):
            return _mean([v["original"] for v in state["entities"].values()])
        return self.room_measurements(room)["target_temperature"]

    def preheat_plan(self, room: dict[str, Any]) -> PreheatPlan | None:
        """Return the optimum start plan for a room under current conditions."""
        target = self.comfort_temperature(room)
        if target is None:
            return None
        return preheat_lead(
            self.room_measurements(room)["current_temperature"],
            target,
            self.outdoor_temperature(),
            self.model(room[CONF_ROOM_ID]).estimate,
        )

    # ------------------------------------------------------------------
    # Night setback & optimum start
    # ------------------------------------------------------------------
    def _night_window(
        self, room: dict[str, Any], now: datetime, record: bool = True
    ) -> tuple[datetime, datetime, datetime]:
        """Return (setback start, restore moment, comfort moment) for the current night."""
        schedule = self.schedule(room)
        window_start, window_end = night_period(now, schedule.start, schedule.end)
        if not schedule.optimum_start:
            return window_start, window_end, window_end
        _, comfort = night_period(now, schedule.start, schedule.comfort_time)
        plan = self.preheat_plan(room)
        restore_at = comfort - plan.lead if plan else window_end
        if record:
            self.plans[room[CONF_ROOM_ID]] = {
                "comfort_at": comfort.isoformat(),
                "heating_start": restore_at.isoformat(),
                "lead_minutes": round(plan.lead.total_seconds() / 60) if plan else None,
                "method": plan.method if plan else "geen doeltemperatuur",
                "confidence": self.model(room[CONF_ROOM_ID]).estimate.confidence,
            }
        return window_start, restore_at, comfort

    def next_heating_start(self, room: dict[str, Any]) -> datetime | None:
        """Return the (planned) optimum start moment of the coming morning."""
        if not self.schedule(room).optimum_start:
            return None
        now = dt_util.now()
        window_start, restore_at, comfort = self._night_window(room, now, record=False)
        if comfort <= now:  # this morning is over: plan for the next night
            _, restore_at, _ = self._night_window(
                room, window_start + timedelta(days=1), record=False
            )
        return restore_at

    async def _async_evaluate_setback(self, now: datetime) -> None:
        """Apply or restore the night setback for every room."""
        async with self._setback_lock:
            await self._async_evaluate_setback_locked(dt_util.as_local(now))

    async def _async_evaluate_setback_locked(self, now: datetime) -> None:
        room_state: dict[str, Any] = self._stored["room_state"]
        configured = {room[CONF_ROOM_ID]: room for room in self.rooms}
        changed = False

        # Rooms that were removed from the configuration while lowered.
        for room_id in [rid for rid in room_state if rid not in configured]:
            if room_state[room_id].get("active"):
                await self._async_restore_room(room_state[room_id], None)
            room_state.pop(room_id)
            changed = True

        for room_id, room in configured.items():
            schedule = self.schedule(room)
            window_start, restore_at, _ = self._night_window(room, now)
            state = room_state.setdefault(
                room_id, {"active": False, "entities": {}, "restored_at": None}
            )
            restored_at = dt_util.parse_datetime(state.get("restored_at") or "")
            already_restored = restored_at is not None and restored_at >= window_start
            switches_on = self.master_enabled and self.room_enabled(room_id)
            wanted = (
                switches_on
                and window_start <= now < restore_at
                and not already_restored
            )
            if wanted and not state["active"]:
                await self._async_apply_room(room, schedule, state)
                changed = True
            elif not wanted and state["active"]:
                await self._async_restore_room(state, schedule.day_temp)
                if switches_on:
                    # Restored by the schedule: do not lower again this night.
                    state["restored_at"] = now.isoformat()
                changed = True
            if state["active"]:
                day = now.date().isoformat()
                if day not in self._stored["setback_dates"]:
                    self._stored["setback_dates"].append(day)
                    changed = True

        if changed:
            self._async_save()

    async def _async_apply_room(
        self, room: dict[str, Any], schedule: RoomSchedule, state: dict[str, Any]
    ) -> None:
        """Lower the target temperature of all loops in a room."""
        entities: dict[str, dict[str, float]] = {}
        for entity_id in room.get(CONF_ROOM_CLIMATES, []):
            climate = self.hass.states.get(entity_id)
            if climate is None or climate.state in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
                HVACMode.OFF,
            ):
                continue
            original = _float_or_none(climate.attributes.get(ATTR_TEMPERATURE))
            if original is None:
                continue
            min_temp = _float_or_none(climate.attributes.get(ATTR_MIN_TEMP))
            if schedule.night_temp is not None:
                target = (
                    max(schedule.night_temp, min_temp)
                    if min_temp is not None
                    else schedule.night_temp
                )
            else:
                target = setback_target(
                    original,
                    schedule.offset,
                    min_temp,
                    _float_or_none(climate.attributes.get(ATTR_TARGET_TEMP_STEP)),
                )
            if target >= original:
                # Already at or below the night temperature: nothing to lower.
                entities[entity_id] = {"original": original, "applied": original}
                continue
            if await self._async_set_temperature(entity_id, target):
                entities[entity_id] = {"original": original, "applied": target}
        # Only mark as active when something was handled, otherwise retry next tick.
        state["active"] = bool(entities)
        state["entities"] = entities
        _LOGGER.debug("Night setback applied in %s: %s", room.get(CONF_ROOM_NAME), entities)

    async def _async_restore_room(
        self, state: dict[str, Any], day_temp: float | None
    ) -> None:
        """Restore the comfort temperature of all loops in a room."""
        for entity_id, values in state.get("entities", {}).items():
            climate = self.hass.states.get(entity_id)
            if climate is None or climate.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            comfort = day_temp if day_temp is not None else values["original"]
            target = restore_value(
                _float_or_none(climate.attributes.get(ATTR_TEMPERATURE)),
                values["applied"],
                comfort,
            )
            if target is not None and target != _float_or_none(
                climate.attributes.get(ATTR_TEMPERATURE)
            ):
                await self._async_set_temperature(entity_id, target)
        state["active"] = False
        state["entities"] = {}

    async def _async_set_temperature(self, entity_id: str, temperature: float) -> bool:
        try:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_TEMPERATURE,
                {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: temperature},
                blocking=True,
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Could not set %s to %.1f °C: %s", entity_id, temperature, err)
            return False
        return True

    async def async_apply_day_temperature(self, room: dict[str, Any]) -> None:
        """Set the day temperature right away (when not in night setback)."""
        schedule = self.schedule(room)
        if schedule.day_temp is None or self.room_setback_active(room[CONF_ROOM_ID]):
            return
        for entity_id in room.get(CONF_ROOM_CLIMATES, []):
            climate = self.hass.states.get(entity_id)
            if climate is None or climate.state in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
                HVACMode.OFF,
            ):
                continue
            if _float_or_none(climate.attributes.get(ATTR_TEMPERATURE)) != schedule.day_temp:
                await self._async_set_temperature(entity_id, schedule.day_temp)

    def comfort_target(self, entity_id: str) -> float | None:
        """Return the comfort target of a loop (the original one during setback)."""
        for state in self._stored["room_state"].values():
            if state.get("active") and entity_id in state.get("entities", {}):
                return state["entities"][entity_id]["original"]
        climate = self.hass.states.get(entity_id)
        if climate is None:
            return None
        return _float_or_none(climate.attributes.get(ATTR_TEMPERATURE))

    def room_status(self, room: dict[str, Any]) -> str:
        """Return a single status for a room."""
        room_id = room[CONF_ROOM_ID]
        measured = self.room_measurements(room)
        if not any(loop.get("available") for loop in measured["loops"]):
            return "unavailable"
        if self.room_has_fireplace(room) and self.fireplace.active:
            return "fireplace"
        state = self._stored["room_state"].get(room_id, {})
        if state.get("active"):
            return "setback"
        restored_at = dt_util.parse_datetime(state.get("restored_at") or "")
        schedule = self.schedule(room)
        if schedule.optimum_start and restored_at is not None:
            now = dt_util.now()
            window_start, comfort = night_period(now, schedule.start, schedule.comfort_time)
            if window_start <= restored_at <= now < comfort:
                return "preheating"
        if measured["heating"]:
            return "heating"
        if all(loop.get("hvac_mode") == HVACMode.OFF for loop in measured["loops"]):
            return "off"
        return "idle"

    # ------------------------------------------------------------------
    # Fireplace
    # ------------------------------------------------------------------
    @callback
    def _async_fireplace_state_changed(self, _event: Event) -> None:
        self._evaluate_fireplace(dt_util.now())
        self.async_update_listeners()

    def _evaluate_fireplace(self, now: datetime) -> None:
        entity_id = self.config.get(CONF_FIREPLACE_CLIMATE)
        if not entity_id:
            return
        climate = self.hass.states.get(entity_id)
        if climate is None:
            self.fireplace.update(now, None, None, None)
            return
        current = _float_or_none(climate.attributes.get(ATTR_CURRENT_TEMPERATURE))
        if (sensor_id := self.config.get(CONF_FIREPLACE_TEMP_SENSOR)) and (
            sensor := self.hass.states.get(sensor_id)
        ):
            current = _float_or_none(sensor.state)
        self.fireplace.update(
            now,
            current,
            self.comfort_target(entity_id),
            climate.attributes.get(ATTR_HVAC_ACTION),
        )

    def fireplace_minutes_today(self) -> int:
        """Return the number of minutes the fireplace burned today."""
        return int(self._stored["fireplace_minutes"].get(dt_util.now().date().isoformat(), 0))

    # ------------------------------------------------------------------
    # Baseline & history
    # ------------------------------------------------------------------
    def _excluded_days(self) -> tuple[set[date], set[date]]:
        return (
            fireplace_excluded_days(
                self._stored["fireplace_minutes"], FIREPLACE_EXCLUDE_MINUTES
            ),
            {date.fromisoformat(d) for d in self._stored["setback_dates"]},
        )

    async def _async_records(self, days: int) -> list[DayRecord]:
        cfg = self.config
        return await async_daily_history(
            self.hass, cfg[CONF_OUTDOOR_SENSOR], cfg[CONF_GAS_SENSOR], days
        )

    async def async_recalculate_baseline(self) -> BaselineResult | None:
        """Recalculate the baseline from the recorder's long-term statistics."""
        try:
            records = await self._async_records(
                int(self.config.get(CONF_BASELINE_DAYS, DEFAULT_BASELINE_DAYS))
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Reading long-term statistics failed")
            return self.baseline

        fireplace_days, setback_days = self._excluded_days()
        result = calculate_baseline(
            records,
            heating_limit=self.heating_limit,
            fireplace_days=fireplace_days,
            setback_days=setback_days,
            min_degree_days=BASELINE_MIN_DEGREE_DAYS,
            min_days=BASELINE_MIN_DAYS,
        )
        previous = self.baseline
        if result.reliable or previous is None or not previous.reliable:
            # Keep a previous reliable baseline when too few clean days remain
            # (e.g. when the night setback has been running for a long time).
            self.baseline = result if result.is_valid or previous is None else previous
            self.baseline_updated = dt_util.now()
            self._stored["baseline"] = {
                **_baseline_to_dict(self.baseline),
                "updated": self.baseline_updated.isoformat(),
            }
        else:
            _LOGGER.info(
                "Only %s usable days found, keeping previous baseline", result.days_used
            )
        self._backfill_savings(records)
        self._async_save()
        _LOGGER.debug("Baseline: %s", self.baseline)
        self.async_update_listeners()
        return self.baseline

    def _backfill_savings(self, records: list[DayRecord]) -> None:
        """Store the savings of every completed day since installation."""
        if self.baseline is None or not self.baseline.is_valid:
            return
        installed = date.fromisoformat(self._stored["installed_on"])
        today = dt_util.now().date()
        for record in records:
            if record.day < installed or record.day >= today:
                continue
            saved = gas_savings(
                expected_gas(
                    self.baseline.m3_per_degree_day,
                    degree_days(record.mean_temperature, self.heating_limit),
                ),
                record.gas,
            )
            if saved is not None:
                self._stored["savings"][record.day.isoformat()] = saved

    async def async_history(self, days: int) -> list[dict[str, Any]]:
        """Return per-day analytics for the panel (oldest first, today last)."""
        records = await self._async_records(days)
        baseline = self.baseline.m3_per_degree_day if self.baseline else None
        fireplace_days, setback_days = self._excluded_days()
        price = self.data.gas_price if self.data else DEFAULT_GAS_PRICE
        rows: list[dict[str, Any]] = []
        cumulative = 0.0
        for record in records:
            dd = degree_days(record.mean_temperature, self.heating_limit)
            expected = expected_gas(baseline, dd)
            saved = gas_savings(expected, record.gas)
            cumulative += saved or 0.0
            rows.append(
                {
                    "date": record.day.isoformat(),
                    "mean_temperature": record.mean_temperature,
                    "degree_days": dd,
                    "gas": record.gas,
                    "expected": expected,
                    "saved": saved,
                    "saved_eur": money(saved, price),
                    "cumulative_saved": cumulative,
                    "cumulative_saved_eur": cumulative * price,
                    "fireplace": record.day in fireplace_days,
                    "setback": record.day in setback_days,
                }
            )
        if self.data is not None:
            cumulative += self.data.saved_today or 0.0
            rows.append(
                {
                    "date": dt_util.now().date().isoformat(),
                    "mean_temperature": self.data.mean_temp_today,
                    "degree_days": self.data.degree_days_today,
                    "gas": self.data.gas_today,
                    "expected": self.data.expected_today,
                    "saved": self.data.saved_today,
                    "saved_eur": money(self.data.saved_today, price),
                    "cumulative_saved": cumulative,
                    "cumulative_saved_eur": cumulative * price,
                    "fireplace": self.fireplace_minutes_today() >= FIREPLACE_EXCLUDE_MINUTES,
                    "setback": dt_util.now().date() in setback_days,
                    "partial": True,
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Savings total (restored by the sensor via RestoreEntity)
    # ------------------------------------------------------------------
    def restore_saved_total(self, value: float | None) -> None:
        """Seed the cumulative savings when the storage was lost."""
        if value is None or self._stored["savings"] or self._stored["savings_offset"]:
            return
        self._stored["savings_offset"] = value
        self._async_save()

    def _saved_total(self, saved_today: float | None) -> tuple[float | None, int]:
        today = dt_util.now().date().isoformat()
        completed = {d: v for d, v in self._stored["savings"].items() if d < today}
        offset = float(self._stored["savings_offset"])
        if not completed and saved_today is None and not offset:
            return None, 0
        return offset + sum(completed.values()) + (saved_today or 0.0), len(completed)

    # ------------------------------------------------------------------
    # Energy data (DataUpdateCoordinator)
    # ------------------------------------------------------------------
    def _gas_price(self) -> tuple[float, str]:
        cfg = self.config
        if entity_id := cfg.get(CONF_GAS_PRICE_ENTITY):
            state = self.hass.states.get(entity_id)
            if state is not None and (price := _float_or_none(state.state)) is not None:
                return price, "entiteit"
        if (price := _float_or_none(cfg.get(CONF_GAS_PRICE))) is not None:
            return price, "vast"
        return DEFAULT_GAS_PRICE, "standaard"

    async def _async_gas_today(self, start: datetime, now: datetime) -> float | None:
        """Gas used today; falls back to the meter reading stored at midnight."""
        gas_id = self.config[CONF_GAS_SENSOR]
        value = await async_period_value(self.hass, gas_id, start, now, "change")
        reading = None
        if (state := self.hass.states.get(gas_id)) is not None:
            reading = _float_or_none(state.state)
        day = now.date().isoformat()
        if reading is not None and day not in self._stored["meter_start"]:
            self._stored["meter_start"][day] = reading
            self._async_save()
        if value is None and reading is not None:
            value = max(0.0, reading - self._stored["meter_start"][day])
        return value

    async def _async_update_data(self) -> EnergyData:
        cfg = self.config
        now = dt_util.now()
        today = dt_util.start_of_local_day()
        yesterday = today - timedelta(days=1)
        temp_id = cfg[CONF_OUTDOOR_SENSOR]
        gas_id = cfg[CONF_GAS_SENSOR]
        limit = self.heating_limit

        price, source = self._gas_price()
        data = EnergyData(gas_price=price, gas_price_source=source)

        data.mean_temp_today = await async_period_value(
            self.hass, temp_id, today, now, "mean"
        )
        if data.mean_temp_today is None:
            data.mean_temp_today = self.outdoor_temperature()
        data.mean_temp_yesterday = await async_period_value(
            self.hass, temp_id, yesterday, today, "mean"
        )
        data.gas_today = await self._async_gas_today(today, now)
        data.gas_yesterday = await async_period_value(
            self.hass, gas_id, yesterday, today, "change"
        )

        data.degree_days_today = accumulated_degree_days(
            data.mean_temp_today, limit, day_fraction(now)
        )
        data.degree_days_today_forecast = degree_days(data.mean_temp_today, limit)
        data.degree_days_yesterday = degree_days(data.mean_temp_yesterday, limit)

        baseline = self.baseline.m3_per_degree_day if self.baseline else None
        data.expected_today = expected_gas(baseline, data.degree_days_today)
        data.expected_yesterday = expected_gas(baseline, data.degree_days_yesterday)
        data.saved_today = gas_savings(data.expected_today, data.gas_today)
        data.saved_yesterday = gas_savings(data.expected_yesterday, data.gas_yesterday)

        yesterday_key = yesterday.date().isoformat()
        if (
            data.saved_yesterday is not None
            and yesterday_key >= self._stored["installed_on"]
            and self._stored["savings"].get(yesterday_key) != data.saved_yesterday
        ):
            self._stored["savings"][yesterday_key] = data.saved_yesterday
            self._async_save()
        data.saved_total, data.saved_total_days = self._saved_total(data.saved_today)
        return data

    def to_euro(self, volume: float | None) -> float | None:
        """Convert m³ to euro using the current (or default) gas price."""
        price = self.data.gas_price if self.data else self._gas_price()[0]
        return money(volume, price)


def _baseline_to_dict(result: BaselineResult) -> dict[str, Any]:
    return {
        "m3_per_degree_day": result.m3_per_degree_day,
        "days_used": result.days_used,
        "total_gas": result.total_gas,
        "total_degree_days": result.total_degree_days,
        "excluded_fireplace": result.excluded_fireplace,
        "excluded_setback": result.excluded_setback,
        "excluded_invalid": result.excluded_invalid,
        "excluded_warm": result.excluded_warm,
        "first_day": result.first_day.isoformat() if result.first_day else None,
        "last_day": result.last_day.isoformat() if result.last_day else None,
        "reliable": result.reliable,
    }


def _baseline_from_dict(data: dict[str, Any]) -> BaselineResult:
    return BaselineResult(
        m3_per_degree_day=data.get("m3_per_degree_day"),
        days_used=data.get("days_used", 0),
        total_gas=data.get("total_gas", 0.0),
        total_degree_days=data.get("total_degree_days", 0.0),
        excluded_fireplace=data.get("excluded_fireplace", 0),
        excluded_setback=data.get("excluded_setback", 0),
        excluded_invalid=data.get("excluded_invalid", 0),
        excluded_warm=data.get("excluded_warm", 0),
        first_day=date.fromisoformat(data["first_day"]) if data.get("first_day") else None,
        last_day=date.fromisoformat(data["last_day"]) if data.get("last_day") else None,
        reliable=data.get("reliable", data.get("days_used", 0) >= BASELINE_MIN_DAYS),
    )


async def async_restore_all(hass: HomeAssistant, entry_id: str) -> None:
    """Restore all lowered thermostats (used when the entry is removed)."""
    store: Store[dict[str, Any]] = Store(
        hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}"
    )
    stored = await store.async_load() or {}
    for state in stored.get("room_state", {}).values():
        if not state.get("active"):
            continue
        for entity_id, values in state.get("entities", {}).items():
            climate = hass.states.get(entity_id)
            if climate is None:
                continue
            target = restore_value(
                _float_or_none(climate.attributes.get(ATTR_TEMPERATURE)),
                values["applied"],
                values["original"],
            )
            if target is None:
                continue
            try:
                await hass.services.async_call(
                    CLIMATE_DOMAIN,
                    SERVICE_SET_TEMPERATURE,
                    {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: target},
                    blocking=True,
                )
            except HomeAssistantError:
                _LOGGER.warning("Could not restore %s", entity_id)
    await store.async_remove()
