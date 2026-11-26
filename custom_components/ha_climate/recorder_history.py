"""Read recorder state history to backfill the thermal model."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import partial
import logging
from typing import Any

from homeassistant.components.climate import ATTR_CURRENT_TEMPERATURE, ATTR_HVAC_ACTION
from homeassistant.components.recorder import get_instance, history
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from .boiler import resample
from .const import AIRCO_ACTIVE_ACTIONS
from .thermal import Series, history_start, observations_from_history

_LOGGER = logging.getLogger(__name__)

DEFAULT_KEEP_DAYS = 10


def _float(value: Any) -> float | None:
    if value in (None, STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _climate_series(states: list[State]) -> tuple[Series, Series]:
    temps: Series = []
    actions: Series = []
    for state in states:
        ts = state.last_updated
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            temps.append((ts, None))
            actions.append((ts, None))
            continue
        temps.append((ts, _float(state.attributes.get(ATTR_CURRENT_TEMPERATURE))))
        actions.append((ts, state.attributes.get(ATTR_HVAC_ACTION)))
    return temps, actions


def _airco_active(state: State) -> bool:
    action = state.attributes.get(ATTR_HVAC_ACTION)
    if action in AIRCO_ACTIVE_ACTIONS:
        return True
    return action is None and state.state not in ("off", STATE_UNAVAILABLE, STATE_UNKNOWN)


def _airco_periods(states: list[State], end: datetime) -> list[tuple[datetime, datetime]]:
    """Periods in which an airco was heating or cooling."""
    periods = []
    since = None
    for state in states:
        active = _airco_active(state)
        if active and since is None:
            since = state.last_updated
        elif not active and since is not None:
            periods.append((since, state.last_updated))
            since = None
    if since is not None:
        periods.append((since, end))
    return periods


def _on_periods(states: list[State], end: datetime) -> list[tuple[datetime, datetime]]:
    periods = []
    since = None
    for state in states:
        if state.state == STATE_ON and since is None:
            since = state.last_updated
        elif state.state != STATE_ON and since is not None:
            periods.append((since, state.last_updated))
            since = None
    if since is not None:
        periods.append((since, end))
    return periods


async def async_backfill_observations(
    hass: HomeAssistant,
    climates: list[str],
    outdoor_sensor: str,
    fireplace_entity: str | None = None,
    aircos: list[str] | None = None,
    valves: list[str] | None = None,
) -> tuple[list, dict[str, Any]]:
    """Compute thermal observations from the recorder history of a room.

    Returns the observations and a summary (period that was analysed).
    """
    recorder = get_instance(hass)
    keep_days = getattr(recorder, "keep_days", DEFAULT_KEEP_DAYS) or DEFAULT_KEEP_DAYS
    end = dt_util.utcnow()
    start = end - timedelta(days=keep_days)
    entity_ids = [*climates, outdoor_sensor]
    if fireplace_entity:
        entity_ids.append(fireplace_entity)
    entity_ids.extend(aircos or [])
    entity_ids.extend(valves or [])

    states: dict[str, list[State]] = await recorder.async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start,
            end,
            entity_ids,
            include_start_time_state=True,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
    )

    loops = {
        entity_id: _climate_series(states.get(entity_id, [])) for entity_id in climates
    }
    outdoor: Series = [
        (s.last_updated, _float(s.state)) for s in states.get(outdoor_sensor, [])
    ]
    required = {f"{e}.temp": temps for e, (temps, _) in loops.items()}
    required["outdoor"] = outdoor
    first = history_start(required)
    summary: dict[str, Any] = {
        "analysed_at": dt_util.utcnow().isoformat(),
        "start": None,
        "end": end.isoformat(),
        "new": 0,
    }
    if first is None:
        _LOGGER.debug("No usable recorder history for %s", climates)
        return [], summary
    first = max(first, start)
    summary["start"] = first.isoformat()
    invalid = (
        _on_periods(states.get(fireplace_entity, []), end) if fireplace_entity else []
    )
    for airco in aircos or []:
        invalid.extend(_airco_periods(states.get(airco, []), end))
    valve_series: list[Series] = [
        [(s.last_updated, _float(s.state)) for s in states.get(valve, [])]
        for valve in valves or []
    ]
    observations = await hass.async_add_executor_job(
        observations_from_history, loops, outdoor, first, end, invalid, valve_series
    )
    summary["windows"] = len(observations)
    return observations, summary


async def async_boiler_trace(
    hass: HomeAssistant,
    numeric: dict[str, str],
    binary: dict[str, str],
    valves: list[str],
    hours: int,
    step: timedelta,
) -> list[dict[str, Any]]:
    """Resampled history of the boiler sensors (and the highest valve position).

    ``numeric`` and ``binary`` map a column name to an entity id.
    """
    end = dt_util.utcnow()
    start = end - timedelta(hours=hours)
    entity_ids = list({*numeric.values(), *binary.values(), *valves})
    if not entity_ids:
        return []
    recorder = get_instance(hass)
    states: dict[str, list[State]] = await recorder.async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start,
            end,
            entity_ids,
            include_start_time_state=True,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=True,
        )
    )

    def series(entity_id: str, convert) -> Series:
        return [(s.last_updated, convert(s.state)) for s in states.get(entity_id, [])]

    def on_off(value: str) -> float | None:
        if value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return 1.0 if value == STATE_ON else 0.0

    columns: dict[str, Any] = {
        key: series(entity_id, _float) for key, entity_id in numeric.items()
    }
    columns.update({key: series(entity_id, on_off) for key, entity_id in binary.items()})
    if valves:
        columns["valve_max"] = [series(valve, _float) for valve in valves]
    # Align the grid on whole steps so the chart labels are round times.
    seconds = int(step.total_seconds())
    first = dt_util.utc_from_timestamp((int(start.timestamp()) // seconds + 1) * seconds)
    return await hass.async_add_executor_job(resample, columns, first, end, step)


async def async_climate_samples(
    hass: HomeAssistant, entity_ids: list[str], days: int
) -> dict[str, list[tuple[datetime, float | None, float | None]]]:
    """(time, target, current temperature) of climate entities over the last days."""
    if not entity_ids:
        return {}
    end = dt_util.utcnow()
    start = end - timedelta(days=days)
    recorder = get_instance(hass)
    states: dict[str, list[State]] = await recorder.async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start,
            end,
            entity_ids,
            include_start_time_state=True,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
    )
    result = {}
    for entity_id in entity_ids:
        samples = []
        for state in states.get(entity_id, []):
            if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, "off"):
                samples.append((state.last_updated, None, None))
                continue
            samples.append(
                (
                    state.last_updated,
                    _float(state.attributes.get("temperature")),
                    _float(state.attributes.get(ATTR_CURRENT_TEMPERATURE)),
                )
            )
        result[entity_id] = samples
    return result
