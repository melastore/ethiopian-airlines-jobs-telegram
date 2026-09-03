from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from ethiopian_jobs.client import DEFAULT_SEND_GAP
from ethiopian_jobs.schedule import (
    DEFAULT_TIMEZONE,
    Schedule,
    ScheduleError,
    parse_weekdays,
)

_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class ConfigError(ValueError):
    pass


def _whole_number(name: str, default: str) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError as error:
        raise ConfigError(f"{name} must be a whole number") from error
    if value < 0:
        raise ConfigError(f"{name} cannot be negative")
    return value


def _positive_float(name: str, default: str) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError as error:
        raise ConfigError(f"{name} must be a number") from error
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return value


def _hour_window(name: str, default: str) -> tuple[int, int]:
    raw = os.getenv(name, default).strip()
    first, separator, last = raw.partition("-")
    if not separator:
        raise ConfigError(f"{name} must look like '7-18'")
    try:
        window = int(first), int(last)
    except ValueError as error:
        raise ConfigError(f"{name} must use whole hours, for example '7-18'") from error
    return window


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    database_path: Path
    request_timeout: float
    send_gap: float
    max_posts_per_run: int
    schedule: Schedule
    log_level: str

    @classmethod
    def from_env(cls, *, require_telegram: bool = True) -> Settings:
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if require_telegram and (not token or not chat_id):
            raise ConfigError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in _LOG_LEVELS:
            raise ConfigError(f"LOG_LEVEL must be one of {', '.join(sorted(_LOG_LEVELS))}")

        first_hour, last_hour = _hour_window("ACTIVE_HOURS", "0-23")
        try:
            schedule = Schedule.build(
                timezone=os.getenv("SCHEDULE_TIMEZONE", DEFAULT_TIMEZONE).strip(),
                first_hour=first_hour,
                last_hour=last_hour,
                weekdays=parse_weekdays(os.getenv("ACTIVE_DAYS", "mon-sun")),
                step_hours=_whole_number("CHECK_EVERY_HOURS", "2") or 1,
            )
        except ScheduleError as error:
            raise ConfigError(str(error)) from error

        return cls(
            telegram_bot_token=token,
            telegram_chat_id=chat_id,
            database_path=Path(os.getenv("DATABASE_PATH", "data/jobs.db")).expanduser(),
            request_timeout=_positive_float("REQUEST_TIMEOUT_SECONDS", "30"),
            send_gap=_positive_float("SEND_GAP_SECONDS", str(DEFAULT_SEND_GAP)),
            max_posts_per_run=_whole_number("MAX_POSTS_PER_RUN", "25"),
            schedule=schedule,
            log_level=log_level,
        )
