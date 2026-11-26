"""Tests for the sidebar panel, WebSocket API, schedules and optimum start."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
    mock_restore_cache_with_extra_data,
)

from homeassistant.core import State
from homeassistant.util import dt as dt_util

DOMAIN = "ha_climate"


def _states(hass, living_target=21.0):
    hass.states.async_set(
        "sensor.outside",
        "5.0",
        {"device_class": "temperature", "unit_of_measurement": "°C", "state_class": "measurement"},
    )
    hass.states.async_set(
        "sensor.gas",
        "1000.0",
        {"device_class": "gas", "unit_of_measurement": "m³", "state_class": "total_increasing"},
    )
    hass.states.async_set(
        "climate.living",
        "heat",
        {"temperature": living_target, "current_temperature": 20.0, "hvac_action": "idle", "min_temp": 5},
    )
    hass.states.async_set(
        "climate.kitchen",
        "heat",
        {"temperature": 20.0, "current_temperature": 19.8, "hvac_action": "heating"},
    )


async def _setup(hass, rooms=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="HA Climate",
        data={"outdoor_sensor": "sensor.outside", "gas_sensor": "sensor.gas", "heating_limit": 18.0},
        options={
            "night_start": "22:00:00",
            "night_end": "06:30:00",
            "night_offset": -2.0,
            "rooms": rooms or [],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.usefixtures("recorder_mock")
async def test_panel_and_websocket(hass, ha_climate_enabled, hass_ws_client) -> None:
    """The panel is registered and rooms/settings can be managed over WebSocket."""
    _states(hass)
    calls = async_mock_service(hass, "climate", "set_temperature")
    entry = await _setup(hass)

    panels = hass.data["frontend_panels"]
    assert "ha-climate" in panels
    panel = panels["ha-climate"]
    assert panel.sidebar_icon == "mdi:thermostat"
    assert panel.sidebar_title == "HA Climate"
    assert panel.config["_panel_custom"]["module_url"].startswith("/ha_climate_static/ha-climate-panel.js")

    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "ha_climate/state"})
    msg = await client.receive_json()
    assert msg["success"], msg
    assert msg["result"]["rooms"] == []
    assert msg["result"]["settings"]["heating_limit"] == 18.0
    assert msg["result"]["energy"]["gas_price"] == pytest.approx(1.40)
    assert msg["result"]["energy"]["gas_price_source"] == "standaard"

    # Add a room.
    await client.send_json_auto_id(
        {
            "type": "ha_climate/room/save",
            "room": {"name": "Woonkamer en keuken", "climates": ["climate.living", "climate.kitchen"]},
        }
    )
    msg = await client.receive_json()
    assert msg["success"], msg
    room_id = msg["result"]["room_id"]
    await hass.async_block_till_done()
    assert hass.states.get("switch.ha_climate_night_setback_woonkamer_en_keuken").state == "on"
    assert hass.states.get("sensor.ha_climate_model_confidence_woonkamer_en_keuken") is not None

    # Saving without changes returns right away (no reload to wait for).
    await client.send_json_auto_id(
        {"type": "ha_climate/room/save", "room": {"id": room_id, "name": "Woonkamer en keuken"}}
    )
    msg = await client.receive_json()
    assert msg["success"], msg

    # Duplicate loop in another room is refused.
    await client.send_json_auto_id(
        {"type": "ha_climate/room/save", "room": {"name": "Keuken", "climates": ["climate.kitchen"]}}
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid"

    # Night above day is refused.
    await client.send_json_auto_id(
        {"type": "ha_climate/room/save", "room": {"id": room_id, "day_temp": 20, "night_temp": 21}}
    )
    msg = await client.receive_json()
    assert not msg["success"]

    # Schedule: day 21 / night 17, optimum start at 07:00.
    calls.clear()
    await client.send_json_auto_id(
        {
            "type": "ha_climate/room/save",
            "room": {
                "id": room_id,
                "day_temp": 21.0,
                "night_temp": 17.0,
                "comfort_time": "07:00",
                "optimum_start": True,
            },
        }
    )
    msg = await client.receive_json()
    assert msg["success"], msg
    await hass.async_block_till_done()
    # Day temperature is applied right away to the loop that differs.
    assert {c.data["entity_id"]: c.data["temperature"] for c in calls} == {"climate.kitchen": 21.0}

    await client.send_json_auto_id({"type": "ha_climate/state"})
    state = (await client.receive_json())["result"]
    room = state["rooms"][0]
    assert room["name"] == "Woonkamer en keuken"
    assert room["schedule"]["day_temp"] == 21.0
    assert room["schedule"]["night_temp"] == 17.0
    assert room["schedule"]["optimum_start"] is True
    assert room["preheat"]["method"] == "fallback"
    assert room["preheat"]["next_heating_start"] is not None
    assert room["model"]["confidence"] == 0

    # History endpoint works (no statistics yet -> only today).
    await client.send_json_auto_id({"type": "ha_climate/history", "days": 14})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["days"][-1]["partial"] is True

    # Settings: fixed gas price.
    await client.send_json_auto_id(
        {"type": "ha_climate/settings/save", "settings": {"gas_price": 1.1, "heating_limit": 17.5}}
    )
    msg = await client.receive_json()
    assert msg["success"], msg
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert coordinator.heating_limit == 17.5
    assert coordinator.data.gas_price == pytest.approx(1.1)
    assert coordinator.data.gas_price_source == "vast"

    # Master switch over WebSocket.
    await client.send_json_auto_id({"type": "ha_climate/master/set", "enabled": False})
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    assert hass.states.get("switch.ha_climate_all_thermostats_night_setback").state == "off"

    # Delete the room.
    await client.send_json_auto_id({"type": "ha_climate/room/delete", "room_id": room_id})
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    assert entry.runtime_data.rooms == []


@pytest.mark.usefixtures("recorder_mock")
async def test_absolute_night_temperature_and_optimum_start(hass, ha_climate_enabled) -> None:
    """Night temperature is absolute and optimum start restores before comfort time."""
    _states(hass)
    calls = async_mock_service(hass, "climate", "set_temperature")
    entry = await _setup(
        hass,
        rooms=[
            {
                "id": "r1",
                "name": "Slaapkamer",
                "climates": ["climate.living"],
                "use_global_night": True,
                "day_temp": 20.0,
                "night_temp": 16.0,
                "comfort_time": "07:00:00",
                "optimum_start": True,
            }
        ],
    )
    coordinator = entry.runtime_data
    base = dt_util.now().replace(hour=22, minute=1, second=0, microsecond=0)

    await coordinator._async_tick(base)  # noqa: SLF001
    await hass.async_block_till_done()
    assert [c.data["temperature"] for c in calls] == [16.0]
    hass.states.async_set(
        "climate.living", "heat", {"temperature": 16.0, "current_temperature": 18.0, "hvac_action": "idle"}
    )

    # 01:00: inside 18 °C, needs +2 °C. Fallback: 2 / 0.5 = 4 h + 15 min -> start 02:45.
    calls.clear()
    await coordinator._async_tick(base.replace(hour=1, minute=0) + timedelta(days=1))  # noqa: SLF001
    assert calls == []
    assert coordinator.room_setback_active("r1")
    plan = coordinator.plans["r1"]
    assert plan["method"] == "fallback"
    assert plan["lead_minutes"] == 255

    await coordinator._async_tick(base.replace(hour=2, minute=46) + timedelta(days=1))  # noqa: SLF001
    await hass.async_block_till_done()
    assert [c.data["temperature"] for c in calls] == [20.0]
    assert not coordinator.room_setback_active("r1")

    # It does not lower again later in the same night even if the plan moves.
    calls.clear()
    hass.states.async_set(
        "climate.living", "heat", {"temperature": 20.0, "current_temperature": 19.9, "hvac_action": "heating"}
    )
    await coordinator._async_tick(base.replace(hour=3, minute=30) + timedelta(days=1))  # noqa: SLF001
    assert calls == []
    assert coordinator.room_status(coordinator.rooms[0]) in ("preheating", "heating")


@pytest.mark.usefixtures("recorder_mock")
async def test_saved_total_is_restored(hass, ha_climate_enabled) -> None:
    """Gas saved total is restored via RestoreEntity when storage is empty."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.ha_climate_gas_saved_total", "12.5"),
                {"native_value": 12.5, "native_unit_of_measurement": "m³"},
            )
        ],
    )
    _states(hass)
    entry = await _setup(hass)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.ha_climate_gas_saved_total")
    assert state is not None
    assert float(state.state) == pytest.approx(12.5)
    assert entry.runtime_data._stored["savings_offset"] == pytest.approx(12.5)  # noqa: SLF001
