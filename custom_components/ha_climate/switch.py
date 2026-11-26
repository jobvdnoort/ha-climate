"""Switch platform: night setback (global and per room)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ROOM_CLIMATES, CONF_ROOM_ID, CONF_ROOM_NAME
from .coordinator import HaClimateConfigEntry, HaClimateCoordinator
from .entity import HaClimateEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HaClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [NightSetbackSwitch(coordinator)]
    entities.extend(RoomNightSetbackSwitch(coordinator, room) for room in coordinator.rooms)
    async_add_entities(entities)


class NightSetbackSwitch(HaClimateEntity, SwitchEntity):
    """Master switch for the night setback."""

    _attr_translation_key = "night_setback"

    def __init__(self, coordinator: HaClimateCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "night_setback")

    @property
    def is_on(self) -> bool:
        """Return whether the night setback is enabled."""
        return self.coordinator.master_enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the rooms that are currently lowered."""
        return {
            "actief_in_ruimtes": [
                room[CONF_ROOM_NAME]
                for room in self.coordinator.rooms
                if self.coordinator.room_setback_active(room[CONF_ROOM_ID])
            ]
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the night setback."""
        await self.coordinator.async_set_master(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the night setback (lowered rooms are restored)."""
        await self.coordinator.async_set_master(False)


class RoomNightSetbackSwitch(HaClimateEntity, SwitchEntity):
    """Night setback switch for one room."""

    _attr_translation_key = "room_night_setback"

    def __init__(self, coordinator: HaClimateCoordinator, room: dict[str, Any]) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, f"night_setback_{room[CONF_ROOM_ID]}")
        self._room = room
        self._room_id = room[CONF_ROOM_ID]
        self._attr_translation_placeholders = {"room": room[CONF_ROOM_NAME]}

    @property
    def is_on(self) -> bool:
        """Return whether the night setback is enabled for this room."""
        return self.coordinator.room_enabled(self._room_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return room details."""
        settings = self.coordinator.night_settings(self._room)
        return {
            "lussen": self._room.get(CONF_ROOM_CLIMATES, []),
            "starttijd": settings.start.strftime("%H:%M"),
            "eindtijd": settings.end.strftime("%H:%M"),
            "verlaging": settings.offset,
            "verlaging_actief": self.coordinator.room_setback_active(self._room_id),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the night setback for this room."""
        await self.coordinator.async_set_room(self._room_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the night setback for this room."""
        await self.coordinator.async_set_room(self._room_id, False)
