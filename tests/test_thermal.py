"""Tests for the self-learning thermal model and optimum start."""

from datetime import UTC, datetime, time, timedelta
import math
import random

import pytest

from .conftest import thermal

T0 = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)


def _simulate(h=1.2, k=0.04, days=14, seed=1, lag_minutes=0):
    """Simulate a floor heated room with a PWM thermostat and night setback."""
    random.seed(seed)
    model = thermal.RoomThermalModel()
    temp, ts, effective = 20.0, T0, 0.0
    for minute in range(60 * 24 * days):
        hour = ts.hour + ts.minute / 60
        outside = 5 + 4 * math.sin(2 * math.pi * (hour - 15) / 24)
        target = 17.5 if (hour >= 22 or hour < 6) else 20.5
        heating = temp < target and minute % 15 >= 5 or temp < target - 0.3
        if lag_minutes:
            effective += (float(heating) - effective) / lag_minutes
        else:
            effective = float(heating)
        temp += (h * effective - k * (temp - outside)) / 60
        model.add_sample(ts, round(temp + random.gauss(0, 0.03), 1), outside, heating)
        ts += timedelta(minutes=1)
    return model


def test_model_learns_parameters():
    model = _simulate()
    est = model.estimate
    assert est.heating_power == pytest.approx(1.2, rel=0.1)
    assert est.cooling_coefficient == pytest.approx(0.04, rel=0.15)
    assert est.confidence > 80
    assert est.observations > 100
    # Rates at ΔT = 15 °C.
    assert est.cooling_rate(15) == pytest.approx(0.6, rel=0.15)
    assert est.heating_rate(15) == pytest.approx(0.6, rel=0.3)


def test_model_with_floor_lag_stays_reasonable():
    est = _simulate(lag_minutes=45).estimate
    assert 0.8 < est.heating_power < 1.4
    assert 0.02 < est.cooling_coefficient < 0.06


def test_confidence_grows_with_observations():
    short = _simulate(days=1).estimate
    long = _simulate(days=10).estimate
    assert short.confidence < long.confidence
    assert short.observations < long.observations


def test_no_observation_on_gaps_or_invalid_samples():
    model = thermal.RoomThermalModel()
    ts = T0
    for i in range(200):
        valid = i % 50 != 0  # invalid sample (e.g. fireplace) resets the window
        model.add_sample(ts, 20.0 - i * 0.005, 5.0, False, valid=valid)
        ts += timedelta(minutes=1)
    assert len(model.observations) == 0
    model.add_sample(ts + timedelta(minutes=30), 19.0, 5.0, False)  # gap
    assert len(model.observations) == 0


def test_window_with_gap_is_discarded():
    model = thermal.RoomThermalModel()
    for i in range(121):
        if 30 <= i < 45:  # 15 minutes without samples
            continue
        model.add_sample(T0 + timedelta(minutes=i), 20.0 - i * 0.01, 5.0, False)
    assert model.observations == []


def test_window_produces_observation():
    model = thermal.RoomThermalModel()
    ts = T0
    obs = None
    for i in range(121):
        obs = model.add_sample(ts, 20.0 - i * 0.01, 5.0, False) or obs
        ts += timedelta(minutes=1)
    assert obs is not None
    assert obs.start == int(T0.timestamp())
    assert obs.source == thermal.SOURCE_LIVE
    assert obs.slope == pytest.approx(-0.6, abs=0.01)
    assert obs.duty == 0.0
    assert obs.delta_t == pytest.approx(14.4, abs=0.1)


def test_only_cooling_data_estimates_k():
    obs = [thermal.Observation(-0.05 * dt, 0.0, dt) for dt in (10, 12, 14, 16) * 5]
    est = thermal.fit_model(obs)
    assert est.cooling_coefficient == pytest.approx(0.05)
    assert est.heating_power is None
    assert est.heating_confidence == 0
    assert est.confidence == 0


def test_serialization_roundtrip():
    model = _simulate(days=2)
    restored = thermal.RoomThermalModel.from_dict(model.as_dict())
    assert len(restored.observations) == len(model.observations)
    assert restored.estimate.heating_power == pytest.approx(model.estimate.heating_power, rel=1e-3)


def test_heatup_duration():
    # Linear when there is no heat loss.
    assert thermal.heatup_duration(18, 20, 5, 1.0, 0.0) == timedelta(hours=2)
    # Already warm.
    assert thermal.heatup_duration(21, 20, 5, 1.0, 0.04) == timedelta(0)
    # With heat loss it takes longer than linear.
    assert thermal.heatup_duration(18, 20, 5, 1.0, 0.04) > timedelta(hours=2)
    # Equilibrium 5 + 1/0.1 = 15 °C: target unreachable.
    assert thermal.heatup_duration(14, 20, 5, 1.0, 0.1) is None


def test_preheat_uses_fallback_when_confidence_low():
    est = thermal.ModelEstimate(
        heating_power=2.0, cooling_coefficient=0.01, heating_confidence=20, cooling_confidence=20
    )
    plan = thermal.preheat_lead(18.0, 20.0, 5.0, est)
    assert plan.method == "fallback"
    # 2 °C at 0.5 °C/h + 15 min margin; model alone would be ~1 h.
    assert plan.lead == timedelta(hours=4, minutes=15)
    assert plan.model_lead < plan.lead


def test_preheat_uses_model_when_confident():
    est = thermal.ModelEstimate(
        heating_power=1.0, cooling_coefficient=0.0, heating_confidence=90, cooling_confidence=90
    )
    plan = thermal.preheat_lead(18.0, 20.0, 5.0, est)
    assert plan.method == "model"
    assert plan.lead == timedelta(hours=2, minutes=15)


def test_preheat_caps_and_handles_missing_data():
    est = thermal.ModelEstimate(
        heating_power=1.0, cooling_coefficient=0.1, heating_confidence=90, cooling_confidence=90
    )
    assert thermal.preheat_lead(14.0, 20.0, 5.0, est).lead == thermal.MAX_PREHEAT
    assert thermal.preheat_lead(None, 20.0, 5.0, est).lead == thermal.MAX_PREHEAT
    assert thermal.preheat_lead(21.0, 20.0, 5.0, est).lead == timedelta(0)


def test_estimate_time_constant():
    est = thermal.ModelEstimate(cooling_coefficient=0.04)
    assert est.time_constant == pytest.approx(25.0)
    assert thermal.ModelEstimate().time_constant is None


def test_model_stage():
    est = thermal.ModelEstimate(heating_confidence=90, cooling_confidence=90)
    assert thermal.model_stage(est, 5) == 1
    assert thermal.model_stage(thermal.ModelEstimate(), 100) == 1
    low = thermal.ModelEstimate(heating_confidence=30, cooling_confidence=40)
    assert thermal.model_stage(low, 100) == 2
    assert thermal.model_stage(est, 100) == 3


def test_legacy_observations_are_loaded():
    model = thermal.RoomThermalModel.from_dict({"observations": [[-0.5, 0.0, 12.0]]})
    assert model.observations[0].slope == -0.5
    assert model.observations[0].start == 0
    data = model.as_dict()
    assert data["observations"][0] == [0, -0.5, 0.0, 12.0, "l"]


def test_dedup_on_window_start():
    model = thermal.RoomThermalModel()
    obs = thermal.Observation(-0.3, 0.0, 10.0, start=7200, source="h")
    assert model.add_observation(obs)
    assert not model.add_observation(thermal.Observation(-0.1, 0.5, 9.0, start=7200))
    assert model.merge([obs, thermal.Observation(-0.2, 0.0, 9.0, start=14400)]) == 1
    assert [o.start for o in model.observations] == [7200, 14400]
    # Out of order inserts stay sorted.
    model.add_observation(thermal.Observation(-0.2, 0.0, 9.0, start=3600 * 0))
    assert [o.start for o in model.observations] == [0, 7200, 14400]


def test_observations_are_kept_beyond_fit_window():
    model = thermal.RoomThermalModel()
    day = 86400
    for i in range(400):  # one observation per day for 400 days
        model.add_observation(thermal.Observation(-0.4, 0.0, 10.0, start=(i + 1) * day))
    assert len(model.observations) == 400
    fit = model.fit_observations()
    # At least MIN_FIT_OBSERVATIONS even though they span more than 90 days.
    assert len(fit) == thermal.MIN_FIT_OBSERVATIONS
    summary = model.summary()
    assert summary["data_points"] == 400
    assert summary["days"] == 400
    assert summary["fit_points"] == thermal.MIN_FIT_OBSERVATIONS


def _history_from_simulation(hours=8):
    """Build recorder-style change lists and the matching live model."""
    temps, actions, outdoor = [], [], []
    live = thermal.RoomThermalModel()
    temp = 20.0
    for minute in range(hours * 60):
        ts = T0 + timedelta(minutes=minute)
        heating = (minute // 60) % 2 == 0
        temp += (1.2 * heating - 0.04 * (temp - 5.0)) / 60
        value = round(temp, 2)
        if not temps or temps[-1][1] != value:
            temps.append((ts, value))
        action = "heating" if heating else "idle"
        if not actions or actions[-1][1] != action:
            actions.append((ts, action))
        live.add_sample(ts, value, 5.0, heating)
    outdoor.append((T0 - timedelta(hours=1), 5.0))
    return {"climate.a": (temps, actions)}, outdoor, live


def test_backfill_matches_live_and_deduplicates():
    loops, outdoor, live = _history_from_simulation()
    end = T0 + timedelta(hours=8)
    observations = thermal.observations_from_history(loops, outdoor, T0, end)
    assert len(observations) == 3  # the 4th window is still open
    assert all(o.source == thermal.SOURCE_HISTORY for o in observations)
    live_by_start = {o.start: o for o in live.observations}
    for obs in observations:
        assert obs.slope == pytest.approx(live_by_start[obs.start].slope, abs=1e-6)
        assert obs.duty == pytest.approx(live_by_start[obs.start].duty)
    # Merging history into the live model adds nothing; a fresh model gets all.
    assert live.merge(observations) == 0
    fresh = thermal.RoomThermalModel()
    assert fresh.merge(observations) == 3
    assert fresh.merge(observations) == 0


def test_backfill_skips_invalid_periods_and_unknown_action():
    loops, outdoor, _ = _history_from_simulation()
    end = T0 + timedelta(hours=8)
    invalid = [(T0 + timedelta(hours=2, minutes=10), T0 + timedelta(hours=2, minutes=40))]
    obs = thermal.observations_from_history(loops, outdoor, T0, end, invalid)
    assert [o.start for o in obs] == [int(T0.timestamp()), int(T0.timestamp()) + 4 * 3600]
    temps, actions = loops["climate.a"]
    unknown = {"climate.a": (temps, [(T0, None)])}
    assert thermal.observations_from_history(unknown, outdoor, T0, end) == []


def test_history_start_is_latest_first_value():
    series = {
        "a": [(T0, None), (T0 + timedelta(hours=1), 20.0)],
        "b": [(T0 + timedelta(hours=3), 5.0)],
    }
    assert thermal.history_start(series) == T0 + timedelta(hours=3)
    assert thermal.history_start({"a": [(T0, None)]}) is None


def test_night_period():
    start, end = time(22, 0), time(6, 30)
    s, e = thermal.night_period(datetime(2026, 1, 5, 23, 0), start, end)
    assert (s, e) == (datetime(2026, 1, 5, 22, 0), datetime(2026, 1, 6, 6, 30))
    s, e = thermal.night_period(datetime(2026, 1, 6, 3, 0), start, end)
    assert (s, e) == (datetime(2026, 1, 5, 22, 0), datetime(2026, 1, 6, 6, 30))
    # Daytime: the most recent night is already over.
    s, e = thermal.night_period(datetime(2026, 1, 6, 12, 0), start, end)
    assert e < datetime(2026, 1, 6, 12, 0)
