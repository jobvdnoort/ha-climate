"""Degree day correction for the comfort temperature (without night setback)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.util import dt as dt_util

from .test_boiler import _setup, _states


@pytest.mark.usefixtures("recorder_mock")
async def test_comfort_correction_ignores_night_setback(hass, ha_climate_enabled, hass_ws_client) -> None:
    """The comfort temperature, not the lowered target, shifts the heating limit."""
    _states(hass)  # loop target 21 °C
    async_mock_service(hass, "climate", "set_temperature")
    entry = await _setup(
        hass, {"degree_day_indoor_correction": True, "degree_day_reference_temp": 20.0}
    )
    coordinator = entry.runtime_data
    # A past day, so the real minute tick does not log into it.
    now = (dt_util.now() - timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)
    for minute in range(10):
        coordinator._learn(now + timedelta(minutes=minute))  # noqa: SLF001
    # Night setback active: the loop is lowered to 19 °C, the comfort stays 21 °C.
    coordinator._stored["room_state"]["r1"] = {  # noqa: SLF001
        "active": True,
        "entities": {"climate.loop1": {"original": 21.0, "applied": 19.0}},
    }
    hass.states.async_set(
        "climate.loop1", "heat", {"temperature": 19.0, "current_temperature": 20.0, "hvac_action": "idle"}
    )
    for minute in range(10, 20):
        coordinator._learn(now + timedelta(minutes=minute))  # noqa: SLF001

    today = now.date()
    assert coordinator.indoor_day(today)[1] == pytest.approx(20.0)  # mean target incl. setback
    assert coordinator.comfort_day(today) == pytest.approx(21.0)
    assert coordinator.heating_limit_for(today) == pytest.approx(19.0)
    # Days without a logged comfort temperature count as the reference.
    assert coordinator.heating_limit_for(today - timedelta(days=30)) == pytest.approx(18.0)

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "ha_climate/state"})
    result = (await client.receive_json())["result"]
    assert result["settings"]["degree_day_reference_temp"] == 20.0
    assert result["baseline"]["reference_temperature"] == 20.0

    await client.send_json_auto_id(
        {"type": "ha_climate/settings/save", "settings": {"degree_day_reference_temp": 21.0}}
    )
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    assert entry.runtime_data.heating_limit_for(today) == pytest.approx(18.0)


@pytest.mark.usefixtures("recorder_mock")
async def test_correction_off_uses_fixed_limit(hass, ha_climate_enabled) -> None:
    """Without the correction the heating limit is fixed."""
    _states(hass)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    now = dt_util.now()
    coordinator._learn(now)  # noqa: SLF001
    assert coordinator.heating_limit_for(now.date()) == 18.0
