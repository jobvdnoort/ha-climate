"""Binary sensor platform: fireplace detection."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_FIREPLACE_CLIMATE
from .coordinator import HaClimateConfigEntry
from .entity import HaClimateEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HaClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    if coordinator.fireplace_configured:
        async_add_entities([FireplaceBinarySensor(coordinator)])


class FireplaceBinarySensor(HaClimateEntity, BinarySensorEntity):
    """Indicates that the fireplace is burning."""

    _attr_translation_key = "fireplace_active"
    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "fireplace_active")

    @property
    def is_on(self) -> bool:
        """Return whether the fireplace is active."""
        return self.coordinator.fireplace.active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic attributes."""
        detector = self.coordinator.fireplace
        return {
            "thermostaat": self.coordinator.config.get(CONF_FIREPLACE_CLIMATE),
            "drempel": detector.threshold,
            "verschil_met_doel": _round(detector.delta_to_target),
            "stijging_laatste_uur": _round(detector.rise),
            "laatst_verwarmd": detector.last_heating.isoformat()
            if detector.last_heating
            else None,
            "minuten_vandaag": self.coordinator.fireplace_minutes_today(),
        }


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None
