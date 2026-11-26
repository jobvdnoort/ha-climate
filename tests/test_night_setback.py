"""Tests for the night setback helpers."""

from datetime import time

import pytest

from .conftest import calc


def test_parse_time():
    assert calc.parse_time("22:00:00") == time(22, 0)
    assert calc.parse_time("06:30") == time(6, 30)
    assert calc.parse_time(time(7, 15)) == time(7, 15)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (time(21, 59), False),
        (time(22, 0), True),
        (time(23, 30), True),
        (time(0, 0), True),
        (time(6, 29), True),
        (time(6, 30), False),
        (time(12, 0), False),
    ],
)
def test_window_over_midnight(now, expected):
    assert calc.in_time_window(now, time(22, 0), time(6, 30)) is expected


def test_window_same_day_and_empty():
    assert calc.in_time_window(time(13, 0), time(12, 0), time(14, 0))
    assert not calc.in_time_window(time(14, 0), time(12, 0), time(14, 0))
    assert not calc.in_time_window(time(12, 0), time(12, 0), time(12, 0))


def test_setback_target():
    assert calc.setback_target(21.0, -2.0) == 19.0
    assert calc.setback_target(20.5, -2.0, step=0.5) == 18.5
    assert calc.setback_target(20.3, -2.0, step=0.5) == 18.5
    assert calc.setback_target(8.0, -2.0, min_temp=7.0) == 7.0


def test_restore_value():
    # Unchanged during the night -> restore original.
    assert calc.restore_value(19.0, 19.0, 21.0) == 21.0
    # Manually changed -> leave alone.
    assert calc.restore_value(20.0, 19.0, 21.0) is None
    # Unknown current value -> restore.
    assert calc.restore_value(None, 19.0, 21.0) == 21.0
