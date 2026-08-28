from __future__ import annotations

import fcntl
import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from ethiopian_jobs.models import JobPost

logger = logging.getLogger(__name__)

# Comfortably below SQLite's variable limit, so even a huge scrape needs few queries.
_QUERY_CHUNK = 400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sent_posts (
    content_key TEXT PRIMARY KEY,
    identity    TEXT NOT NULL,
    kind        TEXT NOT NULL,
    position    TEXT NOT NULL,
    payload     TEXT NOT NULL,
    status      TEXT NOT NULL,
    claimed_at  TEXT NOT NULL,
    sent_at     TEXT
);
CREATE INDEX IF NOT EXISTS sent_posts_identity ON sent_posts (identity);
"""

_CLAIM = """
    INSERT OR IGNORE INTO sent_posts
        (content_key, identity, kind, position, payload, status, claimed_at, sent_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


class AlreadyRunningError(RuntimeError):
    pass


class RunLock(AbstractContextManager["RunLock"]):
    """Stop overlapping processes from sending the same unseen post."""

    def __init__(self, database_path: Path) -> None:
        lock_path = database_path.with_suffix(database_path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = lock_path.open("a+")

    def __enter__(self) -> RunLock:
        try:
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._file.close()
            raise AlreadyRunningError("another notifier process is already running") from error
        return self

    def close(self) -> None:
        fcntl.flock(self._file, fcntl.LOCK_UN)
        self._file.close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _chunks(values: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(values), _QUERY_CHUNK):
        yield values[start : start + _QUERY_CHUNK]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SentStore(AbstractContextManager["SentStore"]):
    """Delivery history. A post recorded here is never sent a second time."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, timeout=30)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._retire_legacy_table()
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def _retire_legacy_table(self) -> None:
        """The 1.0 table keyed posts differently, so its rows can no longer be matched."""
        tables = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sent_posts'"
        ).fetchone()
        if not tables:
            return
        columns = {row[1] for row in self._connection.execute("PRAGMA table_info(sent_posts)")}
        if "content_key" in columns:
            return
        self._connection.execute("ALTER TABLE sent_posts RENAME TO sent_posts_v1")
        self._connection.commit()
        logger.warning(
            "Upgraded the database schema. Run 'ethiopian-jobs prime' once "
            "to adopt the current postings without resending them."
        )

    def unseen(self, posts: Iterable[JobPost]) -> list[JobPost]:
        """Posts with no history row, in order, with in-batch duplicates removed."""
        candidates: dict[str, JobPost] = {}
        for post in posts:
            candidates.setdefault(post.content_key, post)
        if not candidates:
            return []

        known: set[str] = set()
        for chunk in _chunks(list(candidates)):
            placeholders = ",".join("?" * len(chunk))
            rows = self._connection.execute(
                f"SELECT content_key FROM sent_posts WHERE content_key IN ({placeholders})",
                chunk,
            )
            known.update(row[0] for row in rows)
        return [post for key, post in candidates.items() if key not in known]

    def is_update(self, post: JobPost) -> bool:
        """True when this posting was seen before with different content."""
        row = self._connection.execute(
            "SELECT 1 FROM sent_posts WHERE identity = ? LIMIT 1", (post.identity,)
        ).fetchone()
        return row is not None

    @staticmethod
    def _payload(post: JobPost) -> str:
        # The card body is deliberately left out. It is already folded into the
        # content key, and one result page carried three quarters of a megabyte.
        return json.dumps(
            {
                "position": post.position,
                "location": post.location,
                "detail": post.detail,
                "source_url": post.source_url,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def claim(self, post: JobPost) -> bool:
        """Reserve a post before sending. False means another run already has it."""
        now = _now()
        cursor = self._connection.execute(
            _CLAIM,
            (
                post.content_key,
                post.identity,
                post.kind.value,
                post.position,
                self._payload(post),
                "pending",
                now,
                None,
            ),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def confirm(self, post: JobPost) -> None:
        self._connection.execute(
            "UPDATE sent_posts SET status = 'sent', sent_at = ? WHERE content_key = ?",
            (_now(), post.content_key),
        )
        self._connection.commit()

    def release(self, post: JobPost) -> None:
        """Undo a claim that never reached Telegram, so the next run retries it."""
        self._connection.execute(
            "DELETE FROM sent_posts WHERE content_key = ? AND status = 'pending'",
            (post.content_key,),
        )
        self._connection.commit()

    def settle_interrupted(self) -> int:
        """A claim left behind by a killed process may already have reached Telegram.

        Treat it as delivered. Losing one notice beats posting it twice.
        """
        cursor = self._connection.execute(
            "UPDATE sent_posts SET status = 'sent', sent_at = ? WHERE status = 'pending'",
            (_now(),),
        )
        self._connection.commit()
        if cursor.rowcount:
            logger.warning(
                "Closed %d claim(s) left by an interrupted run; they will not be resent",
                cursor.rowcount,
            )
        return cursor.rowcount

    def mark_many(self, posts: Iterable[JobPost]) -> int:
        now = _now()
        rows = [
            (
                post.content_key,
                post.identity,
                post.kind.value,
                post.position,
                self._payload(post),
                "sent",
                now,
                now,
            )
            for post in posts
        ]
        if not rows:
            return 0
        before = self._connection.total_changes
        self._connection.executemany(_CLAIM, rows)
        self._connection.commit()
        return self._connection.total_changes - before

    def close(self) -> None:
        self._connection.close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
