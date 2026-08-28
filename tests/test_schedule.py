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


def test_default_window_covers_ethiopian_one_to_twelve(schedule: Schedule) -> None:
    assert not schedule.is_open(at("2026-08-28 06:59"))
    assert schedule.is_open(at("2026-08-28 07:00"))
    assert schedule.is_open(at("2026-08-28 18:00"))
    assert not schedule.is_open(at("2026-08-28 19:00"))


def test_sunday_is_skipped(schedule: Schedule) -> None:
    assert not schedule.is_open(at("2026-08-30 09:00"))
    assert schedule.next_slot(at("2026-08-29 18:30")) == at("2026-08-31 07:00")


def test_slots_are_hourly(schedule: Schedule) -> None:
    assert schedule.next_slot(at("2026-08-28 07:00")) == at("2026-08-28 08:00")
    assert schedule.next_slot(at("2026-08-28 07:30")) == at("2026-08-28 08:00")


def test_evening_rolls_to_the_next_morning(schedule: Schedule) -> None:
    assert schedule.next_slot(at("2026-08-28 18:10")) == at("2026-08-29 07:00")


def test_weekday_parsing() -> None:
    assert parse_weekdays("mon-sat") == frozenset(range(6))
    assert parse_weekdays("mon,wed,fri") == frozenset({0, 2, 4})
    with pytest.raises(ScheduleError):
        parse_weekdays("funday")


def test_reversed_window_is_rejected() -> None:
    with pytest.raises(ScheduleError):
        Schedule.build(first_hour=18, last_hour=7)
