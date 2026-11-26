"""Tests for degree day calculations."""

from datetime import datetime

import pytest

from .conftest import calc


@pytest.mark.parametrize(
    ("mean", "limit", "expected"),
    [
        (8.0, 18.0, 10.0),
        (18.0, 18.0, 0.0),
        (22.5, 18.0, 0.0),
        (-3.5, 18.0, 21.5),
        (10.0, 16.0, 6.0),
    ],
)
def test_degree_days(mean, limit, expected):
    assert calc.degree_days(mean, limit) == pytest.approx(expected)


def test_degree_days_missing_temperature():
    assert calc.degree_days(None) is None


def test_accumulated_degree_days_scales_with_day_fraction():
    assert calc.accumulated_degree_days(8.0, 18.0, 0.5) == pytest.approx(5.0)
    assert calc.accumulated_degree_days(8.0, 18.0, 1.5) == pytest.approx(10.0)
    assert calc.accumulated_degree_days(20.0, 18.0, 0.5) == 0.0
    assert calc.accumulated_degree_days(None, 18.0, 0.5) is None


def test_day_fraction():
    assert calc.day_fraction(datetime(2026, 1, 1, 0, 0)) == 0.0
    assert calc.day_fraction(datetime(2026, 1, 1, 12, 0)) == pytest.approx(0.5)
    assert calc.day_fraction(datetime(2026, 1, 1, 18, 0)) == pytest.approx(0.75)


def test_expected_and_savings():
    expected = calc.expected_gas(0.4, 10.0)
    assert expected == pytest.approx(4.0)
    assert calc.gas_savings(expected, 3.2) == pytest.approx(0.8)
    assert calc.gas_savings(expected, 4.5) == pytest.approx(-0.5)
    assert calc.money(0.8, 1.35) == pytest.approx(1.08)
    assert calc.expected_gas(None, 10.0) is None
    assert calc.gas_savings(4.0, None) is None
    assert calc.money(0.8, None) is None
