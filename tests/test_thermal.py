"""Tests for the self-learning thermal model and optimum start."""

from datetime import datetime, time, timedelta
import math
import random

import pytest

from .conftest import thermal

T0 = datetime(2026, 1, 5, 0, 0)


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


def test_window_produces_observation():
    model = thermal.RoomThermalModel()
    ts = T0
    obs = None
    for i in range(121):
        obs = model.add_sample(ts, 20.0 - i * 0.01, 5.0, False) or obs
        ts += timedelta(minutes=1)
    assert obs is not None
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


def test_night_period():
    start, end = time(22, 0), time(6, 30)
    s, e = thermal.night_period(datetime(2026, 1, 5, 23, 0), start, end)
    assert (s, e) == (datetime(2026, 1, 5, 22, 0), datetime(2026, 1, 6, 6, 30))
    s, e = thermal.night_period(datetime(2026, 1, 6, 3, 0), start, end)
    assert (s, e) == (datetime(2026, 1, 5, 22, 0), datetime(2026, 1, 6, 6, 30))
    # Daytime: the most recent night is already over.
    s, e = thermal.night_period(datetime(2026, 1, 6, 12, 0), start, end)
    assert e < datetime(2026, 1, 6, 12, 0)
