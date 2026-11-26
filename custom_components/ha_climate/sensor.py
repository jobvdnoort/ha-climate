"""Sensor platform: degree days, baseline, expected/actual gas and savings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import CURRENCY_EURO, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EnergyData, HaClimateConfigEntry, HaClimateCoordinator
from .entity import HaClimateEntity

PARALLEL_UPDATES = 0

UNIT_DEGREE_DAYS = "graaddagen"
UNIT_M3_PER_DD = "m³/graaddag"


@dataclass(frozen=True, kw_only=True)
class HaClimateSensorDescription(SensorEntityDescription):
    """Describes a HA Climate sensor."""

    value_fn: Callable[[HaClimateCoordinator, EnergyData], float | None]
    attrs_fn: Callable[[HaClimateCoordinator, EnergyData], dict[str, Any]] | None = None


def _attrs_dd_today(c: HaClimateCoordinator, d: EnergyData) -> dict[str, Any]:
    return {
        "prognose_volledige_dag": _round(d.degree_days_today_forecast, 2),
        "gemiddelde_buitentemperatuur": _round(d.mean_temp_today, 1),
        "stookgrens": c.heating_limit,
    }


def _attrs_dd_yesterday(c: HaClimateCoordinator, d: EnergyData) -> dict[str, Any]:
    return {
        "gemiddelde_buitentemperatuur": _round(d.mean_temp_yesterday, 1),
        "stookgrens": c.heating_limit,
    }


def _attrs_baseline(c: HaClimateCoordinator, d: EnergyData) -> dict[str, Any]:
    b = c.baseline
    if b is None:
        return {}
    return {
        "dagen_gebruikt": b.days_used,
        "totaal_gas_m3": round(b.total_gas, 2),
        "totaal_graaddagen": round(b.total_degree_days, 1),
        "uitgesloten_openhaard": b.excluded_fireplace,
        "uitgesloten_nachtverlaging": b.excluded_setback,
        "uitgesloten_warm": b.excluded_warm,
        "uitgesloten_onvolledig": b.excluded_invalid,
        "eerste_dag": b.first_day.isoformat() if b.first_day else None,
        "laatste_dag": b.last_day.isoformat() if b.last_day else None,
        "laatst_berekend": c.baseline_updated.isoformat() if c.baseline_updated else None,
    }


def _attrs_total(c: HaClimateCoordinator, d: EnergyData) -> dict[str, Any]:
    return {"dagen": d.saved_total_days}


def _baseline_value(c: HaClimateCoordinator, d: EnergyData) -> float | None:
    return c.baseline.m3_per_degree_day if c.baseline else None


GAS = {
    "native_unit_of_measurement": UnitOfVolume.CUBIC_METERS,
    "device_class": SensorDeviceClass.GAS,
    "suggested_display_precision": 2,
}
EURO = {
    "native_unit_of_measurement": CURRENCY_EURO,
    "device_class": SensorDeviceClass.MONETARY,
    "suggested_display_precision": 2,
}
DD = {
    "native_unit_of_measurement": UNIT_DEGREE_DAYS,
    "suggested_display_precision": 1,
    "icon": "mdi:thermometer-lines",
}

SENSORS: tuple[HaClimateSensorDescription, ...] = (
    HaClimateSensorDescription(
        key="degree_days_today",
        translation_key="degree_days_today",
        value_fn=lambda c, d: d.degree_days_today,
        attrs_fn=_attrs_dd_today,
        **DD,
    ),
    HaClimateSensorDescription(
        key="degree_days_yesterday",
        translation_key="degree_days_yesterday",
        value_fn=lambda c, d: d.degree_days_yesterday,
        attrs_fn=_attrs_dd_yesterday,
        **DD,
    ),
    HaClimateSensorDescription(
        key="baseline",
        translation_key="baseline",
        native_unit_of_measurement=UNIT_M3_PER_DD,
        suggested_display_precision=3,
        icon="mdi:chart-bell-curve-cumulative",
        value_fn=_baseline_value,
        attrs_fn=_attrs_baseline,
    ),
    HaClimateSensorDescription(
        key="expected_gas_today",
        translation_key="expected_gas_today",
        value_fn=lambda c, d: d.expected_today,
        **GAS,
    ),
    HaClimateSensorDescription(
        key="expected_gas_yesterday",
        translation_key="expected_gas_yesterday",
        value_fn=lambda c, d: d.expected_yesterday,
        **GAS,
    ),
    HaClimateSensorDescription(
        key="actual_gas_today",
        translation_key="actual_gas_today",
        value_fn=lambda c, d: d.gas_today,
        **GAS,
    ),
    HaClimateSensorDescription(
        key="actual_gas_yesterday",
        translation_key="actual_gas_yesterday",
        value_fn=lambda c, d: d.gas_yesterday,
        **GAS,
    ),
    HaClimateSensorDescription(
        key="saved_gas_today",
        translation_key="saved_gas_today",
        value_fn=lambda c, d: d.saved_today,
        **GAS,
    ),
    HaClimateSensorDescription(
        key="saved_gas_yesterday",
        translation_key="saved_gas_yesterday",
        value_fn=lambda c, d: d.saved_yesterday,
        **GAS,
    ),
    HaClimateSensorDescription(
        key="saved_gas_total",
        translation_key="saved_gas_total",
        value_fn=lambda c, d: d.saved_total,
        attrs_fn=_attrs_total,
        **GAS,
    ),
    HaClimateSensorDescription(
        key="saved_money_today",
        translation_key="saved_money_today",
        value_fn=lambda c, d: c.to_euro(d.saved_today),
        **EURO,
    ),
    HaClimateSensorDescription(
        key="saved_money_yesterday",
        translation_key="saved_money_yesterday",
        value_fn=lambda c, d: c.to_euro(d.saved_yesterday),
        **EURO,
    ),
    HaClimateSensorDescription(
        key="saved_money_total",
        translation_key="saved_money_total",
        value_fn=lambda c, d: c.to_euro(d.saved_total),
        attrs_fn=_attrs_total,
        **EURO,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HaClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(HaClimateSensor(coordinator, desc) for desc in SENSORS)


class HaClimateSensor(HaClimateEntity, SensorEntity):
    """A HA Climate sensor."""

    entity_description: HaClimateSensorDescription

    def __init__(
        self, coordinator: HaClimateCoordinator, description: HaClimateSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator, self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None or self.coordinator.data is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator, self.coordinator.data)


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None
