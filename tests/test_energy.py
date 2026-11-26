"""Tests for fixed costs, indoor correction, room ranking and event texts."""

from datetime import date, timedelta

import pytest

from .conftest import calc


def test_daily_fixed_costs():
    assert calc.daily_fixed_costs(30.4375, "month") == pytest.approx(1.0)
    assert calc.daily_fixed_costs(18.26, "month") == pytest.approx(0.5999, abs=1e-4)
    assert calc.daily_fixed_costs(0.6, "day") == pytest.approx(0.6)
    assert calc.daily_fixed_costs(None) == 0.0
    assert calc.daily_fixed_costs(0) == 0.0


def test_corrected_heating_limit():
    assert calc.corrected_heating_limit(18.0, None) == 18.0
    assert calc.corrected_heating_limit(18.0, 20.0) == 18.0
    assert calc.corrected_heating_limit(18.0, 21.5) == pytest.approx(19.5)
    assert calc.corrected_heating_limit(18.0, 19.0) == pytest.approx(17.0)


def test_baseline_with_per_day_limits():
    start = date(2026, 1, 1)
    records = [
        calc.DayRecord(start + timedelta(days=i), 8.0, 4.4) for i in range(2)
    ]
    # Day limit 19 °C (house at 21 °C): 11 degree days -> 0.4 m³/dd.
    limits = {r.day: 19.0 for r in records}
    result = calc.calculate_baseline(records, 18.0, min_days=1, limits=limits)
    assert result.m3_per_degree_day == pytest.approx(0.4)
    # Without correction: 10 degree days -> 0.44.
    assert calc.calculate_baseline(records, 18.0, min_days=1).m3_per_degree_day == pytest.approx(0.44)


def test_rank_rooms_orders_least_efficient_first():
    ranking = calc.rank_rooms(
        [
            ("bad", 0.07, 0.6),
            ("good", 0.02, 0.1),
            ("mid", 0.04, 0.3),
            ("unknown", None, None),
        ]
    )
    assert [r.room_id for r in ranking] == ["bad", "mid", "good", "unknown"]
    assert [r.rank for r in ranking] == [1, 2, 3, 4]
    by_id = {r.room_id: r for r in ranking}
    assert by_id["bad"].label == "Hoog warmteverlies"
    assert by_id["bad"].tags == ["hoog warmteverlies", "stookt veel"]
    assert by_id["bad"].score == pytest.approx(1.0)
    assert by_id["mid"].label == "Gemiddeld"
    assert by_id["good"].label == "Zuinig"
    assert by_id["unknown"].label == "Onvoldoende data"
    assert by_id["unknown"].score is None


def test_rank_rooms_heavy_heating_label():
    ranking = calc.rank_rooms([("a", 0.03, 0.55), ("b", 0.02, None)])
    assert ranking[0].room_id == "a"
    assert ranking[0].label == "Stookt veel"


def test_describe_night():
    assert calc.describe_night("21:30:00", "06:00:00", -1.5) == "-1,5 °C, 21:30–06:00"
    assert calc.describe_night("22:00", "06:30", None, 16.0) == "16,0 °C, 22:00–06:30"


def test_corrected_heating_limit_with_reference():
    # Reference = the comfort temperature of the baseline period.
    assert calc.corrected_heating_limit(18.0, None, 20.5) == 18.0
    assert calc.corrected_heating_limit(18.0, 20.5, 20.5) == 18.0
    assert calc.corrected_heating_limit(18.0, 21.5, 20.5) == pytest.approx(19.0)
