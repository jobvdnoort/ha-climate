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
    observations = await hass.async_add_executor_job(
        observations_from_history, loops, outdoor, first, end, invalid
    )
    summary["windows"] = len(observations)
    return observations, summary
