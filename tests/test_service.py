from pathlib import Path

from ethiopian_jobs.client import TelegramError, TelegramUncertain
from ethiopian_jobs.models import JobPost, PostKind
from ethiopian_jobs.service import deliver
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
        self.failing_position = failing_position

    def send(self, item: JobPost) -> None:
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

    def send(self, item: JobPost) -> None:
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
