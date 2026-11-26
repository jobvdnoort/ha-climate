"""HA Climate: degree days, gas savings and night setback for floor heating."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_CONFIG_ENTRY_ID, DOMAIN, SERVICE_RECALCULATE_BASELINE
from .coordinator import HaClimateConfigEntry, HaClimateCoordinator, async_restore_all
from .panel import async_register_panel, async_unregister_panel
from .websocket_api import async_register_websocket_api

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration services and the panel's WebSocket API."""
    async_register_websocket_api(hass)

    async def _async_recalculate(call: ServiceCall) -> dict:
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        entries: list[HaClimateConfigEntry] = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
            and (entry_id is None or entry.entry_id == entry_id)
        ]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_entry"
            )
        response = {}
        for entry in entries:
            coordinator = entry.runtime_data
            result = await coordinator.async_recalculate_baseline()
            await coordinator.async_request_refresh()
            response[entry.entry_id] = {
                "m3_per_degree_day": result.m3_per_degree_day if result else None,
                "days_used": result.days_used if result else 0,
            }
        return response

    hass.services.async_register(
        DOMAIN,
        SERVICE_RECALCULATE_BASELINE,
        _async_recalculate,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HaClimateConfigEntry) -> bool:
    """Set up HA Climate from a config entry."""
    coordinator = HaClimateCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start()
    await async_register_panel(hass)
    entry.async_on_unload(coordinator.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HaClimateConfigEntry) -> bool:
    """Unload a config entry."""
    # The panel stays registered: removing it on every reload (e.g. after saving
    # a room in the panel) would kick the user out of the page.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Restore lowered thermostats, remove stored data and the panel."""
    await async_restore_all(hass, entry.entry_id)
    if not any(
        other.entry_id != entry.entry_id for other in hass.config_entries.async_entries(DOMAIN)
    ):
        async_unregister_panel(hass)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
