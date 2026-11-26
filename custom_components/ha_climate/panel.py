"""Sidebar panel: serves the frontend from ``custom_components/ha_climate/frontend``."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_COMPONENT,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
)

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"
DATA_STATIC = f"{DOMAIN}_static_registered"
DATA_PANEL = f"{DOMAIN}_panel_registered"


def _version() -> str:
    manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
    return manifest.get("version", "0")


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the static files and the sidebar panel (idempotent)."""
    if not hass.data.get(DATA_STATIC):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[DATA_STATIC] = True
    if hass.data.get(DATA_PANEL):
        return
    version = await hass.async_add_executor_job(_version)
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_COMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{PANEL_STATIC_URL}/ha-climate-panel.js?v={version}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=False,
        config={"domain": DOMAIN},
    )
    hass.data[DATA_PANEL] = True


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel (static path stays registered)."""
    if hass.data.pop(DATA_PANEL, False):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
