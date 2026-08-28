import json

import httpx
import pytest

from ethiopian_jobs.client import TelegramClient, TelegramError, TelegramUncertain
from ethiopian_jobs.models import JobPost, PostKind


def make_post() -> JobPost:
    return JobPost(
        kind=PostKind.VACANCY,
        position="Driver I",
        location="Head Office",
        detail="July 13 to 17",
        source_url="https://example.com/vacancies",
    )


def test_telegram_sends_expected_payload() -> None:
    received: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    with TelegramClient(
        "secret-token", "@jobs", transport=httpx.MockTransport(handler)
    ) as telegram:
        telegram.send(make_post())

    assert received["chat_id"] == "@jobs"
    assert received["parse_mode"] == "HTML"
    assert "Driver I" in str(received["text"])


def test_telegram_retries_rate_limit_from_json() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={"ok": False, "parameters": {"retry_after": 3}},
            )
        return httpx.Response(200, json={"ok": True})

    with TelegramClient(
        "secret-token",
        "@jobs",
        sleep=delays.append,
        transport=httpx.MockTransport(handler),
    ) as telegram:
        telegram.send(make_post())

    assert calls == 2
    assert delays == [3.0]


def test_telegram_reports_non_retryable_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, json={"ok": False, "description": "Bad Request"})
    )
    with (
        TelegramClient("secret-token", "@jobs", transport=transport) as telegram,
        pytest.raises(TelegramError, match="Bad Request"),
    ):
        telegram.send(make_post())


def test_connect_failure_is_retried_then_reported_as_undelivered() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("no route", request=request)

    with (
        TelegramClient(
            "secret-token", "@jobs", sleep=lambda _: None,
            transport=httpx.MockTransport(handler),
        ) as telegram,
        pytest.raises(TelegramError, match="Could not reach Telegram"),
    ):
        telegram.send(make_post())

    assert calls == 4


def test_read_timeout_is_never_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("no answer", request=request)

    with (
        TelegramClient(
            "secret-token", "@jobs", sleep=lambda _: None,
            transport=httpx.MockTransport(handler),
        ) as telegram,
        pytest.raises(TelegramUncertain),
    ):
        telegram.send(make_post())

    # The request already left, so a second attempt could post the same job twice.
    assert calls == 1


def test_sends_are_paced_apart() -> None:
    ticks = iter([0.0, 1.0, 1.0])
    delays: list[float] = []
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))

    with TelegramClient(
        "secret-token", "@jobs", send_gap=3.0, sleep=delays.append,
        clock=lambda: next(ticks), transport=transport,
    ) as telegram:
        telegram.send(make_post())
        telegram.send(make_post())

    assert delays == [2.0]
