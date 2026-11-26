"""Tests for the gas baseline calculation."""

from datetime import date, timedelta

import pytest

from .conftest import calc

START = date(2025, 12, 1)


def _records(values):
    return [
        calc.DayRecord(day=START + timedelta(days=i), mean_temperature=t, gas=g)
        for i, (t, g) in enumerate(values)
    ]


def test_baseline_is_ratio_of_sums():
    # degree days: 10, 8, 12 -> 30; gas: 4, 3, 5 -> 12; baseline 0.4
    records = _records([(8.0, 4.0), (10.0, 3.0), (6.0, 5.0)])
    result = calc.calculate_baseline(records, 18.0, min_days=3)
    assert result.m3_per_degree_day == pytest.approx(0.4)
    assert result.days_used == 3
    assert result.total_degree_days == pytest.approx(30.0)
    assert result.first_day == START
    assert result.last_day == START + timedelta(days=2)


def test_baseline_excludes_fireplace_and_setback_days():
    records = _records([(8.0, 4.0), (8.0, 1.0), (8.0, 2.0), (8.0, 4.0)])
    result = calc.calculate_baseline(
        records,
        18.0,
        fireplace_days={START + timedelta(days=1)},
        setback_days={START + timedelta(days=2)},
        min_days=2,
    )
    assert result.m3_per_degree_day == pytest.approx(0.4)
    assert result.days_used == 2
    assert result.excluded_fireplace == 1
    assert result.excluded_setback == 1


def test_baseline_skips_warm_and_invalid_days():
    records = _records(
        [(8.0, 4.0), (17.5, 0.8), (None, 3.0), (8.0, None), (8.0, -12.0), (8.0, 4.0)]
    )
    result = calc.calculate_baseline(records, 18.0, min_degree_days=1.0, min_days=2)
    assert result.m3_per_degree_day == pytest.approx(0.4)
    assert result.excluded_warm == 1
    assert result.excluded_invalid == 3


def test_baseline_requires_minimum_days():
    records = _records([(8.0, 4.0)] * 3)
    result = calc.calculate_baseline(records, 18.0, min_days=7)
    assert result.m3_per_degree_day is None
    assert not result.is_valid
    assert result.days_used == 3


def test_baseline_empty():
    result = calc.calculate_baseline([], 18.0)
    assert result.m3_per_degree_day is None


def test_fireplace_excluded_days_threshold():
    minutes = {"2025-12-01": 10, "2025-12-02": 30, "2025-12-03": 240}
    assert calc.fireplace_excluded_days(minutes, 30) == {
        date(2025, 12, 2),
        date(2025, 12, 3),
    }
