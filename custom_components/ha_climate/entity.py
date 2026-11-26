"""Base entity for HA Climate."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import HaClimateCoordinator


class HaClimateEntity(CoordinatorEntity[HaClimateCoordinator]):
    """Common base for all entities of the integration."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HaClimateCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer="ha-climate",
            model="Graaddagen & nachtverlaging",
            entry_type=DeviceEntryType.SERVICE,
        )
