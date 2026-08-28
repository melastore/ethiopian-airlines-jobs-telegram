from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ethiopian_jobs.client import SourceClient, TelegramClient, TelegramError, TelegramUncertain
from ethiopian_jobs.models import JobPost
from ethiopian_jobs.parser import (
    RESULTS_URL,
    VACANCIES_URL,
    parse_local_vacancies,
    parse_results,
)
from ethiopian_jobs.storage import SentStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunSummary:
    found: int
    new: int
    sent: int
    failed: int
    uncertain: int = 0

    def __str__(self) -> str:
        return (
            f"found={self.found} new={self.new} sent={self.sent} "
            f"failed={self.failed} uncertain={self.uncertain}"
        )


def scrape(source: SourceClient) -> list[JobPost]:
    # The two pages are independent, so fetch them together.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="scrape") as pool:
        vacancies_html = pool.submit(source.get, VACANCIES_URL)
        results_html = pool.submit(source.get, RESULTS_URL)
        vacancies = parse_local_vacancies(vacancies_html.result())
        results = parse_results(results_html.result())
    return [*vacancies, *results]


def deliver(posts: list[JobPost], store: SentStore, telegram: TelegramClient) -> RunSummary:
    """Send every post that has never been delivered.

    Each post is claimed in the database before it is sent. A claim that is never
    resolved counts as delivered, because a duplicate notice is worse than a
    missing one and Telegram gives us no way to ask.
    """
    store.settle_interrupted()
    unseen = store.unseen(posts)
    sent = 0
    failed = 0
    uncertain = 0

    for post in unseen:
        update = store.is_update(post)
        if not store.claim(post):
            logger.debug("Skipping %s, another run already claimed it", post.label)
            continue
        try:
            telegram.send(post)
        except TelegramError as error:
            store.release(post)
            failed += 1
            logger.error("Could not post %s: %s", post.label, error)
            continue
        except TelegramUncertain as error:
            uncertain += 1
            logger.error("Delivery of %s is unconfirmed, not retrying: %s", post.label, error)
            continue
        store.confirm(post)
        sent += 1
        logger.info("Posted %s %s", "updated" if update else "new", post.label)

    return RunSummary(
        found=len(posts), new=len(unseen), sent=sent, failed=failed, uncertain=uncertain
    )
