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
CONF_HEATING_LIMIT: Final = "heating_limit"
CONF_BASELINE_DAYS: Final = "baseline_days"

CONF_NIGHT_START: Final = "night_start"
CONF_NIGHT_END: Final = "night_end"
CONF_NIGHT_OFFSET: Final = "night_offset"

CONF_ROOMS: Final = "rooms"
CONF_ROOM_ID: Final = "id"
CONF_ROOM_NAME: Final = "name"
CONF_ROOM_CLIMATES: Final = "climates"
CONF_ROOM_USE_GLOBAL: Final = "use_global_night"
CONF_ROOM_SELECT: Final = "room"

CONF_FIREPLACE_CLIMATE: Final = "fireplace_climate"
CONF_FIREPLACE_TEMP_SENSOR: Final = "fireplace_temp_sensor"
CONF_FIREPLACE_THRESHOLD: Final = "fireplace_threshold"

# --- Defaults ---------------------------------------------------------------
DEFAULT_HEATING_LIMIT: Final = 18.0
DEFAULT_BASELINE_DAYS: Final = 365
DEFAULT_NIGHT_START: Final = "22:00:00"
DEFAULT_NIGHT_END: Final = "06:30:00"
DEFAULT_NIGHT_OFFSET: Final = -2.0
DEFAULT_FIREPLACE_THRESHOLD: Final = 0.5

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

# --- Storage ----------------------------------------------------------------
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.storage"
# Number of days kept in the persisted day-based history.
HISTORY_RETENTION_DAYS: Final = 800

# --- Services ---------------------------------------------------------------
SERVICE_RECALCULATE_BASELINE: Final = "recalculate_baseline"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"

HEATING_ACTIONS: Final = frozenset({"heating", "preheating"})
