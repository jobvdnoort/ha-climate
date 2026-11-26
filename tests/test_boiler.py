"""Tests for the boiler (OpenTherm) tracking and the valve based heating intensity."""

from datetime import UTC, datetime, timedelta

import pytest

from .conftest import boiler, thermal

T0 = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)


def _run(tracker, schedule, dhw=None, start=T0):
    """Feed minute samples: ``schedule`` is a list of (minutes, flame)."""
    ts = start
    for minutes, flame in schedule:
        for _ in range(minutes):
            tracker.update(ts, flame, dhw)
            tracker.sample(ts, 45.0, 30.0)
            ts += timedelta(minutes=1)
    tracker.update(ts, False, dhw)
    return ts


def test_starts_burn_time_and_runs():
    tracker = boiler.BoilerTracker()
    _run(tracker, [(10, False), (30, True), (10, False), (5, True), (5, False)])
    day = boiler.summarize_day(tracker.days[T0.date().isoformat()])
    assert day["starts"] == 2
    assert day["burn_hours"] == pytest.approx(35 / 60)
    assert day["avg_run_minutes"] == pytest.approx(17.5)
    assert day["short_runs"] == 1
    assert day["flow_avg"] == pytest.approx(45.0)
    assert day["modulation_avg"] == pytest.approx(30.0)
    assert day["heat_minutes"] == pytest.approx(35)
    assert day["dhw_minutes"] == 0


def test_running_at_start_is_not_a_start():
    tracker = boiler.BoilerTracker()
    _run(tracker, [(20, True), (5, False)])
    day = boiler.summarize_day(tracker.days[T0.date().isoformat()])
    assert day["starts"] == 0
    assert day["burn_hours"] == pytest.approx(20 / 60)


def test_unknown_state_keeps_previous():
    tracker = boiler.BoilerTracker()
    tracker.update(T0, False)
    tracker.update(T0 + timedelta(minutes=1), True)
    tracker.update(T0 + timedelta(minutes=2), None)
    tracker.update(T0 + timedelta(minutes=3), True)
    assert tracker.days[T0.date().isoformat()]["starts"] == 1
    assert tracker.current_run_minutes(T0 + timedelta(minutes=4)) == pytest.approx(3)


def test_hot_water_vs_heating():
    tracker = boiler.BoilerTracker()
    ts = _run(tracker, [(1, False), (20, True)], dhw=False)
    _run(tracker, [(1, False), (10, True)], dhw=True, start=ts)
    day = boiler.summarize_day(tracker.days[T0.date().isoformat()])
    assert day["heat_minutes"] == pytest.approx(20)
    assert day["dhw_minutes"] == pytest.approx(10)
    assert day["dhw_share"] == pytest.approx(1 / 3)


def test_dhw_without_flame_sensor():
    tracker = boiler.BoilerTracker(track_flame=False)
    for minute in range(16):
        tracker.update(T0 + timedelta(minutes=minute), None, minute < 15)
    day = boiler.summarize_day(tracker.days[T0.date().isoformat()])
    assert day["dhw_minutes"] == pytest.approx(15)
    assert day["starts"] == 0


def test_long_gaps_are_not_counted():
    tracker = boiler.BoilerTracker()
    tracker.update(T0, False)
    tracker.update(T0 + timedelta(minutes=1), True)
    tracker.update(T0 + timedelta(hours=3), True)  # HA was down
    assert tracker.days[T0.date().isoformat()]["flame_s"] == 0


def test_external_counters_win_and_roundtrip():
    tracker = boiler.BoilerTracker()
    _run(tracker, [(1, False), (5, True)])
    record = tracker.day(T0.date().isoformat())
    record["ext_starts"] = 12
    record["ext_hours"] = 3.0
    restored = boiler.BoilerTracker.from_dict(tracker.as_dict())
    day = boiler.summarize_day(restored.days[T0.date().isoformat()])
    assert day["starts"] == 12
    assert day["burn_hours"] == 3.0
    assert day["avg_run_minutes"] == pytest.approx(15)


def test_cycling_pressure_and_units():
    assert boiler.is_cycling(12, 6.0)
    assert not boiler.is_cycling(2, 4.0)
    assert not boiler.is_cycling(12, 25.0)
    assert boiler.pressure_status(1.1) == "low"
    assert boiler.pressure_status(1.6) == "ok"
    assert boiler.pressure_status(None) is None
    assert boiler.hours_from(90, "min") == 1.5
    assert boiler.hours_from(2, "h") == 2
    assert boiler.minutes_from(0.5, "h") == 30
    assert boiler.minutes_from(12, None) == 12
    assert boiler.summarize_day(None)["starts"] is None


def test_resample_and_valve_max():
    start = T0
    series = {
        "flow": [(T0 - timedelta(minutes=3), 40.0), (T0 + timedelta(minutes=7), 50.0)],
        "valve_max": [
            [(T0, 20.0)],
            [(T0 + timedelta(minutes=5), 80.0)],
        ],
    }
    points = boiler.resample(series, start, T0 + timedelta(minutes=10))
    assert [p["flow"] for p in points] == [40.0, 40.0, 50.0]
    assert [p["valve_max"] for p in points] == [20.0, 80.0, 80.0]
    assert boiler.valve_stats([10, None, 50]) == (30, 50)
    assert boiler.valve_stats([None]) == (None, None)


def test_valve_position_is_heating_intensity():
    model = thermal.RoomThermalModel()
    ts = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    temp = 20.0
    observation = None
    for _ in range(121):
        observation = model.add_sample(ts, temp, 5.0, 0.4) or observation
        temp += 0.005
        ts += timedelta(minutes=1)
    assert observation is not None
    assert observation.duty == pytest.approx(0.4)


def test_history_uses_valves_over_hvac_action():
    start = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    loops = {"climate.a": ([(start, 20.0)], [(start, "idle")])}
    outdoor = [(start, 5.0)]
    valves = [[(start, 60.0)], [(start, 20.0)]]
    samples = list(
        thermal.resample_history(loops, outdoor, start, start + timedelta(minutes=2), (), valves)
    )
    assert samples[0][3] == pytest.approx(0.4)
    samples = list(thermal.resample_history(loops, outdoor, start, start + timedelta(minutes=2)))
    assert samples[0][3] is False
