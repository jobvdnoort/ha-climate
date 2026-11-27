"""Pure calculation logic for HA Climate.

This module intentionally has no Home Assistant imports so it can be unit
tested in isolation.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
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
    limits: dict[date, float] | None = None,
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
    ``limits`` optionally overrides the heating limit per day (indoor correction).
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
        limit = (limits or {}).get(record.day, heating_limit)
        dd = degree_days(record.mean_temperature, limit)
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


def parse_periods(value: object) -> tuple[tuple[time, time], ...]:
    """Parse configured comfort periods into sorted (start, end) tuples.

    Accepts ``[{"start": "06:30", "end": "07:30"}, ...]``; invalid or empty
    periods (start == end) are skipped.
    """
    result: list[tuple[time, time]] = []
    if not isinstance(value, (list, tuple)):
        return ()
    for item in value:
        try:
            start = parse_time(item["start"])
            end = parse_time(item["end"])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if start != end:
            result.append((start, end))
    return tuple(sorted(result))


def describe_periods(
    periods: Iterable[tuple[time, time]],
    offset: float | None = None,
    night_temp: float | None = None,
) -> str:
    """Return e.g. ``comfort 06:30–07:30, 17:00–21:00, daarbuiten 16,0 °C``."""
    amount = (
        f"{format_number(night_temp)} °C"
        if night_temp is not None
        else f"{format_number(offset if offset is not None else 0.0)} °C"
    )
    blocks = ", ".join(f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')}" for s, e in periods)
    return f"comfort {blocks}, daarbuiten {amount}"


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

    When the target is lowered (by hand or by a schedule) the room is above
    its new target for hours while it cools down. That is not a fireplace, so
    after a lower target only a real temperature *rise* counts, until the room
    has cooled down to the new target.
    """

    threshold: float = 0.5
    rise_window: timedelta = timedelta(minutes=60)
    heating_cooldown: timedelta = timedelta(minutes=60)
    active: bool = False
    last_heating: datetime | None = None
    delta_to_target: float | None = None
    rise: float | None = None
    target: float | None = None
    settling: bool = False  # target was lowered, room still cooling down
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
        if target_temperature is not None:
            if self.target is not None and target_temperature < self.target - 0.05:
                self.settling = True
            self.target = target_temperature
        if self.settling and (
            self.delta_to_target is None or self.delta_to_target <= self.threshold / 2
        ):
            self.settling = False

        if heating:
            self.active = False
            return self.active

        cooled_down = (
            self.last_heating is None or now - self.last_heating >= self.heating_cooldown
        )
        rising = cooled_down and self.rise >= self.threshold
        above = (
            not self.settling
            and self.delta_to_target is not None
            and self.delta_to_target >= self.threshold
        )

        if self.active:
            release = self.threshold / 2
            still_warm = (
                not self.settling
                and self.delta_to_target is not None
                and self.delta_to_target > release
            )
            self.active = still_warm or rising
        else:
            self.active = above or rising
        return self.active

    def reset(self) -> None:
        """Forget all samples."""
        self._samples.clear()
        self.active = False
        self.settling = False
        self.target = None
        self.delta_to_target = None
        self.rise = None


def fireplace_excluded_days(minutes_per_day: dict[str, int], min_minutes: int) -> set[date]:
    """Return the days on which the fireplace burned at least ``min_minutes``."""
    return {
        date.fromisoformat(day)
        for day, minutes in minutes_per_day.items()
        if minutes >= min_minutes
    }


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------
DAYS_PER_MONTH = 30.4375  # 365.25 / 12


def daily_fixed_costs(amount: float | None, unit: str = "month") -> float:
    """Convert fixed delivery costs to € per day (``unit`` is "month" or "day")."""
    if not amount:
        return 0.0
    return amount / DAYS_PER_MONTH if unit == "month" else amount


# ---------------------------------------------------------------------------
# Indoor temperature correction
# ---------------------------------------------------------------------------
REFERENCE_INDOOR_TEMPERATURE = 20.0


def corrected_heating_limit(
    heating_limit: float,
    mean_target: float | None,
    reference: float = REFERENCE_INDOOR_TEMPERATURE,
) -> float:
    """Shift the heating limit by the deviation of the indoor target from a reference.

    The usual 18 °C heating limit assumes ~20 °C inside (internal gains cover
    the last 2 °C). A house kept at 21 °C starts heating at ~19 °C outside, a
    house kept at 19 °C at ~17 °C. ``reference`` is the comfort temperature of
    the baseline period; days without a known target count as that reference.
    """
    if mean_target is None:
        return heating_limit
    return heating_limit + (mean_target - reference)


# ---------------------------------------------------------------------------
# Room ranking
# ---------------------------------------------------------------------------
HIGH_HEAT_LOSS = 0.06  # 1/h  (°C/h per °C ΔT)
MEDIUM_HEAT_LOSS = 0.035
HIGH_DUTY = 0.5
MEDIUM_DUTY = 0.25


@dataclass(slots=True)
class RoomRanking:
    """Energy ranking of one room."""

    room_id: str
    heat_loss: float | None  # normalized heat loss k, 1/h
    duty: float | None  # 0..1 share of time actively heating
    score: float | None  # 0..1, higher = less efficient
    label: str
    tags: list[str]
    rank: int = 0


def rank_rooms(rooms: list[tuple[str, float | None, float | None]]) -> list[RoomRanking]:
    """Rank rooms from least to most efficient.

    ``rooms`` holds (room_id, heat_loss, duty). The score averages both values,
    each relative to the highest value among the rooms, so the room that loses
    heat fastest *and* heats most often ends on top.
    """
    max_k = max((k for _, k, _ in rooms if k), default=0.0)
    max_duty = max((d for _, _, d in rooms if d), default=0.0)
    result: list[RoomRanking] = []
    for room_id, k, duty in rooms:
        parts = []
        if k is not None and max_k > 0:
            parts.append(k / max_k)
        if duty is not None and max_duty > 0:
            parts.append(duty / max_duty)
        score = sum(parts) / len(parts) if parts else None
        tags: list[str] = []
        if k is None and duty is None:
            label = "Onvoldoende data"
        elif k is not None and k >= HIGH_HEAT_LOSS:
            label = "Hoog warmteverlies"
        elif duty is not None and duty >= HIGH_DUTY:
            label = "Stookt veel"
        elif (k is not None and k >= MEDIUM_HEAT_LOSS) or (
            duty is not None and duty >= MEDIUM_DUTY
        ):
            label = "Gemiddeld"
        else:
            label = "Zuinig"
        if k is not None and k >= HIGH_HEAT_LOSS:
            tags.append("hoog warmteverlies")
        if duty is not None and duty >= HIGH_DUTY:
            tags.append("stookt veel")
        result.append(RoomRanking(room_id, k, duty, score, label, tags))
    result.sort(key=lambda r: (r.score is None, -(r.score or 0.0)))
    for position, ranking in enumerate(result, start=1):
        ranking.rank = position
    return result


# ---------------------------------------------------------------------------
# Event texts
# ---------------------------------------------------------------------------
def format_number(value: float, digits: int = 1) -> str:
    """Dutch number formatting (decimal comma)."""
    return f"{value:.{digits}f}".replace(".", ",")


def describe_night(
    start: str, end: str, offset: float | None = None, night_temp: float | None = None
) -> str:
    """Return e.g. ``-1,5 °C, 21:30–06:00`` or ``16,0 °C, 22:00–06:30``."""
    amount = (
        f"{format_number(night_temp)} °C"
        if night_temp is not None
        else f"{format_number(offset if offset is not None else 0.0)} °C"
    )
    return f"{amount}, {start[:5]}–{end[:5]}"


# ---------------------------------------------------------------------------
# Hourly comparison: what does a setback save, and what does the reheat cost?
# ---------------------------------------------------------------------------
RECOVERY_HOURS = 6


PROFILE_MIN_DAYS = 7
PROFILE_MIN_DEGREE_DAYS = 5.0


def hourly_profile(
    hours: list[tuple[datetime, float | None, float | None]],
    heating_limit: Callable[[date], float],
    exclude: set[date] | frozenset[date] = frozenset(),
    min_degree_days: float = PROFILE_MIN_DEGREE_DAYS,
    min_days: int = PROFILE_MIN_DAYS,
) -> tuple[list[float], int] | None:
    """Share of the daily gas per hour of the day (24 values summing to 1).

    Learned from cold enough, complete days (24 hours with gas and
    temperature) that are not in ``exclude``. A house does not use its gas
    evenly over the day: the morning warm-up, showers and cooking all fall in
    fixed hours. Comparing an hour with this profile instead of with a flat
    1/24 share keeps those habits from looking like reheat cost.
    Returns ``(profile, days used)`` or ``None`` with too few days.
    """
    by_day: dict[date, list[tuple[int, float, float]]] = {}
    for start, temperature, gas in hours:
        if temperature is None or gas is None:
            continue
        by_day.setdefault(start.date(), []).append((start.hour, temperature, gas))
    sums = [0.0] * 24
    total = 0.0
    used = 0
    for day, rows in by_day.items():
        if day in exclude or len(rows) != 24 or len({h for h, _, _ in rows}) != 24:
            continue
        mean = sum(t for _, t, _ in rows) / 24
        day_gas = sum(g for _, _, g in rows)
        if heating_limit(day) - mean < min_degree_days or day_gas <= 0:
            continue
        for hour, _, gas in rows:
            sums[hour] += gas
        total += day_gas
        used += 1
    if used < min_days or total <= 0:
        return None
    return [value / total for value in sums], used


def hourly_comparison(
    hours: list[tuple[datetime, float | None, float | None]],
    m3_per_degree_day: float,
    heating_limit: Callable[[date], float],
    lowered: Callable[[datetime], float],
    recovery_hours: int = RECOVERY_HOURS,
    profile: list[float] | None = None,
    day_temperature: Callable[[date], float | None] | None = None,
) -> dict:
    """Compare the gas per hour with the expected gas without measures.

    Without a ``profile`` the expected gas of an hour is
    ``baseline × max(0, limit − T_hour) / 24``: the baseline spread evenly over
    the day. With a ``profile`` (see :func:`hourly_profile`) it is the expected
    gas of the whole day, ``baseline × max(0, limit − T_day)``, times the share
    of that hour in the days before the measurement; ``T_day`` comes from
    ``day_temperature`` or else the mean of the given hours of that day. ``lowered``
    returns the share (0–1) of the house that is lowered in an hour. Hours are
    classified as *setback* (≥ half lowered), *recovery* (up to
    ``recovery_hours`` after a setback) or *other*. The sum of expected − actual
    per class shows whether lowering pays off: savings during the setback minus
    the extra gas to warm up again.
    """
    rows = []
    since_setback: int | None = None
    totals = {
        key: {"gas": 0.0, "expected": 0.0, "hours": 0}
        for key in ("setback", "recovery", "other")
    }
    cum_gas = cum_expected = 0.0
    day_means: dict[date, float | None] = {}
    if profile is not None:
        temps: dict[date, list[float]] = {}
        for start, temperature, _ in hours:
            if temperature is not None:
                temps.setdefault(start.date(), []).append(temperature)
        for day in {start.date() for start, _, _ in hours}:
            value = day_temperature(day) if day_temperature else None
            if value is None and temps.get(day):
                value = sum(temps[day]) / len(temps[day])
            day_means[day] = value
    for start, temperature, gas in hours:
        if profile is not None:
            mean = day_means.get(start.date())
            expected = (
                m3_per_degree_day
                * max(0.0, heating_limit(start.date()) - mean)
                * profile[start.hour]
                if mean is not None
                else None
            )
        else:
            expected = (
                m3_per_degree_day * max(0.0, heating_limit(start.date()) - temperature) / 24
                if temperature is not None
                else None
            )
        share = lowered(start)
        if share >= 0.5:
            kind = "setback"
            since_setback = 0
        elif since_setback is not None and since_setback < recovery_hours:
            kind = "recovery"
            since_setback += 1
        else:
            kind = "other"
            since_setback = None
        if gas is not None and expected is not None:
            cum_gas += gas
            cum_expected += expected
            totals[kind]["gas"] += gas
            totals[kind]["expected"] += expected
            totals[kind]["hours"] += 1
        rows.append(
            {
                "start": start.isoformat(),
                "temperature": temperature,
                "gas": gas,
                "expected": expected,
                "saved": expected - gas if gas is not None and expected is not None else None,
                "cumulative_saved": cum_expected - cum_gas,
                "lowered": round(share, 2),
                "kind": kind,
            }
        )
    summary = {
        key: {**value, "saved": value["expected"] - value["gas"]}
        for key, value in totals.items()
    }
    summary["net"] = cum_expected - cum_gas
    summary["setback_and_recovery"] = summary["setback"]["saved"] + summary["recovery"]["saved"]
    return {"hours": rows, "summary": summary}
