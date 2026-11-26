"""Button platform: recalculate the baseline."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HaClimateConfigEntry
from .entity import HaClimateEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HaClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button."""
    async_add_entities([RecalculateBaselineButton(entry.runtime_data)])


class RecalculateBaselineButton(HaClimateEntity, ButtonEntity):
    """Re-read the long-term statistics and recalculate the baseline."""

    _attr_translation_key = "recalculate_baseline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "recalculate_baseline")

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_recalculate()
