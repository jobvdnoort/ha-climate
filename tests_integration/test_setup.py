"""End-to-end test: config flow, options, night setback, fireplace and baseline."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from homeassistant import config_entries
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

DOMAIN = "ha_climate"


def _import_history(hass, days: int = 20) -> None:
    """Import hourly statistics: alternating 8/10 °C, gas = 0.4 m³ per degree day."""
    start = dt_util.start_of_local_day() - timedelta(days=days)
    temps, gas, total = [], [], 0.0
    for hour in range(days * 24):
        moment = start + timedelta(hours=hour)
        mean = 8.0 if (hour // 24) % 2 else 10.0
        temps.append(StatisticData(start=moment, mean=mean, min=mean, max=mean))
        total += 0.4 * (18 - mean) / 24
        gas.append(StatisticData(start=moment, state=1000 + total, sum=total))
    async_import_statistics(
        hass,
        StatisticMetaData(
            source="recorder",
            statistic_id="sensor.outside",
            unit_of_measurement="°C",
            unit_class="temperature",
            has_sum=False,
            mean_type=StatisticMeanType.ARITHMETIC,
            name=None,
        ),
        temps,
    )
    async_import_statistics(
        hass,
        StatisticMetaData(
            source="recorder",
            statistic_id="sensor.gas",
            unit_of_measurement="m³",
            unit_class="volume",
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
            name=None,
        ),
        gas,
    )


async def _options(hass, entry, step, data):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()


@pytest.mark.usefixtures("recorder_mock")
async def test_full_setup(hass, ha_climate_enabled) -> None:
    """Run through the whole integration."""
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
        {"temperature": 21.0, "current_temperature": 21.0, "hvac_action": "idle", "target_temp_step": 0.5},
    )
    hass.states.async_set(
        "climate.kitchen",
        "heat",
        {"temperature": 20.5, "current_temperature": 20.0, "hvac_action": "heating"},
    )
    calls = async_mock_service(hass, "climate", "set_temperature")
    _import_history(hass)
    await async_wait_recording_done(hass)

    # --- Config flow ---------------------------------------------------
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "outdoor_sensor": "sensor.outside",
            "gas_sensor": "sensor.gas",
            "gas_price": 1.25,
            "heating_limit": 18.0,
            "baseline_days": 365,
        },
    )
    assert result["step_id"] == "night"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"night_start": "22:00:00", "night_end": "06:30:00", "night_offset": -2.0},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    await hass.async_block_till_done()

    # --- Options flow ----------------------------------------------------
    await _options(
        hass,
        entry,
        "add_room",
        {
            "name": "Woonkamer",
            "climates": ["climate.living", "climate.kitchen"],
            "use_global_night": True,
            "night_start": "22:00:00",
            "night_end": "06:30:00",
            "night_offset": -2.0,
        },
    )
    await _options(
        hass, entry, "fireplace", {"fireplace_climate": "climate.living", "fireplace_threshold": 0.5}
    )
    room_id = entry.options["rooms"][0]["id"]
    assert hass.states.get("switch.ha_climate_night_setback").state == "on"
    assert hass.states.get("switch.ha_climate_night_setback_woonkamer").state == "on"

    coordinator = entry.runtime_data

    # --- Baseline from long-term statistics ------------------------------
    baseline = await coordinator.async_recalculate_baseline()
    assert baseline.m3_per_degree_day == pytest.approx(0.4, abs=1e-6)
    await coordinator.async_refresh()
    assert coordinator.data.degree_days_yesterday == pytest.approx(10.0)
    assert coordinator.data.expected_yesterday == pytest.approx(4.0, abs=1e-6)
    assert coordinator.to_euro(4.0) == pytest.approx(5.0)

    # --- Night setback ----------------------------------------------------
    night = dt_util.now().replace(hour=22, minute=5, second=0, microsecond=0)
    await coordinator._async_tick(night)  # noqa: SLF001
    await hass.async_block_till_done()
    assert {c.data["entity_id"]: c.data["temperature"] for c in calls} == {
        "climate.living": 19.0,
        "climate.kitchen": 18.5,
    }
    assert coordinator.room_setback_active(room_id)

    # The thermostats follow; the kitchen is changed manually during the night.
    hass.states.async_set(
        "climate.living", "heat", {"temperature": 19.0, "current_temperature": 21.0, "hvac_action": "idle"}
    )
    hass.states.async_set(
        "climate.kitchen", "heat", {"temperature": 20.0, "current_temperature": 20.0, "hvac_action": "idle"}
    )
    await hass.async_block_till_done()
    # Fireplace compares against the comfort target (21.0), not the lowered one.
    assert hass.states.get("binary_sensor.ha_climate_fireplace_active").state == "off"

    hass.states.async_set(
        "climate.living", "heat", {"temperature": 19.0, "current_temperature": 21.7, "hvac_action": "idle"}
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ha_climate_fireplace_active").state == "on"

    # --- Morning restore ---------------------------------------------------
    calls.clear()
    morning = night.replace(hour=6, minute=31) + timedelta(days=1)
    await coordinator._async_tick(morning)  # noqa: SLF001
    await hass.async_block_till_done()
    # Only the loop that was not changed manually is restored.
    assert {c.data["entity_id"]: c.data["temperature"] for c in calls} == {"climate.living": 21.0}
    assert not coordinator.room_setback_active(room_id)

    # --- Service ------------------------------------------------------------
    response = await hass.services.async_call(
        DOMAIN, "recalculate_baseline", {}, blocking=True, return_response=True
    )
    assert response[entry.entry_id]["m3_per_degree_day"] == pytest.approx(0.4, abs=1e-6)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
