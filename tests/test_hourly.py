"""Tests for the hourly setback vs. reheat comparison and the boiler run KPIs."""

from datetime import datetime, timedelta

import pytest

from .conftest import boiler, calc

START = datetime(2026, 11, 26, 12, 0)


def _hours(gas_by_hour):
    return [(START + timedelta(hours=i), 0.0, gas) for i, gas in enumerate(gas_by_hour)]


def test_setback_and_recovery_are_split() -> None:
    # Expected per hour: 0.5 × (18 − 0) / 24 = 0.375 m³.
    gas = [0.375] * 9 + [0.2] * 9 + [0.6] * 6 + [0.375] * 6
    lowered = lambda h: 1.0 if 21 <= h.hour or h.hour < 6 else 0.0  # noqa: E731
    result = calc.hourly_comparison(_hours(gas), 0.5, lambda _d: 18.0, lowered)
    sm = result["summary"]
    assert sm["setback"]["hours"] == 9
    assert sm["setback"]["saved"] == pytest.approx(9 * 0.175)
    assert sm["recovery"]["hours"] == 6
    assert sm["recovery"]["saved"] == pytest.approx(6 * -0.225)
    assert sm["other"]["saved"] == pytest.approx(0)
    assert sm["setback_and_recovery"] == pytest.approx(9 * 0.175 - 6 * 0.225)
    assert sm["net"] == pytest.approx(sm["setback_and_recovery"])
    assert result["hours"][0]["kind"] == "other"
    assert result["hours"][9]["kind"] == "setback"
    assert result["hours"][18]["kind"] == "recovery"
    assert result["hours"][-1]["cumulative_saved"] == pytest.approx(sm["net"])


def test_missing_hours_are_skipped() -> None:
    hours = [(START, None, 0.3), (START + timedelta(hours=1), 5.0, None)]
    result = calc.hourly_comparison(hours, 0.5, lambda _d: 18.0, lambda _h: 0.0)
    assert result["summary"]["net"] == 0
    assert result["hours"][0]["expected"] is None
    assert result["hours"][1]["saved"] is None


def test_long_run_counts_in_average_run_time() -> None:
    tracker = boiler.BoilerTracker()
    t = datetime(2026, 11, 27, 0, 0)
    tracker.update(t, False)
    # 10 short runs of 5 min at night, then one long run still going.
    for _ in range(10):
        tracker.update(t, True)
        t += timedelta(minutes=5)
        tracker.update(t, False)
        t += timedelta(minutes=25)
    tracker.update(t, True)
    for _ in range(7 * 60):
        t += timedelta(minutes=1)
        tracker.update(t, True)
    day = boiler.summarize_day(tracker.days["2026-11-27"])
    assert day["starts"] == 11
    assert day["avg_run_minutes"] == pytest.approx((50 + 420) / 11)
    assert not boiler.is_cycling(day["starts"], day["avg_run_minutes"])
    assert boiler.short_runs_warning(day["short_runs"], day["runs"])
    assert not boiler.short_runs_warning(2, 3)
