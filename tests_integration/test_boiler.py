"""Tests for the optional boiler (OpenTherm) analysis and valve position sensors."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.util import dt as dt_util

DOMAIN = "ha_climate"
ROOM = {
    "id": "r1",
    "name": "Woonkamer",
    "climates": ["climate.loop1"],
    "valves": ["sensor.valve1", "sensor.valve2"],
    "use_global_night": True,
}
BOILER = {
    "boiler_flame": "binary_sensor.cv_vlam_status",
    "boiler_dhw": "binary_sensor.cv_warm_water_status",
    "boiler_modulation": "sensor.cv_degree_of_modulation",
    "boiler_flow_temp": "sensor.cv_h1_water_temperatuur",
    "boiler_flow_setpoint": "sensor.cv_h1_flow_setpoint_value",
    "boiler_pressure": "sensor.cv_waterdruk",
    "boiler_error": "sensor.cv_error_code",
}


def _states(hass, flame="off", dhw="off", pressure="1.1"):
    hass.states.async_set("sensor.outside", "5.0", {"device_class": "temperature", "state_class": "measurement"})
    hass.states.async_set("sensor.gas", "1000.0", {"device_class": "gas", "state_class": "total_increasing"})
    hass.states.async_set(
        "climate.loop1", "heat", {"temperature": 21.0, "current_temperature": 20.0, "hvac_action": "idle"}
    )
    hass.states.async_set("sensor.valve1", "40", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.valve2", "80", {"unit_of_measurement": "%"})
    hass.states.async_set("binary_sensor.cv_vlam_status", flame)
    hass.states.async_set("binary_sensor.cv_warm_water_status", dhw)
    hass.states.async_set("sensor.cv_degree_of_modulation", "35", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.cv_h1_water_temperatuur", "42.5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.cv_h1_flow_setpoint_value", "45", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.cv_waterdruk", pressure, {"unit_of_measurement": "bar"})
    hass.states.async_set("sensor.cv_error_code", "0")


async def _setup(hass, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="HA Climate",
        data={"outdoor_sensor": "sensor.outside", "gas_sensor": "sensor.gas", "heating_limit": 18.0},
        options={"rooms": [ROOM], **(options or {})},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.usefixtures("recorder_mock")
async def test_without_boiler_nothing_changes(hass, ha_climate_enabled, hass_ws_client) -> None:
    """No boiler entities: no boiler payload and no boiler columns."""
    _states(hass)
    await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "ha_climate/state"})
    result = (await client.receive_json())["result"]
    assert result["boiler"] is None
    # The valves are still shown on the room.
    room = result["rooms"][0]
    assert room["valve"] == 60
    assert room["valve_max"] == 80
    await client.send_json_auto_id({"type": "ha_climate/history", "days": 3})
    rows = (await client.receive_json())["result"]["days"]
    assert all("boiler" not in row for row in rows)
    await client.send_json_auto_id({"type": "ha_climate/boiler/trace"})
    assert (await client.receive_json())["result"] == {"points": []}


@pytest.mark.usefixtures("recorder_mock")
async def test_boiler_settings_tracking_and_trace(hass, ha_climate_enabled, hass_ws_client) -> None:
    """Boiler entities are saved in the settings, starts are counted and charted."""
    _states(hass)
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "ha_climate/settings/save", "settings": BOILER})
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    for key, value in BOILER.items():
        assert entry.options[key] == value

    # Invalid domains are rejected.
    await client.send_json_auto_id(
        {"type": "ha_climate/settings/save", "settings": {"boiler_flame": "sensor.cv_vlam_status"}}
    )
    assert not (await client.receive_json())["success"]

    coordinator = entry.runtime_data
    now = dt_util.now().replace(hour=10, minute=0, second=0, microsecond=0)
    # Two short runs (pendelen) and one hot water run.
    for start, length, dhw in ((0, 4, "off"), (10, 5, "off"), (20, 6, "on"), (30, 7, "off")):
        _states(hass, flame="off", dhw=dhw)
        coordinator._track_boiler(now + timedelta(minutes=start - 1), sample=True)  # noqa: SLF001
        _states(hass, flame="on", dhw=dhw)
        for minute in range(length):
            coordinator._track_boiler(now + timedelta(minutes=start + minute), sample=True)  # noqa: SLF001
        _states(hass, flame="off", dhw=dhw)
        coordinator._track_boiler(now + timedelta(minutes=start + length), sample=True)  # noqa: SLF001

    today = coordinator.boiler_day(now.date())
    assert today["starts"] == 4
    assert today["burn_hours"] == pytest.approx(22 / 60)
    assert today["avg_run_minutes"] == pytest.approx(5.5)
    assert today["short_runs"] == 4
    assert today["dhw_minutes"] == pytest.approx(6)
    assert today["heat_minutes"] == pytest.approx(16)
    assert today["flow_avg"] == pytest.approx(42.5)

    await client.send_json_auto_id({"type": "ha_climate/state"})
    boiler = (await client.receive_json())["result"]["boiler"]
    assert boiler["flame"] is False
    assert boiler["modulation"] == 35
    assert boiler["flow_setpoint"] == 45
    assert boiler["pressure_status"] == "low"
    assert boiler["error"] == "0"
    assert boiler["max_valve"] == 80
    assert boiler["cycling"] is True
    assert boiler["today"]["starts"] == 4

    # A state change of the flame sensor counts a start right away.
    hass.states.async_set("binary_sensor.cv_vlam_status", "on")
    await hass.async_block_till_done()
    assert coordinator.boiler.flame is True

    await client.send_json_auto_id({"type": "ha_climate/history", "days": 3})
    rows = (await client.receive_json())["result"]["days"]
    assert rows[-1]["boiler"]["starts"] >= 4

    await client.send_json_auto_id({"type": "ha_climate/export"})
    days = (await client.receive_json())["result"]["days"]
    assert "boiler" in days[-1]

    await client.send_json_auto_id({"type": "ha_climate/boiler/trace"})
    points = (await client.receive_json())["result"]["points"]
    assert points
    assert {"flow", "setpoint", "modulation", "flame", "dhw", "valve_max"} <= set(points[0])


@pytest.mark.usefixtures("recorder_mock")
async def test_room_valves_save_and_model(hass, ha_climate_enabled, hass_ws_client) -> None:
    """Valve sensors are saved per room and drive the model's duty."""
    _states(hass)
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "ha_climate/room/save", "room": {"id": "r1", "valves": ["sensor.valve1"]}}
    )
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert coordinator.room("r1")["valves"] == ["sensor.valve1"]

    # A second room may not reuse the same valve sensor.
    hass.states.async_set("climate.loop2", "heat", {"temperature": 20.0, "current_temperature": 19.0})
    await client.send_json_auto_id(
        {
            "type": "ha_climate/room/save",
            "room": {"name": "Keuken", "climates": ["climate.loop2"], "valves": ["sensor.valve1"]},
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]

    # In the past, so the real minute tick cannot mix into the simulated window.
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(days=2)
    start -= timedelta(hours=start.hour % 2)
    for minute in range(122):
        coordinator._learn(start + timedelta(minutes=minute))  # noqa: SLF001
    observations = coordinator.model("r1").observations
    assert len(observations) == 1
    assert observations[0].duty == pytest.approx(0.4)
