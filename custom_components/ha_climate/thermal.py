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
  of requiring long uninterrupted heating periods.

The room is sampled every minute. Every ``window`` (2 h) of valid, gap-free
samples yields one observation: the least-squares temperature slope (°C/h),
the duty cycle and the mean ΔT. ``h`` and ``k`` follow from a linear least
squares fit over the most recent observations, and the standard errors of the
fit give a confidence score.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import math

# --- Tuning ---------------------------------------------------------------
WINDOW = timedelta(hours=2)
MAX_GAP = timedelta(minutes=10)
MIN_SAMPLES = 20
MAX_OBSERVATIONS = 300  # ~25 days of 2 h windows: adapts to seasons
FULL_CONFIDENCE_OBSERVATIONS = 60
MIN_CONFIDENCE_FOR_MODEL = 50.0  # %, below this the safe fallback is used
FALLBACK_HEATING_RATE = 0.5  # °C/h, conservative default for floor heating
OPTIMUM_START_MARGIN = timedelta(minutes=15)
MAX_PREHEAT = timedelta(hours=6)


@dataclass(slots=True)
class Observation:
    """One window of measurements."""

    slope: float  # °C/h
    duty: float  # 0..1
    delta_t: float  # mean T_in - T_out

    def as_list(self) -> list[float]:
        """Serialize compactly."""
        return [round(self.slope, 4), round(self.duty, 3), round(self.delta_t, 2)]

    @classmethod
    def from_list(cls, data: Iterable[float]) -> Observation:
        """Deserialize."""
        slope, duty, delta_t = data
        return cls(float(slope), float(duty), float(delta_t))


@dataclass(slots=True)
class ModelEstimate:
    """Result of fitting the model."""

    heating_power: float | None = None  # h, °C/h
    cooling_coefficient: float | None = None  # k, 1/h
    heating_confidence: float = 0.0  # %
    cooling_confidence: float = 0.0  # %
    observations: int = 0

    @property
    def confidence(self) -> float:
        """Overall confidence: the weakest of both parameters."""
        return min(self.heating_confidence, self.cooling_confidence)

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


@dataclass
class RoomThermalModel:
    """Collects samples for one room and maintains the observations."""

    observations: list[Observation] = field(default_factory=list)
    window: timedelta = WINDOW
    _samples: list[tuple[datetime, float, float, bool]] = field(
        default_factory=list, repr=False
    )
    _estimate: ModelEstimate | None = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: dict | None) -> RoomThermalModel:
        """Restore from storage."""
        data = data or {}
        return cls(
            observations=[Observation.from_list(o) for o in data.get("observations", [])]
        )

    def as_dict(self) -> dict:
        """Serialize for storage."""
        return {"observations": [o.as_list() for o in self.observations]}

    def reset(self) -> None:
        """Forget everything that was learned."""
        self.observations.clear()
        self._samples.clear()
        self._estimate = None

    def add_sample(
        self,
        ts: datetime,
        inside: float | None,
        outside: float | None,
        heating: bool | None,
        valid: bool = True,
    ) -> Observation | None:
        """Add a measurement; returns a new observation when a window completes."""
        if not valid or inside is None or outside is None or heating is None:
            self._samples.clear()
            return None
        if self._samples and ts - self._samples[-1][0] > MAX_GAP:
            self._samples.clear()
        self._samples.append((ts, inside, outside, heating))
        if ts - self._samples[0][0] < self.window or len(self._samples) < MIN_SAMPLES:
            return None

        samples = self._samples
        observation = Observation(
            slope=_slope_per_hour([(s[0], s[1]) for s in samples]),
            duty=sum(1 for s in samples if s[3]) / len(samples),
            delta_t=sum(s[1] - s[2] for s in samples) / len(samples),
        )
        # Next window starts where this one ended.
        self._samples = [samples[-1]]
        if abs(observation.slope) > 5:  # implausible (window opened, sensor glitch)
            return None
        self.observations.append(observation)
        del self.observations[:-MAX_OBSERVATIONS]
        self._estimate = None
        return observation

    @property
    def estimate(self) -> ModelEstimate:
        """Return the (cached) model fit."""
        if self._estimate is None:
            self._estimate = fit_model(self.observations)
        return self._estimate


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
