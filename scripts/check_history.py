"""Refuse to run when the restored delivery history looks wrong.

Used by the scheduled workflow. A missing or damaged history would make every
current posting look new, and the channel would get all of them again.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else "data/jobs.db")
    if not path.exists():
        print("No history file yet. The flood guard will stop a mass send.")
        return 0

    connection = sqlite3.connect(path)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            print("The restored history is corrupt.", file=sys.stderr)
            return 1
        rows = connection.execute("SELECT count(*) FROM sent_posts").fetchone()[0]
    except sqlite3.DatabaseError as error:
        print(f"The restored history is unreadable: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()

    if rows == 0:
        print("The restored history is empty.", file=sys.stderr)
        return 1
    print(f"History holds {rows} delivered posts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
