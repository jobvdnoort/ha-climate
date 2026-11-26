"""Boiler (OpenTherm) tracking and analysis.

Pure Python (no Home Assistant imports) so it can be unit tested.

The tracker follows the burner (flame) and hot water (DHW) status and keeps,
per local day: the number of burner starts, burning time, time spent on hot
water vs. space heating, the number of short runs (cycling) and averages of the
flow temperature and modulation while burning.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# A burner run shorter than this counts as a short cycle.
SHORT_RUN_MINUTES = 10.0
# Average run time below this (with enough starts) is reported as cycling.
CYCLING_AVG_MINUTES = 10.0
CYCLING_MIN_STARTS = 3
# Water pressure below this is shown as a warning.
MIN_PRESSURE = 1.2
MAX_PRESSURE = 2.5
# Longest gap that is still counted as continuous (e.g. a restart of HA).
MAX_ADVANCE = timedelta(minutes=10)

DAY_FIELDS = (
    "starts",
    "flame_s",
    "dhw_s",
    "heat_s",
    "short",
    "runs",
    "run_s",
    "flow_sum",
    "flow_n",
    "mod_sum",
    "mod_n",
)


def empty_day() -> dict[str, float]:
    """A new, empty day record."""
    return dict.fromkeys(DAY_FIELDS, 0)


@dataclass
class BoilerTracker:
    """Follows the flame and DHW status and accumulates daily statistics."""

    days: dict[str, dict[str, float]] = field(default_factory=dict)
    flame: bool | None = None
    dhw: bool | None = None
    run_start: datetime | None = None
    last: datetime | None = None
    track_flame: bool = True

    # ---- persistence ------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict | None, track_flame: bool = True) -> BoilerTracker:
        """Restore the daily statistics (the live state is re-read)."""
        data = data or {}
        days = {
            day: {**empty_day(), **values} for day, values in (data.get("days") or {}).items()
        }
        return cls(days=days, track_flame=track_flame)

    def as_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "days": {
                day: {k: round(v, 2) if isinstance(v, float) else v for k, v in values.items()}
                for day, values in self.days.items()
            }
        }

    def prune(self, cutoff: str) -> None:
        """Drop days before ``cutoff`` (ISO date)."""
        self.days = {day: v for day, v in self.days.items() if day >= cutoff}

    def day(self, key: str) -> dict[str, float]:
        """Return (and create) the record of a day."""
        return self.days.setdefault(key, empty_day())

    # ---- live tracking ------------------------------------------------
    def _accumulate(self, now: datetime) -> None:
        """Add the time since the last update to the current state."""
        if self.last is not None and now > self.last:
            elapsed = now - self.last
            if elapsed <= MAX_ADVANCE:
                record = self.day(self.last.date().isoformat())
                seconds = elapsed.total_seconds()
                burning = self.flame if self.track_flame else None
                if burning:
                    record["flame_s"] += seconds
                    if self.dhw:
                        record["dhw_s"] += seconds
                    else:
                        record["heat_s"] += seconds
                elif not self.track_flame and self.dhw:
                    # Without a flame sensor the DHW status alone is counted.
                    record["dhw_s"] += seconds
        self.last = now

    def update(
        self,
        now: datetime,
        flame: bool | None,
        dhw: bool | None = None,
    ) -> bool:
        """Process the current state; returns True when a new burner start began.

        ``None`` for ``flame``/``dhw`` means unknown: the previous state is kept.
        Call this on every state change and at least every minute.
        """
        self._accumulate(now)
        started = False
        key = now.date().isoformat()
        if dhw is not None:
            self.dhw = dhw
        if flame is not None and self.track_flame:
            if flame and self.flame is False:
                started = True
                self.day(key)["starts"] += 1
                self.run_start = now
            elif flame and self.flame is None:
                # Already burning when tracking began: the run length is unknown.
                self.run_start = None
            elif not flame and self.flame and self.run_start is not None:
                self._finish_run(now)
            if not flame:
                self.run_start = None
            self.flame = flame
        return started

    def _finish_run(self, now: datetime) -> None:
        minutes = (now - self.run_start).total_seconds() / 60
        record = self.day(self.run_start.date().isoformat())
        record["runs"] += 1
        record["run_s"] += minutes * 60
        if minutes < SHORT_RUN_MINUTES:
            record["short"] += 1

    def sample(self, now: datetime, flow: float | None, modulation: float | None) -> None:
        """Add a minute sample of the flow temperature and modulation."""
        if self.track_flame and not self.flame:
            return
        record = self.day(now.date().isoformat())
        if flow is not None:
            record["flow_sum"] += flow
            record["flow_n"] += 1
        if modulation is not None:
            record["mod_sum"] += modulation
            record["mod_n"] += 1

    def current_run_minutes(self, now: datetime) -> float | None:
        """Length of the burner run in progress (None when not burning/unknown)."""
        if not self.flame or self.run_start is None:
            return None
        return (now - self.run_start).total_seconds() / 60


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------
def summarize_day(record: dict[str, float] | None) -> dict[str, float | int | None]:
    """Derived KPIs of a day record."""
    if not record:
        return {
            "starts": None,
            "burn_hours": None,
            "avg_run_minutes": None,
            "short_runs": None,
            "dhw_minutes": None,
            "heat_minutes": None,
            "dhw_share": None,
            "flow_avg": None,
            "modulation_avg": None,
        }
    flame_s = record.get("flame_s", 0) or 0
    dhw_s = record.get("dhw_s", 0) or 0
    heat_s = record.get("heat_s", 0) or 0
    runs = record.get("runs", 0) or 0
    starts = int(record.get("starts", 0) or 0)
    if runs:
        avg_run = record.get("run_s", 0) / runs / 60
    elif starts:
        avg_run = flame_s / starts / 60
    else:
        avg_run = None
    burn_hours = flame_s / 3600
    # Values of the boiler's own counters (when configured) win.
    if record.get("ext_starts") is not None:
        starts = int(record["ext_starts"])
    if record.get("ext_hours") is not None:
        burn_hours = float(record["ext_hours"])
    if record.get("ext_avg") is not None:
        avg_run = float(record["ext_avg"])
    elif (record.get("ext_starts") is not None or record.get("ext_hours") is not None) and starts:
        avg_run = burn_hours * 60 / starts
    total = dhw_s + heat_s
    return {
        "starts": starts,
        "burn_hours": burn_hours,
        "avg_run_minutes": avg_run,
        "short_runs": int(record.get("short", 0) or 0),
        "dhw_minutes": dhw_s / 60,
        "heat_minutes": heat_s / 60,
        "dhw_share": dhw_s / total if total else None,
        "flow_avg": record["flow_sum"] / record["flow_n"] if record.get("flow_n") else None,
        "modulation_avg": record["mod_sum"] / record["mod_n"] if record.get("mod_n") else None,
    }


def is_cycling(starts: float | None, avg_run_minutes: float | None) -> bool:
    """Whether the burner short cycles (many short runs)."""
    return (
        starts is not None
        and avg_run_minutes is not None
        and starts >= CYCLING_MIN_STARTS
        and avg_run_minutes < CYCLING_AVG_MINUTES
    )


def pressure_status(pressure: float | None) -> str | None:
    """'low', 'high' or 'ok' for a water pressure in bar."""
    if pressure is None:
        return None
    if pressure < MIN_PRESSURE:
        return "low"
    if pressure > MAX_PRESSURE:
        return "high"
    return "ok"


def hours_from(value: float | None, unit: str | None) -> float | None:
    """Convert a duration sensor value to hours."""
    if value is None:
        return None
    unit = (unit or "h").lower()
    if unit in ("min", "minutes", "m"):
        return value / 60
    if unit in ("s", "sec", "seconds"):
        return value / 3600
    if unit in ("d", "days"):
        return value * 24
    return value


def minutes_from(value: float | None, unit: str | None) -> float | None:
    """Convert a duration sensor value to minutes (default unit: minutes)."""
    if value is None:
        return None
    unit = (unit or "min").lower()
    if unit in ("h", "hours"):
        return value * 60
    if unit in ("s", "sec", "seconds"):
        return value / 60
    return value


# ---------------------------------------------------------------------------
# 24 h trace from recorder history
# ---------------------------------------------------------------------------
Series = list[tuple[datetime, float | None]]


def resample(
    series: dict[str, Series | list[Series]],
    start: datetime,
    end: datetime,
    step: timedelta = timedelta(minutes=5),
    reduce: dict[str, str] | None = None,
) -> list[dict]:
    """Sample-and-hold several change lists onto a regular grid.

    A key may map to a list of series (e.g. all valve sensors); these are
    combined with ``reduce[key]`` ("max" or "mean", default "max").
    """
    reduce = reduce or {}
    grid: list[datetime] = []
    moment = start
    while moment <= end:
        grid.append(moment)
        moment += step

    def hold(values: Series) -> list[float | None]:
        ordered = sorted(values, key=lambda p: p[0])
        result: list[float | None] = []
        idx, current = 0, None
        for ts in grid:
            while idx < len(ordered) and ordered[idx][0] <= ts:
                current = ordered[idx][1]
                idx += 1
            result.append(current)
        return result

    columns: dict[str, list[float | None]] = {}
    for key, value in series.items():
        if value and isinstance(value[0], list):
            held = [hold(s) for s in value]
            mode = reduce.get(key, "max")
            column = []
            for i in range(len(grid)):
                known = [h[i] for h in held if h[i] is not None]
                if not known:
                    column.append(None)
                elif mode == "mean":
                    column.append(sum(known) / len(known))
                else:
                    column.append(max(known))
            columns[key] = column
        else:
            columns[key] = hold(value or [])
    return [
        {"ts": ts.isoformat(), **{key: col[i] for key, col in columns.items()}}
        for i, ts in enumerate(grid)
    ]


def valve_stats(values: Iterable[float | None]) -> tuple[float | None, float | None]:
    """Mean and maximum of valve positions (0-100 %)."""
    known = [max(0.0, min(100.0, v)) for v in values if v is not None]
    if not known:
        return None, None
    return sum(known) / len(known), max(known)
