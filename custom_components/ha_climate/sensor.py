"""Sensor platform: degree days, baseline, expected/actual gas and savings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CURRENCY_EURO, PERCENTAGE, EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ROOM_ID, CONF_ROOM_NAME
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
    return {"dagen": d.saved_total_days, **_attrs_price(c, d)}


def _attrs_price(c: HaClimateCoordinator, d: EnergyData) -> dict[str, Any]:
    return {"gasprijs": d.gas_price, "prijsbron": d.gas_price_source}


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
        attrs_fn=lambda c, d: {
            **_attrs_baseline(c, d),
            "betrouwbaar": bool(c.baseline and c.baseline.reliable),
        },
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
        key="saved_money_today",
        translation_key="saved_money_today",
        value_fn=lambda c, d: c.to_euro(d.saved_today),
        attrs_fn=_attrs_price,
        **EURO,
    ),
    HaClimateSensorDescription(
        key="saved_money_yesterday",
        translation_key="saved_money_yesterday",
        value_fn=lambda c, d: c.to_euro(d.saved_yesterday),
        attrs_fn=_attrs_price,
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
    entities: list[SensorEntity] = [
        HaClimateSensor(coordinator, desc) for desc in SENSORS
    ]
    entities.append(SavedGasTotalSensor(coordinator))
    for room in coordinator.rooms:
        entities.extend(
            RoomModelSensor(coordinator, room, desc) for desc in ROOM_SENSORS
        )
    async_add_entities(entities)


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


class SavedGasTotalSensor(HaClimateEntity, RestoreSensor):
    """Cumulative gas savings, restored after a restart."""

    _attr_translation_key = "saved_gas_total"
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_device_class = SensorDeviceClass.GAS
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: HaClimateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "saved_gas_total")
        self._restored: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known total."""
        await super().async_added_to_hass()
        value: Any = None
        if (last := await self.async_get_last_sensor_data()) is not None:
            value = last.native_value
        elif (last_state := await self.async_get_last_state()) is not None:
            value = last_state.state
        try:
            self._restored = float(value) if value is not None else None
        except (TypeError, ValueError):
            self._restored = None
        if self._restored is not None:
            self.coordinator.restore_saved_total(self._restored)
            await self.coordinator.async_request_refresh()

    @property
    def native_value(self) -> float | None:
        """Return the cumulative savings."""
        data = self.coordinator.data
        if data is None or data.saved_total is None:
            return self._restored
        return data.saved_total

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return None
        return _attrs_total(self.coordinator, self.coordinator.data)


# ---------------------------------------------------------------------------
# Thermal model sensors per room
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class RoomSensorDescription(SensorEntityDescription):
    """Describes a per-room sensor."""

    value_fn: Callable[[HaClimateCoordinator, dict[str, Any]], Any]


def _delta_t(c: HaClimateCoordinator, room: dict[str, Any]) -> float | None:
    inside = c.room_measurements(room)["current_temperature"]
    outside = c.outdoor_temperature()
    if inside is None or outside is None:
        return None
    return inside - outside


def _rounded(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


ROOM_SENSORS: tuple[RoomSensorDescription, ...] = (
    RoomSensorDescription(
        key="cooling_rate",
        translation_key="room_cooling_rate",
        native_unit_of_measurement="°C/h",
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c, r: _rounded(
            c.model(r[CONF_ROOM_ID]).estimate.cooling_rate(_delta_t(c, r))
        ),
    ),
    RoomSensorDescription(
        key="heating_rate",
        translation_key="room_heating_rate",
        native_unit_of_measurement="°C/h",
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c, r: _rounded(
            c.model(r[CONF_ROOM_ID]).estimate.heating_rate(_delta_t(c, r))
        ),
    ),
    RoomSensorDescription(
        key="model_confidence",
        translation_key="room_model_confidence",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c, r: c.model(r[CONF_ROOM_ID]).estimate.confidence,
    ),
    RoomSensorDescription(
        key="heating_start",
        translation_key="room_heating_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c, r: c.next_heating_start(r),
    ),
)


class RoomModelSensor(HaClimateEntity, SensorEntity):
    """Thermal model value of a room."""

    entity_description: RoomSensorDescription

    def __init__(
        self,
        coordinator: HaClimateCoordinator,
        room: dict[str, Any],
        description: RoomSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, f"{description.key}_{room[CONF_ROOM_ID]}")
        self.entity_description = description
        self._room = room
        self._attr_translation_placeholders = {"room": room[CONF_ROOM_NAME]}

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator, self._room)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return model details."""
        estimate = self.coordinator.model(self._room[CONF_ROOM_ID]).estimate
        attrs: dict[str, Any] = {
            "afkoelcoefficient_per_uur": _rounded(estimate.cooling_coefficient, 4),
            "verwarmingsvermogen_c_per_uur": _rounded(estimate.heating_power),
            "betrouwbaarheid_afkoelen": estimate.cooling_confidence,
            "betrouwbaarheid_opwarmen": estimate.heating_confidence,
            "meetmomenten": estimate.observations,
        }
        if self.entity_description.key == "heating_start":
            attrs.update(self.coordinator.plans.get(self._room[CONF_ROOM_ID], {}))
        return attrs
