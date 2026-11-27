"""Self-learning thermal model per room and optimum start calculation.

Pure Python (no Home Assistant imports) so it can be unit tested.

Model
-----
The room temperature is described by a first order model::

    dT/dt = h · duty − k · (T_in − T_out)

* ``k`` – cooling coefficient (1/h): how fast the room cools down per °C
  difference with outside. The cooling rate at a given moment is ``k · ΔT``.
* ``h`` – heating power (°C/h): temperature rise per hour at 100 % duty when
  inside and outside temperature would be equal.
* ``duty`` – fraction of time the floor heating was heating (0–1). Floor
  heating thermostats often modulate (PWM), so the duty cycle is used instead
  of requiring long uninterrupted heating periods. When valve position sensors
  (0–100 %) are configured, the mean valve opening is used as the heating
  intensity instead of the on/off ``hvac_action``.

The room is sampled every minute. Samples are grouped in windows on a fixed
2 h grid (00:00, 02:00, … UTC); every valid, gap-free window yields one
observation: the least-squares temperature slope (°C/h), the duty cycle and the
mean ΔT. Because the grid is fixed, an observation computed live and one
computed later from recorder history for the same period get the same key, so
re-calculating never creates duplicates. All observations are kept
permanently; ``h`` and ``k`` follow from a least squares fit over the most
recent season and the standard errors of the fit give a confidence score.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
import math

# --- Tuning ---------------------------------------------------------------
WINDOW = timedelta(hours=2)
WINDOW_SECONDS = int(WINDOW.total_seconds())
MAX_GAP = timedelta(minutes=10)
MIN_COVERAGE = 0.75  # a window needs samples covering ≥ 75 % of its length
SAMPLE_INTERVAL = timedelta(minutes=1)
MIN_SAMPLES = int(MIN_COVERAGE * WINDOW / SAMPLE_INTERVAL)
MAX_STORED_OBSERVATIONS = 20000  # ~4.5 years of 2 h windows, kept permanently
FIT_WINDOW_DAYS = 90  # the fit uses the most recent season ...
MIN_FIT_OBSERVATIONS = 300  # ... but never fewer than this many observations
FULL_CONFIDENCE_OBSERVATIONS = 60
MIN_CONFIDENCE_FOR_MODEL = 50.0  # %, below this the safe fallback is used
STAGE_LEARNING_OBSERVATIONS = 12  # stage 1 -> 2 (one day of data)
STAGE_LEARNING_CONFIDENCE = 20.0
FALLBACK_HEATING_RATE = 0.5  # °C/h, conservative default for floor heating
OPTIMUM_START_MARGIN = timedelta(minutes=15)
MAX_PREHEAT = timedelta(hours=6)

HEATING_ACTIONS = frozenset({"heating", "preheating"})

SOURCE_LIVE = "l"
SOURCE_HISTORY = "h"


def window_start(ts: datetime) -> int:
    """Return the start (epoch seconds) of the fixed 2 h grid slot of ``ts``."""
    epoch = int(ts.timestamp())
    return epoch - epoch % WINDOW_SECONDS


@dataclass(slots=True)
class Observation:
    """One 2 h window of measurements, identified by its start time."""

    slope: float  # °C/h
    duty: float  # 0..1
    delta_t: float  # mean T_in - T_out
    start: int = 0  # epoch seconds of the window start (0 = legacy, unknown)
    source: str = SOURCE_LIVE

    def as_list(self) -> list:
        """Serialize compactly."""
        return [
            self.start,
            round(self.slope, 4),
            round(self.duty, 3),
            round(self.delta_t, 2),
            self.source,
        ]

    @classmethod
    def from_list(cls, data: Iterable) -> Observation:
        """Deserialize (also the legacy ``[slope, duty, delta_t]`` format)."""
        values = list(data)
        if len(values) == 3:
            slope, duty, delta_t = values
            return cls(float(slope), float(duty), float(delta_t))
        start, slope, duty, delta_t, source = values
        return cls(float(slope), float(duty), float(delta_t), int(start), str(source))

    @property
    def day(self) -> date | None:
        """UTC date of the window (None for legacy observations)."""
        return datetime.fromtimestamp(self.start, UTC).date() if self.start else None


@dataclass(slots=True)
class ModelEstimate:
    """Result of fitting the model."""

    heating_power: float | None = None  # h, °C/h
    cooling_coefficient: float | None = None  # k, 1/h
    heating_confidence: float = 0.0  # %
    cooling_confidence: float = 0.0  # %
    observations: int = 0  # observations used for the fit

    @property
    def confidence(self) -> float:
        """Overall confidence: the weakest of both parameters."""
        return min(self.heating_confidence, self.cooling_confidence)

    @property
    def time_constant(self) -> float | None:
        """Thermal time constant τ = 1/k in hours (how slowly the room reacts)."""
        if not self.cooling_coefficient:
            return None
        return 1.0 / self.cooling_coefficient

    def cooling_rate(self, delta_t: float | None) -> float | None:
        """Cooling speed in °C/h at the given inside-outside difference."""
        if self.cooling_coefficient is None or delta_t is None:
            return None
        return self.cooling_coefficient * delta_t

    def heating_rate(self, delta_t: float | None) -> float | None:
        """Net heating speed in °C/h at full duty and the given ΔT."""
        if self.heating_power is None or self.cooling_coefficient is None or delta_t is None:
            return None
        return self.heating_power - self.cooling_coefficient * delta_t


def model_stage(estimate: ModelEstimate, observations: int) -> int:
    """Return 1 (collecting data), 2 (learning the room) or 3 (predictive control)."""
    if observations < STAGE_LEARNING_OBSERVATIONS or estimate.confidence < STAGE_LEARNING_CONFIDENCE:
        return 1
    if estimate.confidence < MIN_CONFIDENCE_FOR_MODEL:
        return 2
    return 3


def _slope_per_hour(samples: list[tuple[datetime, float]]) -> float:
    """Least squares slope of temperature over time in °C/h."""
    t0 = samples[0][0]
    xs = [(ts - t0).total_seconds() / 3600 for ts, _ in samples]
    ys = [t for _, t in samples]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return sxy / sxx


def _confidence(n: int, value: float, std_error: float) -> float:
    """Confidence (0-100) from the number of observations and relative spread."""
    if value <= 0 or not math.isfinite(std_error):
        return 0.0
    amount = min(1.0, n / FULL_CONFIDENCE_OBSERVATIONS)
    spread = 1.0 / (1.0 + 2.0 * std_error / value)
    return round(100.0 * amount * spread, 1)


def fit_model(observations: list[Observation]) -> ModelEstimate:
    """Fit ``slope = h·duty − k·ΔT`` with least squares (no intercept)."""
    n = len(observations)
    estimate = ModelEstimate(observations=n)
    if n < 3:
        return estimate
    # Normal equations for x1 = duty (coef h) and x2 = -ΔT (coef k).
    s11 = sum(o.duty * o.duty for o in observations)
    s22 = sum(o.delta_t * o.delta_t for o in observations)
    s12 = sum(-o.duty * o.delta_t for o in observations)
    b1 = sum(o.duty * o.slope for o in observations)
    b2 = sum(-o.delta_t * o.slope for o in observations)

    det = s11 * s22 - s12 * s12
    if s22 <= 0:
        return estimate
    if s11 <= 1e-6 or abs(det) < 1e-9 * max(1.0, s11 * s22):
        # Only idle data so far: estimate k alone.
        k = b2 / s22
        rss = sum((o.slope + k * o.delta_t) ** 2 for o in observations)
        sigma2 = rss / max(1, n - 1)
        se_k = math.sqrt(sigma2 / s22)
        estimate.cooling_coefficient = max(0.0, k)
        estimate.cooling_confidence = _confidence(n, k, se_k)
        return estimate

    h = (b1 * s22 - b2 * s12) / det
    k = (s11 * b2 - s12 * b1) / det
    rss = sum((o.slope - h * o.duty + k * o.delta_t) ** 2 for o in observations)
    sigma2 = rss / max(1, n - 2)
    se_h = math.sqrt(max(0.0, sigma2 * s22 / det))
    se_k = math.sqrt(max(0.0, sigma2 * s11 / det))

    estimate.cooling_coefficient = max(0.0, k)
    estimate.cooling_confidence = _confidence(n, k, se_k)
    heating_samples = sum(1 for o in observations if o.duty > 0.1)
    if heating_samples >= 3:
        estimate.heating_power = max(0.0, h)
        estimate.heating_confidence = _confidence(heating_samples, h, se_h)
    return estimate


def observation_from_samples(
    samples: list[tuple[datetime, float, float, float]], start: int, source: str
) -> Observation | None:
    """Turn the samples of one grid window into an observation (or None)."""
    if len(samples) < MIN_SAMPLES:
        return None
    if samples[-1][0] - samples[0][0] < WINDOW * MIN_COVERAGE - SAMPLE_INTERVAL:
        return None
    observation = Observation(
        slope=_slope_per_hour([(s[0], s[1]) for s in samples]),
        duty=sum(s[3] for s in samples) / len(samples),
        delta_t=sum(s[1] - s[2] for s in samples) / len(samples),
        start=start,
        source=source,
    )
    if abs(observation.slope) > 5:  # implausible (window opened, sensor glitch)
        return None
    return observation


def _intensity(heating: bool | float) -> float:
    """Heating as a fraction 0–1 (on/off or valve position)."""
    if isinstance(heating, bool):
        return 1.0 if heating else 0.0
    return max(0.0, min(1.0, float(heating)))


class WindowCollector:
    """Groups minute samples into fixed 2 h grid windows."""

    def __init__(self, source: str = SOURCE_LIVE) -> None:
        """Initialize."""
        self.source = source
        self._slot: int | None = None
        self._samples: list[tuple[datetime, float, float, float]] = []
        self._valid = True

    def reset(self) -> None:
        """Drop the current window."""
        self._slot = None
        self._samples = []
        self._valid = True

    def add(
        self,
        ts: datetime,
        inside: float | None,
        outside: float | None,
        heating: bool | float | None,
        valid: bool = True,
    ) -> Observation | None:
        """Add a sample; returns the observation of a window that just closed.

        ``heating`` is on/off (``hvac_action``) or a heating intensity 0–1
        (valve position).
        """
        slot = window_start(ts)
        finished = None
        if self._slot is not None and slot != self._slot:
            finished = self.flush()
        if self._slot is None:
            self._slot, self._samples, self._valid = slot, [], True
        sample_ok = valid and None not in (inside, outside, heating)
        if not sample_ok:
            # Fireplace, unknown hvac_action or missing sensor: discard this window.
            self._valid = False
        elif self._samples and ts - self._samples[-1][0] > MAX_GAP:
            self._valid = False
        elif self._valid:
            self._samples.append((ts, inside, outside, _intensity(heating)))
        return finished

    def flush(self) -> Observation | None:
        """Close the current window."""
        observation = None
        if self._slot is not None and self._valid:
            observation = observation_from_samples(self._samples, self._slot, self.source)
        self.reset()
        return observation


@dataclass
class RoomThermalModel:
    """All observations of one room (kept permanently) plus the live collector."""

    observations: list[Observation] = field(default_factory=list)
    backfill: dict = field(default_factory=dict)
    _collector: WindowCollector = field(default_factory=WindowCollector, repr=False)
    _estimate: ModelEstimate | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Keep observations sorted on start time."""
        self.observations.sort(key=lambda o: o.start)
        self._keys = {o.start for o in self.observations if o.start}

    @classmethod
    def from_dict(cls, data: dict | None) -> RoomThermalModel:
        """Restore from storage."""
        data = data or {}
        return cls(
            observations=[Observation.from_list(o) for o in data.get("observations", [])],
            backfill=dict(data.get("backfill", {})),
        )

    def as_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "observations": [o.as_list() for o in self.observations],
            "backfill": self.backfill,
        }

    def reset(self) -> None:
        """Forget everything that was learned."""
        self.observations.clear()
        self._keys.clear()
        self.backfill = {}
        self._collector.reset()
        self._estimate = None

    def add_observation(self, observation: Observation) -> bool:
        """Store an observation unless one for the same window already exists."""
        if observation.start and observation.start in self._keys:
            return False
        starts = [o.start for o in self.observations]
        self.observations.insert(bisect.bisect_right(starts, observation.start), observation)
        if observation.start:
            self._keys.add(observation.start)
        if len(self.observations) > MAX_STORED_OBSERVATIONS:
            for old in self.observations[:-MAX_STORED_OBSERVATIONS]:
                self._keys.discard(old.start)
            del self.observations[:-MAX_STORED_OBSERVATIONS]
        self._estimate = None
        return True

    def merge(self, observations: Iterable[Observation]) -> int:
        """Add several observations; returns how many were new."""
        return sum(1 for o in observations if self.add_observation(o))

    def add_sample(
        self,
        ts: datetime,
        inside: float | None,
        outside: float | None,
        heating: bool | float | None,
        valid: bool = True,
    ) -> Observation | None:
        """Add a live measurement; returns a new observation when a window completes."""
        observation = self._collector.add(ts, inside, outside, heating, valid)
        if observation is not None and self.add_observation(observation):
            return observation
        return None

    def fit_observations(self) -> list[Observation]:
        """Observations used for the fit: the last season, at least the last N."""
        if not self.observations:
            return []
        newest = self.observations[-1].start
        cutoff = newest - FIT_WINDOW_DAYS * 86400
        recent = [o for o in self.observations if o.start >= cutoff]
        if len(recent) < MIN_FIT_OBSERVATIONS:
            return self.observations[-MIN_FIT_OBSERVATIONS:]
        return recent

    @property
    def estimate(self) -> ModelEstimate:
        """Return the (cached) model fit."""
        if self._estimate is None:
            self._estimate = fit_model(self.fit_observations())
        return self._estimate

    def summary(self) -> dict:
        """Describe the collected data (for the panel)."""
        dated = [o for o in self.observations if o.start]
        fit = self.fit_observations()
        fit_dated = [o for o in fit if o.start]

        def iso(o: Observation | None) -> str | None:
            return datetime.fromtimestamp(o.start, UTC).isoformat() if o else None

        return {
            "data_points": len(self.observations),
            "from_history": sum(1 for o in self.observations if o.source == SOURCE_HISTORY),
            "from_live": sum(1 for o in self.observations if o.source == SOURCE_LIVE),
            "first": iso(dated[0] if dated else None),
            "last": iso(dated[-1] if dated else None),
            "days": len({o.day for o in dated}),
            "fit_points": len(fit),
            "fit_first": iso(fit_dated[0] if fit_dated else None),
            "heating_points": sum(1 for o in fit if o.duty > 0.1),
            "cooling_points": sum(1 for o in fit if o.duty <= 0.1),
        }


# ---------------------------------------------------------------------------
# Backfill from recorder history
# ---------------------------------------------------------------------------
Series = list[tuple[datetime, object]]


def _step(series: Series, minutes: list[datetime]) -> list[object]:
    """Sample-and-hold a change list onto the minute grid."""
    values: list[object] = []
    idx, current = 0, None
    for minute in minutes:
        while idx < len(series) and series[idx][0] <= minute:
            current = series[idx][1]
            idx += 1
        values.append(current)
    return values


def history_start(series_by_entity: dict[str, Series]) -> datetime | None:
    """Earliest moment at which every entity has history (None if one is missing)."""
    firsts = []
    for series in series_by_entity.values():
        known = [ts for ts, value in series if value is not None]
        if not known:
            return None
        firsts.append(min(known))
    return max(firsts) if firsts else None


def resample_history(
    loops: dict[str, tuple[Series, Series]],
    outdoor: Series,
    start: datetime,
    end: datetime,
    invalid: list[tuple[datetime, datetime]] = (),
    valves: list[Series] = (),
) -> Iterator[tuple[datetime, float | None, float | None, bool | float | None, bool]]:
    """Yield per-minute (ts, inside, outside, heating, valid) samples.

    ``loops`` maps each climate entity to two change lists: its
    ``current_temperature`` and its ``hvac_action``. Values are held until the
    next change; ``None`` means unknown/unavailable. ``valves`` are change lists
    of valve positions (0–100 %); when known, their mean is the heating
    intensity instead of the ``hvac_action``.
    """
    first = start.replace(second=0, microsecond=0)
    if first < start:
        first += SAMPLE_INTERVAL
    minutes: list[datetime] = []
    moment = first
    while moment < end:
        minutes.append(moment)
        moment += SAMPLE_INTERVAL
    if not minutes:
        return
    temps = [_step(t, minutes) for t, _ in loops.values()]
    actions = [_step(a, minutes) for _, a in loops.values()]
    outside = _step(outdoor, minutes)
    positions = [_step(v, minutes) for v in valves]
    invalid = sorted(invalid)
    for i, minute in enumerate(minutes):
        current = [t[i] for t in temps if isinstance(t[i], (int, float))]
        inside = sum(current) / len(current) if current else None
        known = [a[i] for a in actions if a[i] not in (None, "", "unknown", "unavailable")]
        heating: bool | float | None = (
            any(a in HEATING_ACTIONS for a in known) if known else None
        )
        opened = [p[i] for p in positions if isinstance(p[i], (int, float))]
        if opened:
            heating = sum(opened) / len(opened) / 100
        out = outside[i] if isinstance(outside[i], (int, float)) else None
        valid = not any(s <= minute < e for s, e in invalid)
        yield minute, inside, out, heating, valid


def observations_from_history(
    loops: dict[str, tuple[Series, Series]],
    outdoor: Series,
    start: datetime,
    end: datetime,
    invalid: list[tuple[datetime, datetime]] = (),
    valves: list[Series] = (),
) -> list[Observation]:
    """Compute observations from recorder history (source = history)."""
    collector = WindowCollector(SOURCE_HISTORY)
    result: list[Observation] = []
    for sample in resample_history(loops, outdoor, start, end, invalid, valves):
        if (obs := collector.add(*sample)) is not None:
            result.append(obs)
    # The last (incomplete) window is left to the live collector.
    return result



# ---------------------------------------------------------------------------
# Optimum start
# ---------------------------------------------------------------------------
def heatup_duration(
    inside: float,
    target: float,
    outside: float,
    heating_power: float,
    cooling_coefficient: float,
) -> timedelta | None:
    """Time needed to heat from ``inside`` to ``target`` at full duty.

    Solves ``dT/dt = h − k(T − T_out)``. Returns None when the target can not
    be reached (the equilibrium temperature is below the target).
    """
    if target <= inside:
        return timedelta(0)
    if heating_power <= 0:
        return None
    if cooling_coefficient < 1e-4:
        return timedelta(hours=(target - inside) / heating_power)
    equilibrium = outside + heating_power / cooling_coefficient
    if equilibrium <= target:
        return None
    hours = -math.log((target - equilibrium) / (inside - equilibrium)) / cooling_coefficient
    return timedelta(hours=hours)


@dataclass(slots=True)
class PreheatPlan:
    """Planned heating start for optimum start."""

    lead: timedelta
    method: str  # "model" or "fallback"
    model_lead: timedelta | None


def preheat_lead(
    inside: float | None,
    target: float,
    outside: float | None,
    estimate: ModelEstimate,
    fallback_rate: float = FALLBACK_HEATING_RATE,
    margin: timedelta = OPTIMUM_START_MARGIN,
    max_lead: timedelta = MAX_PREHEAT,
) -> PreheatPlan:
    """Return how long before the comfort time heating must start.

    While the model is not confident enough the safe fallback (a conservative
    fixed heating rate) is used; the earliest of both starts wins.
    """
    if inside is None:
        return PreheatPlan(lead=max_lead, method="fallback", model_lead=None)
    rise = max(0.0, target - inside)
    fallback = timedelta(hours=rise / fallback_rate) + margin if rise > 0 else timedelta(0)

    model_lead: timedelta | None = None
    if (
        estimate.heating_power is not None
        and estimate.cooling_coefficient is not None
        and outside is not None
    ):
        duration = heatup_duration(
            inside, target, outside, estimate.heating_power, estimate.cooling_coefficient
        )
        model_lead = max_lead if duration is None else duration + (margin if rise > 0 else timedelta(0))

    if model_lead is not None and estimate.confidence >= MIN_CONFIDENCE_FOR_MODEL:
        lead, method = model_lead, "model"
    else:
        lead, method = max(fallback, model_lead or timedelta(0)), "fallback"
    return PreheatPlan(lead=min(lead, max_lead), method=method, model_lead=model_lead)


# ---------------------------------------------------------------------------
# Night period
# ---------------------------------------------------------------------------
def _at(day: datetime, moment: time) -> datetime:
    return day.replace(
        hour=moment.hour, minute=moment.minute, second=moment.second, microsecond=0
    )


def night_period(now: datetime, start: time, end: time) -> tuple[datetime, datetime]:
    """Return (start, end) of the most recent night period that started ≤ now."""
    window_start = _at(now, start)
    if window_start > now:
        window_start -= timedelta(days=1)
    window_end = _at(window_start, end)
    if window_end <= window_start:
        window_end += timedelta(days=1)
    return window_start, window_end


# ---------------------------------------------------------------------------
# Comfort periods (day schedule)
# ---------------------------------------------------------------------------
def comfort_gaps(
    now: datetime, periods: Iterable[tuple[time, time]]
) -> list[tuple[datetime, datetime]]:
    """Return the (start, end) of the setback windows around ``now``, sorted.

    ``periods`` are the comfort periods of a day (e.g. 06:30–07:30 and
    17:00–21:00). Outside them the room is lowered: a setback window starts
    at the end of a comfort period and ends at the start of the next one.
    Periods may cross midnight. Windows that are covered by another period
    (overlapping periods) are dropped.
    """
    periods = [(s, e) for s, e in periods if s != e]
    if not periods:
        return []
    gaps: list[tuple[datetime, datetime]] = []
    for offset in (-2, -1, 0, 1):
        base = now + timedelta(days=offset)
        for _, end in periods:
            gap_start = _at(base, end)
            starts = [
                _at(gap_start + timedelta(days=d), s)
                for s, _ in periods
                for d in (0, 1)
            ]
            gap_end = min(s for s in starts if s > gap_start)
            gaps.append((gap_start, gap_end))
    covered = []
    for gap_start, gap_end in sorted(set(gaps)):
        inside_period = False
        for offset in (-1, 0):
            for start, end in periods:
                p_start = _at(gap_start + timedelta(days=offset), start)
                p_end = _at(p_start, end)
                if p_end <= p_start:
                    p_end += timedelta(days=1)
                if p_start <= gap_start < p_end:
                    inside_period = True
        if not inside_period:
            covered.append((gap_start, gap_end))
    return covered


def comfort_gap(
    now: datetime, periods: Iterable[tuple[time, time]]
) -> tuple[datetime, datetime] | None:
    """Return the most recent setback window that started ≤ now."""
    gaps = [gap for gap in comfort_gaps(now, periods) if gap[0] <= now]
    return gaps[-1] if gaps else None


def next_comfort_gap_start(
    now: datetime, periods: Iterable[tuple[time, time]]
) -> datetime | None:
    """Return the start of the first setback window after ``now``."""
    starts = [gap[0] for gap in comfort_gaps(now, periods) if gap[0] > now]
    return starts[0] if starts else None


def setback_hours(periods: Iterable[tuple[time, time]]) -> float:
    """Hours per day outside the comfort periods."""
    reference = datetime(2026, 1, 15, 12, 0)
    gaps = comfort_gaps(reference, periods)
    day_start = reference.replace(hour=0, minute=0)
    day_end = day_start + timedelta(days=1)
    total = 0.0
    for start, end in gaps:
        overlap = min(end, day_end) - max(start, day_start)
        total += max(0.0, overlap.total_seconds() / 3600)
    return total
