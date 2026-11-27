"""Tests for comfort periods (day schedules with several blocks)."""

from datetime import datetime, time

from .conftest import calc, thermal

describe_periods = calc.describe_periods
parse_periods = calc.parse_periods
comfort_gap = thermal.comfort_gap
comfort_gaps = thermal.comfort_gaps
next_comfort_gap_start = thermal.next_comfort_gap_start
setback_hours = thermal.setback_hours

BATH = ((time(6, 30), time(7, 30)), (time(17, 0), time(21, 0)))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute)


def test_parse_periods_sorts_and_skips_invalid() -> None:
    raw = [
        {"start": "17:00:00", "end": "21:00:00"},
        {"start": "06:30", "end": "07:30"},
        {"start": "08:00", "end": "08:00"},
        {"start": "x"},
        "nonsense",
    ]
    assert parse_periods(raw) == BATH
    assert parse_periods(None) == ()


def test_gap_during_the_day() -> None:
    assert comfort_gap(at(27, 12), BATH) == (at(27, 7, 30), at(27, 17))


def test_gap_overnight() -> None:
    assert comfort_gap(at(27, 23), BATH) == (at(27, 21), at(28, 6, 30))
    assert comfort_gap(at(28, 3), BATH) == (at(27, 21), at(28, 6, 30))


def test_inside_a_period_the_last_gap_is_over() -> None:
    start, end = comfort_gap(at(27, 18), BATH)
    assert (start, end) == (at(27, 7, 30), at(27, 17))
    assert end <= at(27, 18)
    assert next_comfort_gap_start(at(27, 18), BATH) == at(27, 21)


def test_period_across_midnight() -> None:
    periods = ((time(22, 0), time(2, 0)),)
    assert comfort_gap(at(27, 12), periods) == (at(27, 2), at(27, 22))
    start, end = comfort_gap(at(27, 23), periods)
    assert end <= at(27, 23)


def test_overlapping_periods_are_merged() -> None:
    periods = ((time(6, 0), time(9, 0)), (time(8, 0), time(10, 0)))
    gaps = comfort_gaps(at(27, 12), periods)
    assert all(start.hour != 9 for start, _ in gaps)
    assert comfort_gap(at(27, 12), periods) == (at(27, 10), at(28, 6))


def test_setback_hours() -> None:
    assert setback_hours(BATH) == 19.0


def test_describe_periods() -> None:
    assert describe_periods(BATH, -1.5) == "comfort 06:30–07:30, 17:00–21:00, daarbuiten -1,5 °C"
    assert describe_periods(BATH, None, 18.0).endswith("daarbuiten 18,0 °C")
