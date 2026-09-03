from pathlib import Path

import pytest

from ethiopian_jobs.client import TelegramError, TelegramUncertain
from ethiopian_jobs.models import JobPost, PostKind
from ethiopian_jobs.service import FloodGuard, deliver, name_list, scrape
from ethiopian_jobs.storage import SentStore


def post(position: str) -> JobPost:
    return JobPost(
        kind=PostKind.RESULT,
        position=position,
        location="Head Office",
        detail="Interview",
        source_url="https://example.com/results",
    )


class FakeTelegram:
    def __init__(self, failing_position: str | None = None) -> None:
        self.sent: list[JobPost] = []
        self.documents: list[object] = []
        self.failing_position = failing_position

    def send(self, item: JobPost, document: object = None) -> None:
        self.documents.append(document)
        if item.position == self.failing_position:
            raise TelegramError("test failure")
        self.sent.append(item)


def test_delivery_marks_only_confirmed_messages(tmp_path: Path) -> None:
    good = post("Driver I")
    failed = post("Industrial Nurse")
    telegram = FakeTelegram(failing_position=failed.position)

    with SentStore(tmp_path / "jobs.db") as store:
        summary = deliver([good, failed], store, telegram)  # type: ignore[arg-type]
        assert summary.sent == 1
        assert summary.failed == 1
        assert store.unseen([good, failed]) == [failed]


class UncertainTelegram:
    def __init__(self) -> None:
        self.attempts = 0

    def send(self, item: JobPost, document: object = None) -> None:
        self.attempts += 1
        raise TelegramUncertain("connection dropped")


def test_unconfirmed_delivery_is_never_retried(tmp_path: Path) -> None:
    item = post("Driver I")
    telegram = UncertainTelegram()

    with SentStore(tmp_path / "jobs.db") as store:
        summary = deliver([item], store, telegram)  # type: ignore[arg-type]
        assert summary.uncertain == 1
        assert summary.sent == 0
        assert store.unseen([item]) == []

        deliver([item], store, telegram)  # type: ignore[arg-type]
        assert telegram.attempts == 1


def test_failed_send_is_offered_again(tmp_path: Path) -> None:
    item = post("Industrial Nurse")
    telegram = FakeTelegram(failing_position=item.position)

    with SentStore(tmp_path / "jobs.db") as store:
        deliver([item], store, telegram)  # type: ignore[arg-type]
        assert store.unseen([item]) == [item]


def test_inline_name_list_becomes_a_pdf_attachment() -> None:
    item = JobPost(
        kind=PostKind.RESULT,
        position="Spa Therapist",
        location="Head Office",
        detail="Interview",
        source_url="https://example.com/results#panel_0",
        candidate_rows=(("SER NO.", "FULL NAME"), ("1", "Abebe K."), ("2", "Sara T.")),
    )
    filename, content = name_list(item, None)
    assert filename == "spa-therapist-name-list.pdf"
    assert content.startswith(b"%PDF-")


def test_a_card_without_a_name_list_sends_no_file() -> None:
    assert name_list(post("Driver I"), None) is None


def test_flood_guard_blocks_a_run_with_a_lost_history(tmp_path: Path) -> None:
    items = [post(f"Driver {number}") for number in range(5)]
    telegram = FakeTelegram()

    with SentStore(tmp_path / "jobs.db") as store:
        with pytest.raises(FloodGuard):
            deliver(items, store, telegram, limit=3)  # type: ignore[arg-type]
        assert telegram.sent == []
        assert len(store.unseen(items)) == 5


def test_flood_guard_allows_a_normal_run(tmp_path: Path) -> None:
    items = [post(f"Driver {number}") for number in range(3)]
    telegram = FakeTelegram()

    with SentStore(tmp_path / "jobs.db") as store:
        assert deliver(items, store, telegram, limit=12).sent == 3  # type: ignore[arg-type]


class FakeSource:
    def __init__(self, vacancies_html: str, results_html: str | None = None) -> None:
        self._v = vacancies_html
        self._r = results_html

    def get(self, url: str) -> str:
        if "vacancies" in url:
            return self._v
        if self._r is None:
            raise RuntimeError("Results page down")
        return self._r


def test_scrape_survives_partial_page_failure(fixture_dir: Path) -> None:
    vacancies_html = (fixture_dir / "vacancies.html").read_text()
    source = FakeSource(vacancies_html=vacancies_html, results_html=None)
    posts = scrape(source)  # type: ignore[arg-type]
    assert len(posts) == 1
    assert posts[0].position == "Driver I"


def test_scrape_raises_when_both_pages_fail() -> None:
    class FailingSource:
        def get(self, url: str) -> str:
            raise RuntimeError("Site unreachable")

    with pytest.raises(RuntimeError, match="Site unreachable"):
        scrape(FailingSource())  # type: ignore[arg-type]
