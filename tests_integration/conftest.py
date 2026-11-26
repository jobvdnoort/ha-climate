"""Fixtures for the Home Assistant integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from homeassistant import loader

pytest_plugins = ["pytest_homeassistant_custom_component"]

COMPONENTS = str(Path(__file__).parent.parent / "custom_components")


@pytest.fixture
def ha_climate_enabled(hass):
    """Make the custom integration of this repository discoverable."""
    import custom_components  # noqa: PLC0415

    if COMPONENTS not in custom_components.__path__:
        custom_components.__path__.append(COMPONENTS)
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
