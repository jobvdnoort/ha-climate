"""Constants for the HA Climate integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ha_climate"
NAME: Final = "HA Climate"

# --- Configuration keys -----------------------------------------------------
CONF_OUTDOOR_SENSOR: Final = "outdoor_sensor"
CONF_GAS_SENSOR: Final = "gas_sensor"
CONF_GAS_PRICE: Final = "gas_price"
CONF_GAS_PRICE_ENTITY: Final = "gas_price_entity"
CONF_GAS_FIXED_COSTS: Final = "gas_fixed_costs"
CONF_GAS_FIXED_COSTS_UNIT: Final = "gas_fixed_costs_unit"  # "month" or "day"
CONF_SAVINGS_START: Final = "savings_start"
CONF_DD_INDOOR_CORRECTION: Final = "degree_day_indoor_correction"
# Comfort temperature the baseline period was heated to (reference of the correction).
CONF_DD_REFERENCE_TEMP: Final = "degree_day_reference_temp"
CONF_HEATING_LIMIT: Final = "heating_limit"
CONF_BASELINE_DAYS: Final = "baseline_days"

CONF_NIGHT_START: Final = "night_start"
CONF_NIGHT_END: Final = "night_end"
CONF_NIGHT_OFFSET: Final = "night_offset"

CONF_ROOMS: Final = "rooms"
CONF_ROOM_ID: Final = "id"
CONF_ROOM_NAME: Final = "name"
CONF_ROOM_CLIMATES: Final = "climates"
CONF_ROOM_AIRCOS: Final = "aircos"
# Optional valve position / actuator sensors (0-100 %) of the floor heating loops.
CONF_ROOM_VALVES: Final = "valves"
CONF_ROOM_USE_GLOBAL: Final = "use_global_night"
CONF_ROOM_SELECT: Final = "room"
CONF_DAY_TEMP: Final = "day_temp"
CONF_NIGHT_TEMP: Final = "night_temp"
CONF_COMFORT_TIME: Final = "comfort_time"
CONF_OPTIMUM_START: Final = "optimum_start"
# Optional comfort periods of a day: [{"start": "06:30:00", "end": "07:30:00"}, ...].
# Outside these periods the room is lowered (replaces the night window).
CONF_PERIODS: Final = "periods"
MAX_PERIODS: Final = 6

CONF_FIREPLACE_CLIMATE: Final = "fireplace_climate"
CONF_FIREPLACE_TEMP_SENSOR: Final = "fireplace_temp_sensor"
CONF_FIREPLACE_THRESHOLD: Final = "fireplace_threshold"

# Optional boiler (OpenTherm) entities.
CONF_BOILER_FLAME: Final = "boiler_flame"
CONF_BOILER_HEAT_REQUEST: Final = "boiler_heat_request"
CONF_BOILER_DHW: Final = "boiler_dhw"
CONF_BOILER_MODULATION: Final = "boiler_modulation"
CONF_BOILER_FLOW_TEMP: Final = "boiler_flow_temp"
CONF_BOILER_FLOW_SETPOINT: Final = "boiler_flow_setpoint"
CONF_BOILER_PRESSURE: Final = "boiler_pressure"
CONF_BOILER_ERROR: Final = "boiler_error"
CONF_BOILER_STARTS_TODAY: Final = "boiler_starts_today"
CONF_BOILER_HOURS_TODAY: Final = "boiler_hours_today"
CONF_BOILER_AVG_RUNTIME: Final = "boiler_avg_runtime"
BOILER_KEYS: Final = (
    CONF_BOILER_FLAME,
    CONF_BOILER_HEAT_REQUEST,
    CONF_BOILER_DHW,
    CONF_BOILER_MODULATION,
    CONF_BOILER_FLOW_TEMP,
    CONF_BOILER_FLOW_SETPOINT,
    CONF_BOILER_PRESSURE,
    CONF_BOILER_ERROR,
    CONF_BOILER_STARTS_TODAY,
    CONF_BOILER_HOURS_TODAY,
    CONF_BOILER_AVG_RUNTIME,
)
BOILER_BINARY_KEYS: Final = (CONF_BOILER_FLAME, CONF_BOILER_HEAT_REQUEST, CONF_BOILER_DHW)

# --- Defaults ---------------------------------------------------------------
DEFAULT_HEATING_LIMIT: Final = 18.0
DEFAULT_DD_REFERENCE_TEMP: Final = 20.0
# 0 = use all history since both sensors have data.
DEFAULT_BASELINE_DAYS: Final = 0
DEFAULT_NIGHT_START: Final = "22:00:00"
DEFAULT_NIGHT_END: Final = "06:30:00"
DEFAULT_NIGHT_OFFSET: Final = -2.0
DEFAULT_FIREPLACE_THRESHOLD: Final = 0.5
DEFAULT_COMFORT_TIME: Final = "07:00:00"
DEFAULT_FIXED_COSTS_UNIT: Final = "month"
# Share of time heating is evaluated over this period for the room ranking.
RANKING_DAYS: Final = 7
ADVICE_DAYS: Final = 10  # days of setpoints and gas the advice is based on
ADVICE_CACHE: Final = timedelta(minutes=10)
MAX_EVENTS: Final = 2000
AIRCO_ACTIVE_ACTIONS: Final = frozenset({"heating", "cooling", "preheating"})
AIRCO_DEFAULT_COOL_TEMP: Final = 22.0
# Used for the euro savings when no gas price is configured (NL 2026, incl. taxes).
DEFAULT_GAS_PRICE: Final = 1.40

# --- Tuning -----------------------------------------------------------------
UPDATE_INTERVAL: Final = timedelta(minutes=5)
# Window in which a temperature rise is evaluated for fireplace detection.
FIREPLACE_RISE_WINDOW: Final = timedelta(minutes=60)
# A rise only counts if the floor heating did not heat during this period
# (floor heating keeps warming the room for a while after it stops).
FIREPLACE_HEATING_COOLDOWN: Final = timedelta(minutes=60)
# A day is excluded from the baseline when the fireplace burned at least this long.
FIREPLACE_EXCLUDE_MINUTES: Final = 30
# Days with fewer degree days are ignored for the baseline (mostly hot water usage).
BASELINE_MIN_DEGREE_DAYS: Final = 1.0
# Minimum number of usable days before a baseline is considered valid.
BASELINE_MIN_DAYS: Final = 7

# Window and resolution of the boiler chart.
BOILER_TRACE_HOURS: Final = 24
BOILER_TRACE_STEP: Final = timedelta(minutes=5)

# --- Storage ----------------------------------------------------------------
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.storage"
HISTORY_STORAGE_KEY: Final = f"{DOMAIN}.history"
# Number of days kept in the persisted day-based history.
HISTORY_RETENTION_DAYS: Final = 800

# --- Frontend panel ---------------------------------------------------------
PANEL_URL_PATH: Final = "ha-climate"
PANEL_COMPONENT: Final = "ha-climate-panel"
PANEL_STATIC_URL: Final = "/ha_climate_static"
PANEL_ICON: Final = "mdi:thermostat"
PANEL_TITLE: Final = "HA Climate"

# --- Services ---------------------------------------------------------------
SERVICE_RECALCULATE_BASELINE: Final = "recalculate_baseline"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"

HEATING_ACTIONS: Final = frozenset({"heating", "preheating"})
