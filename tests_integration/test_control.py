"""Room temperature control, aircos, savings start, advice, events, export and costs."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from homeassistant.util import dt as dt_util

from .test_history import _import

DOMAIN = "ha_climate"
ROOM = {
    "id": "r1",
    "name": "Woonkamer",
    "climates": ["climate.loop1", "climate.loop2"],
    "aircos": ["climate.airco"],
    "use_global_night": True,
}


def _states(hass, airco_action="idle", airco_mode="off") -> None:
    hass.states.async_set(
        "sensor.outside", "5.0",
        {"device_class": "temperature", "unit_of_measurement": "°C", "state_class": "measurement"},
    )
    hass.states.async_set(
        "sensor.gas", "1000.0",
        {"device_class": "gas", "unit_of_measurement": "m³", "state_class": "total_increasing"},
    )
    for entity_id, temp in (("climate.loop1", 20.0), ("climate.loop2", 20.5)):
        hass.states.async_set(
            entity_id, "heat",
            {"temperature": temp, "current_temperature": 19.5, "hvac_action": "idle",
             "min_temp": 5, "max_temp": 28},
        )
    hass.states.async_set(
        "climate.airco", airco_mode,
        {"temperature": 22.0, "current_temperature": 21.0, "hvac_action": airco_action,
         "hvac_modes": ["off", "cool", "heat"]},
    )


async def _setup(hass, **options):
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=3,
        data={"outdoor_sensor": "sensor.outside", "gas_sensor": "sensor.gas", "heating_limit": 18.0},
        options={"rooms": [dict(ROOM)], "night_start": "22:00:00", "night_end": "06:30:00",
                 "night_offset": -2.0, **options},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.usefixtures("recorder_mock")
async def test_room_temperature_and_airco(hass, ha_climate_enabled, hass_ws_client) -> None:
    """+/- sets every loop at once; aircos are controlled separately."""
    _states(hass)
    temp_calls = async_mock_service(hass, "climate", "set_temperature")
    mode_calls = async_mock_service(hass, "climate", "set_hvac_mode")
    entry = await _setup(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": "ha_climate/room/set_temperature", "room_id": "r1", "temperature": 21.5}
    )
    msg = await client.receive_json()
    assert msg["success"], msg
    assert sorted(msg["result"]["entities"]) == ["climate.loop1", "climate.loop2"]
    assert {c.data["entity_id"]: c.data["temperature"] for c in temp_calls} == {
        "climate.loop1": 21.5,
        "climate.loop2": 21.5,
    }  # the airco is not touched

    # Airco: cool, boost, off and a temperature.
    temp_calls.clear()
    for mode in ("cool", "boost", "off"):
        await client.send_json_auto_id({"type": "ha_climate/airco", "room_id": "r1", "mode": mode})
        assert (await client.receive_json())["success"]
    assert [c.data["hvac_mode"] for c in mode_calls] == ["cool", "heat", "off"]
    # Boost heats to the comfort temperature (mean loop target 20.25) + 0.5.
    assert temp_calls[-1].data == {"entity_id": "climate.airco", "temperature": pytest.approx(20.75)}
    await client.send_json_auto_id({"type": "ha_climate/airco", "room_id": "r1", "temperature": 23})
    assert (await client.receive_json())["success"]
    assert temp_calls[-1].data["temperature"] == 23

    # The state exposes the airco next to (not inside) the loops.
    await client.send_json_auto_id({"type": "ha_climate/state"})
    room = (await client.receive_json())["result"]["rooms"][0]
    assert [a["entity_id"] for a in room["aircos"]] == ["climate.airco"]
    assert [loop["entity_id"] for loop in room["loops"]] == ["climate.loop1", "climate.loop2"]

    # Night setback only lowers the loops, never the airco.
    temp_calls.clear()
    coordinator = entry.runtime_data
    night = dt_util.now().replace(hour=22, minute=1, second=0, microsecond=0)
    await coordinator._async_tick(night)  # noqa: SLF001
    assert {c.data["entity_id"] for c in temp_calls} == {"climate.loop1", "climate.loop2"}


@pytest.mark.usefixtures("recorder_mock")
async def test_active_airco_is_excluded_from_model(hass, ha_climate_enabled) -> None:
    """Samples while the airco heats/cools invalidate the window."""
    _states(hass, airco_action="cooling", airco_mode="cool")
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    assert coordinator.room_measurements(ROOM)["airco_active"] is True
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    start -= timedelta(hours=start.hour % 2)
    for minute in range(121):
        coordinator._learn(start + timedelta(minutes=minute))  # noqa: SLF001
    assert coordinator.model("r1").observations == []

    _states(hass)  # airco off again -> windows are used
    for minute in range(121, 121 + 241):
        coordinator._learn(start + timedelta(minutes=minute))  # noqa: SLF001
    assert len(coordinator.model("r1").observations) == 1
    # Indoor temperatures are logged per day.
    measured, target = coordinator.indoor_day(start.astimezone(dt_util.get_default_time_zone()).date())
    assert measured == pytest.approx(19.5)
    assert target == pytest.approx(20.25)


@pytest.mark.usefixtures("recorder_mock")
async def test_savings_start_events_and_export(hass, ha_climate_enabled, hass_ws_client) -> None:
    """Baseline from the days before the savings start, change events and CSV rows."""
    _states(hass)
    async_mock_service(hass, "climate", "set_temperature")
    _import(hass, temp_days=30, gas_days=30)
    await async_wait_recording_done(hass)
    entry = await _setup(hass, gas_price=1.0, gas_fixed_costs=30.4375)
    coordinator = entry.runtime_data
    await coordinator.async_recalculate()
    assert coordinator.data.fixed_costs == pytest.approx(1.0)  # €/month -> €/day
    client = await hass_ws_client(hass)

    today = dt_util.now().date()
    start = today - timedelta(days=10)
    await client.send_json_auto_id(
        {"type": "ha_climate/settings/save", "settings": {"savings_start": start.isoformat()}}
    )
    msg = await client.receive_json()
    assert msg["success"], msg
    coordinator = entry.runtime_data
    await coordinator.async_recalculate_baseline()
    info = coordinator.baseline_info()
    assert info["savings_start"] == start.isoformat()
    assert info["baseline_end"] == start.isoformat()
    assert coordinator.baseline.last_day < start
    assert coordinator.effective_baseline == pytest.approx(0.4, abs=1e-6)

    # Tips: measured days since the start and estimates per month.
    await client.send_json_auto_id({"type": "ha_climate/advice", "refresh": True})
    msg = await client.receive_json()
    assert msg["success"], msg
    advice = msg["result"]
    assert advice["basis"]["measured_days"] == 10
    assert advice["basis"]["days"] == 10
    ids = {t["id"] for t in advice["tips"]}
    assert "measurement" in ids
    assert "day-lower" in ids
    assert advice["rooms"][0]["day_target"] == pytest.approx(20.25)

    rows = await coordinator.async_history(30)
    before = [r for r in rows if r["date"] < start.isoformat()]
    after = [r for r in rows if r["date"] >= start.isoformat() and not r.get("partial")]
    assert all(r["cumulative_saved"] is None for r in before)
    assert after[0]["cumulative_saved"] == pytest.approx(after[0]["saved"])
    assert rows[0]["cost"] == pytest.approx(4.0 * 1.0 + 1.0, abs=1e-6)

    # Events: master off/on and a changed night setting.
    await client.send_json_auto_id({"type": "ha_climate/master/set", "enabled": False})
    assert (await client.receive_json())["success"]
    await client.send_json_auto_id(
        {"type": "ha_climate/settings/save", "settings": {"night_offset": -1.5, "night_start": "21:30"}}
    )
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    texts = [e["text"] for e in coordinator._history["events"]]  # noqa: SLF001
    assert "Nachtverlaging uit (alle thermostaten, -2,0 °C, 22:00–06:30)" in texts
    assert "Nachtverlaging aangepast: -1,5 °C, 21:30–06:30" in texts

    # Every night setting gets its own measured period.
    periods = coordinator.setting_periods()
    assert periods[0]["start"] == start.isoformat()
    assert periods[0]["days"] == 10
    assert periods[0]["text"] == "Nachtverlaging -2,0 °C, 22:00–06:30"
    assert periods[-1]["current"] is True
    assert periods[-1]["text"] == "Nachtverlaging uit"
    assert periods[-1]["settings"]["night_offset"] == -1.5

    # Export contains every stored day and today's events.
    await client.send_json_auto_id({"type": "ha_climate/export"})
    msg = await client.receive_json()
    assert msg["success"]
    days = msg["result"]["days"]
    assert len(days) == 31  # 30 stored days + today
    assert days[-1]["partial"] is True
    assert {e["text"] for e in days[-1]["events"]} >= {
        "Nachtverlaging aangepast: -1,5 °C, 21:30–06:30"
    }
    assert set(days[0]) >= {
        "indoor_temperature", "indoor_target", "fireplace_minutes", "cost_fixed", "events"
    }

    # Ranking is part of the state.
    await client.send_json_auto_id({"type": "ha_climate/state"})
    state = (await client.receive_json())["result"]
    assert state["ranking"][0]["name"] == "Woonkamer"
    assert state["ranking"][0]["label"] == "Onvoldoende data"


@pytest.mark.usefixtures("recorder_mock")
async def test_fixed_cost_unit_migration(hass, ha_climate_enabled) -> None:
    """Existing fixed costs were per day and keep that unit."""
    _states(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=2,
        data={"outdoor_sensor": "sensor.outside", "gas_sensor": "sensor.gas"},
        options={"rooms": [], "gas_fixed_costs": 0.6},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.minor_version == 3
    assert entry.options["gas_fixed_costs_unit"] == "day"
    assert entry.runtime_data.data.fixed_costs == pytest.approx(0.6)


@pytest.mark.usefixtures("recorder_mock")
async def test_comfort_blocks(hass, ha_climate_enabled, hass_ws_client) -> None:
    """Comfort blocks lower the room outside the blocks and plan optimum start per block."""
    _states(hass)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "ha_climate/room/save",
            "room": {
                "id": "r1", "day_temp": 21.0, "night_temp": 17.0, "optimum_start": True,
                "periods": [{"start": "06:30", "end": "07:30"}, {"start": "17:00", "end": "21:00"}],
            },
        }
    )
    msg = await client.receive_json()
    assert msg["success"], msg
    coordinator = entry.runtime_data
    room = coordinator.room("r1")
    assert len(coordinator.schedule(room).periods) == 2
    temp_calls = async_mock_service(hass, "climate", "set_temperature")

    # Mid-day: between the blocks, so lowered to the night temperature.
    noon = dt_util.now().replace(hour=12, minute=0, second=0, microsecond=0)
    await coordinator._async_evaluate_setback(noon)
    assert coordinator.room_setback_active("r1")
    assert {c.data["temperature"] for c in temp_calls} == {17.0}
    start = dt_util.parse_datetime(coordinator.plans["r1"]["heating_start"])
    comfort = dt_util.parse_datetime(coordinator.plans["r1"]["comfort_at"])
    assert comfort.hour == 17 and start < comfort

    # Inside the evening block the room is back on its day temperature.
    for entity_id in ("climate.loop1", "climate.loop2"):
        hass.states.async_set(
            entity_id, "heat",
            {"temperature": 17.0, "current_temperature": 19.5, "hvac_action": "idle",
             "min_temp": 5, "max_temp": 28},
        )
    temp_calls.clear()
    await coordinator._async_evaluate_setback(noon.replace(hour=18))
    assert not coordinator.room_setback_active("r1")
    assert {c.data["temperature"] for c in temp_calls} == {21.0}

    # Invalid block is refused.
    await client.send_json_auto_id(
        {"type": "ha_climate/room/save",
         "room": {"id": "r1", "periods": [{"start": "08:00", "end": "08:00"}]}}
    )
    msg = await client.receive_json()
    assert not msg["success"]
