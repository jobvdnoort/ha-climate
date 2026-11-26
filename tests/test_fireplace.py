"""Tests for the fireplace detection."""

from datetime import datetime, timedelta

from .conftest import calc

T0 = datetime(2026, 1, 10, 18, 0)


def _detector(**kwargs):
    return calc.FireplaceDetector(
        threshold=kwargs.pop("threshold", 0.5),
        rise_window=timedelta(minutes=60),
        heating_cooldown=timedelta(minutes=60),
        **kwargs,
    )


def test_active_when_above_target_and_not_heating():
    det = _detector()
    assert det.update(T0, 21.6, 21.0, "idle") is True
    assert round(det.delta_to_target, 2) == 0.6


def test_not_active_below_threshold():
    det = _detector()
    assert det.update(T0, 21.3, 21.0, "idle") is False


def test_not_active_while_floor_heating_heats():
    det = _detector()
    assert det.update(T0, 22.0, 21.0, "heating") is False


def test_active_on_rise_without_heating():
    det = _detector()
    assert det.update(T0, 20.0, 21.0, "idle") is False
    assert det.update(T0 + timedelta(minutes=20), 20.3, 21.0, "idle") is False
    # Still below target, but rose 0.6 °C within the hour.
    assert det.update(T0 + timedelta(minutes=40), 20.6, 21.0, "idle") is True
    assert round(det.rise, 2) == 0.6


def test_rise_ignored_shortly_after_heating():
    """Floor heating keeps warming the room after it stops: no false positive."""
    det = _detector()
    det.update(T0, 20.0, 21.0, "heating")
    assert det.update(T0 + timedelta(minutes=30), 20.7, 21.0, "idle") is False
    # Above-target still counts though.
    assert det.update(T0 + timedelta(minutes=40), 21.6, 21.0, "idle") is True


def test_rise_window_drops_old_samples():
    det = _detector()
    det.update(T0, 20.0, 22.0, "idle")
    # 2 hours later: old sample is gone, so no rise is detected.
    assert det.update(T0 + timedelta(hours=2), 20.6, 22.0, "idle") is False


def test_hysteresis_keeps_active_until_half_threshold():
    det = _detector()
    assert det.update(T0, 21.6, 21.0, "idle") is True
    # Dropped to +0.3: above half threshold (0.25), still active.
    assert det.update(T0 + timedelta(minutes=90), 21.3, 21.0, "idle") is True
    # Dropped to +0.1: released.
    assert det.update(T0 + timedelta(minutes=180), 21.1, 21.0, "idle") is False


def test_heating_ends_fireplace_state():
    det = _detector()
    assert det.update(T0, 21.6, 21.0, "idle") is True
    assert det.update(T0 + timedelta(minutes=5), 21.6, 21.0, "heating") is False


def test_missing_temperature_is_inactive():
    det = _detector()
    assert det.update(T0, 21.6, 21.0, "idle") is True
    assert det.update(T0 + timedelta(minutes=1), None, 21.0, "idle") is False


def test_unknown_hvac_action_counts_as_not_heating():
    det = _detector()
    assert det.update(T0, 21.6, 21.0, None) is True
