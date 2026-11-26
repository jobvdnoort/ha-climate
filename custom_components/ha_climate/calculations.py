"""Pure calculation logic for HA Climate.

This module intentionally has no Home Assistant imports so it can be unit
tested in isolation.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

HEATING_ACTIONS = frozenset({"heating", "preheating"})


# ---------------------------------------------------------------------------
# Degree days
# ---------------------------------------------------------------------------
def degree_days(mean_temperature: float | None, heating_limit: float = 18.0) -> float | None:
    """Return the degree days for a (full) day: max(0, limit - mean temperature)."""
    if mean_temperature is None:
        return None
    return max(0.0, heating_limit - mean_temperature)


def accumulated_degree_days(
    mean_temperature_so_far: float | None,
    heating_limit: float,
    elapsed_fraction: float,
) -> float | None:
    """Return the degree days accumulated so far today.

    The degree days for the full day are scaled by the fraction of the day that
    has passed, so the value can be compared with the gas used so far.
    """
    full_day = degree_days(mean_temperature_so_far, heating_limit)
    if full_day is None:
        return None
    fraction = min(1.0, max(0.0, elapsed_fraction))
    return full_day * fraction


def day_fraction(now: datetime) -> float:
    """Return the fraction of the (local) day that has elapsed."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return min(1.0, max(0.0, (now - midnight).total_seconds() / 86400))


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DayRecord:
    """Historic values for a single day."""

    day: date
    mean_temperature: float | None
    gas: float | None


@dataclass(slots=True)
class BaselineResult:
    """Outcome of a baseline calculation."""

    m3_per_degree_day: float | None
    days_used: int = 0
    total_gas: float = 0.0
    total_degree_days: float = 0.0
    excluded_fireplace: int = 0
    excluded_setback: int = 0
    excluded_invalid: int = 0
    excluded_warm: int = 0
    first_day: date | None = None
    last_day: date | None = None
    reliable: bool = False

    @property
    def is_valid(self) -> bool:
        """Return whether a baseline value could be calculated."""
        return self.m3_per_degree_day is not None


def calculate_baseline(
    records: Iterable[DayRecord],
    heating_limit: float = 18.0,
    fireplace_days: Iterable[date] = (),
    setback_days: Iterable[date] = (),
    min_degree_days: float = 1.0,
    min_days: int = 7,
) -> BaselineResult:
    """Calculate the average gas usage in m³ per degree day.

    The baseline is the ratio of the summed gas usage and the summed degree days
    of all usable days (a ratio of sums is far more robust than an average of
    daily ratios). Days are skipped when:

    * temperature or gas data is missing or the gas value is negative,
    * the fireplace was active (the room was heated with wood instead of gas),
    * the night setback was active (the baseline must reflect "no savings"),
    * there were fewer than ``min_degree_days`` degree days (non-heating days).

    The result is marked ``reliable`` when at least ``min_days`` days were used.
    """
    fireplace = set(fireplace_days)
    setback = set(setback_days)
    result = BaselineResult(m3_per_degree_day=None)

    for record in sorted(records, key=lambda r: r.day):
        if record.mean_temperature is None or record.gas is None or record.gas < 0:
            result.excluded_invalid += 1
            continue
        if record.day in fireplace:
            result.excluded_fireplace += 1
            continue
        if record.day in setback:
            result.excluded_setback += 1
            continue
        dd = degree_days(record.mean_temperature, heating_limit)
        assert dd is not None
        if dd < min_degree_days:
            result.excluded_warm += 1
            continue
        result.days_used += 1
        result.total_gas += record.gas
        result.total_degree_days += dd
        result.first_day = result.first_day or record.day
        result.last_day = record.day

    # A value is calculated as soon as there is one usable day so the sensors
    # never stay "unknown"; it is flagged reliable from ``min_days`` days on.
    if result.days_used >= 1 and result.total_degree_days > 0:
        result.m3_per_degree_day = result.total_gas / result.total_degree_days
        result.reliable = result.days_used >= max(1, min_days)
    return result


def expected_gas(baseline: float | None, degree_day_value: float | None) -> float | None:
    """Return the expected gas usage: baseline × degree days."""
    if baseline is None or degree_day_value is None:
        return None
    return baseline * degree_day_value


def gas_savings(expected: float | None, actual: float | None) -> float | None:
    """Return saved gas (expected - actual). Negative means more gas was used."""
    if expected is None or actual is None:
        return None
    return expected - actual


def money(volume: float | None, price: float | None) -> float | None:
    """Return the monetary value of a gas volume."""
    if volume is None or price is None:
        return None
    return volume * price


# ---------------------------------------------------------------------------
# Night setback
# ---------------------------------------------------------------------------
def parse_time(value: str | time) -> time:
    """Parse ``HH:MM`` or ``HH:MM:SS`` into a time object."""
    if isinstance(value, time):
        return value
    parts = [int(p) for p in str(value).split(":")]
    while len(parts) < 3:
        parts.append(0)
    return time(parts[0], parts[1], parts[2])


def in_time_window(now: time, start: time, end: time) -> bool:
    """Return whether ``now`` lies in [start, end), supporting windows past midnight."""
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


def setback_target(
    original: float,
    offset: float,
    min_temp: float | None = None,
    step: float | None = None,
) -> float:
    """Return the lowered target temperature, rounded to the thermostat step."""
    target = original + offset
    step = step if step and step > 0 else 0.1
    target = round(round(target / step) * step, 2)
    if min_temp is not None:
        target = max(target, min_temp)
    return target


def restore_value(
    current_target: float | None,
    applied_target: float,
    original: float,
    tolerance: float = 0.05,
) -> float | None:
    """Return the temperature to restore in the morning, or None to leave it alone.

    If someone changed the thermostat manually during the night, the manual
    setting wins and nothing is restored.
    """
    if current_target is None:
        return original
    if abs(current_target - applied_target) <= tolerance:
        return original
    return None


# ---------------------------------------------------------------------------
# Fireplace detection
# ---------------------------------------------------------------------------
@dataclass
class FireplaceDetector:
    """Detect a burning fireplace from room temperature and heating activity.

    The fireplace is considered active when the floor heating is *not* heating
    and either

    * the room temperature is at least ``threshold`` above the (comfort) target, or
    * the room temperature rose at least ``threshold`` within ``rise_window``
      while the floor heating did not heat during ``heating_cooldown``.

    A hysteresis of half the threshold prevents flapping.
    """

    threshold: float = 0.5
    rise_window: timedelta = timedelta(minutes=60)
    heating_cooldown: timedelta = timedelta(minutes=60)
    active: bool = False
    last_heating: datetime | None = None
    delta_to_target: float | None = None
    rise: float | None = None
    _samples: deque[tuple[datetime, float]] = field(default_factory=deque, repr=False)

    def update(
        self,
        now: datetime,
        current_temperature: float | None,
        target_temperature: float | None,
        hvac_action: str | None,
    ) -> bool:
        """Feed a new measurement and return whether the fireplace is active."""
        heating = hvac_action in HEATING_ACTIONS
        if heating:
            self.last_heating = now

        if current_temperature is None:
            self.delta_to_target = None
            self.rise = None
            self.active = False
            return self.active

        self._samples.append((now, current_temperature))
        while self._samples and now - self._samples[0][0] > self.rise_window:
            self._samples.popleft()

        self.delta_to_target = (
            current_temperature - target_temperature
            if target_temperature is not None
            else None
        )
        self.rise = current_temperature - min(t for _, t in self._samples)

        if heating:
            self.active = False
            return self.active

        cooled_down = (
            self.last_heating is None or now - self.last_heating >= self.heating_cooldown
        )
        rising = cooled_down and self.rise >= self.threshold
        above = self.delta_to_target is not None and self.delta_to_target >= self.threshold

        if self.active:
            release = self.threshold / 2
            still_warm = self.delta_to_target is not None and self.delta_to_target > release
            self.active = still_warm or rising
        else:
            self.active = above or rising
        return self.active

    def reset(self) -> None:
        """Forget all samples."""
        self._samples.clear()
        self.active = False
        self.delta_to_target = None
        self.rise = None


def fireplace_excluded_days(minutes_per_day: dict[str, int], min_minutes: int) -> set[date]:
    """Return the days on which the fireplace burned at least ``min_minutes``."""
    return {
        date.fromisoformat(day)
        for day, minutes in minutes_per_day.items()
        if minutes >= min_minutes
    }
