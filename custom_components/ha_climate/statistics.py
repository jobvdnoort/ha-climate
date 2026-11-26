"""Access to the Home Assistant recorder (Long-Term Statistics)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    statistic_during_period,
    statistics_during_period,
)
from homeassistant.const import UnitOfTemperature, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .calculations import DayRecord

_LOGGER = logging.getLogger(__name__)

UNITS = {
    "temperature": UnitOfTemperature.CELSIUS,
    "volume": UnitOfVolume.CUBIC_METERS,
}


def _row_start(value: Any) -> datetime:
    """Return the start of a statistics row as a local datetime."""
    if isinstance(value, datetime):
        return dt_util.as_local(value)
    return dt_util.as_local(dt_util.utc_from_timestamp(float(value)))


async def async_period_value(
    hass: HomeAssistant,
    statistic_id: str,
    start: datetime,
    end: datetime | None,
    stat_type: str,
) -> float | None:
    """Return a single aggregated value ("mean" or "change") for a period."""
    try:
        result = await get_instance(hass).async_add_executor_job(
            statistic_during_period, hass, start, end, statistic_id, {stat_type}, UNITS
        )
    except Exception:  # noqa: BLE001 - recorder errors must never break the integration
        _LOGGER.debug("Could not read statistics for %s", statistic_id, exc_info=True)
        return None
    value = result.get(stat_type)
    if value is None:
        return None
    value = float(value)
    if stat_type == "change" and value < 0:
        # A meter cannot run backwards: meter swap/reset or inconsistent statistics.
        _LOGGER.debug("Ignoring negative change %.3f for %s", value, statistic_id)
        return None
    return value


async def async_daily_history(
    hass: HomeAssistant,
    temperature_id: str,
    gas_id: str,
    days: int,
) -> list[DayRecord]:
    """Return daily mean temperature and gas usage for the last ``days`` full days."""
    today = dt_util.start_of_local_day()
    start = today - timedelta(days=days)
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        today,
        {temperature_id, gas_id},
        "day",
        UNITS,
        {"mean", "change"},
    )

    temps: dict[date, float | None] = {}
    for row in stats.get(temperature_id, []):
        temps[_row_start(row["start"]).date()] = row.get("mean")

    gas: dict[date, float | None] = {}
    for row in stats.get(gas_id, []):
        change = row.get("change")
        # Negative usage is impossible (meter reset/replacement): treat as missing.
        gas[_row_start(row["start"]).date()] = (
            change if change is None or change >= 0 else None
        )

    return [
        DayRecord(day=day, mean_temperature=temps.get(day), gas=gas.get(day))
        for day in sorted(set(temps) | set(gas))
    ]
