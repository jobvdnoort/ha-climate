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
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .boiler import (
    BoilerTracker,
    hours_from,
    is_cycling,
    minutes_from,
    pressure_status,
    summarize_day,
    valve_stats,
)
from .calculations import (
    BaselineResult,
    DayRecord,
    FireplaceDetector,
    accumulated_degree_days,
    calculate_baseline,
    corrected_heating_limit,
    daily_fixed_costs,
    describe_night,
    rank_rooms,
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
    BOILER_KEYS,
    BOILER_TRACE_HOURS,
    BOILER_TRACE_STEP,
    CONF_BOILER_AVG_RUNTIME,
    CONF_BOILER_DHW,
    CONF_BOILER_ERROR,
    CONF_BOILER_FLAME,
    CONF_BOILER_FLOW_SETPOINT,
    CONF_BOILER_FLOW_TEMP,
    CONF_BOILER_HEAT_REQUEST,
    CONF_BOILER_HOURS_TODAY,
    CONF_BOILER_MODULATION,
    CONF_BOILER_PRESSURE,
    CONF_BOILER_STARTS_TODAY,
    CONF_BASELINE_DAYS,
    CONF_COMFORT_TIME,
    CONF_DAY_TEMP,
    CONF_FIREPLACE_CLIMATE,
    CONF_FIREPLACE_TEMP_SENSOR,
    CONF_FIREPLACE_THRESHOLD,
    CONF_GAS_PRICE,
    CONF_DD_INDOOR_CORRECTION,
    CONF_DD_REFERENCE_TEMP,
    CONF_GAS_FIXED_COSTS,
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
    AIRCO_ACTIVE_ACTIONS,
    AIRCO_DEFAULT_COOL_TEMP,
    DEFAULT_BASELINE_DAYS,
    DEFAULT_DD_REFERENCE_TEMP,
    DEFAULT_FIXED_COSTS_UNIT,
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
    HISTORY_STORAGE_KEY,
    MAX_EVENTS,
    RANKING_DAYS,
    ADVICE_CACHE,
    ADVICE_DAYS,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .advice import (
    HouseInput,
    RoomInput,
    build_advice,
    summarize_setpoints,
    window_hours,
)
from .recorder_history import (
    async_backfill_observations,
    async_boiler_trace,
    async_climate_samples,
)
from .statistics import async_daily_history, async_first_overlap, async_period_value
from .thermal import (
    PreheatPlan,
    RoomThermalModel,
    model_stage,
    night_period,
    preheat_lead,
)

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


def _on_off(value: Any) -> bool | None:
    """Convert a binary state to bool (None when unknown)."""
    if value == STATE_ON:
        return True
    if value == STATE_OFF:
        return False
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
    fixed_costs: float = 0.0  # € per day
    cost_today: float | None = None  # variable + fixed
    cost_yesterday: float | None = None


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
        # Permanent history (daily degree days/gas and all thermal observations).
        self._history_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{HISTORY_STORAGE_KEY}.{entry.entry_id}"
        )
        self._history: dict[str, Any] = {}
        self._recalculate_lock = asyncio.Lock()
        self._unsub: list[CALLBACK_TYPE] = []
        self._setback_lock = asyncio.Lock()
        self.baseline: BaselineResult | None = None
        self.baseline_updated: datetime | None = None
        self.models: dict[str, RoomThermalModel] = {}
        self.plans: dict[str, dict[str, Any]] = {}
        self._advice: tuple[datetime, dict[str, Any]] | None = None
        self.fireplace = FireplaceDetector(
            threshold=float(
                self.config.get(CONF_FIREPLACE_THRESHOLD, DEFAULT_FIREPLACE_THRESHOLD)
            ),
            rise_window=FIREPLACE_RISE_WINDOW,
            heating_cooldown=FIREPLACE_HEATING_COOLDOWN,
        )
        self.boiler = BoilerTracker(track_flame=bool(self.config.get(CONF_BOILER_FLAME)))

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

    # ---- boiler (optional) --------------------------------------------
    @property
    def boiler_configured(self) -> bool:
        """Return whether any boiler (OpenTherm) entity is configured."""
        return any(self.config.get(key) for key in BOILER_KEYS)

    def _state_value(self, key: str) -> Any:
        if not (entity_id := self.config.get(key)):
            return None
        state = self.hass.states.get(entity_id)
        return state.state if state is not None else None

    def _boiler_float(self, key: str) -> float | None:
        return _float_or_none(self._state_value(key))

    def _boiler_bool(self, key: str) -> bool | None:
        return _on_off(self._state_value(key))

    def _boiler_unit(self, key: str) -> str | None:
        if not (entity_id := self.config.get(key)):
            return None
        state = self.hass.states.get(entity_id)
        return state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None

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
        stored.setdefault(
            "installed_on",
            min([*stored["savings"].keys(), dt_util.now().date().isoformat()]),
        )
        self._stored = stored
        if (cached := stored.get("baseline")) is not None:
            self.baseline = _baseline_from_dict(cached)
            self.baseline_updated = dt_util.parse_datetime(cached.get("updated", ""))
        history = await self._history_store.async_load() or {}
        history.setdefault("days", {})
        history.setdefault("models", {})
        history.setdefault("overlap_start", None)
        # day -> [Σ measured, n, Σ target, n, Σ comfort, n]
        history.setdefault("indoor", {})
        history.setdefault("events", [])  # [{"ts", "type", "room", "text"}]
        history.setdefault("boiler", {})  # {"days": {day: {...}}}
        self.boiler = BoilerTracker.from_dict(
            history["boiler"], track_flame=bool(self.config.get(CONF_BOILER_FLAME))
        )
        # Older versions could "freeze" the baseline. The baseline is now
        # always learned from the days before the savings start, which keeps
        # it fixed by itself.
        stored.pop("frozen_baseline", None)
        stored.setdefault("night_signature", None)
        # Migrate models from the old single storage file. The history is
        # written right away, before the old copy can disappear from storage.
        legacy_models = stored.pop("models", None)
        self._history = history
        if legacy_models:
            for room_id, model in legacy_models.items():
                history["models"].setdefault(room_id, model)
            await self._history_store.async_save(history)
        for room in self.rooms:
            self.models[room[CONF_ROOM_ID]] = RoomThermalModel.from_dict(
                history["models"].get(room[CONF_ROOM_ID])
            )
        self._log_night_setting_changes()

    # ------------------------------------------------------------------
    # Event log (kept permanently in the history store)
    # ------------------------------------------------------------------
    def log_event(
        self, kind: str, text: str, room_id: str | None = None, when: datetime | None = None
    ) -> None:
        """Store an event that is shown in the charts and the CSV export."""
        events: list[dict[str, Any]] = self._history["events"]
        events.append(
            {
                "ts": (when or dt_util.now()).isoformat(),
                "type": kind,
                "room": room_id,
                "text": text,
            }
        )
        del events[:-MAX_EVENTS]
        self._async_save_history()

    def events_by_day(self) -> dict[str, list[dict[str, Any]]]:
        """Events grouped by local date."""
        result: dict[str, list[dict[str, Any]]] = {}
        for event in self._history["events"]:
            moment = dt_util.parse_datetime(event["ts"])
            if moment is None:
                continue
            result.setdefault(dt_util.as_local(moment).date().isoformat(), []).append(event)
        return result

    def _night_description(self, room: dict[str, Any] | None = None) -> str:
        if room is None:
            cfg = self.config
            return describe_night(
                str(cfg.get(CONF_NIGHT_START) or DEFAULT_NIGHT_START),
                str(cfg.get(CONF_NIGHT_END) or DEFAULT_NIGHT_END),
                float(cfg.get(CONF_NIGHT_OFFSET, DEFAULT_NIGHT_OFFSET)),
            )
        schedule = self.schedule(room)
        end = schedule.comfort_time if schedule.optimum_start else schedule.end
        text = describe_night(
            schedule.start.strftime("%H:%M"),
            end.strftime("%H:%M"),
            schedule.offset,
            schedule.night_temp,
        )
        return f"{text}, optimum start" if schedule.optimum_start else text

    def _log_night_setting_changes(self) -> None:
        """Compare the night settings with the last known ones (any source)."""
        signature = {"global": self._night_description()}
        names = {}
        for room in self.rooms:
            signature[room[CONF_ROOM_ID]] = self._night_description(room)
            names[room[CONF_ROOM_ID]] = room[CONF_ROOM_NAME]
        previous = self._stored.get("night_signature")
        self._stored["night_signature"] = signature
        if previous is None:
            return
        if previous != signature:
            self._async_save()
        if previous.get("global") != signature["global"]:
            self.log_event(
                "settings", f"Nachtverlaging aangepast: {signature['global']}"
            )
        for room_id, text in signature.items():
            if room_id == "global" or previous.get(room_id) == text:
                continue
            verb = "ingesteld" if room_id not in previous else "aangepast"
            self.log_event(
                "settings", f"Nachtverlaging {names[room_id]} {verb}: {text}", room_id
            )

    @callback
    def _async_save(self) -> None:
        """Schedule a save of the persisted state."""
        self._prune_history()
        self._store.async_delay_save(self._data_to_save, 10)

    def _data_to_save(self) -> dict[str, Any]:
        return self._stored

    @callback
    def _async_save_history(self) -> None:
        """Schedule a save of the permanent history (written less often)."""
        self._history_store.async_delay_save(self._history_to_save, 60)

    def _history_to_save(self) -> dict[str, Any]:
        # Models of rooms that were removed are kept, so re-adding a room with
        # the same id (or restoring a backup) does not lose what was learned.
        self._history["models"].update(
            {room_id: model.as_dict() for room_id, model in self.models.items()}
        )
        if self.boiler.days:
            self.boiler.prune(
                (dt_util.now().date() - timedelta(days=HISTORY_RETENTION_DAYS)).isoformat()
            )
            self._history["boiler"] = self.boiler.as_dict()
        return self._history

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
        boiler_tracked = [
            entity
            for entity in (self.config.get(CONF_BOILER_FLAME), self.config.get(CONF_BOILER_DHW))
            if entity
        ]
        if boiler_tracked:
            # Burner starts are counted on every change, not only once a minute.
            self._unsub.append(
                async_track_state_change_event(
                    self.hass, boiler_tracked, self._async_boiler_state_changed
                )
            )
        self._unsub.append(async_at_started(self.hass, self._async_started))

    async def _async_started(self, _hass: HomeAssistant) -> None:
        """Run once Home Assistant has fully started."""
        await self.async_recalculate_baseline()
        # New rooms (or a first start) learn right away from recorder history.
        pending = [
            room[CONF_ROOM_ID]
            for room in self.rooms
            if not self.model(room[CONF_ROOM_ID]).backfill
        ]
        if pending:
            await self.async_backfill_thermal(pending)
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
        await self._history_store.async_save(self._history_to_save())
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
        if self._stored.get("master", True) != enabled:
            self.log_event(
                "master",
                f"Nachtverlaging {'aan' if enabled else 'uit'} (alle thermostaten, "
                f"{self._night_description()})",
            )
        self._stored["master"] = enabled
        self._async_save()
        await self._async_evaluate_setback(dt_util.now())
        self.async_update_listeners()

    async def async_set_room(self, room_id: str, enabled: bool) -> None:
        """Enable/disable the night setback for a single room."""
        if self.room_enabled(room_id) != enabled and (room := self.room(room_id)):
            self.log_event(
                "room",
                f"Nachtverlaging {room[CONF_ROOM_NAME]} {'aan' if enabled else 'uit'}"
                f" ({self._night_description(room)})",
                room_id,
            )
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
        if self.boiler_configured:
            self._track_boiler(now, sample=True)
        self._learn(now)
        await self._async_evaluate_setback(now)
        self.async_update_listeners()

    # ------------------------------------------------------------------
    # Boiler (OpenTherm)
    # ------------------------------------------------------------------
    @callback
    def _async_boiler_state_changed(self, event: Event) -> None:
        self._track_boiler(dt_util.as_local(event.time_fired))

    def _track_boiler(self, now: datetime, sample: bool = False) -> None:
        """Follow the burner/DHW status and keep the daily statistics."""
        now = dt_util.as_local(now)
        self.boiler.update(
            now, self._boiler_bool(CONF_BOILER_FLAME), self._boiler_bool(CONF_BOILER_DHW)
        )
        if not sample:
            return
        self.boiler.sample(
            now,
            self._boiler_float(CONF_BOILER_FLOW_TEMP),
            self._boiler_float(CONF_BOILER_MODULATION),
        )
        record = self.boiler.day(now.date().isoformat())
        external = self._boiler_external()
        for key, value in (
            ("ext_starts", external["starts"]),
            ("ext_hours", external["burn_hours"]),
            ("ext_avg", external["avg_run_minutes"]),
        ):
            if value is not None:
                record[key] = value
        # Minute counters change constantly; the delayed save batches them.
        if now.minute % 15 == 0:
            self._async_save_history()

    def _boiler_external(self) -> dict[str, float | None]:
        """Values of the boiler's own counters (optional entities)."""
        return {
            "starts": self._boiler_float(CONF_BOILER_STARTS_TODAY),
            "burn_hours": hours_from(
                self._boiler_float(CONF_BOILER_HOURS_TODAY),
                self._boiler_unit(CONF_BOILER_HOURS_TODAY),
            ),
            "avg_run_minutes": minutes_from(
                self._boiler_float(CONF_BOILER_AVG_RUNTIME),
                self._boiler_unit(CONF_BOILER_AVG_RUNTIME),
            ),
        }

    def boiler_day(self, day: date) -> dict[str, Any]:
        """KPIs of one day (own tracking, the boiler's counters win)."""
        return summarize_day(self.boiler.days.get(day.isoformat()))

    def boiler_status(self) -> dict[str, Any] | None:
        """Live status and today's KPIs (None when no boiler is configured)."""
        if not self.boiler_configured:
            return None
        cfg = self.config
        now = dt_util.now()
        today = self.boiler_day(now.date())
        pressure = self._boiler_float(CONF_BOILER_PRESSURE)
        error = self._state_value(CONF_BOILER_ERROR)
        if error in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            error = None
        valves = [
            m["valve_max"]
            for room in self.rooms
            if (m := self.room_measurements(room))["valve_max"] is not None
        ]
        return {
            "entities": {key: cfg.get(key) for key in BOILER_KEYS},
            "flame": self._boiler_bool(CONF_BOILER_FLAME),
            "heat_request": self._boiler_bool(CONF_BOILER_HEAT_REQUEST),
            "dhw": self._boiler_bool(CONF_BOILER_DHW),
            "modulation": self._boiler_float(CONF_BOILER_MODULATION),
            "flow_temperature": self._boiler_float(CONF_BOILER_FLOW_TEMP),
            "flow_setpoint": self._boiler_float(CONF_BOILER_FLOW_SETPOINT),
            "pressure": pressure,
            "pressure_status": pressure_status(pressure),
            "error": error,
            "current_run_minutes": self.boiler.current_run_minutes(now),
            "max_valve": max(valves) if valves else None,
            "today": today,
            "cycling": is_cycling(today["starts"], today["avg_run_minutes"]),
            "tracking_flame": bool(cfg.get(CONF_BOILER_FLAME)),
        }

    async def async_boiler_trace(self) -> list[dict[str, Any]]:
        """Last 24 h of flow temperature, setpoint, modulation and max valve."""
        cfg = self.config
        numeric = {
            column: cfg[key]
            for column, key in (
                ("flow", CONF_BOILER_FLOW_TEMP),
                ("setpoint", CONF_BOILER_FLOW_SETPOINT),
                ("modulation", CONF_BOILER_MODULATION),
            )
            if cfg.get(key)
        }
        binary = {
            column: cfg[key]
            for column, key in (("flame", CONF_BOILER_FLAME), ("dhw", CONF_BOILER_DHW))
            if cfg.get(key)
        }
        valves = [v for room in self.rooms for v in room.get(CONF_ROOM_VALVES, [])]
        return await async_boiler_trace(
            self.hass, numeric, binary, valves, BOILER_TRACE_HOURS, BOILER_TRACE_STEP
        )

    async def _async_nightly_baseline(self, _now: datetime) -> None:
        await self.async_recalculate_baseline()
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Room measurements
    # ------------------------------------------------------------------
    def _climate_info(self, entity_id: str) -> dict[str, Any]:
        state = self.hass.states.get(entity_id)
        if state is None:
            return {"entity_id": entity_id, "available": False}
        return {
            "entity_id": entity_id,
            "name": state.attributes.get("friendly_name", entity_id),
            "available": state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN),
            "hvac_mode": state.state,
            "hvac_modes": list(state.attributes.get(ATTR_HVAC_MODES) or []),
            "hvac_action": state.attributes.get(ATTR_HVAC_ACTION),
            "current_temperature": _float_or_none(
                state.attributes.get(ATTR_CURRENT_TEMPERATURE)
            ),
            "target_temperature": _float_or_none(state.attributes.get(ATTR_TEMPERATURE)),
            "min_temp": _float_or_none(state.attributes.get(ATTR_MIN_TEMP)),
            "max_temp": _float_or_none(state.attributes.get(ATTR_MAX_TEMP)),
            "step": _float_or_none(state.attributes.get(ATTR_TARGET_TEMP_STEP)),
        }

    def room_measurements(self, room: dict[str, Any]) -> dict[str, Any]:
        """Return the live measurements of the loops (and aircos) in a room."""
        loops = [self._climate_info(e) for e in room.get(CONF_ROOM_CLIMATES, [])]
        aircos = [self._climate_info(e) for e in room.get(CONF_ROOM_AIRCOS, [])]
        available = [loop for loop in loops if loop.get("available")]
        actions = [loop["hvac_action"] for loop in available if loop.get("hvac_action")]
        valves = []
        for entity_id in room.get(CONF_ROOM_VALVES, []):
            state = self.hass.states.get(entity_id)
            valves.append(
                {
                    "entity_id": entity_id,
                    "name": state.attributes.get("friendly_name", entity_id) if state else entity_id,
                    "position": _float_or_none(state.state) if state else None,
                }
            )
        valve_mean, valve_max = valve_stats([v["position"] for v in valves])
        return {
            "loops": loops,
            "aircos": aircos,
            "valves": valves,
            "valve": valve_mean,
            "valve_max": valve_max,
            "current_temperature": _mean([loop["current_temperature"] for loop in available]),
            "target_temperature": _mean([loop["target_temperature"] for loop in available]),
            "heating": (any(a in HEATING_ACTIONS for a in actions) if actions else None),
            "airco_active": self._airco_active(aircos),
        }

    @staticmethod
    def _airco_active(aircos: list[dict[str, Any]]) -> bool:
        """An airco that heats or cools disturbs the floor heating model."""
        for airco in aircos:
            if not airco.get("available"):
                continue
            action = airco.get("hvac_action")
            if action in AIRCO_ACTIVE_ACTIONS:
                return True
            if action is None and airco.get("hvac_mode") not in (HVACMode.OFF, None):
                # Without hvac_action an airco that is switched on counts as active.
                return True
        return False

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
        indoor: list[float] = []
        targets: list[float] = []
        comforts: list[float] = []
        for room in self.rooms:
            measured = self.room_measurements(room)
            if measured["current_temperature"] is not None:
                indoor.append(measured["current_temperature"])
            if measured["target_temperature"] is not None:
                targets.append(measured["target_temperature"])
            if (comfort := self.comfort_temperature(room, measured)) is not None:
                comforts.append(comfort)
            valid = not (
                (self.room_has_fireplace(room) and self.fireplace.active)
                or measured["airco_active"]
            )
            # With valve sensors the mean opening is the heating intensity.
            heating = (
                measured["valve"] / 100 if measured["valve"] is not None else measured["heating"]
            )
            if self.model(room[CONF_ROOM_ID]).add_sample(
                now, measured["current_temperature"], outside, heating, valid
            ):
                learned = True
        if indoor or targets or comforts:
            day = now.date().isoformat()
            log = self._history["indoor"].setdefault(day, [0.0, 0, 0.0, 0, 0.0, 0])
            if len(log) < 6:  # logged by an older version
                log.extend([0.0, 0])
            if indoor:
                log[0] = round(log[0] + sum(indoor) / len(indoor), 3)
                log[1] += 1
            if targets:
                log[2] = round(log[2] + sum(targets) / len(targets), 3)
                log[3] += 1
            if comforts:
                # Day temperature, without the night setback.
                log[4] = round(log[4] + sum(comforts) / len(comforts), 3)
                log[5] += 1
            # Minute counters change constantly; the delayed save batches them.
            learned = learned or now.minute % 15 == 0
        if learned:
            self._async_save_history()

    def reset_model(self, room_id: str) -> None:
        """Forget what was learned for a room."""
        self.model(room_id).reset()
        self._async_save_history()

    def comfort_temperature(
        self, room: dict[str, Any], measured: dict[str, Any] | None = None
    ) -> float | None:
        """Return the temperature the room should have during the day."""
        schedule = self.schedule(room)
        if schedule.day_temp is not None:
            return schedule.day_temp
        state = self._stored["room_state"].get(room[CONF_ROOM_ID], {})
        if state.get("active") and state.get("entities"):
            return _mean([v["original"] for v in state["entities"].values()])
        return (measured or self.room_measurements(room))["target_temperature"]

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

    async def async_set_room_temperature(self, room: dict[str, Any], temperature: float) -> list[str]:
        """Set all floor heating loops of a room to one temperature."""
        changed = []
        for entity_id in room.get(CONF_ROOM_CLIMATES, []):
            info = self._climate_info(entity_id)
            if not info.get("available") or info.get("hvac_mode") == HVACMode.OFF:
                continue
            target = temperature
            if info.get("min_temp") is not None:
                target = max(target, info["min_temp"])
            if info.get("max_temp") is not None:
                target = min(target, info["max_temp"])
            if await self._async_set_temperature(entity_id, target):
                changed.append(entity_id)
        self.async_update_listeners()
        return changed

    async def async_airco(
        self,
        room: dict[str, Any],
        mode: str | None = None,
        temperature: float | None = None,
        entity_ids: list[str] | None = None,
    ) -> None:
        """Control the aircos of a room: mode off/cool/boost and/or temperature."""
        aircos = [
            e for e in room.get(CONF_ROOM_AIRCOS, []) if entity_ids is None or e in entity_ids
        ]
        if not aircos:
            raise HomeAssistantError("Deze kamer heeft geen airco")
        comfort = self.comfort_temperature(room)
        for entity_id in aircos:
            info = self._climate_info(entity_id)
            modes = info.get("hvac_modes") or []
            target = temperature
            if mode == "off":
                await self._async_call_climate(
                    SERVICE_SET_HVAC_MODE, entity_id, {ATTR_HVAC_MODE: HVACMode.OFF}
                )
                continue
            if mode == "cool":
                if modes and HVACMode.COOL not in modes:
                    raise HomeAssistantError(f"{entity_id} kan niet koelen")
                await self._async_call_climate(
                    SERVICE_SET_HVAC_MODE, entity_id, {ATTR_HVAC_MODE: HVACMode.COOL}
                )
                if target is None and info.get("target_temperature") is None:
                    target = AIRCO_DEFAULT_COOL_TEMP
            elif mode == "boost":
                if modes and HVACMode.HEAT not in modes:
                    raise HomeAssistantError(f"{entity_id} kan niet verwarmen")
                await self._async_call_climate(
                    SERVICE_SET_HVAC_MODE, entity_id, {ATTR_HVAC_MODE: HVACMode.HEAT}
                )
                if target is None:
                    # Quickly heat to the room's comfort temperature (+0.5 °C margin).
                    target = (comfort or info.get("target_temperature") or 21.0) + 0.5
            if target is not None:
                await self._async_call_climate(
                    SERVICE_SET_TEMPERATURE, entity_id, {ATTR_TEMPERATURE: target}
                )
        self.async_update_listeners()

    async def _async_call_climate(
        self, service: str, entity_id: str, data: dict[str, Any]
    ) -> None:
        await self.hass.services.async_call(
            CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
        )

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

    # ---- permanent daily store -------------------------------------
    def _store_records(self, records: list[DayRecord]) -> int:
        """Merge daily statistics into the permanent store; returns new days."""
        days: dict[str, list[float | None]] = self._history["days"]
        new = 0
        for record in records:
            key = record.day.isoformat()
            old = days.get(key, [None, None])
            mean = record.mean_temperature if record.mean_temperature is not None else old[0]
            gas = record.gas if record.gas is not None else old[1]
            value = [
                round(mean, 3) if mean is not None else None,
                round(gas, 4) if gas is not None else None,
            ]
            if key not in days:
                new += 1
            if days.get(key) != value:
                days[key] = value
        if records:
            self._async_save_history()
        return new

    def _stored_records(self, start: date, end: date) -> list[DayRecord]:
        """Daily records from the permanent store for start ≤ day < end."""
        records = []
        for key, (mean, gas) in sorted(self._history["days"].items()):
            day = date.fromisoformat(key)
            if start <= day < end:
                records.append(DayRecord(day=day, mean_temperature=mean, gas=gas))
        return records

    async def _async_sync_days(self, days: int | None = None, start: datetime | None = None) -> None:
        """Copy daily statistics from the recorder into the permanent store."""
        cfg = self.config
        records = await async_daily_history(
            self.hass, cfg[CONF_OUTDOOR_SENSOR], cfg[CONF_GAS_SENSOR], days=days, start=start
        )
        self._store_records(records)

    @property
    def overlap_start(self) -> date | None:
        """First day on which both the outdoor and the gas sensor have data."""
        value = self._history.get("overlap_start")
        return date.fromisoformat(value) if value else None

    # ---- recalculation ---------------------------------------------
    async def async_recalculate(self) -> BaselineResult | None:
        """Full recalculation: gas baseline from LTS and thermal backfill."""
        async with self._recalculate_lock:
            result = await self.async_recalculate_baseline(full=True)
            await self.async_backfill_thermal()
        await self.async_request_refresh()
        return result

    async def async_recalculate_baseline(self, full: bool = False) -> BaselineResult | None:
        """Recalculate the baseline from all stored days since the sensor overlap.

        With ``full`` (or when nothing is stored yet) the complete long-term
        statistics history is read from the first day both sensors have data;
        otherwise only the last few days are synced into the permanent store.
        """
        cfg = self.config
        today = dt_util.now().date()
        try:
            if full or not self._history["days"] or self.overlap_start is None:
                overlap = await async_first_overlap(
                    self.hass, cfg[CONF_OUTDOOR_SENSOR], cfg[CONF_GAS_SENSOR]
                )
                if overlap is not None:
                    self._history["overlap_start"] = overlap.date().isoformat()
                    await self._async_sync_days(start=overlap)
            else:
                await self._async_sync_days(days=7)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Reading long-term statistics failed")

        # Days before the overlap can exist in the store (from earlier
        # versions); the baseline only uses days where both sensors had data.
        start = self.overlap_start or (
            min((date.fromisoformat(d) for d in self._history["days"]), default=today)
        )
        # Only days before the savings start count: the baseline describes the
        # house *before* the measures, so it stays fixed once measuring starts.
        end = self.baseline_end
        window = int(cfg.get(CONF_BASELINE_DAYS) or DEFAULT_BASELINE_DAYS)
        if window > 0:
            start = max(start, end - timedelta(days=window))
        records = self._stored_records(start, end)

        fireplace_days, setback_days = self._excluded_days()
        result = calculate_baseline(
            records,
            heating_limit=self.heating_limit,
            fireplace_days=fireplace_days,
            setback_days=setback_days,
            min_degree_days=BASELINE_MIN_DEGREE_DAYS,
            min_days=BASELINE_MIN_DAYS,
            limits=self._limits(records),
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
                "window_start": start.isoformat(),
                "days_available": len(records),
            }
        else:
            _LOGGER.info(
                "Only %s usable days found, keeping previous baseline", result.days_used
            )
        self._backfill_savings(self._stored_records(self._measurement_start(), today))
        self._async_save()
        _LOGGER.debug("Baseline: %s", self.baseline)
        self.async_update_listeners()
        return self.baseline

    # ---- baseline & savings period -----------------------------------
    @property
    def baseline_end(self) -> date:
        """First day that is *not* part of the baseline (the savings start)."""
        today = dt_util.now().date()
        start = self.savings_start
        return min(start, today) if start is not None else today

    @property
    def effective_baseline(self) -> float | None:
        """Baseline used for the expected gas usage."""
        return self.baseline.m3_per_degree_day if self.baseline else None

    @property
    def savings_start(self) -> date | None:
        """First day of the savings measurement (configurable)."""
        value = self.config.get(CONF_SAVINGS_START)
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    def _measurement_start(self) -> date:
        """Savings are counted from the configured start (or installation)."""
        return self.savings_start or date.fromisoformat(self._stored["installed_on"])

    @property
    def indoor_correction(self) -> bool:
        """Whether degree days are corrected for the indoor target temperature."""
        return bool(self.config.get(CONF_DD_INDOOR_CORRECTION, False))

    @property
    def reference_temperature(self) -> float:
        """Comfort temperature of the baseline period (reference of the correction)."""
        value = _float_or_none(self.config.get(CONF_DD_REFERENCE_TEMP))
        return value if value is not None else DEFAULT_DD_REFERENCE_TEMP

    def indoor_day(self, day: date) -> tuple[float | None, float | None]:
        """Mean measured and target indoor temperature of a day."""
        log = self._history["indoor"].get(day.isoformat())
        if not log:
            return None, None
        measured = log[0] / log[1] if log[1] else None
        target = log[2] / log[3] if log[3] else None
        return measured, target

    def comfort_day(self, day: date) -> float | None:
        """Mean comfort (day) temperature of a day, without the night setback."""
        log = self._history["indoor"].get(day.isoformat())
        if not log or len(log) < 6 or not log[5]:
            return None
        return log[4] / log[5]

    def heating_limit_for(self, day: date) -> float:
        """Heating limit of a day, corrected for the comfort temperature if enabled.

        Days without a logged comfort temperature (e.g. before installation)
        count as heated to the reference temperature, i.e. they are not shifted,
        so the baseline period and later days use the same rule.
        """
        if not self.indoor_correction:
            return self.heating_limit
        return corrected_heating_limit(
            self.heating_limit, self.comfort_day(day), self.reference_temperature
        )

    def _limits(self, records: list[DayRecord]) -> dict[date, float] | None:
        if not self.indoor_correction:
            return None
        return {r.day: self.heating_limit_for(r.day) for r in records}

    def baseline_info(self) -> dict[str, Any]:
        """Describe the period the baseline is based on."""
        stored = self._stored.get("baseline") or {}
        return {
            "overlap_start": self._history.get("overlap_start"),
            "window_start": stored.get("window_start"),
            "days_available": stored.get("days_available"),
            "days_stored": len(self._history["days"]),
            "effective": self.effective_baseline,
            "baseline_end": self.baseline_end.isoformat(),
            "savings_start": self.savings_start.isoformat() if self.savings_start else None,
            "measurement_start": self._measurement_start().isoformat(),
            "indoor_correction": self.indoor_correction,
            "reference_temperature": self.reference_temperature,
        }

    def _fireplace_entity_id(self) -> str | None:
        registry = er.async_get(self.hass)
        return registry.async_get_entity_id(
            "binary_sensor", DOMAIN, f"{self.config_entry.entry_id}_fireplace_active"
        )

    async def async_backfill_thermal(self, room_ids: list[str] | None = None) -> None:
        """Learn from the recorder history of the rooms' climate entities."""
        outdoor = self.config[CONF_OUTDOOR_SENSOR]
        for room in self.rooms:
            room_id = room[CONF_ROOM_ID]
            if room_ids is not None and room_id not in room_ids:
                continue
            fireplace = self._fireplace_entity_id() if self.room_has_fireplace(room) else None
            try:
                observations, summary = await async_backfill_observations(
                    self.hass,
                    room.get(CONF_ROOM_CLIMATES, []),
                    outdoor,
                    fireplace,
                    aircos=room.get(CONF_ROOM_AIRCOS, []),
                    valves=room.get(CONF_ROOM_VALVES, []),
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Reading recorder history for %s failed", room[CONF_ROOM_NAME])
                continue
            model = self.model(room_id)
            summary["new"] = model.merge(observations)
            model.backfill = summary
            _LOGGER.debug(
                "Backfill %s: %s windows, %s new", room[CONF_ROOM_NAME],
                summary.get("windows", 0), summary["new"],
            )
        self._async_save_history()
        self.async_update_listeners()

    def model_status(self, room_id: str) -> dict[str, Any]:
        """Return the learning status of a room's model."""
        model = self.model(room_id)
        estimate = model.estimate
        summary = model.summary()
        return {
            **summary,
            "stage": model_stage(estimate, summary["data_points"]),
            "confidence": estimate.confidence,
            "cooling_confidence": estimate.cooling_confidence,
            "heating_confidence": estimate.heating_confidence,
            "cooling_coefficient": estimate.cooling_coefficient,
            "heating_power": estimate.heating_power,
            "time_constant": estimate.time_constant,
            "backfill": model.backfill,
        }

    def _backfill_savings(self, records: list[DayRecord]) -> None:
        """Store the savings of every completed day since installation."""
        baseline = self.effective_baseline
        if baseline is None:
            return
        start = self._measurement_start()
        today = dt_util.now().date()
        for record in records:
            if record.day < start or record.day >= today:
                continue
            saved = gas_savings(
                expected_gas(
                    baseline,
                    degree_days(record.mean_temperature, self.heating_limit_for(record.day)),
                ),
                record.gas,
            )
            if saved is not None:
                self._stored["savings"][record.day.isoformat()] = saved

    def gas_cost(self, gas: float | None, price: float, fixed: float) -> float | None:
        """Total gas costs of a day: variable usage plus fixed delivery costs."""
        if gas is None:
            return None
        return gas * price + fixed

    def _day_rows(self, records: list[DayRecord], include_today: bool) -> list[dict[str, Any]]:
        """Per-day analytics rows (charts and CSV export)."""
        today = dt_util.now().date()
        baseline = self.effective_baseline
        fireplace_days, setback_days = self._excluded_days()
        events = self.events_by_day()
        price = self.data.gas_price if self.data else self._gas_price()[0]
        fixed = self.data.fixed_costs if self.data else self._fixed_costs()
        start = self._measurement_start()
        rows: list[dict[str, Any]] = []
        cumulative = 0.0
        boiler = self.boiler_configured

        def row(day: date, mean, dd, gas, expected, saved, **extra) -> dict[str, Any]:
            nonlocal cumulative
            counting = day >= start
            if counting:
                cumulative += saved or 0.0
            indoor, target = self.indoor_day(day)
            return {
                "date": day.isoformat(),
                "mean_temperature": mean,
                "indoor_temperature": indoor,
                "indoor_target": target,
                "indoor_comfort": self.comfort_day(day),
                "heating_limit": self.heating_limit_for(day),
                "degree_days": dd,
                "gas": gas,
                "expected": expected,
                "saved": saved,
                "saved_eur": money(saved, price),
                "cumulative_saved": cumulative if counting else None,
                "cumulative_saved_eur": cumulative * price if counting else None,
                "cost_variable": money(gas, price),
                "cost_fixed": fixed if gas is not None else None,
                "cost": self.gas_cost(gas, price, fixed),
                "fireplace": day in fireplace_days,
                "fireplace_minutes": int(
                    self._stored["fireplace_minutes"].get(day.isoformat(), 0)
                ),
                "setback": day in setback_days,
                "events": [
                    {"time": e["ts"], "type": e["type"], "text": e["text"]}
                    for e in events.get(day.isoformat(), [])
                ],
                **({"boiler": self.boiler_day(day)} if boiler else {}),
                **extra,
            }

        for record in records:
            dd = degree_days(record.mean_temperature, self.heating_limit_for(record.day))
            expected = expected_gas(baseline, dd)
            rows.append(
                row(record.day, record.mean_temperature, dd, record.gas, expected,
                    gas_savings(expected, record.gas))
            )
        if include_today and self.data is not None:
            rows.append(
                row(
                    today,
                    self.data.mean_temp_today,
                    self.data.degree_days_today,
                    self.data.gas_today,
                    self.data.expected_today,
                    self.data.saved_today,
                    partial=True,
                )
            )
            rows[-1]["fireplace"] = self.fireplace_minutes_today() >= FIREPLACE_EXCLUDE_MINUTES
        return rows

    async def async_history(self, days: int) -> list[dict[str, Any]]:
        """Return per-day analytics for the panel (oldest first, today last)."""
        today = dt_util.now().date()
        try:
            await self._async_sync_days(days=days)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Could not sync recent statistics", exc_info=True)
        return self._day_rows(
            self._stored_records(today - timedelta(days=days), today), include_today=True
        )

    def export_rows(self) -> list[dict[str, Any]]:
        """All permanently stored days (for the CSV export)."""
        today = dt_util.now().date()
        start = min(
            (date.fromisoformat(d) for d in self._history["days"]), default=today
        )
        return self._day_rows(self._stored_records(start, today), include_today=True)

    # ---- room ranking -------------------------------------------------
    def room_ranking(self, days: int = RANKING_DAYS) -> list[dict[str, Any]]:
        """Rank rooms from least to most efficient (heat loss and heating share)."""
        cutoff = int((dt_util.utcnow() - timedelta(days=days)).timestamp())
        values = []
        info = {}
        for room in self.rooms:
            room_id = room[CONF_ROOM_ID]
            model = self.model(room_id)
            recent = [o for o in model.observations if o.start >= cutoff]
            duty = sum(o.duty for o in recent) / len(recent) if recent else None
            values.append((room_id, model.estimate.cooling_coefficient, duty))
            info[room_id] = {"name": room[CONF_ROOM_NAME], "windows": len(recent)}
        return [
            {
                "room_id": r.room_id,
                "name": info[r.room_id]["name"],
                "rank": r.rank,
                "heat_loss": r.heat_loss,
                "duty": r.duty,
                "score": r.score,
                "label": r.label,
                "tags": r.tags,
                "windows": info[r.room_id]["windows"],
                "days": days,
            }
            for r in rank_rooms(values)
        ]

    # ---- saving advice --------------------------------------------------
    async def async_advice(self, force: bool = False) -> dict[str, Any]:
        """Tips with an estimated saving, based on the last days and the models."""
        now = dt_util.now()
        if (
            not force
            and self._advice is not None
            and now - self._advice[0] < ADVICE_CACHE
        ):
            return self._advice[1]
        today = now.date()
        records = [
            r
            for r in self._stored_records(today - timedelta(days=ADVICE_DAYS), today)
            if r.mean_temperature is not None
        ]
        outdoor = (
            sum(r.mean_temperature for r in records) / len(records) if records else None
        )
        if outdoor is None:
            outdoor = self.outdoor_temperature()
        heating_gas = None
        if records and self.effective_baseline is not None:
            dd = [
                degree_days(r.mean_temperature, self.heating_limit_for(r.day))
                for r in records
            ]
            heating_gas = self.effective_baseline * sum(dd) / len(dd)

        # Measured since the savings start (complete days, without fireplace).
        fireplace_days, _ = self._excluded_days()
        measured = [
            row
            for row in self._day_rows(
                self._stored_records(self._measurement_start(), today), include_today=False
            )
            if row["gas"] is not None
            and row["expected"] is not None
            and date.fromisoformat(row["date"]) not in fireplace_days
        ]

        # Setpoints of the last days from the recorder.
        climates = [e for room in self.rooms for e in room.get(CONF_ROOM_CLIMATES, [])]
        try:
            samples = await async_climate_samples(self.hass, climates, ADVICE_DAYS)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Reading climate history for the advice failed", exc_info=True)
            samples = {}
        end = dt_util.utcnow()
        start = end - timedelta(days=ADVICE_DAYS)
        ranking = {r["room_id"]: r["label"] for r in self.room_ranking()}
        rooms = []
        for room in self.rooms:
            room_id = room[CONF_ROOM_ID]
            schedule = self.schedule(room)
            series = [samples[e] for e in room.get(CONF_ROOM_CLIMATES, []) if samples.get(e)]
            summary = await self.hass.async_add_executor_job(
                lambda series=series, schedule=schedule: summarize_setpoints(
                    series, start, end, schedule.start, schedule.end,
                    to_local=dt_util.as_local,
                )
            )
            measured_now = self.room_measurements(room)
            day_target = summary["day"]
            if day_target is None:
                day_target = self.comfort_temperature(room, measured_now)
            inside = summary["measured"]
            if inside is None:
                inside = measured_now["current_temperature"]
            estimate = self.model(room_id).estimate
            delta = inside - outdoor if inside is not None and outdoor is not None else None
            offset = schedule.offset
            if schedule.night_temp is not None and day_target is not None:
                offset = min(0.0, schedule.night_temp - day_target)
            rooms.append(
                RoomInput(
                    room_id=room_id,
                    name=room[CONF_ROOM_NAME],
                    weight=max(1, len(room.get(CONF_ROOM_CLIMATES, []))),
                    day_target=day_target,
                    night_target=summary["night"],
                    measured=inside,
                    cooling=estimate.cooling_coefficient,
                    heat_rate=estimate.heating_rate(delta),
                    confidence=estimate.confidence,
                    setback_enabled=self.room_enabled(room_id),
                    night_hours=window_hours(schedule.start, schedule.end),
                    offset=offset,
                    uses_global=room.get(CONF_ROOM_USE_GLOBAL, True),
                    optimum_start=schedule.optimum_start,
                    label=ranking.get(room_id),
                )
            )
        cfg = self.config
        boiler = self.boiler_status() if self.boiler_configured else None
        house = HouseInput(
            outdoor_mean=outdoor,
            heating_gas_per_day=heating_gas,
            gas_price=self.data.gas_price if self.data else self._gas_price()[0],
            days=len(records),
            measured_days=len(measured),
            measured_expected=sum(r["expected"] for r in measured),
            measured_actual=sum(r["gas"] for r in measured),
            master_enabled=self.master_enabled,
            global_offset=float(cfg.get(CONF_NIGHT_OFFSET, DEFAULT_NIGHT_OFFSET)),
            global_hours=window_hours(
                parse_time(cfg.get(CONF_NIGHT_START) or DEFAULT_NIGHT_START),
                parse_time(cfg.get(CONF_NIGHT_END) or DEFAULT_NIGHT_END),
            ),
            boiler_cycling=bool(boiler and boiler.get("cycling")),
        )
        result = build_advice(rooms, house)
        result["basis"]["measurement_start"] = self._measurement_start().isoformat()
        result["basis"]["generated"] = now.isoformat()
        self._advice = (now, result)
        return result

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
        start = self._measurement_start().isoformat()
        completed = {
            d: v for d, v in self._stored["savings"].items() if start <= d < today
        }
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

    def _fixed_costs(self) -> float:
        """Fixed gas delivery costs in € per day (0 when not set)."""
        return daily_fixed_costs(
            _float_or_none(self.config.get(CONF_GAS_FIXED_COSTS)),
            self.config.get(CONF_GAS_FIXED_COSTS_UNIT) or DEFAULT_FIXED_COSTS_UNIT,
        )

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
        price, source = self._gas_price()
        data = EnergyData(
            gas_price=price, gas_price_source=source, fixed_costs=self._fixed_costs()
        )

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

        limit_today = self.heating_limit_for(today.date())
        data.degree_days_today = accumulated_degree_days(
            data.mean_temp_today, limit_today, day_fraction(now)
        )
        data.degree_days_today_forecast = degree_days(data.mean_temp_today, limit_today)
        data.degree_days_yesterday = degree_days(
            data.mean_temp_yesterday, self.heating_limit_for(yesterday.date())
        )

        baseline = self.effective_baseline
        data.expected_today = expected_gas(baseline, data.degree_days_today)
        data.expected_yesterday = expected_gas(baseline, data.degree_days_yesterday)
        data.saved_today = gas_savings(data.expected_today, data.gas_today)
        data.saved_yesterday = gas_savings(data.expected_yesterday, data.gas_yesterday)

        yesterday_key = yesterday.date().isoformat()
        if (
            data.saved_yesterday is not None
            and yesterday_key >= self._measurement_start().isoformat()
            and self._stored["savings"].get(yesterday_key) != data.saved_yesterday
        ):
            self._stored["savings"][yesterday_key] = data.saved_yesterday
            self._async_save()
        data.saved_total, data.saved_total_days = self._saved_total(data.saved_today)
        data.cost_today = self.gas_cost(data.gas_today, price, data.fixed_costs)
        data.cost_yesterday = self.gas_cost(data.gas_yesterday, price, data.fixed_costs)

        # Keep yesterday permanently (also after the recorder purged its states).
        if data.mean_temp_yesterday is not None or data.gas_yesterday is not None:
            key = yesterday.date().isoformat()
            if key not in self._history["days"] or None in self._history["days"][key]:
                self._store_records(
                    [DayRecord(yesterday.date(), data.mean_temp_yesterday, data.gas_yesterday)]
                )
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
