from pathlib import Path

import pytest

from ethiopian_jobs.models import JobPost, PostKind
from ethiopian_jobs.storage import AlreadyRunningError, RunLock, SentStore


def make_post(detail: str = "July 13 to 17") -> JobPost:
    return JobPost(
        kind=PostKind.VACANCY,
        position="Driver I",
        location="Head Office",
        detail=detail,
        source_url="https://example.com/vacancies",
    )


def test_sent_post_is_not_returned_again(tmp_path: Path) -> None:
    post = make_post()
    with SentStore(tmp_path / "jobs.db") as store:
        assert store.unseen([post]) == [post]
        store.mark_many([post])
        assert store.unseen([post]) == []


def test_material_update_is_offered_again(tmp_path: Path) -> None:
    original = make_post()
    updated = make_post("July 13 to 20")
    with SentStore(tmp_path / "jobs.db") as store:
        store.mark_many([original])
        assert store.unseen([original, updated]) == [updated]


def test_cosmetic_edits_never_resend(tmp_path: Path) -> None:
    original = make_post("July 13, 2026 to July 17, 2026")
    retyped = make_post("July 13,2026  to  July 17 ,2026")
    with SentStore(tmp_path / "jobs.db") as store:
        store.mark_many([original])
        assert store.unseen([retyped]) == []


def test_in_batch_duplicates_are_collapsed(tmp_path: Path) -> None:
    post = make_post()
    with SentStore(tmp_path / "jobs.db") as store:
        assert store.unseen([post, make_post(), post]) == [post]


def test_claim_is_taken_once(tmp_path: Path) -> None:
    post = make_post()
    with SentStore(tmp_path / "jobs.db") as store:
        assert store.claim(post) is True
        assert store.claim(post) is False
        assert store.unseen([post]) == []


def test_released_claim_is_offered_again(tmp_path: Path) -> None:
    post = make_post()
    with SentStore(tmp_path / "jobs.db") as store:
        store.claim(post)
        store.release(post)
        assert store.unseen([post]) == [post]


def test_interrupted_claim_is_never_resent(tmp_path: Path) -> None:
    post = make_post()
    database = tmp_path / "jobs.db"
    with SentStore(database) as store:
        store.claim(post)
    with SentStore(database) as store:
        assert store.settle_interrupted() == 1
        assert store.unseen([post]) == []


def test_changed_source_card_is_not_missed_when_headline_is_unchanged(tmp_path: Path) -> None:
    original = make_post()
    original = JobPost(
        kind=original.kind,
        position=original.position,
        location=original.location,
        detail=original.detail,
        source_url=original.source_url,
        source_key="Interview on Monday; candidate A",
    )
    updated = JobPost(
        kind=original.kind,
        position=original.position,
        location=original.location,
        detail=original.detail,
        source_url=original.source_url,
        source_key="Interview on Tuesday; candidate B",
    )
    with SentStore(tmp_path / "jobs.db") as store:
        store.mark_many([original])
        assert store.unseen([original, updated]) == [updated]


def test_run_lock_rejects_overlapping_process(tmp_path: Path) -> None:
    database = tmp_path / "jobs.db"
    with RunLock(database), pytest.raises(AlreadyRunningError), RunLock(database):
        pass
