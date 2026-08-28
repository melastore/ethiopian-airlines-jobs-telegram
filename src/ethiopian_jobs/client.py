from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress

import httpx

from ethiopian_jobs.formatting import format_telegram
from ethiopian_jobs.models import JobPost

USER_AGENT = "EthiopianJobsTelegram/1.1 (+careers notifier)"
MAX_ATTEMPTS = 4
# Telegram allows roughly 20 messages a minute to a channel. Stay under it so a
# large first run is not throttled into a pile of retries.
DEFAULT_SEND_GAP = 3.5


class SourceClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            transport=httpx.HTTPTransport(retries=2),
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )

    def get(self, url: str) -> str:
        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SourceClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class TelegramError(RuntimeError):
    """The message did not reach Telegram. Safe to try again on the next run."""


class TelegramUncertain(RuntimeError):
    """The request may have been processed. Resending it risks a duplicate."""


class TelegramClient:
    def __init__(
        self,
        token: str,
        chat_id: str,
        timeout: float = 30.0,
        send_gap: float = DEFAULT_SEND_GAP,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._send_gap = send_gap
        self._sleep = sleep
        self._clock = clock
        self._last_send: float | None = None
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
        )

    @staticmethod
    def _body(response: httpx.Response) -> dict:
        with suppress(ValueError):
            body = response.json()
            if isinstance(body, dict):
                return body
        return {}

    @classmethod
    def _retry_delay(cls, response: httpx.Response, attempt: int, body: dict) -> float:
        delay: float | None = None
        parameters = body.get("parameters")
        if isinstance(parameters, dict):
            with suppress(ValueError, TypeError, KeyError):
                delay = float(parameters["retry_after"])
        if delay is None:
            with suppress(ValueError, TypeError, KeyError):
                delay = float(response.headers["Retry-After"])
        return min(delay if delay is not None else 2**attempt, 30.0)

    def _pace(self) -> None:
        if self._last_send is None:
            return
        waiting = self._send_gap - (self._clock() - self._last_send)
        if waiting > 0:
            self._sleep(waiting)

    def send(self, post: JobPost) -> None:
        payload = {
            "chat_id": self._chat_id,
            "text": format_telegram(post),
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        self._pace()
        for attempt in range(MAX_ATTEMPTS):
            last = attempt == MAX_ATTEMPTS - 1
            try:
                response = self._client.post(self._url, json=payload)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Nothing left the machine, so retrying cannot duplicate anything.
                if last:
                    raise TelegramError("Could not reach Telegram") from None
                self._sleep(2**attempt)
                continue
            except httpx.RequestError as error:
                # The request was already on the wire. Telegram may have posted it.
                raise TelegramUncertain(f"No answer from Telegram: {error!r}") from None
            finally:
                self._last_send = self._clock()

            body = self._body(response)
            if response.is_success and body.get("ok") is True:
                return

            if (response.status_code == 429 or response.status_code >= 500) and not last:
                self._sleep(self._retry_delay(response, attempt, body))
                continue

            description = body.get("description") or "Telegram rejected the message"
            raise TelegramError(f"{description} (HTTP {response.status_code})")

        raise TelegramError("Telegram delivery failed")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TelegramClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
