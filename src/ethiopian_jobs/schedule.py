from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Ethiopian clock 1:00 to 12:00 is 07:00 to 18:00 local time.
DEFAULT_TIMEZONE = "Africa/Addis_Ababa"
DEFAULT_FIRST_HOUR = 7
DEFAULT_LAST_HOUR = 18
DEFAULT_WEEKDAYS = frozenset(range(6))  # Monday to Saturday

_DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ScheduleError(ValueError):
    pass


def parse_weekdays(value: str) -> frozenset[int]:
    """Accept 'mon-sat', 'mon,wed,fri' or a mix of both."""
    days: set[int] = set()
    for part in value.replace(" ", "").lower().split(","):
        if not part:
            continue
        if "-" in part:
            start, _, end = part.partition("-")
            try:
                first, last = _DAY_NAMES.index(start), _DAY_NAMES.index(end)
            except ValueError as error:
                raise ScheduleError(f"Unknown day in '{part}'") from error
            span = range(first, last + 1) if first <= last else [*range(first, 7), *range(last + 1)]
            days.update(span)
        else:
            try:
                days.add(_DAY_NAMES.index(part))
            except ValueError as error:
                raise ScheduleError(f"Unknown day '{part}'") from error
    if not days:
        raise ScheduleError("At least one weekday is required")
    return frozenset(days)


@dataclass(frozen=True, slots=True)
class Schedule:
    """Hourly slots inside a daily window, on selected weekdays."""

    timezone: ZoneInfo
    first_hour: int = DEFAULT_FIRST_HOUR
    last_hour: int = DEFAULT_LAST_HOUR
    weekdays: frozenset[int] = DEFAULT_WEEKDAYS

    def __post_init__(self) -> None:
        if not 0 <= self.first_hour <= 23 or not 0 <= self.last_hour <= 23:
            raise ScheduleError("Hours must be between 0 and 23")
        if self.first_hour > self.last_hour:
            raise ScheduleError("The first hour cannot come after the last hour")

    @classmethod
    def build(
        cls,
        timezone: str = DEFAULT_TIMEZONE,
        first_hour: int = DEFAULT_FIRST_HOUR,
        last_hour: int = DEFAULT_LAST_HOUR,
        weekdays: frozenset[int] = DEFAULT_WEEKDAYS,
    ) -> Schedule:
        try:
            zone = ZoneInfo(timezone)
        except Exception as error:
            raise ScheduleError(f"Unknown timezone '{timezone}'") from error
        return cls(zone, first_hour, last_hour, weekdays)

    def local(self, moment: datetime) -> datetime:
        return moment.astimezone(self.timezone)

    def is_open(self, moment: datetime) -> bool:
        here = self.local(moment)
        return here.weekday() in self.weekdays and self.first_hour <= here.hour <= self.last_hour

    def next_slot(self, after: datetime) -> datetime:
        """First slot strictly after the given moment."""
        here = self.local(after).replace(minute=0, second=0, microsecond=0)
        # A week of hours is always enough to reach the next open slot.
        for step in range(1, 24 * 7 + 1):
            candidate = here + timedelta(hours=step)
            if self.is_open(candidate):
                return candidate
        raise ScheduleError("The schedule never opens")

    def seconds_until(self, slot: datetime, now: datetime) -> float:
        return max((slot - now).total_seconds(), 0.0)

    def describe(self) -> str:
        days = ", ".join(_DAY_NAMES[day].capitalize() for day in sorted(self.weekdays))
        return f"{self.first_hour:02d}:00-{self.last_hour:02d}:00 {self.timezone.key} on {days}"
