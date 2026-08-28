from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ethiopian_jobs.schedule import Schedule, ScheduleError, parse_weekdays

ADDIS = ZoneInfo("Africa/Addis_Ababa")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ADDIS)


@pytest.fixture
def schedule() -> Schedule:
    return Schedule.build()


def test_the_default_runs_every_two_hours_on_every_day(schedule: Schedule) -> None:
    assert schedule.step_hours == 2
    assert len(schedule.weekdays) == 7
    assert schedule.next_slot(at("2026-08-28 07:10")) == at("2026-08-28 08:00")
    assert schedule.next_slot(at("2026-08-28 22:30")) == at("2026-08-29 00:00")
    # Sunday is no longer skipped.
    assert schedule.is_open(at("2026-08-30 10:00"))


def test_odd_hours_are_not_slots(schedule: Schedule) -> None:
    assert schedule.is_open(at("2026-08-28 10:00"))
    assert not schedule.is_open(at("2026-08-28 11:00"))


def test_a_daytime_window_can_still_be_configured() -> None:
    office = Schedule.build(first_hour=7, last_hour=18, weekdays=parse_weekdays("mon-sat"))
    assert not office.is_open(at("2026-08-28 06:59"))
    assert office.is_open(at("2026-08-28 07:00"))
    assert not office.is_open(at("2026-08-30 09:00"))
    assert office.next_slot(at("2026-08-29 18:30")) == at("2026-08-31 07:00")


def test_an_hourly_window_keeps_every_hour() -> None:
    hourly = Schedule.build(first_hour=7, last_hour=18, step_hours=1)
    assert hourly.next_slot(at("2026-08-28 07:00")) == at("2026-08-28 08:00")


def test_weekday_parsing() -> None:
    assert parse_weekdays("mon-sat") == frozenset(range(6))
    assert parse_weekdays("mon,wed,fri") == frozenset({0, 2, 4})
    with pytest.raises(ScheduleError):
        parse_weekdays("funday")


def test_a_bad_window_or_gap_is_rejected() -> None:
    with pytest.raises(ScheduleError):
        Schedule.build(first_hour=18, last_hour=7)
    with pytest.raises(ScheduleError):
        Schedule.build(step_hours=0)
