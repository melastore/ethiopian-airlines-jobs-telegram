from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime

from ethiopian_jobs.client import SourceClient, TelegramClient
from ethiopian_jobs.config import ConfigError, Settings
from ethiopian_jobs.formatting import format_telegram
from ethiopian_jobs.models import JobPost
from ethiopian_jobs.service import FloodGuard, RunSummary, deliver, scrape
from ethiopian_jobs.storage import AlreadyRunningError, RunLock, SentStore

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ethiopian-jobs",
        description="Post Ethiopian Airlines local vacancies and recruitment results to Telegram.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="check once and send unseen posts")
    subparsers.add_parser("watch", help="check every hour inside the configured window")
    subparsers.add_parser("check", help="scrape and print posts without sending or saving")
    subparsers.add_parser("prime", help="mark current posts as seen without sending")
    subparsers.add_parser("schedule", help="print the next few run times and exit")
    return parser


class _Redactor(logging.Filter):
    """Keep the bot token out of the logs. Its URL carries it in plain sight."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secret:
            record.msg = str(record.msg).replace(self._secret, "***")
            if record.args:
                record.args = tuple(
                    str(arg).replace(self._secret, "***") if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx logs every request URL at INFO, and the Telegram URL contains the token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    redactor = _Redactor(settings.telegram_bot_token)
    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)


def _scrape(settings: Settings) -> list[JobPost]:
    with SourceClient(settings.request_timeout) as source:
        return scrape(source)


def _run_once(settings: Settings) -> RunSummary:
    with RunLock(settings.database_path), SourceClient(settings.request_timeout) as source:
        posts = scrape(source)
        with (
            SentStore(settings.database_path) as store,
            TelegramClient(
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                settings.request_timeout,
                settings.send_gap,
            ) as telegram,
        ):
            summary = deliver(posts, store, telegram, source, settings.max_posts_per_run)
    logger.info("Run complete: %s", summary)
    return summary


def _watch(settings: Settings) -> int:
    schedule = settings.schedule
    logger.info("Watching %s", schedule.describe())
    if schedule.is_open(datetime.now(tz=schedule.timezone)):
        _safe_run(settings)
    while True:
        now = datetime.now(tz=schedule.timezone)
        slot = schedule.next_slot(now)
        logger.info("Next check at %s", slot.strftime("%a %Y-%m-%d %H:%M %Z"))
        time.sleep(schedule.seconds_until(slot, now))
        _safe_run(settings)


def _safe_run(settings: Settings) -> None:
    try:
        _run_once(settings)
    except AlreadyRunningError as error:
        logger.warning("Skipping this slot: %s", error)
    except Exception:
        logger.exception("Check failed, the watcher will try again at the next slot")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    require_telegram = args.command in {"run", "watch"}
    try:
        settings = Settings.from_env(require_telegram=require_telegram)
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    _configure_logging(settings)

    try:
        if args.command == "check":
            for post in _scrape(settings):
                print(format_telegram(post), "\n")
            return 0

        if args.command == "schedule":
            moment = datetime.now(tz=settings.schedule.timezone)
            print(settings.schedule.describe())
            for _ in range(8):
                moment = settings.schedule.next_slot(moment)
                print(moment.strftime("%a %Y-%m-%d %H:%M %Z"))
            return 0

        if args.command == "prime":
            with RunLock(settings.database_path):
                posts = _scrape(settings)
                with SentStore(settings.database_path) as store:
                    added = store.mark_many(posts)
            logger.info("Primed %d posts (%d already known)", added, len(posts) - added)
            return 0

        if args.command == "run":
            summary = _run_once(settings)
            return 1 if summary.failed else 0

        return _watch(settings)
    except FloodGuard as error:
        logger.error("Refusing to send: %s", error)
        return 4
    except AlreadyRunningError as error:
        print(f"{error}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        logger.info("Stopped")
        return 130
    except Exception:
        logger.exception("Command failed")
        return 1
