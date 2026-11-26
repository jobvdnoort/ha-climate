"""Coordinator for HA Climate: energy statistics, night setback and fireplace."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
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
    FireplaceDetector,
    accumulated_degree_days,
    calculate_baseline,
    day_fraction,
    degree_days,
    expected_gas,
    fireplace_excluded_days,
    gas_savings,
    in_time_window,
    money,
    parse_time,
    restore_value,
    setback_target,
)
from .const import (
    BASELINE_MIN_DAYS,
    BASELINE_MIN_DEGREE_DAYS,
    CONF_BASELINE_DAYS,
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
    CONF_OUTDOOR_SENSOR,
    CONF_ROOM_CLIMATES,
    CONF_ROOM_ID,
    CONF_ROOM_USE_GLOBAL,
    CONF_ROOMS,
    DEFAULT_BASELINE_DAYS,
    DEFAULT_FIREPLACE_THRESHOLD,
    DEFAULT_HEATING_LIMIT,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_OFFSET,
    DEFAULT_NIGHT_START,
    DOMAIN,
    FIREPLACE_EXCLUDE_MINUTES,
    FIREPLACE_HEATING_COOLDOWN,
    FIREPLACE_RISE_WINDOW,
    HISTORY_RETENTION_DAYS,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .statistics import async_daily_history, async_period_value

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


def merged_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return config entry data with options applied on top."""
    return {**entry.data, **entry.options}


@dataclass(slots=True)
class NightSettings:
    """Effective night setback settings for a room."""

    start: Any
    end: Any
    offset: float


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
    gas_price: float | None = None


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

    @property
    def fireplace_configured(self) -> bool:
        """Return whether a fireplace thermostat is configured."""
        return bool(self.config.get(CONF_FIREPLACE_CLIMATE))

    def night_settings(self, room: dict[str, Any]) -> NightSettings:
        """Return the effective night settings for a room."""
        cfg = self.config
        source = cfg if room.get(CONF_ROOM_USE_GLOBAL, True) else room
        return NightSettings(
            start=parse_time(source.get(CONF_NIGHT_START, DEFAULT_NIGHT_START)),
            end=parse_time(source.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)),
            offset=float(source.get(CONF_NIGHT_OFFSET, DEFAULT_NIGHT_OFFSET)),
        )

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
        stored.setdefault("meter_start", {})
        stored.setdefault("baseline", None)
        self._stored = stored
        if (cached := stored.get("baseline")) is not None:
            self.baseline = _baseline_from_dict(cached)
            self.baseline_updated = dt_util.parse_datetime(cached.get("updated", ""))

    @callback
    def _async_save(self) -> None:
        """Schedule a save of the persisted state."""
        self._prune_history()
        self._store.async_delay_save(lambda: self._stored, 10)

    def _prune_history(self) -> None:
        cutoff = (dt_util.now().date() - timedelta(days=HISTORY_RETENTION_DAYS)).isoformat()
        for key in ("fireplace_minutes", "savings", "meter_start"):
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

    @callback
    def async_stop(self) -> None:
        """Stop listeners and timers."""
        while self._unsub:
            self._unsub.pop()()

    async def async_shutdown(self) -> None:
        """Flush state on shutdown."""
        self.async_stop()
        await self._store.async_save(self._stored)
        await super().async_shutdown()

    # ------------------------------------------------------------------
    # Switch state
    # ------------------------------------------------------------------
    @property
    def master_enabled(self) -> bool:
        """Return whether the night setback is enabled globally."""
        return bool(self._stored.get("master", True))

    def room_enabled(self, room_id: str) -> bool:
        """Return whether the night setback is enabled for a room."""
        return bool(self._stored["room_enabled"].get(room_id, True))

    def room_setback_active(self, room_id: str) -> bool:
        """Return whether the night setback is currently applied in a room."""
        return bool(self._stored["room_state"].get(room_id, {}).get("active"))

    async def async_set_master(self, enabled: bool) -> None:
        """Enable/disable the night setback globally."""
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
        """Evaluate night setback and fireplace state."""
        now = dt_util.as_local(now)
        await self._async_evaluate_setback(now)
        if self.fireplace_configured:
            self._evaluate_fireplace(now)
            if self.fireplace.active:
                day = now.date().isoformat()
                minutes = self._stored["fireplace_minutes"]
                minutes[day] = minutes.get(day, 0) + 1
                self._async_save()
        self.async_update_listeners()

    async def _async_nightly_baseline(self, _now: datetime) -> None:
        await self.async_recalculate_baseline()
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Night setback
    # ------------------------------------------------------------------
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
                await self._async_restore_room(room_state[room_id])
            room_state.pop(room_id)
            changed = True

        for room_id, room in configured.items():
            settings = self.night_settings(room)
            wanted = (
                self.master_enabled
                and self.room_enabled(room_id)
                and in_time_window(now.time(), settings.start, settings.end)
            )
            state = room_state.setdefault(room_id, {"active": False, "entities": {}})
            if wanted and not state["active"]:
                await self._async_apply_room(room, settings, state)
                changed = True
            elif not wanted and state["active"]:
                await self._async_restore_room(state)
                changed = True
            if state["active"]:
                day = now.date().isoformat()
                if day not in self._stored["setback_dates"]:
                    self._stored["setback_dates"].append(day)
                    changed = True

        if changed:
            self._async_save()

    async def _async_apply_room(
        self, room: dict[str, Any], settings: NightSettings, state: dict[str, Any]
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
            target = setback_target(
                original,
                settings.offset,
                _float_or_none(climate.attributes.get(ATTR_MIN_TEMP)),
                _float_or_none(climate.attributes.get(ATTR_TARGET_TEMP_STEP)),
            )
            if await self._async_set_temperature(entity_id, target):
                entities[entity_id] = {"original": original, "applied": target}
        # Only mark as active when something was lowered, otherwise retry next tick.
        state["active"] = bool(entities)
        state["entities"] = entities
        _LOGGER.debug("Night setback applied in %s: %s", room.get("name"), entities)

    async def _async_restore_room(self, state: dict[str, Any]) -> None:
        """Restore the comfort temperature of all loops in a room."""
        for entity_id, values in state.get("entities", {}).items():
            climate = self.hass.states.get(entity_id)
            if climate is None or climate.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            target = restore_value(
                _float_or_none(climate.attributes.get(ATTR_TEMPERATURE)),
                values["applied"],
                values["original"],
            )
            if target is not None:
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

    def comfort_target(self, entity_id: str) -> float | None:
        """Return the comfort target of a loop (the original one during setback)."""
        for state in self._stored["room_state"].values():
            if state.get("active") and entity_id in state.get("entities", {}):
                return state["entities"][entity_id]["original"]
        climate = self.hass.states.get(entity_id)
        if climate is None:
            return None
        return _float_or_none(climate.attributes.get(ATTR_TEMPERATURE))

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
    # Baseline
    # ------------------------------------------------------------------
    async def async_recalculate_baseline(self) -> BaselineResult | None:
        """Recalculate the baseline from the recorder's long-term statistics."""
        cfg = self.config
        try:
            records = await async_daily_history(
                self.hass,
                cfg[CONF_OUTDOOR_SENSOR],
                cfg[CONF_GAS_SENSOR],
                int(cfg.get(CONF_BASELINE_DAYS, DEFAULT_BASELINE_DAYS)),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Reading long-term statistics failed")
            return self.baseline

        result = calculate_baseline(
            records,
            heating_limit=self.heating_limit,
            fireplace_days=fireplace_excluded_days(
                self._stored["fireplace_minutes"], FIREPLACE_EXCLUDE_MINUTES
            ),
            setback_days={date.fromisoformat(d) for d in self._stored["setback_dates"]},
            min_degree_days=BASELINE_MIN_DEGREE_DAYS,
            min_days=BASELINE_MIN_DAYS,
        )
        if result.is_valid or self.baseline is None or not self.baseline.is_valid:
            # Keep a previous valid baseline when too few clean days remain
            # (e.g. when the night setback has been running for a long time).
            self.baseline = result
            self.baseline_updated = dt_util.now()
            self._stored["baseline"] = {
                **_baseline_to_dict(result),
                "updated": self.baseline_updated.isoformat(),
            }
            self._async_save()
        else:
            _LOGGER.info(
                "Only %s usable days found, keeping previous baseline", result.days_used
            )
        _LOGGER.debug("Baseline: %s", self.baseline)
        self.async_update_listeners()
        return self.baseline

    # ------------------------------------------------------------------
    # Energy data (DataUpdateCoordinator)
    # ------------------------------------------------------------------
    def _gas_price(self) -> float | None:
        cfg = self.config
        if entity_id := cfg.get(CONF_GAS_PRICE_ENTITY):
            state = self.hass.states.get(entity_id)
            if state is not None and (price := _float_or_none(state.state)) is not None:
                return price
        return _float_or_none(cfg.get(CONF_GAS_PRICE))

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

        data = EnergyData(gas_price=self._gas_price())

        data.mean_temp_today = await async_period_value(
            self.hass, temp_id, today, now, "mean"
        )
        if data.mean_temp_today is None and (state := self.hass.states.get(temp_id)):
            data.mean_temp_today = _float_or_none(state.state)
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

        # Total savings: sum of completed days on which the night setback was active.
        yesterday_key = yesterday.date().isoformat()
        if (
            data.saved_yesterday is not None
            and yesterday_key in self._stored["setback_dates"]
            and self._stored["savings"].get(yesterday_key) != data.saved_yesterday
        ):
            self._stored["savings"][yesterday_key] = data.saved_yesterday
            self._async_save()
        savings = self._stored["savings"]
        if savings:
            data.saved_total = sum(savings.values())
            data.saved_total_days = len(savings)
        return data

    def to_euro(self, volume: float | None) -> float | None:
        """Convert m³ to euro using the current gas price."""
        return money(volume, self.data.gas_price if self.data else None)


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
