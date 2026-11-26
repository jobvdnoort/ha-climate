"""Tests for the saving advice."""

from datetime import datetime, time, timedelta
import math

import pytest

from .conftest import advice as adv


def test_setback_hours_slow_room_limited_by_cooling():
    # τ = 50 h: in 9 h the room cools 15 × (1 − e^−0.18) ≈ 2.47 °C at most.
    slow = adv.setback_degree_hours(15, 0.02, -4, 9, 0.5)
    deep = adv.setback_degree_hours(15, 0.02, -10, 9, 0.5)
    assert slow == pytest.approx(deep)  # deeper than reachable makes no difference
    shallow = adv.setback_degree_hours(15, 0.02, -1, 9, 0.5)
    assert 0 < shallow < slow


def test_setback_hours_includes_reheat():
    # A fast room reaches the setpoint and then stays there.
    area = adv.setback_degree_hours(15, 0.5, -2, 9, 1.0)
    reach = -math.log(1 - 2 / 15) / 0.5
    expected = 15 * (reach - (1 - math.exp(-0.5 * reach)) / 0.5) + 2 * (9 - reach) + 2 * 2 / 2
    assert area == pytest.approx(expected)
    assert adv.setback_degree_hours(0, 0.5, -2, 9, 1.0) == 0


def test_night_drop():
    assert adv.night_drop(15, 0.02, -1.5, 9) == pytest.approx(1.5)
    assert adv.night_drop(15, 0.005, -3, 9) == pytest.approx(15 * (1 - math.exp(-0.045)))


def test_window_hours_over_midnight():
    assert adv.window_hours(time(21), time(6)) == 9
    assert adv.window_hours(time(1), time(5, 30)) == 4.5


def test_summarize_setpoints_day_and_night():
    start = datetime(2026, 11, 20, 6)
    loop = [
        (start, 20.0, 19.5),
        (start + timedelta(hours=15), 18.0, 19.0),
        (start + timedelta(hours=24), 20.0, 19.5),
    ]
    result = adv.summarize_setpoints(
        [loop], start, start + timedelta(hours=30), time(21), time(6), step=timedelta(hours=1)
    )
    assert result["day"] == pytest.approx(20.0)
    assert result["night"] == pytest.approx(18.0)
    assert 19.0 < result["measured"] < 19.5


def _rooms(**kwargs):
    base = {"cooling": 0.04, "heat_rate": 0.8, "confidence": 70, "day_target": 20.0, "measured": 20.0}
    base.update(kwargs)
    return [adv.RoomInput("a", "Woonkamer", weight=3, **base), adv.RoomInput("b", "Slaapkamer", **base)]


def _house(**kwargs):
    base = {"outdoor_mean": 5.0, "heating_gas_per_day": 6.0, "gas_price": 1.5, "days": 10}
    base.update(kwargs)
    return adv.HouseInput(**base)


def test_first_day_shows_measurement_started():
    result = adv.build_advice(_rooms(offset=-1.5), _house())
    tips = {t["id"]: t for t in result["tips"]}
    assert result["tips"][0]["id"] == "measurement"
    assert tips["measurement"]["title"] == "Meting gestart"
    # Overall 0.5 °C lower with ΔT 15: 1/30 of the heating gas.
    assert tips["day-lower"]["saving_m3_month"] == pytest.approx(6.0 / 30 * 30, abs=0.1)
    assert tips["night-deeper"]["saving_m3_month"] > 0
    assert tips["night-earlier"]["saving_m3_month"] > 0
    assert result["basis"]["calibration"] == 1.0
    assert 0 < result["basis"]["predicted_fraction"] < 0.1


def test_calibration_with_measured_days():
    rooms = _rooms(offset=-1.5)
    predicted = adv.build_advice(rooms, _house())["basis"]["predicted_fraction"]
    # Measured twice the predicted saving over 14 days: full correction.
    house = _house(measured_days=14, measured_expected=100.0, measured_actual=100 * (1 - 2 * predicted))
    result = adv.build_advice(rooms, house)
    assert result["basis"]["calibration"] == pytest.approx(2.0, rel=1e-3)
    assert result["basis"]["measured_fraction"] == pytest.approx(2 * predicted)
    # With 7 days only half of the correction is applied.
    house.measured_days = 7
    assert adv.build_advice(rooms, house)["basis"]["calibration"] == pytest.approx(1.5, rel=1e-3)
    # Too few days: no calibration yet.
    house.measured_days = 2
    assert adv.build_advice(rooms, house)["basis"]["calibration"] == 1.0


def test_room_tips():
    rooms = _rooms(offset=-1.5)
    rooms[1].day_target = 22.0
    rooms[1].measured = 22.0
    rooms[0].measured = 21.5  # 1.5 °C above setpoint
    rooms[0].label = "Hoog warmteverlies"
    result = adv.build_advice(rooms, _house())
    ids = {t["id"] for t in result["tips"]}
    assert {"warm-b", "above-a", "loss-a"} <= ids


def test_disabled_setback_and_no_data():
    rooms = _rooms(offset=-2)
    result = adv.build_advice(rooms, _house(master_enabled=False))
    tips = {t["id"]: t for t in result["tips"]}
    assert tips["night-enable"]["saving_eur_month"] > 0
    assert "night-deeper" not in tips
    empty = adv.build_advice(rooms, _house(heating_gas_per_day=None))
    assert [t["id"] for t in empty["tips"]] == ["measurement", "no-data"]


def _period(text, days, fraction, current=False, expected=50.0):
    return {
        "text": text, "days": days, "fraction": fraction, "current": current, "start": "2026-11-27",
        "expected": expected, "per_day": fraction * expected / days if days else None,
        "settings": {"master": True, "night_start": "21:00", "night_end": "06:00", "night_offset": -1.5},
    }


def test_revert_tip_when_earlier_setting_did_better():
    periods = [_period("Nachtverlaging -1,5 °C", 10, 0.08), _period("Nachtverlaging -3,0 °C", 5, 0.02, True)]
    result = adv.build_advice(_rooms(offset=-3), _house(periods=periods))
    tip = next(t for t in result["tips"] if t["id"] == "revert")
    assert tip["action"]["night_offset"] == -1.5
    assert tip["saving_m3_month"] > 0


def test_works_tip_and_no_judgement_too_early():
    periods = [_period("Nachtverlaging -1,5 °C", 4, 0.06, True)]
    ids = [t["id"] for t in adv.build_advice(_rooms(offset=-1.5), _house(periods=periods))["tips"]]
    assert "works" in ids
    periods = [_period("Nachtverlaging -1,5 °C", 2, -0.2, True)]
    ids = [t["id"] for t in adv.build_advice(_rooms(offset=-1.5), _house(periods=periods))["tips"]]
    assert not {"works", "revert", "no-effect"} & set(ids)


def test_no_effect_tip():
    periods = [_period("Nachtverlaging uit", 8, 0.0), _period("Nachtverlaging -2,0 °C", 6, -0.05, True)]
    tip = next(
        t for t in adv.build_advice(_rooms(offset=-2), _house(periods=periods))["tips"] if t["id"] in ("revert", "no-effect")
    )
    assert tip["id"] == "revert"  # the earlier setting did better
