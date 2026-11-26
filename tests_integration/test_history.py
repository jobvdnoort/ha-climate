"""Tests for the LTS overlap baseline, permanent storage, thermal backfill and costs."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.util import dt as dt_util

DOMAIN = "ha_climate"


def _import(hass, temp_days: int, gas_days: int) -> None:
    """Temperature history of ``temp_days`` and gas history of ``gas_days`` days."""
    today = dt_util.start_of_local_day()
    temps, gas, total = [], [], 0.0
    for hour in range(temp_days * 24):
        moment = today - timedelta(days=temp_days) + timedelta(hours=hour)
        mean = 8.0
        temps.append(StatisticData(start=moment, mean=mean, min=mean, max=mean))
    for hour in range(gas_days * 24):
        moment = today - timedelta(days=gas_days) + timedelta(hours=hour)
        total += 0.4 * 10 / 24  # 10 degree days per day -> 4 m³
        gas.append(StatisticData(start=moment, state=1000 + total, sum=total))
    async_import_statistics(
        hass,
        StatisticMetaData(
            source="recorder", statistic_id="sensor.outside", unit_of_measurement="°C",
            unit_class="temperature", has_sum=False, mean_type=StatisticMeanType.ARITHMETIC,
            name=None,
        ),
        temps,
    )
    async_import_statistics(
        hass,
        StatisticMetaData(
            source="recorder", statistic_id="sensor.gas", unit_of_measurement="m³",
            unit_class="volume", has_sum=True, mean_type=StatisticMeanType.NONE, name=None,
        ),
        gas,
    )


def _sensors(hass) -> None:
    hass.states.async_set(
        "sensor.outside", "5.0",
        {"device_class": "temperature", "unit_of_measurement": "°C", "state_class": "measurement"},
    )
    hass.states.async_set(
        "sensor.gas", "1000.0",
        {"device_class": "gas", "unit_of_measurement": "m³", "state_class": "total_increasing"},
    )


def _entry(hass, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=2,
        data={"outdoor_sensor": "sensor.outside", "gas_sensor": "sensor.gas", "heating_limit": 18.0},
        options={"rooms": [], **options},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.usefixtures("recorder_mock")
async def test_baseline_from_overlap_and_permanent_days(hass, ha_climate_enabled) -> None:
    """The baseline starts at the first day both sensors have data; days are stored."""
    _sensors(hass)
    _import(hass, temp_days=40, gas_days=25)
    await async_wait_recording_done(hass)
    entry = _entry(hass, gas_price=1.5, gas_fixed_costs=0.4)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data

    result = await coordinator.async_recalculate()
    today = dt_util.now().date()
    info = coordinator.baseline_info()
    assert info["overlap_start"] == (today - timedelta(days=25)).isoformat()
    assert result.days_used == 25
    assert result.first_day == today - timedelta(days=25)
    assert result.m3_per_degree_day == pytest.approx(0.4, abs=1e-6)
    # Days from the overlap on are stored permanently.
    assert len(coordinator._history["days"]) == 25  # noqa: SLF001

    # Recalculating again does not duplicate anything.
    await coordinator.async_recalculate()
    assert len(coordinator._history["days"]) == 25  # noqa: SLF001

    # Costs: variable + fixed.
    data = coordinator.data
    assert data.fixed_costs == pytest.approx(0.4)
    assert data.cost_yesterday == pytest.approx(4.0 * 1.5 + 0.4, abs=1e-6)
    rows = await coordinator.async_history(14)
    assert rows[0]["cost"] == pytest.approx(4.0 * 1.5 + 0.4, abs=1e-6)
    assert rows[0]["cost_variable"] == pytest.approx(6.0, abs=1e-6)
    assert rows[0]["saved_eur"] == pytest.approx(0.0, abs=1e-6)  # savings without fixed costs
    assert hass.states.get("sensor.ha_climate_gas_costs_yesterday") is not None

    # The days survive a reload (permanent store), even without recorder access.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(entry.runtime_data._history["days"]) == 25  # noqa: SLF001


@pytest.mark.usefixtures("recorder_mock")
async def test_thermal_backfill_from_recorder_history(hass, ha_climate_enabled, freezer) -> None:
    """A new room learns from existing climate history and does not start at 0 points."""
    async_mock_service(hass, "climate", "set_temperature")
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=10)
    start -= timedelta(hours=start.hour % 2)  # align with the 2 h grid
    freezer.move_to(start)
    _sensors(hass)
    temp = 19.0
    for minute in range(0, 9 * 60, 5):
        freezer.move_to(start + timedelta(minutes=minute))
        heating = (minute // 120) % 2 == 0
        temp += (1.2 * heating - 0.04 * (temp - 5.0)) * 5 / 60
        hass.states.async_set(
            "climate.living", "heat",
            {"temperature": 20.0, "current_temperature": round(temp, 2),
             "hvac_action": "heating" if heating else "idle"},
        )
        hass.states.async_set("sensor.outside", "5.0", {"unit_of_measurement": "°C"})
        await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    freezer.move_to(start + timedelta(hours=9, minutes=1))
    async_fire_time_changed(hass)
    await async_wait_recording_done(hass)

    entry = _entry(
        hass,
        rooms=[{"id": "r1", "name": "Woonkamer", "climates": ["climate.living"], "use_global_night": True}],
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    await coordinator.async_backfill_thermal()

    model = coordinator.model("r1")
    status = coordinator.model_status("r1")
    assert status["data_points"] == 4  # four complete 2 h windows
    assert status["from_history"] == 4
    assert status["backfill"]["start"] is not None
    assert {o.start for o in model.observations} == {
        int((start + timedelta(hours=2 * i)).timestamp()) for i in range(4)
    }
    assert status["cooling_coefficient"] is not None

    # Running the backfill again adds nothing (deduplication on window start).
    await coordinator.async_backfill_thermal()
    assert coordinator.model_status("r1")["data_points"] == 4
    assert coordinator.model("r1").backfill["new"] == 0


@pytest.mark.usefixtures("recorder_mock")
async def test_migration_baseline_days(hass, ha_climate_enabled) -> None:
    """The old default of 365 days becomes 0 (= all history since the overlap)."""
    _sensors(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        data={"outdoor_sensor": "sensor.outside", "gas_sensor": "sensor.gas", "baseline_days": 365},
        options={"rooms": []},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.minor_version == 2
    assert entry.data["baseline_days"] == 0
